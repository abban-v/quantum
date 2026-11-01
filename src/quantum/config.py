"""Project-wide paths and configuration.

All physical quantities are stored in SI-derived units:
  - distance: metres
  - time: seconds
  - speed: metres / second (converted at ingest)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
CURATED_DIR = DATA_DIR / "curated"
MANIFEST_DIR = DATA_DIR / "manifests"
SCENARIO_DIR = DATA_DIR / "scenarios"
ARTIFACT_DIR = REPO_ROOT / "artifacts"
CONFIG_PATH = REPO_ROOT / "config.yaml"


class ConfigError(RuntimeError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    place: str
    network_type: str
    graph_cache: Path
    edges_cache: Path
    traffic_multiplier: float
    max_qubits: int
    max_quantum_stops: int
    qaoa_timeout_s: float
    qaoa_maxiter: int
    qaoa_shots: int
    default_speed_kph: float

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        path = Path(path) if path is not None else CONFIG_PATH
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - defensive
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

        required = {
            "place",
            "network_type",
            "graph_cache",
            "edges_cache",
            "traffic_multiplier",
            "max_qubits",
            "max_quantum_stops",
            "qaoa_timeout_s",
            "qaoa_maxiter",
            "qaoa_shots",
            "default_speed_kph",
        }
        missing = required - raw.keys()
        if missing:
            raise ConfigError(f"Missing config keys: {sorted(missing)}")

        cfg = cls(
            place=str(raw["place"]),
            network_type=str(raw["network_type"]),
            graph_cache=_resolve(raw["graph_cache"]),
            edges_cache=_resolve(raw["edges_cache"]),
            traffic_multiplier=float(raw["traffic_multiplier"]),
            max_qubits=int(raw["max_qubits"]),
            max_quantum_stops=int(raw["max_quantum_stops"]),
            qaoa_timeout_s=float(raw["qaoa_timeout_s"]),
            qaoa_maxiter=int(raw["qaoa_maxiter"]),
            qaoa_shots=int(raw["qaoa_shots"]),
            default_speed_kph=float(raw["default_speed_kph"]),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.traffic_multiplier <= 0:
            raise ConfigError("traffic_multiplier must be > 0")
        if self.max_qubits < 1:
            raise ConfigError("max_qubits must be >= 1")
        if self.max_quantum_stops < 1:
            raise ConfigError("max_quantum_stops must be >= 1")
        if self.max_quantum_stops**2 > self.max_qubits:
            raise ConfigError(
                "max_quantum_stops**2 exceeds max_qubits "
                f"({self.max_quantum_stops}^2 > {self.max_qubits})"
            )
        if self.qaoa_timeout_s <= 0:
            raise ConfigError("qaoa_timeout_s must be > 0")
        if self.qaoa_maxiter < 1:
            raise ConfigError("qaoa_maxiter must be >= 1")
        if self.qaoa_shots < 1:
            raise ConfigError("qaoa_shots must be >= 1")


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_dirs() -> None:
    """Create runtime directories (safe to call repeatedly)."""
    for directory in (CACHE_DIR, CURATED_DIR, MANIFEST_DIR, SCENARIO_DIR, ARTIFACT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
