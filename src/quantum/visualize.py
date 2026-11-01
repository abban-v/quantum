"""Folium map layers for the demo dashboard."""

from __future__ import annotations

from typing import Iterable

import folium
from folium.plugins import AntPath

from quantum.dispatch import RoutePlan
from quantum.problem import Hospital, Incident, Vehicle

MAP_CENTER = (40.7580, -73.9855)  # Times Square
MAP_ZOOM = 12

CLASSICAL_COLOR = "#1f77b4"
QUANTUM_COLOR = "#2ca02c"
INCIDENT_COLOR = "#d62728"
ALS_COLOR = "#d62728"
BLS_COLOR = "#1f77b4"
HOSPITAL_COLOR = "#9467bd"


def base_map(center: tuple[float, float] = MAP_CENTER, zoom: int = MAP_ZOOM) -> folium.Map:
    return folium.Map(
        location=list(center),
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
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
        folium.CircleMarker(
            location=[hospital.lat, hospital.lon],
            radius=7,
            color=HOSPITAL_COLOR,
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(popup, max_width=320),
            tooltip=hospital.name,
        ).add_to(layer)
    layer.add_to(map_obj)


def add_vehicles(
    map_obj: folium.Map, vehicles: Iterable[Vehicle], layer_name: str = "Ambulances"
) -> None:
    layer = folium.FeatureGroup(name=layer_name, show=True)
    for vehicle in vehicles:
        color = ALS_COLOR if vehicle.kind == "ALS" else BLS_COLOR
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
            icon=folium.Icon(color="red" if vehicle.kind == "ALS" else "blue", icon="plus-sign"),
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
) -> None:
    coords = plan.coords
    if len(coords) < 2:
        return
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
    layer.add_to(map_obj)
