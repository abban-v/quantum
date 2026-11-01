"""Browser-flow smoke tests for the Streamlit dashboard.

These use the cached graph so they stay offline. If the cache has not been
prepared, the test is skipped rather than downloading data during the suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from quantum.sim import SimulationEngine

ROOT = Path(__file__).resolve().parents[1]
GRAPH_CACHE = ROOT / "data/cache/manhattan_drive.graphml"
APP = ROOT / "app.py"


def _button(app: AppTest, label: str):
    matches = [button for button in app.button if button.label == label]
    assert matches, f"button {label!r} not found"
    return matches[0]


@pytest.mark.skipif(
    not GRAPH_CACHE.exists(), reason="run scripts/prepare_data.py first"
)
def test_dispatch_starts_the_simulation_automatically():
    app = AppTest.from_file(str(APP), default_timeout=180)
    app.run()
    assert not app.exception

    app.selectbox[0].set_value("S4").run()
    assert not app.exception

    _button(app, "Dispatch").click().run()
    assert not app.exception

    engine = app.session_state["sim"]
    assert isinstance(engine, SimulationEngine)
    assert app.session_state["sim_playing"] is True
    assert app.session_state["plans"]
    assert engine.now >= app.session_state["plans_when"]

    _button(app, "Pause").click().run()
    assert not app.exception
    assert app.session_state["sim_playing"] is False

    before = engine.now
    _button(app, "Step").click().run()
    assert not app.exception
    assert app.session_state["sim"].now > before
