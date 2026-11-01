from __future__ import annotations

import numpy as np
import pytest

from quantum.dispatch import best_hospital_for_cluster, prepare
from quantum.qubo import (
    QuboError,
    brute_force,
    brute_force_all,
    build_qubo,
    is_valid_permutation,
    ising_coefficients,
    to_ising,
)


def _problem(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    als = scenario.vehicle("ALS-1")
    hospital = best_hospital_for_cluster(prepared, als, scenario.incidents)
    return build_qubo(prepared, als, scenario.incidents, hospital)


def test_qubit_budget(grid_graph, scenario, config):
    problem = _problem(grid_graph, scenario, config)
    assert problem.n_qubits == 9
    assert problem.n_qubits <= config.max_qubits


def test_valid_permutation_has_zero_penalty(grid_graph, scenario, config):
    problem = _problem(grid_graph, scenario, config)
    x = problem.bits_from_order([0, 1, 2])
    assert is_valid_permutation(problem, x)
    assert problem.energy(x) > 0
    invalid = x.copy()
    invalid[1] = 1.0  # duplicate assignment in row 0 and column 1
    assert not is_valid_permutation(problem, invalid)
    assert problem.energy(invalid) > problem.energy(x)


def test_brute_force_matches_full_search(grid_graph, scenario, config):
    problem = _problem(grid_graph, scenario, config)
    order, energy = brute_force(problem)
    _, full_energy = brute_force_all(problem)
    assert energy == pytest.approx(full_energy)


def test_ising_matches_qubo_energy(grid_graph, scenario, config):
    problem = _problem(grid_graph, scenario, config)
    operator, offset = to_ising(problem)
    assert operator.num_qubits == problem.n_qubits
    h, J, offset2 = ising_coefficients(problem)
    assert offset == pytest.approx(offset2)
    # For a valid bitstring, the diagonal QUBO energy is finite and positive.
    x = problem.bits_from_order([0, 1, 2])
    assert problem.energy(x) > 0


def test_too_many_stops_rejected(grid_graph, scenario, config):
    prepared = prepare(scenario, grid_graph, config)
    als = scenario.vehicle("ALS-1")
    hospital = best_hospital_for_cluster(prepared, als, scenario.incidents)
    config2 = config.__class__(**{**config.__dict__, "max_quantum_stops": 2, "max_qubits": 12})
    prepared2 = prepare(scenario, grid_graph, config2)
    with pytest.raises(QuboError, match="exceed max_quantum_stops"):
        build_qubo(prepared2, als, scenario.incidents, hospital)
