"""Scenario construction and dispatch helpers shared by the app and the CLI."""

from __future__ import annotations

import networkx as nx

from quantum.config import Config
from quantum.dispatch import (
    DispatchError,
    DispatchResult,
    PreparedProblem,
    RoutePlan,
    assign,
    cluster_plan,
    prepare,
)
from quantum.nlp_parser import TriageResult
from quantum.problem import Incident, Scenario, Vehicle


def find_cluster_vehicle(scenario: Scenario, incidents: list[Incident]) -> Vehicle | None:
    """Pick the largest vehicle that can carry every incident's equipment."""
    best: Vehicle | None = None
    for vehicle in scenario.vehicles:
        if vehicle.capacity < len(incidents):
            continue
        if any(not vehicle.can_carry(i.equipment_required) for i in incidents):
            continue
        if best is None or vehicle.capacity > best.capacity:
            best = vehicle
    return best


def build_custom_scenario(
    base: Scenario,
    point: tuple[float, float],
    text: str,
    triage: TriageResult,
    multi: bool,
) -> Scenario:
    """Build a scenario from a map click and a free-text description."""
    lat, lon = point
    incidents = [
        Incident(
            id="CUSTOM-1",
            lat=lat,
            lon=lon,
            description=text,
            severity=triage.severity,
            equipment_required=triage.equipment_required,
            specialty_required=triage.specialty_required,
            source="synthetic",
            notes="Created from the dashboard text input.",
        )
    ]
    if multi:
        offsets = [(0.0007, 0.0004), (-0.0006, 0.0005)]
        severities = [max(5.0, triage.severity * 0.4), 5.0]
        for index, ((dlat, dlon), severity) in enumerate(zip(offsets, severities), start=2):
            incidents.append(
                Incident(
                    id=f"CUSTOM-{index}",
                    lat=lat + dlat,
                    lon=lon + dlon,
                    description=f"Additional casualty {index} near the primary incident.",
                    severity=severity,
                    equipment_required="none",
                    specialty_required=None,
                    source="synthetic",
                    notes="Synthetic multi-casualty companion.",
                )
            )
    return Scenario(
        id="CUSTOM",
        name="Custom incident",
        incidents=incidents,
        vehicles=list(base.vehicles),
        hospitals=list(base.hospitals),
        traffic_multiplier=base.traffic_multiplier,
        seed=base.seed,
        source="synthetic",
        notes="Built at runtime from a map click and free text.",
    )


def dispatch_scenario(
    scenario: Scenario, graph: nx.MultiDiGraph, cfg: Config
) -> tuple[PreparedProblem, list[RoutePlan]]:
    """Cluster when one vehicle can serve every stop, else use greedy assignment."""
    prepared = prepare(scenario, graph, cfg)
    if len(scenario.incidents) >= 2:
        vehicle = find_cluster_vehicle(scenario, scenario.incidents)
        if vehicle is not None:
            try:
                plan = cluster_plan(prepared, vehicle, [i.id for i in scenario.incidents])
                return prepared, [plan]
            except DispatchError:
                pass
    result: DispatchResult = assign(prepared)
    if not result.plans:
        raise DispatchError("No vehicle could be assigned to the incident(s).")
    return prepared, result.plans
