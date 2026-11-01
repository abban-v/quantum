from __future__ import annotations

import pytest

from quantum.dispatch import DispatchError, run_scenario
from quantum.nlp_parser import parse_rules
from quantum.scenarios import (
    build_custom_scenario,
    dispatch_scenario,
    find_cluster_vehicle,
)


def test_find_cluster_vehicle_picks_capacity_and_equipment(scenario):
    vehicle = find_cluster_vehicle(scenario, scenario.incidents)
    assert vehicle is not None
    assert vehicle.id == "ALS-1"
    assert vehicle.capacity >= len(scenario.incidents)


def test_find_cluster_vehicle_returns_none_when_equipment_missing(scenario):
    ventilator_incident = scenario.incidents[0]
    bls_only = scenario.model_copy(
        update={"vehicles": [scenario.vehicle("BLS-1")]}
    )
    assert find_cluster_vehicle(bls_only, [ventilator_incident]) is None


def test_build_custom_scenario_single(scenario):
    triage = parse_rules("snake bite with difficulty breathing")
    custom = build_custom_scenario(
        scenario, (40.751, -73.981), "snake bite with difficulty breathing", triage, False
    )
    assert custom.id == "CUSTOM"
    assert len(custom.incidents) == 1
    incident = custom.incidents[0]
    assert incident.severity == 50.0
    assert incident.equipment_required == "ventilator"
    assert incident.description.startswith("snake bite")


def test_build_custom_scenario_multi_adds_companions(scenario):
    triage = parse_rules("severe motor vehicle collision with massive trauma")
    custom = build_custom_scenario(
        scenario, (40.751, -73.981), "severe MVA", triage, True
    )
    assert len(custom.incidents) == 3
    assert custom.incidents[1].severity == pytest.approx(16.0)
    assert custom.incidents[2].severity == 5.0


def test_dispatch_scenario_clusters_when_one_vehicle_fits(grid_graph, scenario, config):
    prepared, plans = dispatch_scenario(scenario, grid_graph, config)
    assert len(plans) == 1
    assert set(plans[0].incident_ids) == {i.id for i in scenario.incidents}
    assert prepared.snap


def test_run_scenario_cluster_vehicle(grid_graph, scenario, config):
    result = run_scenario(scenario, grid_graph, config, cluster_vehicle="ALS-1")
    assert len(result.plans) == 1
    assert result.plans[0].vehicle_id == "ALS-1"


def test_run_scenario_unknown_vehicle(grid_graph, scenario, config):
    with pytest.raises(KeyError, match="Unknown vehicle"):
        run_scenario(scenario, grid_graph, config, cluster_vehicle="NOPE")
