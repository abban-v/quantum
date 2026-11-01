# AGENTS.md — working agreement for this repository

## Read first

1. `~/.opencode/plan/implementation.md` is the living plan (canonical copy).
2. `plan/tasks.yaml` is the machine-readable task registry.
3. `data/curated/README.md` documents what is real, curated, or synthetic.

## After completing work

1. Update the relevant task's `status` in `plan/tasks.yaml`:
   - `doing` while in progress
   - `review` when implemented but needing human judgment
   - never set `verified`; only a human may do that
2. Run `make plan` to regenerate the status block in the plan.
3. Run `make test` and `make plan-check`.
4. Do not mark a task `done` by hand; evidence must pass.

## Ground rules

- Keep the demo runnable with no network after the graph cache exists.
- Never present simulated ED offload, traffic, or clearance values as live data.
- Every data record must keep its `source` field (`real`, `curated`, `synthetic`).
- Do not add cloud dependencies to the demo path. Ollama is optional and local.
- Keep the quantum subproblem within `max_quantum_stops**2 <= max_qubits`.
- Run Qiskit work through `run_with_large_stack` when called from Streamlit.
- Prefer small modules and explicit errors over silent fallbacks.
