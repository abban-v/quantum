from __future__ import annotations

from datetime import datetime

import folium
from streamlit_folium import _get_map_string, generate_js_hash

from quantum.dispatch import Leg, RoutePlan, cluster_plan, prepare
from quantum.sim import SimulationEngine
from quantum.traffic import TrafficModel
from quantum.visualize import (
    add_click_marker,
    add_hospitals,
    add_incidents,
    add_road_basemap,
    add_route,
    add_run,
    add_traffic_layer,
    add_traffic_legend,
    add_vehicles,
    base_map,
    region_bounds,
)


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
    html = map_obj.get_root().render()
    assert "OpenStreetMap" in html


def test_region_bounds_wraps_graph(grid_graph):
    south, west, north, east = region_bounds(grid_graph, pad=0.001)
    assert south < 40.750 < north
    assert west < -73.980 < east
    assert north > 40.753
    assert east > -73.977


def test_online_map_is_bounded(grid_graph):
    bounds = region_bounds(grid_graph)
    map_obj = base_map(bounds=bounds, tiles="osm")
    options = map_obj.options
    assert options["max_bounds"] == [
        [bounds[0], bounds[1]],
        [bounds[2], bounds[3]],
    ]
    html = map_obj.get_root().render()
    assert "OpenStreetMap" in html


def test_vector_map_has_no_tile_layer(grid_graph):
    map_obj = base_map(bounds=region_bounds(grid_graph), tiles="vector", graph=grid_graph)
    children = [child for child in map_obj._children.values()]
    assert not any(type(child).__name__ == "TileLayer" for child in children)
    html = map_obj.get_root().render()
    assert "Roads (offline vector)" in html


def test_traffic_layer_counts_edges(grid_graph):
    map_obj = base_map()
    model = TrafficModel()
    counts = add_traffic_layer(
        map_obj, grid_graph, model, datetime(2026, 11, 3, 8, 30)
    )
    # The grid uses residential streets, which the traffic layer draws.
    assert sum(counts.values()) > 0
    assert set(counts) == {"free", "moderate", "heavy", "blocked"}
    html = map_obj.get_root().render()
    assert "Traffic · " in html


def test_legend_and_click_marker_render(grid_graph):
    map_obj = base_map()
    add_traffic_legend(map_obj)
    add_click_marker(map_obj, (40.750, -73.980))
    html = map_obj.get_root().render()
    assert "Synthetic traffic" in html
    assert "Selected point" in html


def test_add_run_draws_position_and_paths(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    plan = cluster_plan(prepared, scenario.vehicle("ALS-1"), ["I1"])
    engine = SimulationEngine(
        prepared=prepared, plans=[plan], start=datetime(2026, 11, 3, 8, 30)
    )
    engine.tick(5.0)
    run = engine.runs["ALS-1"]

    map_obj = base_map()
    add_run(map_obj, run)
    html = map_obj.get_root().render()
    assert run.vehicle.id in html
    assert "remaining" in html
    assert run.status.replace("_", " ") in html


def test_base_map_does_not_fit_bounds_on_every_render(grid_graph):
    map_obj = base_map(
        center=(40.750, -73.980),
        zoom=14,
        bounds=region_bounds(grid_graph),
        tiles="vector",
        graph=grid_graph,
    )
    assert not any(
        type(child).__name__ == "FitBounds" for child in map_obj._children.values()
    )


def test_hospitals_use_red_plus_badge(scenario):
    map_obj = base_map()
    add_hospitals(map_obj, scenario.hospitals)
    html = map_obj.get_root().render()
    assert "qevr-hospital" in html
    assert "background:#d62728" in html


def test_vehicles_use_vehicle_glyph(scenario):
    map_obj = base_map()
    add_vehicles(map_obj, scenario.vehicles)
    html = map_obj.get_root().render()
    assert "qevr-vehicle" in html
    assert "\\u003csvg" in html


def test_dynamic_route_layer_can_be_kept_out_of_base_map():
    map_obj = base_map()
    before = len(map_obj._children)
    layer = add_route(map_obj, _plan(), add_to_map=False)
    assert layer is not None
    assert len(map_obj._children) == before
    assert len(layer._children) == 2


def test_dynamic_run_layer_can_be_kept_out_of_base_map(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    plan = cluster_plan(prepared, scenario.vehicle("ALS-1"), ["I1"])
    engine = SimulationEngine(
        prepared=prepared, plans=[plan], start=datetime(2026, 11, 3, 8, 30)
    )
    engine.tick(5.0)
    map_obj = base_map()
    before = len(map_obj._children)
    layer = add_run(map_obj, engine.runs["ALS-1"], add_to_map=False)
    assert len(map_obj._children) == before
    assert layer is not None


def test_dynamic_route_changes_do_not_change_map_key():
    """The simulation layer must update without remounting the Leaflet map."""
    plan_a = _plan()
    plan_b = _plan()
    plan_b.legs[0].coords = [(40.751, -73.979), (40.761, -73.969)]

    def map_key(plan):
        map_obj = base_map(center=(40.758, -73.9855), zoom=12)
        add_route(map_obj, plan, add_to_map=False)
        return generate_js_hash(_get_map_string(map_obj), "qevr_map", False)

    assert map_key(plan_a) == map_key(plan_b)
