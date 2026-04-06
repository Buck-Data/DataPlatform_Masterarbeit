from datetime import datetime, date
from sqlalchemy.orm import Session
from app.db.models import LogisticsOrder
import uuid


def get_all_logistics_orders(db: Session) -> list:
    return db.query(LogisticsOrder).order_by(LogisticsOrder.created_at.desc()).all()


def get_orders_by_actor(db: Session, actor_id: str) -> list:
    return (
        db.query(LogisticsOrder)
        .filter(LogisticsOrder.requesting_actor_id == actor_id)
        .order_by(LogisticsOrder.created_at.desc())
        .all()
    )


def get_orders_for_receiving_actor(db: Session, actor_id: str) -> list:
    return (
        db.query(LogisticsOrder)
        .filter(LogisticsOrder.receiving_actor_id == actor_id)
        .order_by(LogisticsOrder.created_at.desc())
        .all()
    )


def get_orders_by_batch(db: Session, batch_id: str) -> list:
    return (
        db.query(LogisticsOrder)
        .filter(LogisticsOrder.batch_id == batch_id)
        .order_by(LogisticsOrder.created_at.desc())
        .all()
    )


def get_order_by_id(db: Session, order_id: str):
    return db.query(LogisticsOrder).filter(LogisticsOrder.id == order_id).first()


def create_logistics_order(
    db: Session,
    batch_id: str,
    requesting_actor_id: str,
    receiving_actor_id: str | None,
    pickup_date: date,
    delivery_date: date | None,
    pickup_location: str,
    delivery_location: str,
    container_status: str = "abholbereit",
    delivery_status: str = "geplant",
    carrier: str = None,
    notes: str = None,
) -> LogisticsOrder:
    order = LogisticsOrder(
        id=str(uuid.uuid4()),
        batch_id=batch_id,
        requesting_actor_id=requesting_actor_id,
        receiving_actor_id=receiving_actor_id,
        pickup_date=pickup_date,
        delivery_date=delivery_date,
        pickup_location=pickup_location,
        delivery_location=delivery_location,
        container_status=container_status,
        delivery_status=delivery_status,
        carrier=carrier,
        notes=notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def update_order_status(
    db: Session,
    order_id: str,
    delivery_status: str = None,
) -> LogisticsOrder:
    order = get_order_by_id(db, order_id)
    if not order:
        return None
    if delivery_status:
        order.delivery_status = delivery_status
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order


def logistics_to_dict(order: LogisticsOrder) -> dict:
    return {
        "id": order.id,
        "batch_id": order.batch_id,
        "requesting_actor_id": order.requesting_actor_id,
        "receiving_actor_id": order.receiving_actor_id,
        "pickup_date": str(order.pickup_date),
        "delivery_date": str(order.delivery_date) if order.delivery_date else None,
        "pickup_location": order.pickup_location,
        "delivery_location": order.delivery_location,
        "container_status": order.container_status,
        "delivery_status": order.delivery_status,
        "carrier": order.carrier,
        "notes": order.notes,
    }
