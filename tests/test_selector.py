from __future__ import annotations

from pathlib import Path

from agentgw.harness.spec import SkillRecord
from agentgw.skills.selector import select_skills


def _skill(name: str, description: str, **kwargs) -> SkillRecord:
    return SkillRecord(
        name=name,
        description=description,
        body=f"body-{name}",
        path=Path(f"/tmp/{name}/SKILL.md"),
        directory=Path(f"/tmp/{name}"),
        **kwargs,
    )


def test_explicit_slash_activates():
    skills = [
        _skill("greet", "Say hello when the user greets."),
        _skill("workspace-notes", "Take notes in the workspace."),
    ]
    chosen = select_skills("please /greet me", skills)
    assert [s.name for s in chosen] == ["greet"]


def test_keyword_overlap_activates_notes():
    skills = [
        _skill("greet", "Say hello when the user greets."),
        _skill(
            "workspace-notes",
            "Read and write notes in the workspace. Use when taking notes or saving text.",
        ),
    ]
    chosen = select_skills("please take notes about this meeting", skills)
    names = [s.name for s in chosen]
    assert "workspace-notes" in names
    assert "greet" not in names


def test_unrelated_prompt_activates_nothing():
    skills = [
        _skill("greet", "Say hello when the user greets."),
        _skill("workspace-notes", "Read and write notes in the workspace."),
    ]
    chosen = select_skills("what is 2+2?", skills)
    assert chosen == []


def test_always_on_skill():
    skills = [
        _skill("core", "Always available core instructions.", metadata={"always": True}),
        _skill("greet", "Say hello when the user greets."),
    ]
    chosen = select_skills("what is 2+2?", skills)
    assert [s.name for s in chosen] == ["core"]
