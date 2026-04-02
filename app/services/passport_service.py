from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models import MaterialPassport, TraceabilityEvent, QualityAnalysis
import uuid


def get_passport_for_batch(db: Session, batch_id: str):
    """Gibt den neuesten Materialpass für eine Charge zurück."""
    return (
        db.query(MaterialPassport)
        .filter(MaterialPassport.batch_id == batch_id)
        .order_by(MaterialPassport.version.desc())
        .first()
    )


def get_passport_by_id(db: Session, passport_id: str):
    return db.query(MaterialPassport).filter(MaterialPassport.id == passport_id).first()


def get_all_passports(db: Session) -> list:
    return db.query(MaterialPassport).order_by(MaterialPassport.created_at.desc()).all()


def create_passport(
    db: Session,
    batch_id: str,
    issuer_id: str,
    validation_status: str = "entwurf",
    certification_ref: str = None,
) -> MaterialPassport:
    existing = get_passport_for_batch(db, batch_id)
    version = (existing.version + 1) if existing else 1

    passport = MaterialPassport(
        id=str(uuid.uuid4()),
        batch_id=batch_id,
        version=version,
        validation_status=validation_status,
        certification_ref=certification_ref,
        issuer_id=issuer_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(passport)
    db.commit()
    db.refresh(passport)
    return passport


def update_passport_status(
    db: Session,
    passport_id: str,
    validation_status: str,
    certification_ref: str = None,
) -> MaterialPassport:
    passport = get_passport_by_id(db, passport_id)
    if not passport:
        return None
    passport.validation_status = validation_status
    if certification_ref:
        passport.certification_ref = certification_ref
    passport.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(passport)
    return passport


def get_traceability_events(db: Session, batch_id: str) -> list:
    return (
        db.query(TraceabilityEvent)
        .filter(TraceabilityEvent.batch_id == batch_id)
        .order_by(TraceabilityEvent.timestamp.asc())
        .all()
    )


def create_traceability_event(
    db: Session,
    batch_id: str,
    event_type: str,
    actor_id: str,
    location: str = None,
    notes: str = None,
    epcis_type: str = "ObjectEvent",
    timestamp: datetime = None,
) -> TraceabilityEvent:
    if timestamp is None:
        timestamp = datetime.utcnow()
    event = TraceabilityEvent(
        id=str(uuid.uuid4()),
        batch_id=batch_id,
        event_type=event_type,
        timestamp=timestamp,
        actor_id=actor_id,
        location=location,
        notes=notes,
        epcis_type=epcis_type,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_quality_analysis(db: Session, batch_id: str):
    return (
        db.query(QualityAnalysis)
        .filter(QualityAnalysis.batch_id == batch_id)
        .order_by(QualityAnalysis.inspected_at.desc())
        .first()
    )
