from datetime import datetime, date
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.db.models import ScrapBatch, Actor
import uuid


ALLOWED_BATCH_OWNER_ROLES = {"haendler", "stahlwerk"}


def ensure_valid_batch_owner(db: Session, owner_id: str) -> Actor:
    owner = db.query(Actor).filter(Actor.id == owner_id).first()
    if not owner:
        raise ValueError("Zugeordneter Akteur für die Charge wurde nicht gefunden.")
    if owner.role not in ALLOWED_BATCH_OWNER_ROLES:
        raise ValueError("Eine Charge muss einem Händler oder Stahlwerk zugewiesen sein.")
    return owner


def get_all_batches(db: Session) -> list:
    return db.query(ScrapBatch).order_by(ScrapBatch.created_at.desc()).all()


def get_batch_by_id(db: Session, batch_id: str):
    return db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()


def get_batch_by_number(db: Session, batch_number: str):
    return db.query(ScrapBatch).filter(ScrapBatch.batch_number == batch_number).first()


def get_batches_by_owner(db: Session, owner_id: str) -> list:
    return (
        db.query(ScrapBatch)
        .filter(ScrapBatch.owner_id == owner_id)
        .order_by(ScrapBatch.created_at.desc())
        .all()
    )


def create_batch(
    db: Session,
    batch_number: str,
    scrap_class: str,
    origin_type: str,
    mass_kg: float,
    owner_id: str,
    volume_m3: float = None,
    processing_degree: str = None,
    supplier_source: str = None,
    price_per_ton: float = None,
    origin_region: str = None,
    supplier_id: str = None,
    collection_period: str = None,
    preparation_degree: str = None,
    contamination_level: str = None,
    price_basis: str = None,
    pricing_formula_ref: str = None,
) -> ScrapBatch:
    ensure_valid_batch_owner(db, owner_id)
    batch = ScrapBatch(
        id=str(uuid.uuid4()),
        batch_number=batch_number,
        scrap_class=scrap_class,
        origin_type=origin_type,
        mass_kg=mass_kg,
        volume_m3=volume_m3,
        processing_degree=processing_degree,
        supplier_source=supplier_source,
        price_per_ton=price_per_ton,
        origin_region=origin_region,
        supplier_id=supplier_id,
        collection_period=collection_period,
        preparation_degree=preparation_degree,
        contamination_level=contamination_level,
        price_basis=price_basis,
        pricing_formula_ref=pricing_formula_ref,
        owner_id=owner_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def batch_to_dict(batch: ScrapBatch) -> dict:
    """
    Konvertiert eine ScrapBatch-Instanz in ein Dict mit ALLEN ABAC-relevanten Feldern.
    Dieses Dict ist die Grundlage für die Casbin-Filterung in der ABAC-Engine.
    """
    return {
        # Basisfelder
        "batch_number": batch.batch_number,
        "scrap_class": batch.scrap_class,
        "origin_type": batch.origin_type,
        "mass_kg": batch.mass_kg,
        "volume_m3": batch.volume_m3,
        "eaf_compatibility": batch.eaf_compatibility,
        # Provenienzdaten
        "origin_region": batch.origin_region,
        "collection_period": batch.collection_period,
        "preparation_degree": batch.preparation_degree,
        "contamination_level": batch.contamination_level,
        # Wirtschaftliche Felder (Hoheitswissen des Händlers)
        "price_basis": batch.price_basis,
        "pricing_formula_ref": batch.pricing_formula_ref,
        # Lieferantenreferenz (niemals an Dritte)
        "supplier_id": batch.supplier_id,
        # Legacy-Felder (abwärtskompatibel)
        "processing_degree": batch.processing_degree,
        "supplier_source": batch.supplier_source,
        "price_per_ton": batch.price_per_ton,
    }


def batch_to_workflow_dict(batch: ScrapBatch) -> dict:
    """Erweitertes Dict inkl. Workflow-Status-Felder für den Händler→Stahlwerk-Prozess."""
    base = batch_to_dict(batch)
    base.update({
        "id": batch.id,
        "status": batch.workflow_status,
        "created_by_trader_id": batch.created_by_trader_id,
        "offered_to_steel_mill_id": batch.offered_to_steel_mill_id,
        "delivery_date": batch.delivery_date.isoformat() if batch.delivery_date else None,
        "confirmed_by_trader": batch.confirmed_by_trader,
        "confirmed_by_steel_mill": batch.confirmed_by_steel_mill,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "owner_id": batch.owner_id,
    })
    return base


def get_batches_for_trader(db: Session, trader_id: str) -> list:
    """Alle Chargen die diesem Händler zugeordnet sind oder von ihm angelegt wurden."""
    return (
        db.query(ScrapBatch)
        .filter(
            or_(
                ScrapBatch.created_by_trader_id == trader_id,
                ScrapBatch.owner_id == trader_id,
            )
        )
        .order_by(ScrapBatch.created_at.desc())
        .all()
    )


def get_batches_for_steel_mill(db: Session, steel_mill_id: str) -> list:
    """Chargen die diesem Stahlwerk angeboten wurden oder zugewiesen sind."""
    return (
        db.query(ScrapBatch)
        .filter(
            ScrapBatch.offered_to_steel_mill_id == steel_mill_id,
            ScrapBatch.workflow_status.in_(["angeboten", "zugewiesen", "geliefert"]),
        )
        .order_by(ScrapBatch.created_at.desc())
        .all()
    )


def create_trader_batch(
    db: Session,
    scrap_class: str,
    origin_type: str,
    mass_kg: float,
    trader_id: str,
    preparation_degree: str = None,
    contamination_level: str = None,
    origin_region: str = None,
    collection_period: str = None,
) -> ScrapBatch:
    """Legt eine neue Charge an, die vom Händler aus Containerabholungen zusammengestellt wurde."""
    ensure_valid_batch_owner(db, trader_id)
    year = datetime.utcnow().year
    prefix = f"CH-{year}-"
    existing_numbers = [
        row[0]
        for row in db.query(ScrapBatch.batch_number)
        .filter(ScrapBatch.batch_number.like(f"{prefix}%"))
        .all()
        if row[0]
    ]
    existing_sequences = []
    for number in existing_numbers:
        suffix = number.removeprefix(prefix)
        if suffix.isdigit():
            existing_sequences.append(int(suffix))
    next_sequence = max(existing_sequences, default=0) + 1
    batch_number = f"{prefix}{next_sequence:03d}"

    batch = ScrapBatch(
        id=str(uuid.uuid4()),
        batch_number=batch_number,
        scrap_class=scrap_class,
        origin_type=origin_type,
        mass_kg=mass_kg,
        owner_id=trader_id,
        created_by_trader_id=trader_id,
        preparation_degree=preparation_degree,
        contamination_level=contamination_level,
        origin_region=origin_region,
        collection_period=collection_period,
        workflow_status="entwurf",
        confirmed_by_trader=False,
        confirmed_by_steel_mill=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch
