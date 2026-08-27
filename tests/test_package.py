from __future__ import annotations

from pathlib import Path

from agentgw.agent.package import load_package
from agentgw.harness.run import Harness
from tests.conftest import DEMO_AGENT


def test_demo_package_includes_shared_skills():
    pkg = load_package(DEMO_AGENT)
    names = {s.name for s in pkg.skills}
    assert "greet" in names
    assert "workspace-notes" in names
    assert pkg.tool_policy.permits("echo")
    assert "echo" in pkg.registry.names()


def test_compile_activates_greet_only():
    pkg = load_package(DEMO_AGENT)
    harness = Harness(pkg, llm=None)
    spec = harness.compile("hello there, please greet me")
    activated = {s.name for s in spec.activated_skills}
    assert "greet" in activated
    assert "workspace-notes" not in activated
    assert "<available_skills>" in spec.system_prompt
    assert "### greet" in spec.system_prompt


def test_skill_allow_filters(tmp_path: Path):
    agent = tmp_path / "AGENT.md"
    skills = tmp_path / "skills" / "greet"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: greet\ndescription: Say hello when greeting.\n---\nHi.\n",
        encoding="utf-8",
    )
    other = tmp_path / "skills" / "other"
    other.mkdir()
    (other / "SKILL.md").write_text(
        "---\nname: other\ndescription: Something else entirely.\n---\nNope.\n",
        encoding="utf-8",
    )
    agent.write_text(
        "---\n"
        "name: boxed\n"
        "description: Only greet.\n"
        "skills:\n"
        "  roots: [skills]\n"
        "  allow: [greet]\n"
        "---\n\nYou are boxed.\n",
        encoding="utf-8",
    )
    pkg = load_package(agent)
    assert [s.name for s in pkg.skills] == ["greet"]
