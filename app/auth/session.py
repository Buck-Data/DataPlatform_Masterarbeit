"""
Rollensimulation für den Prototyp-Demo.
Simuliert drei Nutzer mit unterschiedlichen Rollen via st.session_state.
Grundlage für T2/O1: derselbe Materialpass, aber rollenabhängige Feldsichtbarkeit.
"""
import streamlit as st
from app.db.session import get_session
from app.db.models import Actor

DEMO_USERS = {
    "metallverarbeiter": {
        "display_name": "Metallverarbeitung König GmbH",
        "role": "metallverarbeiter",
        "role_label": "Metallverarbeiter",
        "organization": "Metallverarbeitung König GmbH",
    },
    "haendler": {
        "display_name": "Müller Recycling GmbH",
        "role": "haendler",
        "role_label": "Händler / Recycler",
        "organization": "Müller Recycling GmbH",
    },
    "stahlwerk": {
        "display_name": "Südstahl AG",
        "role": "stahlwerk",
        "role_label": "Stahlwerk",
        "organization": "Südstahl AG",
    },
}


def init_session():
    """Initialisiert Session-State mit Standardrolle."""
    if "role" not in st.session_state:
        st.session_state.role = "haendler"
    if "actor_id" not in st.session_state:
        _load_actor_id()


def _load_actor_id():
    """Lädt die Actor-ID aus der Datenbank anhand der aktuellen Rolle."""
    role = st.session_state.get("role", "haendler")
    try:
        db = get_session()
        actor = db.query(Actor).filter(Actor.role == role).first()
        db.close()
        if actor:
            st.session_state.actor_id = actor.id
        else:
            st.session_state.actor_id = None
    except Exception:
        st.session_state.actor_id = None


def get_current_role() -> str:
    return st.session_state.get("role", "haendler")


def get_current_actor_id() -> str:
    return st.session_state.get("actor_id", None)


def get_current_user() -> dict:
    role = get_current_role()
    return DEMO_USERS.get(role, DEMO_USERS["haendler"])


def render_role_switcher():
    """
    Rendert den Rollenumschalter in der Sidebar.
    Kernstück der T2/O1-Demo: Rollenwechsel ändert die Feldsichtbarkeit.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Aktive Rolle**")

    role_options = list(DEMO_USERS.keys())
    role_labels = [DEMO_USERS[r]["role_label"] for r in role_options]
    current_role = get_current_role()
    current_index = role_options.index(current_role) if current_role in role_options else 0

    selected_label = st.sidebar.radio(
        "Rolle wechseln",
        options=role_labels,
        index=current_index,
        label_visibility="collapsed",
    )

    selected_role = role_options[role_labels.index(selected_label)]
    if selected_role != st.session_state.get("role"):
        st.session_state.role = selected_role
        _load_actor_id()
        st.rerun()

    user = get_current_user()
    st.sidebar.markdown(f"**Aktiver Nutzer:** {user['display_name']}")
    st.sidebar.markdown("---")
