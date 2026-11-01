"""Folium map layers for the demo dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import folium
import networkx as nx
from folium.plugins import AntPath

from quantum.dispatch import RoutePlan
from quantum.problem import Hospital, Incident, Vehicle
from quantum.sim import VehicleRun
from quantum.traffic import (
    CLASS_COLORS,
    TrafficModel,
    edge_coords,
    edge_name,
)

MAP_CENTER = (40.7580, -73.9855)  # Times Square
MAP_ZOOM = 12

CLASSICAL_COLOR = "#1f77b4"
QUANTUM_COLOR = "#2ca02c"
INCIDENT_COLOR = "#d62728"
ALS_COLOR = "#d62728"
BLS_COLOR = "#1f77b4"
HOSPITAL_COLOR = "#d62728"
COMPLETED_COLOR = "#2b8cbe"
REMAINING_COLOR = "#f0c808"
POSITION_COLOR = "#111111"

VEHICLE_ICON_SIZE = (30, 30)
HOSPITAL_ICON_SIZE = (26, 26)

#: Road classes drawn on the offline basemap and traffic layer.
MAJOR_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
}


def region_bounds(
    graph: nx.MultiDiGraph, pad: float = 0.008
) -> tuple[float, float, float, float]:
    """Return ``(south, west, north, east)`` for the graph, with padding."""
    if graph.number_of_nodes() == 0:
        raise ValueError("Cannot compute bounds for an empty graph")
    lats = [float(data["y"]) for _, data in graph.nodes(data=True)]
    lons = [float(data["x"]) for _, data in graph.nodes(data=True)]
    return (
        min(lats) - pad,
        min(lons) - pad,
        max(lats) + pad,
        max(lons) + pad,
    )


def base_map(
    center: tuple[float, float] = MAP_CENTER,
    zoom: int = MAP_ZOOM,
    tiles: str = "osm",
    bounds: tuple[float, float, float, float] | None = None,
    graph: nx.MultiDiGraph | None = None,
    max_edges: int = 2500,
) -> folium.Map:
    """Build a map that cannot pan away from the demo region.

    ``tiles="osm"`` uses online OpenStreetMap tiles. ``tiles="vector"`` draws
    the cached road graph itself, so the map still has streets with no network.
    """
    options: dict[str, object] = {}
    if bounds is not None:
        south, west, north, east = bounds
        options.update(
            min_lat=south,
            max_lat=north,
            min_lon=west,
            max_lon=east,
            max_bounds=True,
        )

    if tiles == "vector":
        map_obj = folium.Map(
            location=list(center),
            zoom_start=zoom,
            tiles=None,
            control_scale=True,
            **options,
        )
        if graph is not None:
            add_road_basemap(map_obj, graph, max_edges=max_edges)
    else:
        map_obj = folium.Map(
            location=list(center),
            zoom_start=zoom,
            tiles="OpenStreetMap",
            control_scale=True,
            **options,
        )

    # Do not call ``fit_bounds`` here. Streamlit-Folium rebuilds this map on
    # every script run, and a fit-bounds call overrides the user's saved view
    # on each rebuild, which makes the map snap back to the full region.
    return map_obj


def _sampled_edges(
    graph: nx.MultiDiGraph,
    max_edges: int,
    major_only: bool = True,
) -> list[tuple[int, int, int, dict]]:
    """Pick a deterministic, evenly spaced subset of edges."""
    if max_edges <= 0:
        return []
    selected: list[tuple[int, int, int, dict]] = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        if major_only:
            road = str(data.get("highway") or "").split(",")[0].strip().lower()
            if road not in MAJOR_HIGHWAYS:
                continue
        selected.append((int(u), int(v), int(key), data))
    if len(selected) <= max_edges:
        return selected
    stride = len(selected) / max_edges
    return [selected[int(index * stride)] for index in range(max_edges)]


def _line_features(
    graph: nx.MultiDiGraph, edges: Iterable[tuple[int, int, int, dict]]
) -> list[dict]:
    features: list[dict] = []
    for u, v, key, _ in edges:
        coords = edge_coords(graph, u, v, key)
        if len(coords) < 2:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lat, lon in coords],
                },
            }
        )
    return features


def _add_geojson(
    map_obj: folium.Map,
    features: list[dict],
    color: str,
    weight: float,
    opacity: float,
    name: str,
) -> None:
    if not features:
        return
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        name=name,
        style_function=lambda _: {
            "color": color,
            "weight": weight,
            "opacity": opacity,
        },
        tooltip=name,
    ).add_to(map_obj)


def add_road_basemap(
    map_obj: folium.Map,
    graph: nx.MultiDiGraph,
    max_edges: int = 2500,
) -> None:
    """Draw cached streets as a vector basemap that works offline."""
    edges = _sampled_edges(graph, max_edges, major_only=False)
    features = _line_features(graph, edges)
    _add_geojson(
        map_obj,
        features,
        color="#b9b9b9",
        weight=1.6,
        opacity=0.9,
        name="Roads (offline vector)",
    )


def add_traffic_layer(
    map_obj: folium.Map,
    graph: nx.MultiDiGraph,
    traffic: TrafficModel,
    when: datetime,
    max_edges: int = 1800,
) -> dict[str, int]:
    """Colour sampled streets by the synthetic congestion class.

    Returns the number of drawn edges per congestion class so the caller can
    report what the layer contains.
    """
    edges = _sampled_edges(graph, max_edges, major_only=False)
    by_class: dict[str, list[dict]] = {key: [] for key in CLASS_COLORS}
    for u, v, key, data in edges:
        coords = edge_coords(graph, u, v, key)
        if len(coords) < 2:
            continue
        factor = traffic.delay_factor(u, v, key, data, when)
        congestion = TrafficModel.congestion_class(factor)
        by_class[congestion].append(
            {
                "type": "Feature",
                "properties": {"name": edge_name(data)},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lat, lon in coords],
                },
            }
        )

    for congestion, features in by_class.items():
        _add_geojson(
            map_obj,
            features,
            color=CLASS_COLORS[congestion],
            weight=3.2,
            opacity=0.85,
            name=f"Traffic · {congestion}",
        )
    return {name: len(features) for name, features in by_class.items()}


def add_traffic_legend(map_obj: folium.Map) -> None:
    """Add a small fixed legend for the congestion colours."""
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
        f'<span style="width:14px;height:6px;background:{color};display:inline-block;"></span>'
        f"<span>{name}</span></div>"
        for name, color in CLASS_COLORS.items()
    )
    html = (
        '<div style="position:fixed;bottom:24px;left:24px;z-index:9999;'
        "background:rgba(255,255,255,0.92);padding:8px 10px;border-radius:6px;"
        "font-size:12px;color:#222;box-shadow:0 1px 4px rgba(0,0,0,0.3);"
        'font-family:sans-serif;">'
        "<b>Synthetic traffic</b>"
        f"{rows}"
        "</div>"
    )
    map_obj.get_root().html.add_child(folium.Element(html))


def _hospital_icon() -> folium.DivIcon:
    """Red circular badge with a white plus, so hospitals read as hospitals."""
    html = (
        '<div class="qevr-hospital" style="width:26px;height:26px;'
        "border-radius:50%;background:#d62728;border:2px solid #ffffff;"
        "box-shadow:0 1px 4px rgba(0,0,0,0.45);display:flex;"
        "align-items:center;justify-content:center;color:#ffffff;"
        'font:700 20px/1 Arial,sans-serif;">+</div>'
    )
    return folium.DivIcon(
        html=html,
        icon_size=HOSPITAL_ICON_SIZE,
        icon_anchor=(HOSPITAL_ICON_SIZE[0] // 2, HOSPITAL_ICON_SIZE[1] // 2),
        class_name="qevr-hospital-icon",
    )


def _vehicle_icon(vehicle: Vehicle) -> folium.DivIcon:
    """Small ambulance/van glyph instead of a generic map pin."""
    color = ALS_COLOR if vehicle.kind == "ALS" else BLS_COLOR
    html = (
        '<div class="qevr-vehicle" style="width:30px;height:30px;'
        f"border-radius:8px;background:{color};border:2px solid #ffffff;"
        "box-shadow:0 1px 4px rgba(0,0,0,0.45);display:flex;"
        'align-items:center;justify-content:center;">'
        '<svg width="22" height="22" viewBox="0 0 24 24" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<rect x="2" y="7" width="13" height="8" rx="1.5" fill="#ffffff"/>'
        '<path d="M15 9h4l3 4v2h-7V9Z" fill="#ffffff"/>'
        f'<path d="M16 10h2.4l1.8 2.5H16V10Z" fill="{color}"/>'
        f'<rect x="5" y="9" width="2" height="5" rx="0.4" fill="{color}"/>'
        f'<rect x="3.5" y="10.5" width="5" height="2" rx="0.4" fill="{color}"/>'
        '<circle cx="7" cy="17" r="2" fill="#1f2937"/>'
        '<circle cx="17" cy="17" r="2" fill="#1f2937"/>'
        "</svg></div>"
    )
    return folium.DivIcon(
        html=html,
        icon_size=VEHICLE_ICON_SIZE,
        icon_anchor=(VEHICLE_ICON_SIZE[0] // 2, VEHICLE_ICON_SIZE[1] // 2),
        class_name="qevr-vehicle-icon",
    )


def add_hospitals(
    map_obj: folium.Map, hospitals: Iterable[Hospital], layer_name: str = "Hospitals"
) -> None:
    layer = folium.FeatureGroup(name=layer_name, show=True)
    for hospital in hospitals:
        specialties = ", ".join(hospital.specialties) or "general"
        popup = (
            f"<b>{hospital.name}</b><br>"
            f"Specialties: {specialties}<br>"
            f"Simulated offload: {hospital.offload_min:.0f} min<br>"
            f"Trauma level: {hospital.trauma_level or 'n/a'}<br>"
            f"<i>Source: {hospital.source}</i>"
        )
        folium.Marker(
            location=[hospital.lat, hospital.lon],
            icon=_hospital_icon(),
            popup=folium.Popup(popup, max_width=320),
            tooltip=hospital.name,
        ).add_to(layer)
    layer.add_to(map_obj)


def add_vehicles(
    map_obj: folium.Map, vehicles: Iterable[Vehicle], layer_name: str = "Ambulances"
) -> None:
    layer = folium.FeatureGroup(name=layer_name, show=True)
    for vehicle in vehicles:
        popup = (
            f"<b>{vehicle.id}</b> ({vehicle.kind})<br>"
            f"Capacity: {vehicle.capacity}<br>"
            f"Ventilator: {'yes' if vehicle.ventilator else 'no'}<br>"
            f"Height: {vehicle.height_m:.1f} m, weight: {vehicle.weight_kg:.0f} kg<br>"
            f"<i>Source: {vehicle.source}</i>"
        )
        folium.Marker(
            location=[vehicle.lat, vehicle.lon],
            popup=folium.Popup(popup, max_width=280),
            tooltip=f"{vehicle.id} ({vehicle.kind})",
            icon=_vehicle_icon(vehicle),
        ).add_to(layer)
    layer.add_to(map_obj)


def add_incidents(
    map_obj: folium.Map, incidents: Iterable[Incident], layer_name: str = "Incidents"
) -> None:
    layer = folium.FeatureGroup(name=layer_name, show=True)
    for incident in incidents:
        popup = (
            f"<b>{incident.id}</b><br>{incident.description}<br>"
            f"Severity (lambda): {incident.severity:.0f}<br>"
            f"Equipment: {incident.equipment_required}<br>"
            f"Specialty: {incident.specialty_required or 'none'}<br>"
            f"<i>Source: {incident.source}</i>"
        )
        folium.Marker(
            location=[incident.lat, incident.lon],
            popup=folium.Popup(popup, max_width=320),
            tooltip=f"{incident.id}: lambda={incident.severity:.0f}",
            icon=folium.Icon(color="red", icon="warning-sign"),
        ).add_to(layer)
    layer.add_to(map_obj)


def add_route(
    map_obj: folium.Map,
    plan: RoutePlan,
    color: str = CLASSICAL_COLOR,
    label: str = "Classical route",
    animated: bool = True,
    layer_name: str | None = None,
    add_to_map: bool = True,
) -> folium.FeatureGroup | None:
    coords = plan.coords
    if len(coords) < 2:
        return None
    layer = folium.FeatureGroup(name=layer_name or label, show=True)
    folium.PolyLine(
        locations=[list(point) for point in coords],
        color=color,
        weight=5,
        opacity=0.25,
        tooltip=label,
    ).add_to(layer)
    if animated:
        AntPath(
            locations=[list(point) for point in coords],
            color=color,
            weight=5,
            opacity=0.9,
            delay=800,
            dash_array=[10, 20],
            tooltip=label,
        ).add_to(layer)
    else:
        folium.PolyLine(
            locations=[list(point) for point in coords],
            color=color,
            weight=5,
            opacity=0.9,
            tooltip=label,
        ).add_to(layer)
    if add_to_map:
        layer.add_to(map_obj)
    return layer


def add_run(
    map_obj: folium.Map,
    run: VehicleRun,
    label_prefix: str = "Simulation",
    add_to_map: bool = True,
) -> folium.FeatureGroup:
    """Draw one simulated vehicle: completed, remaining, and live position."""
    layer = folium.FeatureGroup(
        name=f"{label_prefix} · {run.vehicle.id}", show=True
    )
    completed = run.completed_path
    if len(completed) >= 2:
        folium.PolyLine(
            locations=[list(point) for point in completed],
            color=COMPLETED_COLOR,
            weight=5,
            opacity=0.9,
            tooltip=f"{run.vehicle.id} completed",
        ).add_to(layer)
    remaining = run.remaining_coords
    if len(remaining) >= 2:
        folium.PolyLine(
            locations=[list(point) for point in remaining],
            color=REMAINING_COLOR,
            weight=4,
            opacity=0.9,
            dash_array="6 8",
            tooltip=f"{run.vehicle.id} remaining",
        ).add_to(layer)

    onboard = ", ".join(run.onboard) or "none"
    popup = (
        f"<b>{run.vehicle.id}</b> ({run.vehicle.kind})<br>"
        f"Status: {run.status.replace('_', ' ')}<br>"
        f"On board: {onboard}<br>"
        f"Leg {min(run.leg_index + 1, len(run.plan.legs))} of {len(run.plan.legs)}"
    )
    folium.CircleMarker(
        location=[run.position[0], run.position[1]],
        radius=9,
        color=POSITION_COLOR,
        weight=2,
        fill=True,
        fill_color=COMPLETED_COLOR,
        fill_opacity=1.0,
        popup=folium.Popup(popup, max_width=280),
        tooltip=f"{run.vehicle.id}: {run.status.replace('_', ' ')}",
    ).add_to(layer)
    if add_to_map:
        layer.add_to(map_obj)
    return layer


def add_click_marker(
    map_obj: folium.Map, point: tuple[float, float], label: str = "Selected point"
) -> None:
    folium.Marker(
        location=[point[0], point[1]],
        tooltip=label,
        icon=folium.Icon(color="orange", icon="map-marker"),
    ).add_to(map_obj)
