import streamlit as st
import pandas as pd
import requests
from datetime import date, timedelta

from app.auth.session import init_session, render_role_switcher, get_current_role, get_current_actor_id
from app.db.session import get_session
from app.db.models import ScrapBatch, Actor, ChemicalComposition
from app.abac.engine import get_abac_engine, RESTRICTED_MARKER
from app.ui_helpers import (
    badge, scrap_class_label, EU_SCRAP_CLASSES,
    EAF_STATUS_COLORS, format_datetime, scrap_origin_category, assigned_trader_name
)

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

API = "http://api:8000"

st.set_page_config(page_title="Chargenübersicht", layout="wide")

init_session()
render_role_switcher()

st.title("Chargenübersicht")

role = get_current_role()
actor_id = get_current_actor_id()
engine = get_abac_engine()

db = get_session()
try:
    role_actors = (
        db.query(Actor)
        .filter(Actor.role == role)
        .order_by(Actor.name.asc())
        .all()
    )
finally:
    db.close()

current_actor = next((actor for actor in role_actors if actor.id == actor_id), None)
if current_actor is None and role_actors:
    current_actor = role_actors[0]
    actor_id = current_actor.id
    st.session_state.actor_id = actor_id

if role_actors:
    selected_actor = st.selectbox(
        "Unternehmen",
        options=role_actors,
        index=role_actors.index(current_actor) if current_actor in role_actors else 0,
        format_func=lambda actor: actor.name,
        key=f"charge_overview_actor_{role}",
    )
    if selected_actor.id != actor_id:
        actor_id = selected_actor.id
        current_actor = selected_actor
        st.session_state.actor_id = actor_id
        st.rerun()

if current_actor:
    st.caption(f"Aktives Unternehmen: **{current_actor.name}**")

# ── Tabs je nach Rolle ────────────────────────────────────────────────────────
if role == "haendler":
    tab1, tab2 = st.tabs(["Alle Chargen", "Chargen-Verwaltung"])
elif role == "stahlwerk":
    tab1, tab3 = st.tabs(["Alle Chargen", "Chargenangebote"])
else:
    tab1, = st.tabs(["Alle Chargen"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: Alle Chargen (bisherige Übersicht)
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("Alle erfassten Schrottchargen auf der Plattform.")

    db = get_session()
    try:
        batches = db.query(ScrapBatch).order_by(ScrapBatch.created_at.desc()).all()
        actors = {a.id: a for a in db.query(Actor).all()}
        latest_chem = {}
        for b in batches:
            chem = (
                db.query(ChemicalComposition)
                .filter(ChemicalComposition.batch_id == b.id)
                .order_by(ChemicalComposition.measured_at.desc())
                .first()
            )
            latest_chem[b.id] = chem
    finally:
        db.close()

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        scrap_class_options = ["Alle"] + sorted(list(EU_SCRAP_CLASSES.keys()))
        selected_class = st.selectbox("Schrottklasse filtern", scrap_class_options)
    with col_f2:
        origin_options = ["Alle", "Altschrott", "Neuschrott", "Eigenschrott"]
        selected_origin = st.selectbox("Schrottart filtern", origin_options)

    filtered = batches
    if selected_class != "Alle":
        filtered = [b for b in filtered if b.scrap_class == selected_class]
    if selected_origin != "Alle":
        filtered = [b for b in filtered if scrap_origin_category(b.origin_type) == selected_origin]

    st.markdown(f"**{len(filtered)} Charge(n) gefunden**")

    can_see_eaf = engine.can_access_field(role, "scrapbatch", "eaf_compatibility")

    if not filtered:
        st.info("Keine Chargen gefunden.")
    else:
        header_cols = st.columns([1.5, 1.3, 1.8, 2.0, 1.8, 1.2, 1.5] + ([1.5] if can_see_eaf else []) + [1.3, 1.0])
        header_idx = 0
        header_cols[header_idx].markdown("**Chargennummer**")
        header_idx += 1
        header_cols[header_idx].markdown("**Schrottart**")
        header_idx += 1
        header_cols[header_idx].markdown("**Schrottklasse**")
        header_idx += 1
        header_cols[header_idx].markdown("**Herkunft**")
        header_idx += 1
        header_cols[header_idx].markdown("**Händler**")
        header_idx += 1
        header_cols[header_idx].markdown("**Masse (kg)**")
        header_idx += 1
        header_cols[header_idx].markdown("**Analyse**")
        header_idx += 1
        if can_see_eaf:
            header_cols[header_idx].markdown("**EAF-Eignung**")
            header_idx += 1
        header_cols[header_idx].markdown("**Erfasst am**")
        header_idx += 1
        header_cols[header_idx].markdown("**Aktion**")
        st.divider()

        for batch in filtered:
            chem = latest_chem.get(batch.id)
            scrap_type = scrap_origin_category(batch.origin_type)
            trader_name = assigned_trader_name(actors, batch.owner_id, batch.created_by_trader_id)

            with st.container():
                cols = st.columns([1.5, 1.3, 1.8, 2.0, 1.8, 1.2, 1.5] + ([1.5] if can_see_eaf else []) + [1.3, 1.0])
                idx = 0

                cols[idx].markdown(f"**{batch.batch_number}**")
                idx += 1

                cols[idx].markdown(scrap_type)
                idx += 1

                cols[idx].markdown(scrap_class_label(batch.scrap_class))
                idx += 1

                cols[idx].markdown(batch.origin_type or "–")
                idx += 1

                cols[idx].markdown(trader_name)
                idx += 1

                cols[idx].markdown(f"{batch.mass_kg:,.0f}")
                idx += 1

                if chem:
                    if chem.threshold_exceeded:
                        cols[idx].markdown(badge("Grenzwert überschritten", "#B71C1C"), unsafe_allow_html=True)
                    else:
                        cols[idx].markdown(badge("Im Normalbereich", "#2E7D32"), unsafe_allow_html=True)
                else:
                    cols[idx].markdown('<span style="color:#aaa;font-style:italic;">Keine Analyse</span>', unsafe_allow_html=True)
                idx += 1

                if can_see_eaf:
                    eaf = batch.eaf_compatibility or "–"
                    color = EAF_STATUS_COLORS.get(eaf, "#546E7A")
                    cols[idx].markdown(badge(eaf, color), unsafe_allow_html=True)
                    idx += 1

                cols[idx].markdown(format_datetime(batch.created_at))
                idx += 1

                if cols[idx].button("Materialpass", key=f"mp_{batch.id}"):
                    st.session_state["selected_batch_id"] = batch.id
                    st.switch_page("pages/2_Materialpass.py")

            st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: Chargen-Verwaltung (nur Händler)
# ══════════════════════════════════════════════════════════════════════════════
if role == "haendler":
    with tab2:
        st.markdown("Erstelle Chargen aus Containerabholungen und biete sie Stahlwerken an.")

        actors_resp = requests.get(f"{API}/actors")
        all_actors = actors_resp.json() if actors_resp.ok else []
        stahlwerk_list = [a for a in all_actors if a["role"] == "stahlwerk"]

        STATUS_COLORS = {
            "entwurf":    "🟡",
            "angeboten":  "🔵",
            "zugewiesen": "🟢",
            "geliefert":  "✅",
        }

        # ── Meine Chargen ──────────────────────────────────────────────────────
        st.subheader("Meine Workflow-Chargen")
        batches_resp = requests.get(
            f"{API}/workflow/batches",
            params={"role": "haendler", "actor_id": actor_id},
        )
        wf_batches = batches_resp.json() if batches_resp.ok else []

        if not wf_batches:
            st.info("Noch keine Workflow-Chargen vorhanden.")
        else:
            for b in wf_batches:
                icon = STATUS_COLORS.get(b.get("status", ""), "⚪")
                label = (
                    f"{icon} **{b['batch_number']}** — "
                    f"{b.get('scrap_class','?')} | {b.get('mass_kg',0):,.0f} kg | "
                    f"Status: {b.get('status','?')}"
                )
                with st.expander(label):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Schrottklasse:** {b.get('scrap_class','–')}")
                        st.markdown(f"**Herkunftstyp:** {b.get('origin_type','–')}")
                        st.markdown(f"**Zugeordneter Händler:** {assigned_trader_name({a['id']: a for a in all_actors}, b.get('owner_id'), b.get('created_by_trader_id'))}")
                        st.markdown(f"**Region:** {b.get('origin_region','–')}")
                        st.markdown(f"**Masse:** {b.get('mass_kg',0):,.0f} kg")
                        st.markdown(f"**Aufbereitungsgrad:** {b.get('preparation_degree','–')}")
                        st.markdown(f"**Kontaminationsgrad:** {b.get('contamination_level','–')}")
                    with col2:
                        st.markdown(f"**Status:** {b.get('status','–')}")
                        st.markdown(f"**Erstellt am:** {(b.get('created_at') or '–')[:10]}")
                        if b.get("offered_to_steel_mill_id"):
                            mill = next((s for s in stahlwerk_list if s["id"] == b["offered_to_steel_mill_id"]), None)
                            st.markdown(f"**Angeboten an:** {mill['name'] if mill else b['offered_to_steel_mill_id']}")
                        if b.get("delivery_date"):
                            st.markdown(f"**Lieferdatum:** {b['delivery_date']}")
                        if b.get("confirmed_by_trader") is not None:
                            st.markdown(f"**Bestätigung Händler:** {'✅' if b['confirmed_by_trader'] else '⏳'}")
                            st.markdown(f"**Bestätigung Stahlwerk:** {'✅' if b['confirmed_by_steel_mill'] else '⏳'}")

                    # Chemie
                    chem = b.get("chemical")
                    if chem and chem.get("element_values"):
                        st.markdown("**Chemische Analyse:**")
                        ev = chem["element_values"]
                        th = chem.get("thresholds", {})
                        rows = [
                            {
                                "Element": el,
                                "Wert (%)": round(val, 4),
                                "Grenzwert (%)": round(th[el], 4) if el in th else "–",
                                "Status": "❌" if (el in th and val > th[el]) else "✅",
                            }
                            for el, val in ev.items() if el in th
                        ]
                        if rows:
                            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                    # Provenienz
                    prov = b.get("provenance_chain", [])
                    if prov:
                        st.markdown(f"**Herkunftskette:** {len(prov)} Abholung(en)")
                        prov_rows = [{
                            "Datum": (p.get("pickup_date") or "–")[:10],
                            "Schrotttyp": p.get("scrap_type", "–"),
                            "Vol. (m³)": p.get("estimated_volume_m3", "–"),
                            "Füllstand (%)": p.get("fill_level_at_pickup", "–"),
                        } for p in prov]
                        st.dataframe(pd.DataFrame(prov_rows), use_container_width=True, hide_index=True)

                    # Aktionen
                    batch_id = b["id"]
                    status = b.get("status")

                    if status == "entwurf" and stahlwerk_list:
                        st.markdown("**Charge anbieten:**")
                        oc1, oc2 = st.columns(2)
                        with oc1:
                            target_mill = st.selectbox(
                                "Stahlwerk",
                                stahlwerk_list,
                                format_func=lambda a: a["name"],
                                key=f"offer_mill_{batch_id}",
                            )
                            delivery_date = st.date_input(
                                "Lieferdatum",
                                value=date.today() + timedelta(days=14),
                                key=f"offer_date_{batch_id}",
                            )
                        with oc2:
                            st.markdown("")
                            if st.button("Angebot senden", key=f"btn_offer_{batch_id}", type="primary"):
                                resp = requests.post(
                                    f"{API}/workflow/batches/{batch_id}/offer",
                                    params={"actor_id": actor_id},
                                    json={
                                        "steel_mill_id": target_mill["id"],
                                        "delivery_date": delivery_date.isoformat(),
                                    },
                                )
                                if resp.ok:
                                    st.success(f"Angebot gesendet an {target_mill['name']}.")
                                    st.rerun()
                                else:
                                    st.error(resp.json().get("detail", resp.text))

                    elif status == "zugewiesen" and not b.get("confirmed_by_trader"):
                        if st.button("Lieferung bestätigen (Händler)", key=f"btn_confirm_{batch_id}", type="primary"):
                            resp = requests.post(
                                f"{API}/workflow/batches/{batch_id}/confirm-delivery",
                                json={"confirming_role": "haendler", "actor_id": actor_id},
                            )
                            if resp.ok:
                                st.success(resp.json().get("message", "Bestätigung gespeichert."))
                                st.rerun()
                            else:
                                st.error(resp.json().get("detail", resp.text))
                    elif status == "zugewiesen" and b.get("confirmed_by_trader"):
                        st.success("Lieferung durch dich bestätigt – warte auf Stahlwerk.")

        st.divider()

        # ── Neue Charge anlegen ────────────────────────────────────────────────
        st.subheader("Neue Charge anlegen")

        history_resp = requests.get(f"{API}/pickup-history", params={"actor_id": actor_id})
        history_entries = history_resp.json() if history_resp.ok else []

        fc1, fc2 = st.columns(2)
        with fc1:
            new_scrap_class = st.text_input("Schrottklasse (z. B. E1, E3, E8)", value="E1", key="create_batch_scrap_class")
            new_origin_type = st.text_input("Herkunftstyp", value="Industriebetrieb", key="create_batch_origin_type")
            new_mass_kg = st.number_input("Masse (kg)", min_value=100.0, value=10000.0, step=100.0, key="create_batch_mass")
            new_origin_region = st.text_input("Region (optional)", key="create_batch_region")
        with fc2:
            new_prep = st.selectbox("Aufbereitungsgrad", ["", "unbearbeitet", "geschreddert", "gebündelt", "sortiert"], key="create_batch_prep")
            new_contam = st.selectbox("Kontaminationsgrad", ["", "gering", "mittel", "hoch"], key="create_batch_contam")
            new_period = st.text_input("Sammelperiode (optional)", key="create_batch_period")

        if history_entries:
            pickup_options = {
                f"{h['id'][:8]}... | {h.get('scrap_type','?')} | {h.get('estimated_volume_m3','?')} m³ | {(h.get('completed_at') or '–')[:10]}": h["id"]
                for h in history_entries
            }
            preselected_pickups = st.session_state.pop("prefill_pickup_ids", [])
            default_pickup_labels = [
                label for label, pickup_id in pickup_options.items()
                if pickup_id in preselected_pickups
            ]
            selected_pickups = st.multiselect(
                "Abholhistorie verknüpfen (optional)",
                options=list(pickup_options.keys()),
                default=default_pickup_labels,
                key="create_batch_pickups",
            )
            selected_pickup_ids = [pickup_options[k] for k in selected_pickups]
        else:
            st.caption("Keine Abholhistorie vorhanden.")
            selected_pickup_ids = []

        add_chem = st.checkbox("Chemische Analyse hinterlegen", key="create_batch_add_chem")
        chem_values = {}
        if add_chem:
            cc1, cc2, cc3, cc4, cc5 = st.columns(5)
            cu = cc1.number_input("Cu (%)", min_value=0.0, max_value=5.0, value=0.20, step=0.01, format="%.3f", key="create_batch_cu")
            sn = cc2.number_input("Sn (%)", min_value=0.0, max_value=2.0, value=0.05, step=0.01, format="%.3f", key="create_batch_sn")
            ni = cc3.number_input("Ni (%)", min_value=0.0, max_value=5.0, value=0.08, step=0.01, format="%.3f", key="create_batch_ni")
            cr = cc4.number_input("Cr (%)", min_value=0.0, max_value=5.0, value=0.05, step=0.01, format="%.3f", key="create_batch_cr")
            mo = cc5.number_input("Mo (%)", min_value=0.0, max_value=2.0, value=0.02, step=0.01, format="%.3f", key="create_batch_mo")
            chem_values = {"Cu": cu, "Sn": sn, "Ni": ni, "Cr": cr, "Mo": mo}
            limits = {"Cu": 0.35, "Sn": 0.10, "Ni": 0.15, "Cr": 0.20, "Mo": 0.05}
            warnings = [f"{el}: {val:.3f}% > {limits[el]:.2f}%" for el, val in chem_values.items() if val > limits.get(el, 999)]
            if warnings:
                st.warning("Grenzwert-Überschreitungen: " + ", ".join(warnings))

        submitted = st.button("Charge anlegen", type="primary", key="create_batch_submit")

        if submitted:
            payload = {
                "scrap_class": new_scrap_class,
                "origin_type": new_origin_type,
                "mass_kg": new_mass_kg,
                "trader_id": actor_id,
                "preparation_degree": new_prep or None,
                "contamination_level": new_contam or None,
                "origin_region": new_origin_region or None,
                "collection_period": new_period or None,
                "source_pickup_ids": selected_pickup_ids,
                "chemical_values": chem_values if add_chem else None,
            }
            resp = requests.post(f"{API}/workflow/batches", json=payload)
            if resp.ok:
                data = resp.json()
                st.success(f"Charge **{data['batch_number']}** angelegt.")
                st.rerun()
            else:
                st.error(resp.json().get("detail", resp.text))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: Chargenangebote (nur Stahlwerk)
# ══════════════════════════════════════════════════════════════════════════════
if role == "stahlwerk":
    with tab3:
        st.markdown("Eingehende Chargenangebote prüfen, annehmen oder ablehnen und Lieferungen bestätigen.")

        tier = None
        if actor_id:
            actors_resp = requests.get(f"{API}/actors")
            all_actors = actors_resp.json() if actors_resp.ok else []
            me = next((a for a in all_actors if a["id"] == actor_id), None)
            tier = (me or {}).get("relationship_tier") or "standard"
            st.caption(f"Relationship-Tier: **{tier}** — bestimmt ABAC-Detailtiefe der Chemiedaten.")

        batches_resp = requests.get(
            f"{API}/workflow/batches",
            params={"role": "stahlwerk", "actor_id": actor_id},
        )
        sw_batches = batches_resp.json() if batches_resp.ok else []

        incoming = [b for b in sw_batches if b.get("status") == "angeboten"]
        assigned = [b for b in sw_batches if b.get("status") == "zugewiesen"]
        delivered = [b for b in sw_batches if b.get("status") == "geliefert"]

        def is_visible(value):
            return value not in (None, "", RESTRICTED_MARKER)

        def render_chem_chart(chem, batch_number, chart_key):
            if not chem or chem.get("element_values") in (None, RESTRICTED_MARKER):
                st.caption("Keine Analysedaten.")
                return
            ev = chem["element_values"]
            th = chem.get("thresholds", {})
            elements = [el for el in ev if el in th]
            if not elements:
                return
            values = [ev[el] for el in elements]
            limits_vals = [th[el] for el in elements]
            colors = []
            for el, val in zip(elements, values):
                lim = th.get(el)
                if lim and val > lim:
                    colors.append("#ef4444")
                elif lim and val > lim * 0.85:
                    colors.append("#f59e0b")
                else:
                    colors.append("#22c55e")

            if PLOTLY_OK:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=elements, y=values, marker_color=colors,
                    name="Messwert",
                    text=[f"{v:.3f}%" for v in values], textposition="outside",
                ))
                fig.add_trace(go.Scatter(
                    x=elements, y=limits_vals, mode="markers",
                    marker=dict(symbol="line-ew", size=20, color="red", line=dict(color="red", width=2)),
                    name="Grenzwert",
                ))
                fig.update_layout(
                    title=f"Chemie – {batch_number}",
                    yaxis_title="Anteil (%)", height=320,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{chart_key}")
            else:
                rows = [{"Element": el, "Wert (%)": round(v, 4), "Grenzwert (%)": round(th[el], 4), "Status": "❌" if v > th[el] else "✅"}
                        for el, v in zip(elements, values)]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        def render_sw_batch(b, section):
            batch_id = b["id"]
            status = b.get("status", "?")
            icons = {"angeboten": "🔵", "zugewiesen": "🟢", "geliefert": "✅"}
            label = (
                f"{icons.get(status,'⚪')} **{b['batch_number']}** — "
                f"{b.get('scrap_class','?')} | {b.get('mass_kg',0):,.0f} kg"
                + (f" | Lieferung: {b['delivery_date']}" if b.get("delivery_date") else "")
            )
            with st.expander(label):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Schrottklasse:** {b.get('scrap_class','–')}")
                    st.markdown(f"**Masse:** {b.get('mass_kg',0):,.0f} kg")
                    st.markdown(f"**Aufbereitungsgrad:** {b.get('preparation_degree','–')}")
                    if is_visible(b.get("collection_period")):
                        st.markdown(f"**Erfassungszeitraum:** {b['collection_period']}")
                    if is_visible(b.get("origin_type")):
                        st.markdown(f"**Herkunftstyp:** {b['origin_type']}")
                    if is_visible(b.get("origin_region")):
                        st.markdown(f"**Region:** {b['origin_region']}")
                    if is_visible(b.get("volume_m3")):
                        st.markdown(f"**Volumen:** {b['volume_m3']} m³")
                    if is_visible(b.get("contamination_level")):
                        st.markdown(f"**Kontaminationsgrad:** {b['contamination_level']}")
                    if is_visible(b.get("eaf_compatibility")):
                        st.markdown(f"**EAF-Eignung:** {b['eaf_compatibility']}")
                with col2:
                    if b.get("delivery_date"):
                        st.markdown(f"**Lieferdatum:** {b['delivery_date']}")
                    if status == "zugewiesen":
                        st.markdown(f"**Bestätigung Händler:** {'✅' if b.get('confirmed_by_trader') else '⏳'}")
                        st.markdown(f"**Bestätigung Stahlwerk:** {'✅' if b.get('confirmed_by_steel_mill') else '⏳'}")
                    if b.get("provenance_count"):
                        st.markdown(f"**Provenienz:** {b['provenance_count']} Abholung(en)")

                chem = b.get("chemical")
                if chem and chem.get("element_values") not in (None, RESTRICTED_MARKER):
                    st.markdown("---")
                    st.markdown("**Chemische Zusammensetzung** *(nur Strategic-Tier sichtbar)*")
                    render_chem_chart(chem, b["batch_number"], f"{section}_{batch_id[:8]}")
                    exceeded = chem.get("exceeded_elements", [])
                    if exceeded:
                        st.warning(f"Grenzwertüberschreitungen: **{', '.join(exceeded)}**")
                    else:
                        st.success("Alle Grenzwerte eingehalten.")

                st.markdown("---")
                if section == "incoming":
                    ac, rc = st.columns(2)
                    with ac:
                        if st.button("Annehmen", key=f"accept_{batch_id}", type="primary"):
                            resp = requests.post(f"{API}/workflow/batches/{batch_id}/accept-offer", params={"actor_id": actor_id})
                            if resp.ok:
                                st.success("Angenommen.")
                                st.rerun()
                            else:
                                st.error(resp.json().get("detail", resp.text))
                    with rc:
                        if st.button("Ablehnen", key=f"reject_{batch_id}"):
                            resp = requests.post(f"{API}/workflow/batches/{batch_id}/reject-offer", params={"actor_id": actor_id})
                            if resp.ok:
                                st.info("Abgelehnt.")
                                st.rerun()
                            else:
                                st.error(resp.json().get("detail", resp.text))

                elif section == "assigned" and not b.get("confirmed_by_steel_mill"):
                    if st.button("Lieferung bestätigen (Stahlwerk)", key=f"confirm_{batch_id}", type="primary"):
                        resp = requests.post(
                            f"{API}/workflow/batches/{batch_id}/confirm-delivery",
                            json={"confirming_role": "stahlwerk", "actor_id": actor_id},
                        )
                        if resp.ok:
                            st.success(resp.json().get("message", "Bestätigung gespeichert."))
                            st.rerun()
                        else:
                            st.error(resp.json().get("detail", resp.text))
                elif section == "assigned" and b.get("confirmed_by_steel_mill"):
                    st.success("Bereits bestätigt – warte auf Händler.")

        sw_tab1, sw_tab2, sw_tab3 = st.tabs([
            f"Eingehende Angebote ({len(incoming)})",
            f"Zugewiesen ({len(assigned)})",
            f"Geliefert ({len(delivered)})",
        ])

        with sw_tab1:
            if not incoming:
                st.info("Keine offenen Angebote.")
            for b in incoming:
                render_sw_batch(b, "incoming")

        with sw_tab2:
            if not assigned:
                st.info("Keine zugewiesenen Chargen.")
            for b in assigned:
                render_sw_batch(b, "assigned")

        with sw_tab3:
            if not delivered:
                st.info("Noch keine abgeschlossenen Lieferungen.")
            else:
                rows = [{
                    "Charge": b["batch_number"],
                    "Klasse": b.get("scrap_class", "–"),
                    "Masse (kg)": f"{b.get('mass_kg',0):,.0f}",
                    "Lieferdatum": b.get("delivery_date", "–"),
                    "EAF-Eignung": b.get("eaf_compatibility", "–") if is_visible(b.get("eaf_compatibility")) else "–",
                    "Überschreitungen": (
                        ", ".join((b.get("chemical") or {}).get("exceeded_elements", []))
                        if (b.get("chemical") or {}).get("exceeded_elements") not in (None, RESTRICTED_MARKER)
                        else "–"
                    ) or "keine",
                } for b in delivered]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
