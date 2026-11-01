from __future__ import annotations

from datetime import datetime

import pytest

from quantum.traffic import TrafficModel
from quantum.graph import (
    NoPathError,
    build_routing_graph,
    path_coords,
    prune_for_vehicle,
    route_metrics,
    shortest_path,
    travel_time_s,
)
from quantum.problem import Vehicle


def test_travel_time_uses_multiplier():
    assert travel_time_s({"travel_time": 10.0}, 1.5) == pytest.approx(15.0)
    assert travel_time_s({"length": 100.0, "speed_kph": 36.0}, 1.0) == pytest.approx(10.0)
    assert travel_time_s({}, 1.0) is None


def test_time_of_day_traffic_changes_edge_cost(grid_graph):
    model = TrafficModel()
    peak = build_routing_graph(
        grid_graph, 1.0, traffic=model, when=datetime(2026, 11, 3, 8, 30)
    )
    night = build_routing_graph(
        grid_graph, 1.0, traffic=model, when=datetime(2026, 11, 3, 3, 30)
    )
    assert peak[0][1]["travel_time_s"] > night[0][1]["travel_time_s"]
    assert peak[0][1]["delay_factor"] > night[0][1]["delay_factor"]


def test_routing_and_metrics(grid_graph):
    routing = build_routing_graph(grid_graph, 1.0)
    path = shortest_path(routing, 0, 15)
    assert path[0] == 0 and path[-1] == 15
    time_s, length_m = route_metrics(routing, path)
    assert time_s > 0 and length_m > 0
    coords = path_coords(routing, path)
    assert len(coords) >= 2


def test_pruning_blocks_tall_vehicle(grid_graph):
    grid_graph[0][1][0]["maxheight_m"] = 3.0
    routing = build_routing_graph(grid_graph, 1.0)
    tall = Vehicle(id="T", kind="ALS", station_id="S", lat=40.75, lon=-73.98, height_m=3.4, ventilator=True)
    short = Vehicle(id="S", kind="BLS", station_id="S", lat=40.75, lon=-73.98, height_m=2.8)
    assert not prune_for_vehicle(routing, tall).has_edge(0, 1)
    assert prune_for_vehicle(routing, short).has_edge(0, 1)


def test_no_path_raises(grid_graph):
    routing = build_routing_graph(grid_graph, 1.0)
    routing.remove_node(15)
    with pytest.raises(NoPathError):
        shortest_path(routing, 0, 15)
