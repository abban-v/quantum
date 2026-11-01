"""Shared deterministic fixtures for the unit tests (no network required)."""

from __future__ import annotations

import networkx as nx
import pytest

from quantum.config import Config
from quantum.problem import Hospital, Incident, Scenario, Vehicle


@pytest.fixture()
def config(tmp_path) -> Config:
    return Config(
        place="Synthetic",
        network_type="drive",
        graph_cache=tmp_path / "graph.graphml",
        edges_cache=tmp_path / "edges.parquet",
        traffic_multiplier=1.0,
        max_qubits=12,
        max_quantum_stops=3,
        qaoa_timeout_s=10.0,
        qaoa_maxiter=40,
        qaoa_shots=256,
        default_speed_kph=30.0,
    )


@pytest.fixture()
def grid_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    base_lat, base_lon = 40.750, -73.980
    step = 0.001
    for row in range(4):
        for col in range(4):
            node = row * 4 + col
            graph.add_node(node, x=base_lon + col * step, y=base_lat + row * step)
    for row in range(4):
        for col in range(4):
            node = row * 4 + col
            if col < 3:
                _add_edge(graph, node, node + 1)
                _add_edge(graph, node + 1, node)
            if row < 3:
                _add_edge(graph, node, node + 4)
                _add_edge(graph, node + 4, node)
    return graph


def _add_edge(graph: nx.MultiDiGraph, u: int, v: int, maxheight_m=None) -> None:
    graph.add_edge(
        u,
        v,
        key=0,
        length=100.0,
        speed_kph=30.0,
        travel_time=12.0,
        highway="residential",
        geometry=None,
        maxheight_m=maxheight_m,
        maxweight_kg=None,
    )


@pytest.fixture()
def scenario() -> Scenario:
    hospitals = [
        Hospital(id="H1", name="General", lat=40.750, lon=-73.980, specialties=["trauma"], offload_min=10),
        Hospital(id="H2", name="Burn", lat=40.751, lon=-73.979, specialties=["burn"], offload_min=20),
    ]
    vehicles = [
        Vehicle(
            id="ALS-1", kind="ALS", station_id="S1", lat=40.750, lon=-73.980,
            capacity=3, ventilator=True, height_m=3.4, weight_kg=5000,
        ),
        Vehicle(
            id="BLS-1", kind="BLS", station_id="S1", lat=40.750, lon=-73.980,
            capacity=1, ventilator=False, height_m=3.0, weight_kg=4000,
        ),
    ]
    incidents = [
        Incident(id="I1", lat=40.751, lon=-73.981, description="snake bite", severity=50, equipment_required="ventilator", specialty_required=None),
        Incident(id="I2", lat=40.752, lon=-73.982, description="chest pain", severity=20, equipment_required="ventilator", specialty_required=None),
        Incident(id="I3", lat=40.753, lon=-73.983, description="minor cut", severity=5, equipment_required="none", specialty_required=None),
    ]
    return Scenario(
        id="TEST",
        name="Synthetic test",
        incidents=incidents,
        vehicles=vehicles,
        hospitals=hospitals,
        traffic_multiplier=1.0,
        seed=3,
    )
