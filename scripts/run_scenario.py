"""Run one scenario from the command line.

Usage:
    uv run python scripts/run_scenario.py --scenario S4
    uv run python scripts/run_scenario.py --scenario S4 --cluster ALS-01

The first form uses the greedy multi-vehicle assignment. The second orders
every incident for a single vehicle (the quantum demo path).
"""

from __future__ import annotations

import argparse
import sys

from quantum.config import Config
from quantum.data.fetch import DataFetchError, fetch_graph
from quantum.data.loader import (
    DataValidationError,
    apply_clearance_overrides,
    load_scenarios,
)
from quantum.dispatch import DispatchError, run_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="S4", help="scenario id (default: S4)")
    parser.add_argument(
        "--cluster",
        default=None,
        help="order all incidents for this vehicle id instead of greedy assignment",
    )
    args = parser.parse_args()

    try:
        cfg = Config.load()
        graph = fetch_graph(cfg)
        apply_clearance_overrides(graph)
        scenarios = {scenario.id: scenario for scenario in load_scenarios()}
    except (DataFetchError, DataValidationError) as exc:
        print(f"data error: {exc}", file=sys.stderr)
        return 1

    if args.scenario not in scenarios:
        print(
            f"unknown scenario {args.scenario!r}; choose from {sorted(scenarios)}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_scenario(scenarios[args.scenario], graph, cfg, args.cluster)
    except DispatchError as exc:
        print(f"dispatch error: {exc}", file=sys.stderr)
        return 3

    print(f"scenario {args.scenario}: {scenarios[args.scenario].name}")
    for plan in result.plans:
        print(
            f"  {plan.vehicle_id}: {' -> '.join(plan.incident_ids)}"
            f" -> {plan.hospital_id}"
            f" | transit {plan.total_transit_s / 60:.1f} min"
            f" | offload {plan.offload_min:.0f} min"
            f" | total {plan.total_mission_min:.1f} min"
            f" | objective {plan.objective_score_s / 60:.1f} min"
            f" | equipment={plan.equipment_match}"
            f" specialty={plan.specialty_match}"
            f" clearance={plan.clearance_ok}"
        )
    for note in result.notes:
        print(f"  note: {note}")
    if result.unassigned:
        print(f"  unassigned: {', '.join(result.unassigned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
