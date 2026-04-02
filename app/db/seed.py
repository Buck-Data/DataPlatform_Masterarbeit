"""
Seed-Skript: Erstellt realistische Testdaten für die Masterarbeit-Demo (Kapitel 6.2).
Wird bei docker-compose up automatisch ausgeführt (nach alembic upgrade head).

Akteure:
  - Metallverarbeitung König GmbH  (metallverarbeiter)
  - Schmidt Stanzteile GmbH        (metallverarbeiter)
  - Bauer Metallbau GmbH           (metallverarbeiter)
  - Müller Recycling GmbH          (haendler)
  - Hoffmann Metallhandel GmbH     (haendler)
  - Keller Schrott GmbH            (haendler)
  - Südstahl AG                    (stahlwerk)
  - Oststahl AG                    (stahlwerk)
  - Nordstahl AG                   (stahlwerk)

Chargen:
  - CH-2026-001 bis CH-2026-007
"""
import sys
import os
import uuid
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.session import SessionLocal
from app.db.models import (
    Actor, ScrapBatch, ChemicalComposition, MaterialPassport,
    TraceabilityEvent, QualityAnalysis, LogisticsOrder, CBAMRecord, FieldAccessPolicy,
    Container, PickupRequest, PickupHistoryEntry, BatchSourcePickup,
)
from app.services.chemical_service import calculate_threshold_status, calculate_eaf_compatibility


def _clear_all_data(db) -> None:
    """Löscht alle Datensätze in korrekter FK-Reihenfolge."""
    db.query(FieldAccessPolicy).delete()
    db.query(CBAMRecord).delete()
    db.query(LogisticsOrder).delete()
    db.query(QualityAnalysis).delete()
    db.query(TraceabilityEvent).delete()
    db.query(MaterialPassport).delete()
    db.query(ChemicalComposition).delete()
    db.query(BatchSourcePickup).delete()
    db.query(ScrapBatch).delete()
    db.query(PickupHistoryEntry).delete()
    db.query(PickupRequest).delete()
    db.query(Container).delete()
    db.query(Actor).delete()
    db.commit()
    print("Bestehende Daten gelöscht.")


def _seed_containers(db) -> None:
    """Erstellt Container- und PickupRequest-Demo-Daten mit dem aktuellen Schema.
    Loescht bestehende Container/Requests und legt neue an.
    Wird aufgerufen wenn Container fehlen oder veraltetes Schema (capacity_m3 > 500) vorliegt.
    """
    actor_schmalz = db.query(Actor).filter(Actor.name == "Metallverarbeitung König GmbH").first()
    actor_schmidt = db.query(Actor).filter(Actor.name == "Müller Recycling GmbH").first()
    actor_mueller = db.query(Actor).filter(Actor.name == "Hoffmann Metallhandel GmbH").first()

    # Hoffmann Metallhandel anlegen falls nicht vorhanden (gleicher Name wie im Haupt-Seed)
    if actor_mueller is None:
        actor_mueller = Actor(
            id=str(uuid.uuid4()),
            name="Hoffmann Metallhandel GmbH",
            role="haendler",
            organization="Hoffmann Metallhandel GmbH",
            contact_email="ankauf@hoffmann-metallhandel.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        db.add(actor_mueller)
        db.flush()

    # Bestehende Container-Daten loeschen (inkl. abhaengige Requests und Historie)
    db.query(PickupHistoryEntry).delete()
    db.query(PickupRequest).delete()
    db.query(Container).delete()
    db.flush()

    # CNT-2026-001: 30 m3 Industrieneuschrott, 100% voll
    container_a = Container(
        id=str(uuid.uuid4()), container_number="CNT-2026-001",
        owner_id=actor_schmalz.id,
        location="Lagerplatz A - Metallverarbeitung König GmbH, Stuttgart",
        capacity_m3=30.0, fill_level=100,
        status="voll", scrap_class="E1",
        notes="Industrieneuschrott aus laufender Produktion, sauber",
        created_at=datetime(2026, 2, 10), updated_at=datetime(2026, 2, 10),
    )
    # CNT-2026-002: 25 m3 Altschrott, 100% voll, abholbereit
    container_b = Container(
        id=str(uuid.uuid4()), container_number="CNT-2026-002",
        owner_id=actor_schmalz.id,
        location="Lagerplatz B - Metallverarbeitung König GmbH, Stuttgart",
        capacity_m3=25.0, fill_level=100,
        status="abholbereit", scrap_class="E3",
        notes="Gemischter Altschrott, zur Abholung freigegeben",
        created_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 5),
    )
    # CNT-2026-003: 20 m3 Leichtschrott, 97% voll, abholbereit (Wettbewerbs-Demo)
    container_c = Container(
        id=str(uuid.uuid4()), container_number="CNT-2026-003",
        owner_id=actor_schmalz.id,
        location="Lagerplatz C - Metallverarbeitung König GmbH, Stuttgart",
        capacity_m3=20.0, fill_level=97,
        status="abholbereit", scrap_class="E8",
        notes="Leichtschrott/Shredder - zwei konkurrierende Abholantraege vorhanden",
        created_at=datetime(2026, 2, 10), updated_at=datetime(2026, 2, 10),
    )
    db.add_all([container_a, container_b, container_c])
    db.flush()

    # Zwei konkurrierende Abholantraege fuer Container C (haendler-initiiert)
    pr_schmidt = PickupRequest(
        id=str(uuid.uuid4()), container_id=container_c.id,
        requesting_actor_id=actor_schmidt.id,
        initiator="haendler",
        requested_pickup_date=date(2026, 2, 20),
        offered_price_per_ton=185.0, status="ausstehend",
        confirmed_by_metal_processor=False, confirmed_by_trader=False,
        notes="Müller Recycling GmbH: kurzfristige Abholung moeglich, Festpreis 185 EUR/t",
        created_at=datetime(2026, 2, 11, 9, 0), updated_at=datetime(2026, 2, 11, 9, 0),
    )
    pr_mueller = PickupRequest(
        id=str(uuid.uuid4()), container_id=container_c.id,
        requesting_actor_id=actor_mueller.id,
        initiator="haendler",
        requested_pickup_date=date(2026, 2, 22),
        offered_price_per_ton=190.0, status="ausstehend",
        confirmed_by_metal_processor=False, confirmed_by_trader=False,
        notes="Hoffmann Metallhandel: hoeheres Angebot 190 EUR/t, Abholung 2 Tage spaeter",
        created_at=datetime(2026, 2, 11, 14, 30), updated_at=datetime(2026, 2, 11, 14, 30),
    )
    db.add_all([pr_schmidt, pr_mueller])
    db.commit()
    print("Container-Seed-Daten erstellt: 3 Container (capacity_m3/fill_level), 2 Abholantraege.")


def _seed_workflow_batches(db, actor_schmidt, actor_suedstahl, container_ref=None) -> None:
    """Legt zwei Demo-Workflow-Chargen an (entwurf + angeboten) mit Herkunftsketten.
    Wird nur aufgerufen wenn noch keine Workflow-Chargen vorhanden sind.
    """
    from app.services.chemical_service import calculate_threshold_status, calculate_eaf_compatibility

    thresholds = {"Cu": 0.35, "Sn": 0.10, "Ni": 0.15, "Cr": 0.20, "Mo": 0.05}

    # Demo-Abholhistorie: simuliert eine bereits abgeschlossene Containerabholung
    # container_ref: ein vorhandener Container (für NOT NULL FK-Constraint)
    if container_ref is None:
        from app.db.models import Container as _Container
        container_ref = db.query(_Container).first()

    # Demo-PickupRequest (abgeschlossen) — nötig für NOT NULL pickup_request_id
    demo_pr = PickupRequest(
        id=str(uuid.uuid4()),
        container_id=container_ref.id,
        requesting_actor_id=actor_schmidt.id,
        initiator="haendler",
        requested_pickup_date=date(2026, 2, 4),
        offered_price_per_ton=182.0,
        status="abgeholt",
        notes="Demo-Abholung (Workflow-Quellenverknüpfung)",
        confirmed_by_metal_processor=True,
        confirmed_by_trader=True,
        created_at=datetime(2026, 2, 1),
        updated_at=datetime(2026, 2, 5),
    )
    db.add(demo_pr)
    db.flush()

    history_entry = PickupHistoryEntry(
        id=str(uuid.uuid4()),
        container_id=container_ref.id,
        pickup_request_id=demo_pr.id,
        trader_id=actor_schmidt.id,
        metal_processor_id=container_ref.owner_id,
        completed_at=datetime(2026, 2, 5, 11, 0),
        fill_level_at_pickup=100,
        estimated_volume_m3=30.0,
        scrap_type="E1",
    )
    db.add(history_entry)
    db.flush()

    # Workflow-Charge 1: Entwurf (noch nicht angeboten)
    wf_batch1 = ScrapBatch(
        id=str(uuid.uuid4()),
        batch_number="CH-2026-004",
        scrap_class="E1",
        origin_type="Industriebetrieb",
        origin_region="Baden-Württemberg, DE",
        mass_kg=15000.0,
        volume_m3=12.0,
        preparation_degree="gebündelt",
        contamination_level="gering",
        collection_period="Q1 2026",
        owner_id=actor_schmidt.id,
        created_by_trader_id=actor_schmidt.id,
        workflow_status="entwurf",
        confirmed_by_trader=False,
        confirmed_by_steel_mill=False,
        created_at=datetime(2026, 2, 15),
        updated_at=datetime(2026, 2, 15),
    )
    db.add(wf_batch1)
    db.flush()

    # Quellenverknüpfung Charge 1 → Abholhistorie
    db.add(BatchSourcePickup(
        id=str(uuid.uuid4()),
        batch_id=wf_batch1.id,
        pickup_history_entry_id=history_entry.id,
    ))

    # Chemie für Charge 1 (sauber)
    ev1 = {"Cu": 0.18, "Sn": 0.04, "Ni": 0.06, "Cr": 0.03, "Mo": 0.01, "Fe": 99.68}
    exceeded1, exceeded_elements1 = calculate_threshold_status(ev1, thresholds)
    eaf1 = calculate_eaf_compatibility(ev1, thresholds)
    wf_batch1.eaf_compatibility = eaf1
    db.add(ChemicalComposition(
        id=str(uuid.uuid4()),
        batch_id=wf_batch1.id,
        element_values=ev1,
        thresholds=thresholds,
        analysis_method="Händleranalyse (RFA)",
        measured_at=datetime(2026, 2, 16, 9, 0),
        measured_by="Müller Recycling GmbH – internes Labor",
        threshold_exceeded=exceeded1,
        exceeded_elements=exceeded_elements1,
    ))

    # Workflow-Charge 2: Angeboten an Südstahl AG
    wf_batch2 = ScrapBatch(
        id=str(uuid.uuid4()),
        batch_number="CH-2026-005",
        scrap_class="E3",
        origin_type="Gebäudeabriss",
        origin_region="Bayern, DE",
        mass_kg=22000.0,
        volume_m3=18.5,
        preparation_degree="unbearbeitet",
        contamination_level="mittel",
        collection_period="Q1 2026",
        owner_id=actor_schmidt.id,
        created_by_trader_id=actor_schmidt.id,
        offered_to_steel_mill_id=actor_suedstahl.id,
        delivery_date=date(2026, 2, 10),
        workflow_status="angeboten",
        confirmed_by_trader=False,
        confirmed_by_steel_mill=False,
        created_at=datetime(2026, 2, 18),
        updated_at=datetime(2026, 2, 20),
    )
    db.add(wf_batch2)
    db.flush()

    # Chemie für Charge 2 (Cu knapp unter Grenzwert)
    ev2 = {"Cu": 0.32, "Sn": 0.08, "Ni": 0.11, "Cr": 0.07, "Mo": 0.02, "Fe": 99.40}
    exceeded2, exceeded_elements2 = calculate_threshold_status(ev2, thresholds)
    eaf2 = calculate_eaf_compatibility(ev2, thresholds)
    wf_batch2.eaf_compatibility = eaf2
    db.add(ChemicalComposition(
        id=str(uuid.uuid4()),
        batch_id=wf_batch2.id,
        element_values=ev2,
        thresholds=thresholds,
        analysis_method="RFA",
        measured_at=datetime(2026, 2, 19, 10, 30),
        measured_by="Analytiklabor München GmbH",
        threshold_exceeded=exceeded2,
        exceeded_elements=exceeded_elements2,
    ))

    workflow_event_chains = [
        # CH-2026-004: kompakte Kette mit 2 Stationen
        [
            {
                "batch": wf_batch1, "type": "erfassung", "actor_id": container_ref.owner_id,
                "location": "Metallverarbeitung König GmbH, Stuttgart",
                "notes": "Industrieneuschrott in Containerlogistik erfasst und für Händlercharge vorgemerkt.",
                "epcis": "ObjectEvent", "ts": datetime(2026, 2, 5, 11, 0),
            },
            {
                "batch": wf_batch1, "type": "eigentuemerwechsel", "actor_id": actor_schmidt.id,
                "location": "Lager Müller Recycling GmbH, München",
                "notes": "Charge CH-2026-004 aus abgeschlossener Abholung zusammengestellt und in Händlerbestand übernommen.",
                "epcis": "TransactionEvent", "ts": datetime(2026, 2, 15, 12, 15),
            },
        ],
        # CH-2026-005: 3 Stationen bis zum Angebot an das Stahlwerk
        [
            {
                "batch": wf_batch2, "type": "erfassung", "actor_id": container_ref.owner_id,
                "location": "Metallverarbeitung König GmbH, Stuttgart",
                "notes": "Gemischter Schrott aus Rückbauprojekt als Charge vorbereitet.",
                "epcis": "ObjectEvent", "ts": datetime(2026, 2, 10, 8, 30),
            },
            {
                "batch": wf_batch2, "type": "eigentuemerwechsel", "actor_id": actor_schmidt.id,
                "location": "Lager Müller Recycling GmbH, München",
                "notes": "Übernahme und Klassifizierung durch Müller Recycling GmbH.",
                "epcis": "TransactionEvent", "ts": datetime(2026, 2, 18, 9, 45),
            },
            {
                "batch": wf_batch2, "type": "qualitaetspruefung", "actor_id": actor_schmidt.id,
                "location": "Analytiklabor München GmbH",
                "notes": "RFA-Analyse vor Angebotsfreigabe an Südstahl AG durchgeführt.",
                "epcis": "ObjectEvent", "ts": datetime(2026, 2, 19, 10, 30),
            },
        ],
    ]

    for chain in workflow_event_chains:
        for ed in chain:
            db.add(TraceabilityEvent(
                id=str(uuid.uuid4()),
                batch_id=ed["batch"].id,
                event_type=ed["type"],
                timestamp=ed["ts"],
                actor_id=ed["actor_id"],
                location=ed["location"],
                notes=ed["notes"],
                epcis_type=ed["epcis"],
            ))

    workflow_passports = [
        {
            "batch": wf_batch1,
            "status": "entwurf",
            "certification_ref": None,
            "updated_at": datetime(2026, 2, 16, 9, 30),
        },
        {
            "batch": wf_batch2,
            "status": "validiert",
            "certification_ref": None,
            "updated_at": datetime(2026, 2, 19, 11, 0),
        },
    ]

    for pd in workflow_passports:
        db.add(MaterialPassport(
            id=str(uuid.uuid4()),
            batch_id=pd["batch"].id,
            version=1,
            validation_status=pd["status"],
            certification_ref=pd["certification_ref"],
            issuer_id=actor_schmidt.id,
            created_at=pd["updated_at"],
            updated_at=pd["updated_at"],
        ))

    db.flush()
    print("Workflow-Chargen-Seed: CH-2026-004 (entwurf), CH-2026-005 (angeboten an Südstahl).")


def _needs_full_reseed(db) -> bool:
    """Prüft, ob die Demo-Daten noch auf einem alten oder unvollständigen Stand sind."""
    batch_numbers = {
        row[0] for row in db.query(ScrapBatch.batch_number).all() if row[0]
    }
    expected_batch_numbers = {
        "CH-2026-001",
        "CH-2026-002",
        "CH-2026-003",
        "CH-2026-004",
        "CH-2026-005",
        "CH-2026-006",
        "CH-2026-007",
    }

    if batch_numbers != expected_batch_numbers:
        return True

    actor_names = {
        row[0] for row in db.query(Actor.name).all() if row[0]
    }
    expected_actor_names = {
        "Metallverarbeitung König GmbH",
        "Schmidt Stanzteile GmbH",
        "Bauer Metallbau GmbH",
        "Müller Recycling GmbH",
        "Hoffmann Metallhandel GmbH",
        "Keller Schrott GmbH",
        "Südstahl AG",
        "Oststahl AG",
        "Nordstahl AG",
    }

    if actor_names != expected_actor_names:
        return True

    required_batches = {
        "CH-2026-004": {"min_events": 2},
        "CH-2026-005": {"min_events": 3},
        "CH-2026-006": {"min_events": 4},
        "CH-2026-007": {"min_events": 2},
    }

    for batch_number, rules in required_batches.items():
        batch = db.query(ScrapBatch).filter(ScrapBatch.batch_number == batch_number).first()
        if batch is None:
            return True

        passport = db.query(MaterialPassport).filter(MaterialPassport.batch_id == batch.id).first()
        if passport is None:
            return True

        event_count = db.query(TraceabilityEvent).filter(TraceabilityEvent.batch_id == batch.id).count()
        if event_count < rules["min_events"]:
            return True

    return False


def seed():
    db = SessionLocal()
    try:
        # Prüfe, ob die Demo-Daten bereits vollständig dem aktuellen Stand entsprechen
        if db.query(Actor).count() > 0:
            if _needs_full_reseed(db):
                print("Veraltete oder unvollständige Demo-Daten gefunden – vollständiges Reseed wird ausgeführt.")
                _clear_all_data(db)
            else:
                print("Seed-Daten aktuell – Seed wird uebersprungen.")
                return

        # Container-Reseed noetig wenn:
        # a) Keine Container vorhanden (erste Initialisierung nach Migration 0003)
        # b) capacity_m3 > 500 → alte kg-Werte aus Migration 0003→0004 Konvertierung
        existing_new = db.query(Actor).filter(Actor.name == "Müller Recycling GmbH").count()
        if existing_new > 0:
            # Container-Reseed noetig wenn:
            # a) Keine Container vorhanden (erste Initialisierung nach Migration 0003)
            # b) capacity_m3 > 500 → alte kg-Werte aus Migration 0003→0004 Konvertierung
            container_count = db.query(Container).count()
            needs_reseed = False
            if container_count == 0:
                print("Container-Daten fehlen – erstelle Container-Seed-Daten...")
                needs_reseed = True
            else:
                # Pruefen ob alte kg-Werte noch drin sind (capacity_m3 > 500)
                from sqlalchemy import text
                result = db.execute(
                    text("SELECT COUNT(*) FROM containers WHERE capacity_m3 > 500")
                ).scalar()
                if result > 0:
                    print("Veraltete Container-Schema-Werte gefunden – reseed nach Migration 0004...")
                    needs_reseed = True

            if needs_reseed:
                _seed_containers(db)

            # Workflow-Chargen anlegen falls noch keine vorhanden
            wf_count = db.query(ScrapBatch).filter(
                ScrapBatch.created_by_trader_id != None
            ).count()
            if wf_count == 0:
                actor_schmidt = db.query(Actor).filter(Actor.name == "Müller Recycling GmbH").first()
                actor_suedstahl = db.query(Actor).filter(Actor.name == "Südstahl AG").first()
                if actor_schmidt and actor_suedstahl:
                    _seed_workflow_batches(db, actor_schmidt, actor_suedstahl)
                    db.commit()
            else:
                print("Seed-Daten aktuell – Seed wird uebersprungen.")
            return

        print("Erstelle Demo-Seed-Daten (Kapitel 6.2)...")

        # ── Akteure ───────────────────────────────────────────────────────────
        actor_schmalz = Actor(
            id=str(uuid.uuid4()),
            name="Metallverarbeitung König GmbH",
            role="metallverarbeiter",
            organization="Metallverarbeitung König GmbH",
            contact_email="info@koenig-metallverarbeitung.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        actor_schmidt = Actor(
            id=str(uuid.uuid4()),
            name="Müller Recycling GmbH",
            role="haendler",
            organization="Müller Recycling GmbH",
            contact_email="handel@mueller-recycling.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        # Stahlwerk Standard-Tier: sieht Basisinfos, keine erweiterte Herkunft
        actor_suedstahl = Actor(
            id=str(uuid.uuid4()),
            name="Südstahl AG",
            role="stahlwerk",
            organization="Südstahl AG",
            contact_email="einkauf@suedstahl.de",
            relationship_tier="standard",
            created_at=datetime(2026, 2, 5),
        )
        # Stahlwerk Strategic-Tier: vertrauensbasierte Partnerschaft mit Müller Recycling
        actor_thyssen = Actor(
            id=str(uuid.uuid4()),
            name="Oststahl AG",
            role="stahlwerk",
            organization="Oststahl AG",
            contact_email="einkauf@oststahl.de",
            relationship_tier="strategic",
            created_at=datetime(2026, 2, 5),
        )
        # Zweiter Händler für Container-Logistik-Demo (konkurrierender Abholantrag)
        actor_mueller = Actor(
            id=str(uuid.uuid4()),
            name="Hoffmann Metallhandel GmbH",
            role="haendler",
            organization="Hoffmann Metallhandel GmbH",
            contact_email="ankauf@hoffmann-metallhandel.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        actor_bauer = Actor(
            id=str(uuid.uuid4()),
            name="Bauer Metallbau GmbH",
            role="metallverarbeiter",
            organization="Bauer Metallbau GmbH",
            contact_email="info@bauer-metallbau.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        actor_stanzteile = Actor(
            id=str(uuid.uuid4()),
            name="Schmidt Stanzteile GmbH",
            role="metallverarbeiter",
            organization="Schmidt Stanzteile GmbH",
            contact_email="info@schmidt-stanzteile.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        actor_keller = Actor(
            id=str(uuid.uuid4()),
            name="Keller Schrott GmbH",
            role="haendler",
            organization="Keller Schrott GmbH",
            contact_email="handel@keller-schrott.de",
            relationship_tier=None,
            created_at=datetime(2026, 2, 5),
        )
        actor_nordstahl = Actor(
            id=str(uuid.uuid4()),
            name="Nordstahl AG",
            role="stahlwerk",
            organization="Nordstahl AG",
            contact_email="einkauf@nordstahl.de",
            relationship_tier="preferred",
            created_at=datetime(2026, 2, 5),
        )
        db.add_all([
            actor_schmalz,
            actor_stanzteile,
            actor_bauer,
            actor_schmidt,
            actor_mueller,
            actor_keller,
            actor_suedstahl,
            actor_thyssen,
            actor_nordstahl,
        ])
        db.flush()

        # ── Schrottchargen ────────────────────────────────────────────────────
        #
        # Charge 1: Altschrott Gebäudeabriss — Cu ÜBER Grenzwert → EAF: bedingt geeignet
        batch1 = ScrapBatch(
            id=str(uuid.uuid4()),
            batch_number="CH-2026-001",
            scrap_class="E3",
            origin_type="Gebäudeabriss",
            origin_region="Bayern, DE",
            mass_kg=24500.0,
            volume_m3=19.0,
            collection_period="Q1 2026",
            preparation_degree="unbearbeitet",
            contamination_level="mittel",
            price_basis="LME Kupfer - 8%",
            pricing_formula_ref="KD-2025-SCHMALZ-001",
            supplier_id=actor_schmalz.id,
            supplier_source="Metallverarbeitung König GmbH",      # Legacy-Feld
            price_per_ton=None,
            owner_id=actor_schmidt.id,
            created_at=datetime(2026, 2, 15),
            updated_at=datetime(2026, 2, 15),
        )
        # Charge 2: Industrieneuschrott — alle Werte im Normalbereich → EAF: geeignet
        batch2 = ScrapBatch(
            id=str(uuid.uuid4()),
            batch_number="CH-2026-002",
            scrap_class="E1",
            origin_type="Industriebetrieb",
            origin_region="Baden-Württemberg, DE",
            mass_kg=18000.0,
            volume_m3=12.5,
            collection_period="Q1 2026",
            preparation_degree="gebündelt",
            contamination_level="gering",
            price_basis="LME Kupfer + 2%",
            pricing_formula_ref="KD-2025-SCHMALZ-002",
            supplier_id=actor_schmalz.id,
            supplier_source="Metallverarbeitung König GmbH",
            price_per_ton=None,
            owner_id=actor_schmidt.id,
            created_at=datetime(2026, 2, 3),
            updated_at=datetime(2026, 2, 3),
        )
        # Charge 3: Gemischter Altschrott Wertstoffhof — Sn ÜBER Grenzwert → EAF: bedingt geeignet
        batch3 = ScrapBatch(
            id=str(uuid.uuid4()),
            batch_number="CH-2026-003",
            scrap_class="E8",
            origin_type="Wertstoffhof",
            origin_region="Sachsen, DE",
            mass_kg=31200.0,
            volume_m3=45.0,
            collection_period="Q1 2026",
            preparation_degree="geschreddert",
            contamination_level="hoch",
            price_basis="Festpreis 180 EUR/t",
            pricing_formula_ref="KD-2025-SCHMALZ-003",
            supplier_id=actor_schmalz.id,
            supplier_source="Metallverarbeitung König GmbH",
            price_per_ton=None,
            owner_id=actor_schmidt.id,
            created_at=datetime(2026, 2, 10),
            updated_at=datetime(2026, 2, 10),
        )
        batch4 = ScrapBatch(
            id=str(uuid.uuid4()),
            batch_number="CH-2026-006",
            scrap_class="E6",
            origin_type="Neuschrott",
            origin_region="Nordrhein-Westfalen, DE",
            mass_kg=26800.0,
            volume_m3=21.0,
            collection_period="Q1 2026",
            preparation_degree="sortiert",
            contamination_level="gering",
            price_basis="Indexpreis + Qualitätsbonus",
            pricing_formula_ref="KD-2025-KOENIG-004",
            supplier_id=actor_bauer.id,
            supplier_source="Bauer Metallbau GmbH",
            price_per_ton=None,
            owner_id=actor_mueller.id,
            created_at=datetime(2026, 2, 18),
            updated_at=datetime(2026, 2, 18),
        )
        batch5 = ScrapBatch(
            id=str(uuid.uuid4()),
        batch_number="CH-2026-007",
        scrap_class="E2",
            origin_type="Industriebetrieb",
            origin_region="Hessen, DE",
            mass_kg=19500.0,
            volume_m3=14.0,
            collection_period="Q1 2026",
            preparation_degree="gebündelt",
            contamination_level="gering",
            price_basis="Festpreis 228 EUR/t",
            pricing_formula_ref="KD-2025-STANZ-005",
            supplier_id=actor_stanzteile.id,
            supplier_source="Schmidt Stanzteile GmbH",
            price_per_ton=None,
            owner_id=actor_keller.id,
            created_at=datetime(2026, 2, 24),
            updated_at=datetime(2026, 2, 24),
        )
        db.add_all([batch1, batch2, batch3, batch4, batch5])
        db.flush()

        # ── Chemische Zusammensetzungen ───────────────────────────────────────
        # Grenzwerte gemäß Demo-Szenario
        thresholds_demo = {
            "Cu": 0.35,   # Charge 1: Cu = 0.41 → ÜBERSCHRITTEN
            "Sn": 0.10,   # Charge 3: Sn = 0.11 → ÜBERSCHRITTEN
            "Ni": 0.15,
            "Cr": 0.20,
            "Mo": 0.05,
            "S":  0.05,
            "P":  0.04,
        }

        chemical_data = [
            # Charge 1: Cu über Grenzwert (0.41 > 0.35)
            {
                "batch": batch1,
                "element_values": {
                    "Cu": 0.41, "Sn": 0.08, "Ni": 0.12, "Cr": 0.05,
                    "Mo": 0.02, "S": 0.03, "P": 0.02, "Fe": 99.27,
                },
                "thresholds": thresholds_demo,
                "analysis_method": "RFA",
                "measured_by": "Analytiklabor München GmbH",
                "measured_at": datetime(2026, 2, 17, 10, 30),
            },
            # Charge 2: alle Werte sauber
            {
                "batch": batch2,
                "element_values": {
                    "Cu": 0.18, "Sn": 0.03, "Ni": 0.05, "Cr": 0.02,
                    "Mo": 0.01, "S": 0.01, "P": 0.01, "Fe": 99.69,
                },
                "thresholds": thresholds_demo,
                "analysis_method": "OES",
                "measured_by": "Müller Recycling GmbH – internes Labor",
                "measured_at": datetime(2026, 2, 5, 9, 0),
            },
            # Charge 3: Sn über Grenzwert (0.11 > 0.10)
            {
                "batch": batch3,
                "element_values": {
                    "Cu": 0.28, "Sn": 0.11, "Ni": 0.08, "Cr": 0.04,
                    "Mo": 0.01, "S": 0.05, "P": 0.03, "Fe": 99.40,
                },
                "thresholds": thresholds_demo,
                "analysis_method": "Laboranalyse",
                "measured_by": "TÜV Sachsen Prüfstelle",
                "measured_at": datetime(2026, 2, 12, 14, 0),
            },
            {
                "batch": batch4,
                "element_values": {
                    "Cu": 0.16, "Sn": 0.03, "Ni": 0.06, "Cr": 0.05,
                    "Mo": 0.01, "S": 0.02, "P": 0.01, "Fe": 99.66,
                },
                "thresholds": thresholds_demo,
                "analysis_method": "OES",
                "measured_by": "Hoffmann Metallhandel GmbH – Labor West",
                "measured_at": datetime(2026, 2, 19, 8, 45),
            },
            {
                "batch": batch5,
                "element_values": {
                    "Cu": 0.12, "Sn": 0.02, "Ni": 0.04, "Cr": 0.03,
                    "Mo": 0.01, "S": 0.01, "P": 0.01, "Fe": 99.76,
                },
                "thresholds": thresholds_demo,
                "analysis_method": "RFA",
                "measured_by": "Keller Schrott GmbH – Qualitätslabor",
                "measured_at": datetime(2026, 2, 25, 10, 15),
            },
        ]

        compositions = []
        for cd in chemical_data:
            exceeded, exceeded_elements = calculate_threshold_status(
                cd["element_values"], cd["thresholds"]
            )
            eaf = calculate_eaf_compatibility(cd["element_values"], cd["thresholds"])
            cd["batch"].eaf_compatibility = eaf

            c = ChemicalComposition(
                id=str(uuid.uuid4()),
                batch_id=cd["batch"].id,
                element_values=cd["element_values"],
                thresholds=cd["thresholds"],
                analysis_method=cd["analysis_method"],
                measured_at=cd["measured_at"],
                measured_by=cd["measured_by"],
                threshold_exceeded=exceeded,
                exceeded_elements=exceeded_elements,
            )
            compositions.append(c)

        db.add_all(compositions)
        db.flush()

        # ── Qualitätsanalysen ─────────────────────────────────────────────────
        quality_data = [
            {
                "batch": batch1, "condition": "leicht verunreinigt", "density": "schwer",
                "dimension": "mitteldimensioniert", "moisture": 4.2, "oil": False,
                "radioactive": True, "inspector": actor_schmidt,
                "inspected_at": datetime(2026, 2, 16, 14, 0),
            },
            {
                "batch": batch2, "condition": "sauber", "density": "schwer",
                "dimension": "mitteldimensioniert", "moisture": 0.9, "oil": False,
                "radioactive": True, "inspector": actor_schmidt,
                "inspected_at": datetime(2026, 2, 4, 11, 0),
            },
            {
                "batch": batch3, "condition": "stark verunreinigt", "density": "leicht",
                "dimension": "kleindimensioniert", "moisture": 7.5, "oil": True,
                "radioactive": True, "inspector": actor_schmidt,
                "inspected_at": datetime(2026, 2, 11, 10, 0),
            },
            {
                "batch": batch4, "condition": "sauber", "density": "schwer",
                "dimension": "grossdimensioniert", "moisture": 1.1, "oil": False,
                "radioactive": True, "inspector": actor_mueller,
                "inspected_at": datetime(2026, 2, 19, 9, 15),
            },
            {
                "batch": batch5, "condition": "sauber", "density": "mittel",
                "dimension": "mitteldimensioniert", "moisture": 0.8, "oil": False,
                "radioactive": True, "inspector": actor_keller,
                "inspected_at": datetime(2026, 2, 25, 11, 0),
            },
        ]

        for qd in quality_data:
            qa = QualityAnalysis(
                id=str(uuid.uuid4()),
                batch_id=qd["batch"].id,
                physical_condition=qd["condition"],
                density_class=qd["density"],
                dimension_class=qd["dimension"],
                moisture_content=qd["moisture"],
                oil_residue=qd["oil"],
                radioactive_cleared=qd["radioactive"],
                inspected_at=qd["inspected_at"],
                inspector_id=qd["inspector"].id,
            )
            db.add(qa)

        db.flush()

        # ── Rückverfolgbarkeitsereignisse ─────────────────────────────────────
        event_chains = [
            # Charge 1: E3 Gebäudeabriss
            [
                {
                    "batch": batch1, "type": "erfassung", "actor": actor_schmalz,
                    "location": "Abrissgelände Augsburg", "epcis": "ObjectEvent",
                    "notes": "Schrott aus Gebäudeabriss erfasst und gewogen",
                    "ts": datetime(2026, 2, 15, 8, 0),
                },
                {
                    "batch": batch1, "type": "eigentuemerwechsel", "actor": actor_schmidt,
                    "location": "Lager Müller Recycling GmbH, München", "epcis": "TransactionEvent",
                    "notes": "Übernahme durch Müller Recycling GmbH",
                    "ts": datetime(2026, 2, 15, 16, 0),
                },
                {
                    "batch": batch1, "type": "qualitaetspruefung", "actor": actor_schmidt,
                    "location": "Analytiklabor München", "epcis": "ObjectEvent",
                    "notes": "RFA-Analyse: Cu = 0.41% – Grenzwert 0.35% überschritten",
                    "ts": datetime(2026, 2, 17, 10, 30),
                },
                {
                    "batch": batch1, "type": "anlieferung", "actor": actor_suedstahl,
                    "location": "Südstahl AG Werk, Nürnberg – Wiegebrücke", "epcis": "ObjectEvent",
                    "notes": "Anlieferung mit Hinweis auf Cu-Überschreitung (Sonderfreigabe)",
                    "ts": datetime(2026, 2, 20, 6, 30),
                },
            ],
            # Charge 2: E1 Industrieneuschrott
            [
                {
                    "batch": batch2, "type": "erfassung", "actor": actor_schmalz,
                    "location": "Industriebetrieb Stuttgart", "epcis": "ObjectEvent",
                    "notes": "Neuschrott aus Produktionsrückständen – direkt gebündelt",
                    "ts": datetime(2026, 2, 3, 9, 0),
                },
                {
                    "batch": batch2, "type": "aufbereitung", "actor": actor_schmalz,
                    "location": "Aufbereitungsanlage König, Stuttgart", "epcis": "ObjectEvent",
                    "notes": "Paketierung auf 500kg-Ballen",
                    "ts": datetime(2026, 2, 3, 14, 0),
                },
                {
                    "batch": batch2, "type": "eigentuemerwechsel", "actor": actor_schmidt,
                    "location": "Lager Müller Recycling GmbH, München", "epcis": "TransactionEvent",
                    "notes": "Übernahme durch Müller Recycling GmbH – erstklassige Qualität",
                    "ts": datetime(2026, 2, 4, 10, 0),
                },
                {
                    "batch": batch2, "type": "qualitaetspruefung", "actor": actor_schmidt,
                    "location": "Müller Recycling internes Labor", "epcis": "ObjectEvent",
                    "notes": "OES-Analyse: alle Werte im Normalbereich",
                    "ts": datetime(2026, 2, 5, 9, 0),
                },
            ],
            # Charge 3: E8 Wertstoffhof
            [
                {
                    "batch": batch3, "type": "erfassung", "actor": actor_schmalz,
                    "location": "Wertstoffhof Leipzig", "epcis": "ObjectEvent",
                    "notes": "Gemischter Altschrott – hoher Verunreinigungsgrad",
                    "ts": datetime(2026, 2, 10, 8, 0),
                },
                {
                    "batch": batch3, "type": "aufbereitung", "actor": actor_schmalz,
                    "location": "Shredder-Anlage König, Leipzig", "epcis": "ObjectEvent",
                    "notes": "Geschreddert, Magnetscheidung durchgeführt",
                    "ts": datetime(2026, 2, 10, 14, 0),
                },
                {
                    "batch": batch3, "type": "eigentuemerwechsel", "actor": actor_schmidt,
                    "location": "Lager Müller Recycling GmbH, München", "epcis": "TransactionEvent",
                    "notes": "Übernahme durch Müller Recycling GmbH – Qualitätsvorbehalt",
                    "ts": datetime(2026, 2, 11, 9, 0),
                },
                {
                    "batch": batch3, "type": "qualitaetspruefung", "actor": actor_schmidt,
                    "location": "TÜV Sachsen Prüfstelle", "epcis": "ObjectEvent",
                    "notes": "Laboranalyse: Sn = 0.11% – Grenzwert 0.10% überschritten",
                    "ts": datetime(2026, 2, 12, 14, 0),
                },
            ],
            # Charge 4: E6 Neuschrott
            [
                {
                    "batch": batch4, "type": "erfassung", "actor": actor_bauer,
                    "location": "Werkshof Bauer Metallbau, Dortmund", "epcis": "ObjectEvent",
                    "notes": "Sortenreiner Neuschrott aus Profilzuschnitten erfasst",
                    "ts": datetime(2026, 2, 18, 7, 45),
                },
                {
                    "batch": batch4, "type": "eigentuemerwechsel", "actor": actor_mueller,
                    "location": "Lager Hoffmann Metallhandel GmbH, Essen", "epcis": "TransactionEvent",
                    "notes": "Übernahme durch Hoffmann Metallhandel GmbH",
                    "ts": datetime(2026, 2, 18, 15, 30),
                },
                {
                    "batch": batch4, "type": "qualitaetspruefung", "actor": actor_mueller,
                    "location": "Labor West, Essen", "epcis": "ObjectEvent",
                    "notes": "OES-Analyse: alle relevanten Werte deutlich im Zielkorridor",
                    "ts": datetime(2026, 2, 19, 8, 45),
                },
                {
                    "batch": batch4, "type": "anlieferung", "actor": actor_nordstahl,
                    "location": "Nordstahl AG Werk, Bremen", "epcis": "ObjectEvent",
                    "notes": "Planmäßige Anlieferung ohne Qualitätsabweichungen",
                    "ts": datetime(2026, 2, 22, 6, 50),
                },
            ],
            # Charge 5: E2 gebündelter Industrieneuschrott
            [
                {
                    "batch": batch5, "type": "erfassung", "actor": actor_stanzteile,
                    "location": "Presswerk Schmidt Stanzteile, Kassel", "epcis": "ObjectEvent",
                    "notes": "Gebündelter Produktionsschrott aus Stanzprozessen erfasst",
                    "ts": datetime(2026, 2, 24, 8, 20),
                },
                {
                    "batch": batch5, "type": "anlieferung", "actor": actor_thyssen,
                    "location": "Oststahl AG Werk, Duisburg", "epcis": "ObjectEvent",
                    "notes": "Direktlieferung der gebündelten Qualitätscharge an Oststahl AG bestätigt",
                    "ts": datetime(2026, 2, 26, 7, 10),
                },
            ],
        ]

        for chain in event_chains:
            for ed in chain:
                event = TraceabilityEvent(
                    id=str(uuid.uuid4()),
                    batch_id=ed["batch"].id,
                    event_type=ed["type"],
                    timestamp=ed["ts"],
                    actor_id=ed["actor"].id,
                    location=ed["location"],
                    notes=ed["notes"],
                    epcis_type=ed["epcis"],
                )
                db.add(event)

        db.flush()

        # ── Materialpässe ─────────────────────────────────────────────────────
        passport_data = [
            {
                "batch": batch1, "issuer": actor_schmidt, "status": "validiert",
                "cert": None, "version": 1,
            },
            {
                "batch": batch2, "issuer": actor_schmidt, "status": "zertifiziert",
                "cert": "CERT-2025-E1-0102", "version": 1,
            },
            {
                "batch": batch3, "issuer": actor_schmidt, "status": "entwurf",
                "cert": None, "version": 1,
            },
            {
                "batch": batch4, "issuer": actor_mueller, "status": "zertifiziert",
                "cert": "CERT-2026-E6-0006", "version": 1,
            },
            {
                "batch": batch5, "issuer": actor_keller, "status": "validiert",
                "cert": None, "version": 1,
            },
        ]

        for pd in passport_data:
            passport = MaterialPassport(
                id=str(uuid.uuid4()),
                batch_id=pd["batch"].id,
                version=pd["version"],
                validation_status=pd["status"],
                certification_ref=pd["cert"],
                issuer_id=pd["issuer"].id,
                created_at=datetime(2026, 2, 15),
                updated_at=datetime(2026, 2, 15),
            )
            db.add(passport)

        db.flush()

        # ── Logistikaufträge ──────────────────────────────────────────────────
        logistics_data = [
            {
                "batch": batch1, "actor": actor_schmidt,
                "pickup_date": date(2026, 2, 19),
                "delivery_date": date(2026, 2, 20),
                "pickup_location": "Lager Müller Recycling GmbH, München",
                "delivery_location": "Südstahl AG Werk, Nürnberg",
                "container_status": "abholbereit", "delivery_status": "geliefert",
                "carrier": "Schrottlogistik Bayern GmbH",
                "notes": "Sonderfreigabe erteilt. Händlerlieferung am 20.02.2026 vollständig entladen.",
            },
            {
                "batch": batch2, "actor": actor_schmidt,
                "pickup_date": date(2026, 2, 5),
                "delivery_date": date(2026, 2, 7),
                "pickup_location": "Lager Müller Recycling GmbH, München",
                "delivery_location": "Oststahl AG Werk, Duisburg",
                "container_status": "voll", "delivery_status": "geplant",
                "carrier": "TransLogistik Nord GmbH",
                "notes": "Anlieferfenster mit Oststahl AG für 07.02.2026, 08:00-10:00 Uhr abgestimmt.",
            },
            {
                "batch": batch3, "actor": actor_schmidt,
                "pickup_date": date(2026, 2, 12),
                "delivery_date": date(2026, 2, 13),
                "pickup_location": "Lager Müller Recycling GmbH, München",
                "delivery_location": "Südstahl AG Werk, Nürnberg",
                "container_status": "abholbereit", "delivery_status": "in_transit",
                "carrier": "Bayerische Schrottlogistik KG",
                "notes": "ETA Südstahl AG: 13.02.2026 gegen 09:30 Uhr. Sn-Überschreitung kommuniziert, Abzug vereinbart.",
            },
            {
                "batch": batch4, "actor": actor_mueller,
                "pickup_date": date(2026, 2, 21),
                "delivery_date": date(2026, 2, 22),
                "pickup_location": "Lager Hoffmann Metallhandel GmbH, Essen",
                "delivery_location": "Nordstahl AG Werk, Bremen",
                "container_status": "voll", "delivery_status": "geliefert",
                "carrier": "RuhrCargo Stahlservice GmbH",
                "notes": "Saubere Neuschrottcharge, ohne Abweichungen übernommen",
            },
            {
                "batch": batch5, "actor": actor_keller,
                "pickup_date": date(2026, 2, 26),
                "delivery_date": date(2026, 2, 26),
                "pickup_location": "Lager Keller Schrott GmbH, Kassel",
                "delivery_location": "Oststahl AG Werk, Duisburg",
                "container_status": "abholbereit", "delivery_status": "geliefert",
                "carrier": "MitteLog Transport GmbH",
                "notes": "Gebündelte Qualitätscharge termingerecht angeliefert",
            },
        ]

        for ld in logistics_data:
            order = LogisticsOrder(
                id=str(uuid.uuid4()),
                batch_id=ld["batch"].id,
                requesting_actor_id=ld["actor"].id,
                pickup_date=ld["pickup_date"],
                delivery_date=ld["delivery_date"],
                pickup_location=ld["pickup_location"],
                delivery_location=ld["delivery_location"],
                container_status=ld["container_status"],
                delivery_status=ld["delivery_status"],
                carrier=ld["carrier"],
                notes=ld["notes"],
                created_at=datetime(2026, 2, 15),
                updated_at=datetime(2026, 2, 15),
            )
            db.add(order)

        # ── CBAM-Einträge ─────────────────────────────────────────────────────
        cbam_entries = [
            {
                "batch": batch1, "s1": 148.2, "s2": 52.4, "s3": 38.7,
                "method": "GHG-Protocol Scope 1+2+3", "period": "2026-Q1",
            },
            {
                "batch": batch2, "s1": 92.5, "s2": 31.8, "s3": 22.1,
                "method": "GHG-Protocol Scope 1+2", "period": "2026-Q1",
            },
            {
                "batch": batch4, "s1": 96.4, "s2": 33.2, "s3": 24.5,
                "method": "GHG-Protocol Scope 1+2", "period": "2026-Q1",
            },
            {
                "batch": batch5, "s1": 88.9, "s2": 29.7, "s3": 20.8,
                "method": "GHG-Protocol Scope 1+2", "period": "2026-Q1",
            },
        ]

        for cd in cbam_entries:
            cbam = CBAMRecord(
                id=str(uuid.uuid4()),
                batch_id=cd["batch"].id,
                scope1_emissions_kg=cd["s1"],
                scope2_emissions_kg=cd["s2"],
                scope3_emissions_kg=cd["s3"],
                calculation_method=cd["method"],
                reporting_period=cd["period"],
                created_at=datetime(2026, 2, 28),
            )
            db.add(cbam)

        # ── FieldAccessPolicies (DB-Dokumentation der Casbin-Policy) ──────────
        # Spiegelt abac_policy.csv für die Audit-Nachvollziehbarkeit in der DB.
        policies = [
            # Metallverarbeiter
            {"field": "batch_number",           "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "scrap_class",             "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "origin_type",             "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "origin_region",           "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "collection_period",       "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "mass_kg",                 "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "volume_m3",               "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "preparation_degree",      "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "price_basis",             "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "pricing_formula_ref",     "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "eaf_compatibility",       "role": "metallverarbeiter", "rule": "deny",  "tier": None},
            {"field": "supplier_id",             "role": "metallverarbeiter", "rule": "deny",  "tier": None},
            {"field": "contamination_level",     "role": "metallverarbeiter", "rule": "allow", "tier": None},
            {"field": "element_values",          "role": "metallverarbeiter", "rule": "deny",  "tier": None},
            # Händler
            {"field": "batch_number",            "role": "haendler", "rule": "allow", "tier": None},
            {"field": "scrap_class",             "role": "haendler", "rule": "allow", "tier": None},
            {"field": "origin_type",             "role": "haendler", "rule": "allow", "tier": None},
            {"field": "origin_region",           "role": "haendler", "rule": "allow", "tier": None},
            {"field": "collection_period",       "role": "haendler", "rule": "allow", "tier": None},
            {"field": "mass_kg",                 "role": "haendler", "rule": "allow", "tier": None},
            {"field": "preparation_degree",      "role": "haendler", "rule": "allow", "tier": None},
            {"field": "contamination_level",     "role": "haendler", "rule": "allow", "tier": None},
            {"field": "price_basis",             "role": "haendler", "rule": "allow", "tier": None},
            {"field": "pricing_formula_ref",     "role": "haendler", "rule": "allow", "tier": None},
            {"field": "supplier_id",             "role": "haendler", "rule": "allow", "tier": None},
            {"field": "element_values",          "role": "haendler", "rule": "allow", "tier": None},
            {"field": "thresholds",              "role": "haendler", "rule": "allow", "tier": None},
            {"field": "exceeded_elements",       "role": "haendler", "rule": "allow", "tier": None},
            # Stahlwerk – Standard (alle Tiers)
            {"field": "batch_number",            "role": "stahlwerk", "rule": "allow", "tier": None},
            {"field": "scrap_class",             "role": "stahlwerk", "rule": "allow", "tier": None},
            {"field": "mass_kg",                 "role": "stahlwerk", "rule": "allow", "tier": None},
            {"field": "preparation_degree",      "role": "stahlwerk", "rule": "allow", "tier": None},
            {"field": "collection_period",       "role": "stahlwerk", "rule": "allow", "tier": None},
            {"field": "supplier_id",             "role": "stahlwerk", "rule": "deny",  "tier": None},
            {"field": "price_basis",             "role": "stahlwerk", "rule": "deny",  "tier": None},
            {"field": "pricing_formula_ref",     "role": "stahlwerk", "rule": "deny",  "tier": None},
            {"field": "origin_type",             "role": "stahlwerk", "rule": "deny",  "tier": "standard"},
            {"field": "origin_region",           "role": "stahlwerk", "rule": "deny",  "tier": "standard"},
            # Stahlwerk – Preferred-Tier
            {"field": "origin_type",             "role": "stahlwerk", "rule": "allow", "tier": "preferred"},
            {"field": "origin_region",           "role": "stahlwerk", "rule": "allow", "tier": "preferred"},
            {"field": "volume_m3",               "role": "stahlwerk", "rule": "allow", "tier": "preferred"},
            # Stahlwerk – Strategic-Tier
            {"field": "contamination_level",     "role": "stahlwerk", "rule": "allow", "tier": "strategic"},
            {"field": "eaf_compatibility",       "role": "stahlwerk", "rule": "allow", "tier": "strategic"},
            {"field": "element_values",          "role": "stahlwerk", "rule": "allow", "tier": "strategic"},
            {"field": "thresholds",              "role": "stahlwerk", "rule": "allow", "tier": "strategic"},
            {"field": "exceeded_elements",       "role": "stahlwerk", "rule": "allow", "tier": "strategic"},
            {"field": "threshold_exceeded",      "role": "stahlwerk", "rule": "allow", "tier": "strategic"},
        ]

        for p in policies:
            fap = FieldAccessPolicy(
                id=str(uuid.uuid4()),
                data_field=p["field"],
                actor_role=p["role"],
                access_rule=p["rule"],
                is_default=True,
                relationship_tier=p["tier"],
                created_at=datetime(2026, 2, 1),
            )
            db.add(fap)

        # ── Container (Metallverarbeitung König GmbH - neues Volumen-Schema) ─
        container_a = Container(
            id=str(uuid.uuid4()), container_number="CNT-2026-001",
            owner_id=actor_schmalz.id,
            location="Lagerplatz A - Metallverarbeitung König GmbH, Stuttgart",
            capacity_m3=30.0, fill_level=100,
            status="voll", scrap_class="E1",
            notes="Industrieneuschrott aus laufender Produktion, sauber",
            created_at=datetime(2026, 2, 10), updated_at=datetime(2026, 2, 10),
        )
        container_b = Container(
            id=str(uuid.uuid4()), container_number="CNT-2026-002",
            owner_id=actor_schmalz.id,
            location="Lagerplatz B - Metallverarbeitung König GmbH, Stuttgart",
            capacity_m3=25.0, fill_level=100,
            status="abholbereit", scrap_class="E3",
            notes="Gemischter Altschrott, zur Abholung freigegeben",
            created_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 5),
        )
        container_c = Container(
            id=str(uuid.uuid4()), container_number="CNT-2026-003",
            owner_id=actor_schmalz.id,
            location="Lagerplatz C - Metallverarbeitung König GmbH, Stuttgart",
            capacity_m3=20.0, fill_level=97,
            status="abholbereit", scrap_class="E8",
            notes="Leichtschrott/Shredder - zwei konkurrierende Abholantraege vorhanden",
            created_at=datetime(2026, 2, 10), updated_at=datetime(2026, 2, 10),
        )
        db.add_all([container_a, container_b, container_c])
        db.flush()

        # ── Abholantraege fuer Container C (Wettbewerb zwischen Haendlern) ────
        pr_schmidt = PickupRequest(
            id=str(uuid.uuid4()), container_id=container_c.id,
            requesting_actor_id=actor_schmidt.id,
            initiator="haendler",
            requested_pickup_date=date(2026, 2, 20),
            offered_price_per_ton=185.0, status="ausstehend",
            confirmed_by_metal_processor=False, confirmed_by_trader=False,
            notes="Müller Recycling GmbH: kurzfristige Abholung moeglich, Festpreis 185 EUR/t",
            created_at=datetime(2026, 2, 11, 9, 0), updated_at=datetime(2026, 2, 11, 9, 0),
        )
        pr_mueller = PickupRequest(
            id=str(uuid.uuid4()), container_id=container_c.id,
            requesting_actor_id=actor_mueller.id,
            initiator="haendler",
            requested_pickup_date=date(2026, 2, 22),
            offered_price_per_ton=190.0, status="ausstehend",
            confirmed_by_metal_processor=False, confirmed_by_trader=False,
            notes="Hoffmann Metallhandel GmbH: hoeheres Angebot 190 EUR/t, Abholung 2 Tage spaeter",
            created_at=datetime(2026, 2, 11, 14, 30), updated_at=datetime(2026, 2, 11, 14, 30),
        )
        db.add_all([pr_schmidt, pr_mueller])
        db.flush()

        # ── Workflow-Chargen (Händler→Stahlwerk-Demo) ─────────────────────────
        _seed_workflow_batches(db, actor_schmidt, actor_suedstahl, container_a)

        db.commit()
        print(
            f"Demo-Seed erfolgreich: 9 Akteure, 5 Standard-Chargen + 2 Workflow-Chargen, "
            f"{len(compositions)} Analysen, 3 Logistikauftraege, "
            f"3 Container, 2 Abholantraege."
        )

    except Exception as e:
        db.rollback()
        print(f"Seed-Fehler: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
