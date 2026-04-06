import uuid
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, date

from app.db.session import get_db
from app.db.models import (
    Actor, ScrapBatch, EU_SCRAP_CLASSES,
    Container, PickupRequest, PickupHistoryEntry,
)
from app.services import batch_service, chemical_service, logistics_service, passport_service
from app.abac.engine import get_abac_engine
from app.api.routers import batch_workflow

app = FastAPI(
    title="Scrap Data Platform API",
    description="Datenplattform für Metallschrottkreislaufsysteme – Masterarbeit Prototyp",
    version="1.0.0",
)

class ChemicalCompositionCreate(BaseModel):
    batch_id: str
    element_values: dict
    thresholds: dict
    analysis_method: str
    measured_by: str
    measured_at: Optional[datetime] = None


class LogisticsOrderCreate(BaseModel):
    batch_id: str
    requesting_actor_id: str
    receiving_actor_id: str
    pickup_date: date
    delivery_date: Optional[date] = None
    pickup_location: str
    delivery_location: str
    container_status: str = "abholbereit"
    delivery_status: str = "geplant"
    carrier: Optional[str] = None
    notes: Optional[str] = None


class LogisticsStatusUpdate(BaseModel):
    delivery_status: Optional[str] = None


class ContainerCreate(BaseModel):
    container_number: str
    owner_id: str
    location: str
    capacity_m3: float
    fill_level: int = 0
    status: str = "leer"
    scrap_class: Optional[str] = None
    notes: Optional[str] = None


class PickupRequestCreate(BaseModel):
    requesting_actor_id: str
    requested_pickup_date: date
    offered_price_per_ton: Optional[float] = None
    notes: Optional[str] = None
    initiator: str = "haendler"


class TraderRequestCreate(BaseModel):
    haendler_id: str
    requested_pickup_date: date
    notes: Optional[str] = None

app.include_router(batch_workflow.router)


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/actors")
def list_actors(db: Session = Depends(get_db)):
    actors = db.query(Actor).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "role": a.role,
            "organization": a.organization,
            "contact_email": a.contact_email,
            "relationship_tier": a.relationship_tier,
        }
        for a in actors
    ]

@app.get("/batches")
def list_batches(
    role: Optional[str] = Query(None, description="Rolle für ABAC-Filterung"),
    db: Session = Depends(get_db),
):
    batches = batch_service.get_all_batches(db)
    engine = get_abac_engine()
    result = []
    for b in batches:
        batch_dict = batch_service.batch_to_dict(b)
        if role:
            batch_dict = engine.filter_batch_fields(role, batch_dict)
        batch_dict["id"] = b.id
        batch_dict["owner_id"] = b.owner_id
        result.append(batch_dict)
    return result


@app.get("/batches/{batch_id}")
def get_batch(
    batch_id: str,
    role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    batch = batch_service.get_batch_by_id(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden")
    batch_dict = batch_service.batch_to_dict(batch)
    if role:
        engine = get_abac_engine()
        batch_dict = engine.filter_batch_fields(role, batch_dict)
    batch_dict["id"] = batch.id
    return batch_dict

@app.get("/batches/{batch_id}/chemical")
def get_chemical(
    batch_id: str,
    role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    compositions = chemical_service.get_compositions_for_batch(db, batch_id)
    engine = get_abac_engine()
    result = []
    for c in compositions:
        chem_dict = {
            "id": c.id,
            "analysis_method": c.analysis_method,
            "measured_at": c.measured_at.isoformat() if c.measured_at else None,
            "measured_by": c.measured_by,
            "element_values": c.element_values,
            "thresholds": c.thresholds,
            "threshold_exceeded": c.threshold_exceeded,
            "exceeded_elements": c.exceeded_elements,
        }
        if role:
            filtered = engine.filter_chemical_fields(role, chem_dict)
            filtered["id"] = c.id
            result.append(filtered)
        else:
            result.append(chem_dict)
    return result


@app.post("/batches/{batch_id}/chemical")
def create_chemical(
    batch_id: str,
    data: ChemicalCompositionCreate,
    db: Session = Depends(get_db),
):
    composition = chemical_service.create_chemical_composition(
        db=db,
        batch_id=batch_id,
        element_values=data.element_values,
        thresholds=data.thresholds,
        analysis_method=data.analysis_method,
        measured_by=data.measured_by,
        measured_at=data.measured_at,
    )
    return {
        "id": composition.id,
        "threshold_exceeded": composition.threshold_exceeded,
        "exceeded_elements": composition.exceeded_elements,
        "message": "Analyse gespeichert",
    }

@app.get("/batches/{batch_id}/passport")
def get_passport(batch_id: str, db: Session = Depends(get_db)):
    passport = passport_service.get_passport_for_batch(db, batch_id)
    if not passport:
        raise HTTPException(status_code=404, detail="Kein Materialpass gefunden")
    return {
        "id": passport.id,
        "batch_id": passport.batch_id,
        "version": passport.version,
        "validation_status": passport.validation_status,
        "certification_ref": passport.certification_ref,
        "issuer_id": passport.issuer_id,
        "created_at": passport.created_at.isoformat() if passport.created_at else None,
        "updated_at": passport.updated_at.isoformat() if passport.updated_at else None,
    }

@app.get("/batches/{batch_id}/events")
def get_events(batch_id: str, db: Session = Depends(get_db)):
    events = passport_service.get_traceability_events(db, batch_id)
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "actor_id": e.actor_id,
            "location": e.location,
            "notes": e.notes,
            "epcis_type": e.epcis_type,
        }
        for e in events
    ]

@app.get("/logistics")
def list_logistics(
    role: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if actor_id and role == "stahlwerk":
        orders = logistics_service.get_orders_for_receiving_actor(db, actor_id)
    elif actor_id:
        orders = logistics_service.get_orders_by_actor(db, actor_id)
    else:
        orders = logistics_service.get_all_logistics_orders(db)

    engine = get_abac_engine()
    result = []
    for o in orders:
        order_dict = logistics_service.logistics_to_dict(o)
        if role:
            order_dict = engine.filter_logistics_fields(role, order_dict)
        order_dict["id"] = o.id
        order_dict["batch_id"] = o.batch_id
        order_dict["requesting_actor_id"] = o.requesting_actor_id
        result.append(order_dict)
    return result


@app.post("/logistics")
def create_logistics(
    data: LogisticsOrderCreate,
    actor_id: str = Query(...),
    db: Session = Depends(get_db),
):
    if actor_id != data.requesting_actor_id:
        raise HTTPException(status_code=403, detail="Akteur stimmt nicht mit dem anlegenden Händler überein.")
    trader = db.query(Actor).filter(Actor.id == data.requesting_actor_id).first()
    if not trader or trader.role != "haendler":
        raise HTTPException(status_code=403, detail="Nur Händler dürfen Logistikaufträge anlegen.")
    receiver = db.query(Actor).filter(Actor.id == data.receiving_actor_id).first()
    if not receiver or receiver.role != "stahlwerk":
        raise HTTPException(status_code=400, detail="Empfänger muss ein Stahlwerk sein.")
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Charge nicht gefunden")
    if batch.created_by_trader_id != data.requesting_actor_id:
        raise HTTPException(status_code=403, detail="Transportauftrag nur für eigene Händlercharge erlaubt.")
    if batch.offered_to_steel_mill_id and batch.offered_to_steel_mill_id != data.receiving_actor_id:
        raise HTTPException(status_code=400, detail="Charge ist bereits einem anderen Stahlwerk zugeordnet.")

    order = logistics_service.create_logistics_order(
        db=db,
        batch_id=data.batch_id,
        requesting_actor_id=data.requesting_actor_id,
        receiving_actor_id=data.receiving_actor_id,
        pickup_date=data.pickup_date,
        delivery_date=data.delivery_date,
        pickup_location=data.pickup_location,
        delivery_location=data.delivery_location,
        container_status=data.container_status,
        delivery_status=data.delivery_status,
        carrier=data.carrier,
        notes=data.notes,
    )
    return {"id": order.id, "message": "Logistikauftrag angelegt"}


@app.patch("/logistics/{order_id}/status")
def update_logistics_status(
    order_id: str,
    data: LogisticsStatusUpdate,
    actor_id: str = Query(...),
    db: Session = Depends(get_db),
):
    order = logistics_service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Logistikauftrag nicht gefunden")

    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if not actor:
        raise HTTPException(status_code=404, detail="Akteur nicht gefunden")
    if actor.role == "haendler" and order.requesting_actor_id != actor_id:
        raise HTTPException(status_code=403, detail="Nur der anlegende Händler darf den Transportstatus ändern.")
    if actor.role == "stahlwerk" and order.receiving_actor_id != actor_id:
        raise HTTPException(status_code=403, detail="Nur das empfangende Stahlwerk darf diesen Transport aktualisieren.")
    if actor.role not in {"haendler", "stahlwerk"}:
        raise HTTPException(status_code=403, detail="Keine Berechtigung für Transportstatus.")
    if actor.role == "haendler" and data.delivery_status == "geliefert":
        raise HTTPException(status_code=400, detail="Der Status 'geliefert' wird durch das empfangende Stahlwerk bestätigt.")
    if actor.role == "stahlwerk" and data.delivery_status not in {None, "geliefert"}:
        raise HTTPException(status_code=400, detail="Stahlwerke dürfen nur den Wareneingang als 'geliefert' bestätigen.")

    updated = logistics_service.update_order_status(
        db, order_id, data.delivery_status
    )
    return {"id": updated.id, "delivery_status": updated.delivery_status, "container_status": updated.container_status}

def _container_to_dict(c: Container) -> dict:
    estimated_m3 = round(c.fill_level / 100 * c.capacity_m3, 2) if c.capacity_m3 else 0.0
    return {
        "id": c.id,
        "container_number": c.container_number,
        "owner_id": c.owner_id,
        "location": c.location,
        "capacity_m3": c.capacity_m3,
        "fill_level": c.fill_level,
        "estimated_volume_m3": estimated_m3,
        "status": c.status,
        "scrap_class": c.scrap_class,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _pickup_request_to_dict(r: PickupRequest) -> dict:
    return {
        "id": r.id,
        "container_id": r.container_id,
        "requesting_actor_id": r.requesting_actor_id,
        "initiator": r.initiator,
        "requested_pickup_date": r.requested_pickup_date.isoformat() if r.requested_pickup_date else None,
        "offered_price_per_ton": r.offered_price_per_ton,
        "status": r.status,
        "notes": r.notes,
        "confirmed_by_metal_processor": r.confirmed_by_metal_processor,
        "confirmed_by_trader": r.confirmed_by_trader,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _history_entry_to_dict(h: PickupHistoryEntry) -> dict:
    return {
        "id": h.id,
        "container_id": h.container_id,
        "pickup_request_id": h.pickup_request_id,
        "trader_id": h.trader_id,
        "metal_processor_id": h.metal_processor_id,
        "completed_at": h.completed_at.isoformat() if h.completed_at else None,
        "fill_level_at_pickup": h.fill_level_at_pickup,
        "estimated_volume_m3": h.estimated_volume_m3,
        "scrap_type": h.scrap_type,
    }


@app.get("/containers")
def list_containers(
    owner_id: Optional[str] = Query(None, description="Filter by owner actor ID"),
    db: Session = Depends(get_db),
):
    q = db.query(Container)
    if owner_id:
        q = q.filter(Container.owner_id == owner_id)
    return [_container_to_dict(c) for c in q.order_by(Container.created_at.desc()).all()]


@app.post("/containers")
def create_container(
    data: ContainerCreate,
    actor_id: str = Query(...),
    db: Session = Depends(get_db),
):
    if actor_id != data.owner_id:
        raise HTTPException(status_code=403, detail="Akteur stimmt nicht mit dem Container-Eigentümer überein.")
    owner = db.query(Actor).filter(Actor.id == data.owner_id).first()
    if not owner or owner.role != "metallverarbeiter":
        raise HTTPException(status_code=403, detail="Container dürfen nur für Metallverarbeiter angelegt werden.")
    c = Container(
        id=str(uuid.uuid4()),
        container_number=data.container_number,
        owner_id=data.owner_id,
        location=data.location,
        capacity_m3=data.capacity_m3,
        fill_level=max(0, min(100, data.fill_level)),
        status=data.status,
        scrap_class=data.scrap_class,
        notes=data.notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "message": "Container angelegt"}


@app.get("/containers/{container_id}")
def get_container(container_id: str, db: Session = Depends(get_db)):
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container nicht gefunden")
    return _container_to_dict(c)


@app.get("/containers/{container_id}/pickup-requests")
def list_pickup_requests(container_id: str, db: Session = Depends(get_db)):
    reqs = (
        db.query(PickupRequest)
        .filter(PickupRequest.container_id == container_id)
        .order_by(PickupRequest.created_at.desc())
        .all()
    )
    return [_pickup_request_to_dict(r) for r in reqs]


@app.post("/containers/{container_id}/pickup-requests")
def create_pickup_request(
    container_id: str,
    data: PickupRequestCreate,
    actor_id: str = Query(...),
    db: Session = Depends(get_db)
):
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container nicht gefunden")
    if actor_id != data.requesting_actor_id:
        raise HTTPException(status_code=403, detail="Akteur stimmt nicht mit dem anfragenden Händler überein.")
    actor = db.query(Actor).filter(Actor.id == data.requesting_actor_id).first()
    if not actor or actor.role != "haendler":
        raise HTTPException(status_code=403, detail="Nur Händler dürfen Abholanträge stellen.")
    if data.initiator != "haendler":
        raise HTTPException(status_code=400, detail="Ungültiger Initiator für diesen Endpunkt.")
    existing = db.query(PickupRequest).filter(
        PickupRequest.container_id == container_id,
        PickupRequest.requesting_actor_id == data.requesting_actor_id,
        PickupRequest.status.in_(["ausstehend", "angenommen"]),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Für diesen Container existiert bereits ein aktiver Antrag dieses Händlers.")
    r = PickupRequest(
        id=str(uuid.uuid4()),
        container_id=container_id,
        requesting_actor_id=data.requesting_actor_id,
        initiator="haendler",
        requested_pickup_date=data.requested_pickup_date,
        offered_price_per_ton=data.offered_price_per_ton,
        status="ausstehend",
        notes=data.notes,
        confirmed_by_metal_processor=False,
        confirmed_by_trader=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "message": "Abholantrag gestellt"}


@app.post("/containers/{container_id}/request-trader")
def request_trader(
    container_id: str,
    data: TraderRequestCreate,
    actor_id: str = Query(...),
    db: Session = Depends(get_db)
):
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container nicht gefunden")
    actor = db.query(Actor).filter(Actor.id == c.owner_id).first()
    trader = db.query(Actor).filter(Actor.id == data.haendler_id).first()
    if c.owner_id != actor_id:
        raise HTTPException(status_code=403, detail="Nur der Container-Eigentümer darf Händler anfragen.")
    if not actor or actor.role != "metallverarbeiter":
        raise HTTPException(status_code=403, detail="Container-Eigentümer muss Metallverarbeiter sein.")
    if not trader or trader.role != "haendler":
        raise HTTPException(status_code=404, detail="Angefragter Händler nicht gefunden.")
    if c.status not in ("abholbereit", "leer", "teilbefuellt", "voll", "verfuegbar"):
        raise HTTPException(
            status_code=400,
            detail=f"Container hat Status '{c.status}' – keine neue Anfrage möglich."
        )
    existing = db.query(PickupRequest).filter(
        PickupRequest.container_id == container_id,
        PickupRequest.requesting_actor_id == data.haendler_id,
        PickupRequest.initiator == "metallverarbeiter",
        PickupRequest.status.in_(["ausstehend", "angenommen"]),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Für diesen Händler existiert bereits eine aktive Anfrage.")
    r = PickupRequest(
        id=str(uuid.uuid4()),
        container_id=container_id,
        requesting_actor_id=data.haendler_id,
        initiator="metallverarbeiter",
        requested_pickup_date=data.requested_pickup_date,
        offered_price_per_ton=None,
        status="ausstehend",
        notes=data.notes,
        confirmed_by_metal_processor=False,
        confirmed_by_trader=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(r)
    # Container-Status auf "angefragt" setzen
    c.status = "angefragt"
    c.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(r)
    return {"id": r.id, "message": "Anfrage an Händler gestellt", "container_status": c.status}


@app.patch("/containers/{container_id}/pickup-requests/{request_id}/accept")
def accept_pickup_request(
    container_id: str,
    request_id: str,
    actor_id: str = Query(...),
    db: Session = Depends(get_db),
):
    r = db.query(PickupRequest).filter(
        PickupRequest.id == request_id, PickupRequest.container_id == container_id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Abholantrag nicht gefunden")
    c = db.query(Container).filter(Container.id == container_id).first()
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if not actor:
        raise HTTPException(status_code=404, detail="Akteur nicht gefunden")
    if r.initiator == "haendler":
        if actor.role != "metallverarbeiter" or not c or c.owner_id != actor_id:
            raise HTTPException(status_code=403, detail="Nur der Container-Eigentümer darf Händleranträge annehmen.")
    else:
        if actor.role != "haendler" or r.requesting_actor_id != actor_id:
            raise HTTPException(status_code=403, detail="Nur der angefragte Händler darf diese Anfrage annehmen.")
    r.status = "angenommen"
    r.updated_at = datetime.utcnow()
    if c and c.status != "angefragt":
        c.status = "angefragt"
        c.updated_at = datetime.utcnow()
    db.query(PickupRequest).filter(
        PickupRequest.container_id == container_id,
        PickupRequest.id != request_id,
        PickupRequest.status == "ausstehend",
    ).update({"status": "abgelehnt", "updated_at": datetime.utcnow()})
    db.commit()
    return {"id": r.id, "status": r.status}


@app.patch("/containers/{container_id}/pickup-requests/{request_id}/reject")
def reject_pickup_request(
    container_id: str,
    request_id: str,
    actor_id: str = Query(...),
    db: Session = Depends(get_db),
):
    r = db.query(PickupRequest).filter(
        PickupRequest.id == request_id, PickupRequest.container_id == container_id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Abholantrag nicht gefunden")
    c = db.query(Container).filter(Container.id == container_id).first()
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if not actor:
        raise HTTPException(status_code=404, detail="Akteur nicht gefunden")
    if r.initiator == "haendler":
        if actor.role != "metallverarbeiter" or not c or c.owner_id != actor_id:
            raise HTTPException(status_code=403, detail="Nur der Container-Eigentümer darf Händleranträge ablehnen.")
    else:
        if actor.role != "haendler" or r.requesting_actor_id != actor_id:
            raise HTTPException(status_code=403, detail="Nur der angefragte Händler darf diese Anfrage ablehnen.")
    r.status = "abgelehnt"
    r.updated_at = datetime.utcnow()
    if r.initiator == "metallverarbeiter":
        if c and c.status == "angefragt":
            c.status = "abholbereit"
            c.updated_at = datetime.utcnow()
    db.commit()
    return {"id": r.id, "status": r.status}


@app.patch("/containers/{container_id}/pickup-requests/{request_id}/confirm")
def confirm_pickup(
    container_id: str,
    request_id: str,
    actor_id: str = Query(...),
    confirming_role: str = Query(..., description="'metallverarbeiter' oder 'haendler'"),
    db: Session = Depends(get_db),
):
    r = db.query(PickupRequest).filter(
        PickupRequest.id == request_id, PickupRequest.container_id == container_id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Abholantrag nicht gefunden")
    if r.status != "angenommen":
        raise HTTPException(
            status_code=400,
            detail=f"Nur angenommene Anfragen können bestätigt werden (aktuell: {r.status})."
        )

    c = db.query(Container).filter(Container.id == container_id).first()
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if not actor or not c:
        raise HTTPException(status_code=404, detail="Akteur oder Container nicht gefunden")

    if confirming_role == "metallverarbeiter":
        if actor.role != "metallverarbeiter" or c.owner_id != actor_id:
            raise HTTPException(status_code=403, detail="Nur der Container-Eigentümer darf als Metallverarbeiter bestätigen.")
        r.confirmed_by_metal_processor = True
    elif confirming_role == "haendler":
        if actor.role != "haendler" or r.requesting_actor_id != actor_id:
            raise HTTPException(status_code=403, detail="Nur der zuständige Händler darf bestätigen.")
        r.confirmed_by_trader = True
    else:
        raise HTTPException(status_code=400, detail="Ungültige Rolle für Bestätigung.")

    r.updated_at = datetime.utcnow()

    if r.confirmed_by_metal_processor and r.confirmed_by_trader:
        history = PickupHistoryEntry(
            id=str(uuid.uuid4()),
            container_id=container_id,
            pickup_request_id=r.id,
            trader_id=r.requesting_actor_id,
            metal_processor_id=c.owner_id,
            completed_at=datetime.utcnow(),
            fill_level_at_pickup=c.fill_level,
            estimated_volume_m3=round(c.fill_level / 100 * c.capacity_m3, 2),
            scrap_type=c.scrap_class,
        )
        db.add(history)
        c.fill_level = 0
        c.status = "verfuegbar"
        c.updated_at = datetime.utcnow()
        r.status = "abgeholt"
        db.commit()
        return {
            "id": r.id,
            "status": r.status,
            "message": "Abholung beidseitig bestätigt – Container zurückgesetzt.",
            "history_entry_id": history.id,
        }

    db.commit()
    return {
        "id": r.id,
        "status": r.status,
        "confirmed_by_metal_processor": r.confirmed_by_metal_processor,
        "confirmed_by_trader": r.confirmed_by_trader,
        "message": "Bestätigung gespeichert – warte auf die andere Partei.",
    }


@app.get("/pickup-history")
def get_pickup_history(
    actor_id: Optional[str] = Query(None, description="Filter: trader_id oder metal_processor_id"),
    db: Session = Depends(get_db),
):
    q = db.query(PickupHistoryEntry)
    if actor_id:
        q = q.filter(
            (PickupHistoryEntry.trader_id == actor_id) |
            (PickupHistoryEntry.metal_processor_id == actor_id)
        )
    entries = q.order_by(PickupHistoryEntry.completed_at.desc()).all()
    return [_history_entry_to_dict(h) for h in entries]

@app.get("/abac/fields/{role}/{resource_type}")
def get_accessible_fields(role: str, resource_type: str):
    engine = get_abac_engine()
    fields = engine.get_accessible_fields(role, resource_type)
    return {"role": role, "resource_type": resource_type, "accessible_fields": fields}

@app.get("/scrap-classes")
def get_scrap_classes():
    return EU_SCRAP_CLASSES
