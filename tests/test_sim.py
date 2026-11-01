from __future__ import annotations

from datetime import datetime

from quantum.dispatch import assign, cluster_plan, prepare
from quantum.sim import SimulationEngine


def _engine(grid_graph, scenario, config, incident_ids=None):
    prepared = prepare(scenario, grid_graph, config)
    vehicle = scenario.vehicle("ALS-1")
    ids = incident_ids or [incident.id for incident in scenario.incidents]
    plan = cluster_plan(prepared, vehicle, ids)
    return SimulationEngine(
        prepared=prepared,
        plans=[plan],
        start=datetime(2026, 11, 3, 8, 30),
    )


def _advance(engine, seconds, step=5.0):
    elapsed = 0.0
    while elapsed < seconds - 1e-9:
        engine.tick(step)
        elapsed += step


def test_engine_starts_heading_to_first_scene(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config, ["I1"])
    run = engine.runs["ALS-1"]
    assert run.status == "to_scene"
    assert run.leg_index == 0
    assert run.finished is False
    assert engine.finished is False
    # Patients start waiting with the hospital assigned by the plan.
    patient = engine.patients["I1"]
    assert patient.status == "waiting"
    assert patient.hospital_id == run.plan.patient_hospitals["I1"]


def test_tick_moves_vehicle_along_leg(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config, ["I1"])
    run = engine.runs["ALS-1"]
    start = run.position
    engine.tick(5.0)
    assert run.position != start
    assert 0.0 < run.leg_elapsed_s < run.plan.legs[0].travel_time_s
    # Live paths meet at the vehicle, so the map has no gap.
    assert run.remaining_coords[0] == run.position
    assert run.completed_path[-1] == run.position
    assert 0.0 < run.leg_fraction < 1.0


def test_full_run_picks_up_and_delivers_every_patient(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config)
    seen_statuses = set()
    for _ in range(2000):
        engine.tick(10.0)
        for patient in engine.patients.values():
            seen_statuses.add(patient.status)
        if engine.finished:
            break

    assert engine.finished is True
    assert seen_statuses == {"waiting", "onboard", "delivered"}
    metrics = engine.metrics()
    assert metrics["patients"] == len(scenario.incidents)
    assert metrics["delivered"] == len(scenario.incidents)
    assert metrics["waiting"] == 0
    assert metrics["onboard"] == 0
    assert metrics["idle"] == 1

    run = engine.runs["ALS-1"]
    assert run.finished is True
    assert run.onboard == []
    assert run.remaining_coords == []


def test_one_large_tick_finishes_plan(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config)
    engine.tick(24 * 3600.0)
    assert engine.finished is True
    assert all(p.status == "delivered" for p in engine.patients.values())


def test_patients_use_their_own_hospitals(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config)
    engine.tick(24 * 3600.0)
    delivered_events = [
        message
        for _, message in engine.events
        if "delivered" in message
    ]
    # Each plan leg alternates scene/hospital, so every patient appears once.
    assert len(delivered_events) == len(scenario.incidents)
    run = engine.runs["ALS-1"]
    for incident_id in run.plan.incident_ids:
        hospital_id = run.plan.patient_hospitals[incident_id]
        assert any(
            f"delivered {incident_id} to {hospital_id}" in message
            for message in delivered_events
        )


def test_reset_clears_previous_progress(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config, ["I1"])
    engine.tick(600.0)
    assert engine.now > engine.start
    assert engine.events

    engine.reset()
    assert engine.now == engine.start
    # Reset keeps only the fresh dispatch log for the initial leg.
    assert len(engine.events) == 1
    assert "en route to scene" in engine.events[0][1]
    assert engine.finished is False
    assert engine.runs["ALS-1"].leg_index == 0
    assert all(p.status == "waiting" for p in engine.patients.values())


def test_metrics_track_busy_and_idle(grid_graph, scenario, config):
    engine = _engine(grid_graph, scenario, config)
    assert engine.metrics()["busy"] == 1
    engine.tick(24 * 3600.0)
    metrics = engine.metrics()
    assert metrics["busy"] == 0
    assert metrics["idle"] == 1


def test_duplicate_vehicle_plans_are_chained(grid_graph, scenario, config):
    incidents = scenario.incidents[:2]
    vehicle = scenario.vehicle("ALS-1").model_copy(update={"capacity": 2})
    scenario = scenario.model_copy(
        update={"incidents": incidents, "vehicles": [vehicle]}
    )
    prepared = prepare(scenario, grid_graph, config)
    result = assign(prepared)
    assert len(result.plans) == 2
    assert {plan.vehicle_id for plan in result.plans} == {"ALS-1"}

    engine = SimulationEngine(
        prepared=prepared,
        plans=result.plans,
        start=datetime(2026, 11, 3, 8, 30),
    )
    assert list(engine.runs) == ["ALS-1"]
    run = engine.runs["ALS-1"]
    assert len(run.plan.incident_ids) == 2
    assert len(run.plan.legs) == 4

    engine.tick(24 * 3600.0)
    assert all(patient.status == "delivered" for patient in engine.patients.values())
