"""Classical dispatch: hospital scoring, greedy assignment, and stop ordering."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

import networkx as nx

from quantum.config import Config
from quantum.data.loader import snap_targets_to_graph
from quantum.graph import (
    NoPathError,
    build_routing_graph,
    path_coords,
    prune_for_vehicle,
    route_metrics,
    shortest_path,
)
from quantum.problem import URGENCY_STEP_SECONDS, Hospital, Incident, Scenario, Vehicle


class DispatchError(RuntimeError):
    """Raised when a scenario cannot be dispatched at all."""


@dataclass
class Leg:
    from_id: str
    to_id: str
    path: list[int]
    coords: list[tuple[float, float]]
    travel_time_s: float
    length_m: float


@dataclass
class HospitalOption:
    hospital: Hospital
    leg: Leg
    offload_s: float
    score_s: float
    specialty_match: bool


@dataclass
class RoutePlan:
    vehicle_id: str
    incident_ids: list[str]
    hospital_id: str
    legs: list[Leg]
    total_transit_s: float
    offload_min: float
    total_mission_min: float
    equipment_match: bool
    clearance_ok: bool
    specialty_match: bool
    mode: str = "classical"
    objective_score_s: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def coords(self) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for leg in self.legs:
            if out and leg.coords and out[-1] == leg.coords[0]:
                out.extend(leg.coords[1:])
            else:
                out.extend(leg.coords)
        return out


@dataclass
class DispatchResult:
    plans: list[RoutePlan]
    unassigned: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PreparedProblem:
    scenario: Scenario
    graph: nx.MultiDiGraph
    routing: nx.DiGraph
    snap: dict[str, int]
    pruned: dict[str, nx.DiGraph]
    cfg: Config


def prepare(scenario: Scenario, graph: nx.MultiDiGraph, cfg: Config) -> PreparedProblem:
    """Build routing graphs, snap every target, and prune per vehicle."""
    if not scenario.incidents:
        raise DispatchError("Scenario has no incidents")
    if not scenario.vehicles:
        raise DispatchError("Scenario has no vehicles")
    if not scenario.hospitals:
        raise DispatchError("Scenario has no hospitals")

    routing = build_routing_graph(graph, scenario.traffic_multiplier)

    hospital_points = [(h.id, h.lat, h.lon) for h in scenario.hospitals]
    vehicle_points = [(v.id, v.lat, v.lon) for v in scenario.vehicles]
    incident_points = [(i.id, i.lat, i.lon) for i in scenario.incidents]

    snap = snap_targets_to_graph(graph, hospital_points + vehicle_points, max_distance_m=300.0)
    # Incidents can be inside parks or buildings; allow a wider snap radius.
    snap.update(snap_targets_to_graph(graph, incident_points, max_distance_m=500.0))

    pruned: dict[str, nx.DiGraph] = {}
    for vehicle in scenario.vehicles:
        pruned[vehicle.id] = prune_for_vehicle(routing, vehicle)

    return PreparedProblem(
        scenario=scenario,
        graph=graph,
        routing=routing,
        snap=snap,
        pruned=pruned,
        cfg=cfg,
    )


def route_leg(prepared: PreparedProblem, vehicle: Vehicle, from_id: str, to_id: str) -> Leg:
    graph = prepared.pruned[vehicle.id]
    try:
        path = shortest_path(graph, prepared.snap[from_id], prepared.snap[to_id])
    except NoPathError as exc:
        raise NoPathError(
            f"{vehicle.id}: no passable route {from_id} -> {to_id} ({exc})"
        ) from exc
    travel_s, length_m = route_metrics(graph, path)
    return Leg(
        from_id=from_id,
        to_id=to_id,
        path=path,
        coords=path_coords(graph, path),
        travel_time_s=travel_s,
        length_m=length_m,
    )


def hospital_options(
    prepared: PreparedProblem, vehicle: Vehicle, incident: Incident
) -> list[HospitalOption]:
    """Rank hospitals for one incident, applying specialty filters when possible."""
    required = incident.specialty_required
    candidates = [
        h for h in prepared.scenario.hospitals
        if required is None or required in h.specialties
    ]
    specialty_match = True
    notes: list[str] = []
    if not candidates:
        candidates = list(prepared.scenario.hospitals)
        specialty_match = False
        notes.append(
            f"No hospital advertises specialty {required!r}; falling back to all hospitals."
        )

    options: list[HospitalOption] = []
    for hospital in candidates:
        try:
            leg = route_leg(prepared, vehicle, incident.id, hospital.id)
        except NoPathError:
            continue
        offload_s = hospital.offload_min * 60.0
        options.append(
            HospitalOption(
                hospital=hospital,
                leg=leg,
                offload_s=offload_s,
                score_s=leg.travel_time_s + offload_s,
                specialty_match=specialty_match,
            )
        )
    options.sort(key=lambda item: item.score_s)
    return options


def plan_incident(prepared: PreparedProblem, vehicle: Vehicle, incident: Incident) -> RoutePlan:
    options = hospital_options(prepared, vehicle, incident)
    if not options:
        raise DispatchError(
            f"No reachable hospital for incident {incident.id} with vehicle {vehicle.id}"
        )
    best = options[0]
    leg_to_incident = route_leg(prepared, vehicle, vehicle.id, incident.id)
    total_transit = leg_to_incident.travel_time_s + best.leg.travel_time_s
    return RoutePlan(
        vehicle_id=vehicle.id,
        incident_ids=[incident.id],
        hospital_id=best.hospital.id,
        legs=[leg_to_incident, best.leg],
        total_transit_s=total_transit,
        offload_min=best.hospital.offload_min,
        total_mission_min=total_transit / 60.0 + best.hospital.offload_min,
        equipment_match=vehicle.can_carry(incident.equipment_required),
        clearance_ok=True,
        specialty_match=best.specialty_match,
        mode="classical",
        objective_score_s=total_transit + best.offload_s,
    )


def assign(prepared: PreparedProblem) -> DispatchResult:
    """Greedy severity-first assignment with capacity and equipment constraints."""
    remaining_capacity = {v.id: v.capacity for v in prepared.scenario.vehicles}
    current_location = {v.id: v.id for v in prepared.scenario.vehicles}
    plans: list[RoutePlan] = []
    unassigned: list[str] = []
    notes: list[str] = []

    for incident in sorted(prepared.scenario.incidents, key=lambda i: -i.severity):
        best: tuple[float, Vehicle, RoutePlan] | None = None
        for vehicle in prepared.scenario.vehicles:
            if remaining_capacity[vehicle.id] <= 0:
                continue
            if not vehicle.can_carry(incident.equipment_required):
                continue
            try:
                leg_to_incident = route_leg(
                    prepared, vehicle, current_location[vehicle.id], incident.id
                )
                options = hospital_options(prepared, vehicle, incident)
            except (NoPathError, DispatchError):
                continue
            if not options:
                continue
            option = options[0]
            total_transit = leg_to_incident.travel_time_s + option.leg.travel_time_s
            total = total_transit + option.offload_s
            plan = RoutePlan(
                vehicle_id=vehicle.id,
                incident_ids=[incident.id],
                hospital_id=option.hospital.id,
                legs=[leg_to_incident, option.leg],
                total_transit_s=total_transit,
                offload_min=option.hospital.offload_min,
                total_mission_min=total / 60.0,
                equipment_match=True,
                clearance_ok=True,
                specialty_match=option.specialty_match,
                mode="classical",
                objective_score_s=total,
            )
            if best is None or total < best[0]:
                best = (total, vehicle, plan)

        if best is None:
            unassigned.append(incident.id)
            continue
        _, vehicle, plan = best
        plans.append(plan)
        remaining_capacity[vehicle.id] -= 1
        current_location[vehicle.id] = plan.hospital_id

    if unassigned:
        notes.append(f"Unassigned incidents: {', '.join(unassigned)}")
    return DispatchResult(plans=plans, unassigned=unassigned, notes=notes)


def _cluster_cost(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    order: tuple[Incident, ...],
    hospital: Hospital,
) -> tuple[float, list[Leg]]:
    legs: list[Leg] = []
    total = 0.0
    current = vehicle.id
    for position, incident in enumerate(order, start=1):
        leg = route_leg(prepared, vehicle, current, incident.id)
        legs.append(leg)
        total += leg.travel_time_s
        # Same urgency model the QUBO uses, so classical and quantum are comparable.
        total += URGENCY_STEP_SECONDS * incident.severity * position
        current = incident.id
    final = route_leg(prepared, vehicle, current, hospital.id)
    legs.append(final)
    total += final.travel_time_s
    return total, legs


def order_cluster(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    incidents: list[Incident],
    hospital: Hospital,
) -> tuple[list[Incident], list[Leg], float]:
    """Nearest-neighbour followed by exhaustive/2-opt improvement (<=6 stops)."""
    if not incidents:
        raise DispatchError("Cluster has no incidents")
    if len(incidents) > 6:
        raise DispatchError("Cluster ordering is capped at 6 stops")

    remaining = list(incidents)
    order: list[Incident] = []
    current = vehicle.id
    while remaining:
        nearest = min(
            remaining,
            key=lambda inc: route_leg(prepared, vehicle, current, inc.id).travel_time_s,
        )
        order.append(nearest)
        remaining.remove(nearest)
        current = nearest.id

    best_order = tuple(order)
    best_cost, best_legs = _cluster_cost(prepared, vehicle, best_order, hospital)

    if len(incidents) <= 6:
        for candidate in permutations(incidents):
            cost, legs = _cluster_cost(prepared, vehicle, candidate, hospital)
            if cost < best_cost:
                best_cost, best_legs, best_order = cost, legs, candidate

    return list(best_order), best_legs, best_cost


def plan_for_order(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    incidents: list[Incident],
    hospital: Hospital,
    order_ids: list[str],
    mode: str = "classical",
) -> RoutePlan:
    """Evaluate a specific stop order (used by the QAOA comparison)."""
    by_id = {incident.id: incident for incident in incidents}
    if set(order_ids) != set(by_id):
        raise DispatchError("order_ids must be a permutation of the incident set")

    legs: list[Leg] = []
    current = vehicle.id
    objective = 0.0
    for position, incident_id in enumerate(order_ids, start=1):
        leg = route_leg(prepared, vehicle, current, incident_id)
        legs.append(leg)
        objective += leg.travel_time_s
        objective += URGENCY_STEP_SECONDS * by_id[incident_id].severity * position
        current = incident_id
    final = route_leg(prepared, vehicle, current, hospital.id)
    legs.append(final)
    objective += final.travel_time_s
    objective += hospital.offload_min * 60.0

    transit_s = sum(leg.travel_time_s for leg in legs)
    required = {i.specialty_required for i in incidents if i.specialty_required}
    return RoutePlan(
        vehicle_id=vehicle.id,
        incident_ids=list(order_ids),
        hospital_id=hospital.id,
        legs=legs,
        total_transit_s=transit_s,
        offload_min=hospital.offload_min,
        total_mission_min=transit_s / 60.0 + hospital.offload_min,
        equipment_match=all(vehicle.can_carry(i.equipment_required) for i in incidents),
        clearance_ok=True,
        specialty_match=required.issubset(set(hospital.specialties)),
        mode=mode,
        objective_score_s=objective,
    )


def best_hospital_for_cluster(
    prepared: PreparedProblem, vehicle: Vehicle, incidents: list[Incident]
) -> Hospital:
    """Pick the hospital that minimises the best classical order."""
    required = {i.specialty_required for i in incidents if i.specialty_required}
    candidates = [
        h for h in prepared.scenario.hospitals if required.issubset(set(h.specialties))
    ]
    if not candidates:
        candidates = list(prepared.scenario.hospitals)

    best: tuple[float, Hospital] | None = None
    for hospital in candidates:
        try:
            _, _, transit = order_cluster(prepared, vehicle, incidents, hospital)
        except (NoPathError, DispatchError):
            continue
        total = transit + hospital.offload_min * 60.0
        if best is None or total < best[0]:
            best = (total, hospital)
    if best is None:
        raise DispatchError("No reachable hospital for the cluster")
    return best[1]


def cluster_plan(
    prepared: PreparedProblem, vehicle: Vehicle, incident_ids: list[str]
) -> RoutePlan:
    """Plan one vehicle visiting several incidents, then the best hospital."""
    incidents = [i for i in prepared.scenario.incidents if i.id in set(incident_ids)]
    if len(incidents) != len(incident_ids):
        raise DispatchError("Some incident ids are not in the scenario")
    if len(incidents) > vehicle.capacity:
        raise DispatchError(
            f"{vehicle.id} capacity {vehicle.capacity} < {len(incidents)} incidents"
        )
    if any(not vehicle.can_carry(i.equipment_required) for i in incidents):
        raise DispatchError(f"{vehicle.id} lacks equipment for one or more incidents")

    required = {i.specialty_required for i in incidents if i.specialty_required}
    candidates = [
        h for h in prepared.scenario.hospitals if required.issubset(set(h.specialties))
    ]
    specialty_match = True
    notes: list[str] = []
    if not candidates:
        candidates = list(prepared.scenario.hospitals)
        specialty_match = False
        notes.append("No single hospital covers every required specialty; falling back.")

    best: tuple[float, list[Incident], list[Leg], Hospital] | None = None
    for hospital in candidates:
        order, legs, transit = order_cluster(prepared, vehicle, incidents, hospital)
        total = transit + hospital.offload_min * 60.0
        if best is None or total < best[0]:
            best = (total, order, legs, hospital)

    if best is None:
        raise DispatchError("No reachable hospital for the cluster")

    total, order, legs, hospital = best
    transit_s = sum(leg.travel_time_s for leg in legs)
    return RoutePlan(
        vehicle_id=vehicle.id,
        incident_ids=[i.id for i in order],
        hospital_id=hospital.id,
        legs=legs,
        total_transit_s=transit_s,
        offload_min=hospital.offload_min,
        total_mission_min=transit_s / 60.0 + hospital.offload_min,
        equipment_match=True,
        clearance_ok=True,
        specialty_match=specialty_match,
        mode="classical",
        objective_score_s=total,
        notes=notes,
    )


def run_scenario(
    scenario: Scenario,
    graph: nx.MultiDiGraph,
    cfg: Config,
    cluster_vehicle: str | None = None,
) -> DispatchResult:
    """Prepare and dispatch one scenario (used by the CLI and tests).

    With ``cluster_vehicle`` set, all incidents are ordered for that single
    vehicle; otherwise the greedy multi-vehicle assignment is used.
    """
    prepared = prepare(scenario, graph, cfg)
    if cluster_vehicle is None:
        return assign(prepared)
    vehicle = scenario.vehicle(cluster_vehicle)
    plan = cluster_plan(prepared, vehicle, [incident.id for incident in scenario.incidents])
    return DispatchResult(plans=[plan])
