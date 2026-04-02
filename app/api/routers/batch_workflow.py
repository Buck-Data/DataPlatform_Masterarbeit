"""
Router: Händler→Stahlwerk-Workflow (/workflow/batches)
======================================================
Verwaltet den Lebenszyklus einer ScrapBatch vom Händler-Entwurf bis zur
bestätigten Lieferung ans Stahlwerk.

Alle Endpunkte sind per ABAC-Engine abgesichert:
  - Händler: eigene Chargen anlegen, anbieten, Lieferung bestätigen
  - Stahlwerk: eingehende Angebote prüfen, annehmen/ablehnen, bestätigen
  - Metallverarbeiter: kein Zugriff (keine Policy-Regeln → 403)
"""
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    ScrapBatch, Actor, TraceabilityEvent,
    BatchSourcePickup, PickupHistoryEntry,
)
from app.services import batch_service, chemical_service
from app.abac.engine import get_abac_engine

router = APIRouter(prefix="/workflow/batches", tags=["Batch-Workflow"])

# Standard-Grenzwerte für Tramp-Elemente (EAF-Qualitätsanforderungen)
DEFAULT_THRESHOLDS = {"Cu": 0.35, "Sn": 0.10, "Ni": 0.15, "Cr": 0.20, "Mo": 0.05}


# ── Pydantic-Schemas ──────────────────────────────────────────────────────────

class BatchCreate(BaseModel):
    scrap_class: str
    origin_type: str
    mass_kg: float
    trader_id: str
    preparation_degree: Optional[str] = None
    contamination_level: Optional[str] = None
    origin_region: Optional[str] = None
    collection_period: Optional[str] = None
    source_pickup_ids: list[str] = []
    # Optionale chemische Zusammensetzung
    chemical_values: Optional[dict] = None


class BatchOffer(BaseModel):
    steel_mill_id: str
    delivery_date: date
    message: Optional[str] = None


class DeliveryConfirm(BaseModel):
    # "haendler" oder "stahlwerk" — wer bestätigt
    confirming_role: str
    actor_id: str


# ── Hilfsfunktion: ABAC-Zugriffsprüfung ──────────────────────────────────────

def _check_batch_workflow_access(role: str, action: str):
    """Wirft HTTP 403 wenn die Rolle keinen Zugriff auf die Aktion hat."""
    engine = get_abac_engine()
    if not engine.enforcer.enforce(role, "batch_workflow", "write", action) and \
       not engine.enforcer.enforce(role, "batch_workflow", "read", action):
        raise HTTPException(
            status_code=403,
            detail=f"Zugriff verweigert: Rolle '{role}' darf '{action}' nicht auf batch_workflow."
        )


def _batch_response(batch: ScrapBatch, db: Session, role: str = None, tier: str | None = None) -> dict:
    """Baut die vollständige Response-Struktur für eine Charge zusammen."""
    data = batch_service.batch_to_workflow_dict(batch)
    if role:
        engine = get_abac_engine()
        base_fields = batch_service.batch_to_dict(batch)
        if role == "stahlwerk":
            base_fields = engine.filter_batch_fields_tiered(role, tier, base_fields)
        else:
            base_fields = engine.filter_batch_fields(role, base_fields)
        data.update(base_fields)

    # Chemische Analyse (neueste) anhängen
    latest_chem = chemical_service.get_latest_composition(db, batch.id)
    if latest_chem:
        chem_data = {
            "element_values": latest_chem.element_values,
            "thresholds": latest_chem.thresholds,
            "threshold_exceeded": latest_chem.threshold_exceeded,
            "exceeded_elements": latest_chem.exceeded_elements,
            "analysis_method": latest_chem.analysis_method,
            "measured_at": latest_chem.measured_at.isoformat() if latest_chem.measured_at else None,
        }
        # ABAC-Filterung der Chemie-Felder
        if role:
            engine = get_abac_engine()
            if role == "stahlwerk":
                chem_data = engine.filter_chemical_fields_tiered(role, tier, chem_data)
            else:
                chem_data = engine.filter_chemical_fields(role, chem_data)
        data["chemical"] = chem_data
    else:
        data["chemical"] = None

    # Herkunfts-Provenienz: Containerabholungen verknüpft mit dieser Charge
    source_pickups = db.query(BatchSourcePickup).filter(
        BatchSourcePickup.batch_id == batch.id
    ).all()
    provenance = []
    for sp in source_pickups:
        entry = db.query(PickupHistoryEntry).filter(
            PickupHistoryEntry.id == sp.pickup_history_entry_id
        ).first()
        if entry:
            # Händler-interne Felder (container_id, trader_id) werden herausgefiltert
            # — Stahlwerk sieht nur was die ABAC-Policy erlaubt
            p = {
                "pickup_date": entry.completed_at.isoformat() if entry.completed_at else None,
                "scrap_type": entry.scrap_type,
                "estimated_volume_m3": entry.estimated_volume_m3,
                "fill_level_at_pickup": entry.fill_level_at_pickup,
            }
            # Trader/Container-IDs nur für den Händler selbst sichtbar
            if role in ("haendler", None):
                p["trader_id"] = entry.trader_id
                p["container_id"] = entry.container_id
            provenance.append(p)
    data["provenance_chain"] = provenance
    data["provenance_count"] = len(provenance)

    return data


# ── Endpunkte ─────────────────────────────────────────────────────────────────

@router.post("")
def create_batch(data: BatchCreate, db: Session = Depends(get_db)):
    """Händler legt eine neue Charge aus Containerabholungen an.
    ABAC: nur haendler darf create_batch.
    """
    # Akteur laden und Rolle prüfen
    trader = db.query(Actor).filter(Actor.id == data.trader_id).first()
    if not trader:
        raise HTTPException(status_code=404, detail="Akteur nicht gefunden.")
    _check_batch_workflow_access(trader.role, "create_batch")

    # Charge anlegen
    batch = batch_service.create_trader_batch(
        db=db,
        scrap_class=data.scrap_class,
        origin_type=data.origin_type,
        mass_kg=data.mass_kg,
        trader_id=data.trader_id,
        preparation_degree=data.preparation_degree,
        contamination_level=data.contamination_level,
        origin_region=data.origin_region,
        collection_period=data.collection_period,
    )

    # Quellenverknüpfungen anlegen (Abholungen → Charge)
    for pickup_id in data.source_pickup_ids:
        entry = db.query(PickupHistoryEntry).filter(
            PickupHistoryEntry.id == pickup_id
        ).first()
        if entry:
            link = BatchSourcePickup(
                id=str(uuid.uuid4()),
                batch_id=batch.id,
                pickup_history_entry_id=pickup_id,
            )
            db.add(link)

    # Optionale chemische Analyse direkt mit anlegen
    if data.chemical_values:
        chemical_service.create_chemical_composition(
            db=db,
            batch_id=batch.id,
            element_values=data.chemical_values,
            thresholds=DEFAULT_THRESHOLDS,
            analysis_method="Händleranalyse (RFA)",
            measured_by=trader.name,
        )
    else:
        db.commit()

    return {"id": batch.id, "batch_number": batch.batch_number, "message": "Charge angelegt."}


@router.get("")
def list_batches(
    role: str = Query(..., description="haendler oder stahlwerk"),
    actor_id: str = Query(..., description="ID des anfragenden Akteurs"),
    db: Session = Depends(get_db),
):
    """Chargen rollenbezogen abrufen.
    Händler: eigene Chargen (created_by_trader_id).
    Stahlwerk: angebotene und zugewiesene Chargen (offered_to_steel_mill_id).
    Metallverarbeiter: 403.
    """
    engine = get_abac_engine()
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    tier = actor.relationship_tier if actor and role == "stahlwerk" else None
    if role == "haendler":
        _check_batch_workflow_access(role, "own_batches")
        batches = batch_service.get_batches_for_trader(db, actor_id)
    elif role == "stahlwerk":
        _check_batch_workflow_access(role, "incoming_offers")
        batches = batch_service.get_batches_for_steel_mill(db, actor_id)
    else:
        raise HTTPException(
            status_code=403,
            detail=f"Rolle '{role}' hat keinen Zugriff auf Chargen-Übersicht."
        )

    return [_batch_response(b, db, role, tier) for b in batches]


@router.get("/{batch_id}")
def get_batch(
    batch_id: str,
    role: str = Query(...),
    actor_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """Einzelne Charge mit vollständiger Herkunftskette und ABAC-gefilterter Chemie."""
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden.")

    # Zugriffsprüfung: Händler darf nur eigene, Stahlwerk nur zugewiesene
    if role == "haendler" and batch.created_by_trader_id != actor_id:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diese Charge.")
    if role == "stahlwerk" and batch.offered_to_steel_mill_id != actor_id:
        raise HTTPException(status_code=403, detail="Charge nicht an dieses Stahlwerk gerichtet.")
    if role == "metallverarbeiter":
        raise HTTPException(status_code=403, detail="Metallverarbeiter hat keinen Zugriff.")

    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    tier = actor.relationship_tier if actor and role == "stahlwerk" else None
    return _batch_response(batch, db, role, tier)


@router.post("/{batch_id}/offer")
def offer_batch(
    batch_id: str,
    data: BatchOffer,
    actor_id: str = Query(..., description="ID des anbietenden Händlers"),
    db: Session = Depends(get_db),
):
    """Händler bietet Charge einem Stahlwerk an.
    Status: entwurf → angeboten.
    """
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden.")
    if batch.owner_id != actor_id:
        raise HTTPException(status_code=403, detail="Nur der aktuell zugeordnete Händler darf anbieten.")
    if batch.workflow_status != "entwurf":
        raise HTTPException(
            status_code=400,
            detail=f"Charge hat Status '{batch.workflow_status}' – nur Entwürfe können angeboten werden."
        )

    steel_mill = db.query(Actor).filter(
        Actor.id == data.steel_mill_id, Actor.role == "stahlwerk"
    ).first()
    if not steel_mill:
        raise HTTPException(status_code=404, detail="Stahlwerk nicht gefunden.")

    batch.offered_to_steel_mill_id = data.steel_mill_id
    batch.delivery_date = data.delivery_date
    batch.workflow_status = "angeboten"
    batch.updated_at = datetime.utcnow()
    db.commit()

    return {"id": batch.id, "status": batch.workflow_status, "message": f"Angebot an {steel_mill.name} gesendet."}


@router.post("/{batch_id}/accept-offer")
def accept_offer(
    batch_id: str,
    actor_id: str = Query(..., description="ID des akzeptierenden Stahlwerks"),
    db: Session = Depends(get_db),
):
    """Stahlwerk akzeptiert Chargenangebot.
    Status: angeboten → zugewiesen.
    """
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden.")
    if batch.offered_to_steel_mill_id != actor_id:
        raise HTTPException(status_code=403, detail="Charge nicht an dieses Stahlwerk gerichtet.")
    if batch.workflow_status != "angeboten":
        raise HTTPException(
            status_code=400,
            detail=f"Charge hat Status '{batch.workflow_status}' – nur angebotene Chargen können akzeptiert werden."
        )

    batch.workflow_status = "zugewiesen"
    batch.owner_id = actor_id
    batch.updated_at = datetime.utcnow()
    db.commit()

    return {"id": batch.id, "status": batch.workflow_status}


@router.post("/{batch_id}/reject-offer")
def reject_offer(
    batch_id: str,
    actor_id: str = Query(..., description="ID des ablehnenden Stahlwerks"),
    db: Session = Depends(get_db),
):
    """Stahlwerk lehnt Chargenangebot ab.
    Status: angeboten → entwurf (Händler kann erneut anbieten).
    """
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden.")
    if batch.offered_to_steel_mill_id != actor_id:
        raise HTTPException(status_code=403, detail="Charge nicht an dieses Stahlwerk gerichtet.")
    if batch.workflow_status != "angeboten":
        raise HTTPException(
            status_code=400,
            detail=f"Charge hat Status '{batch.workflow_status}'."
        )

    # Zurück auf Entwurf setzen, damit der Händler ein neues Angebot machen kann
    batch.workflow_status = "entwurf"
    batch.owner_id = batch.created_by_trader_id
    batch.offered_to_steel_mill_id = None
    batch.delivery_date = None
    batch.updated_at = datetime.utcnow()
    db.commit()

    return {"id": batch.id, "status": batch.workflow_status, "message": "Angebot abgelehnt – zurück auf Entwurf."}


@router.post("/{batch_id}/confirm-delivery")
def confirm_delivery(
    batch_id: str,
    data: DeliveryConfirm,
    db: Session = Depends(get_db),
):
    """Lieferung bestätigen — Händler und Stahlwerk bestätigen jeweils separat.
    Wenn beide confirmed: atomare Transaktion →
      - workflow_status = 'geliefert'
      - TraceabilityEvent (anlieferung) anlegen
    """
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden.")
    if batch.workflow_status != "zugewiesen":
        raise HTTPException(
            status_code=400,
            detail=f"Charge hat Status '{batch.workflow_status}' – nur zugewiesene Chargen können bestätigt werden."
        )

    if data.confirming_role == "haendler":
        if batch.created_by_trader_id != data.actor_id and batch.owner_id != data.actor_id:
            raise HTTPException(status_code=403, detail="Nur der zugeordnete Händler darf bestätigen.")
        batch.confirmed_by_trader = True
    elif data.confirming_role == "stahlwerk":
        if batch.offered_to_steel_mill_id != data.actor_id:
            raise HTTPException(status_code=403, detail="Nur das zugewiesene Stahlwerk darf bestätigen.")
        batch.confirmed_by_steel_mill = True
    else:
        raise HTTPException(status_code=400, detail="Ungültige Rolle für Bestätigung.")

    batch.updated_at = datetime.utcnow()

    # Atomare Transaktion: wenn beide bestätigt haben → geliefert
    if batch.confirmed_by_trader and batch.confirmed_by_steel_mill:
        batch.workflow_status = "geliefert"

        # TraceabilityEvent für die Lieferungsbestätigung anlegen
        event = TraceabilityEvent(
            id=str(uuid.uuid4()),
            batch_id=batch.id,
            event_type="anlieferung",
            timestamp=datetime.utcnow(),
            actor_id=batch.created_by_trader_id,
            location="Stahlwerk (Lieferbestätigung)",
            notes=(
                f"Lieferung beidseitig bestätigt: "
                f"Charge {batch.batch_number} an Stahlwerk geliefert."
            ),
            epcis_type="TransactionEvent",
        )
        db.add(event)
        db.commit()

        return {
            "id": batch.id,
            "status": batch.workflow_status,
            "message": "Lieferung abgeschlossen – TraceabilityEvent erstellt.",
        }

    db.commit()
    return {
        "id": batch.id,
        "status": batch.workflow_status,
        "confirmed_by_trader": batch.confirmed_by_trader,
        "confirmed_by_steel_mill": batch.confirmed_by_steel_mill,
        "message": "Bestätigung gespeichert – warte auf die andere Partei.",
    }
