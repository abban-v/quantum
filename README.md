# Quantum-Assisted Emergency Vehicle Routing (Q-EVR)

> **Quantum and hybrid optimization for time-critical emergency response under dynamic traffic, road closures, patient triage priorities, specialized vehicle equipment (ventilators/ALS), multi-agency coordination (Ambulance, Fire, Police), hospital offload delays, rig physical constraints, and tactical police staging.**
>
> **Featuring an Interactive Real-World Browser Map UI with Natural Language Incident Dispatch, backed by IBM Quantum Cloud QPU Execution.**

---

## 1. Introduction & Problem Statement

In time-critical emergencies—such as multi-point fire breakouts, industrial explosions, or major toxic incidents—seconds count. Inefficient vehicle dispatch and uncoordinated multi-agency routing directly increase response latency, worsen patient outcomes, and risk severe casualties.

Conversations with frontline first responders, paramedics (on *r/ems*), firefighters (*r/firefighting*), and 911 dispatchers (*r/911dispatchers*) reveal critical real-world failure modes that traditional routing algorithms fail to address. We model these directly in our system:

---

### The Interactive Real-World Vision: Browser Map & Text Dispatch

Rather than existing as a static math model, this project delivers an **interactive browser-based emergency command dashboard**:

1. **Interactive Real-World Map:** A live, dynamic city map (rendered in the browser) displaying road networks, active traffic congestion, low overpasses, bridges, candidate hospitals with real-time ER offload queues, and geographically stationed emergency vehicles (BLS Ambulances, ALS Mobile ICUs with ventilators, Fire Engines, and Police Cruisers).
2. **Click-to-Incident Dispatch:** The operator clicks any location on the map to place an active incident marker.
3. **Natural Language Emergency Specification ("In Text"):** The user specifies the emergency in plain text. Examples:
   - *"Apartment building fire, 2 people trapped on 3rd floor, severe smoke inhalation with acute respiratory arrest."*
   - *"Hiker bitten by venomous viper on nature trail, swelling rapidly, difficulty breathing."*
   - *"Elderly patient with low-grade fever and mild dehydration."*
   - *"Volatile domestic altercation with serious head trauma, scene actively unstable."*
4. **Automated Requirement & Triage Extraction:** The system automatically analyzes the text prompt and extracts the underlying mathematical parameters:
   - **Triage Urgency Score ($\lambda_i$):** (e.g., Critical $\lambda = 50$ for respiratory arrest/snake bite vs. Low $\lambda = 1$ for fever).
   - **Specialized Equipment Demand:** (Ventilator/ALS unit required vs. antivenom stock vs. standard stretcher).
   - **Multi-Agency Requirements:** (Fire Engine extrication required prior to EMS; Police scene safety clearance / green-corridor escort).
   - **Destination Hospital Selection:** (Burn Center for fire victims, Level 1 Trauma for head injuries, factoring live ER offload wait times).
   - **Rig Physical Clearance:** (Filtering low overpasses and weight limits for dispatched fire apparatus).
5. **Real Quantum Execution via IBM Quantum Cloud:** The problem is compiled into an Ising Hamiltonian and submitted to **IBM Quantum Cloud QPUs** (using `qiskit-ibm-runtime`) or executed on a high-speed local simulator.
6. **Live Route Animation:** The user watches the emergency vehicles dynamically mobilize and animate along their computed optimal routes on the interactive map in real time.

---

### Key Real-World Scenarios & Community Pain Points

#### Scenario A: The "Holding the Wall" Crisis & Hospital Offload Delays (Community Pain Point 1)
- **The Ground Reality:** Paramedics routinely face the "holding the wall" crisis: transporting a patient in 8 minutes, only to spend **2 to 4 hours parked in the emergency department hallway** waiting for an open hospital bed to transfer care. This locks ambulances out of service, causing citywide **"Level Zero"** (zero available ambulances in the entire municipality for incoming 911 calls).
- **The Solution (End-to-End Hospital Offload & Specialty Routing):** The routing engine does not simply send patients to the geographically closest hospital. It evaluates the complete lifecycle:
  $$\text{Total Mission Time} = \text{Transit Time} + \text{Live ER Offload Wait Time} - \text{Specialty Accreditation Bonus}$$
  Driving an extra 6 minutes to a regional hospital with zero offload delay gets the ambulance back on the road **2 hours faster** than dumping them at an overcrowded downtown ER. Furthermore, patients are routed directly to certified specialty centers (e.g., Burn Units, Level 1 Trauma, Comprehensive Stroke Centers, Pediatric ICUs).

#### Scenario B: Rig Geometry, Overpass Clearance & Weight Restrictions (Community Pain Point 3)
- **The Ground Reality:** Consumer navigation apps (Google Maps, Waze) and generic CAD systems are built for passenger cars. They routinely route **50,000 lb fire engines and 13-foot-tall ladder trucks** under low railroad overpasses, across weight-restricted bridges, or down narrow residential lanes lined with parked cars where rigs get wedged.
- **The Solution (Vehicle-Class Physical Geometry Pruning):** The classical graph preprocessor filters the urban network against vehicle-specific physical attributes (height, axle weight, turning radius). Edges violating physical limits are pruned prior to optimization, guaranteeing that routes assigned to heavy apparatus are 100% physically passable.

#### Scenario C: Tactical Staging Desynchronization with Police (Community Pain Point 4)
- **The Ground Reality:** On volatile or dangerous calls (active violence, domestic disputes, riots, hazardous material spills), EMS is strictly instructed to "stage" 2 blocks away until Police declare the scene secure. Currently, dispatch desynchronization causes EMS to arrive 10 minutes before Police (idling unprotected in danger) or causes Police to secure the scene while EMS is still 15 minutes away, leaving wounded victims without care.
- **The Solution (Synchronized Police Staging & Arrival-Window Coupling):** The system coordinates multi-agency arrival schedules through temporal coupling constraints:
  $$t_{\text{ems}} = t_{\text{police}} + \Delta_{\text{clearance}}$$
  EMS is guided to a designated safe staging waypoint and only given the final approach vector precisely when Police scene clearance is verified, eliminating unprotected idling and delayed care.

#### Scenario D: Specialized Vehicle Equipment & Facility Matching (e.g., Ventilators for Respiratory Attacks)
Emergency vehicle fleets are **heterogeneous**:
- **Basic Life Support (BLS):** Equipped for non-invasive first aid, basic vitals monitoring, and stretcher transport.
- **Advanced Life Support (ALS / Mobile ICU):** Equipped with advanced mechanical ventilators, intubation kits, defibrillators, and specialized paramedics.
- **The Challenge:** If a patient suffers an acute **respiratory attack** (e.g., severe smoke inhalation from a fire, acute asthma, or anaphylaxis), dispatching a standard BLS ambulance without ventilator support can prove fatal. The optimization engine must **prioritize and route an ambulance equipped with active ventilator support**, even if an unequipped BLS unit happens to be slightly closer geographically.

#### Scenario E: Multi-Agency Inter-Vehicle Coordination (Fire Department, Police & EMS)
- **Fire Department (Fire Engines / Hazmat / Search & Rescue):**
  - **Fire Suppression & Hazmat Containment:** Extinguishing active fires and securing chemical/gas leaks.
  - **Extrication & Physical Rescue:** Cutting trapped victims out of burning structures or vehicular wreckage.
  - **Precedence Rule:** An ambulance cannot treat or transport a victim trapped inside a burning structure until a **Fire Rescue crew arrives first, secures the hazard, and extricates the patient**.
- **Police Department (Patrol Cruisers / Traffic Units):**
  - **Green Corridor Creation:** Clearing and cordoning key arterial avenues, reducing dynamic congestion multipliers ($\tau_{ij}$) for following ambulances and fire trucks.
  - **Perimeter Cordon & Evacuation:** Diverting civilian traffic away from danger zones to prevent secondary gridlocks.
- **Cross-Agency Collision Avoidance:** Heavy fire apparatus require broad turning radii and clear hydrants; uncoordinated routing causes ambulances and fire trucks to block each other on narrow urban streets.

#### Scenario F: Dynamic En-Route Re-Routing & Capacity-Aware Detour (Fever vs. Snake Bite)
Imagine an ambulance has picked up **Patient A**, who has a mild fever (low urgency), and is en route to the hospital:
- While in transit, an extreme, life-threatening emergency occurs nearby: **Patient B** suffers a neurotoxic **snake bite** (high fatality risk without rapid antivenom administration).
- **Capacity-Aware Detour:** If the ambulance has available patient capacity ($Q \ge 2$), the system dynamically evaluates a detour: divert immediately to stabilize and board Patient B, then proceed to the hospital with both patients. Because a fever can safely wait while a snake bite can turn fatal within minutes, triage urgency strictly justifies the detour.
- **Capacity Exhaustion:** If the vehicle has reached full capacity ($Q = 1$), the system disallows the detour and immediately routes the nearest idle unit instead.

#### Scenario G: Idle Ambulance Dispatch Prioritization & Anti-Redundancy
- **Idle Prioritization:** When an ambulance is idle or empty at a depot, it must prioritize life-threatening emergencies over non-critical calls, preventing FIFO queue starvation for fatal calls.
- **Anti-Redundancy:** Prevents multiple emergency units from converging on the same incident location without operational justification.

---

### The Computational Challenge

Coordinating multiple heterogeneous vehicle classes across agencies visiting multiple incidents under conflicting multi-objective constraints:
$$\text{Distance} + \text{Live Congestion} + \text{Triage Urgency} + \text{Equipment Matching} + \text{Offload Delays} + \text{Rig Dimensions} + \text{Police Staging} + \text{Capacity}$$
is a variant of the **Multi-Agency Capacitated Heterogeneous Vehicle Routing Problem with Time Windows, Precedence, and Physical Road Constraints (MA-HCVRPTW-P)**, which is strictly **NP-hard**.

As the number of response nodes, vehicle equipment types, and incidents grows, the combinatorial permutation space explodes factorially:
$$\mathcal{O}\left( \prod_{a \in \text{Agencies}} \frac{(N_a-1)!}{(N_a-K_a)!} \cdot K_a^{N_a} \right)$$
Finding global or near-global optima within critical response seconds challenges classical heuristics, making this an ideal domain for **quantum and hybrid quantum-classical optimization**.

---

## 2. Our Ideas & Core Approach

We address this multi-agency emergency routing challenge by formulating it as an **Interactive Hybrid Quantum-Classical Optimization Pipeline**.

```
[User Browser: Interactive Real-World Map]
  (Click to place incident + Type emergency description in natural language)
                               │
                               ▼
            [Natural Language Intent & Triage Parser]
              ├─ Extract Triage Urgency (e.g. Snake bite / Respiratory -> λ=50)
              ├─ Identify Medical Needs (Ventilator required -> ALS ambulance)
              ├─ Identify Agency Requirements (Structure fire -> Fire extrication first; Danger -> Police staging)
              └─ Select Candidate Specialty Hospitals (Burn Center, Stroke Unit + ER Offload Wait)
                               │
                               ▼
                 [Classical Graph Preprocessing]
                   ├─ Filter physical road network (prune low overpasses & weak bridges for Fire Engines)
                   ├─ Compute dynamic congestion matrix with police corridor discounts
                   └─ Qubit-reduction: Pre-clamp incompatible vehicle-incident variables & fix origins
                               │
                               ▼
                  [QUBO / Ising Formulation]
                   ├─ Multi-Agency Transition Cost + Traffic
                   ├─ Hospital Selection + ER Offload Delays ("Holding the Wall" mitigation)
                   ├─ Triage Urgency + Equipment Mismatch Penalties
                   └─ Inter-Agency Precedence & Police Staging Synchronization
                               │
                               ▼
        [Quantum Optimization via IBM Quantum Cloud / Local Aer]
          ┌─────────────────────────────────────────────────────────────┐
          │  Primary: IBM Quantum Heron / Eagle QPUs                    │
          │  (via `qiskit-ibm-runtime` SamplerV2 / EstimatorV2)         │
          │                                                             │
          │  Fallback / Dev: Qiskit Aer Statevector & Noise Simulator   │
          │                                                             │
          │  Classical Optimizer Loop: COBYLA / SPSA updating (γ, β)    │
          └─────────────────────────────────────────────────────────────┘
                               │
                               ▼
              [Postprocessing & Solution Decoding]
                ├─ Decode bitstrings into vehicle transit legs & step timelines
                ├─ Validate constraint satisfaction & enforce schedule alignment
                └─ Compute baseline comparison (vs. Uncoordinated Greedy & 2-Opt)
                               │
                               ▼
        [Live Browser UI: Animated Multi-Vehicle Routing]
          (Watch Ambulances, Fire Engines & Police Cruisers dynamically animate
           along optimal routes to incident sites and specialty hospitals)
```

### Key Conceptual Pillars

1. **Natural Language Emergency Dispatch:**
   Users specify the situation naturally. The NLP extraction layer translates complex clinical and situational prose into concrete mathematical parameters ($\lambda_i$, equipment flags, agency dependencies, hospital criteria).

2. **Cloud Quantum Execution via IBM Quantum Cloud (`qiskit-ibm-runtime`):**
   Standard consumer hardware struggles to simulate quantum state spaces beyond small qubit thresholds. We connect our quantum pipeline directly to **IBM Quantum Cloud QPUs**, utilizing Qiskit Runtime Primitives (`SamplerV2`, `EstimatorV2`) for real quantum processor execution, with an offline **Qiskit Aer** fallback for rapid local development.

3. **Hospital Offload & Bed Availability Integration:**
   Instead of terminating at an arbitrary fixed hospital, the final leg selects from available regional hospitals $h \in \mathcal{H}$ minimizing:
   $$\text{Transit Time}(i \to h) + T_{\text{offload}}(h) - \Omega(h, \text{condition}_i)$$
   drastically reducing ambulance turnaround times and mitigating systemwide "Level Zero".

4. **Physical Clearance & Weight Safety Guarantee:**
   Rig dimensions are enforced upstream during classical preprocessing. Edges with overpass heights lower than rig clearance or bridges below weight capacity are eliminated from the transition matrix, preventing rig entrapment while saving physical qubits.

5. **Tactical Staging Synchronization with Police:**
   For high-hazard or violent calls, EMS routes to a nearby staging coordinate and is held until Police arrival:
   $$t_{\text{ems}} = t_{\text{police}} + \Delta_{\text{clearance}}$$
   eliminating unprotected paramedic exposure and minimizing post-clearance response lag.

6. **Multi-Agency Precedence & Role Synchronization:**
   For incidents involving structural fire or entrapment, the optimizer guarantees through quadratic penalty coupling that the **Fire Rescue unit arrives at step $t_{\text{fire}} < t_{\text{ems}}$**, ensuring victims are extricated before ambulance arrival.

7. **Police "Green Corridor" Clearance Modeling:**
   When a police escort traverses an arterial road corridor $(i, j)$ prior to ambulance or fire truck arrival, the dynamic traffic congestion multiplier is reduced:
   $$\tau'_{ij} = \kappa \cdot \tau_{ij} \quad (0 < \kappa < 1)$$

8. **Medical Facility & Equipment Compatibility:**
   Patients with respiratory distress are served exclusively by vehicles possessing active ventilator capabilities, either by hard pre-pruning incompatible decision variables or through a massive penalty in the Hamiltonian.

---

## 3. Mathematical Formulation (QUBO & Ising Mapping)

We formulate the multi-agency, multi-vehicle emergency dispatch as a **Quadratic Unconstrained Binary Optimization (QUBO)** problem.

### A. Decision Variables
Let $K$ be the total fleet across agencies:
$$v \in \mathcal{V} = \mathcal{V}_{\text{EMS}} \cup \mathcal{V}_{\text{Fire}} \cup \mathcal{V}_{\text{Police}}$$
Let $N$ be the incident and staging nodes, and $\mathcal{H}$ be candidate destination hospitals.
For vehicle $v \in \mathcal{V}$, location $i \in \{0, \dots, N-1\} \cup \mathcal{H}$, and step $t \in \{0, \dots, T-1\}$:
$$x_{i, t}^{(v)} \in \{0, 1\}$$
where $x_{i, t}^{(v)} = 1$ if vehicle $v$ visits location $i$ at step $t$, and $0$ otherwise.

---

### B. Objective Function

#### 1. Transition Cost & Dynamic Traffic (with Police Corridor Clearance)
$$H_{\text{cost}} = \sum_{v \in \mathcal{V}} \sum_{t=0}^{T-2} \sum_{i=0}^{N-1} \sum_{j=0, j \neq i}^{N-1} C_{ij}^{(v)}(t) \cdot x_{i, t}^{(v)} \cdot x_{j, t+1}^{(v)}$$
where:
$$C_{ij}^{(v)}(t) = d_{ij} \times \tau_{ij}(v, t) + \delta_{\text{blockage}}(i, j)$$
- $\tau_{ij}(v, t)$: Traffic multiplier, discounted by factor $\kappa$ if a police unit has cleared edge $(i, j)$ at or before step $t$.
- **Rig Geometry Pruning:** If rig height $h_v > H_{\max}(i, j)$ or weight $w_v > W_{\max}(i, j)$, $C_{ij}^{(v)} \to \infty$ (or the arc is pruned classically).

#### 2. Hospital Offload Delays & Specialty Matching (The "Holding the Wall" Term)
For the final transport leg to candidate hospital $h \in \mathcal{H}$ at final step $T_{\text{final}}$:
$$H_{\text{hospital}} = \sum_{v \in \mathcal{V}_{\text{EMS}}} \sum_{h \in \mathcal{H}} \left( C_{i, h} + T_{\text{offload}}(h) - \Omega(h, \text{condition}_i) \right) x_{h, T_{\text{final}}}^{(v)}$$
- $T_{\text{offload}}(h)$: Real-time average hallway/ER offload wait time at hospital $h$.
- $\Omega(h, \text{condition}_i)$: Bonus weight for matching specific patient conditions to specialized hospital accreditation (e.g., Burn Center for fire victims, Comprehensive Stroke Center).

#### 3. Patient Triage Urgency (Snake Bite / Respiratory Arrest vs. Fever)
$$H_{\text{urgency}} = \sum_{v \in \mathcal{V}_{\text{EMS}}} \sum_{i=1}^{N-1} \sum_{t=1}^{T-1} \left( \lambda_i \cdot t \right) x_{i, t}^{(v)}$$
- For a **mild fever**: $\lambda_{\text{fever}} = 1$ (low delay penalty).
- For a **snake bite / respiratory attack**: $\lambda_{\text{critical}} = 50$ (severe delay penalty).

---

### C. Constraint Penalty Terms

Because QUBO is unconstrained, operational and multi-agency constraints are enforced via quadratic penalty terms ($A, B, D, W_{\text{equip}}, W_{\text{prec}}, W_{\text{stage}} \gg \max(C_{ij})$):

#### 1. Police Staging Synchronization (Scene Safety Coupling)
For violent or high-hazard incident $i$ requiring police clearance before EMS entry:
$$P_{\text{stage}} = W_{\text{stage}} \left( \sum_{t=0}^{T-1} t \cdot x_{i, t}^{(v_{\text{ems}})} - \sum_{t=0}^{T-1} t \cdot x_{i, t}^{(v_{\text{police}})} - \Delta_{\text{clearance}} \right)^2$$
Ensures EMS arrives precisely $\Delta_{\text{clearance}}$ steps after Police secures the scene, preventing unsafe early entry or prolonged idle staging.

#### 2. Inter-Agency Precedence Constraint (Fire Extrication Before EMS Transport)
If incident site $i$ involves fire or entrapment requiring fire extrication before ambulance transport:
$$P_{\text{precedence}} = W_{\text{prec}} \sum_{v_f \in \mathcal{V}_{\text{Fire}}} \sum_{v_e \in \mathcal{V}_{\text{EMS}}} \sum_{t_1 \ge t_2} x_{i, t_1}^{(v_f)} \cdot x_{i, t_2}^{(v_e)}$$
Injects an energetic penalty if EMS arrives before or simultaneously with the fire crew ($t_2 \le t_1$).

#### 3. Medical Facility & Equipment Compatibility (Ventilator / ALS Matching)
$$P_{\text{equipment}} = W_{\text{equip}} \sum_{v \in \mathcal{V}_{\text{EMS}}} \sum_{i=1}^{N-1} \sum_{t=0}^{T-1} M_{i, v} \cdot x_{i, t}^{(v)}$$
where $M_{i, v} = 1$ if vehicle $v$ lacks required equipment for patient $i$ (e.g., ventilator for respiratory attack). In classical preprocessing, variables with $M_{i, v} = 1$ are pruned to conserve qubits.

#### 4. One Location per Step (Per Vehicle)
$$P_{\text{step}} = A \sum_{v \in \mathcal{V}} \sum_{t=0}^{T-1} \left( \sum_{i} x_{i, t}^{(v)} - 1 \right)^2$$

#### 5. Anti-Redundancy & Unique Coverage (No Duplicate Units)
$$P_{\text{unique\_coverage}} = D \sum_{i=1}^{N-1} \left( \sum_{v \in \mathcal{V}_{\text{EMS}}} \sum_{t=0}^{T-1} x_{i, t}^{(v)} - 1 \right)^2$$

#### 6. Vehicle Capacity Constraint
$$\sum_{i=1}^{N-1} \sum_{t=1}^{T-1} x_{i, t}^{(v)} \le Q_v - p_v$$

---

### D. Mapping to Quantum Hamiltonian
Binary variables are mapped to quantum spin operators via:
$$x_{i, t}^{(v)} = \frac{I - Z_{i, t}^{(v)}}{2}$$
Yielding the Problem Cost Hamiltonian:
$$H_C = \sum_{k} h_k Z_k + \sum_{k < l} J_{kl} Z_k Z_l + \text{offset}$$
where each qubit corresponds to an assigned $(v, i, t)$ tuple.

---

## 4. What We Plan to Do

- [x] Define real-world multi-agency emergency dispatch use cases (fire extrication precedence, police corridor clearance, ventilator matching, snake bite vs. fever detour, hospital offload wait-times, rig geometry limits, police staging synchronization).
- [ ] **Interactive Real-World Map Dashboard (`app.py` & `src/quantum/ui/`):**
  - Interactive browser map showing live city street network, vehicle locations, fire stations, and hospitals.
  - Click-on-map incident placing with pop-up text entry modal.
  - Real-time animated vehicle transit along selected optimal paths.
- [ ] **Natural Language Incident & Triage Parser (`src/quantum/nlp_parser.py`):**
  - Converts user plain-text descriptions into mathematical parameters: triage urgency ($\lambda_i$), equipment tags (ventilator/ALS), agency dependencies (Fire/Police), and hospital specialty tags.
- [ ] **Multi-Agency Synthetic Network Generator (`src/quantum/problem.py`):**
  - City graph with multi-agency staging hubs (Hospital, Fire Station, Police Precinct).
  - Physical road attributes: bridge weight limits, overpass clearances, road closures, and dynamic traffic.
  - Candidate hospital profiles with live ER offload wait times ($T_{\text{offload}}$) and specialty accreditations.
  - Heterogeneous fleet modeling: BLS vs. ALS ambulances, heavy Fire Engines, Police Patrol Escorts.
- [ ] **Multi-Agency QUBO & Hamiltonian Generator (`src/quantum/qubo.py`):**
  - Mathematical QUBO matrix builder incorporating urgency, equipment matching, fire-EMS precedence, police staging synchronization, hospital offload trade-offs, and anti-redundancy.
  - Converts QUBO to Qiskit `SparsePauliOp` Pauli-$Z$ Hamiltonian.
  - Qubit-reduction via physical clearance edge pruning, equipment filtering, and fixed start coordinates.
- [ ] **IBM Quantum Cloud & Local Qiskit Solver (`src/quantum/qaoa_solver.py`):**
  - Cloud QPU execution via `qiskit-ibm-runtime` (using `SamplerV2` and `EstimatorV2`).
  - Local Qiskit Aer statevector & noise simulator for fast offline development.
  - Classical optimizer loop (COBYLA/SPSA) minimizing $\langle \psi(\gamma, \beta) | H_C | \psi(\gamma, \beta) \rangle$.
- [ ] **Classical Baseline Benchmark (`src/quantum/baselines.py`):**
  - Uncoordinated Greedy Nearest Neighbor (demonstrating common real-world failures: dumping patients into 3-hour offload queues, routing fire engines into low clearances, arriving before police clearance).
  - Classical 2-Opt local search / Simulated Annealing.
  - Exact Brute-Force solver (for ground truth verification on small subgraphs).
- [ ] **Evaluation & Visual Analytics (`src/quantum/visualize.py` & `notebooks/demo.ipynb`):**
  - Visual 2D map showing road networks, multi-agency vehicle routes (Ambulance, Fire, Police), bridge/clearance restrictions, hospital offload heatmaps, and detour timelines.
  - Comparative metrics table (Total Turnaround Time, Offload Delay Saved, Precedence Violations, Staging Accuracy, Equipment Mismatch Rate, Redundancy Violations, Feasibility Rate).

---

## 5. Possible Implementation & Technology Stack

### Tech Stack
- **Language:** Python 3.12
- **Interactive Web Interface:** Streamlit / Leaflet / Folium (real-world OpenStreetMap tiles, interactive click listeners, and animated vehicle path overlays)
- **Natural Language Parsing:** Rule-based / lightweight NLP parser extracting medical triage urgency, agency requirements, and equipment flags
- **Quantum Cloud Backend:** IBM Quantum Cloud via `qiskit-ibm-runtime>=0.51.0` (executing on Heron/Eagle QPUs)
- **Local Quantum Simulator:** `qiskit-aer>=0.18.2` (AerSimulator with statevector and shot-noise models)
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
        ├── problem.py                 # Multi-agency network, traffic, rig limits, ER wait times & fleet models
        ├── qubo.py                    # Multi-agency QUBO matrix & Pauli Hamiltonian builder
        ├── dynamic_dispatcher.py       # En-route detour, staging synchronization, hospital selection & capacity logic
        ├── qaoa_solver.py             # QAOA execution on IBM Quantum Cloud & Qiskit Aer
        ├── baselines.py               # Classical Greedy, 2-Opt, & Brute-Force
        └── visualize.py               # Interactive map renderers & performance visualizer
```

### Evaluation Metrics
| Metric | Description | Target |
|---|---|---|
| **Hospital Turnaround Time** | Total mission time including transit + live ER offload wait time | Minimized (saves 1-3 hrs vs. nearest ER) |
| **Rig Clearance Violations** | Number of heavy rigs routed through low clearances or weight-limited bridges | Exactly 0 |
| **Police Staging Desync** | Time delta between police scene security declaration and EMS arrival | $|\Delta| \le 1$ time step |
| **Inter-Agency Precedence Violations** | Percentage of times EMS arrives before Fire extrication at hazardous sites | Exactly 0% |
| **Equipment Mismatch Rate** | Percentage of patients assigned to vehicles lacking required equipment (e.g. ventilator) | Exactly 0% |
| **Route Feasibility (%)** | Percentage of sampled quantum bitstrings yielding valid multi-vehicle routes | $> 90\%$ after optimization |
| **Triage Delay Score** | Cumulative delay penalty for high-severity patients (snake bite / respiratory) | Minimized / Zero critical delay |
| **Redundancy Rate** | Percentage of duplicate dispatches to the same location | Exactly 0% |
| **Approximation Ratio** | Ratio of QAOA solution cost to the exact optimal cost | $\ge 0.85$ for $p=1, 2$ |

---

## 6. How to Run & Get Started

### 1. Setup Environment
```bash
# Clone and enter the repository
cd /path/to/quantum/quantum

# Install dependencies using uv
uv sync
```

### 2. Configure IBM Quantum Cloud Credentials (Optional for Cloud QPU)
To execute QAOA circuits on actual IBM Quantum Cloud QPUs, set your IBM Quantum API token:
```bash
export QISKIT_IBM_TOKEN="your_ibm_quantum_api_token_here"
```
*(If no token is provided, the system automatically runs on the high-speed local Qiskit Aer simulator.)*

### 3. Launch the Interactive Real-World Web Dashboard
```bash
# Launch the interactive browser map application
uv run streamlit run app.py
```
*(Click anywhere on the map, describe the emergency in the prompt box, and watch the optimal quantum-assisted routes execute live!)*

### 4. Run the Jupyter Research & Benchmark Notebook
```bash
uv run jupyter notebook notebooks/emergency_routing.ipynb
```
