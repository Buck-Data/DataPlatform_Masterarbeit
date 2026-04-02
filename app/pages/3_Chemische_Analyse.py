"""
Seite 3: Chemische Analyse (F3)
Erfassung neuer Analysedaten und Anzeige des Analyseverlaufs.
Zugänglich für Händler und Stahlwerk (Metallverarbeiter erhält Hinweis).
"""
import streamlit as st
from datetime import datetime

from app.auth.session import init_session, render_role_switcher, get_current_role, DEMO_USERS
from app.db.session import get_session
from app.db.models import Actor
from app.services import batch_service, chemical_service
from app.abac.engine import get_abac_engine, RESTRICTED_MARKER
from app.ui_helpers import (
    badge,
    chemical_element_label,
    format_datetime,
    scrap_class_label,
    TRAMP_ELEMENTS,
)

st.set_page_config(page_title="Chemische Analyse", layout="wide")

init_session()
render_role_switcher()

role = get_current_role()
role_label = DEMO_USERS[role]["role_label"]
engine = get_abac_engine()

st.title("Chemische Analyse")

# Zugriffshinweis für Metallverarbeiter
if role == "metallverarbeiter":
    st.warning(
        "Für die Rolle 'Metallverarbeiter' sind detaillierte Analysedaten nicht zugänglich. "
        "Die Erfassung neuer Analysen ist Händlern und Stahlwerken vorbehalten."
    )
    st.stop()

# ── Daten laden ───────────────────────────────────────────────────────────────
db = get_session()
try:
    batches = batch_service.get_all_batches(db)
    actors = {a.id: a for a in db.query(Actor).all()}
finally:
    db.close()

if not batches:
    st.warning("Keine Chargen in der Datenbank.")
    st.stop()

batch_options = {b.batch_number: b for b in batches}
selected_number = st.selectbox("Charge auswählen", list(batch_options.keys()))
selected_batch = batch_options[selected_number]

# ── Bisherige Analysen ────────────────────────────────────────────────────────
st.subheader(f"Analysehistorie – {selected_batch.batch_number}")
st.caption(f"Schrottklasse: {scrap_class_label(selected_batch.scrap_class)} | Herkunft: {selected_batch.origin_type}")

db = get_session()
try:
    compositions = chemical_service.get_compositions_for_batch(db, selected_batch.id)
finally:
    db.close()

if not compositions:
    st.info("Noch keine Analysen für diese Charge erfasst.")
else:
    for comp in compositions:
        with st.expander(
            f"Analyse vom {format_datetime(comp.measured_at)} – {comp.analysis_method} – "
            f"{'Grenzwert überschritten' if comp.threshold_exceeded else 'Im Normalbereich'}",
            expanded=(comp == compositions[0]),
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Methode:** {comp.analysis_method}")
                st.markdown(f"**Analysiert durch:** {comp.measured_by}")
                st.markdown(f"**Zeitpunkt:** {format_datetime(comp.measured_at)}")

            with col2:
                if comp.threshold_exceeded:
                    st.markdown(badge("Grenzwert überschritten", "#B71C1C"), unsafe_allow_html=True)
                    for el in (comp.exceeded_elements or []):
                        val = comp.element_values.get(el, 0)
                        thr = comp.thresholds.get(el, 0)
                        st.warning(
                            f"Grenzwertüberschreitung: {chemical_element_label(el)} = {val:.3f} % "
                            f"(Grenzwert: {thr:.2f} %). "
                            f"Dieser Wert lässt sich im EAF-Schmelzprozess nicht entfernen."
                        )
                else:
                    st.markdown(badge("Alle Werte im Normalbereich", "#2E7D32"), unsafe_allow_html=True)

            # Elementtabelle
            if role in ("haendler", "stahlwerk") and engine.can_access_field(role, "chemical", "element_values"):
                rows_html = ""
                for element in TRAMP_ELEMENTS:
                    if element not in comp.element_values:
                        continue
                    val = comp.element_values[element]
                    thr = comp.thresholds.get(element)
                    if thr is not None:
                        exceeded = val > thr
                        status_badge = badge("Überschritten", "#B71C1C") if exceeded else badge("OK", "#2E7D32")
                        rows_html += (
                            f"<tr><td><b>{chemical_element_label(element)}</b></td>"
                            f"<td>{val:.3f} %</td>"
                            f"<td>{thr:.2f} %</td>"
                            f"<td>{status_badge}</td></tr>"
                        )

                st.markdown(
                    f"""<table style="width:100%;border-collapse:collapse;margin-top:8px;">
                    <thead>
                      <tr style="background:#f0f2f6;">
                        <th style="text-align:left;padding:5px 10px;">Element</th>
                        <th style="text-align:left;padding:5px 10px;">Messwert</th>
                        <th style="text-align:left;padding:5px 10px;">Grenzwert</th>
                        <th style="text-align:left;padding:5px 10px;">Status</th>
                      </tr>
                    </thead>
                    <tbody>{rows_html}</tbody></table>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<span style="color:#aaa;font-style:italic;">Elementwerte nicht zugänglich für Rolle: {role_label}</span>',
                    unsafe_allow_html=True,
                )

st.divider()

# ── Neue Analyse erfassen ─────────────────────────────────────────────────────
st.subheader("Neue Analyse erfassen")

with st.form("neue_analyse"):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Analysemetadaten**")
        analysis_method = st.selectbox(
            "Analysemethode",
            ["RFA", "OES", "Laboranalyse", "XRF", "ICP-OES"],
        )
        measured_by = st.text_input("Analysiert durch", value=DEMO_USERS[role]["display_name"])
        measured_at = st.date_input("Analysedatum", value=datetime.today())

    with col2:
        st.markdown("**Grenzwerte (konfigurierbar)**")
        thr_cu = st.number_input("Cu-Grenzwert (%)", value=0.30, step=0.01, format="%.2f")
        thr_sn = st.number_input("Sn-Grenzwert (%)", value=0.10, step=0.01, format="%.2f")
        thr_ni = st.number_input("Ni-Grenzwert (%)", value=0.15, step=0.01, format="%.2f")
        thr_cr = st.number_input("Cr-Grenzwert (%)", value=0.20, step=0.01, format="%.2f")
        thr_mo = st.number_input("Mo-Grenzwert (%)", value=0.05, step=0.01, format="%.3f")

    st.markdown("**Tramp-Elemente (Messwerte)**")
    el_cols = st.columns(3)
    cu_val = el_cols[0].number_input("Kupfer (Cu) (%)", value=0.15, step=0.01, format="%.3f")
    sn_val = el_cols[1].number_input("Zinn (Sn) (%)", value=0.03, step=0.01, format="%.3f")
    ni_val = el_cols[2].number_input("Nickel (Ni) (%)", value=0.08, step=0.01, format="%.3f")
    cr_val = el_cols[0].number_input("Chrom (Cr) (%)", value=0.06, step=0.01, format="%.3f")
    mo_val = el_cols[1].number_input("Molybdän (Mo) (%)", value=0.02, step=0.01, format="%.3f")

    submitted = st.form_submit_button("Analyse speichern")

if submitted:
    element_values = {
        "Cu": cu_val, "Sn": sn_val, "Ni": ni_val,
        "Cr": cr_val, "Mo": mo_val,
    }
    thresholds = {
        "Cu": thr_cu, "Sn": thr_sn, "Ni": thr_ni,
        "Cr": thr_cr, "Mo": thr_mo,
    }
    measured_datetime = datetime.combine(measured_at, datetime.min.time())

    db = get_session()
    try:
        comp = chemical_service.create_chemical_composition(
            db=db,
            batch_id=selected_batch.id,
            element_values=element_values,
            thresholds=thresholds,
            analysis_method=analysis_method,
            measured_by=measured_by,
            measured_at=measured_datetime,
        )

        if comp.threshold_exceeded:
            for el in (comp.exceeded_elements or []):
                val = element_values.get(el, 0)
                thr = thresholds.get(el, 0)
                st.warning(
                    f"Grenzwertüberschreitung: {chemical_element_label(el)} = {val:.3f} % "
                    f"(Grenzwert: {thr:.2f} %). "
                    f"Dieser Wert lässt sich im EAF-Schmelzprozess nicht entfernen."
                )
        else:
            st.success("Analyse gespeichert. Alle Werte im Normalbereich.")

        # EAF-Kompatibilität anzeigen
        eaf = selected_batch.eaf_compatibility
        st.info(f"EAF-Kompatibilität aktualisiert: {eaf}")

    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
    finally:
        db.close()

    st.rerun()
