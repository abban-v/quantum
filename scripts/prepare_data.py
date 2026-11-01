"""Prepare the cached Manhattan graph and export a flat edge table.

Usage:
    uv run python scripts/prepare_data.py [--force]

Outputs:
    data/cache/manhattan_drive.graphml
    data/curated/manhattan_edges.parquet
    data/manifests/osm_manhattan.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from quantum.config import Config, MANIFEST_DIR, ensure_dirs
from quantum.data.fetch import fetch_graph, sha256_file
from quantum.data.loader import parse_height_m, parse_weight_kg, validate_graph


def _scalar(value):
    """OSM tags are sometimes lists; parquet needs scalars."""
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the cached graph")
    args = parser.parse_args()

    ensure_dirs()
    cfg = Config.load()
    graph = fetch_graph(cfg, force=args.force)
    stats = validate_graph(graph)
    print(f"graph: {stats['nodes']} nodes, {stats['edges']} edges")

    rows = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        rows.append(
            {
                "u": int(u),
                "v": int(v),
                "key": int(key),
                "length_m": float(data.get("length", 0.0)),
                "speed_kph": float(data.get("speed_kph", 0.0)),
                "travel_time_s": float(data.get("travel_time", 0.0)),
                "highway": _scalar(data.get("highway")),
                "bridge": bool(data.get("bridge", False)),
                "tunnel": bool(data.get("tunnel", False)),
                "name": _scalar(data.get("name")),
                "maxheight_m": parse_height_m(data.get("maxheight")),
                "maxweight_kg": parse_weight_kg(data.get("maxweight")),
            }
        )

    frame = pd.DataFrame(rows)
    out = cfg.edges_cache
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    print(f"wrote {len(frame)} edges to {out}")

    manifest = {
        "dataset": "manhattan_edges",
        "derived_from": str(cfg.graph_cache),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "nodes": int(stats["nodes"]),
        "dropped_disconnected_nodes": int(graph.graph.get("qevr_dropped_nodes", 0)),
        "sha256": sha256_file(out),
        "units": {"length_m": "metres", "speed_kph": "km/h", "travel_time_s": "seconds"},
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = MANIFEST_DIR / "manhattan_edges.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote manifest to {manifest_path}")

    tagged = frame["maxheight_m"].notna().sum()
    print(f"edges with parsed height: {tagged} (expected 0 for this extract)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
