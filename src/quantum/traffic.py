"""Synthetic time-of-day traffic for the demo.

The profiles are hand-set multipliers on free-flow travel time. They are
**synthetic** and exist to make the day/time control and the traffic layer
meaningful; they are not live traffic data. Every value is labelled by
``TrafficModel.source``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import networkx as nx

CongestionClass = str

CLASS_COLORS = {
    "free": "#2b8cbe",      # blue: fast
    "moderate": "#f0c808",  # yellow: slowing
    "heavy": "#e34a33",     # red: heavy
    "blocked": "#7f0000",   # dark red: effectively stopped
}

#: Hourly delay factors (multiplier on free-flow travel time), index 0..23.
_WEEKDAY = {
    "motorway": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.25, 1.55, 1.75, 1.55,
        1.35, 1.30, 1.35, 1.40, 1.50, 1.65, 1.85, 1.95, 1.70, 1.40,
        1.20, 1.10, 1.05, 1.00,
    ],
    "primary": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.30, 1.70, 1.95, 1.70,
        1.45, 1.35, 1.40, 1.45, 1.55, 1.75, 2.00, 2.10, 1.80, 1.45,
        1.25, 1.10, 1.05, 1.00,
    ],
    "secondary": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.25, 1.55, 1.75, 1.55,
        1.35, 1.30, 1.35, 1.40, 1.50, 1.65, 1.85, 1.95, 1.70, 1.40,
        1.20, 1.10, 1.05, 1.00,
    ],
    "residential": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.10, 1.20, 1.25, 1.15,
        1.10, 1.05, 1.05, 1.05, 1.10, 1.15, 1.25, 1.30, 1.20, 1.10,
        1.05, 1.00, 1.00, 1.00,
    ],
}

_WEEKEND = {
    "motorway": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.10, 1.20, 1.30,
        1.35, 1.40, 1.45, 1.50, 1.55, 1.60, 1.65, 1.70, 1.55, 1.40,
        1.25, 1.15, 1.05, 1.00,
    ],
    "primary": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.15, 1.30, 1.45,
        1.55, 1.60, 1.65, 1.70, 1.75, 1.80, 1.85, 1.90, 1.75, 1.55,
        1.35, 1.20, 1.10, 1.00,
    ],
    "secondary": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.10, 1.20, 1.30,
        1.40, 1.45, 1.50, 1.55, 1.60, 1.65, 1.70, 1.75, 1.60, 1.45,
        1.25, 1.15, 1.05, 1.00,
    ],
    "residential": [
        1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.10, 1.15,
        1.20, 1.20, 1.20, 1.20, 1.20, 1.20, 1.25, 1.25, 1.15, 1.10,
        1.05, 1.00, 1.00, 1.00,
    ],
}


def _road_class(edge: dict) -> str:
    raw = str(edge.get("highway") or "residential")
    # OSM tags can be comma-joined lists after the parquet export.
    first = raw.split(",")[0].strip().lower()
    if first.endswith("_link"):
        first = first[:-5]
    if first in {"motorway", "trunk"}:
        return "motorway"
    if first in {"primary", "primary_link"}:
        return "primary"
    if first in {"secondary", "secondary_link", "tertiary", "tertiary_link"}:
        return "secondary"
    return "residential"


@dataclass
class TrafficModel:
    """Time-of-day multipliers plus manual per-street overrides."""

    overrides: dict[tuple[int, int, int], float] = field(default_factory=dict)
    source: str = "synthetic"

    def delay_factor(
        self,
        u: int,
        v: int,
        key: int,
        edge: dict,
        when: datetime,
    ) -> float:
        override = self.overrides.get((int(u), int(v), int(key)))
        if override is not None:
            return override
        table = _WEEKDAY if when.weekday() < 5 else _WEEKEND
        values = table.get(_road_class(edge), table["residential"])
        return float(values[when.hour % 24])

    def set_override(self, u: int, v: int, key: int, factor: float) -> None:
        if factor <= 0:
            raise ValueError("traffic factor must be > 0")
        self.overrides[(int(u), int(v), int(key))] = float(factor)

    def clear_override(self, u: int, v: int, key: int) -> None:
        self.overrides.pop((int(u), int(v), int(key)), None)

    def clear_all(self) -> None:
        self.overrides.clear()

    @staticmethod
    def congestion_class(delay_factor: float) -> CongestionClass:
        if delay_factor <= 1.18:
            return "free"
        if delay_factor <= 1.82:
            return "moderate"
        if delay_factor <= 3.33:
            return "heavy"
        return "blocked"

    @classmethod
    def color(cls, delay_factor: float) -> str:
        return CLASS_COLORS[cls.congestion_class(delay_factor)]

    @staticmethod
    def label(when: datetime) -> str:
        day = "Weekday" if when.weekday() < 5 else "Weekend"
        hour = when.hour
        if when.weekday() < 5 and 7 <= hour < 10:
            peak = "AM peak"
        elif when.weekday() < 5 and 16 <= hour < 19:
            peak = "PM peak"
        elif 0 <= hour < 6:
            peak = "overnight"
        else:
            peak = "off-peak"
        return f"{day} {when:%H:%M} · {peak}"


def edge_coords(
    graph: nx.MultiDiGraph, u: int, v: int, key: int | None = None
) -> list[tuple[float, float]]:
    """Return (lat, lon) pairs for one edge, using geometry when available."""
    data = graph.get_edge_data(u, v) or {}
    if key is not None and key in data:
        data = {key: data[key]}
    for payload in data.values():
        geometry = payload.get("geometry")
        coords = getattr(geometry, "coords", None)
        if coords:
            return [(float(y), float(x)) for x, y in coords]
    return [
        (float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])),
        (float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])),
    ]


def edge_name(edge: dict) -> str:
    name = edge.get("name")
    if isinstance(name, (list, tuple)):
        name = ", ".join(str(item) for item in name)
    if name:
        return str(name)
    return str(edge.get("highway") or "unnamed road").replace("_", " ").title()


def _project(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """Local metres around a reference latitude."""
    return lon * 111_320.0 * math.cos(math.radians(lat0)), lat * 111_320.0


def _point_segment_distance_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    lat0: float,
) -> float:
    px, py = _project(point[0], point[1], lat0)
    ax, ay = _project(start[0], start[1], lat0)
    bx, by = _project(end[0], end[1], lat0)
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def nearest_edge(
    graph: nx.MultiDiGraph,
    lat: float,
    lon: float,
    max_distance_m: float = 60.0,
) -> tuple[int, int, int, dict, float] | None:
    """Find the closest directed edge to a map click.

    Returns ``(u, v, key, data, distance_m)`` or ``None`` when the click is
    farther than ``max_distance_m`` from every edge.
    """
    best: tuple[float, int, int, int, dict] | None = None
    for u, v, key, data in graph.edges(keys=True, data=True):
        coords = edge_coords(graph, u, v, key)
        if len(coords) < 2:
            continue
        distance = min(
            _point_segment_distance_m((lat, lon), coords[i], coords[i + 1], lat)
            for i in range(len(coords) - 1)
        )
        if best is None or distance < best[0]:
            best = (distance, int(u), int(v), int(key), data)
    if best is None or best[0] > max_distance_m:
        return None
    return best[1], best[2], best[3], best[4], best[0]
