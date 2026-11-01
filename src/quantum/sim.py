"""Minimal deterministic ambulance simulation for the demo.

One vehicle follows a ``RoutePlan`` whose legs alternate:

    vehicle -> incident -> hospital -> next incident -> hospital -> ...

The engine is intentionally small: it moves along the leg geometry, waits on
scene, picks the patient up, waits for offload at that patient's hospital, and
then either continues to the next patient or becomes idle. It does not model
traffic changes mid-leg or rerouting; those are separate concerns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal

from quantum.dispatch import PreparedProblem, RoutePlan
from quantum.problem import Vehicle

SCENE_SECONDS = {"BLS": 240.0, "ALS": 360.0}


@dataclass
class Patient:
    id: str
    incident_id: str
    hospital_id: str
    severity: float
    status: Literal["waiting", "onboard", "delivered"] = "waiting"


@dataclass
class VehicleRun:
    vehicle: Vehicle
    plan: RoutePlan
    status: str = "idle"
    leg_index: int = 0
    leg_elapsed_s: float = 0.0
    position: tuple[float, float] = (0.0, 0.0)
    onboard: list[str] = field(default_factory=list)
    scene_remaining_s: float = 0.0
    offload_remaining_s: float = 0.0
    completed_coords: list[tuple[float, float]] = field(default_factory=list)
    current_coords: list[tuple[float, float]] = field(default_factory=list)
    finished: bool = False

    @property
    def leg_fraction(self) -> float:
        if self.leg_index >= len(self.plan.legs):
            return 1.0
        leg = self.plan.legs[self.leg_index]
        if leg.travel_time_s <= 0:
            return 1.0
        return max(0.0, min(1.0, self.leg_elapsed_s / leg.travel_time_s))

    @property
    def completed_path(self) -> list[tuple[float, float]]:
        """Finished legs plus the part of the current leg already driven."""
        coords = list(self.completed_coords)
        if self.current_coords and self.status in {"to_scene", "to_hospital"}:
            coords.append(self.position)
        return coords

    @property
    def remaining_coords(self) -> list[tuple[float, float]]:
        if self.finished or not self.current_coords:
            return []
        coords = _trim_coords(self.current_coords, self.leg_fraction)
        for leg in self.plan.legs[self.leg_index + 1 :]:
            if coords and leg.coords and coords[-1] == leg.coords[0]:
                coords.extend(leg.coords[1:])
            else:
                coords.extend(leg.coords)
        return coords


@dataclass
class SimulationEngine:
    prepared: PreparedProblem
    plans: list[RoutePlan]
    start: datetime
    scene_seconds: dict[str, float] = field(
        default_factory=lambda: dict(SCENE_SECONDS)
    )

    now: datetime = field(init=False)
    patients: dict[str, Patient] = field(init=False, default_factory=dict)
    runs: dict[str, VehicleRun] = field(init=False, default_factory=dict)
    events: list[tuple[datetime, str]] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.now = self.start
        self.patients.clear()
        self.runs.clear()
        self.events.clear()
        for incident in self.prepared.scenario.incidents:
            self.patients[incident.id] = Patient(
                id=incident.id,
                incident_id=incident.id,
                hospital_id="",
                severity=incident.severity,
            )
        grouped: dict[str, list[RoutePlan]] = {}
        for plan in self.plans:
            grouped.setdefault(plan.vehicle_id, []).append(plan)
        for vehicle_id, group in grouped.items():
            vehicle = self.prepared.scenario.vehicle(vehicle_id)
            plan = group[0] if len(group) == 1 else _merge_plans(group)
            run = VehicleRun(
                vehicle=vehicle,
                plan=plan,
                position=(vehicle.lat, vehicle.lon),
            )
            for incident_id in plan.incident_ids:
                patient = self.patients.get(incident_id)
                if patient is not None:
                    patient.hospital_id = plan.patient_hospitals.get(
                        incident_id, plan.hospital_id
                    )
            self.runs[vehicle.id] = run
            self._start_leg(run)

    # ------------------------------------------------------------------ tick

    def tick(self, dt_s: float) -> None:
        """Advance the simulation by ``dt_s`` seconds."""
        if dt_s <= 0:
            return
        self.now += timedelta(seconds=dt_s)
        for run in self.runs.values():
            self._advance(run, dt_s)

    def _advance(self, run: VehicleRun, dt_s: float) -> None:
        remaining = dt_s
        # Every leg costs at most three transitions (travel, scene, offload),
        # so this bound lets one large tick finish a whole plan.
        guard = 3 * len(run.plan.legs) + 4
        while remaining > 1e-9 and not run.finished and guard > 0:
            guard -= 1
            if run.status in {"to_scene", "to_hospital"}:
                leg = run.plan.legs[run.leg_index]
                needed = max(0.0, leg.travel_time_s - run.leg_elapsed_s)
                if needed <= 1e-9:
                    self._complete_leg(run)
                    continue
                step = min(remaining, needed)
                run.leg_elapsed_s += step
                remaining -= step
                fraction = (
                    min(1.0, run.leg_elapsed_s / leg.travel_time_s)
                    if leg.travel_time_s > 0
                    else 1.0
                )
                run.position = _interpolate(leg.coords, fraction)
                if run.leg_elapsed_s >= leg.travel_time_s - 1e-9:
                    self._complete_leg(run)
            elif run.status == "on_scene":
                step = min(remaining, run.scene_remaining_s)
                run.scene_remaining_s -= step
                remaining -= step
                if run.scene_remaining_s <= 1e-9:
                    self._pickup(run)
                    run.leg_index += 1
                    self._start_leg(run)
            elif run.status == "offload":
                step = min(remaining, run.offload_remaining_s)
                run.offload_remaining_s -= step
                remaining -= step
                if run.offload_remaining_s <= 1e-9:
                    self._deliver(run)
                    run.leg_index += 1
                    self._start_leg(run)
            else:
                break

    def _start_leg(self, run: VehicleRun) -> None:
        if run.leg_index >= len(run.plan.legs):
            run.status = "idle"
            run.finished = True
            run.current_coords = []
            self._log(f"{run.vehicle.id} available")
            return
        leg = run.plan.legs[run.leg_index]
        run.status = "to_scene" if run.leg_index % 2 == 0 else "to_hospital"
        run.leg_elapsed_s = 0.0
        run.current_coords = list(leg.coords)
        if leg.coords:
            run.position = leg.coords[0]
        target = leg.to_id
        verb = "scene" if run.status == "to_scene" else "hospital"
        self._log(f"{run.vehicle.id} en route to {verb} {target}")

    def _complete_leg(self, run: VehicleRun) -> None:
        leg = run.plan.legs[run.leg_index]
        if leg.coords:
            run.completed_coords.extend(leg.coords)
            run.position = leg.coords[-1]
        incident_id = run.plan.incident_ids[run.leg_index // 2]
        if run.status == "to_scene":
            run.status = "on_scene"
            run.scene_remaining_s = self.scene_seconds.get(run.vehicle.kind, 240.0)
            self._log(f"{run.vehicle.id} on scene at {incident_id}")
        else:
            hospital_id = run.plan.patient_hospitals.get(
                incident_id, run.plan.hospital_id
            )
            hospital = self.prepared.scenario.hospital(hospital_id)
            run.status = "offload"
            run.offload_remaining_s = hospital.offload_min * 60.0
            self._log(f"{run.vehicle.id} at {hospital_id} for offload")

    def _pickup(self, run: VehicleRun) -> None:
        incident_id = run.plan.incident_ids[run.leg_index // 2]
        patient = self.patients.get(incident_id)
        if patient is None:
            return
        if len(run.onboard) >= run.vehicle.capacity:
            self._log(f"{run.vehicle.id} full; cannot pick up {incident_id}")
            return
        patient.status = "onboard"
        run.onboard.append(incident_id)
        self._log(f"{run.vehicle.id} picked up {incident_id}")

    def _deliver(self, run: VehicleRun) -> None:
        incident_id = run.plan.incident_ids[run.leg_index // 2]
        patient = self.patients.get(incident_id)
        hospital_id = run.plan.patient_hospitals.get(
            incident_id, run.plan.hospital_id
        )
        if incident_id not in run.onboard:
            self._log(f"{run.vehicle.id} reached {hospital_id} without {incident_id}")
            return
        run.onboard.remove(incident_id)
        if patient is not None:
            patient.status = "delivered"
        self._log(f"{run.vehicle.id} delivered {incident_id} to {hospital_id}")

    # --------------------------------------------------------------- output

    def _log(self, message: str) -> None:
        self.events.append((self.now, message))
        if len(self.events) > 200:
            del self.events[:50]

    @property
    def finished(self) -> bool:
        return all(run.finished for run in self.runs.values())

    def metrics(self) -> dict[str, int]:
        return {
            "patients": len(self.patients),
            "waiting": sum(1 for p in self.patients.values() if p.status == "waiting"),
            "onboard": sum(1 for p in self.patients.values() if p.status == "onboard"),
            "delivered": sum(
                1 for p in self.patients.values() if p.status == "delivered"
            ),
            "busy": sum(
                1
                for run in self.runs.values()
                if not run.finished and run.status != "idle"
            ),
            "idle": sum(1 for run in self.runs.values() if run.finished),
        }

    def reset(self) -> None:
        self.__post_init__()


def _merge_plans(plans: list[RoutePlan]) -> RoutePlan:
    """Chain several plans for one vehicle into one sequential run.

    ``dispatch.assign`` can give the same vehicle more than one plan. Chaining
    their legs keeps every patient in the simulation instead of letting the
    last plan overwrite the earlier run.
    """
    first = plans[0]
    return replace(
        first,
        incident_ids=[incident for plan in plans for incident in plan.incident_ids],
        legs=[leg for plan in plans for leg in plan.legs],
        total_transit_s=sum(plan.total_transit_s for plan in plans),
        offload_min=sum(plan.offload_min for plan in plans),
        total_mission_min=sum(plan.total_mission_min for plan in plans),
        equipment_match=all(plan.equipment_match for plan in plans),
        specialty_match=all(plan.specialty_match for plan in plans),
        objective_score_s=sum(plan.objective_score_s for plan in plans),
        patient_hospitals={
            incident_id: hospital_id
            for plan in plans
            for incident_id, hospital_id in plan.patient_hospitals.items()
        },
        pruned_edges=max(plan.pruned_edges for plan in plans),
        notes=[],
    )


def _trim_coords(
    coords: list[tuple[float, float]], fraction: float
) -> list[tuple[float, float]]:
    """Return the not-yet-driven part of a polyline, starting at the vehicle."""
    if not coords:
        return []
    if len(coords) < 2:
        return list(coords)
    fraction = max(0.0, min(1.0, fraction))
    lengths = [_distance_m(a, b) for a, b in zip(coords, coords[1:])]
    total = sum(lengths)
    if total <= 0:
        return [coords[-1]]
    target = fraction * total
    travelled = 0.0
    for index, length in enumerate(lengths):
        if travelled + length >= target:
            start = _interpolate(coords, fraction)
            return [start] + coords[index + 1 :]
        travelled += length
    return [coords[-1]]


def _interpolate(
    coords: list[tuple[float, float]], fraction: float
) -> tuple[float, float]:
    if not coords:
        return (0.0, 0.0)
    if len(coords) == 1:
        return coords[0]
    fraction = max(0.0, min(1.0, fraction))
    lengths = [_distance_m(a, b) for a, b in zip(coords, coords[1:])]
    total = sum(lengths)
    if total <= 0:
        return coords[-1]
    target = fraction * total
    travelled = 0.0
    for index, length in enumerate(lengths):
        if travelled + length >= target:
            ratio = (target - travelled) / length if length > 0 else 0.0
            return _lerp(coords[index], coords[index + 1], ratio)
        travelled += length
    return coords[-1]


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[0] + b[0]) / 2.0)
    dy = (b[0] - a[0]) * 111_320.0
    dx = (b[1] - a[1]) * 111_320.0 * math.cos(lat)
    return math.hypot(dx, dy)


def _lerp(
    a: tuple[float, float], b: tuple[float, float], ratio: float
) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)
