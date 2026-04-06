"""
Seite 5: Materialpass & Datensouveränität – Rollenvergleich (Kapitel 6.2)

Zeigt denselben Materialpass aus vier Perspektiven simultan:
  Tab 1: Metallverarbeiter (auswählbar)
  Tab 2: Händler (auswählbar)
  Tab 3: Stahlwerk Standard-Tier (Südstahl AG)
  Tab 4: Stahlwerk Strategic-Tier (auswählbar)

Gesperrte Felder werden NICHT ausgeblendet, sondern als
  [GESPERRT — nicht sichtbar für diese Rolle]
dargestellt – damit der ABAC-Mechanismus für den Leser der Thesis erfahrbar wird.

Die Sichtbarkeitslogik kommt ausschließlich aus der Casbin-ABAC-Engine
(abac_policy.csv) und den FieldAccessPolicy-Einträgen in der DB – kein Frontend-Hardcoding.
"""
import streamlit as st
import plotly.graph_objects as go

from app.db.session import get_session
from app.db.models import Actor, CBAMRecord
from app.services import batch_service, chemical_service, passport_service
from app.abac.engine import get_abac_engine, RESTRICTED_MARKER
from app.ui_helpers import (
    badge, chemical_element_label, scrap_class_label, format_datetime, format_date,
    EAF_STATUS_COLORS, VALIDATION_STATUS_COLORS, EVENT_TYPE_LABELS,
    assigned_trader_name,
    TRAMP_ELEMENTS,
)

st.set_page_config(page_title="Materialpass & Datensouveränität", layout="wide")

engine = get_abac_engine()

# ── Farben und Konstanten ─────────────────────────────────────────────────────
GESPERRT_HTML = (
    '<span style="background:#fff0f0; color:#cc0000; padding:2px 8px; '
    'border-radius:3px; font-size:0.85em; border:1px solid #ffcccc;">'
    'GESPERRT — nicht sichtbar für diese Rolle</span>'
)

TIER_LABELS = {
    "standard":  "Standard",
    "preferred": "Preferred",
    "strategic": "Strategic",
}

TIER_COLORS = {
    "standard":  "#546E7A",
    "preferred": "#1565C0",
    "strategic": "#2E7D32",
}

# Alle Felder, die im Materialpass dargestellt werden sollen (geordnet nach Abschnitt)
BATCH_FIELDS_ORDERED = [
    ("batch_number",       "Chargennummer",              "scrapbatch", None),
    ("scrap_class",        "Schrottklasse (EU)",          "scrapbatch", None),
    ("origin_type",        "Herkunftstyp",               "scrapbatch", None),
    ("origin_region",      "Herkunftsregion",            "scrapbatch", None),
    ("collection_period",  "Erfassungszeitraum",         "scrapbatch", None),
    ("mass_kg",            "Masse",                      "scrapbatch", "kg"),
    ("volume_m3",          "Volumen",                    "scrapbatch", "m³"),
    ("preparation_degree", "Aufbereitungsgrad",          "scrapbatch", None),
    ("contamination_level","Verunreinigungsgrad",        "scrapbatch", None),
    ("eaf_compatibility",  "EAF-Kompatibilität",         "scrapbatch", None),
]

CHEM_FIELDS_ORDERED = [
    ("analysis_method",    "Analysemethode",             "chemical",   None),
    ("threshold_exceeded", "Grenzwert überschritten",    "chemical",   None),
    ("exceeded_elements",  "Überschrittene Elemente",    "chemical",   None),
    ("element_values",     "Elementwerte (Tabelle)",     "chemical",   None),
    ("thresholds",         "Grenzwerte (Tabelle)",       "chemical",   None),
]


def _field_row(label: str, raw_value, role: str, tier: str | None,
               resource_type: str, field_key: str, unit: str = None):
    """
    Rendert eine Zeile im Materialpass-Formular.
    Sichtbar = Wert anzeigen; gesperrt = roter GESPERRT-Block.
    Die Entscheidung trifft ausschließlich die ABAC-Engine.
    """
    accessible = engine.can_access_field_tiered(role, tier, resource_type, field_key)
    col_label, col_value = st.columns([1.4, 2.6])
    with col_label:
        st.markdown(f"**{label}**")
    with col_value:
        if not accessible:
            st.markdown(GESPERRT_HTML, unsafe_allow_html=True)
        elif raw_value is None or raw_value == "":
            st.markdown('<span style="color:#aaa;">–</span>', unsafe_allow_html=True)
        else:
            display = f"{raw_value} {unit}" if unit else str(raw_value)
            st.markdown(display)


def _render_eaf_field(value, role: str, tier: str | None):
    accessible = engine.can_access_field_tiered(role, tier, "scrapbatch", "eaf_compatibility")
    col_label, col_value = st.columns([1.4, 2.6])
    with col_label:
        st.markdown("**EAF-Kompatibilität**")
    with col_value:
        if not accessible:
            st.markdown(GESPERRT_HTML, unsafe_allow_html=True)
        elif value:
            color = EAF_STATUS_COLORS.get(value, "#546E7A")
            st.markdown(badge(value, color), unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#aaa;">–</span>', unsafe_allow_html=True)


def _render_threshold_exceeded_field(chem, role: str, tier: str | None):
    accessible = engine.can_access_field_tiered(role, tier, "chemical", "threshold_exceeded")
    col_label, col_value = st.columns([1.4, 2.6])
    with col_label:
        st.markdown("**Grenzwert überschritten**")
    with col_value:
        if not accessible:
            st.markdown(GESPERRT_HTML, unsafe_allow_html=True)
        elif chem and chem.threshold_exceeded:
            st.markdown(badge("JA", "#B71C1C"), unsafe_allow_html=True)
        else:
            st.markdown(badge("Nein", "#2E7D32"), unsafe_allow_html=True)


def _render_chemical_chart(chem, role: str, tier: str | None, chart_key: str = ""):
    """
    Plotly-Balkendiagramm: Elementanteile mit Grenzwertlinien.
    Nur anzeigen, wenn die Rolle Zugriff auf element_values hat.
    """
    if not engine.can_access_field_tiered(role, tier, "chemical", "element_values"):
        col_label, col_value = st.columns([1.4, 2.6])
        with col_label:
            st.markdown("**Elementwerte-Diagramm**")
        with col_value:
            st.markdown(GESPERRT_HTML, unsafe_allow_html=True)
        return

    if not chem or not chem.element_values:
        st.info("Keine Analysedaten vorhanden.")
        return

    # Elemente ohne Fe für bessere Sichtbarkeit der Spurenelemente
    elements = [e for e in TRAMP_ELEMENTS if e in chem.element_values]
    values = [chem.element_values[e] for e in elements]
    thresholds = [chem.thresholds.get(e) for e in elements]

    # Farbe: rot wenn überschritten, grün wenn OK
    colors = []
    for e, v in zip(elements, values):
        thr = chem.thresholds.get(e)
        if thr is not None and v > thr:
            colors.append("#D32F2F")
        else:
            colors.append("#388E3C")

    fig = go.Figure()

    # Balken: Messwerte
    fig.add_trace(go.Bar(
            x=[chemical_element_label(e) for e in elements],
            y=values,
        marker_color=colors,
        name="Messwert (%)",
        text=[f"{v:.3f}%" for v in values],
        textposition="outside",
    ))

    # Grenzwertlinien pro Element (als einzelne Liniensegmente)
    for i, (e, thr) in enumerate(zip(elements, thresholds)):
        if thr is not None:
            fig.add_shape(
                type="line",
                x0=i - 0.4, x1=i + 0.4,
                y0=thr, y1=thr,
                line=dict(color="#B71C1C", width=2, dash="dash"),
            )

    # Grenzwert-Legende (dummy trace)
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode="lines",
        line=dict(color="#B71C1C", width=2, dash="dash"),
        name="Grenzwert",
    ))

    fig.update_layout(
        title="Tramp-Elemente mit Grenzwertlinien",
        xaxis_title="Element",
        yaxis_title="Anteil (%)",
        height=320,
        margin=dict(t=40, b=20),
        showlegend=True,
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#f0f0f0"),
    )

    st.plotly_chart(fig, use_container_width=True, key=f"chem_chart_{chart_key}")


def _render_element_table(chem, role: str, tier: str | None):
    """Tabelle aller Elementwerte mit Grenzwert-Vergleich."""
    if not engine.can_access_field_tiered(role, tier, "chemical", "element_values"):
        col_label, col_value = st.columns([1.4, 2.6])
        with col_label:
            st.markdown("**Elementwerte**")
        with col_value:
            st.markdown(GESPERRT_HTML, unsafe_allow_html=True)
        return

    if not chem or not chem.element_values:
        return

    rows_html = ""
    for element in TRAMP_ELEMENTS:
        if element not in chem.element_values:
            continue
        val = chem.element_values[element]
        thr = chem.thresholds.get(element) if chem.thresholds else None
        if thr is not None:
            exceeded = val > thr
            status_badge = badge("Überschritten", "#B71C1C") if exceeded else badge("OK", "#2E7D32")
            thr_str = f"{thr:.3f} %"
        else:
            status_badge = "–"
            thr_str = "–"
        rows_html += (
            f"<tr><td><b>{chemical_element_label(element)}</b></td>"
            f"<td>{val:.3f} %</td>"
            f"<td>{thr_str}</td>"
            f"<td>{status_badge}</td></tr>"
        )

    st.markdown(
        f"""<table style="width:100%;border-collapse:collapse;font-size:0.88em;">
        <thead>
          <tr style="background:#f0f2f6;">
            <th style="text-align:left;padding:4px 8px;">Element</th>
            <th style="text-align:left;padding:4px 8px;">Messwert</th>
            <th style="text-align:left;padding:4px 8px;">Grenzwert</th>
            <th style="text-align:left;padding:4px 8px;">Status</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody></table>""",
        unsafe_allow_html=True,
    )


def _render_grenzwert_warnung(chem, role: str, tier: str | None):
    """Zeigt F3-Warnung wenn Grenzwert überschritten und Rolle das sehen darf."""
    if not engine.can_access_field_tiered(role, tier, "chemical", "threshold_exceeded"):
        return
    if chem and chem.threshold_exceeded:
        for el in (chem.exceeded_elements or []):
            val = chem.element_values.get(el, 0)
            thr = chem.thresholds.get(el, 0)
            st.warning(
                f"Grenzwertüberschreitung: {chemical_element_label(el)} = {val:.3f} % "
                f"(Grenzwert: {thr:.3f} %). "
                f"Dieser Wert lässt sich im EAF-Schmelzprozess nicht entfernen."
            )


def _render_policy_legend(role: str, tier: str | None):
    """
    Legende: Zeigt für jedes Feld die zugehörige Casbin-Policy-Regel.
    Macht die ABAC-Mechanik für die Thesis transparent.
    """
    with st.expander("Casbin-Policy-Legende — welche Regel erlaubt/sperrt dieses Feld?"):
        st.caption(
            "Die folgende Tabelle zeigt für jedes Feld die Casbin-Policy-Regel, "
            "die den Zugriff erlaubt oder — wenn kein Treffer — sperrt."
        )
        rows = []
        all_fields = BATCH_FIELDS_ORDERED + CHEM_FIELDS_ORDERED
        for field_key, label, resource_type, _ in all_fields:
            accessible = engine.can_access_field_tiered(role, tier, resource_type, field_key)
            rule = engine.get_policy_rule_for_field(role, tier, resource_type, field_key)
            status = "Erlaubt" if accessible else "Gesperrt"
            status_color = "#2E7D32" if accessible else "#B71C1C"
            rows.append((label, field_key, status, status_color, rule or "— kein allow-Eintrag —"))

        html_rows = ""
        for label, field_key, status, color, rule in rows:
            html_rows += (
                f"<tr>"
                f"<td>{label}</td>"
                f"<td><code>{field_key}</code></td>"
                f"<td><span style='color:{color};font-weight:bold;'>{status}</span></td>"
                f"<td style='font-family:monospace;font-size:0.8em;color:#555;'>{rule}</td>"
                f"</tr>"
            )
        st.markdown(
            f"""<table style="width:100%;border-collapse:collapse;font-size:0.83em;">
            <thead>
              <tr style="background:#f0f2f6;">
                <th style="padding:4px 8px;">Feld</th>
                <th style="padding:4px 8px;">Feldname</th>
                <th style="padding:4px 8px;">Zugriff</th>
                <th style="padding:4px 8px;">Policy-Regel (abac_policy.csv)</th>
              </tr>
            </thead>
            <tbody>{html_rows}</tbody></table>""",
            unsafe_allow_html=True,
        )


def _render_passport_tab(
    batch, chem, passport, events, actors: dict,
    role: str, tier: str | None, role_label: str, tab_key: str = "",
):
    """
    Rendert den vollständigen Materialpass für eine Rolle/Tier-Kombination.
    Alle Felder werden gezeigt — gesperrte als GESPERRT-Block.
    """
    # Tier-Badge in der Spaltenüberschrift
    if tier:
        tier_color = TIER_COLORS.get(tier, "#546E7A")
        st.markdown(
            f"Rolle: **{role_label}** &nbsp;"
            + badge(f"Tier: {TIER_LABELS.get(tier, tier)}", tier_color),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"Rolle: **{role_label}**")

    # ── Abschnitt A: Chargenbasisdaten ────────────────────────────────────────
    st.markdown("##### Chargenbasisdaten")

    _field_row("Chargennummer",      batch.batch_number,     role, tier, "scrapbatch", "batch_number")

    # Schrottklasse mit EU-Vollbezeichnung
    sc_accessible = engine.can_access_field_tiered(role, tier, "scrapbatch", "scrap_class")
    col_l, col_v = st.columns([1.4, 2.6])
    with col_l:
        st.markdown("**Schrottklasse (EU)**")
    with col_v:
        if sc_accessible:
            st.markdown(scrap_class_label(batch.scrap_class))
        else:
            st.markdown(GESPERRT_HTML, unsafe_allow_html=True)

    _field_row("Herkunftstyp",       batch.origin_type,      role, tier, "scrapbatch", "origin_type")
    _field_row("Zugeordneter Händler", assigned_trader_name(actors, batch.owner_id, batch.created_by_trader_id), role, tier, "scrapbatch", "batch_number")
    _field_row("Herkunftsregion",    batch.origin_region,    role, tier, "scrapbatch", "origin_region")
    _field_row("Erfassungszeitraum", batch.collection_period,role, tier, "scrapbatch", "collection_period")
    _field_row("Masse",              batch.mass_kg,          role, tier, "scrapbatch", "mass_kg",    "kg")
    _field_row("Volumen",            batch.volume_m3,        role, tier, "scrapbatch", "volume_m3",  "m³")
    _field_row("Aufbereitungsgrad",  batch.preparation_degree, role, tier, "scrapbatch", "preparation_degree")
    _field_row("Verunreinigungsgrad",batch.contamination_level, role, tier, "scrapbatch", "contamination_level")
    _render_eaf_field(batch.eaf_compatibility, role, tier)

    st.divider()

    # ── Abschnitt B: Chemische Zusammensetzung ────────────────────────────────
    st.markdown("##### Chemische Zusammensetzung (F3)")
    st.caption("Tramp-Elemente reichern sich im EAF-Prozess an – Überschreitungen sind nicht korrigierbar.")

    if not chem:
        st.info("Keine Analyse vorhanden.")
    else:
        _field_row("Analysemethode",    chem.analysis_method,  role, tier, "chemical", "analysis_method")
        _render_threshold_exceeded_field(chem, role, tier)

        # Warnung (F3)
        _render_grenzwert_warnung(chem, role, tier)

        # Überschrittene Elemente
        exc_accessible = engine.can_access_field_tiered(role, tier, "chemical", "exceeded_elements")
        col_l, col_v = st.columns([1.4, 2.6])
        with col_l:
            st.markdown("**Überschrittene Elemente**")
        with col_v:
            if not exc_accessible:
                st.markdown(GESPERRT_HTML, unsafe_allow_html=True)
            elif chem.exceeded_elements:
                st.markdown(", ".join(chem.exceeded_elements))
            else:
                st.markdown("Keine")

        # Elementdiagramm
        _render_chemical_chart(chem, role, tier, chart_key=tab_key)

        # Elementtabelle
        _render_element_table(chem, role, tier)

    st.divider()

    # ── Abschnitt C: Rückverfolgbarkeit ───────────────────────────────────────
    st.markdown("##### Rückverfolgbarkeit")
    st.caption("Beispielhafte Ereigniskette der Charge über 2 bis 4 Stationen.")

    if not events:
        st.info("Keine Rückverfolgbarkeitsereignisse vorhanden.")
    else:
        for i, event in enumerate(events):
            actor_name = actors[event.actor_id].name if event.actor_id in actors else event.actor_id
            event_label = EVENT_TYPE_LABELS.get(event.event_type, event.event_type)
            with st.container():
                col_icon, col_content = st.columns([0.08, 0.92])
                with col_icon:
                    st.markdown(f"**{i + 1}.**")
                with col_content:
                    st.markdown(f"**{event_label}** – {format_datetime(event.timestamp)}")
                    detail_cols = st.columns(3)
                    detail_cols[0].markdown(f"Akteur: {actor_name}")
                    detail_cols[1].markdown(f"Ort: {event.location or '–'}")
                    detail_cols[2].markdown(f"EPCIS: {event.epcis_type or '–'}")
                    if event.notes:
                        st.caption(event.notes)
            if i < len(events) - 1:
                st.markdown("&nbsp;&nbsp;&nbsp;↓", unsafe_allow_html=True)

    st.divider()

    # ── Abschnitt D: Validierungsstatus ──────────────────────────────────────
    st.markdown("##### Materialpass-Validierungsstatus (F2)")

    if not passport:
        st.info("Noch kein Materialpass angelegt.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Version", f"v{passport.version}")
        with col2:
            color = VALIDATION_STATUS_COLORS.get(passport.validation_status, "#546E7A")
            st.markdown("**Status**")
            st.markdown(badge(passport.validation_status.capitalize(), color), unsafe_allow_html=True)
        with col3:
            st.markdown("**Zertifizierungsreferenz**")
            st.markdown(passport.certification_ref or "–")

    st.divider()

    # ── Policy-Legende ────────────────────────────────────────────────────────
    _render_policy_legend(role, tier)


# ══════════════════════════════════════════════════════════════════════════════
# HAUPTLAYOUT
# ══════════════════════════════════════════════════════════════════════════════

st.title("Materialpass & Datensouveränität")
st.markdown("**Demo-Szenario Kapitel 6.2** — Vier Perspektiven auf denselben Materialpass.")

st.info(
    "**ABAC-Mechanismus (T2/O1):** Die Feldfilterung erfolgt ausschließlich durch die "
    "Casbin-Engine (abac_policy.csv), nicht durch UI-Logik. Gesperrte Felder werden "
    "als **GESPERRT**-Block dargestellt, sodass der Mechanismus sichtbar und spürbar ist."
)

# ── Charge auswählen ──────────────────────────────────────────────────────────
db = get_session()
try:
    batches = batch_service.get_all_batches(db)
    actors = {a.id: a for a in db.query(Actor).all()}
finally:
    db.close()

metal_processors = sorted(
    [a for a in actors.values() if a.role == "metallverarbeiter"],
    key=lambda a: a.name,
)
traders = sorted(
    [a for a in actors.values() if a.role == "haendler"],
    key=lambda a: a.name,
)
steel_mills = sorted(
    [a for a in actors.values() if a.role == "stahlwerk"],
    key=lambda a: a.name,
)

if not batches:
    st.warning("Keine Chargen in der Datenbank. Bitte Seed-Daten prüfen.")
    st.stop()

batch_options = {b.batch_number: b.id for b in batches}
# Vorauswahl aus Session-State (von Seite 1)
default_batch = st.session_state.get("selected_batch_id")
default_key = None
if default_batch:
    for bn, bid in batch_options.items():
        if bid == default_batch:
            default_key = bn
            break

selected_number = st.selectbox(
    "Charge für Vergleich auswählen",
    options=list(batch_options.keys()),
    index=list(batch_options.keys()).index(default_key) if default_key else 0,
)
batch_id = batch_options[selected_number]

# ── Daten für gewählte Charge laden ──────────────────────────────────────────
db = get_session()
try:
    batch = batch_service.get_batch_by_id(db, batch_id)
    chem = chemical_service.get_latest_composition(db, batch_id)
    passport = passport_service.get_passport_for_batch(db, batch_id)
    events = passport_service.get_traceability_events(db, batch_id)
finally:
    db.close()

if not batch:
    st.error("Charge nicht gefunden.")
    st.stop()

# Kurzzusammenfassung der Charge
col_info1, col_info2, col_info3 = st.columns(3)
col_info1.metric("Schrottklasse", scrap_class_label(batch.scrap_class))
col_info2.metric("Masse", f"{batch.mass_kg:,.0f} kg")
if chem:
    eaf = batch.eaf_compatibility or "–"
    col_info3.metric("EAF-Kompatibilität", eaf)
else:
    col_info3.metric("EAF-Kompatibilität", "–")

if chem and chem.threshold_exceeded:
    st.error(
        f"Grenzwertüberschreitung in Charge {batch.batch_number}: "
        + ", ".join(chem.exceeded_elements or [])
        + " — sichtbar nur für berechtigte Rollen."
    )

st.divider()

# ── Tier-Auswahl für die Stahlwerk-Tabs ──────────────────────────────────────
# Nutzer kann Vergleichspartner und Beziehungstyp live umschalten.
with st.sidebar:
    st.markdown("**Vergleichspartner**")

    selected_metal_processor = st.selectbox(
        "Metallverarbeiter (Tab 1)",
        options=metal_processors,
        index=next(
            (i for i, actor in enumerate(metal_processors) if actor.name == "Metallverarbeitung König GmbH"),
            0,
        ),
        format_func=lambda actor: actor.name,
        key="comparison_metal_processor",
    )
    selected_trader = st.selectbox(
        "Händler (Tab 2)",
        options=traders,
        index=next(
            (i for i, actor in enumerate(traders) if actor.name == "Müller Recycling GmbH"),
            0,
        ),
        format_func=lambda actor: actor.name,
        key="comparison_trader",
    )
    selected_standard_mill = st.selectbox(
        "Stahlwerk (Tab 3)",
        options=steel_mills,
        index=next(
            (i for i, actor in enumerate(steel_mills) if actor.name == "Südstahl AG"),
            0,
        ),
        format_func=lambda actor: actor.name,
        key="comparison_standard_mill",
    )
    selected_strategic_mill = st.selectbox(
        "Stahlwerk (Tab 4)",
        options=steel_mills,
        index=next(
            (i for i, actor in enumerate(steel_mills) if actor.name == "Oststahl AG"),
            0,
        ),
        format_func=lambda actor: actor.name,
        key="comparison_strategic_mill",
    )

    st.markdown("---")
    st.markdown("**Beziehungstyp Vergleich**")
    tier_suedstahl = st.radio(
        f"{selected_standard_mill.name} (Tab 3)",
        options=["standard", "preferred", "strategic"],
        index=["standard", "preferred", "strategic"].index(
            selected_standard_mill.relationship_tier or "standard"
        ),
        format_func=lambda x: TIER_LABELS[x],
        key="tier_suedstahl",
    )
    tier_thyssen = st.radio(
        f"{selected_strategic_mill.name} (Tab 4)",
        options=["standard", "preferred", "strategic"],
        index=["standard", "preferred", "strategic"].index(
            selected_strategic_mill.relationship_tier or "strategic"
        ),
        format_func=lambda x: TIER_LABELS[x],
        key="tier_thyssen",
    )

# ── Vier-Tab-Layout ───────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    f"Metallverarbeiter ({selected_metal_processor.name})",
    f"Händler ({selected_trader.name})",
    f"Stahlwerk Standard — {selected_standard_mill.name}",
    f"Stahlwerk Strategic — {selected_strategic_mill.name}",
])

with tab1:
    _render_passport_tab(
        batch=batch, chem=chem, passport=passport, events=events, actors=actors,
        role="metallverarbeiter", tier=None,
        role_label=f"Metallverarbeiter ({selected_metal_processor.name})",
        tab_key="mv",
    )

with tab2:
    _render_passport_tab(
        batch=batch, chem=chem, passport=passport, events=events, actors=actors,
        role="haendler", tier=None,
        role_label=f"Händler ({selected_trader.name})",
        tab_key="h",
    )

with tab3:
    st.caption(
        f"Beziehungstyp wählbar in der Sidebar — aktuell: **{TIER_LABELS[tier_suedstahl]}**. "
        "Standard sieht nur Basisdaten, Preferred erweitert Herkunft und Volumen, Strategic zeigt zusätzlich Chemie, EAF und Verunreinigungsgrad."
    )
    _render_passport_tab(
        batch=batch, chem=chem, passport=passport, events=events, actors=actors,
        role="stahlwerk", tier=tier_suedstahl,
        role_label=f"Stahlwerk – {selected_standard_mill.name}",
        tab_key=f"sw_sued_{tier_suedstahl}",
    )

with tab4:
    st.caption(
        f"Beziehungstyp wählbar in der Sidebar — aktuell: **{TIER_LABELS[tier_thyssen]}**. "
        "Strategic erweitert Preferred um Verunreinigungsgrad, EAF-Kompatibilität und chemische Zusammensetzung."
    )
    _render_passport_tab(
        batch=batch, chem=chem, passport=passport, events=events, actors=actors,
        role="stahlwerk", tier=tier_thyssen,
        role_label=f"Stahlwerk – {selected_strategic_mill.name}",
        tab_key=f"sw_thyssen_{tier_thyssen}",
    )
