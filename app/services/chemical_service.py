from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models import ChemicalComposition, ScrapBatch
import uuid


DEFAULT_THRESHOLDS = {
    "Cu": 0.30,
    "Sn": 0.10,
    "Ni": 0.15,
    "Cr": 0.20,
    "Mo": 0.05,
}


def calculate_threshold_status(element_values: dict, thresholds: dict) -> tuple[bool, list]:
    """Berechnet, ob Grenzwerte überschritten sind und welche Elemente betroffen sind."""
    exceeded = []
    for element, value in element_values.items():
        if element in thresholds and value > thresholds[element]:
            exceeded.append(element)
    return len(exceeded) > 0, exceeded


def calculate_eaf_compatibility(element_values: dict, thresholds: dict) -> str:
    """
    Leitet EAF-Kompatibilitätsklasse aus chemischer Zusammensetzung ab.
    Nicht manuell eingebbar – verhindert Widersprüche zu Analysedaten (F4).
    """
    critical_exceeded = []
    for element, value in element_values.items():
        if element in thresholds and value > thresholds[element] * 1.5:
            critical_exceeded.append(element)

    minor_exceeded = []
    for element, value in element_values.items():
        if element in thresholds and thresholds[element] < value <= thresholds[element] * 1.5:
            minor_exceeded.append(element)

    if len(critical_exceeded) > 0:
        return "nicht geeignet"
    elif len(minor_exceeded) > 0:
        return "bedingt geeignet"
    else:
        return "geeignet"


def create_chemical_composition(
    db: Session,
    batch_id: str,
    element_values: dict,
    thresholds: dict,
    analysis_method: str,
    measured_by: str,
    measured_at: datetime = None,
) -> ChemicalComposition:
    if measured_at is None:
        measured_at = datetime.utcnow()

    threshold_exceeded, exceeded_elements = calculate_threshold_status(element_values, thresholds)

    composition = ChemicalComposition(
        id=str(uuid.uuid4()),
        batch_id=batch_id,
        element_values=element_values,
        thresholds=thresholds,
        analysis_method=analysis_method,
        measured_at=measured_at,
        measured_by=measured_by,
        threshold_exceeded=threshold_exceeded,
        exceeded_elements=exceeded_elements,
    )
    db.add(composition)

    # EAF-Kompatibilität in ScrapBatch aktualisieren
    batch = db.query(ScrapBatch).filter(ScrapBatch.id == batch_id).first()
    if batch:
        batch.eaf_compatibility = calculate_eaf_compatibility(element_values, thresholds)
        batch.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(composition)
    return composition


def get_compositions_for_batch(db: Session, batch_id: str) -> list:
    return (
        db.query(ChemicalComposition)
        .filter(ChemicalComposition.batch_id == batch_id)
        .order_by(ChemicalComposition.measured_at.desc())
        .all()
    )


def get_latest_composition(db: Session, batch_id: str):
    return (
        db.query(ChemicalComposition)
        .filter(ChemicalComposition.batch_id == batch_id)
        .order_by(ChemicalComposition.measured_at.desc())
        .first()
    )
