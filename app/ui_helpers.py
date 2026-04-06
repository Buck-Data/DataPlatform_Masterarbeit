import streamlit as st

RESTRICTED_MARKER = "__RESTRICTED__"

DELIVERY_STATUS_COLORS = {
    "geplant": "#1565C0",
    "abgeholt": "#6A1B9A",
    "in_transit": "#E65100",
    "geliefert": "#2E7D32",
    "verzoegert": "#B71C1C",
}

CONTAINER_STATUS_COLORS = {
    "leer": "#546E7A",
    "teilbefuellt": "#F57F17",
    "voll": "#1565C0",
    "abholbereit": "#2E7D32",
}

VALIDATION_STATUS_COLORS = {
    "entwurf": "#546E7A",
    "validiert": "#1565C0",
    "zertifiziert": "#2E7D32",
}

EAF_STATUS_COLORS = {
    "geeignet": "#2E7D32",
    "bedingt geeignet": "#E65100",
    "nicht geeignet": "#B71C1C",
}

EU_SCRAP_CLASSES = {
    "E1": "E1 – Leichter Stahlaltschrott",
    "E2": "E2 – Schwerer Neuschrott",
    "E3": "E3 – Schwerer Stahlaltschrott",
    "E6": "E6 – Leichter Neuschrott",
    "E8": "E8 – Neuschrottspäne",
    "E40": "E40 – Shredderschrott",
}

CHEMICAL_ELEMENT_LABELS = {
    "Cu": "Kupfer (Cu)",
    "Sn": "Zinn (Sn)",
    "Ni": "Nickel (Ni)",
    "Cr": "Chrom (Cr)",
    "Mo": "Molybdän (Mo)",
    "S": "Schwefel (S)",
    "P": "Phosphor (P)",
    "Fe": "Eisen (Fe)",
}

TRAMP_ELEMENTS = ["Cu", "Sn", "Ni", "Cr", "Mo"]


def badge(label: str, color: str) -> str:
    return (
        f'<span style="background-color:{color}; color:white; padding:3px 10px; '
        f'border-radius:4px; font-size:0.82em; font-weight:600;">{label}</span>'
    )


def restricted_placeholder(role: str) -> str:
    return (
        f'<span style="color:#aaa; font-style:italic; font-size:0.9em;">'
        f'Nicht zugänglich für Rolle: {role}</span>'
    )


def render_field(label: str, value, role: str, unit: str = ""):
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(f"**{label}**")
    with col2:
        if value == RESTRICTED_MARKER:
            st.markdown(restricted_placeholder(role), unsafe_allow_html=True)
        elif value is None or value == "":
            st.markdown('<span style="color:#aaa;">–</span>', unsafe_allow_html=True)
        else:
            display = f"{value} {unit}".strip() if unit else str(value)
            st.markdown(display)


def render_badge_field(label: str, value, role: str, color_map: dict):
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(f"**{label}**")
    with col2:
        if value == RESTRICTED_MARKER:
            st.markdown(restricted_placeholder(role), unsafe_allow_html=True)
        elif value:
            color = color_map.get(value, "#546E7A")
            st.markdown(badge(value, color), unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#aaa;">–</span>', unsafe_allow_html=True)


def scrap_class_label(code: str) -> str:
    return EU_SCRAP_CLASSES.get(code, code)


def scrap_origin_category(origin_type: str | None) -> str:
    if not origin_type:
        return "–"
    mapping = {
        "Industriebetrieb": "Neuschrott",
        "Wertstoffhof": "Altschrott",
        "Gebäudeabriss": "Altschrott",
        "Neuschrott": "Neuschrott",
        "Altschrott": "Altschrott",
        "Eigenschrott": "Eigenschrott",
    }
    return mapping.get(origin_type, "–")


def assigned_trader_name(
    actors_by_id: dict,
    owner_id: str | None = None,
    created_by_trader_id: str | None = None,
) -> str:
    trader_id = created_by_trader_id
    if not trader_id and owner_id:
        owner = actors_by_id.get(owner_id)
        owner_role = getattr(owner, "role", None) if owner is not None else None
        if owner_role is None and isinstance(owner, dict):
            owner_role = owner.get("role")
        if owner_role == "haendler":
            trader_id = owner_id

    if not trader_id:
        return "–"

    trader = actors_by_id.get(trader_id)
    if trader is None:
        return "–"

    trader_name = getattr(trader, "name", None)
    if trader_name is None and isinstance(trader, dict):
        trader_name = trader.get("name")
    return trader_name or "–"


def chemical_element_label(code: str) -> str:
    return CHEMICAL_ELEMENT_LABELS.get(code, code)


def format_datetime(dt) -> str:
    if dt is None:
        return "–"
    if hasattr(dt, "strftime"):
        return dt.strftime("%d.%m.%Y %H:%M")
    return str(dt)


def format_date(d) -> str:
    if d is None:
        return "–"
    if hasattr(d, "strftime"):
        return d.strftime("%d.%m.%Y")
    return str(d)


EVENT_TYPE_LABELS = {
    "erfassung": "Erfassung",
    "eigentuemerwechsel": "Eigentuemerwechsel",
    "aufbereitung": "Aufbereitung",
    "qualitaetspruefung": "Qualitaetspruefung",
    "anlieferung": "Anlieferung",
    "einschmelzung": "Einschmelzung",
}
