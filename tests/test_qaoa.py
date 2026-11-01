from __future__ import annotations

from quantum.dispatch import best_hospital_for_cluster, prepare
from quantum.qaoa_solver import run_qaoa
from quantum.runtime import run_with_large_stack


def test_qaoa_returns_repaired_route(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    als = scenario.vehicle("ALS-1")
    hospital = best_hospital_for_cluster(prepared, als, scenario.incidents)
    result = run_qaoa(prepared, als, scenario.incidents, hospital, config, seed=3)
    assert not result.fallback
    assert result.repaired_feasibility == 1.0
    assert set(result.order_ids) == {incident.id for incident in scenario.incidents}
    assert 0.0 <= result.approximation_ratio <= 1.0
    assert result.quantum_plan.total_mission_min > 0
    assert result.classical_plan.total_mission_min > 0


def test_large_stack_helper_returns_value():
    assert run_with_large_stack(lambda value: value * 2, 21) == 42


def test_large_stack_helper_propagates_error():
    def boom():
        raise ValueError("boom")

    try:
        run_with_large_stack(boom)
    except ValueError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
