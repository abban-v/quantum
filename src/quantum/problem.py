"""Domain models for the Q-EVR demo.

Every record carries a ``source`` field so the UI can distinguish real,
curated, and synthetic data. All distances are metres and all times seconds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Source = Literal["real", "curated", "synthetic"]
VehicleKind = Literal["BLS", "ALS"]
Equipment = Literal["none", "ventilator"]

#: Seconds of delay represented by one unit of triage severity per stop.
URGENCY_STEP_SECONDS = 60.0


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class Hospital(GeoPoint):
    id: str
    name: str
    specialties: list[str] = Field(default_factory=list)
    offload_min: float = Field(ge=0.0, description="Simulated ED offload wait in minutes")
    trauma_level: int | None = Field(default=None, ge=1, le=4)
    source: Source = "curated"
    notes: str = ""

    @field_validator("specialties")
    @classmethod
    def _normalise_specialties(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().lower() for item in value if item.strip()})


class Vehicle(GeoPoint):
    id: str
    kind: VehicleKind
    station_id: str
    capacity: int = Field(default=1, ge=1, le=4)
    ventilator: bool = False
    height_m: float = Field(default=3.2, gt=0.0)
    weight_kg: float = Field(default=4500.0, gt=0.0)
    source: Source = "curated"
    notes: str = ""

    @model_validator(mode="after")
    def _als_has_ventilator(self) -> "Vehicle":
        if self.kind == "ALS" and not self.ventilator:
            raise ValueError(f"ALS vehicle {self.id} must have ventilator=True")
        if self.kind == "BLS" and self.ventilator:
            raise ValueError(f"BLS vehicle {self.id} cannot have ventilator=True")
        return self

    def can_carry(self, equipment: Equipment) -> bool:
        return equipment == "none" or (equipment == "ventilator" and self.ventilator)


class Incident(GeoPoint):
    id: str
    description: str = ""
    severity: float = Field(ge=0.0, description="Triage lambda; higher is more urgent")
    equipment_required: Equipment = "none"
    specialty_required: str | None = None
    source: Source = "synthetic"
    notes: str = ""

    @field_validator("specialty_required")
    @classmethod
    def _normalise_specialty(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None


class Scenario(BaseModel):
    id: str
    name: str
    incidents: list[Incident]
    vehicles: list[Vehicle] = Field(default_factory=list)
    hospitals: list[Hospital] = Field(default_factory=list)
    traffic_multiplier: float = Field(default=1.25, gt=0.0)
    seed: int = 7
    source: Source = "curated"
    notes: str = ""

    @model_validator(mode="after")
    def _unique_ids(self) -> "Scenario":
        for label, items in (
            ("incident", self.incidents),
            ("vehicle", self.vehicles),
            ("hospital", self.hospitals),
        ):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label} ids in scenario {self.id}")
        if not self.incidents:
            raise ValueError(f"Scenario {self.id} has no incidents")
        return self

    def hospital(self, hospital_id: str) -> Hospital:
        for item in self.hospitals:
            if item.id == hospital_id:
                return item
        raise KeyError(f"Unknown hospital id: {hospital_id}")

    def vehicle(self, vehicle_id: str) -> Vehicle:
        for item in self.vehicles:
            if item.id == vehicle_id:
                return item
        raise KeyError(f"Unknown vehicle id: {vehicle_id}")
