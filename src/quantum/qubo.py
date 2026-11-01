"""QUBO construction and Ising mapping for a single vehicle's stop order.

For ``m`` incidents the model uses ``m**2`` binary variables:
``x[i, t] = 1`` when incident ``i`` is visited at position ``t`` (0-based).
The depot is fixed before position 0 and the hospital after position ``m-1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

import numpy as np
from qiskit.quantum_info import SparsePauliOp

from quantum.config import Config
from quantum.dispatch import PreparedProblem, route_leg
from quantum.problem import URGENCY_STEP_SECONDS, Hospital, Incident, Vehicle


class QuboError(RuntimeError):
    """Raised when a cluster cannot be encoded within the qubit budget."""


@dataclass(frozen=True)
class QuboProblem:
    Q: np.ndarray
    n_qubits: int
    n_stops: int
    constant: float
    incident_ids: list[str]

    def index(self, incident_index: int, position: int) -> int:
        return incident_index * self.n_stops + position

    def energy(self, x: np.ndarray) -> float:
        return float(self.constant + x @ self.Q @ x)

    def bits_from_order(self, order: list[int]) -> np.ndarray:
        if sorted(order) != list(range(self.n_stops)):
            raise QuboError("order must be a permutation of incident indices")
        x = np.zeros(self.n_qubits, dtype=float)
        for position, incident_index in enumerate(order):
            x[self.index(incident_index, position)] = 1.0
        return x

    def order_from_bits(self, x: np.ndarray) -> list[int]:
        if len(x) != self.n_qubits:
            raise QuboError("bit vector length does not match qubit count")
        matrix = x.reshape(self.n_stops, self.n_stops)
        # Greedy maximum-weight assignment, then fill any holes.
        order: list[int] = []
        used: set[int] = set()
        for position in range(self.n_stops):
            candidates = [
                (matrix[i, position], i) for i in range(self.n_stops) if i not in used
            ]
            _, chosen = max(candidates, key=lambda item: (item[0], -item[1]))
            order.append(chosen)
            used.add(chosen)
        return order


def build_qubo(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    incidents: list[Incident],
    hospital: Hospital,
    penalty: float | None = None,
    patient_hospitals: dict[str, str] | None = None,
) -> QuboProblem:
    m = len(incidents)
    if m < 2:
        raise QuboError("A quantum subproblem needs at least 2 stops")
    if m > prepared.cfg.max_quantum_stops:
        raise QuboError(
            f"{m} stops exceed max_quantum_stops={prepared.cfg.max_quantum_stops}"
        )
    n = m * m
    if n > prepared.cfg.max_qubits:
        raise QuboError(f"{n} qubits exceed max_qubits={prepared.cfg.max_qubits}")

    hospital_by_id = patient_hospitals or {
        incident.id: hospital.id for incident in incidents
    }
    depot_to = [
        route_leg(prepared, vehicle, vehicle.id, incident.id).travel_time_s
        for incident in incidents
    ]
    to_hospital = [
        route_leg(
            prepared, vehicle, incident.id, hospital_by_id[incident.id]
        ).travel_time_s
        for incident in incidents
    ]
    if patient_hospitals:
        # After incident i the vehicle drops patient i at hospital_i, then
        # continues to incident j. Include that hospital detour in the
        # transition cost so the quantum order matches the simulated route.
        between = [
            [
                (
                    route_leg(
                        prepared, vehicle, a.id, hospital_by_id[a.id]
                    ).travel_time_s
                    + route_leg(
                        prepared, vehicle, hospital_by_id[a.id], b.id
                    ).travel_time_s
                )
                if a.id != b.id
                else 0.0
                for b in incidents
            ]
            for a in incidents
        ]
    else:
        between = [
            [
                route_leg(prepared, vehicle, a.id, b.id).travel_time_s
                if a.id != b.id
                else 0.0
                for b in incidents
            ]
            for a in incidents
        ]

    max_travel = max(depot_to + to_hospital + [value for row in between for value in row])
    max_urgency = max(
        URGENCY_STEP_SECONDS * incident.severity * m for incident in incidents
    )
    if penalty is None:
        penalty = 2.0 * max_travel + max_urgency + 1.0

    Q = np.zeros((n, n), dtype=float)
    problem = QuboProblem(
        Q=Q,
        n_qubits=n,
        n_stops=m,
        constant=0.0,
        incident_ids=[incident.id for incident in incidents],
    )

    # Travel: depot -> first, incident -> incident, last -> hospital.
    for i in range(m):
        Q[problem.index(i, 0), problem.index(i, 0)] += depot_to[i]
        Q[problem.index(i, m - 1), problem.index(i, m - 1)] += to_hospital[i]
    for t in range(m - 1):
        for i in range(m):
            for j in range(m):
                if i != j:
                    Q[problem.index(i, t), problem.index(j, t + 1)] += between[i][j]

    # Triage urgency: same position-based model as the classical ordering.
    for i, incident in enumerate(incidents):
        for t in range(m):
            Q[problem.index(i, t), problem.index(i, t)] += (
                URGENCY_STEP_SECONDS * incident.severity * (t + 1)
            )

    # One incident per position and one position per incident.
    constant = 0.0
    for t in range(m):
        for i in range(m):
            Q[problem.index(i, t), problem.index(i, t)] -= penalty
        for i in range(m):
            for j in range(i + 1, m):
                Q[problem.index(i, t), problem.index(j, t)] += 2.0 * penalty
        constant += penalty
    for i in range(m):
        for t in range(m):
            Q[problem.index(i, t), problem.index(i, t)] -= penalty
        for t in range(m):
            for u in range(t + 1, m):
                Q[problem.index(i, t), problem.index(i, u)] += 2.0 * penalty
        constant += penalty

    return QuboProblem(
        Q=Q,
        n_qubits=n,
        n_stops=m,
        constant=constant,
        incident_ids=problem.incident_ids,
    )


def ising_coefficients(problem: QuboProblem) -> tuple[np.ndarray, dict[tuple[int, int], float], float]:
    """Return (h, J, offset) for ``H = offset + sum h_i Z_i + sum J_ij Z_i Z_j``."""
    n = problem.n_qubits
    Q = problem.Q
    h = np.zeros(n, dtype=float)
    J: dict[tuple[int, int], float] = {}

    for i in range(n):
        h[i] = -Q[i, i] / 2.0
    for i in range(n):
        for j in range(i + 1, n):
            if Q[i, j] != 0.0:
                J[(i, j)] = Q[i, j] / 4.0
                h[i] -= Q[i, j] / 4.0
                h[j] -= Q[i, j] / 4.0

    offset = problem.constant + sum(Q[i, i] / 2.0 for i in range(n))
    offset += sum(value for value in J.values())
    return h, J, float(offset)


def to_ising(problem: QuboProblem) -> tuple[SparsePauliOp, float]:
    """Map ``x_i = (1 - Z_i) / 2`` and return (operator, offset)."""
    n = problem.n_qubits
    h, J, offset = ising_coefficients(problem)

    terms: list[tuple[str, float]] = []
    for i in range(n):
        if h[i] != 0.0:
            terms.append((_pauli(n, {i: "Z"}), float(h[i])))
    for (i, j), value in J.items():
        terms.append((_pauli(n, {i: "Z", j: "Z"}), float(value)))
    if not terms:
        terms.append((_pauli(n, {}), 0.0))
    return SparsePauliOp.from_list(terms), offset


def _pauli(n: int, positions: dict[int, str]) -> str:
    chars = ["I"] * n
    for index, symbol in positions.items():
        chars[n - 1 - index] = symbol
    return "".join(chars)


def brute_force(problem: QuboProblem) -> tuple[list[int], float]:
    """Exact optimum over the valid permutation subspace."""
    best_order: list[int] | None = None
    best_energy = float("inf")
    for order in permutations(range(problem.n_stops)):
        x = problem.bits_from_order(list(order))
        energy = problem.energy(x)
        if energy < best_energy:
            best_energy = energy
            best_order = list(order)
    if best_order is None:  # pragma: no cover - m >= 2 guarantees a permutation
        raise QuboError("No permutation found")
    return best_order, best_energy


def brute_force_all(problem: QuboProblem) -> tuple[np.ndarray, float]:
    """Exact optimum over all 2^n bitstrings (validation only, n <= 12)."""
    if problem.n_qubits > 12:
        raise QuboError("Full brute force is capped at 12 qubits")
    best_x: np.ndarray | None = None
    best_energy = float("inf")
    for value in range(1 << problem.n_qubits):
        x = np.array([(value >> k) & 1 for k in range(problem.n_qubits)], dtype=float)
        energy = problem.energy(x)
        if energy < best_energy:
            best_energy = energy
            best_x = x
    if best_x is None:  # pragma: no cover
        raise QuboError("Brute force failed")
    return best_x, best_energy


def is_valid_permutation(problem: QuboProblem, x: np.ndarray) -> bool:
    matrix = np.asarray(x, dtype=float).reshape(problem.n_stops, problem.n_stops)
    return bool(
        np.allclose(matrix.sum(axis=0), 1.0)
        and np.allclose(matrix.sum(axis=1), 1.0)
        and np.allclose(matrix, np.round(matrix))
    )
