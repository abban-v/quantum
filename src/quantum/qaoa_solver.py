"""QAOA execution on local Qiskit Aer, plus bitstring repair.

The solver optimises the order of a small set of stops for one vehicle. The
hospital is chosen classically beforehand, so the quantum subproblem stays
inside the demo's 12-qubit budget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from scipy.optimize import linear_sum_assignment, minimize

from quantum.config import Config
from quantum.dispatch import (
    DispatchError,
    PreparedProblem,
    RoutePlan,
    order_cluster,
    order_patient_cluster,
    plan_for_order,
)
from quantum.problem import Hospital, Incident, Vehicle
from quantum.qubo import (
    QuboError,
    QuboProblem,
    brute_force,
    build_qubo,
    is_valid_permutation,
    ising_coefficients,
)


class _Timeout(Exception):
    pass


@dataclass
class QAOAResult:
    quantum_plan: RoutePlan
    classical_plan: RoutePlan
    order_indices: list[int]
    order_ids: list[str]
    energy: float
    optimal_energy: float
    approximation_ratio: float
    raw_feasibility: float
    repaired_feasibility: float
    samples: int
    iterations: int
    runtime_s: float
    params: list[float]
    fallback: bool = False
    notes: list[str] = field(default_factory=list)


def build_circuit(
    n: int,
    h: np.ndarray,
    J: dict[tuple[int, int], float],
    params: list[float],
) -> QuantumCircuit:
    if len(params) % 2 != 0:
        raise ValueError("params must be [gamma_1, beta_1, ..., gamma_p, beta_p]")
    layers = len(params) // 2
    circuit = QuantumCircuit(n, name="qevr_qaoa")
    circuit.h(range(n))
    for layer in range(layers):
        gamma, beta = params[2 * layer], params[2 * layer + 1]
        for i in range(n):
            if h[i] != 0.0:
                circuit.rz(2.0 * gamma * h[i], i)
        for (i, j), value in J.items():
            if value != 0.0:
                circuit.rzz(2.0 * gamma * value, i, j)
        for i in range(n):
            circuit.rx(2.0 * beta, i)
    return circuit


def _statevector(circuit: QuantumCircuit) -> Statevector:
    return Statevector.from_instruction(circuit)


def _diagonal_energies(problem: QuboProblem) -> np.ndarray:
    """QUBO energy of every computational-basis state (n <= 12)."""
    size = 1 << problem.n_qubits
    indices = np.arange(size)
    bits = ((indices[:, None] >> np.arange(problem.n_qubits)) & 1).astype(float)
    return np.einsum("ij,jk,ik->i", bits, problem.Q, bits) + problem.constant


def _energy(sv: Statevector, diagonal: np.ndarray) -> float:
    probabilities = np.asarray(sv.probabilities(), dtype=float)
    return float(probabilities @ diagonal)


def _classical_plan(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    incidents: list[Incident],
    hospital: Hospital,
    patient_hospitals: dict[str, str] | None = None,
) -> tuple[RoutePlan, list[str]]:
    if patient_hospitals:
        order, _, _, hospital_by_id = order_patient_cluster(
            prepared, vehicle, incidents, patient_hospitals
        )
        order_ids = [incident.id for incident in order]
        return (
            plan_for_order(
                prepared,
                vehicle,
                incidents,
                hospital,
                order_ids,
                patient_hospitals=hospital_by_id,
            ),
            order_ids,
        )
    order, _, _ = order_cluster(prepared, vehicle, incidents, hospital)
    order_ids = [incident.id for incident in order]
    return plan_for_order(prepared, vehicle, incidents, hospital, order_ids), order_ids


def _initial_points(p: int) -> list[list[float]]:
    base = [(0.2, 0.8), (0.5, 0.5), (0.8, 1.2), (1.0, 0.3)]
    return [[value for _ in range(p) for value in pair] for pair in base]


def run_qaoa(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    incidents: list[Incident],
    hospital: Hospital,
    cfg: Config,
    seed: int = 7,
    p: int = 1,
    patient_hospitals: dict[str, str] | None = None,
) -> QAOAResult:
    start = time.monotonic()
    classical_plan, classical_ids = _classical_plan(
        prepared, vehicle, incidents, hospital, patient_hospitals
    )

    try:
        problem = build_qubo(
            prepared,
            vehicle,
            incidents,
            hospital,
            patient_hospitals=patient_hospitals,
        )
    except QuboError as exc:
        return _fallback(
            prepared, vehicle, incidents, hospital, classical_plan, classical_ids,
            start, f"QUBO build failed: {exc}",
        )

    h, J, offset = ising_coefficients(problem)
    diagonal = _diagonal_energies(problem)

    iterations = 0
    timed_out = False
    # (repaired_energy, params, raw_energy, probs)
    best: tuple[float, list[float], float, np.ndarray] | None = None

    for start_point in _initial_points(p):
        local_energy = float("inf")
        local_params = list(start_point)

        def objective(params: np.ndarray) -> float:
            nonlocal local_energy, local_params, iterations
            if time.monotonic() - start > cfg.qaoa_timeout_s:
                raise _Timeout
            circuit = build_circuit(problem.n_qubits, h, J, list(params))
            sv = _statevector(circuit)
            value = _energy(sv, diagonal)
            iterations += 1
            if value < local_energy:
                local_energy = value
                local_params = list(params)
            return value

        try:
            minimize(
                objective,
                np.array(start_point, dtype=float),
                method="COBYLA",
                options={"maxiter": cfg.qaoa_maxiter, "tol": 1e-6, "rhobeg": 0.2},
            )
        except _Timeout:
            timed_out = True
        except Exception as exc:  # pragma: no cover - defensive
            return _fallback(
                prepared, vehicle, incidents, hospital, classical_plan, classical_ids,
                start, f"Optimizer failed: {exc}",
            )

        if not np.isfinite(local_energy):
            continue
        circuit = build_circuit(problem.n_qubits, h, J, local_params)
        probs = np.asarray(_statevector(circuit).probabilities(), dtype=float)
        order = _repair(_marginals(probs, problem.n_qubits), problem.n_stops)
        repaired = problem.energy(problem.bits_from_order(order))
        if best is None or repaired < best[0]:
            best = (repaired, local_params, local_energy, probs)
        if timed_out:
            break

    if best is None:
        return _fallback(
            prepared, vehicle, incidents, hospital, classical_plan, classical_ids,
            start, "Optimizer produced no finite energy.",
        )
    repaired_energy, params, energy, probs = best
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(probs), size=cfg.qaoa_shots, p=probs)

    valid = 0
    for index in indices:
        x = np.array([(int(index) >> k) & 1 for k in range(problem.n_qubits)], dtype=float)
        if is_valid_permutation(problem, x):
            valid += 1
    raw_feasibility = valid / cfg.qaoa_shots

    marginals = _marginals(probs, problem.n_qubits)
    order = _repair(marginals, problem.n_stops)

    opt_order, opt_energy = brute_force(problem)
    ratio = 0.0
    if repaired_energy > 0:
        ratio = min(1.0, max(0.0, opt_energy / repaired_energy))

    order_ids = [problem.incident_ids[i] for i in order]
    quantum_plan = plan_for_order(
        prepared,
        vehicle,
        incidents,
        hospital,
        order_ids,
        mode="quantum",
        patient_hospitals=patient_hospitals,
    )

    notes: list[str] = []
    if timed_out:
        notes.append("Optimizer hit the time budget; results are from the best angles seen.")
    if energy > opt_energy + 1e-6:
        notes.append(
            f"QAOA energy {energy:.1f} above exact optimum {opt_energy:.1f}."
        )
    if repaired_energy > opt_energy + 1e-6:
        notes.append("Repaired order is not the exact QUBO optimum.")
    if not np.allclose(order, opt_order):
        notes.append("QAOA order differs from the exact brute-force order.")

    return QAOAResult(
        quantum_plan=quantum_plan,
        classical_plan=classical_plan,
        order_indices=order,
        order_ids=order_ids,
        energy=energy,
        optimal_energy=opt_energy,
        approximation_ratio=ratio,
        raw_feasibility=raw_feasibility,
        repaired_feasibility=1.0,
        samples=cfg.qaoa_shots,
        iterations=iterations,
        runtime_s=time.monotonic() - start,
        params=params,
        fallback=False,
        notes=notes,
    )


def _marginals(probs: np.ndarray, n: int) -> np.ndarray:
    size = 1 << n
    if len(probs) != size:
        raise ValueError("probability vector length does not match qubit count")
    marginals = np.zeros(n, dtype=float)
    for k in range(n):
        mask = np.array([(index >> k) & 1 for index in range(size)], dtype=bool)
        marginals[k] = probs[mask].sum()
    return marginals


def _repair(marginals: np.ndarray, m: int) -> list[int]:
    matrix = np.asarray(marginals, dtype=float).reshape(m, m)
    rows, cols = linear_sum_assignment(-matrix)
    order = [0] * m
    for incident_index, position in zip(rows, cols):
        order[position] = int(incident_index)
    return order


def _fallback(
    prepared: PreparedProblem,
    vehicle: Vehicle,
    incidents: list[Incident],
    hospital: Hospital,
    classical_plan: RoutePlan,
    classical_ids: list[str],
    start: float,
    reason: str,
) -> QAOAResult:
    notes = [reason, "Showing the classical route instead."]
    return QAOAResult(
        quantum_plan=classical_plan,
        classical_plan=classical_plan,
        order_indices=[],
        order_ids=classical_ids,
        energy=float("nan"),
        optimal_energy=float("nan"),
        approximation_ratio=0.0,
        raw_feasibility=0.0,
        repaired_feasibility=1.0,
        samples=0,
        iterations=0,
        runtime_s=time.monotonic() - start,
        params=[],
        fallback=True,
        notes=notes,
    )
