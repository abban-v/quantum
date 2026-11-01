from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantum.problem import Hospital, Incident, Scenario, Vehicle


def test_als_requires_ventilator():
    with pytest.raises(ValidationError, match="must have ventilator"):
        Vehicle(id="A", kind="ALS", station_id="S", lat=40.0, lon=-73.0, ventilator=False)


def test_bls_cannot_have_ventilator():
    with pytest.raises(ValidationError, match="cannot have ventilator"):
        Vehicle(id="B", kind="BLS", station_id="S", lat=40.0, lon=-73.0, ventilator=True)


def test_duplicate_ids_rejected():
    hospital = Hospital(id="H", name="H", lat=40.0, lon=-73.0, offload_min=1)
    vehicle = Vehicle(id="V", kind="BLS", station_id="S", lat=40.0, lon=-73.0)
    incident = Incident(id="I", lat=40.0, lon=-73.0, severity=5)
    with pytest.raises(ValidationError, match="Duplicate hospital ids"):
        Scenario(
            id="X", name="X", incidents=[incident], vehicles=[vehicle],
            hospitals=[hospital, hospital],
        )


def test_equipment_matching():
    als = Vehicle(id="A", kind="ALS", station_id="S", lat=40.0, lon=-73.0, ventilator=True)
    bls = Vehicle(id="B", kind="BLS", station_id="S", lat=40.0, lon=-73.0)
    assert als.can_carry("ventilator")
    assert not bls.can_carry("ventilator")
    assert bls.can_carry("none")
