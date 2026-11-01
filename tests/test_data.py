from __future__ import annotations

import json

import pandas as pd
import pytest

from quantum.config import Config
from quantum.data.fetch import fetch_graph
from quantum.data.loader import (
    DataValidationError,
    apply_clearance_overrides,
    largest_strongly_connected_component,
    parse_height_m,
    parse_weight_kg,
    snap_targets_to_graph,
    validate_graph,
)


def test_largest_scc_drops_disconnected_nodes(grid_graph):
    grid_graph.add_node(99, x=-73.9, y=40.8)
    pruned = largest_strongly_connected_component(grid_graph)
    assert 99 not in pruned
    assert pruned.number_of_nodes() == 16
    assert pruned.graph["qevr_dropped_nodes"] == 1


def test_largest_scc_is_noop_when_connected(grid_graph):
    assert largest_strongly_connected_component(grid_graph) is grid_graph


def test_fetch_graph_prunes_cached_graph(tmp_path, monkeypatch, grid_graph):
    grid_graph.add_node(99, x=-73.9, y=40.8)
    cache = tmp_path / "graph.graphml"
    cache.write_text("placeholder")
    cfg = Config(
        place="Synthetic",
        network_type="drive",
        graph_cache=cache,
        edges_cache=tmp_path / "edges.parquet",
        traffic_multiplier=1.0,
        max_qubits=12,
        max_quantum_stops=3,
        qaoa_timeout_s=5.0,
        qaoa_maxiter=20,
        qaoa_shots=64,
        default_speed_kph=30.0,
    )
    monkeypatch.setattr(
        "quantum.data.fetch.ox.load_graphml", lambda path: grid_graph
    )
    graph = fetch_graph(cfg)
    assert 99 not in graph
    assert graph.number_of_nodes() == 16


def test_validate_graph_rejects_empty_graph():
    import networkx as nx

    with pytest.raises(DataValidationError, match="no nodes"):
        validate_graph(nx.MultiDiGraph())


def test_apply_clearance_overrides_marks_source(grid_graph, tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps(
            {
                "overrides": [
                    {"u": 0, "v": 1, "maxheight_m": 3.0, "reason": "test"},
                    {"u": 1, "v": 2, "maxweight_kg": 3000.0, "reason": "test"},
                ]
            }
        )
    )
    assert apply_clearance_overrides(grid_graph, path) == 2
    assert grid_graph[0][1][0]["maxheight_m"] == 3.0
    assert grid_graph[0][1][0]["clearance_source"] == "synthetic"
    assert grid_graph[1][2][0]["maxweight_kg"] == 3000.0


def test_apply_clearance_overrides_rejects_missing_edge(grid_graph, tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({"overrides": [{"u": 0, "v": 99, "maxheight_m": 3.0}]}))
    with pytest.raises(DataValidationError, match="not present"):
        apply_clearance_overrides(grid_graph, path)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3.5", 3.5),
        ("12'6\"", 3.81),
        ("12 ft 6 in", 3.81),
        (None, None),
        ("", None),
        ("no limit", None),
    ],
)
def test_parse_height(raw, expected):
    assert parse_height_m(raw) == (pytest.approx(expected) if expected else expected)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3500", 3500.0),
        ("3.5 t", 3500.0),
        ("7700 lb", 3492.66),
        (None, None),
        ("", None),
    ],
)
def test_parse_weight(raw, expected):
    assert parse_weight_kg(raw) == (pytest.approx(expected, rel=1e-4) if expected else expected)


def test_snap_targets_rejects_far_points(grid_graph):
    with pytest.raises(DataValidationError, match="too far"):
        snap_targets_to_graph(grid_graph, [("far", 41.0, -74.0)], max_distance_m=100)


def test_snap_targets_returns_nearest_node(grid_graph):
    snapped = snap_targets_to_graph(grid_graph, [("near", 40.7501, -73.9799)])
    assert snapped["near"] == 0


def test_exported_edge_table_schema():
    config = Config.load()
    if not config.edges_cache.exists():
        pytest.skip("edge table has not been prepared")
    frame = pd.read_parquet(config.edges_cache)
    required = {
        "u", "v", "key", "length_m", "speed_kph", "travel_time_s",
        "highway", "bridge", "tunnel", "name", "maxheight_m", "maxweight_kg",
    }
    assert required.issubset(frame.columns)
    assert len(frame) > 1000
    assert (frame["length_m"] > 0).all()
    assert (frame["travel_time_s"] > 0).all()
