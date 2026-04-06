import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Float, Boolean, Integer, DateTime, Date,
    ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


EU_SCRAP_CLASSES = {
    "E1": "E1 – Leichter Stahlaltschrott",
    "E2": "E2 – Schwerer Neuschrott",
    "E3": "E3 – Schwerer Stahlaltschrott",
    "E6": "E6 – Leichter Neuschrott",
    "E8": "E8 – Neuschrottspäne",
    "E40": "E40 – Shredderschrott",
}

# Relationship-Tiers zwischen Händler und Stahlwerk
RELATIONSHIP_TIERS = ["standard", "preferred", "strategic"]

ACTOR_ROLES = ["metallverarbeiter", "haendler", "stahlwerk"]
ORIGIN_TYPES = ["Altschrott", "Neuschrott", "Eigenschrott", "Gebäudeabriss", "Industriebetrieb", "Wertstoffhof"]
EAF_COMPATIBILITY = ["geeignet", "bedingt geeignet", "nicht geeignet"]
VALIDATION_STATUS = ["entwurf", "validiert", "zertifiziert"]
EVENT_TYPES = [
    "erfassung", "eigentuemerwechsel", "aufbereitung",
    "qualitaetspruefung", "anlieferung", "einschmelzung"
]
PHYSICAL_CONDITIONS = ["sauber", "leicht verunreinigt", "stark verunreinigt"]
DENSITY_CLASSES = ["leicht", "mittel", "schwer"]
DIMENSION_CLASSES = ["kleindimensioniert", "mitteldimensioniert", "grossdimensioniert"]
# "angefragt": MV hat spezifischen Händler angefragt
# "verfuegbar": Container wurde abgeholt, bereit für neue Befüllung
CONTAINER_STATUSES = ["leer", "teilbefuellt", "voll", "abholbereit", "angefragt", "verfuegbar"]
DELIVERY_STATUSES = ["geplant", "abgeholt", "in_transit", "geliefert", "verzoegert"]
ACCESS_RULES = ["allow", "deny"]
CONTAMINATION_LEVELS = ["gering", "mittel", "hoch"]
# "abgeholt": beide Parteien haben bestätigt
PICKUP_REQUEST_STATUSES = ["ausstehend", "angenommen", "abgelehnt", "abgeschlossen", "abgeholt"]
# Workflow-Status einer ScrapBatch im Händler→Stahlwerk-Prozess
BATCH_WORKFLOW_STATUSES = ["entwurf", "angeboten", "zugewiesen", "geliefert"]


class Actor(Base):
    __tablename__ = "actors"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    organization = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=True)
    # Relationship-Tier: nur für Stahlwerk-Akteure relevant
    # bestimmt, welche Felder das Stahlwerk von einem Händler sehen darf
    relationship_tier = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    batches = relationship("ScrapBatch", back_populates="owner", foreign_keys="ScrapBatch.owner_id")
    supplied_batches = relationship("ScrapBatch", back_populates="supplier", foreign_keys="ScrapBatch.supplier_id")
    # Chargen die dieser Händler angelegt hat (Workflow)
    created_batches = relationship("ScrapBatch", back_populates="created_by_trader", foreign_keys="ScrapBatch.created_by_trader_id")
    # Chargenangebote die an dieses Stahlwerk gerichtet sind
    offered_batches = relationship("ScrapBatch", back_populates="offered_to_steel_mill", foreign_keys="ScrapBatch.offered_to_steel_mill_id")
    logistics_orders = relationship(
        "LogisticsOrder",
        back_populates="requesting_actor",
        foreign_keys="LogisticsOrder.requesting_actor_id",
    )
    incoming_logistics_orders = relationship(
        "LogisticsOrder",
        back_populates="receiving_actor",
        foreign_keys="LogisticsOrder.receiving_actor_id",
    )
    traceability_events = relationship("TraceabilityEvent", back_populates="actor")
    quality_analyses = relationship("QualityAnalysis", back_populates="inspector")
    passports_issued = relationship("MaterialPassport", back_populates="issuer")
    containers = relationship("Container", back_populates="owner", foreign_keys="Container.owner_id")
    pickup_requests_made = relationship(
        "PickupRequest", back_populates="requesting_actor",
        foreign_keys="PickupRequest.requesting_actor_id"
    )
    # Abholhistorie: als Händler oder als Metallverarbeiter
    pickup_history_as_trader = relationship(
        "PickupHistoryEntry", back_populates="trader",
        foreign_keys="PickupHistoryEntry.trader_id"
    )
    pickup_history_as_mv = relationship(
        "PickupHistoryEntry", back_populates="metal_processor",
        foreign_keys="PickupHistoryEntry.metal_processor_id"
    )


class ScrapBatch(Base):
    __tablename__ = "scrap_batches"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_number = Column(String(100), unique=True, nullable=False)
    scrap_class = Column(String(20), nullable=False)
    origin_type = Column(String(50), nullable=False)
    mass_kg = Column(Float, nullable=False)
    volume_m3 = Column(Float, nullable=True)

    # Provenienzdaten – teils ABAC-geschützt
    origin_region = Column(String(255), nullable=True)
    collection_period = Column(String(50), nullable=True)
    preparation_degree = Column(String(100), nullable=True)
    contamination_level = Column(String(50), nullable=True)

    # Wirtschaftliche Felder – niemals an Dritte
    price_basis = Column(String(255), nullable=True)
    pricing_formula_ref = Column(String(255), nullable=True)

    # Lieferantenreferenz – Hoheitswissen des Händlers, wird nie weitergegeben
    supplier_id = Column(String(36), ForeignKey("actors.id"), nullable=True)

    # Bestehende Felder (abwärtskompatibel)
    processing_degree = Column(String(100), nullable=True)
    eaf_compatibility = Column(String(50), nullable=True)
    supplier_source = Column(String(255), nullable=True)
    price_per_ton = Column(Float, nullable=True)

    owner_id = Column(String(36), ForeignKey("actors.id"), nullable=False)

    # ── Händler→Stahlwerk-Workflow-Felder ─────────────────────────────────────
    # Welcher Händler hat diese Charge angelegt (nullable für Legacy-Batches)
    created_by_trader_id = Column(String(36), ForeignKey("actors.id"), nullable=True)
    # Workflow-Status: entwurf → angeboten → zugewiesen → geliefert
    workflow_status = Column(String(20), nullable=True, default="entwurf")
    # Welchem Stahlwerk wurde die Charge angeboten
    offered_to_steel_mill_id = Column(String(36), ForeignKey("actors.id"), nullable=True)
    # Geplantes Lieferdatum
    delivery_date = Column(Date, nullable=True)
    # Gegenseitige Bestätigung der Lieferung
    confirmed_by_trader = Column(Boolean, default=False, nullable=False)
    confirmed_by_steel_mill = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Actor", back_populates="batches", foreign_keys=[owner_id])
    supplier = relationship("Actor", back_populates="supplied_batches", foreign_keys=[supplier_id])
    created_by_trader = relationship("Actor", back_populates="created_batches", foreign_keys=[created_by_trader_id])
    offered_to_steel_mill = relationship("Actor", back_populates="offered_batches", foreign_keys=[offered_to_steel_mill_id])
    chemical_compositions = relationship("ChemicalComposition", back_populates="batch")
    material_passports = relationship("MaterialPassport", back_populates="batch")
    traceability_events = relationship("TraceabilityEvent", back_populates="batch")
    quality_analyses = relationship("QualityAnalysis", back_populates="batch")
    logistics_orders = relationship("LogisticsOrder", back_populates="batch")
    cbam_records = relationship("CBAMRecord", back_populates="batch")
    source_pickups = relationship("BatchSourcePickup", back_populates="batch")


class ChemicalComposition(Base):
    __tablename__ = "chemical_compositions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    element_values = Column(JSONB, nullable=False)
    thresholds = Column(JSONB, nullable=False)
    analysis_method = Column(String(100), nullable=False)
    measured_at = Column(DateTime, nullable=False)
    measured_by = Column(String(255), nullable=False)
    threshold_exceeded = Column(Boolean, default=False)
    exceeded_elements = Column(JSONB, nullable=True)

    batch = relationship("ScrapBatch", back_populates="chemical_compositions")


class MaterialPassport(Base):
    __tablename__ = "material_passports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    version = Column(Integer, default=1)
    validation_status = Column(String(50), default="entwurf")
    certification_ref = Column(String(255), nullable=True)
    issuer_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    batch = relationship("ScrapBatch", back_populates="material_passports")
    issuer = relationship("Actor", back_populates="passports_issued")


class TraceabilityEvent(Base):
    __tablename__ = "traceability_events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    actor_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    epcis_type = Column(String(100), nullable=True)

    batch = relationship("ScrapBatch", back_populates="traceability_events")
    actor = relationship("Actor", back_populates="traceability_events")


class QualityAnalysis(Base):
    __tablename__ = "quality_analyses"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    physical_condition = Column(String(50), nullable=False)
    density_class = Column(String(50), nullable=False)
    dimension_class = Column(String(50), nullable=False)
    moisture_content = Column(Float, nullable=True)
    oil_residue = Column(Boolean, default=False)
    radioactive_cleared = Column(Boolean, default=True)
    inspected_at = Column(DateTime, nullable=False)
    inspector_id = Column(String(36), ForeignKey("actors.id"), nullable=False)

    batch = relationship("ScrapBatch", back_populates="quality_analyses")
    inspector = relationship("Actor", back_populates="quality_analyses")


class LogisticsOrder(Base):
    __tablename__ = "logistics_orders"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    requesting_actor_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    receiving_actor_id = Column(String(36), ForeignKey("actors.id"), nullable=True)
    pickup_date = Column(Date, nullable=False)
    delivery_date = Column(Date, nullable=True)
    pickup_location = Column(String(255), nullable=False)
    delivery_location = Column(String(255), nullable=False)
    container_status = Column(String(50), default="leer")
    delivery_status = Column(String(50), default="geplant")
    carrier = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    batch = relationship("ScrapBatch", back_populates="logistics_orders")
    requesting_actor = relationship(
        "Actor",
        back_populates="logistics_orders",
        foreign_keys=[requesting_actor_id],
    )
    receiving_actor = relationship("Actor", back_populates="incoming_logistics_orders", foreign_keys=[receiving_actor_id])


class CBAMRecord(Base):
    __tablename__ = "cbam_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    scope1_emissions_kg = Column(Float, nullable=False)
    scope2_emissions_kg = Column(Float, nullable=False)
    scope3_emissions_kg = Column(Float, nullable=True)
    calculation_method = Column(String(100), nullable=False)
    reporting_period = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("ScrapBatch", back_populates="cbam_records")


class Container(Base):
    __tablename__ = "containers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    container_number = Column(String(100), unique=True, nullable=False)
    owner_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    location = Column(String(255), nullable=False)
    # Maximalvolumen in Kubikmetern (physische Containergröße)
    capacity_m3 = Column(Float, nullable=False)
    # Füllstand 0–100 % (Schätzung durch Metallverarbeiter, kein Wiegen)
    fill_level = Column(Integer, default=0)
    # leer, teilbefuellt, voll, abholbereit, angefragt, verfuegbar
    status = Column(String(50), default="leer")
    scrap_class = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("Actor", back_populates="containers", foreign_keys=[owner_id])
    pickup_requests = relationship("PickupRequest", back_populates="container")
    history_entries = relationship("PickupHistoryEntry", back_populates="container")


class PickupRequest(Base):
    __tablename__ = "pickup_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    container_id = Column(String(36), ForeignKey("containers.id"), nullable=False)
    # Der Händler — entweder der Anfragende (haendler-initiiert) oder der Angefragte (mv-initiiert)
    requesting_actor_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    # Wer hat den Prozess gestartet: "haendler" oder "metallverarbeiter"
    initiator = Column(String(20), nullable=False, default="haendler")
    requested_pickup_date = Column(Date, nullable=False)
    offered_price_per_ton = Column(Float, nullable=True)
    # ausstehend, angenommen, abgelehnt, abgeschlossen, abgeholt
    status = Column(String(50), default="ausstehend")
    notes = Column(Text, nullable=True)
    # Gegenseitige Bestätigung (erst wenn beide True → status="abgeholt")
    confirmed_by_metal_processor = Column(Boolean, default=False, nullable=False)
    confirmed_by_trader = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    container = relationship("Container", back_populates="pickup_requests")
    requesting_actor = relationship(
        "Actor", back_populates="pickup_requests_made",
        foreign_keys=[requesting_actor_id]
    )


class PickupHistoryEntry(Base):
    """Abschluss-Protokoll einer Abholung — wird erstellt wenn beide Parteien bestätigt haben."""
    __tablename__ = "pickup_history_entries"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    container_id = Column(String(36), ForeignKey("containers.id"), nullable=False)
    pickup_request_id = Column(String(36), ForeignKey("pickup_requests.id"), nullable=False)
    trader_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    metal_processor_id = Column(String(36), ForeignKey("actors.id"), nullable=False)
    completed_at = Column(DateTime, nullable=False)
    # Füllstand zum Zeitpunkt der Abholung (vor dem Reset auf 0)
    fill_level_at_pickup = Column(Integer, nullable=False)
    # Berechnetes Schätzvolumen zum Zeitpunkt der Abholung (fill_level_at_pickup/100 * capacity_m3)
    estimated_volume_m3 = Column(Float, nullable=False)
    scrap_type = Column(String(20), nullable=True)

    container = relationship("Container", back_populates="history_entries")
    trader = relationship(
        "Actor", back_populates="pickup_history_as_trader",
        foreign_keys=[trader_id]
    )
    metal_processor = relationship(
        "Actor", back_populates="pickup_history_as_mv",
        foreign_keys=[metal_processor_id]
    )
    batch_sources = relationship("BatchSourcePickup", back_populates="pickup_history_entry")


class BatchSourcePickup(Base):
    """Verknüpft eine ScrapBatch mit den Containerabholungen aus denen sie entstanden ist.
    Blending: eine Charge kann aus mehreren Abholungen entstehen.
    Splitting: eine Abholung kann in mehrere Chargen eingehen.
    """
    __tablename__ = "batch_source_pickups"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    batch_id = Column(String(36), ForeignKey("scrap_batches.id"), nullable=False)
    pickup_history_entry_id = Column(String(36), ForeignKey("pickup_history_entries.id"), nullable=False)

    batch = relationship("ScrapBatch", back_populates="source_pickups")
    pickup_history_entry = relationship("PickupHistoryEntry", back_populates="batch_sources")


class FieldAccessPolicy(Base):
    __tablename__ = "field_access_policies"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    data_field = Column(String(255), nullable=False)
    actor_role = Column(String(50), nullable=False)
    access_rule = Column(String(10), nullable=False, default="allow")
    is_default = Column(Boolean, default=True)
    # Relationship-Tier: NULL = gilt für alle Tiers; sonst "standard", "preferred", "strategic"
    relationship_tier = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
