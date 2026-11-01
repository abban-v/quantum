from __future__ import annotations

from quantum.dispatch import assign, cluster_plan, prepare


def test_prepare_snaps_every_target(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    for item in scenario.hospitals + scenario.vehicles + scenario.incidents:
        assert item.id in prepared.snap


def test_assign_respects_equipment(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    result = assign(prepared)
    assert result.plans
    for plan in result.plans:
        assert plan.equipment_match
        assert plan.clearance_ok
        vehicle = scenario.vehicle(plan.vehicle_id)
        for incident_id in plan.incident_ids:
            incident = next(i for i in scenario.incidents if i.id == incident_id)
            assert vehicle.can_carry(incident.equipment_required)


def test_cluster_plan_orders_all_incidents(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    als = scenario.vehicle("ALS-1")
    plan = cluster_plan(prepared, als, [i.id for i in scenario.incidents])
    assert set(plan.incident_ids) == {i.id for i in scenario.incidents}
    # vehicle -> incident -> hospital, once per patient
    assert len(plan.legs) == 2 * len(scenario.incidents)
    assert set(plan.patient_hospitals) == {i.id for i in scenario.incidents}
    assert plan.total_mission_min > 0
    assert plan.offload_min > 0
