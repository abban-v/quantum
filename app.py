"""Q-EVR interactive dashboard.

Run with:
    uv run streamlit run app.py
"""

from __future__ import annotations

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
from quantum.scenarios import (
    build_custom_scenario,
    dispatch_scenario,
)
from quantum.visualize import (
    CLASSICAL_COLOR,
    QUANTUM_COLOR,
    add_hospitals,
    add_incidents,
    add_route,
    add_vehicles,
    base_map,
)

st.set_page_config(page_title="Q-EVR", page_icon="🚑", layout="wide")


@st.cache_resource(show_spinner="Loading Manhattan road graph…")
def load_world():
    cfg = Config.load()
    graph = fetch_graph(cfg)
    apply_clearance_overrides(graph)
    return cfg, graph


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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_plan_table(plans: list[RoutePlan]) -> None:
    frame = pd.DataFrame(
        [
            {
                "Vehicle": plan.vehicle_id,
                "Incidents": ", ".join(plan.incident_ids),
                "Hospital": plan.hospital_id,
                "Transit (min)": round(plan.total_transit_s / 60.0, 1),
                "Offload (min)": round(plan.offload_min, 1),
                "Total (min)": round(plan.total_mission_min, 1),
                "Equipment OK": plan.equipment_match,
                "Specialty OK": plan.specialty_match,
                "Clearance OK": plan.clearance_ok,
            }
            for plan in plans
        ]
    )
    st.dataframe(frame, hide_index=True, use_container_width=True)


def render_quantum(result: QAOAResult) -> None:
    st.subheader("Quantum comparison")
    if result.fallback:
        st.warning("Quantum run fell back to the classical route. " + " ".join(result.notes))
    cols = st.columns(4)
    cols[0].metric("Approx. ratio", f"{result.approximation_ratio:.2f}")
    cols[1].metric("Raw feasibility", f"{result.raw_feasibility:.1%}")
    cols[2].metric("Repaired feasibility", f"{result.repaired_feasibility:.0%}")
    cols[3].metric("Runtime", f"{result.runtime_s:.2f} s")
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
                    "Objective (min)": round(result.classical_plan.objective_score_s / 60.0, 1),
                    "Mission (min)": round(result.classical_plan.total_mission_min, 1),
                },
                {
                    "Route": "Quantum (repaired)",
                    "Order": " → ".join(result.quantum_plan.incident_ids),
                    "Objective (min)": round(result.quantum_plan.objective_score_s / 60.0, 1),
                    "Mission (min)": round(result.quantum_plan.total_mission_min, 1),
                },
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    for note in result.notes:
        st.caption(note)


def main() -> None:
    init_state()
    st.title("🚑 Q-EVR — Quantum-Assisted Emergency Vehicle Routing")
    st.caption(
        "Manhattan demo · OpenStreetMap geometry · simulated offload times · "
        "local Qiskit Aer · all data is labeled real / curated / synthetic."
    )

    try:
        cfg, graph = load_world()
        scenarios = {scenario.id: scenario for scenario in load_scenarios()}
        hospitals = load_hospitals()
        vehicles = load_vehicles()
    except (DataFetchError, DataValidationError) as exc:
        st.error(f"Could not load data: {exc}")
        st.stop()

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
            st.session_state.click = (selected.incidents[0].lat, selected.incidents[0].lon)
            st.session_state.plans = []
            st.session_state.quantum = None
            st.session_state.triage = None

        use_llm = st.checkbox("Use local Ollama fallback", value=False)
        multi = st.checkbox("Multi-casualty custom (3 patients)", value=False)
        if st.button("Reset to preset"):
            st.session_state.custom = False
            st.session_state.text = selected.incidents[0].description
            st.session_state.click = (selected.incidents[0].lat, selected.incidents[0].lon)
            st.session_state.plans = []
            st.session_state.quantum = None
            st.session_state.triage = None
        st.divider()
        st.markdown(
            "**How to use**\n"
            "1. Pick a preset, or click the map to place an incident.\n"
            "2. Describe the emergency in plain text.\n"
            "3. Press **Dispatch** for the classical route.\n"
            "4. Press **Run quantum** for the QAOA overlay."
        )
        st.caption("Offload waits are simulated demo values, not live ED data.")

    if st.session_state.custom and st.session_state.click:
        st.info(
            f"Custom incident at {st.session_state.click[0]:.5f}, "
            f"{st.session_state.click[1]:.5f}"
        )

    left, right = st.columns([2.1, 1.0], gap="large")

    with left:
        map_obj = base_map()
        add_hospitals(map_obj, hospitals)
        add_vehicles(map_obj, vehicles)
        active_incidents = (
            st.session_state.scenario.incidents
            if st.session_state.custom and st.session_state.scenario
            else selected.incidents
        )
        add_incidents(map_obj, active_incidents)
        if st.session_state.custom and st.session_state.click:
            lat, lon = st.session_state.click
            folium.Marker(
                location=[lat, lon],
                tooltip="Selected incident point",
                icon=folium.Icon(color="orange", icon="screenshot"),
            ).add_to(map_obj)
        for plan in st.session_state.plans:
            add_route(
                map_obj,
                plan,
                color=CLASSICAL_COLOR,
                label=f"Classical · {plan.vehicle_id}",
                layer_name=f"Classical · {plan.vehicle_id}",
            )
        if st.session_state.quantum and not st.session_state.quantum.fallback:
            add_route(
                map_obj,
                st.session_state.quantum.quantum_plan,
                color=QUANTUM_COLOR,
                label="Quantum (repaired)",
                layer_name="Quantum (repaired)",
            )
        folium.LayerControl(collapsed=False).add_to(map_obj)
        map_state = st_folium(
            map_obj,
            height=580,
            use_container_width=True,
            returned_objects=["last_clicked"],
            key="qevr_map",
        )
        clicked = map_state.get("last_clicked") if map_state else None
        if clicked:
            key = f"{clicked['lat']:.6f},{clicked['lng']:.6f}"
            if key != st.session_state.last_click_key:
                st.session_state.last_click_key = key
                st.session_state.click = (clicked["lat"], clicked["lng"])
                st.session_state.custom = True
                st.session_state.plans = []
                st.session_state.quantum = None
                st.session_state.scenario = None

    with right:
        st.subheader("Emergency input")
        st.text_area(
            "Describe the emergency",
            key="text",
            height=110,
            placeholder="e.g. Snake bite with difficulty breathing…",
        )
        if st.button("Dispatch", type="primary", use_container_width=True):
            try:
                if st.session_state.custom:
                    if not st.session_state.click:
                        raise DispatchError("Click the map to place the incident first.")
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
                        scenario.incidents[0].equipment_required = triage.equipment_required
                        scenario.incidents[0].specialty_required = triage.specialty_required
                prepared, plans = dispatch_scenario(scenario, graph, cfg)
                st.session_state.scenario = scenario
                st.session_state.prepared = prepared
                st.session_state.plans = plans
                st.session_state.triage = triage
                st.session_state.quantum = None
                st.session_state.notice = ""
            except (DispatchError, ValueError) as exc:
                st.error(str(exc))

        if st.session_state.triage:
            triage = st.session_state.triage
            st.markdown("**Parsed triage**")
            st.caption(
                f"λ={triage.severity:.0f} · equipment={triage.equipment_required} · "
                f"specialty={triage.specialty_required or 'none'} · "
                f"confidence={triage.confidence:.0%} ({triage.parser})"
            )
            if triage.needs_confirmation:
                st.warning("Low confidence — confirm the details before dispatch.")
            for note in triage.notes:
                st.caption(note)

        if st.session_state.plans:
            st.markdown("**Dispatch plan**")
            render_plan_table(st.session_state.plans)
            plan = st.session_state.plans[0]
            if len(plan.incident_ids) >= 2:
                if st.button("Run quantum", use_container_width=True):
                    try:
                        scenario = st.session_state.scenario
                        prepared = st.session_state.prepared
                        vehicle = scenario.vehicle(plan.vehicle_id)
                        incidents = [
                            i for i in scenario.incidents if i.id in set(plan.incident_ids)
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
                            )
                        st.session_state.quantum = result
                    except Exception as exc:  # keep the demo alive
                        st.error(f"Quantum run failed: {exc}")
            else:
                st.caption("Quantum ordering needs at least two stops. Use the multi-casualty option.")

        if st.session_state.quantum:
            render_quantum(st.session_state.quantum)

    st.divider()
    st.caption(
        "Data provenance: hospital locations and station coordinates are real OSM "
        "features; specialties, offload waits, vehicles, incidents, and clearance "
        "limits are curated or synthetic demo values. OSM data © OpenStreetMap "
        "contributors (ODbL)."
    )


if __name__ == "__main__":
    main()
