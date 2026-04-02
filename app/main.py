import streamlit as st

from app.auth.session import init_session, render_role_switcher, get_current_role, DEMO_USERS
from app.ui_helpers import badge, VALIDATION_STATUS_COLORS, EAF_STATUS_COLORS

st.set_page_config(
    page_title="Scrap Data Platform",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
render_role_switcher()

role = get_current_role()
role_label = DEMO_USERS[role]["role_label"]

# ── Kopfbereich ───────────────────────────────────────────────────────────────
st.title("Datenplattform Metallschrottkreislauf")
st.markdown("**Prototyp | Masterarbeit | Marcel Buck**")
st.markdown(
    "Diese Anwendung demonstriert die vier ausgewählte Anforderungen aus dem Kapitel 6 "
    "der Masterarbeit, das technisch mit dem Kapitel 5 umgesetzt wurde."
)

st.divider()

# ── Anforderungsübersicht ─────────────────────────────────────────────────────
st.subheader("Implementierte Anforderungen")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**F3: Chemische Zusammensetzung**")
    st.markdown(
        "Erfassung chemischer Analysedaten pro Charge, konfigurierbare Grenzwerte für "
        "Tramp-Elemente (Cu, Sn, Ni, Cr). Automatisches Warnsignal bei Überschreitung. "
    )
    st.markdown("Seite: **Chemische Analyse**")

    st.divider()

    st.markdown("**F2: Digitaler Materialpass**")
    st.markdown(
        "Strukturiertes Dokument pro Charge mit Analysedaten, Rückverfolgbarkeit und "
        "Validierungsstatus."
    )
    st.markdown("Seite: **Materialpass**")

with col2:
    st.markdown("**F8: Operative Logistik- und Abholkoordination**")
    st.markdown(
        "Abholaufträge anlegen und verwalten, Containerstatus einsehen, Lieferstatus nachverfolgen.  "
    )
    st.markdown("Seite: **Logistikkoordination**")

    st.divider()

    st.markdown("**T2 + O1: Datensouveränität via ABAC**")
    st.markdown(
        "2 Nutzer mit unterschiedlichen Rollen sehen denselben Materialpass mit "
        "unterschiedlichen Feldern. Die ABAC-Engine erzwingt dies technisch. "
    )
    st.markdown("Seite: **Materialpass Vergleich**")

st.divider()

# ── Aktuelle Rolle ────────────────────────────────────────────────────────────
st.subheader("Demo-Konfiguration")

col1, col2, col3 = st.columns(3)

with col1:
    color = "#1565C0" if role == "metallverarbeiter" else "#546E7A"
    st.markdown(
        f'Metallverarbeiter {badge("aktiv", color) if role == "metallverarbeiter" else ""}',
        unsafe_allow_html=True,
    )
    st.caption("Metallverarbeitung König GmbH")
    st.caption("Sieht: Containerstatus, Lieferantendetails, Preis/Tonne")
    st.caption("Nicht sichtbar: Chemische Detailanalyse, EAF-Kompatibilität...")

with col2:
    color = "#1565C0" if role == "haendler" else "#546E7A"
    st.markdown(
        f'Händler / Recycler {badge("aktiv", color) if role == "haendler" else ""}',
        unsafe_allow_html=True,
    )
    st.caption("Müller Recycling GmbH")
    st.caption("Sieht: Basisinfos, Bezugsquelle, Preis, Grenzwertstatus")
    st.caption("Nicht sichtbar: Elementwerte, EAF-Kompatibilität")

with col3:
    color = "#1565C0" if role == "stahlwerk" else "#546E7A"
    st.markdown(
        f'Stahlwerk {badge("aktiv", color) if role == "stahlwerk" else ""}',
        unsafe_allow_html=True,
    )
    st.caption("Südstahl AG")
    st.caption("Sieht: Chemische Details, EAF-Kompatibilität, Lieferstatus")
    st.caption("Nicht sichtbar: Bezugsquelle, Preis/Tonne")

st.divider()
