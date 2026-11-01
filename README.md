# Quantum-Assisted Emergency Vehicle Routing (Q-EVR)

> **Hybrid quantum-classical optimization for time-critical ambulance response under dynamic traffic, patient triage priorities, specialized fleet equipment (BLS vs. ALS ventilators), hospital offload delays ("holding the wall"), rig physical clearance constraints, and capacity-aware detours.**
>
> **Featuring an Interactive Real-World Browser Map UI with Natural Language Incident Dispatch, powered by Local Quantum Simulation using Qiskit & Qiskit Aer.**

> **Status:** working demo prototype. Road geometry and hospital/station locations are real OpenStreetMap data; traffic, offload waits, incident severities, vehicle capabilities, and clearance limits are **simulated**. See [Quick start](#quick-start--run-the-demo-basic) and [`data/curated/README.md`](data/curated/README.md).

---

## Quick start — run the demo (basic)

This repository currently ships a **local Manhattan demo**. It needs no cloud account, API key, or quantum hardware.

### What you need

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/)
- Internet access **on the first run only**, to download the OpenStreetMap road graph (about 1 minute). After that the app runs from the local cache.

### Run it

```bash
cd /path/to/quantum/quantum
uv sync
uv run streamlit run app.py
```

Open <http://localhost:8501>.

Optional: pre-download the graph so the first page load is fast:

```bash
uv run python scripts/prepare_data.py
```

The graph is cached at `data/cache/manhattan_drive.graphml` (gitignored).

### Basic demo flow (about 60 seconds)

1. In the sidebar, choose preset **S4 — Multi-casualty collision**.
2. Set the **day and time**. Traffic colours on the map use a synthetic weekday/weekend profile, and the same profile changes edge travel times.
3. Click **Dispatch**. The map draws the classical route and the tables show each patient's hospital, transit, offload, total mission, equipment, specialty, and pruned-edge counts. The live simulation starts automatically.
4. Click **Run quantum**. A green repaired-QAOA overlay appears with the energy ratio, repair mass, raw feasibility, and runtime.
5. Watch the ambulances move along their routes, pick patients up, wait for the simulated offload, and deliver each patient to their own hospital. Use **Pause**, **Step**, **Reset**, and the speed slider to inspect the run.
6. Use the layer control (top right) to toggle the traffic layer, routes, hospitals, ambulances, and incidents. The map keeps the zoom and centre you choose.

### Click-to-place a custom incident

1. Set **Map click** to **Place incident** and click anywhere on the map. An orange marker is placed.
2. Type a description, for example `snake bite with difficulty breathing`.
3. Click **Dispatch**.
4. For a quantum order, tick **Multi-casualty custom (3 patients)** before dispatching. QAOA needs at least two stops.

### Edit traffic

1. Use the **Network delay multiplier** slider to scale the synthetic time-of-day profile across the whole map.
2. To change one street, either set **Map click** to **Edit traffic** and click it, or choose the street by name in the **Pick a street by name** selector.
3. Adjust the delay factor and press **Apply override** (map selection) or **Apply to street** (name selection). The next **Dispatch** uses it.
4. Use **Clear this street**, **Clear street override**, or **Clear all overrides** to return to the time-of-day profile.

### Offline basemap

Choose **Offline vector** in the sidebar to draw the cached OpenStreetMap road graph
instead of online tiles. The app then needs no network at all, including after the
graph cache exists.

### What the demo actually does

- Downloads and caches the Manhattan drive graph from OpenStreetMap.
- Parses the free-text description with rules. Ollama is optional; the demo works without it.
- Applies a **synthetic** weekday/weekend, hour-of-day traffic profile to every edge, plus optional network-wide and per-street overrides.
- Assigns vehicles, picks a hospital per patient, and computes road routes.
- For 2–3 stops, builds a 4–9 qubit QUBO, runs QAOA `p=1` on local Qiskit Aer, repairs the sampled bitstring to a valid stop order, and overlays the result.
- Runs a deterministic ambulance simulation with scene time, patient pickup, simulated offload, and per-patient delivery.
- Uses **simulated** offload waits, severities, traffic, and clearance limits. Hospital and station locations are real OSM features.


### Quantum usage in this demo

This is the part that must stay real: the demo genuinely builds and simulates a
quantum circuit, but only for the small stop-ordering subproblem.

| Stage | What runs | Where |
|---|---|---|
| Decision variables | `x[i, t]` one-hot stop/position bits for one vehicle, `m²` qubits for `m` stops (4–9 qubits in the presets) | `src/quantum/qubo.py` |
| Objective | Road travel time with the selected traffic profile, urgency delay `60 s × severity × position`, per-patient hospital detour and offload | `src/quantum/qubo.py` |
| Constraints | One stop per position and one position per stop, plus the demo's `max_quantum_stops² <= max_qubits` guard | `src/quantum/qubo.py` |
| Circuit | QAOA `p=1`, Hadamard mixer, `RZ`/`RZZ` cost layers, `RX` mixer | `src/quantum/qaoa_solver.py` |
| Execution | Exact statevector on local Qiskit Aer; COBYLA optimises `(γ, β)` | `src/quantum/qaoa_solver.py` |
| Decoding | Hungarian repair of the measured marginals to a valid permutation, then the classical route builder computes the physical route | `src/quantum/qaoa_solver.py` |
| Comparison | Classical order vs repaired quantum order, exact brute-force QUBO optimum for the energy ratio | `src/quantum/qaoa_solver.py` |

Honest boundaries:

- **No quantum hardware and no cloud.** Everything is local statevector simulation.
- **No live traffic, no live ED offload, no real clearance data.** Those are synthetic demo values and are labelled as such in the UI and data files.
- **No asynchronous background solve.** QAOA runs synchronously behind a spinner in a large-stack thread. A run typically takes well under a second to a few seconds.
- **No 16-qubit claim.** The shipped guard is `max_quantum_stops=3` and `max_qubits=12`; presets use 4–9 qubits.
- **Classical work stays classical.** Graph pruning, snapping, hospital selection, and route timing are classical by design.

### Implementation status

| Area | Status |
|---|---|
| OSM graph download/cache, snapping, clearance pruning | Implemented |
| Rule-based triage parser, optional local Ollama fallback | Implemented |
| Per-patient hospital choice and multi-stop routing | Implemented |
| Synthetic day/time traffic plus manual street overrides | Implemented |
| QUBO + QAOA statevector + bitstring repair | Implemented |
| Interactive map, click-to-place, traffic editor, offline vector basemap | Implemented |
| Ambulance simulation with pickup/offload/delivery | Implemented |
| Live traffic or live ED offload feeds | Not implemented (synthetic only) |
| Quantum hardware execution or error mitigation | Not implemented |
| Dynamic en-route rerouting during the simulation | Not implemented |
| 2-Opt / simulated-annealing benchmark suite | Not implemented |
| Jupyter benchmark notebook | Not implemented |

### Useful commands

```bash
uv run pytest -q
uv run python scripts/run_scenario.py --scenario S4
uv run python scripts/run_scenario.py --scenario S4 --cluster ALS-01
```

### If something goes wrong

- **Port already in use:** `uv run streamlit run app.py --server.port 8502`
- **Graph download fails:** retry once; the public Overpass API is occasionally rate-limited.
- **No “Run quantum” button:** the plan has only one stop. Use preset S4 or the multi-casualty option.
- **Start over:** click **Reset to preset** in the sidebar.

---

## 1. Introduction & Problem Statement

In time-critical medical emergencies—such as acute respiratory arrest, cardiac emergencies, major trauma, or neurotoxic envenomation—seconds count. Inefficient ambulance dispatch, mismatched clinical vehicle equipment, and uncoordinated hospital destination routing directly increase response latency, worsen patient morbidity, and risk preventable fatalities.

Conversations with frontline paramedics (on *r/ems*) and 911 dispatchers (*r/911dispatchers*) reveal critical real-world failure modes that traditional routing algorithms fail to address. We model these directly in our system:

---

### The Interactive Real-World Vision: Browser Map & Text Dispatch

Rather than existing as an abstract math model, this project delivers an **interactive browser-based emergency command dashboard**:

1. **Interactive Real-World Map:** A dynamic city map (rendered in the browser) displaying road networks, synthetic time-of-day traffic congestion, low overpasses, weight-restricted bridges, candidate regional hospitals with **simulated** emergency department (ED) offload queues, and geographically stationed ambulances (Basic Life Support / BLS, and Advanced Life Support / ALS Mobile ICUs equipped with mechanical ventilators).
2. **Click-to-Incident Dispatch:** The operator clicks any location on the map to place an active incident marker.
3. **Natural Language Emergency Specification ("In Text"):** The user specifies the emergency in plain text. Examples:
   - *"Apartment building fire victim, severe smoke inhalation with acute respiratory distress, cyanotic."*
   - *"Hiker bitten by venomous viper on nature trail, swelling rapidly, difficulty breathing."*
   - *"Elderly patient with low-grade fever and mild dehydration."*
   - *"Severe motor vehicle collision with massive trauma, multi-system injury."*
4. **Automated Requirement & Triage Extraction:** The system automatically analyzes the text prompt and extracts the underlying mathematical parameters:
   - **Triage Urgency Score ($\lambda_i$):** (e.g., Critical $\lambda = 50$ for respiratory arrest/snake bite vs. Low $\lambda = 1$ for fever).
   - **Clinical Equipment Demand ($E_i$):** (Ventilator/ALS unit required vs. standard stretcher/BLS transport).
   - **Destination Hospital Specialty Selection:** (Burn Center for fire victims, Comprehensive Stroke Center, Level 1 Trauma for head injuries, factoring simulated ED offload wait times).
   - **Rig Physical Clearance:** (Filtering low overpasses and bridge weight limits for heavy Mobile ICU rigs).
5. **Local Quantum Circuit Execution via Qiskit & Qiskit Aer:** The stop-ordering subproblem is compiled into an Ising Hamiltonian and solved entirely on your local machine with Qiskit Aer **statevector** simulation, driving the classical-quantum hybrid loop (COBYLA) with zero cloud dependencies or external API keys. Shot-based noise models and hardware execution are not part of the demo.
6. **Simulated Route Animation:** Dispatching starts a deterministic simulation that moves the dispatched ambulances along their computed routes, picks patients up, waits for the simulated offload, and delivers each patient to their assigned hospital. Pause, step, reset, and speed controls are available.

---

### Key Real-World Scenarios & Community Pain Points

#### Scenario A: The "Holding the Wall" Crisis & Hospital Offload Delays (Community Pain Point 1)
- **The Ground Reality:** Paramedics routinely face the "holding the wall" crisis: transporting a patient in 8 minutes, only to spend **2 to 4 hours parked in the emergency department hallway** waiting for an open hospital bed to transfer care. This locks ambulances out of service, causing citywide **"Level Zero"** (zero available ambulances in the entire municipality for incoming 911 calls).
- **The Solution (End-to-End Hospital Offload & Specialty Routing):** The routing engine does not simply send patients to the geographically closest hospital. It evaluates the complete lifecycle:
  $$\text{Total Mission Time} = \text{Transit Time} + \text{Live ER Offload Wait Time} - \text{Specialty Accreditation Bonus}$$
  Driving an extra 6 minutes to a regional hospital with zero offload delay gets the ambulance back on the road **2 hours faster** than dumping them at an overcrowded downtown ER. Furthermore, patients are routed directly to certified specialty centers (e.g., Burn Units, Level 1 Trauma, Comprehensive Stroke Centers, Pediatric ICUs).

#### Scenario B: Heterogeneous Fleet & Specialized Clinical Equipment (Ventilators for Respiratory Arrest)
Ambulance fleets are **heterogeneous**:
- **Basic Life Support (BLS):** Equipped for non-invasive first aid, basic vitals monitoring, oxygen masks, and stretcher transport.
- **Advanced Life Support (ALS / Mobile ICU):** Equipped with advanced mechanical ventilators, endotracheal intubation kits, cardiac monitors, IV infusion pumps, and specialized flight/critical care paramedics.
- **The Challenge:** If a patient suffers an acute **respiratory attack** (e.g., severe smoke inhalation, acute asthma, or anaphylaxis), dispatching an unequipped BLS ambulance can prove fatal. The optimization engine **strictly prioritizes and routes an ambulance equipped with active ventilator/ALS capability**, even if an unequipped BLS unit happens to be slightly closer geographically.

#### Scenario C: Rig Physical Geometry, Overpass Clearance & Weight Restrictions
- **The Ground Reality:** Heavy ambulance apparatus—such as Freightliner medium-duty Mobile ICUs and bariatric transport rigs—frequently exceed 10 to 11 feet in height and 20,000+ lbs in gross vehicle weight. Generic car navigation apps routinely route these vehicles under low railroad bridges or across weight-limited secondary spans, causing rig entrapment or catastrophic bridge strikes.
- **The Solution (Rig Geometry Pruning):** Classical graph preprocessing filters the road network against the dispatched vehicle's physical dimensions (height, axle weight, turning radius). Inaccessible edges are pruned prior to Hamiltonian mapping, guaranteeing 100% physically passable trajectories.

#### Scenario D: Dynamic En-Route Re-Routing & Capacity-Aware Detour (Fever vs. Snake Bite)
Imagine an ambulance has picked up **Patient A**, who has a mild fever (low urgency), and is en route to the hospital:
- While in transit, an extreme, life-threatening emergency occurs nearby: **Patient B** suffers a neurotoxic **snake bite** (high fatality risk without rapid antivenom administration).
- **Capacity-Aware Detour:** If the ambulance has available patient capacity ($Q \ge 2$), the system dynamically evaluates a detour: divert immediately to stabilize and board Patient B, then proceed to the hospital with both patients. Because a fever can safely wait while a snake bite can turn fatal within minutes, triage urgency strictly justifies the detour.
- **Capacity Exhaustion:** If the vehicle has reached full capacity ($Q = 1$), the system disallows the detour and immediately routes the nearest idle unit instead.

#### Scenario E: Idle Ambulance Dispatch Prioritization & Anti-Redundancy
- **Idle Prioritization:** When an ambulance is idle or empty at a station or depot, it must prioritize life-threatening emergencies over non-critical calls, preventing FIFO queue starvation for fatal calls.
- **Anti-Redundancy:** Prevents multiple emergency units from converging on the same incident location without operational justification.

---

### The Computational Challenge

Coordinating multiple heterogeneous ambulances visiting multiple incidents under conflicting multi-objective constraints:
$$\text{Distance} + \text{Live Congestion} + \text{Triage Urgency} + \text{Equipment Matching} + \text{Hospital Offload Delays} + \text{Rig Dimensions} + \text{Capacity}$$
is a variant of the **Heterogeneous Fleet Capacitated Vehicle Routing Problem with Time Windows and Priority Triage (HF-CVRPTW-P)**, which is strictly **NP-hard**.

As the number of response nodes, equipment configurations, and incidents grows, the combinatorial permutation space explodes factorially:
$$\mathcal{O}\left( \frac{(N-1)!}{(N-K)!} \cdot K^N \right)$$
Finding global or near-global optima within critical response seconds challenges classical heuristics, making this an ideal domain for **quantum and hybrid quantum-classical optimization**.

---

## 2. Our Ideas & Core Approach

We address this heterogeneous ambulance routing challenge by formulating it as an **Interactive Hybrid Quantum-Classical Optimization Pipeline** that explicitly bridges real-time web responsiveness with local quantum circuit simulation.

```
[User Browser: Interactive Real-World Map]
  (Click to place incident + Type emergency description in natural language)
                                │
                                ▼
            [Natural Language Intent & Triage Parser]
              ├─ Extract Triage Urgency (e.g. Snake bite / Respiratory -> λ=50)
              ├─ Identify Medical Needs (Ventilator required -> ALS ambulance)
              └─ Select Candidate Specialty Hospitals (Burn Center, Stroke Unit + ER Offload Wait)
                                │
                                ▼
                 [Classical Preprocessing Layer]
                   ├─ Filter physical road network (prune low overpasses via Dijkstra on OSM)
                   ├─ Compute congestion matrix from the synthetic day/time profile
                   ├─ Perform O(|H|) Hospital Lookup: C_{ih} + T_{offload}(h) - Ω_h
                   └─ Guard: at most 3 stops (9 qubits) per vehicle subproblem
                                │
                                ├─────────────────────────────────────────┐
                                │ Classical route (immediate)             │
                                ▼                                         ▼
            [Map: Classical Dispatch]                   [Local Qiskit Aer QAOA Engine]
            (Renders shortest-path route)                 ├─ Exact Statevector (no shot noise)
                                                          ├─ COBYLA from fixed starts
                                                          └─ Local optimizer loop (γ, β)
                                                                          │
                                                                          ▼
                                                       [Classical Bitstring Repair Decoder]
                                                          ├─ Project marginals to a valid tour
                                                          ├─ Recompute the physical schedule
                                                          └─ Equipment filtered before the QUBO
                                                                          │
                                                                          ▼
                                                       [Map Update & Comparative Metrics]
                                                       (Overlays quantum route vs. classical)
```

### Key Conceptual Pillars

1. **Natural Language Emergency Dispatch:**
   Users specify the situation naturally. The NLP extraction layer translates complex clinical and situational prose into concrete mathematical parameters ($\lambda_i$, equipment flags $E_i$, hospital criteria).

2. **Bounded Quantum Subproblem:**
   Rather than attempting to encode the entire metropolitan area into a single massive Hamiltonian, classical preprocessing selects a vehicle and orders at most `max_quantum_stops=3` stops. That gives a 9-qubit one-hot QUBO, well inside the 12-qubit guard, so exact local statevector simulation is fast and memory-safe.

3. **Two-Tier Temporal Decoupling (Sequence Order vs. Continuous Time):**
   The quantum Hamiltonian optimizes the combinatorial **route sequence** (stop 1, stop 2, stop 3). Once the sequence is decoded, the classical graph layer calculates exact continuous physical travel durations ($t = d / v$), speeds, traffic delays, and hospital turnaround times.

4. **Hospital Offload & Bed Availability Integration:**
   Instead of terminating at an arbitrary fixed hospital, the final leg selects from available regional hospitals $h \in \mathcal{H}$ minimizing:
   $$\text{Transit Time}(i \to h) + T_{\text{offload}}(h) - \Omega(h, \text{condition}_i)$$
   evaluated efficiently during classical preprocessing, drastically reducing ambulance turnaround times and mitigating systemwide "Level Zero".

5. **Physical Clearance & Weight Safety Guarantee:**
   Rig dimensions are enforced upstream during classical preprocessing. Edges with overpass heights lower than rig clearance or bridges below weight capacity are eliminated from the transition matrix, preventing rig entrapment while saving physical qubits.

6. **Medical Equipment Compatibility (ALS / Ventilator Matching):**
   Patients requiring critical ventilator support are matched only to ambulances possessing active respiratory capabilities. Incompatible vehicle-patient pairs are filtered before the QUBO is built; the QUBO itself does not carry an equipment penalty.

7. **Classical Post-Processing Bitstring Repair:**
   Measured marginals from shallow-depth QAOA are passed through a Hungarian-assignment repair step that projects them onto a valid permutation. Every displayed order is therefore executable, while the raw and repaired probability masses are reported separately so the quantum result is not overstated.

---

## 3. Mathematical Formulation (QUBO & Ising Mapping)

We formulate the heterogeneous ambulance dispatch as a **Quadratic Unconstrained Binary Optimization (QUBO)** problem over partitioned vehicle sub-clusters.

### A. Decision Variables & Sizing
Let the ambulance fleet be partitioned by capability:
$$v \in \mathcal{V} = \mathcal{V}_{\text{BLS}} \cup \mathcal{V}_{\text{ALS}}$$
For ambulance $v \in \mathcal{V}$, let $\mathcal{C}_v$ be the assigned candidate incident set. The shipped guard is $|\mathcal{C}_v| \le 3$ (`max_quantum_stops`).
For node $i \in \mathcal{C}_v$ and sequence step $t \in \{0, \dots, T_v - 1\}$:
$$x_{i, t}^{(v)} \in \{0, 1\}$$
where $x_{i, t}^{(v)} = 1$ if ambulance $v$ visits location $i$ at step $t$, and $0$ otherwise.

* **Subproblem Qubit Footprint:** The QUBO uses $|\mathcal{C}_v|^2$ bits (9 for 3 stops), inside the demo's `max_qubits=12` guard. That makes exact statevector simulation practical on a laptop.

---

### B. Objective Function

#### 1. Transition Cost & Dynamic Traffic
$$H_{\text{cost}} = \sum_{v \in \mathcal{V}} \sum_{t=0}^{T-2} \sum_{i \in \mathcal{C}_v} \sum_{j \in \mathcal{C}_v, j \neq i} C_{ij}^{(v)}(t) \cdot x_{i, t}^{(v)} \cdot x_{j, t+1}^{(v)}$$
where:
$$C_{ij}^{(v)}(t) = d_{ij} \times \tau_{ij}(v, t) + \delta_{\text{blockage}}(i, j)$$
- $\tau_{ij}(v, t)$: Dynamic traffic multiplier along road edge $(i, j)$ at step $t$.
- **Rig Geometry Pruning:** If ambulance height $h_v > H_{\max}(i, j)$ or weight $w_v > W_{\max}(i, j)$, $C_{ij}^{(v)} \to \infty$ during classical graph pre-filtering.

#### 2. Patient Triage Urgency (Snake Bite / Respiratory Arrest vs. Fever)
$$H_{\text{urgency}} = \sum_{v \in \mathcal{V}} \sum_{i \in \mathcal{C}_v \setminus \{\text{depot}\}} \sum_{t=1}^{T-1} \left( \lambda_i \cdot t \right) x_{i, t}^{(v)}$$
- For a **mild fever**: $\lambda_{\text{fever}} = 1$ (low delay penalty).
- For a **snake bite / respiratory attack**: $\lambda_{\text{critical}} = 50$ (severe delay penalty).

---

### C. Constraint Penalty Terms

Operational constraints are enforced via quadratic penalty terms ($A, D, W_{\text{equip}} \gg \max(C_{ij})$):

#### 1. Unique Incident Coverage & Anti-Redundancy
Every active incident location $i$ in cluster $\mathcal{C}$ must be served exactly once across the fleet:
$$P_{\text{coverage}} = D \sum_{i \in \mathcal{C} \setminus \{\text{depot}\}} \left( \sum_{v \in \mathcal{V}} \sum_{t=1}^{T-1} x_{i, t}^{(v)} - 1 \right)^2$$
Prevents duplicate ambulance dispatches to the same location while ensuring no emergency is neglected.

#### 2. Clinical Equipment Compatibility (Ventilator / ALS Matching)
Let $E_i = 1$ if patient $i$ requires advanced respiratory or cardiac support (e.g., ventilator for respiratory arrest), and $0$ for standard BLS care. Let $M_{v} = 1$ if vehicle $v \in \mathcal{V}_{\text{ALS}}$ possesses active ventilator equipment:
$$P_{\text{equipment}} = W_{\text{equip}} \sum_{v \in \mathcal{V}_{\text{BLS}}} \sum_{i \in \mathcal{C}_v: E_i = 1} \sum_{t=1}^{T-1} x_{i, t}^{(v)}$$
Injects an energetic penalty if an unequipped BLS ambulance is assigned to a ventilator-dependent patient. In classical preprocessing, incompatible vehicle-incident variables are clamped to $0$ to conserve qubits.

#### 3. One Location per Step (Per Vehicle)
Each ambulance can only be present at one physical node at each step $t$:
$$P_{\text{step}} = A \sum_{v \in \mathcal{V}} \sum_{t=0}^{T-1} \left( \sum_{i \in \mathcal{C}_v} x_{i, t}^{(v)} - 1 \right)^2$$

#### 4. Vehicle Capacity & En-Route Detour
For each ambulance, total boarded patients cannot exceed available capacity $Q_v$. Handled during the Cluster-First partitioning stage so that $|\mathcal{C}_v \setminus \{\text{depot}\}| \le Q_v$. For dynamic detours, visiting a hospital node resets the active patient payload counter.

---

### D. Mapping to Quantum Hamiltonian
Binary variables are mapped to quantum spin operators via:
$$x_{i, t}^{(v)} = \frac{I - Z_{i, t}^{(v)}}{2}$$
Yielding the Problem Cost Hamiltonian:
$$H_C = \sum_{k} h_k Z_k + \sum_{k < l} J_{kl} Z_k Z_l + \text{offset}$$
executed via parameterized QAOA ansatz $|\psi(\gamma, \beta)\rangle = \prod_{l=1}^p e^{-i \beta_l H_M} e^{-i \gamma_l H_C} |+\rangle^{\otimes n}$.

---

## 4. Technical Challenges & Quantum Engineering Solutions

Designing a quantum-assisted ambulance routing system reveals distinct theoretical, algorithmic, and computational challenges. Below is a rigorous analysis of the problems faced and our implemented solutions:

### Challenge 1: The Exponential Simulation Memory Wall & Qubit Scaling
* **The Problem:** A monolithic encoding of an urban ambulance fleet across multiple time steps ($|\mathcal{V}| \times (N + |\mathcal{H}|) \times T$) demands $100+$ qubits for even 5 incidents. Simulating $100$ qubits via statevector requires $2^{100} \times 16 \text{ bytes} \approx 2 \times 10^{31} \text{ bytes}$, which is physically impossible. On local machines, `qiskit-aer` statevector simulation crashes with Out-Of-Memory (OOM) beyond 32 qubits.
* **Our Solution (Bounded Subproblem):** Classical preprocessing selects one vehicle's stop set and caps it at `max_quantum_stops=3`. The QUBO is therefore at most 9 qubits, and the code refuses larger subproblems before touching Qiskit. A 9-qubit statevector needs about 8 KB and is fast enough to optimise inside the UI request.

### Challenge 2: Clinical Equipment Matching
* **The Problem:** Adding clinical penalty terms into QUBO for heterogeneous equipment (BLS vs. ALS ventilators) increases Hamiltonian coupling density. In shallow QAOA, soft penalties can still produce bitstrings where an unequipped BLS unit is assigned to a dying respiratory arrest patient.
* **Our Solution:** Equipment compatibility is a **hard classical filter before the QUBO**. Vehicle selection and cluster construction reject any vehicle that cannot carry every patient's required equipment, so the quantum subproblem only ever contains clinically valid assignments. The QUBO does not carry a redundant equipment penalty.

### Challenge 3: Real-Time UI Latency vs. Hybrid Optimizer Iterations
* **The Problem:** 911 dispatch requires an immediate response. A full QAOA optimization loop (COBYLA over statevector evaluations) takes seconds, which would freeze an interactive browser map if it blocked the first render.
* **Our Solution (Dual-Tier Dispatch):**
  1. **Instant Classical Dispatch:** When the operator presses **Dispatch**, a classical heuristic (NetworkX shortest paths plus permutation search over at most 3 stops) immediately draws the route. This is the default view.
  2. **Explicit Quantum Comparison:** **Run quantum** is a separate, opt-in action behind a spinner. It runs in a dedicated large-stack thread (`run_with_large_stack`) so Qiskit's circuit construction does not overflow Streamlit's worker stack. It is synchronous, not asynchronous background work.
  3. **Bounded Subproblems:** The demo never sends more than `max_quantum_stops=3` stops to the QUBO, so statevector simulation stays inside the 12-qubit budget.

### Challenge 4: The Feasibility Deficit of Shallow QAOA ($p=1, 2$)
* **The Problem:** In constrained routing problems, valid routes occupy an exponentially tiny fraction of the $2^n$ Hilbert space. Unassisted sampling from shallow QAOA ($p=1, 2$) with standard Pauli-$X$ mixers frequently samples invalid bitstrings that violate one-hot or coverage constraints.
* **Our Solution (Classical Post-Processing Bitstring Repair):**
  We implement a classical post-processing decoder in `src/quantum/qaoa_solver.py`. The decoder inspects the measured marginals and projects them onto the nearest valid permutation with a Hungarian assignment. The UI reports:
  - **Raw feasible:** share of shots that were valid permutations before repair (typically a few percent at $p=1$).
  - **Repair mass:** share of the measured probability that repairs to the order actually displayed.
  - **Energy ratio:** exact brute-force QUBO optimum divided by the repaired QAOA energy (1.00 means the repaired order is optimal).

  Repair always returns a valid permutation; that is not the same as saying the quantum distribution supports it, which is why repair mass is reported separately.


### Challenge 5: Allocation of Classical vs. Quantum Computational Boundaries
* **The Problem:** Naive quantum proposals attempt to encode street-level obstacle avoidance, bridge weight limits, and hospital offload comparisons into the Hamiltonian, needlessly inflating the qubit count.
* **Our Solution:** Rigorous division of labor:
  * **Classical Layer:** OpenStreetMap road topology, ambulance physical clearance pruning (Dijkstra), ER offload lookup ($\min_{h} (C_{ih} + T_{\text{offload}}(h) - \Omega_h)$ in $\mathcal{O}(|\mathcal{H}|)$), and NLP text parsing.
  * **Quantum Layer:** Combinatorial permutation and triage prioritization across the fleet.

---

## 5. What Is Implemented vs Planned

- [x] Define real-world ambulance dispatch use cases (ventilator matching, hospital offload waits, rig geometry limits, multi-patient routing).
- [x] **Interactive Map Dashboard (`app.py`):**
  - Bounded Folium map with persisted center/zoom, online OSM tiles, and an **offline vector** basemap drawn from the cached graph.
  - Click-to-place incident markers, with the selected point and preset incidents shown consistently.
  - Vehicle-shaped ambulance badges, red-plus hospital badges, synthetic traffic layer with a day/time picker, a network multiplier, and both map-click and street-name override editors.
  - Classical route overlay, repaired-QAOA overlay, and a live simulation layer that starts automatically after Dispatch.
- [x] **Natural Language Incident & Triage Parser (`src/quantum/nlp_parser.py`):**
  - Rule-based urgency, equipment, and specialty extraction, with an optional local Ollama fallback.
- [x] **Ambulance Network & Fleet (`src/quantum/problem.py`, `data/curated/`):**
  - Real OSM hospital and station coordinates; curated specialty/offload fields; synthetic vehicles and incidents.
  - Clearance and weight pruning per vehicle.
  - Per-patient hospital selection and cluster ordering; greedy multi-vehicle assignment for larger scenarios.
  - The demo does **not** implement a general CFRS partitioner beyond the `max_quantum_stops=3` guard.
- [x] **Heterogeneous Ambulance QUBO (`src/quantum/qubo.py`):**
  - One-hot stop/position QUBO with traffic travel times, urgency delay, per-patient hospital detour, and offload.
  - Ising conversion for the QAOA circuit.
- [x] **Local Qiskit Aer QAOA (`src/quantum/qaoa_solver.py`):**
  - QAOA `p=1` on exact statevector, COBYLA angle optimisation, Hungarian bitstring repair, exact brute-force optimum for comparison.
  - Warm-started angles, SLSQP, shot-noise models, and hardware execution are **not** implemented.
- [x] **Ambulance Simulation (`src/quantum/sim.py`):**
  - Deterministic tick engine with scene time, pickup, simulated offload, per-patient delivery, fleet state, and event log.
  - Dynamic en-route rerouting during a run is **not** implemented.
- [x] **Classical Baseline:**
  - Nearest-neighbour ordering plus exhaustive permutation search for clusters of at most 6 stops; greedy assignment across vehicles.
- [ ] Separate `baselines.py` benchmark suite (2-Opt, simulated annealing, historical-data comparison).
- [ ] Jupyter benchmark notebook.

---

## 6. Implementation & Technology Stack

### Tech Stack
- **Language:** Python 3.12
- **Interactive Web Interface:** Streamlit, Folium / Streamlit-Folium (OSM tiles or offline vector roads, click listeners, animated route overlays)
- **Natural Language Parsing:** Rule-based parser extracting medical triage urgency and clinical equipment flags
- **Local Quantum Simulator:** Qiskit Aer statevector simulation
- **Quantum Core SDK:** Qiskit
- **Classical Optimization:** SciPy (`minimize` with COBYLA), NumPy
- **Graph & Geospatial Modeling:** NetworkX, GeoPandas / Shapely
- **Tests:** pytest, Streamlit AppTest

### Actual Codebase Architecture
```text
quantum/
├── pyproject.toml                     # Project dependencies and packaging
├── README.md                          # Project documentation & formulation
├── app.py                             # Interactive browser application (Streamlit / Web Map)
├── data/curated/                      # Curated + synthetic demo records
├── scripts/
│   ├── prepare_data.py                # Graph download/cache and edge export
│   └── run_scenario.py                # CLI dispatch runner
├── tests/                             # Unit and AppTest coverage
└── src/
    └── quantum/
        ├── __init__.py
        ├── config.py                  # config.yaml loader
        ├── data/                      # OSM fetch and curated loaders
        ├── nlp_parser.py              # Text emergency prompt -> triage parameters
        ├── problem.py                 # Fleet, incidents, hospitals, scenario models
        ├── traffic.py                 # Synthetic time-of-day profiles, colours, overrides
        ├── graph.py                   # Routing graph, clearance pruning, shortest paths
        ├── dispatch.py                # Per-patient hospital choice, ordering, route plans
        ├── qubo.py                    # QUBO matrix and Ising coefficients
        ├── qaoa_solver.py             # QAOA on local Aer, repair decoder, comparison
        ├── sim.py                     # Ambulance simulation engine
        ├── visualize.py               # Map, traffic layer, routes, live vehicles
        └── runtime.py                 # Large-stack thread helper for Qiskit
```

### Evaluation Metrics
| Metric | Description | Current demo |
|---|---|---|
| **Hospital Turnaround Time** | Total mission time including transit + simulated ED offload | Minimised by the classical/quantum order comparison |
| **Rig Clearance Violations** | Heavy rigs routed through low clearances or weight-limited bridges | 0 on the demo graph (classical pruning); limits are synthetic |
| **Equipment Mismatch Rate** | Patients assigned to vehicles lacking required equipment | 0 by hard filtering before routing |
| **Raw Quantum Feasibility (%)** | Raw sampled bitstrings that are valid permutations before repair | Reported per run; typically a few percent at $p=1$ |
| **Repair Mass (%)** | Measured probability that repairs to the displayed order | Reported per run; not assumed to be 100% |
| **Triage Delay Score** | Cumulative `60 s × severity × position` penalty | Included in the QUBO objective |
| **Redundancy Rate** | Duplicate dispatches to the same location | 0 by one-hot coverage constraints |
| **Energy Ratio** | Exact QUBO optimum divided by the repaired QAOA energy | Reported per run; typically 0.9–1.0 on preset S4 |
| **UI Response Latency** | Time to display the classical route | Classical dispatch is immediate; quantum is a separate opt-in run |


---

## 7. How to Run & Get Started

See **[Quick start — run the demo (basic)](#quick-start--run-the-demo-basic)** above.

The short version:

```bash
uv sync
uv run streamlit run app.py
```

Then open <http://localhost:8501>, pick preset **S4**, click **Dispatch**, then **Run quantum**.

The Jupyter benchmark notebook (`notebooks/emergency_routing.ipynb`) is **not implemented yet**; it is part of the backlog.
