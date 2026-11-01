# Quantum-Assisted Emergency Vehicle Routing (Q-EVR)

> **Quantum and hybrid optimization for time-critical emergency response under dynamic traffic, road closures, patient triage priorities, capacity constraints, and fleet de-confliction.**

---

## 1. Introduction & Problem Statement

In time-critical emergencies—such as multi-point fire breakouts, toxic exposures, or acute medical incidents—seconds count. Inefficient vehicle dispatch and routing directly increase emergency response latency, worsen patient outcomes, and risk severe casualties.

### Key Real-World Scenarios

#### Scenario A: Dynamic En-Route Re-Routing & Capacity-Aware Detour (Fever vs. Snake Bite)
Imagine an ambulance has picked up **Patient A**, who has a mild fever (low urgency), and is en route to the hospital:
- While in transit, an extreme, life-threatening emergency occurs nearby: **Patient B** suffers a neurotoxic **snake bite** (high fatality risk without rapid antivenom administration).
- **Capacity-Aware Detour:** If the ambulance has available patient capacity ($Q \ge 2$), the system dynamically evaluates a detour: divert immediately to stabilize and board Patient B, then proceed to the hospital with both patients. Because a fever can safely wait while a snake bite can turn fatal within minutes, triage urgency strictly justifies the detour.
- **Capacity Exhaustion:** If the vehicle has reached full capacity ($Q = 1$), the system disallows the detour and immediately routes the nearest idle unit instead.

#### Scenario B: Idle Ambulance Dispatch Prioritization
- When an ambulance is idle or empty at a depot or staging post, it must **prioritize life-threatening emergencies (e.g., snake bite, cardiac arrest) over non-critical calls (e.g., mild fever)**.
- Dispatch sequencing must prevent high-severity patients from starving for resources simply because a low-severity call was logged minutes earlier.

#### Scenario C: Multi-Ambulance De-Confliction & Anti-Redundancy
- In high-stress operations, uncoordinated dispatch often leads to **multiple emergency vehicles converging on the exact same incident location** with no operational justification.
- This creates severe resource waste: other critical zones are starved of coverage, and response corridors become bottlenecked. The routing engine must strictly enforce single-vehicle coverage per incident (unless multiple units are explicitly requested based on casualty headcount).

#### Scenario D: Dynamic Road Network & Environmental Realities
- **Temporal Traffic Conditions:** Congestion varies dramatically by time of day and day of week (e.g., Monday 9:00 AM rush hour vs. Saturday 9:00 PM).
- **Dynamic Road Blockages:** Debris, fallen power lines, flash floods, or active construction create sudden road closures, requiring immediate dynamic rerouting.
- **Resource & Workforce Availability:** Limited ambulance fleets, crew shifts, and hospital capacity impose hard operational constraints.
- **Incomplete Real-World Data:** Emergency teams frequently operate under noisy or partial sensor data.

---

### The Computational Challenge

Standard shortest-path algorithms (like Dijkstra or A*) find optimal paths between single pairs of points. However, dynamically coordinating multiple vehicles visiting multiple incidents under conflicting multi-objective constraints:
$$\text{Distance} + \text{Live Congestion} + \text{Triage Urgency} + \text{Vehicle Capacity} + \text{Anti-Redundancy}$$
is a variant of the **Capacitated Vehicle Routing Problem with Time Windows and Priority (CVRPTW-P)**, which is strictly **NP-hard**.

As the number of response nodes and vehicles grows, the solution space explodes factorially:
$$\mathcal{O}\left( \frac{(N-1)!}{(N-K)!} \cdot K^N \right)$$
Finding global or near-global optima within critical response seconds challenges classical heuristics, making this an ideal domain for **quantum and hybrid quantum-classical optimization**.

---

## 2. Our Ideas & Core Approach

We address this emergency routing challenge by formulating it as a **Hybrid Quantum-Classical Optimization Pipeline**.

```
[City Network & Real-Time Sensor / Dispatch Feed]
  (Locations, Travel Times, Congestion Multipliers, Road Blocks, Patient Triage Levels, Vehicle Capacities)
                                      │
                                      ▼
                         [1. Classical Preprocessing]
                           ├─ Shortest-path time matrix with dynamic traffic & blockages
                           ├─ Dynamic event listener (detects new critical calls, e.g., snake bite)
                           ├─ Capacity validation (checks onboard count vs. max capacity Q)
                           └─ Qubit-reduction: Fix vehicle starting locations & eliminate dead arcs
                                      │
                                      ▼
                          [2. QUBO / Ising Formulation]
                           ├─ Transition Cost + Congestion Matrix
                           ├─ Triage Urgency Penalties (Heavily penalize late arrival for severe cases)
                           ├─ Anti-Redundancy Constraint (Exactly one vehicle per incident)
                           └─ Valid-Route Penalty Constraints (One-node-per-step, visit-once)
                                      │
                                      ▼
                       [3. Quantum Optimization (QAOA)]
                           ├─ Parameterized Quantum Circuit (Cost & Mixer layers)
                           ├─ Quantum State Superposition & Interference
                           └─ Classical Optimizer Loop (COBYLA / SPSA updating γ, β)
                                      │
                                      ▼
                        [4. Postprocessing & Evaluation]
                           ├─ Bitstring measurement & route decoding
                           ├─ Light repair heuristic for constraint satisfaction
                           └─ Benchmark comparison against Classical Baselines
```

### Key Conceptual Pillars

1. **Non-Linear Triage Urgency Penalties:**
   To guarantee that a critical snake-bite victim is reached before a fever patient, urgency penalty weights are assigned non-linearly:
   $$\lambda_{\text{snake bite}} \gg \lambda_{\text{fever}}$$
   Visiting a snake-bite patient at step $t \ge 2$ incurs a massive penalty in the Hamiltonian, forcing the optimizer to place this visit at the earliest feasible step.

2. **Capacity-Aware Dynamic Re-Optimization:**
   When an active ambulance carrying a fever patient receives a new alert, the system evaluates the state:
   $$\text{Current Load} < Q_{\max} \implies \text{Trigger localized QUBO re-solve with vehicle's current GPS as new origin.}$$
   If capacity is exhausted, the call is routed to the nearest idle ambulance.

3. **Fleet-Wide Anti-Redundancy Constraint:**
   The formulation enforces mutual exclusion across vehicles so that no two ambulances are assigned to the same incident location.

4. **Qubit-Efficient Encoding for NISQ Hardware:**
   Standard formulations require $N^2$ qubits per vehicle. By anchoring known vehicle positions at $t=0$ and eliminating infeasible transitions, we compress the variable space to fit cleanly within current Qiskit simulators and IBM Quantum QPUs.

5. **Quantum Advantage in Rugged Energy Landscapes:**
   Triage urgency and spatial proximity pull the solution in opposite directions (e.g., the closest patient has a minor fever, while the life-threatening snake bite is 3 km further). Classical greedy algorithms get trapped in suboptimal local minima; QAOA leverages quantum superposition and tunneling across barrier potentials to explore non-convex solution spaces.

---

## 3. Mathematical Formulation (QUBO & Ising Mapping)

We formulate the multi-vehicle, multi-casualty emergency dispatch as a **Quadratic Unconstrained Binary Optimization (QUBO)** problem.

### A. Decision Variables
Let $K$ be the number of vehicles, $N$ be the total locations ($0$ is hospital/depot, $1 \dots N-1$ are incident sites), and $T$ be the maximum route steps.
For vehicle $v \in \{1, \dots, K\}$, location $i \in \{0, \dots, N-1\}$, and step $t \in \{0, \dots, T-1\}$:
$$x_{i, t}^{(v)} \in \{0, 1\}$$
where $x_{i, t}^{(v)} = 1$ if vehicle $v$ visits location $i$ at step $t$, and $0$ otherwise.

---

### B. Objective Function

#### 1. Transition Cost & Dynamic Traffic
$$H_{\text{cost}} = \sum_{v=1}^{K} \sum_{t=0}^{T-2} \sum_{i=0}^{N-1} \sum_{j=0, j \neq i}^{N-1} C_{ij}(t) \cdot x_{i, t}^{(v)} \cdot x_{j, t+1}^{(v)}$$
where:
$$C_{ij}(t) = d_{ij} \times \tau_{ij}(\text{day}, \text{hour}) + \delta_{\text{blockage}}(i, j)$$
- $d_{ij}$: Physical distance between locations $i$ and $j$.
- $\tau_{ij}(\text{day}, \text{hour})$: Empirical traffic congestion multiplier for that day and hour.
- $\delta_{\text{blockage}}(i, j)$: Infinite or large penalty if road $(i, j)$ is closed or under construction.

#### 2. Patient Triage Urgency (Snake Bite vs. Fever)
$$H_{\text{urgency}} = \sum_{v=1}^{K} \sum_{i=1}^{N-1} \sum_{t=1}^{T-1} \left( \lambda_i \cdot t \right) x_{i, t}^{(v)}$$
- For a **mild fever**: $\lambda_{\text{fever}} = 1$ (low delay penalty).
- For a **snake bite / cardiac emergency**: $\lambda_{\text{snake bite}} = 50$ (severe delay penalty).
The optimizer is heavily penalized for any delay in visiting critical patients, naturally promoting detours when capacity permits.

---

### C. Constraint Penalty Terms

Because QUBO is unconstrained, operational constraints are enforced via quadratic penalty terms ($A, B, D \gg \max(C_{ij})$):

#### 1. One Location per Step (Per Vehicle)
$$P_{\text{step}} = A \sum_{v=1}^{K} \sum_{t=0}^{T-1} \left( \sum_{i=0}^{N-1} x_{i, t}^{(v)} - 1 \right)^2$$

#### 2. Anti-Redundancy & Unique Coverage (No Duplicate Ambulances)
To ensure multiple ambulances do not go to the same source without reason, each incident site $i \ge 1$ must be visited exactly once across the entire fleet:
$$P_{\text{unique\_coverage}} = D \sum_{i=1}^{N-1} \left( \sum_{v=1}^{K} \sum_{t=0}^{T-1} x_{i, t}^{(v)} - 1 \right)^2$$

#### 3. Vehicle Capacity Constraint
For vehicle $v$ with capacity $Q_v$ carrying current passengers $p_v$:
$$\sum_{i=1}^{N-1} \sum_{t=1}^{T-1} x_{i, t}^{(v)} \le Q_v - p_v$$
Enforced either by quadratic slack variables or classical pre-filtering of candidate paths.

---

### D. Mapping to Quantum Hamiltonian
Binary variables are mapped to quantum spin operators via:
$$x_{i, t}^{(v)} = \frac{I - Z_{i, t}^{(v)}}{2}$$
Yielding the Problem Cost Hamiltonian:
$$H_C = \sum_{k} h_k Z_k + \sum_{k < l} J_{kl} Z_k Z_l + \text{offset}$$
where each qubit corresponds to an assigned $(v, i, t)$ tuple.

---

## 4. What We Plan to Do

- [x] Define real-world emergency dispatch use cases (fire emergency, dynamic detour for snake bite vs. fever, anti-redundancy).
- [ ] **Synthetic Emergency Network Generator (`src/quantum/problem.py`):**
  - City graph with hospital, ambulance depots, and incident sites.
  - Triage severity attributes ($\lambda_i$) for emergencies (e.g., snake bite vs. fever).
  - Time-of-day traffic matrices and dynamic road closure flags.
- [ ] **QUBO & Hamiltonian Generator (`src/quantum/qubo.py`):**
  - Mathematical QUBO matrix builder incorporating urgency, capacity, and anti-redundancy.
  - Converts QUBO to Qiskit `SparsePauliOp` Pauli-$Z$ Hamiltonian.
  - Qubit-reduction via fixed initial coordinates.
- [ ] **Dynamic Re-Routing Trigger (`src/quantum/dynamic_dispatcher.py`):**
  - Simulates active ambulance en-route with a fever patient.
  - Receives new high-priority snake-bite call.
  - Validates onboard capacity ($Q \ge 2$) and invokes localized QUBO re-solve.
- [ ] **QAOA Circuit & Solver (`src/quantum/qaoa_solver.py`):**
  - Parameterized QAOA ansatz with $p$ layers using Qiskit 2.x and Qiskit Aer.
  - Classical optimizer loop (COBYLA/SPSA) minimizing $\langle \psi(\gamma, \beta) | H_C | \psi(\gamma, \beta) \rangle$.
- [ ] **Classical Baseline Benchmark (`src/quantum/baselines.py`):**
  - Greedy Nearest Neighbor (demonstrating how it mistakenly visits the fever patient first or sends redundant units).
  - Classical 2-Opt local search / Simulated Annealing.
  - Exact Brute-Force solver (for ground truth verification).
- [ ] **Evaluation & Visual Analytics (`src/quantum/visualize.py` & `notebooks/demo.ipynb`):**
  - Visual 2D map showing road networks, traffic congestion, detour paths, and arrival timelines.
  - Comparative metrics table (Total Response Time, Triage Delay Score, Redundancy Violations, Feasibility Rate).

---

## 5. Possible Implementation & Technology Stack

### Tech Stack
- **Language:** Python 3.12
- **Quantum SDK:** Qiskit 2.6+, Qiskit Aer 0.18+ (Noise-free and noisy statevector/sampler backends)
- **Classical Optimization:** SciPy (`minimize` with COBYLA/SLSQP), NumPy
- **Visualization:** Matplotlib, NetworkX
- **Interactive Environment:** Jupyter Notebooks

### Proposed Codebase Architecture
```text
quantum/
├── pyproject.toml                     # Project dependencies and packaging
├── README.md                          # Project documentation & formulation
├── notebooks/
│   └── emergency_routing.ipynb        # Interactive end-to-end demonstration
└── src/
    └── quantum/
        ├── __init__.py
        ├── problem.py                 # Graph generator, traffic, triage & capacity models
        ├── qubo.py                    # QUBO matrix & Pauli Hamiltonian builder
        ├── dynamic_dispatcher.py       # En-route detour & capacity logic (snake bite vs. fever)
        ├── qaoa_solver.py             # QAOA quantum execution & bitstring sampler
        ├── baselines.py               # Classical Greedy, 2-Opt, & Brute-Force
        └── visualize.py               # Matplotlib route & performance visualizer
```

### Evaluation Metrics
| Metric | Description | Target |
|---|---|---|
| **Route Feasibility (%)** | Percentage of sampled quantum bitstrings yielding valid routes | $> 90\%$ after optimization |
| **Triage Delay Score** | Cumulative delay penalty for high-severity patients (snake bite) | Minimized / Zero critical delay |
| **Redundancy Rate** | Percentage of duplicate dispatches to the same location | Exactly 0% |
| **Total Response Time** | Sum of travel times across all legs under traffic | Minimized vs. classical greedy |
| **Approximation Ratio** | Ratio of QAOA solution cost to the exact optimal cost | $\ge 0.85$ for $p=1, 2$ |

---

## 6. How to Run & Get Started

```bash
# Clone and enter the repository
cd /path/to/quantum/quantum

# Set up virtual environment and install dependencies
uv sync

# Launch the interactive demonstration notebook
uv run jupyter notebook notebooks/emergency_routing.ipynb
```
