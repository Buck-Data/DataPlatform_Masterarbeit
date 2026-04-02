"""
Seite 4: Logistik
Kombinierte End-to-End-Sicht für Container, Abholanfragen und Lieferkoordination.
"""
import streamlit as st
import requests
from datetime import date, timedelta

from app.auth.session import (
    DEMO_USERS,
    get_current_actor_id,
    get_current_role,
    init_session,
    render_role_switcher,
)
from app.db.session import get_session
from app.db.models import Actor
from app.services import batch_service, logistics_service
from app.abac.engine import get_abac_engine
from app.ui_helpers import (
    badge,
    format_date,
    format_datetime,
    scrap_class_label,
    DELIVERY_STATUS_COLORS,
    CONTAINER_STATUS_COLORS,
)

API_BASE = "http://api:8000"

st.set_page_config(page_title="Logistik", layout="wide")

init_session()
render_role_switcher()

role = get_current_role()
actor_id = get_current_actor_id()
role_label = DEMO_USERS[role]["role_label"]
engine = get_abac_engine()

st.title("Logistik")


CONTAINER_ICONS = {
    "leer": "⬜",
    "teilbefuellt": "🟨",
    "voll": "🟧",
    "abholbereit": "🟩",
    "angefragt": "🔔",
    "verfuegbar": "✅",
}

REQUEST_ICONS = {
    "ausstehend": "🔵",
    "angenommen": "🟢",
    "abgelehnt": "🔴",
    "abgeschlossen": "⚫",
    "abgeholt": "✅",
}


def fetch_actors() -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/actors", timeout=5)
        return r.json() if r.ok else []
    except Exception:
        return []


def fetch_containers(owner_id: str | None = None) -> list[dict]:
    try:
        params = {"owner_id": owner_id} if owner_id else {}
        r = requests.get(f"{API_BASE}/containers", params=params, timeout=5)
        return r.json() if r.ok else []
    except Exception:
        return []


def fetch_pickup_requests(container_id: str) -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/containers/{container_id}/pickup-requests", timeout=5)
        return r.json() if r.ok else []
    except Exception:
        return []


def fetch_history(actor_id_filter: str | None = None) -> list[dict]:
    try:
        params = {"actor_id": actor_id_filter} if actor_id_filter else {}
        r = requests.get(f"{API_BASE}/pickup-history", params=params, timeout=5)
        return r.json() if r.ok else []
    except Exception:
        return []


def check_abac(view: str) -> bool:
    try:
        r = requests.get(f"{API_BASE}/abac/fields/{role}/container_logistics", timeout=5)
        if r.ok:
            data = r.json()
            return view in data.get("accessible_fields", [])
    except Exception:
        pass
    return False


def actor_name(actors: list[dict], lookup_id: str) -> str:
    actor = next((a for a in actors if a["id"] == lookup_id), None)
    return actor["name"] if actor else lookup_id[:8] + "..."


def is_order_for_current_steel_mill(order, actor: dict | None) -> bool:
    if actor is None:
        return False
    actor_name_value = actor.get("name", "")
    organization = actor.get("organization", "")
    delivery_location = order.delivery_location or ""
    return any(
        candidate and candidate in delivery_location
        for candidate in (actor_name_value, organization)
    )


def render_delivery_orders(display_orders, batches, actors_by_id, show_full: bool):
    if not display_orders:
        st.info("Keine Aufträge in dieser Ansicht.")
        return

    tab_all, tab_geplant, tab_unterwegs = st.tabs(["Alle", "Geplant", "In Transit / Verzögert"])

    def _render_orders(orders, scope: str):
        for order in orders:
            batch = batches.get(order.batch_id)
            with st.container():
                if show_full:
                    col1, col2, col3, col4, col5 = st.columns([1.5, 2, 2, 1.5, 1.5])
                    col1.markdown(f"**{batch.batch_number if batch else '–'}**")
                    col1.caption(scrap_class_label(batch.scrap_class) if batch else "")

                    col2.markdown(f"Abholung: {format_date(order.pickup_date)}")
                    col2.caption(f"Von: {order.pickup_location}")

                    col3.markdown(f"Ziel: {order.delivery_location}")
                    col3.caption(f"Carrier: {order.carrier or '–'}")

                    col4.markdown(
                        badge(order.container_status, CONTAINER_STATUS_COLORS.get(order.container_status, "#546E7A")),
                        unsafe_allow_html=True,
                    )
                    col4.caption("Containerstatus")

                    col5.markdown(
                        badge(order.delivery_status, DELIVERY_STATUS_COLORS.get(order.delivery_status, "#546E7A")),
                        unsafe_allow_html=True,
                    )
                    col5.caption("Lieferstatus")
                else:
                    col1, col2, col3, col4 = st.columns([1.5, 1.7, 2, 1.4])
                    col1.markdown(f"**{batch.batch_number if batch else '–'}**")
                    col1.caption(scrap_class_label(batch.scrap_class) if batch else "")

                    if engine.can_access_field(role, "logistics", "delivery_date"):
                        delivery_date = order.delivery_date or order.pickup_date
                        col2.markdown(f"Geplante Lieferung: **{format_date(delivery_date)}**")
                    else:
                        col2.markdown('<span style="color:#aaa;font-style:italic;">Lieferdatum: nicht zugänglich</span>', unsafe_allow_html=True)

                    trader_label = actors_by_id.get(order.requesting_actor_id, {}).get("name", "–")
                    col3.markdown(f"Lieferant: **{trader_label}**")
                    carrier_label = order.carrier or "Spedition offen"
                    col3.caption(f"Transport: {carrier_label}")

                    if engine.can_access_field(role, "logistics", "delivery_status"):
                        col4.markdown(
                            badge(order.delivery_status, DELIVERY_STATUS_COLORS.get(order.delivery_status, "#546E7A")),
                            unsafe_allow_html=True,
                        )
                        col4.caption("Lieferstatus")
                    else:
                        col4.markdown('<span style="color:#aaa;font-style:italic;">Lieferstatus: nicht zugänglich</span>', unsafe_allow_html=True)

                st.caption(f"Stand: {format_datetime(order.updated_at)}")

                if role == "stahlwerk" and order.delivery_status != "geliefert":
                    if st.button("Als geliefert bestätigen", key=f"steel_confirm_{scope}_{order.id}", type="primary"):
                        db = get_session()
                        try:
                            updated = logistics_service.update_order_status(
                                db,
                                order.id,
                                delivery_status="geliefert",
                                container_status=order.container_status,
                            )
                            if updated:
                                st.success("Lieferung als geliefert bestätigt.")
                                st.rerun()
                            st.error("Auftrag nicht gefunden.")
                        finally:
                            db.close()
                st.divider()

    with tab_all:
        _render_orders(display_orders, "all")
    with tab_geplant:
        _render_orders([o for o in display_orders if o.delivery_status == "geplant"], "planned")
    with tab_unterwegs:
        _render_orders([o for o in display_orders if o.delivery_status in ("in_transit", "verzoegert")], "transit")


actors = fetch_actors()
actors_by_id = {a["id"]: a for a in actors}
actors_by_role: dict[str, list[dict]] = {}
for actor in actors:
    actors_by_role.setdefault(actor["role"], []).append(actor)

current_actor = actors_by_id.get(actor_id)
if current_actor is None and role in actors_by_role and actors_by_role[role]:
    current_actor = actors_by_role[role][0]
    actor_id = current_actor["id"]

if current_actor is None:
    st.error("Kein passender Akteur für die aktuelle Rolle gefunden.")
    st.stop()

db = get_session()
try:
    all_orders = logistics_service.get_all_logistics_orders(db)
    batches = {b.id: b for b in batch_service.get_all_batches(db)}
finally:
    db.close()

if role == "metallverarbeiter":
    st.info("Sicht auf eigene Container, Abholanfragen und Abholhistorie.")
elif role == "haendler":
    st.info("End-to-End-Sicht für verfügbare Container, eigene Abholanfragen, eingehende Anfragen und Lieferkoordination.")
else:
    st.info("Stahlwerk-Sicht auf erwartete Händlerlieferungen, ETA und Lieferbestätigung.")

show_full_logistics = role != "stahlwerk"
display_orders = [o for o in all_orders if o.requesting_actor_id == actor_id]

if role == "stahlwerk":
    display_orders = sorted(
        [o for o in all_orders if is_order_for_current_steel_mill(o, current_actor)],
        key=lambda o: (o.delivery_date or o.pickup_date or date.max, o.created_at),
    )
    st.subheader("Transporte & Lieferungen")
    render_delivery_orders(display_orders, batches, actors_by_id, show_full=False)
    st.stop()

if role == "metallverarbeiter":
    container_context = st.container()
else:
    tab_container, tab_delivery = st.tabs(["Container & Abholung", "Transporte & Lieferungen"])
    container_context = tab_container

with container_context:
    if role == "metallverarbeiter":
        st.subheader(f"Meine Container – {current_actor['name']}")
        containers = fetch_containers(owner_id=actor_id)
        can_initiate = check_abac("initiate_request")

        if not containers:
            st.info("Noch keine Container vorhanden.")
        else:
            haendler_actors = actors_by_role.get("haendler", [])
            for c in containers:
                icon = CONTAINER_ICONS.get(c["status"], "❓")
                fill = c["fill_level"]
                est_vol = c.get("estimated_volume_m3", 0.0)
                reqs = fetch_pickup_requests(c["id"])
                pending = [r for r in reqs if r["status"] == "ausstehend"]
                accepted = [r for r in reqs if r["status"] == "angenommen"]

                with st.expander(
                    f"{icon} **{c['container_number']}** — {c['status'].upper()} | "
                    f"Füllstand: {fill}% ({est_vol:.1f} m³ von {c['capacity_m3']:.0f} m³)",
                    expanded=(c["status"] in ("abholbereit", "angefragt")),
                ):
                    col1, col2 = st.columns(2)
                    col1.markdown(f"**Standort:** {c['location']}")
                    col1.markdown(f"**Schrottklasse:** {c['scrap_class'] or '–'}")
                    if c["notes"]:
                        col1.caption(c["notes"])
                    col2.markdown(f"**Füllstand:** {fill} %")
                    col2.progress(fill / 100)
                    col2.caption(f"ca. {est_vol:.1f} m³ von {c['capacity_m3']:.0f} m³")

                    st.markdown("---")

                    if can_initiate and c["status"] != "angefragt" and not accepted and haendler_actors:
                        with st.expander("Händler anfragen"):
                            with st.form(f"request_trader_{c['id']}"):
                                selected_trader = st.selectbox(
                                    "Händler auswählen",
                                    options=haendler_actors,
                                    format_func=lambda a: a["name"],
                                )
                                requested_date = st.date_input(
                                    "Gewünschtes Abholdatum",
                                    value=date.today() + timedelta(days=5),
                                    min_value=date.today(),
                                    key=f"mv_date_{c['id']}",
                                )
                                req_notes = st.text_area("Nachricht an Händler (optional)", key=f"mv_notes_{c['id']}")
                                submitted = st.form_submit_button("Anfrage senden", type="primary")
                            if submitted:
                                payload = {
                                    "haendler_id": selected_trader["id"],
                                    "requested_pickup_date": requested_date.isoformat(),
                                    "notes": req_notes or None,
                                }
                                resp = requests.post(f"{API_BASE}/containers/{c['id']}/request-trader", json=payload, timeout=5)
                                if resp.ok:
                                    st.success(f"Anfrage an {selected_trader['name']} gesendet.")
                                    st.rerun()
                                st.error(f"Fehler: {resp.text}")

                    st.markdown(f"**Abholanträge:** {len(reqs)} gesamt, {len(pending)} ausstehend, {len(accepted)} angenommen")
                    if not reqs:
                        st.caption("Noch keine Abholanträge für diesen Container.")
                    for req in reqs:
                        req_icon = REQUEST_ICONS.get(req["status"], "❓")
                        requester = actor_name(actors, req["requesting_actor_id"])
                        price_str = f"{req['offered_price_per_ton']:.2f} EUR/t" if req["offered_price_per_ton"] is not None else "kein Preisangebot"
                        initiator_label = "MV-Anfrage" if req["initiator"] == "metallverarbeiter" else "Händler-Antrag"
                        rcol1, rcol2, rcol3 = st.columns([3, 2, 2])
                        rcol1.markdown(
                            f"{req_icon} **{requester}** ({initiator_label})  \n"
                            f"Wunschtermin: {req['requested_pickup_date']}  \n"
                            f"Preis: {price_str}"
                        )
                        if req["notes"]:
                            rcol1.caption(req["notes"])
                        rcol2.markdown(f"Status: **{req['status']}**")

                        if req["status"] == "ausstehend" and req["initiator"] == "haendler":
                            if rcol3.button("Annehmen", key=f"accept_{req['id']}", type="primary"):
                                resp = requests.patch(f"{API_BASE}/containers/{c['id']}/pickup-requests/{req['id']}/accept", timeout=5)
                                if resp.ok:
                                    st.success("Antrag angenommen.")
                                    st.rerun()
                                st.error(f"Fehler: {resp.text}")
                            if rcol3.button("Ablehnen", key=f"reject_{req['id']}"):
                                resp = requests.patch(f"{API_BASE}/containers/{c['id']}/pickup-requests/{req['id']}/reject", timeout=5)
                                if resp.ok:
                                    st.warning("Antrag abgelehnt.")
                                    st.rerun()
                                st.error(f"Fehler: {resp.text}")

                        if req["status"] == "angenommen" and not req.get("confirmed_by_metal_processor", False):
                            if rcol3.button("Abholung bestätigen", key=f"confirm_mv_{req['id']}", type="primary"):
                                resp = requests.patch(
                                    f"{API_BASE}/containers/{c['id']}/pickup-requests/{req['id']}/confirm?confirming_role=metallverarbeiter",
                                    timeout=5,
                                )
                                if resp.ok:
                                    st.success("Bestätigung gespeichert.")
                                    st.rerun()
                                st.error(f"Fehler: {resp.text}")
                        st.divider()

        st.markdown("---")
        with st.expander("Neuen Container anlegen"):
            with st.form("new_container_form"):
                c_number = st.text_input("Container-Nummer", placeholder="CNT-2026-XXX")
                c_location = st.text_input("Standort", placeholder="Lagerplatz X - Werk YY")
                c_capacity = st.number_input("Maximales Volumen (m³)", min_value=1.0, value=20.0, step=1.0)
                c_fill = st.slider("Füllstand (%)", min_value=0, max_value=100, value=0, step=5)
                st.caption(f"→ Geschätztes Volumen: ca. {round(c_fill / 100 * c_capacity, 1)} m³")
                c_status = st.selectbox("Status", ["leer", "teilbefuellt", "voll", "abholbereit"])
                c_class = st.selectbox("Schrottklasse (optional)", ["", "E1", "E2", "E3", "E6", "E8", "E40"])
                c_notes = st.text_area("Anmerkungen")
                submitted = st.form_submit_button("Container anlegen")
            if submitted:
                payload = {
                    "container_number": c_number,
                    "owner_id": actor_id,
                    "location": c_location,
                    "capacity_m3": c_capacity,
                    "fill_level": c_fill,
                    "status": c_status,
                    "scrap_class": c_class or None,
                    "notes": c_notes or None,
                }
                resp = requests.post(f"{API_BASE}/containers", json=payload, timeout=5)
                if resp.ok:
                    st.success(f"Container {c_number} angelegt.")
                    st.rerun()
                st.error(f"Fehler: {resp.text}")

        st.markdown("---")
        st.subheader("Abholhistorie")
        history = fetch_history(actor_id)
        if not history:
            st.info("Noch keine abgeschlossenen Abholungen.")
        else:
            my_containers = fetch_containers(owner_id=actor_id)
            rows = []
            for h in history:
                cont_num = next((c["container_number"] for c in my_containers if c["id"] == h["container_id"]), h["container_id"][:8] + "...")
                rows.append({
                    "Datum": h["completed_at"][:10] if h["completed_at"] else "–",
                    "Container": cont_num,
                    "Schrottart": h["scrap_type"] or "–",
                    "Händler": actor_name(actors, h["trader_id"]),
                    "Gesch. Volumen (m³)": h["estimated_volume_m3"],
                    "Füllstand bei Abholung (%)": h["fill_level_at_pickup"],
                })
            st.dataframe(rows, use_container_width=True)

    else:
        can_market_view = check_abac("market_view")
        can_submit = check_abac("submit_request")

        st.subheader(f"Verfügbare Container – {current_actor['name']}")
        st.caption("Containermarkt, eigene Abholanträge, direkte Anfragen von Metallverarbeitern und Abholhistorie.")

        if can_market_view:
            all_containers = fetch_containers()
            available = [c for c in all_containers if c["status"] in ("abholbereit", "verfuegbar")]
            if not available:
                st.info("Derzeit keine Container zur Abholung verfügbar.")
            else:
                for c in available:
                    fill = c["fill_level"]
                    est_vol = c.get("estimated_volume_m3", 0.0)
                    owner_nm = actor_name(actors, c["owner_id"])
                    icon = CONTAINER_ICONS.get(c["status"], "❓")

                    with st.expander(
                        f"{icon} **{c['container_number']}** — {fill}% voll ({est_vol:.1f} m³) | "
                        f"{c['scrap_class'] or 'k.A.'} | Eigentümer: {owner_nm}",
                        expanded=True,
                    ):
                        col1, col2 = st.columns(2)
                        col1.markdown(f"**Standort:** {c['location']}")
                        col1.markdown(f"**Schrottklasse:** {c['scrap_class'] or '–'}")
                        col1.markdown(f"**Füllstand:** {fill} %")
                        col1.progress(fill / 100)
                        col1.caption(f"ca. {est_vol:.1f} m³ von {c['capacity_m3']:.0f} m³")
                        if c["notes"]:
                            col2.info(c["notes"])

                        all_reqs = fetch_pickup_requests(c["id"])
                        my_reqs = [r for r in all_reqs if r["requesting_actor_id"] == actor_id]
                        other_count = len(all_reqs) - len(my_reqs)
                        st.markdown("---")

                        if my_reqs:
                            for r in my_reqs:
                                r_icon = REQUEST_ICONS.get(r["status"], "❓")
                                price_str = f"{r['offered_price_per_ton']:.2f} EUR/t" if r["offered_price_per_ton"] else "–"
                                st.markdown(f"{r_icon} **Mein Antrag:** {r['status']}  \nTermin: {r['requested_pickup_date']} | Preis: {price_str}")
                                if r["status"] == "angenommen" and not r.get("confirmed_by_trader", False):
                                    if st.button("Abholung bestätigen", key=f"confirm_h_{r['id']}", type="primary"):
                                        resp = requests.patch(
                                            f"{API_BASE}/containers/{c['id']}/pickup-requests/{r['id']}/confirm?confirming_role=haendler",
                                            timeout=5,
                                        )
                                        if resp.ok:
                                            st.success("Bestätigung gespeichert.")
                                            st.rerun()
                                        st.error(f"Fehler: {resp.text}")
                        elif can_submit:
                            st.caption(f"Noch kein eigener Antrag. {other_count} weitere Anträge vorhanden.")
                            with st.form(f"request_form_{c['id']}"):
                                r_date = st.date_input("Gewünschtes Abholdatum", value=date.today() + timedelta(days=3), min_value=date.today())
                                r_price = st.number_input("Angebotener Preis (EUR/t)", min_value=0.0, value=180.0, step=1.0)
                                r_notes = st.text_area("Anmerkungen (optional)")
                                submit_req = st.form_submit_button("Abholantrag stellen", type="primary")
                            if submit_req:
                                payload = {
                                    "requesting_actor_id": actor_id,
                                    "requested_pickup_date": r_date.isoformat(),
                                    "offered_price_per_ton": r_price,
                                    "notes": r_notes or None,
                                    "initiator": "haendler",
                                }
                                resp = requests.post(f"{API_BASE}/containers/{c['id']}/pickup-requests", json=payload, timeout=5)
                                if resp.ok:
                                    st.success("Abholantrag gestellt.")
                                    st.rerun()
                                st.error(f"Fehler: {resp.text}")

        st.markdown("---")
        st.subheader("Anfragen an mich")
        all_containers_full = fetch_containers()
        incoming_mv = []
        for c in all_containers_full:
            c_reqs = fetch_pickup_requests(c["id"])
            for r in c_reqs:
                if r["requesting_actor_id"] == actor_id and r["initiator"] == "metallverarbeiter" and r["status"] in ("ausstehend", "angenommen"):
                    r["_container_number"] = c["container_number"]
                    r["_owner"] = actor_name(actors, c["owner_id"])
                    r["_container_id"] = c["id"]
                    r["_fill_level"] = c["fill_level"]
                    r["_capacity_m3"] = c["capacity_m3"]
                    r["_scrap_class"] = c["scrap_class"]
                    incoming_mv.append(r)

        if not incoming_mv:
            st.info("Keine ausstehenden Anfragen von Metallverarbeitern.")
        else:
            for r in sorted(incoming_mv, key=lambda x: x["created_at"], reverse=True):
                r_icon = REQUEST_ICONS.get(r["status"], "❓")
                icol1, icol2, icol3 = st.columns([3, 2, 2])
                icol1.markdown(
                    f"{r_icon} **{r['_container_number']}** (Eigentümer: {r['_owner']})  \n"
                    f"Schrottklasse: {r['_scrap_class'] or 'k.A.'}  \n"
                    f"Füllstand: {r['_fill_level']}% "
                    f"(ca. {round(r['_fill_level']/100*r['_capacity_m3'],1)} m³)  \n"
                    f"Wunschtermin: {r['requested_pickup_date']}"
                )
                if r["notes"]:
                    icol1.caption(r["notes"])
                icol2.markdown(f"Status: **{r['status']}**")

                if r["status"] == "ausstehend":
                    if icol3.button("Annehmen", key=f"mv_accept_{r['id']}", type="primary"):
                        resp = requests.patch(f"{API_BASE}/containers/{r['_container_id']}/pickup-requests/{r['id']}/accept", timeout=5)
                        if resp.ok:
                            st.success("Anfrage angenommen.")
                            st.rerun()
                        st.error(f"Fehler: {resp.text}")
                    if icol3.button("Ablehnen", key=f"mv_reject_{r['id']}"):
                        resp = requests.patch(f"{API_BASE}/containers/{r['_container_id']}/pickup-requests/{r['id']}/reject", timeout=5)
                        if resp.ok:
                            st.warning("Anfrage abgelehnt.")
                            st.rerun()
                        st.error(f"Fehler: {resp.text}")
                elif r["status"] == "angenommen" and not r.get("confirmed_by_trader", False):
                    if icol3.button("Abholung bestätigen", key=f"confirm_h_mv_{r['id']}", type="primary"):
                        resp = requests.patch(
                            f"{API_BASE}/containers/{r['_container_id']}/pickup-requests/{r['id']}/confirm?confirming_role=haendler",
                            timeout=5,
                        )
                        if resp.ok:
                            st.success("Bestätigung gespeichert.")
                            st.rerun()
                        st.error(f"Fehler: {resp.text}")
                st.divider()

        st.markdown("---")
        st.subheader("Meine Abholhistorie")
        history = fetch_history(actor_id)
        if not history:
            st.info("Noch keine abgeschlossenen Abholungen.")
        else:
            rows = []
            for h in history:
                cont_num = next((c["container_number"] for c in all_containers_full if c["id"] == h["container_id"]), h["container_id"][:8] + "...")
                rows.append({
                    "Datum": h["completed_at"][:10] if h["completed_at"] else "–",
                    "Container": cont_num,
                    "Schrottart": h["scrap_type"] or "–",
                    "Eigentümer": actor_name(actors, h["metal_processor_id"]),
                    "Gesch. Volumen (m³)": h["estimated_volume_m3"],
                    "Füllstand bei Abholung (%)": h["fill_level_at_pickup"],
                })
            st.dataframe(rows, use_container_width=True)

if role != "metallverarbeiter":
    with tab_delivery:
        st.subheader("Transporte & Lieferungen")
        render_delivery_orders(display_orders, batches, actors_by_id, show_full=show_full_logistics)

        if display_orders and role == "haendler":
            st.markdown("---")
            st.subheader("Statusupdate")

            order_labels = {
                f"{batches[o.batch_id].batch_number if o.batch_id in batches else o.batch_id} – {o.delivery_status}": o.id
                for o in display_orders
            }
            selected_label = st.selectbox("Auftrag auswählen", list(order_labels.keys()))
            selected_order_id = order_labels[selected_label]

            col1, col2 = st.columns(2)
            new_delivery = col1.selectbox("Neuer Lieferstatus", ["geplant", "abgeholt", "in_transit", "geliefert", "verzoegert"])
            new_container = col2.selectbox("Neuer Containerstatus", ["leer", "teilbefuellt", "voll", "abholbereit"])

            if st.button("Status aktualisieren"):
                db = get_session()
                try:
                    updated = logistics_service.update_order_status(db, selected_order_id, new_delivery, new_container)
                    if updated:
                        st.success(f"Status aktualisiert: {new_delivery} / {new_container}")
                        st.rerun()
                    st.error("Auftrag nicht gefunden.")
                finally:
                    db.close()

        if role == "haendler":
            st.markdown("---")
            st.subheader("Neuen Transportauftrag anlegen")
            all_batches = list(batches.values())
            if not all_batches:
                st.warning("Keine Chargen vorhanden.")
            else:
                with st.form("neuer_auftrag"):
                    batch_opts = {b.batch_number: b.id for b in all_batches}
                    selected_batch_nr = st.selectbox("Charge", list(batch_opts.keys()))

                    col1, col2 = st.columns(2)
                    pickup_date = col1.date_input("Abholdatum", value=date.today() + timedelta(days=3))
                    delivery_date = col2.date_input("Geplantes Lieferdatum", value=date.today() + timedelta(days=5))
                    pickup_location = col1.text_input("Abholort", value=current_actor["organization"])
                    delivery_location = col2.text_input("Lieferziel", value="Südstahl AG Werk")
                    carrier = col2.text_input("Transportunternehmen (optional)")

                    container_status = st.selectbox("Containerstatus", ["leer", "teilbefuellt", "voll", "abholbereit"], index=3)
                    notes = st.text_area("Hinweise (optional)")
                    submitted = st.form_submit_button("Transportauftrag anlegen")

                if submitted:
                    db = get_session()
                    try:
                        order = logistics_service.create_logistics_order(
                            db=db,
                            batch_id=batch_opts[selected_batch_nr],
                            requesting_actor_id=actor_id,
                            pickup_date=pickup_date,
                            delivery_date=delivery_date,
                            pickup_location=pickup_location,
                            delivery_location=delivery_location,
                            container_status=container_status,
                            delivery_status="geplant",
                            carrier=carrier or None,
                            notes=notes or None,
                        )
                        st.success(f"Transportauftrag angelegt (ID: {order.id[:8]}...)")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Fehler beim Anlegen: {exc}")
                    finally:
                        db.close()
