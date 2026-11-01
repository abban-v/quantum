from __future__ import annotations

from quantum.config import Config
from quantum.data.loader import load_hospitals, load_scenarios, load_vehicles


def test_package_imports():
    import quantum
    import quantum.dispatch
    import quantum.graph
    import quantum.nlp_parser
    import quantum.qaoa_solver
    import quantum.qubo
    import quantum.runtime
    import quantum.visualize

    assert quantum.__version__


def test_config_loads():
    cfg = Config.load()
    assert cfg.max_quantum_stops**2 <= cfg.max_qubits
    assert cfg.traffic_multiplier > 0


def test_curated_demo_data_loads():
    hospitals = load_hospitals()
    vehicles = load_vehicles()
    scenarios = load_scenarios()
    assert len(hospitals) >= 4
    assert len(vehicles) >= 4
    assert {scenario.id for scenario in scenarios} >= {"S1", "S2", "S3", "S4"}
    assert any(vehicle.kind == "ALS" for vehicle in vehicles)
    assert any(vehicle.kind == "BLS" for vehicle in vehicles)
