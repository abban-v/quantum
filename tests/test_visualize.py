from __future__ import annotations

import folium

from quantum.dispatch import Leg, RoutePlan
from quantum.visualize import add_incidents, add_route, base_map


def _plan() -> RoutePlan:
    leg = Leg(
        from_id="A",
        to_id="B",
        path=[1, 2],
        coords=[(40.75, -73.98), (40.76, -73.97)],
        travel_time_s=60.0,
        length_m=100.0,
    )
    return RoutePlan(
        vehicle_id="ALS-1",
        incident_ids=["I1"],
        hospital_id="H1",
        legs=[leg],
        total_transit_s=60.0,
        offload_min=10.0,
        total_mission_min=11.0,
        equipment_match=True,
        clearance_ok=True,
        specialty_match=True,
    )


def _named_layers(map_obj):
    return {
        child.layer_name: child
        for child in map_obj._children.values()
        if isinstance(child, folium.FeatureGroup)
    }


def test_add_route_creates_named_layer():
    map_obj = base_map()
    add_route(map_obj, _plan(), label="Classical", layer_name="Classical · ALS-1")
    layers = _named_layers(map_obj)
    assert "Classical · ALS-1" in layers
    assert len(layers["Classical · ALS-1"]._children) == 2  # base + animated path


def test_add_route_skips_degenerate_paths():
    map_obj = base_map()
    plan = _plan()
    plan.legs[0].coords = [(40.75, -73.98)]
    before = len(map_obj._children)
    add_route(map_obj, plan)
    assert len(map_obj._children) == before


def test_add_incidents_layer(scenario):
    map_obj = base_map()
    add_incidents(map_obj, scenario.incidents)
    layers = _named_layers(map_obj)
    assert "Incidents" in layers
    assert len(layers["Incidents"]._children) == len(scenario.incidents)


def test_base_map_uses_osm_tiles():
    map_obj = base_map()
    assert isinstance(map_obj, folium.Map)
