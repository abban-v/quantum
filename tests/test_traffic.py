from __future__ import annotations

from datetime import datetime

import pytest

from quantum.traffic import (
    CLASS_COLORS,
    TrafficModel,
    click_key,
    edge_name,
    nearest_edge,
    street_names,
    street_pick,
)


def _edge(highway: str = "primary") -> dict:
    return {"highway": highway, "name": "Test Street"}


def test_peak_hour_is_slower_than_overnight():
    model = TrafficModel()
    when_peak = datetime(2026, 11, 3, 8, 30)  # Tuesday
    when_night = datetime(2026, 11, 3, 3, 30)
    peak = model.delay_factor(1, 2, 0, _edge("primary"), when_peak)
    night = model.delay_factor(1, 2, 0, _edge("primary"), when_night)
    assert peak > night
    assert night == 1.0


def test_weekend_profile_is_used():
    model = TrafficModel()
    saturday = datetime(2026, 11, 7, 8, 30)
    tuesday = datetime(2026, 11, 3, 8, 30)
    assert model.delay_factor(1, 2, 0, _edge("primary"), saturday) != model.delay_factor(
        1, 2, 0, _edge("primary"), tuesday
    )


def test_override_takes_precedence():
    model = TrafficModel()
    when = datetime(2026, 11, 3, 8, 30)
    model.set_override(1, 2, 0, 2.5)
    assert model.delay_factor(1, 2, 0, _edge("primary"), when) == 2.5
    model.clear_override(1, 2, 0)
    assert model.delay_factor(1, 2, 0, _edge("primary"), when) != 2.5


def test_congestion_classes_and_colors():
    assert TrafficModel.congestion_class(1.0) == "free"
    assert TrafficModel.congestion_class(1.5) == "moderate"
    assert TrafficModel.congestion_class(2.5) == "heavy"
    assert TrafficModel.congestion_class(4.0) == "blocked"
    assert TrafficModel.color(1.0) == CLASS_COLORS["free"]
    assert TrafficModel.color(2.5) == CLASS_COLORS["heavy"]


def test_nearest_edge_on_grid(grid_graph):
    # Point just north of the 0 -> 1 edge at 40.750, -73.980.
    hit = nearest_edge(grid_graph, 40.7501, -73.9795, max_distance_m=100.0)
    assert hit is not None
    u, v, key, data, distance = hit
    assert {u, v} == {0, 1}
    assert distance < 30.0
    assert edge_name(data) == "Residential"


def test_nearest_edge_returns_none_when_far(grid_graph):
    assert nearest_edge(grid_graph, 41.0, -74.0, max_distance_m=50.0) is None


def test_street_pick_is_serialisable(grid_graph):
    pick = street_pick(grid_graph, 40.7501, -73.9795, max_distance_m=100.0)
    assert pick is not None
    assert pick["name"] == "Residential"
    assert {pick["u"], pick["v"]} == {0, 1}
    assert pick["distance_m"] < 30.0
    assert set(pick) == {"u", "v", "key", "name", "distance_m"}


def test_street_pick_returns_none_off_road(grid_graph):
    assert street_pick(grid_graph, 41.0, -74.0, max_distance_m=50.0) is None


def test_click_key_rounds_to_six_places():
    assert click_key(40.7500001, -73.98) == "40.750000,-73.980000"
    assert click_key(40.7500004, -73.98) == "40.750000,-73.980000"


def test_network_multiplier_scales_profile():
    model = TrafficModel()
    when = datetime(2026, 11, 3, 8, 30)
    base = model.delay_factor(1, 2, 0, _edge("primary"), when)
    model.set_network_multiplier(1.5)
    assert model.delay_factor(1, 2, 0, _edge("primary"), when) == pytest.approx(
        base * 1.5
    )


def test_network_multiplier_does_not_scale_explicit_override():
    model = TrafficModel()
    when = datetime(2026, 11, 3, 8, 30)
    model.set_override(1, 2, 0, 2.5)
    model.set_network_multiplier(3.0)
    assert model.delay_factor(1, 2, 0, _edge("primary"), when) == 2.5


def test_street_override_applies_and_clears_all_named_edges(grid_graph):
    model = TrafficModel()
    when = datetime(2026, 11, 3, 8, 30)
    applied = model.set_street_override(grid_graph, "Residential", 2.5)
    assert applied > 0
    assert model.delay_factor(0, 1, 0, {"highway": "residential"}, when) == 2.5
    cleared = model.clear_street_override(grid_graph, "Residential")
    assert cleared == applied
    assert model.overrides == {}


def test_street_names_are_ranked_and_deduplicated(grid_graph):
    assert street_names(grid_graph) == ["Residential"]
