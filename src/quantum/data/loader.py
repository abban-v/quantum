"""Load curated demo data and apply physical restrictions to the graph."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, TypeVar

import networkx as nx
from pydantic import BaseModel, ValidationError

from quantum.config import CURATED_DIR
from quantum.problem import Hospital, Incident, Scenario, Vehicle

T = TypeVar("T", bound=BaseModel)


class DataValidationError(RuntimeError):
    """Raised when curated data is missing or malformed."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise DataValidationError(f"Data file not found: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise DataValidationError(f"Invalid JSON in {path}: {exc}") from exc


def _load_list(path: Path, model: type[T], key: str) -> list[T]:
    raw = _read_json(path)
    if isinstance(raw, dict):
        raw = raw.get(key)
    if not isinstance(raw, list):
        raise DataValidationError(f"{path} must contain a list under {key!r}")
    try:
        return [model.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise DataValidationError(f"Invalid records in {path}:\n{exc}") from exc


def load_hospitals(path: Path | None = None) -> list[Hospital]:
    return _load_list(path or CURATED_DIR / "hospitals.json", Hospital, "hospitals")


def load_vehicles(path: Path | None = None) -> list[Vehicle]:
    return _load_list(path or CURATED_DIR / "fleet.json", Vehicle, "vehicles")


def load_scenarios(path: Path | None = None) -> list[Scenario]:
    path = path or CURATED_DIR / "scenarios.json"
    scenarios = _load_list(path, Scenario, "scenarios")
    hospitals = load_hospitals()
    vehicles = load_vehicles()
    for scenario in scenarios:
        if not scenario.hospitals:
            scenario.hospitals = list(hospitals)
        if not scenario.vehicles:
            scenario.vehicles = list(vehicles)
        if not scenario.vehicles:
            raise DataValidationError(f"Scenario {scenario.id} has no vehicles")
        if not scenario.hospitals:
            raise DataValidationError(f"Scenario {scenario.id} has no hospitals")
    return scenarios


def load_incidents(path: Path | None = None) -> list[Incident]:
    return _load_list(path or CURATED_DIR / "incidents.json", Incident, "incidents")


def apply_clearance_overrides(
    graph: nx.MultiDiGraph, path: Path | None = None
) -> int:
    """Attach demo clearance/weight limits to specific edges.

    Returns the number of directed edges modified. Missing edges are reported
    instead of silently ignored.
    """
    path = path or CURATED_DIR / "clearance_overrides.json"
    raw = _read_json(path)
    if isinstance(raw, dict):
        raw = raw.get("overrides", [])
    if not isinstance(raw, list):
        raise DataValidationError(f"{path} must contain a list of overrides")

    modified = 0
    missing: list[str] = []
    for item in raw:
        try:
            u, v = int(item["u"]), int(item["v"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataValidationError(f"Override needs integer u/v: {item}") from exc
        if not graph.has_edge(u, v):
            missing.append(f"{u}->{v}")
            continue
        data = graph.get_edge_data(u, v) or {}
        for key in data:
            if item.get("maxheight_m") is not None:
                data[key]["maxheight_m"] = float(item["maxheight_m"])
            if item.get("maxweight_kg") is not None:
                data[key]["maxweight_kg"] = float(item["maxweight_kg"])
            data[key]["clearance_source"] = "synthetic"
            data[key]["clearance_reason"] = str(item.get("reason", "demo override"))
        modified += 1

    if missing:
        raise DataValidationError(
            "Clearance overrides reference edges not present in the graph: "
            + ", ".join(missing[:5])
        )
    return modified


_HEIGHT_FT_IN = re.compile(r"(?P<ft>\d+(?:\.\d+)?)\s*(?:'|ft|feet)\s*(?:(?P<in>\d+(?:\.\d+)?)\s*(?:\"|in|inch|inches)?)?", re.I)
_HEIGHT_M = re.compile(r"(?P<m>\d+(?:\.\d+)?)\s*(?:m|meter|metre|meters|metres)?", re.I)
_WEIGHT = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kg|kgs|t|ton|tons|lb|lbs|pound|pounds|st)?", re.I)


def parse_height_m(value: Any) -> float | None:
    """Parse OSM-style height tags into metres. Returns None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).strip().lower()
    if not text:
        return None
    match = _HEIGHT_FT_IN.search(text)
    if match and ("'" in text or "ft" in text or "feet" in text):
        feet = float(match.group("ft"))
        inches = float(match.group("in") or 0.0)
        return round(feet * 0.3048 + inches * 0.0254, 3)
    match = _HEIGHT_M.search(text)
    if match:
        metres = float(match.group("m"))
        return metres if metres > 0 else None
    return None


def parse_weight_kg(value: Any) -> float | None:
    """Parse OSM-style weight tags into kilograms. Returns None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).strip().lower()
    if not text:
        return None
    match = _WEIGHT.search(text)
    if not match:
        return None
    amount = float(match.group("value"))
    unit = (match.group("unit") or "kg").lower()
    if unit in {"t", "ton", "tons"}:
        return amount * 1000.0
    if unit in {"lb", "lbs", "pound", "pounds"}:
        return amount * 0.45359237
    if unit == "st":
        return amount * 907.18474
    return amount


def validate_graph(graph: nx.MultiDiGraph) -> dict[str, int]:
    """Fail fast if the cached graph is structurally unusable."""
    if graph.number_of_nodes() == 0:
        raise DataValidationError("Graph has no nodes")
    if graph.number_of_edges() == 0:
        raise DataValidationError("Graph has no edges")
    missing_xy = [n for n, d in graph.nodes(data=True) if "x" not in d or "y" not in d]
    if missing_xy:
        raise DataValidationError(f"{len(missing_xy)} nodes are missing x/y coordinates")
    missing_length = 0
    for _, _, data in graph.edges(data=True):
        if "length" not in data or float(data["length"]) <= 0:
            missing_length += 1
    if missing_length:
        raise DataValidationError(f"{missing_length} edges have no positive length")
    return {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}


def snap_targets_to_graph(
    graph: nx.MultiDiGraph,
    points: Iterable[tuple[str, float, float]],
    max_distance_m: float = 300.0,
) -> dict[str, int]:
    """Return nearest graph node per target; raise if any target is too far."""
    import math

    import numpy as np
    from scipy.spatial import cKDTree

    nodes = list(graph.nodes)
    if not nodes:
        raise DataValidationError("Cannot snap targets to an empty graph")
    coords = np.array(
        [[float(graph.nodes[n]["y"]), float(graph.nodes[n]["x"])] for n in nodes]
    )
    tree = cKDTree(coords)

    snapped: dict[str, int] = {}
    too_far: list[str] = []
    for label, lat, lon in points:
        _, index = tree.query([lat, lon])
        node_lat, node_lon = coords[index]
        dy = (node_lat - lat) * 111_320.0
        dx = (node_lon - lon) * 111_320.0 * math.cos(math.radians(lat))
        distance = (dx * dx + dy * dy) ** 0.5
        if distance > max_distance_m:
            too_far.append(f"{label} ({distance:.0f} m)")
        snapped[label] = int(nodes[index])
    if too_far:
        raise DataValidationError(
            "Targets too far from the road graph: " + ", ".join(too_far)
        )
    return snapped
