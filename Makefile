.PHONY: test demo plan plan-check prepare-data

test:
	uv run pytest -q

demo:
	uv run streamlit run app.py

plan:
	uv run python scripts/plan_sync.py

plan-check:
	uv run python scripts/plan_sync.py --check

prepare-data:
	uv run python scripts/prepare_data.py
