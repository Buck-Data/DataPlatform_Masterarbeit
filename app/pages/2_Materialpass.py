"""
Seite 2: Materialpass – Kerndemonstration für T2/O1 (Datensouveränität via ABAC).

Vier Abschnitte zeigen identische Daten mit rollenabhängiger Feldsichtbarkeit.
Die ABAC-Engine (Casbin) erzwingt den Zugriff technisch – kein UI-Trick.
"""
import streamlit as st
import pandas as pd

from app.auth.session import init_session, render_role_switcher, get_current_role, DEMO_USERS
from app.db.session import get_session
from app.db.models import ScrapBatch, Actor
from app.services import batch_service, chemical_service, passport_service
from app.abac.engine import get_abac_engine, RESTRICTED_MARKER
from app.ui_helpers import (
    badge, restricted_placeholder, render_field, render_badge_field,
    chemical_element_label, scrap_class_label, format_datetime, format_date,
    EAF_STATUS_COLORS, VALIDATION_STATUS_COLORS, EVENT_TYPE_LABELS,
    assigned_trader_name,
    TRAMP_ELEMENTS,
)

st.set_page_config(page_title="Materialpass", layout="wide")

init_session()
render_role_switcher()

role = get_current_role()
role_label = DEMO_USERS[role]["role_label"]
engine = get_abac_engine()
tier = None

TIER_LABELS = {
    "standard": "Standard",
    "preferred": "Preferred",
    "strategic": "Strategic",
}

TIER_COLORS = {
    "standard": "#546E7A",
    "preferred": "#1565C0",
    "strategic": "#2E7D32",
}

# ── Charge auswählen ──────────────────────────────────────────────────────────
db = get_session()
try:
    batches = batch_service.get_all_batches(db)
    actors = {a.id: a for a in db.query(Actor).all()}
finally:
    db.close()

if role == "stahlwerk":
    current_actor = next((a for a in actors.values() if a.id == st.session_state.get("actor_id")), None)
    default_tier = (current_actor.relationship_tier if current_actor else None) or "standard"
    with st.sidebar:
        st.markdown("**Beziehungstyp Stahlwerk**")
        tier = st.radio(
            "Relationship-Tier",
            options=["standard", "preferred", "strategic"],
            index=["standard", "preferred", "strategic"].index(default_tier),
            format_func=lambda value: TIER_LABELS[value],
            key="materialpass_steel_tier",
        )

if not batches:
    st.warning("Keine Chargen in der Datenbank. Bitte Seed-Daten laden.")
    st.stop()

batch_options = {b.batch_number: b.id for b in batches}
default_batch = st.session_state.get("selected_batch_id")
default_key = None
if default_batch:
    for bn, bid in batch_options.items():
        if bid == default_batch:
            default_key = bn
            break

selected_number = st.selectbox(
    "Charge auswählen",
    options=list(batch_options.keys()),
    index=list(batch_options.keys()).index(default_key) if default_key else 0,
)
batch_id = batch_options[selected_number]

# ── Daten laden ───────────────────────────────────────────────────────────────
db = get_session()
try:
    batch = batch_service.get_batch_by_id(db, batch_id)
    chem = chemical_service.get_latest_composition(db, batch_id)
    passport = passport_service.get_passport_for_batch(db, batch_id)
    events = passport_service.get_traceability_events(db, batch_id)
    quality = passport_service.get_quality_analysis(db, batch_id)
finally:
    db.close()

if not batch:
    st.error("Charge nicht gefunden.")
    st.stop()

# ABAC-Filterung
batch_dict = batch_service.batch_to_dict(batch)
filtered_batch = (
    engine.filter_batch_fields_tiered(role, tier, batch_dict)
    if role == "stahlwerk"
    else engine.filter_batch_fields(role, batch_dict)
)

chem_dict = {}
filtered_chem = {}
if chem:
    chem_dict = {
        "analysis_method": chem.analysis_method,
        "element_values": chem.element_values,
        "thresholds": chem.thresholds,
        "threshold_exceeded": chem.threshold_exceeded,
        "exceeded_elements": chem.exceeded_elements,
        "measured_at": chem.measured_at,
        "measured_by": chem.measured_by,
    }
    filtered_chem = (
        engine.filter_chemical_fields_tiered(role, tier, chem_dict)
        if role == "stahlwerk"
        else engine.filter_chemical_fields(role, chem_dict)
    )

# ── Seitentitel ───────────────────────────────────────────────────────────────
st.title(f"Materialpass – {batch.batch_number}")

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Schrottklasse", scrap_class_label(batch.scrap_class))
metric_col2.metric("Masse", f"{batch.mass_kg:,.0f} kg")
metric_col3.metric("Volumen", f"{batch.volume_m3:.1f} m³" if batch.volume_m3 is not None else "–")

# ABAC-Hinweis
st.info(
    f"**Datensouveränität (T2/O1):** Aktive Rolle: **{role_label}**. "
    "Die ABAC-Engine (Casbin) filtert Felder technisch – nicht durch UI-Logik. "
    "Gesperrte Felder werden grau dargestellt."
)

if role == "stahlwerk" and tier:
    st.markdown(
        "Aktiver Beziehungstyp: "
        + badge(TIER_LABELS[tier], TIER_COLORS[tier])
        + "  Standard zeigt Basisdaten, Preferred erweitert Herkunft und Volumen, Strategic zeigt zusätzlich Chemie, EAF und Verunreinigungsgrad."
    , unsafe_allow_html=True)

# ── ABSCHNITT A: Chargenbasisdaten ────────────────────────────────────────────
st.subheader("Chargenbasisdaten")

col1, col2 = st.columns(2)

with col1:
    render_field("Chargennummer", filtered_batch.get("batch_number"), role_label)

    # Schrottklasse mit Vollbezeichnung
    sc_val = filtered_batch.get("scrap_class")
    if sc_val == RESTRICTED_MARKER:
        col_l, col_v = st.columns([1, 2])
        col_l.markdown("**Schrottklasse**")
        col_v.markdown(restricted_placeholder(role_label), unsafe_allow_html=True)
    else:
        render_field("Schrottklasse", scrap_class_label(sc_val) if sc_val else None, role_label)

    render_field("Herkunftstyp", filtered_batch.get("origin_type"), role_label)
    render_field("Zugeordneter Händler", assigned_trader_name(actors, batch.owner_id, batch.created_by_trader_id), role_label)
    render_field("Masse", filtered_batch.get("mass_kg"), role_label, "kg")
    render_field("Volumen", filtered_batch.get("volume_m3"), role_label, "m³")
    render_field("Aufbereitungsgrad", filtered_batch.get("preparation_degree"), role_label)
    render_field("Verunreinigungsgrad", filtered_batch.get("contamination_level"), role_label)

with col2:
    render_badge_field("EAF-Kompatibilität", filtered_batch.get("eaf_compatibility"), role_label, EAF_STATUS_COLORS)

st.divider()

# ── ABSCHNITT B: Chemische Zusammensetzung ────────────────────────────────────
st.subheader("Chemische Zusammensetzung (F3)")
st.caption("Grenzwerte für Tramp-Elemente. Überschreitungen sind im EAF-Prozess nicht korrigierbar.")

if not chem:
    st.info("Keine chemische Analyse für diese Charge erfasst.")
else:
    col1, col2 = st.columns(2)
    with col1:
        render_field("Analysemethode", filtered_chem.get("analysis_method"), role_label)
        render_field("Analysezeitpunkt", format_datetime(chem.measured_at), role_label)
        render_field("Analysiert durch", chem.measured_by, role_label)

    with col2:
        # Grenzwert überschritten – für Händler und Stahlwerk sichtbar
        exceeded_val = filtered_chem.get("threshold_exceeded")
        if exceeded_val == RESTRICTED_MARKER:
            col_l, col_v = st.columns([1, 2])
            col_l.markdown("**Grenzwert überschritten**")
            col_v.markdown(restricted_placeholder(role_label), unsafe_allow_html=True)
        else:
            col_l, col_v = st.columns([1, 2])
            col_l.markdown("**Grenzwert überschritten**")
            with col_v:
                if exceeded_val:
                    st.markdown(badge("JA", "#B71C1C"), unsafe_allow_html=True)
                else:
                    st.markdown(badge("Nein", "#2E7D32"), unsafe_allow_html=True)

        exceeded_elements = filtered_chem.get("exceeded_elements")
        if exceeded_elements == RESTRICTED_MARKER:
            col_l, col_v = st.columns([1, 2])
            col_l.markdown("**Überschrittene Elemente**")
            col_v.markdown(restricted_placeholder(role_label), unsafe_allow_html=True)
        elif exceeded_elements:
            render_field("Überschrittene Elemente", ", ".join(exceeded_elements), role_label)
        else:
            render_field("Überschrittene Elemente", "Keine", role_label)

    # Grenzwertwarnung (F3) – prominent und unmissverständlich
    threshold_visible = (
        engine.can_access_field_tiered(role, tier, "chemical", "threshold_exceeded")
        if role == "stahlwerk"
        else engine.can_access_field(role, "chemical", "threshold_exceeded")
    )
    if chem.threshold_exceeded and threshold_visible:
        exceeded_els = chem.exceeded_elements or []
        for el in exceeded_els:
            val = chem.element_values.get(el, 0)
            thr = chem.thresholds.get(el, 0)
            st.warning(
                f"Grenzwertüberschreitung: {chemical_element_label(el)} = {val:.3f} % "
                f"(Grenzwert: {thr:.2f} %). "
                f"Dieser Wert lässt sich im EAF-Schmelzprozess nicht entfernen."
            )

    # Elementwerttabelle – nur für Stahlwerk
    ev_val = filtered_chem.get("element_values")
    thr_val = filtered_chem.get("thresholds")

    st.markdown("**Elementwerte und Grenzwerte**")
    if ev_val == RESTRICTED_MARKER or thr_val == RESTRICTED_MARKER:
        st.markdown(restricted_placeholder(role_label), unsafe_allow_html=True)
    elif ev_val and thr_val:
        rows = []
        for element in TRAMP_ELEMENTS:
            if element not in ev_val:
                continue
            value = ev_val[element]
            threshold = thr_val.get(element)
            if threshold is not None:
                exceeded = value > threshold
                status = badge("Überschritten", "#B71C1C") if exceeded else badge("OK", "#2E7D32")
                rows.append({
                    "Element": chemical_element_label(element),
                    "Messwert (%)": f"{value:.3f}",
                    "Grenzwert (%)": f"{threshold:.2f}",
                    "Status": status,
                })

        # Tabelle als HTML für Badge-Rendering
        html_rows = ""
        for r in rows:
            html_rows += f"<tr><td>{r['Element']}</td><td>{r['Messwert (%)']}</td><td>{r['Grenzwert (%)']}</td><td>{r['Status']}</td></tr>"

        st.markdown(
            f"""<table style="width:100%; border-collapse:collapse;">
            <thead>
              <tr style="background:#f0f2f6;">
                <th style="text-align:left;padding:6px 10px;">Element</th>
                <th style="text-align:left;padding:6px 10px;">Messwert (%)</th>
                <th style="text-align:left;padding:6px 10px;">Grenzwert (%)</th>
                <th style="text-align:left;padding:6px 10px;">Status</th>
              </tr>
            </thead>
            <tbody>{html_rows}</tbody>
            </table>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<span style="color:#aaa;">Keine Daten verfügbar.</span>', unsafe_allow_html=True)

st.divider()

# ── ABSCHNITT C: Rückverfolgbarkeit ──────────────────────────────────────────
st.subheader("Rückverfolgbarkeit")
st.caption("Alle Ereignisse dieser Charge in chronologischer Reihenfolge.")

if not events:
    st.info("Keine Rückverfolgbarkeitsereignisse vorhanden.")
else:
    db = get_session()
    try:
        actors = {a.id: a for a in db.query(Actor).all()}
    finally:
        db.close()

    for i, event in enumerate(events):
        connector = "│" if i < len(events) - 1 else " "
        actor_name = actors[event.actor_id].name if event.actor_id in actors else event.actor_id
        event_label = EVENT_TYPE_LABELS.get(event.event_type, event.event_type)

        with st.container():
            col_icon, col_content = st.columns([0.05, 0.95])
            with col_icon:
                st.markdown(f"**{i+1}.**")
            with col_content:
                st.markdown(
                    f"**{event_label}** – {format_datetime(event.timestamp)}"
                )
                detail_cols = st.columns(3)
                detail_cols[0].markdown(f"Akteur: {actor_name}")
                detail_cols[1].markdown(f"Ort: {event.location or '–'}")
                detail_cols[2].markdown(f"EPCIS: {event.epcis_type or '–'}")
                if event.notes:
                    st.caption(event.notes)

        if i < len(events) - 1:
            st.markdown("&nbsp;&nbsp;&nbsp;↓", unsafe_allow_html=True)

st.divider()

# ── ABSCHNITT D: Validierungsstatus ──────────────────────────────────────────
st.subheader("Validierungsstatus des Materialpasses")

if not passport:
    st.info("Noch kein Materialpass für diese Charge erstellt.")
else:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Version", f"v{passport.version}")
    with col2:
        color = VALIDATION_STATUS_COLORS.get(passport.validation_status, "#546E7A")
        st.markdown("**Validierungsstatus**")
        st.markdown(badge(passport.validation_status.capitalize(), color), unsafe_allow_html=True)
    with col3:
        if passport.certification_ref:
            render_field("Zertifizierungsreferenz", passport.certification_ref, role_label)
        else:
            st.markdown("**Zertifizierungsreferenz**")
            st.markdown('<span style="color:#aaa;font-style:italic;">Keine Referenz</span>', unsafe_allow_html=True)

    col4, col5 = st.columns(2)
    with col4:
        issuer = actors.get(passport.issuer_id) if passport.issuer_id else None
        render_field("Ausgestellt von", issuer.name if issuer else "–", role_label)
    with col5:
        render_field("Letzte Aktualisierung", format_datetime(passport.updated_at), role_label)
