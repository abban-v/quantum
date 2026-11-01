"""Q-EVR interactive dashboard.

Run with:
    uv run streamlit run app.py
"""

from __future__ import annotations

from datetime import date, datetime, time
from time import monotonic

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from quantum.config import Config
from quantum.data.fetch import DataFetchError, fetch_graph
from quantum.data.loader import (
    DataValidationError,
    apply_clearance_overrides,
    load_hospitals,
    load_scenarios,
    load_vehicles,
)
from quantum.dispatch import DispatchError, RoutePlan
from quantum.nlp_parser import parse_incident
from quantum.qaoa_solver import QAOAResult, run_qaoa
from quantum.runtime import run_with_large_stack
from quantum.scenarios import build_custom_scenario, dispatch_scenario
from quantum.sim import SimulationEngine
from quantum.traffic import (
    CLASS_COLORS,
    TrafficModel,
    click_key,
    edge_coords,
    street_names,
    street_pick,
)
from quantum.visualize import (
    CLASSICAL_COLOR,
    MAP_CENTER,
    MAP_ZOOM,
    QUANTUM_COLOR,
    add_click_marker,
    add_hospitals,
    add_incidents,
    add_route,
    add_run,
    add_traffic_layer,
    add_traffic_legend,
    add_vehicles,
    base_map,
    region_bounds,
)

st.set_page_config(page_title="Q-EVR", page_icon="🚑", layout="wide")


@st.cache_resource(show_spinner="Loading Manhattan road graph…")
def load_world():
    cfg = Config.load()
    graph = fetch_graph(cfg)
    apply_clearance_overrides(graph)
    return cfg, graph


@st.cache_data(show_spinner=False)
def world_bounds(_graph) -> tuple[float, float, float, float]:
    return region_bounds(_graph)


def init_state() -> None:
    defaults = {
        "text": "",
        "click": None,
        "last_click_key": None,
        "custom": False,
        "scenario": None,
        "prepared": None,
        "plans": [],
        "quantum": None,
        "triage": None,
        "loaded_scenario": None,
        "notice": "",
        "traffic": TrafficModel(),
        "traffic_edge": None,
        "plan_stamp": None,
        "plans_when": None,
        "sim": None,
        "sim_playing": False,
        "sim_speed": 120.0,
        "sim_last_tick": 0.0,
        "network_factor": 1.0,
        "street_names": [],
        "map_center": MAP_CENTER,
        "map_zoom": MAP_ZOOM,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_results() -> None:
    st.session_state.plans = []
    st.session_state.quantum = None
    st.session_state.sim = None
    st.session_state.sim_playing = False
    st.session_state.plan_stamp = None
    st.session_state.plans_when = None


def traffic_stamp(when: datetime, traffic: TrafficModel) -> tuple:
    overrides = tuple(
        sorted((key, round(value, 3)) for key, value in traffic.overrides.items())
    )
    return (
        when.strftime("%Y-%m-%d %H:%M"),
        round(traffic.network_multiplier, 3),
        overrides,
    )


def apply_network_traffic() -> None:
    """Apply the sidebar's network-wide multiplier to the traffic model."""
    traffic = st.session_state.traffic
    try:
        traffic.set_network_multiplier(float(st.session_state.network_factor))
    except ValueError as exc:
        st.session_state.notice = str(exc)
        return
    clear_results()
    st.session_state.notice = (
        f"Network traffic multiplier set to {traffic.network_multiplier:.1f}×. "
        "Press Dispatch to recalculate."
    )


def render_plan_table(plans: list[RoutePlan], scenario) -> None:
    hospital_names = {hospital.id: hospital.name for hospital in scenario.hospitals}
    patient_rows = []
    for plan in plans:
        for incident_id in plan.incident_ids:
            hospital_id = plan.patient_hospitals.get(incident_id, plan.hospital_id)
            patient_rows.append(
                {
                    "Vehicle": plan.vehicle_id,
                    "Patient": incident_id,
                    "Hospital": hospital_names.get(hospital_id, hospital_id),
                }
            )
    st.markdown("**Per-patient destination**")
    st.dataframe(pd.DataFrame(patient_rows), hide_index=True)

    summary = pd.DataFrame(
        [
            {
                "Vehicle": plan.vehicle_id,
                "Stops": len(plan.incident_ids),
                "Transit (min)": round(plan.total_transit_s / 60.0, 1),
                "Offload (min)": round(plan.offload_min, 1),
                "Mission (min)": round(plan.total_mission_min, 1),
                "Equipment OK": plan.equipment_match,
                "Specialty OK": plan.specialty_match,
                "Pruned edges": plan.pruned_edges,
            }
            for plan in plans
        ]
    )
    st.markdown("**Fleet plan**")
    st.dataframe(summary, hide_index=True)


def render_quantum(result: QAOAResult) -> None:
    st.subheader("Quantum comparison")
    if result.fallback:
        st.warning(
            "Quantum run fell back to the classical route. " + " ".join(result.notes)
        )
    cols = st.columns(4)
    cols[0].metric("Energy ratio", f"{result.approximation_ratio:.2f}")
    cols[1].metric("Repair mass", f"{result.repaired_feasibility:.1%}")
    cols[2].metric("Raw feasible", f"{result.raw_feasibility:.1%}")
    cols[3].metric("Runtime", f"{result.runtime_s:.2f} s")
    st.caption(
        "Energy ratio = exact QUBO optimum / repaired QAOA energy (1.00 is optimal). "
        "Repair mass = measured probability that repairs to the displayed order. "
        "Raw feasible = shots that were valid permutations before repair."
    )
    st.caption(
        f"QAOA order: {' → '.join(result.order_ids)} · "
        f"{result.iterations} evaluations · {result.samples} shots"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Route": "Classical",
                    "Order": " → ".join(result.classical_plan.incident_ids),
                    "Objective (min)": round(
                        result.classical_plan.objective_score_s / 60.0, 1
                    ),
                    "Mission (min)": round(
                        result.classical_plan.total_mission_min, 1
                    ),
                },
                {
                    "Route": "Quantum (repaired)",
                    "Order": " → ".join(result.quantum_plan.incident_ids),
                    "Objective (min)": round(
                        result.quantum_plan.objective_score_s / 60.0, 1
                    ),
                    "Mission (min)": round(result.quantum_plan.total_mission_min, 1),
                },
            ]
        ),
        hide_index=True,
    )
    for note in result.notes:
        st.caption(note)


@st.fragment(run_every=1.0)
def simulation_tick() -> None:
    """Advance the simulation at most once per second while it is playing.

    The throttle matters: this fragment also runs during ordinary full-app
    reruns. Without it, ``st.rerun(scope="app")`` would immediately rerun the
    app again, ticking the engine in a tight loop and finishing the whole
    simulation before the browser could draw a single frame.
    """
    engine = st.session_state.get("sim")
    if engine is None or not st.session_state.get("sim_playing", False):
        return
    now = monotonic()
    last = float(st.session_state.get("sim_last_tick", 0.0))
    if now - last < 0.9:
        return
    st.session_state.sim_last_tick = now
    if engine.finished:
        st.session_state.sim_playing = False
        st.rerun(scope="app")
    engine.tick(float(st.session_state.get("sim_speed", 120.0)))
    if engine.finished:
        st.session_state.sim_playing = False
    st.rerun(scope="app")


def render_simulation(engine: SimulationEngine, when: datetime) -> None:
    metrics = engine.metrics()
    playing = st.session_state.sim_playing

    cols = st.columns(4)
    cols[0].metric("Waiting", metrics["waiting"])
    cols[1].metric("On board", metrics["onboard"])
    cols[2].metric("Delivered", metrics["delivered"])
    cols[3].metric("Busy rigs", metrics["busy"])

    controls = st.columns(3)
    if engine.finished:
        if controls[0].button("Replay", width="stretch"):
            engine.reset()
            st.session_state.sim_playing = True
            st.session_state.sim_last_tick = 0.0
            st.rerun()
    elif controls[0].button("Pause" if playing else "Play", width="stretch"):
        st.session_state.sim_playing = not playing
        st.session_state.sim_last_tick = 0.0
        st.rerun()
    if controls[1].button("Step", width="stretch"):
        engine.tick(float(st.session_state.sim_speed))
        st.session_state.sim_last_tick = monotonic()
        st.rerun()
    if controls[2].button("Reset", width="stretch"):
        engine.reset()
        st.session_state.sim_playing = False
        st.session_state.sim_last_tick = 0.0
        st.rerun()

    st.slider(
        "Simulated seconds per tick",
        min_value=10.0,
        max_value=300.0,
        step=10.0,
        key="sim_speed",
    )
    delivered = metrics["delivered"]
    total = max(1, metrics["patients"])
    st.progress(delivered / total, text=f"{delivered}/{total} patients delivered")
    st.caption(
        f"Simulated clock: {engine.now:%a %H:%M:%S} · "
        f"dispatch at {when:%a %H:%M} · "
        f"{'finished' if engine.finished else 'running automatically'}"
    )

    fleet = pd.DataFrame(
        [
            {
                "Vehicle": run.vehicle.id,
                "Status": run.status.replace("_", " "),
                "Leg": f"{min(run.leg_index + 1, len(run.plan.legs))}/{len(run.plan.legs)}",
                "On board": ", ".join(run.onboard) or "—",
            }
            for run in engine.runs.values()
        ]
    )
    st.dataframe(fleet, hide_index=True)

    with st.expander("Event log", expanded=False):
        for stamp, message in list(reversed(engine.events))[:12]:
            st.caption(f"{stamp:%H:%M:%S} · {message}")


def main() -> None:
    init_state()

    st.title("🚑 Q-EVR — Quantum-Assisted Emergency Vehicle Routing")
    st.caption(
        "Manhattan demo · OpenStreetMap geometry · synthetic time-of-day traffic · "
        "simulated offload times · local Qiskit Aer · every record is labeled "
        "real / curated / synthetic."
    )

    try:
        cfg, graph = load_world()
        bounds = world_bounds(graph)
        scenarios = {scenario.id: scenario for scenario in load_scenarios()}
        hospitals = load_hospitals()
        vehicles = load_vehicles()
    except (DataFetchError, DataValidationError) as exc:
        st.error(f"Could not load data: {exc}")
        st.stop()

    if not st.session_state.street_names:
        st.session_state.street_names = street_names(graph)

    with st.sidebar:
        st.header("Scenario")
        scenario_id = st.selectbox(
            "Preset",
            options=list(scenarios),
            format_func=lambda key: f"{key} — {scenarios[key].name}",
            key="scenario_id",
        )
        selected = scenarios[scenario_id]
        if st.session_state.loaded_scenario != scenario_id:
            st.session_state.loaded_scenario = scenario_id
            st.session_state.custom = False
            st.session_state.text = selected.incidents[0].description
            st.session_state.click = (
                selected.incidents[0].lat,
                selected.incidents[0].lon,
            )
            st.session_state.triage = None
            clear_results()

        st.divider()
        st.subheader("Day and time")
        day = st.date_input("Date", value=date(2026, 11, 3))
        clock = st.time_input("Time", value=time(8, 30), step=900)
        when = datetime.combine(day, clock)
        traffic = st.session_state.traffic
        st.caption(f"Traffic profile: **{TrafficModel.label(when)}** (synthetic)")
        st.slider(
            "Network delay multiplier",
            min_value=0.5,
            max_value=3.0,
            step=0.1,
            key="network_factor",
            on_change=apply_network_traffic,
            help=(
                "Scales the synthetic time-of-day profile on every street. "
                "Explicit street overrides still take precedence."
            ),
        )

        st.subheader("Map")
        basemap_label = st.radio(
            "Basemap",
            options=["Offline vector", "Online OSM"],
            index=0,
            horizontal=True,
            help="Offline vector draws the cached OSM graph and needs no network.",
        )
        basemap = "vector" if basemap_label == "Offline vector" else "osm"
        show_traffic = st.toggle("Traffic layer", value=True)
        click_mode = st.radio(
            "Map click",
            options=["Place incident", "Edit traffic"],
            horizontal=True,
        )

        st.divider()
        st.subheader("Traffic editor")
        selected_edge = st.session_state.get("traffic_edge")
        if selected_edge:
            data = graph.get_edge_data(
                selected_edge["u"], selected_edge["v"], selected_edge["key"]
            ) or {}
            current = traffic.delay_factor(
                selected_edge["u"],
                selected_edge["v"],
                selected_edge["key"],
                data,
                when,
            )
            st.markdown(f"**{selected_edge['name']}**")
            st.caption(
                f"edge {selected_edge['u']}→{selected_edge['v']} · "
                f"{selected_edge['distance_m']:.0f} m from click"
            )
            factor = st.slider(
                "Delay factor",
                min_value=0.5,
                max_value=5.0,
                value=float(round(current, 2)),
                step=0.1,
                key=f"factor_{selected_edge['u']}_{selected_edge['v']}_{selected_edge['key']}",
            )
            if st.button("Apply override", width="stretch"):
                traffic.set_override(
                    selected_edge["u"],
                    selected_edge["v"],
                    selected_edge["key"],
                    factor,
                )
                clear_results()
                st.session_state.notice = (
                    "Traffic override applied. Press Dispatch to recalculate."
                )
                st.rerun()
            if st.button("Clear this street", width="stretch"):
                traffic.clear_override(
                    selected_edge["u"],
                    selected_edge["v"],
                    selected_edge["key"],
                )
                clear_results()
                st.session_state.notice = "Override cleared. Press Dispatch again."
                st.rerun()
            if st.button("Clear selection", width="stretch"):
                st.session_state.traffic_edge = None
                st.rerun()
        else:
            st.caption(
                "Choose **Edit traffic** and click a street on the map, or use "
                "the street selector below."
            )

        st.markdown("**Pick a street by name**")
        names = st.session_state.get("street_names") or []
        if names:
            street = st.selectbox(
                "Street",
                options=["—"] + names,
                key="street_choice",
                help=(
                    "Reliable alternative to map clicks. Applies to every edge "
                    "with this street name."
                ),
            )
            if street != "—":
                street_factor = st.slider(
                    "Street delay factor",
                    min_value=0.5,
                    max_value=5.0,
                    value=2.0,
                    step=0.1,
                    key="street_factor",
                )
                if st.button("Apply to street", width="stretch"):
                    count = traffic.set_street_override(graph, street, street_factor)
                    clear_results()
                    st.session_state.notice = (
                        f"Applied {street_factor:.1f}× to {count} edges on "
                        f"{street}. Press Dispatch to recalculate."
                    )
                    st.rerun()
                if st.button("Clear street override", width="stretch"):
                    count = traffic.clear_street_override(graph, street)
                    clear_results()
                    st.session_state.notice = (
                        f"Cleared overrides on {count} edges of {street}. "
                        "Press Dispatch again."
                    )
                    st.rerun()
        else:
            st.caption("No named streets are available in the cached graph.")

        if traffic.overrides:
            st.caption(f"{len(traffic.overrides)} edge override(s) active.")
        if traffic.overrides and st.button("Clear all overrides", width="stretch"):
            traffic.clear_all()
            clear_results()
            st.session_state.notice = "All overrides cleared. Press Dispatch again."
            st.rerun()

        st.divider()
        use_llm = st.checkbox("Use local Ollama fallback", value=False)
        multi = st.checkbox("Multi-casualty custom (3 patients)", value=False)
        if st.button("Reset to preset", width="stretch"):
            st.session_state.custom = False
            st.session_state.text = selected.incidents[0].description
            st.session_state.click = (
                selected.incidents[0].lat,
                selected.incidents[0].lon,
            )
            st.session_state.triage = None
            st.session_state.traffic_edge = None
            clear_results()
            st.rerun()

        st.divider()
        st.markdown(
            "**How to use**\n"
            "1. Pick a preset, or choose **Place incident** and click the map.\n"
            "2. Describe the emergency in plain text.\n"
            "3. Press **Dispatch** for the classical route. The simulation "
            "starts automatically.\n"
            "4. Press **Run quantum** for the QAOA comparison.\n"
            "5. Use **Pause**, **Step**, **Reset**, and the speed slider to "
            "inspect the simulation.\n"
            "6. Change traffic with the network multiplier or a street "
            "override, then press **Dispatch** again."
        )
        st.caption(
            "Traffic profiles, offload waits, and clearance limits are synthetic "
            "demo values, not live data."
        )

    if st.session_state.notice:
        st.info(st.session_state.notice)
        st.session_state.notice = ""

    if st.session_state.plans and st.session_state.plan_stamp != traffic_stamp(
        when, traffic
    ):
        st.warning(
            "Time or traffic changed since dispatch. Press **Dispatch** to "
            "recalculate the routes."
        )

    left, right = st.columns([2.1, 1.0], gap="large")

    with left:
        map_obj = base_map(
            center=st.session_state.map_center,
            zoom=st.session_state.map_zoom,
            tiles=basemap,
            bounds=bounds,
            graph=graph,
            max_edges=1200 if st.session_state.sim else 1800,
        )
        if show_traffic:
            add_traffic_layer(map_obj, graph, traffic, when, max_edges=1200)
            add_traffic_legend(map_obj)

        active_scenario = st.session_state.scenario
        active_hospitals = active_scenario.hospitals if active_scenario else hospitals
        active_vehicles = active_scenario.vehicles if active_scenario else vehicles
        if st.session_state.custom and active_scenario is None:
            active_incidents = []
        elif active_scenario is not None:
            active_incidents = active_scenario.incidents
        else:
            active_incidents = selected.incidents

        add_hospitals(map_obj, active_hospitals)
        add_vehicles(map_obj, active_vehicles)
        add_incidents(map_obj, active_incidents)

        if st.session_state.click:
            add_click_marker(
                map_obj,
                st.session_state.click,
                label="Selected incident point",
            )

        if selected_edge:
            coords = edge_coords(
                graph,
                selected_edge["u"],
                selected_edge["v"],
                selected_edge["key"],
            )
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=[list(point) for point in coords],
                    color="#ff00ff",
                    weight=8,
                    opacity=0.9,
                    tooltip="Selected street for traffic override",
                ).add_to(map_obj)

        engine = st.session_state.sim
        dynamic_layers: list[folium.FeatureGroup] = []
        if engine is not None:
            for run in engine.runs.values():
                dynamic_layers.append(add_run(map_obj, run, add_to_map=False))
        else:
            for plan in st.session_state.plans:
                layer = add_route(
                    map_obj,
                    plan,
                    color=CLASSICAL_COLOR,
                    label=f"Classical · {plan.vehicle_id}",
                    layer_name=f"Classical · {plan.vehicle_id}",
                    add_to_map=False,
                )
                if layer is not None:
                    dynamic_layers.append(layer)
            if st.session_state.quantum and not st.session_state.quantum.fallback:
                layer = add_route(
                    map_obj,
                    st.session_state.quantum.quantum_plan,
                    color=QUANTUM_COLOR,
                    label="Quantum (repaired)",
                    layer_name="Quantum (repaired)",
                    add_to_map=False,
                )
                if layer is not None:
                    dynamic_layers.append(layer)

        map_state = st_folium(
            map_obj,
            height=560,
            use_container_width=True,
            returned_objects=["last_clicked"],
            key="qevr_map",
            feature_group_to_add=dynamic_layers or None,
            layer_control=folium.LayerControl(collapsed=True),
        )

        if map_state:
            clicked = map_state.get("last_clicked")
            if clicked:
                key = click_key(clicked["lat"], clicked["lng"])
                if key != st.session_state.last_click_key:
                    st.session_state.last_click_key = key
                    if click_mode == "Edit traffic":
                        pick = street_pick(
                            graph, clicked["lat"], clicked["lng"], max_distance_m=120.0
                        )
                        if pick is None:
                            st.session_state.notice = (
                                "No street within 120 m of that click. Zoom in and "
                                "try again, or use the street selector."
                            )
                        else:
                            st.session_state.traffic_edge = pick
                            st.session_state.notice = (
                                f"Selected {pick['name']}. Adjust the factor in "
                                "the sidebar and apply."
                            )
                    else:
                        st.session_state.click = (
                            clicked["lat"],
                            clicked["lng"],
                        )
                        st.session_state.custom = True
                        st.session_state.scenario = None
                        st.session_state.triage = None
                        st.session_state.traffic_edge = None
                        clear_results()
                        st.session_state.notice = (
                            "Incident point placed. Describe it, then press Dispatch."
                        )
                    st.rerun()

        st.caption(
            "Map is bounded to Manhattan. Traffic colours: "
            + " · ".join(f"{name}" for name in CLASS_COLORS)
            + " (blue → yellow → red → dark red)."
        )

    with right:
        st.subheader("Emergency input")
        st.text_area(
            "Describe the emergency",
            key="text",
            height=110,
            placeholder="e.g. Snake bite with difficulty breathing…",
        )
        if st.button("Dispatch", type="primary", width="stretch"):
            try:
                if st.session_state.custom:
                    if not st.session_state.click:
                        raise DispatchError(
                            "Click the map to place the incident first."
                        )
                    triage = parse_incident(st.session_state.text, use_llm=use_llm)
                    scenario = build_custom_scenario(
                        selected,
                        st.session_state.click,
                        st.session_state.text,
                        triage,
                        multi,
                    )
                else:
                    scenario = selected.model_copy(deep=True)
                    triage = parse_incident(st.session_state.text, use_llm=use_llm)
                    if st.session_state.text.strip():
                        # Let the text drive the primary incident even for presets.
                        scenario.incidents[0].description = st.session_state.text
                        scenario.incidents[0].severity = triage.severity
                        scenario.incidents[0].equipment_required = (
                            triage.equipment_required
                        )
                        scenario.incidents[0].specialty_required = (
                            triage.specialty_required
                        )
                prepared, plans = dispatch_scenario(
                    scenario, graph, cfg, traffic=traffic, when=when
                )
                st.session_state.scenario = scenario
                st.session_state.prepared = prepared
                st.session_state.plans = plans
                st.session_state.triage = triage
                st.session_state.quantum = None
                st.session_state.sim = SimulationEngine(
                    prepared=prepared,
                    plans=plans,
                    start=when,
                )
                st.session_state.sim_playing = True
                st.session_state.sim_last_tick = 0.0
                st.session_state.plan_stamp = traffic_stamp(when, traffic)
                st.session_state.plans_when = when
                st.session_state.notice = (
                    f"Dispatched {len(plans)} route(s) with "
                    f"{TrafficModel.label(when)} traffic. Simulation started "
                    "automatically."
                )
                st.rerun()
            except (DispatchError, ValueError) as exc:
                st.error(str(exc))

        if st.session_state.triage:
            triage = st.session_state.triage
            st.markdown("**Parsed triage**")
            st.caption(
                f"λ={triage.severity:.0f} · "
                f"equipment={triage.equipment_required} · "
                f"specialty={triage.specialty_required or 'none'} · "
                f"confidence={triage.confidence:.0%} ({triage.parser})"
            )
            if triage.needs_confirmation:
                st.warning("Low confidence — confirm the details before dispatch.")
            for note in triage.notes:
                st.caption(note)

        if st.session_state.plans and st.session_state.scenario:
            st.markdown("**Dispatch plan**")
            render_plan_table(st.session_state.plans, st.session_state.scenario)

            plan = st.session_state.plans[0]
            if len(plan.incident_ids) >= 2:
                if st.button("Run quantum", width="stretch"):
                    try:
                        scenario = st.session_state.scenario
                        prepared = st.session_state.prepared
                        vehicle = scenario.vehicle(plan.vehicle_id)
                        incidents = [
                            incident
                            for incident in scenario.incidents
                            if incident.id in set(plan.incident_ids)
                        ]
                        hospital = scenario.hospital(plan.hospital_id)
                        with st.spinner("Running QAOA on local Aer…"):
                            result = run_with_large_stack(
                                run_qaoa,
                                prepared,
                                vehicle,
                                incidents,
                                hospital,
                                cfg,
                                scenario.seed,
                                1,
                                patient_hospitals=plan.patient_hospitals,
                            )
                        st.session_state.quantum = result
                        st.rerun()
                    except Exception as exc:  # keep the demo alive
                        st.error(f"Quantum run failed: {exc}")
            else:
                st.caption(
                    "Quantum ordering needs at least two stops. Use the "
                    "multi-casualty option or a larger preset."
                )

        if st.session_state.quantum:
            render_quantum(st.session_state.quantum)

        if st.session_state.prepared and st.session_state.plans:
            st.divider()
            st.subheader("Live simulation")
            st.caption(
                "The simulation starts automatically after Dispatch. The map "
                "updates once per second; use the controls to pause or step."
            )
            engine = st.session_state.sim
            if engine is None:
                if st.button("Start simulation", type="primary", width="stretch"):
                    st.session_state.sim = SimulationEngine(
                        prepared=st.session_state.prepared,
                        plans=st.session_state.plans,
                        start=st.session_state.plans_when or when,
                    )
                    st.session_state.sim_playing = True
                    st.session_state.sim_last_tick = 0.0
                    st.rerun()
            else:
                render_simulation(
                    engine, st.session_state.plans_when or when
                )

    st.divider()
    st.caption(
        "Data provenance: hospital locations and station coordinates are real OSM "
        "features; specialties, offload waits, vehicles, incidents, traffic "
        "profiles, and clearance limits are curated or synthetic demo values. "
        "OSM data © OpenStreetMap contributors (ODbL)."
    )

    # Run the timer last so button clicks are handled before a tick can request
    # a full-app rerun. Only register the one-second timer while playing, so an
    # idle demo does not rerun a fragment every second.
    if st.session_state.get("sim_playing"):
        simulation_tick()


if __name__ == "__main__":
    main()
