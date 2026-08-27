from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.tools.registry import reset_builtin_tools

ROOT = Path(__file__).resolve().parents[1]
DEMO_AGENT = ROOT / "agents" / "demo"
SHARED_SKILLS = ROOT / "skills"


@pytest.fixture(autouse=True)
def _reset_tools():
    reset_builtin_tools()
    yield
    reset_builtin_tools()
