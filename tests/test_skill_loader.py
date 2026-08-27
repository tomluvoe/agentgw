from __future__ import annotations

from pathlib import Path

from agentgw.skills.gate import is_eligible
from agentgw.skills.loader import discover_skills, load_skill


def test_load_minimal_skill(tmp_path: Path):
    skill_dir = tmp_path / "hello-world"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello-world\ndescription: Say hello. Use when greeting.\n---\n\nWave.\n",
        encoding="utf-8",
    )
    skill = load_skill(skill_dir / "SKILL.md")
    assert skill.name == "hello-world"
    assert "greeting" in skill.description
    assert skill.body == "Wave."
    assert skill.directory == skill_dir.resolve()


def test_discover_later_root_overrides(tmp_path: Path):
    a = tmp_path / "a" / "greet"
    b = tmp_path / "b" / "greet"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "SKILL.md").write_text(
        "---\nname: greet\ndescription: First copy of greet skill.\n---\nA\n",
        encoding="utf-8",
    )
    (b / "SKILL.md").write_text(
        "---\nname: greet\ndescription: Second copy of greet skill.\n---\nB\n",
        encoding="utf-8",
    )
    skills = discover_skills([tmp_path / "a", tmp_path / "b"])
    assert len(skills) == 1
    assert skills[0].body == "B"


def test_gate_missing_env(tmp_path: Path):
    skill_dir = tmp_path / "needs-key"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: needs-key\n"
        "description: Needs a secret env var.\n"
        "metadata:\n"
        "  requires:\n"
        "    env: [TOTALLY_MISSING_AGENTGW_KEY]\n"
        "---\n\nNope.\n",
        encoding="utf-8",
    )
    skill = load_skill(skill_dir / "SKILL.md")
    assert is_eligible(skill, environ={}) is False
    assert is_eligible(skill, environ={"TOTALLY_MISSING_AGENTGW_KEY": "x"}) is True
