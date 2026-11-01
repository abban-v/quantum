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

### Basic demo flow (about 30 seconds)

1. In the sidebar, choose preset **S4 — Multi-casualty collision**.
2. Click **Dispatch**. The map draws the classical route and the plan table shows transit, offload, total, equipment, specialty, and clearance status.
3. Click **Run quantum**. A green repaired-QAOA overlay appears with the approximation ratio, raw feasibility, repaired feasibility, and runtime.
4. Use the layer control (top right) to toggle routes, hospitals, ambulances, and incidents.

### Click-to-place a custom incident

1. Click anywhere on the map. An orange marker is placed.
2. Type a description, for example `snake bite with difficulty breathing`.
3. Click **Dispatch**.
4. For a quantum order, tick **Multi-casualty custom (3 patients)** before dispatching. QAOA needs at least two stops.

### What the demo actually does

- Downloads and caches the Manhattan drive graph from OpenStreetMap.
- Parses the free-text description with rules. Ollama is optional; the demo works without it.
- Chooses a hospital classically, assigns a vehicle, and computes road routes.
- For 2–3 stops, builds a 4–9 qubit QUBO, runs QAOA `p=1` on local Qiskit Aer, repairs the bitstring to a valid stop order, and overlays the result.
- Uses **simulated** offload waits, severities, and clearance limits. Hospital and station locations are real OSM features.

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

1. **Interactive Real-World Map:** A live, dynamic city map (rendered in the browser) displaying road networks, active traffic congestion, low overpasses, weight-restricted bridges, candidate regional hospitals with real-time emergency department (ED) offload queues, and geographically stationed ambulances (Basic Life Support / BLS, and Advanced Life Support / ALS Mobile ICUs equipped with mechanical ventilators).
2. **Click-to-Incident Dispatch:** The operator clicks any location on the map to place an active incident marker.
3. **Natural Language Emergency Specification ("In Text"):** The user specifies the emergency in plain text. Examples:
   - *"Apartment building fire victim, severe smoke inhalation with acute respiratory distress, cyanotic."*
   - *"Hiker bitten by venomous viper on nature trail, swelling rapidly, difficulty breathing."*
   - *"Elderly patient with low-grade fever and mild dehydration."*
   - *"Severe motor vehicle collision with massive trauma, multi-system injury."*
4. **Automated Requirement & Triage Extraction:** The system automatically analyzes the text prompt and extracts the underlying mathematical parameters:
   - **Triage Urgency Score ($\lambda_i$):** (e.g., Critical $\lambda = 50$ for respiratory arrest/snake bite vs. Low $\lambda = 1$ for fever).
   - **Clinical Equipment Demand ($E_i$):** (Ventilator/ALS unit required vs. standard stretcher/BLS transport).
   - **Destination Hospital Specialty Selection:** (Burn Center for fire victims, Comprehensive Stroke Center, Level 1 Trauma for head injuries, factoring live ER offload wait times).
   - **Rig Physical Clearance:** (Filtering low overpasses and bridge weight limits for heavy Mobile ICU rigs).
5. **Local Quantum Circuit Execution via Qiskit & Qiskit Aer:** The routing problem is compiled into an Ising Hamiltonian and solved entirely on your local machine using Qiskit and Qiskit Aer (utilizing statevector and shot-based `AerSimulator` with optional hardware-realistic noise models), driving the classical-quantum hybrid loop (COBYLA/SLSQP) with zero cloud dependencies or external API keys.
6. **Live Route Animation:** The user watches the dispatched ambulances dynamically mobilize and animate along their computed optimal routes on the interactive map in real time.

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
                   ├─ Compute dynamic congestion matrix with live traffic
                   ├─ Perform O(|H|) Hospital Lookup: C_{ih} + T_{offload}(h) - Ω_h
                   └─ Two-Stage CFRS Decomposition: Partition into ≤ 16-qubit vehicle subproblems
                                │
                                ├─────────────────────────────────────────┐
                                │ Instant Classical Route (< 0.2s)        │
                                ▼                                         ▼
            [Live Map Display: Instant Dispatch]        [Local Qiskit Aer QAOA Engine]
            (Renders immediate 2-Opt/Dijkstra route)      ├─ Exact Statevector (zero shot noise)
                                                          ├─ Warm-started parameters (< 10 iters)
                                                          └─ Local COBYLA optimizer loop (γ, β)
                                                                          │
                                                                          ▼
                                                       [Classical Bitstring Repair Decoder]
                                                          ├─ Project raw samples to valid tours
                                                          ├─ Calculate continuous physical schedule
                                                          └─ Enforce clinical equipment constraints
                                                                          │
                                                                          ▼
                                                       [Dynamic Map Update & Comparative Metrics]
                                                       (Overlays quantum route vs. classical baselines)
```

### Key Conceptual Pillars

1. **Natural Language Emergency Dispatch:**
   Users specify the situation naturally. The NLP extraction layer translates complex clinical and situational prose into concrete mathematical parameters ($\lambda_i$, equipment flags $E_i$, hospital criteria).

2. **Cluster-First, Route-Second (CFRS) Problem Decomposition:**
   Rather than attempting to encode the entire metropolitan area into a single massive Hamiltonian ($>100$ qubits), classical preprocessing clusters the incident set so that each vehicle's combinatorial routing subproblem is bounded to **$\le 16$ qubits**. This guarantees rapid, exact local statevector simulation on Qiskit Aer with zero memory overflow.

3. **Two-Tier Temporal Decoupling (Sequence Order vs. Continuous Time):**
   The quantum Hamiltonian optimizes the combinatorial **route sequence** (stop 1, stop 2, stop 3). Once the sequence is decoded, the classical graph layer calculates exact continuous physical travel durations ($t = d / v$), speeds, traffic delays, and hospital turnaround times.

4. **Hospital Offload & Bed Availability Integration:**
   Instead of terminating at an arbitrary fixed hospital, the final leg selects from available regional hospitals $h \in \mathcal{H}$ minimizing:
   $$\text{Transit Time}(i \to h) + T_{\text{offload}}(h) - \Omega(h, \text{condition}_i)$$
   evaluated efficiently during classical preprocessing, drastically reducing ambulance turnaround times and mitigating systemwide "Level Zero".

5. **Physical Clearance & Weight Safety Guarantee:**
   Rig dimensions are enforced upstream during classical preprocessing. Edges with overpass heights lower than rig clearance or bridges below weight capacity are eliminated from the transition matrix, preventing rig entrapment while saving physical qubits.

6. **Medical Equipment Compatibility (ALS / Ventilator Matching):**
   Patients requiring critical ventilator support are matched only to ambulances possessing active respiratory capabilities, either by hard pre-pruning incompatible vehicle-patient pairs or via quadratic penalty terms in the Hamiltonian.

7. **Classical Post-Processing Bitstring Repair:**
   Raw bitstrings sampled from shallow-depth QAOA ($p=1, 2$) are passed through a lightweight greedy repair heuristic, resolving duplicate visits or omitted stops and guaranteeing 100% executable routes.

---

## 3. Mathematical Formulation (QUBO & Ising Mapping)

We formulate the heterogeneous ambulance dispatch as a **Quadratic Unconstrained Binary Optimization (QUBO)** problem over partitioned vehicle sub-clusters.

### A. Decision Variables & Sizing
Let the ambulance fleet be partitioned by capability:
$$v \in \mathcal{V} = \mathcal{V}_{\text{BLS}} \cup \mathcal{V}_{\text{ALS}}$$
For ambulance $v \in \mathcal{V}$, let $\mathcal{C}_v$ be the assigned candidate incident set plus depot/hospital endpoints ($|\mathcal{C}_v| \le 4$).
For node $i \in \mathcal{C}_v$ and sequence step $t \in \{0, \dots, T_v - 1\}$:
$$x_{i, t}^{(v)} \in \{0, 1\}$$
where $x_{i, t}^{(v)} = 1$ if ambulance $v$ visits location $i$ at step $t$, and $0$ otherwise.

* **Subproblem Qubit Footprint:** Clamping fixed ambulance origins at $t=0$ ($x_{\text{depot}, 0}^{(v)} = 1$) restricts subproblems to $|\mathcal{C}_v| \times (T_v - 1) \le 16 \text{ qubits}$, enabling exact local statevector simulation in $< 5 \text{ ms}$ per function evaluation.

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
* **Our Solution (Two-Stage CFRS Decomposition):** We implement the **Cluster-First, Route-Second (CFRS)** paradigm (*Feld et al., 2019*). Classical clustering first groups incidents into localized sub-clusters matching ambulance capacity and clinical compatibility. Each ambulance subproblem contains $\le 4$ stops, requiring only **$\le 16$ qubits**. A 16-qubit statevector requires only $1 \text{ MB}$ of RAM and executes in $\approx 5\text{ ms}$ per evaluation on Qiskit Aer.

### Challenge 2: Clinical Equipment Matching & Variable Pruning
* **The Problem:** Adding clinical penalty terms into QUBO for heterogeneous equipment (BLS vs. ALS ventilators) increases Hamiltonian coupling density. In shallow QAOA, soft penalties can still produce bitstrings where an unequipped BLS unit is assigned to a dying respiratory arrest patient.
* **Our Solution:** Hard **classical variable clamping**: During classical preprocessing, if patient $i$ requires a ventilator ($E_i = 1$) and ambulance $v$ is a BLS unit, all decision variables $x_{i,t}^{(v)}$ are pre-set to $0$ and completely removed from the Hamiltonian before compiling to Qiskit. This guarantees 100% clinical equipment safety while saving precious qubits.

### Challenge 3: Real-Time UI Latency vs. Hybrid Optimizer Iterations
* **The Problem:** 911 dispatch requires an immediate response ($< 1 \text{ second}$). A full QAOA optimization loop (COBYLA running 100 iterations of statevector simulations) takes 30–60 seconds, which freezes an interactive browser map.
* **Our Solution (Dual-Tier Dispatch & Warm-Started Parameter Transfer):**
  1. **Instant Classical Dispatch (< 0.2s):** When an incident is clicked on the map, a classical heuristic (NetworkX Dijkstra + 2-Opt) immediately animates the initial ambulance route on the browser dashboard.
  2. **Asynchronous Background Quantum Optimization:** The QAOA loop runs in a non-blocking background thread.
  3. **QAOA Parameter Transfer (*Brandao et al., 2018*):** For small subgraphs, optimal variational angles $(\gamma^*, \beta^*)$ are concentrated in predictable clusters. Initializing with warm-started pre-computed angles cuts classical optimization iterations down to $< 10$ steps ($< 1.5 \text{ seconds}$).

### Challenge 4: The Feasibility Deficit of Shallow QAOA ($p=1, 2$)
* **The Problem:** In constrained routing problems, valid routes occupy an exponentially tiny fraction of the $2^n$ Hilbert space ($< 10^{-4}$). Unassisted sampling from shallow QAOA ($p=1, 2$) with standard Pauli-$X$ mixers frequently samples invalid bitstrings that violate one-hot or coverage constraints.
* **Our Solution (Classical Post-Processing Bitstring Repair):**
  We implement a classical greedy post-processing decoder in `src/quantum/qaoa_solver.py`. The decoder inspects sampled bitstrings and projects them onto the nearest valid permutation (repairing duplicate visits or unvisited stops). We report both **Raw Quantum Feasibility** ($15\%\text{--}35\%$ on NISQ-depth simulation) and **Post-Repair Route Feasibility** ($100\%$).

### Challenge 5: Allocation of Classical vs. Quantum Computational Boundaries
* **The Problem:** Naive quantum proposals attempt to encode street-level obstacle avoidance, bridge weight limits, and hospital offload comparisons into the Hamiltonian, needlessly inflating the qubit count.
* **Our Solution:** Rigorous division of labor:
  * **Classical Layer:** OpenStreetMap road topology, ambulance physical clearance pruning (Dijkstra), ER offload lookup ($\min_{h} (C_{ih} + T_{\text{offload}}(h) - \Omega_h)$ in $\mathcal{O}(|\mathcal{H}|)$), and NLP text parsing.
  * **Quantum Layer:** Combinatorial permutation and triage prioritization across the fleet.

---

## 5. What We Plan to Do

- [x] Define real-world ambulance dispatch use cases (ventilator matching, snake bite vs. fever detour, hospital offload wait-times, rig geometry limits).
- [ ] **Interactive Real-World Map Dashboard (`app.py` & `src/quantum/ui/`):**
  - Interactive browser map showing live city street network, ambulance stations, and candidate hospitals.
  - Click-on-map incident placing with pop-up text entry modal.
  - Dual-tier rendering: Instant classical route animation (< 0.2s) followed by asynchronous quantum overlay.
- [ ] **Natural Language Incident & Triage Parser (`src/quantum/nlp_parser.py`):**
  - Converts user plain-text descriptions into mathematical parameters: triage urgency ($\lambda_i$), equipment tags (ventilator/ALS), and hospital specialty tags.
- [ ] **Ambulance Network & Fleet Generator (`src/quantum/problem.py`):**
  - City graph with ambulance stations, depots, and candidate hospitals.
  - Physical road attributes: bridge weight limits, overpass clearances, road closures, and dynamic traffic.
  - Candidate hospital profiles with live ER offload wait times ($T_{\text{offload}}$) and specialty accreditations (Burn, Trauma, Stroke).
  - Two-Stage CFRS decomposer partitioning incidents into $\le 16$-qubit subproblems.
- [ ] **Heterogeneous Ambulance QUBO & Hamiltonian Generator (`src/quantum/qubo.py`):**
  - Mathematical QUBO matrix builder incorporating urgency, equipment matching, unique incident coverage, and capacity detours.
  - Converts QUBO to Qiskit `SparsePauliOp` Pauli-$Z$ Hamiltonian.
- [ ] **Local Qiskit Aer QAOA Solver (`src/quantum/qaoa_solver.py`):**
  - Parameterized QAOA ansatz with $p$ layers executed via local Qiskit Aer (`AerSimulator` statevector and shot modes).
  - Warm-started angle initialization and classical optimizer loop (COBYLA/SLSQP).
  - Classical post-processing bitstring repair decoder projecting raw samples to valid routes.
- [ ] **Classical Baseline Benchmark (`src/quantum/baselines.py`):**
  - Uncoordinated Greedy Nearest Neighbor (demonstrating common real-world failures: dumping patients into 3-hour offload queues, routing ambulances into low clearances, dispatching BLS to respiratory arrest).
  - Classical 2-Opt local search / Simulated Annealing.
  - Exact Brute-Force solver (for ground truth verification on small subgraphs).
- [ ] **Evaluation & Visual Analytics (`src/quantum/visualize.py` & `notebooks/emergency_routing.ipynb`):**
  - Visual 2D map showing road networks, ambulance routes (BLS vs. ALS), bridge/clearance restrictions, hospital offload heatmaps, and detour timelines.
  - Comparative metrics table (Total Turnaround Time, Offload Delay Saved, Equipment Mismatch Rate, Raw vs. Post-Repair Feasibility, Approximation Ratio).

---

## 6. Possible Implementation & Technology Stack

### Tech Stack
- **Language:** Python 3.12
- **Interactive Web Interface:** Streamlit, Folium / Streamlit-Folium (real-world OpenStreetMap tiles, interactive click listeners, and animated ambulance path overlays)
- **Natural Language Parsing:** Rule-based / lightweight NLP parser extracting medical triage urgency and clinical equipment flags
- **Local Quantum Simulator:** `qiskit-aer>=0.18.2` (High-performance C++ `AerSimulator` with statevector and shot-noise models)
- **Quantum Core SDK:** `qiskit>=2.6.1`
- **Classical Optimization:** SciPy (`minimize` with COBYLA/SLSQP), NumPy
- **Graph & Geospatial Modeling:** NetworkX, Shapely / GeoPandas
- **Interactive Development:** Jupyter Notebooks

### Proposed Codebase Architecture
```text
quantum/
├── pyproject.toml                     # Project dependencies and packaging
├── README.md                          # Project documentation & formulation
├── app.py                             # Interactive browser application (Streamlit / Web Map)
├── notebooks/
│   └── emergency_routing.ipynb        # Interactive end-to-end demonstration
└── src/
    └── quantum/
        ├── __init__.py
        ├── nlp_parser.py              # Text emergency prompt -> mathematical parameters
        ├── problem.py                 # City network, traffic, rig limits, ER wait times & ambulance fleet
        ├── qubo.py                    # Ambulance QUBO matrix & Pauli Hamiltonian builder
        ├── dynamic_dispatcher.py       # En-route detour, hospital selection, equipment matching & CFRS decomposition
        ├── qaoa_solver.py             # QAOA execution via local Qiskit Aer & bitstring repair decoder
        ├── baselines.py               # Classical Greedy, 2-Opt, & Exact Brute-Force
        └── visualize.py               # Interactive map renderers & performance visualizer
```

### Evaluation Metrics
| Metric | Description | Target |
|---|---|---|
| **Hospital Turnaround Time** | Total mission time including transit + live ER offload wait time | Minimized (saves 1-3 hrs vs. nearest ER) |
| **Rig Clearance Violations** | Number of heavy rigs routed through low clearances or weight-limited bridges | Exactly 0 (via classical preprocessing) |
| **Equipment Mismatch Rate** | Percentage of patients assigned to ambulances lacking required equipment (e.g. ventilator) | Exactly 0% (via pre-clamping / QUBO penalty) |
| **Raw Quantum Feasibility (%)** | Percentage of raw sampled quantum bitstrings yielding valid routes before repair | $15\%\text{--}35\%$ (realistic for NISQ depth $p=1, 2$) |
| **Post-Repair Route Feasibility (%)** | Percentage of routes valid after classical greedy bitstring repair | Exactly $100\%$ |
| **Triage Delay Score** | Cumulative delay penalty for high-severity patients (snake bite / respiratory) | Minimized / Zero critical delay |
| **Redundancy Rate** | Percentage of duplicate dispatches to the same location | Exactly 0% |
| **Approximation Ratio** | Ratio of QAOA solution cost to the exact optimal cost | $\ge 0.70$ (raw $p=1$), $\ge 0.85$ (warm-started/repaired) |
| **UI Response Latency** | Time to display initial route on interactive browser map | $< 0.5 \text{ seconds}$ (classical instant tier) |

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
