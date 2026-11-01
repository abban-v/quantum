from __future__ import annotations

import pytest

from quantum.config import Config, ConfigError


def test_load_config_roundtrip(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
place: Test
network_type: drive
graph_cache: data/cache/x.graphml
edges_cache: data/curated/x.parquet
traffic_multiplier: 1.2
max_qubits: 12
max_quantum_stops: 3
qaoa_timeout_s: 5
qaoa_maxiter: 20
qaoa_shots: 128
default_speed_kph: 30
"""
    )
    cfg = Config.load(path)
    assert cfg.place == "Test"
    assert cfg.max_quantum_stops**2 <= cfg.max_qubits


def test_missing_key_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("place: Test\n")
    with pytest.raises(ConfigError, match="Missing config keys"):
        Config.load(path)


def test_qubit_budget_validation(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
place: Test
network_type: drive
graph_cache: data/cache/x.graphml
edges_cache: data/curated/x.parquet
traffic_multiplier: 1.0
max_qubits: 4
max_quantum_stops: 3
qaoa_timeout_s: 5
qaoa_maxiter: 20
qaoa_shots: 128
default_speed_kph: 30
"""
    )
    with pytest.raises(ConfigError, match="exceeds max_qubits"):
        Config.load(path)
