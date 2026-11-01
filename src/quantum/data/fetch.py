"""Download and cache the OpenStreetMap road graph.

Raw data is cached under ``data/cache`` and never committed. A manifest with
the fetch timestamp, counts, and SHA-256 is written to ``data/manifests``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import osmnx as ox

from quantum.config import CACHE_DIR, Config, MANIFEST_DIR, REPO_ROOT, ensure_dirs
from quantum.data.loader import largest_strongly_connected_component


class DataFetchError(RuntimeError):
    """Raised when the road graph cannot be fetched or loaded."""


def _configure_osmnx_cache() -> None:
    """Keep OSMnx's HTTP cache inside the gitignored data directory."""
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(CACHE_DIR / "osmnx")


def fetch_graph(cfg: Config, force: bool = False) -> nx.MultiDiGraph:
    """Return the cached graph, fetching it from OSM when necessary.

    The graph is reduced to its largest strongly connected component so that
    every snapped target can reach every other one. Without this, points can
    snap to a disconnected stub and produce spurious "no route" failures.
    """
    ensure_dirs()
    _configure_osmnx_cache()
    path = cfg.graph_cache

    if path.exists() and not force:
        try:
            graph = ox.load_graphml(path)
        except Exception as exc:  # corrupt cache should not brick the demo
            raise DataFetchError(
                f"Cached graph at {path} could not be loaded ({exc}). "
                "Re-run with force=True or delete the cache file."
            ) from exc
        return largest_strongly_connected_component(graph)

    try:
        graph = ox.graph_from_place(
            cfg.place,
            network_type=cfg.network_type,
            simplify=True,
        )
    except Exception as exc:
        raise DataFetchError(
            f"OSM fetch failed for {cfg.place!r}: {exc}. "
            "Check network/Overpass availability, or use the synthetic city fallback."
        ) from exc

    if graph.number_of_nodes() == 0:
        raise DataFetchError(f"OSM returned an empty graph for {cfg.place!r}")

    try:
        graph = ox.add_edge_speeds(graph)
        graph = ox.add_edge_travel_times(graph)
    except Exception as exc:
        raise DataFetchError(f"Could not derive edge speeds/travel times: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ox.save_graphml(graph, path)
    except Exception as exc:
        raise DataFetchError(f"Could not cache graph to {path}: {exc}") from exc

    _write_manifest(cfg, path, graph)
    return largest_strongly_connected_component(graph)


def _write_manifest(cfg: Config, path: Path, graph: nx.MultiDiGraph) -> None:
    manifest = {
        "dataset": "osm_road_graph",
        "place": cfg.place,
        "network_type": cfg.network_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "largest_scc_nodes": len(max(nx.strongly_connected_components(graph), key=len)),
        "sha256": sha256_file(path),
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
        "path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    out = MANIFEST_DIR / "osm_manhattan.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
