"""Graph preparation, physical pruning, and shortest-path routing."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import networkx as nx

from quantum.problem import Vehicle
from quantum.traffic import TrafficModel


class NoPathError(RuntimeError):
    """Raised when no physically passable route exists."""


def travel_time_s(edge: dict[str, Any], traffic_multiplier: float = 1.0) -> float | None:
    """Edge travel time in seconds, including a traffic multiplier."""
    if traffic_multiplier <= 0:
        raise ValueError("traffic_multiplier must be > 0")
    raw = edge.get("travel_time")
    if raw is not None:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value * traffic_multiplier
    length = edge.get("length")
    speed = edge.get("speed_kph")
    if length is None or speed is None:
        return None
    try:
        length_m, speed_kph = float(length), float(speed)
    except (TypeError, ValueError):
        return None
    if length_m <= 0 or speed_kph <= 0:
        return None
    return (length_m / (speed_kph / 3.6)) * traffic_multiplier


def build_routing_graph(
    graph: nx.MultiDiGraph,
    traffic_multiplier: float = 1.0,
    traffic: TrafficModel | None = None,
    when: datetime | None = None,
) -> nx.DiGraph:
    """Collapse parallel edges to the fastest directed edge per node pair.

    When ``traffic`` and ``when`` are given, each edge uses its own time-of-day
    delay factor. Otherwise the legacy scalar ``traffic_multiplier`` applies to
    every edge, which keeps the existing tests and CLI behaviour intact.
    """
    routing = nx.DiGraph()
    routing.graph.update(graph.graph)
    routing.add_nodes_from(graph.nodes(data=True))
    for u, v, key, data in graph.edges(keys=True, data=True):
        factor = (
            traffic.delay_factor(u, v, key, data, when)
            if traffic is not None and when is not None
            else traffic_multiplier
        )
        cost = travel_time_s(data, factor)
        if cost is None:
            continue
        existing = routing.get_edge_data(u, v)
        if existing is not None and existing["travel_time_s"] <= cost:
            continue
        routing.add_edge(
            u,
            v,
            travel_time_s=cost,
            length_m=float(data.get("length", 0.0)),
            key=key,
            geometry=data.get("geometry"),
            highway=data.get("highway"),
            name=data.get("name"),
            maxheight_m=data.get("maxheight_m"),
            maxweight_kg=data.get("maxweight_kg"),
            delay_factor=float(factor),
            speed_kph=data.get("speed_kph"),
        )
    return routing


def prune_for_vehicle(routing: nx.DiGraph, vehicle: Vehicle) -> nx.DiGraph:
    """Remove edges the rig cannot physically pass.

    Missing clearance data is treated as passable; synthetic overrides and
    real NBI data are opt-in. This is documented in the UI.
    """
    pruned = routing.copy()
    blocked: list[tuple[int, int]] = []
    for u, v, data in pruned.edges(data=True):
        max_h = data.get("maxheight_m")
        max_w = data.get("maxweight_kg")
        if max_h is not None and vehicle.height_m > float(max_h):
            blocked.append((u, v))
            continue
        if max_w is not None and vehicle.weight_kg > float(max_w):
            blocked.append((u, v))
    pruned.remove_edges_from(blocked)
    return pruned


def shortest_path(routing: nx.DiGraph, source: int, target: int) -> list[int]:
    if source not in routing:
        raise NoPathError(f"Source node {source} is not in the routing graph")
    if target not in routing:
        raise NoPathError(f"Target node {target} is not in the routing graph")
    try:
        return nx.shortest_path(routing, source, target, weight="travel_time_s")
    except nx.NetworkXNoPath as exc:
        raise NoPathError(f"No passable route from {source} to {target}") from exc
    except nx.NodeNotFound as exc:
        raise NoPathError(str(exc)) from exc


def route_metrics(routing: nx.DiGraph, path: list[int]) -> tuple[float, float]:
    """Return (travel_time_s, length_m) for a node path."""
    if len(path) < 2:
        return 0.0, 0.0
    total_time = 0.0
    total_length = 0.0
    for u, v in zip(path, path[1:]):
        data = routing[u][v]
        total_time += float(data["travel_time_s"])
        total_length += float(data["length_m"])
    return total_time, total_length


def path_coords(routing: nx.DiGraph, path: list[int]) -> list[tuple[float, float]]:
    """Convert a node path into (lat, lon) pairs using edge geometry."""
    if not path:
        return []
    coords: list[tuple[float, float]] = []
    for u, v in zip(path, path[1:]):
        data = routing[u][v]
        geometry = data.get("geometry")
        segment = _geometry_coords(geometry)
        if segment is None:
            segment = [
                (routing.nodes[u]["y"], routing.nodes[u]["x"]),
                (routing.nodes[v]["y"], routing.nodes[v]["x"]),
            ]
        if coords and _close(coords[-1], segment[0]):
            coords.extend(segment[1:])
        else:
            coords.extend(segment)
    return coords


def _geometry_coords(geometry: Any) -> list[tuple[float, float]] | None:
    if geometry is None:
        return None
    coords = getattr(geometry, "coords", None)
    if coords is None:
        return None
    return [(float(y), float(x)) for x, y in coords]


def _close(a: tuple[float, float], b: tuple[float, float], eps: float = 1e-9) -> bool:
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps
