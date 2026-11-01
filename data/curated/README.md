# Curated demo data — provenance

This directory holds the small, hand-curated datasets used by the demo. Raw
downloads live in `data/cache/` and are never committed.

| File | What is real | What is synthetic |
|---|---|---|
| `hospitals.json` | Hospital names and coordinates come from OpenStreetMap (`amenity=hospital`). | Specialty lists, trauma levels, and ED offload minutes are **demo placeholders** pending verification against CMS/ACS/ABA/Joint Commission sources. |
| `fleet.json` | Station coordinates come from OpenStreetMap (`amenity=fire_station`). | Vehicles, capabilities, capacities, heights, and weights are **synthetic**. |
| `scenarios.json` | Incident coordinates are real Manhattan locations. | Incident descriptions, severities, and equipment requirements are **synthetic** demo presets. |
| `clearance_overrides.json` | Edge IDs come from the cached OSM graph. | Height and weight limits are **synthetic** and exist only to exercise the pruning path. |

Every record carries a `source` field (`real`, `curated`, or `synthetic`) and,
where useful, a `notes` field. Do not present simulated values as operational
data.

## Synthetic traffic and simulation

`src/quantum/traffic.py` holds hand-set weekday/weekend delay profiles plus
manual per-street and network-wide multipliers. They are **synthetic** and are
not live traffic feeds. `src/quantum/sim.py` combines those travel times with
the curated offload minutes and fixed scene times (BLS 4 min, ALS 6 min) to
animate the demo. Every simulation value is illustrative only.

## Regenerating the graph

```bash
uv run python scripts/prepare_data.py --force
```

This writes `data/cache/manhattan_drive.graphml`, `data/curated/manhattan_edges.parquet`,
and `data/manifests/osm_manhattan.json`. The graph is ODbL 1.0 data ©
OpenStreetMap contributors.
