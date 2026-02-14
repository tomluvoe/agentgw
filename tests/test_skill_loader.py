"""Tests for skill loading and validation."""

from pathlib import Path

import pytest

from agentgw.core.skill_loader import SkillLoader


@pytest.fixture
def skills_dir(tmp_dir):
    d = tmp_dir / "skills"
    d.mkdir()
    return d


def _write_skill(skills_dir: Path, name: str, content: str):
    (skills_dir / f"{name}.yaml").write_text(content)


class TestSkillLoader:
    def test_load_valid_skill(self, skills_dir):
        _write_skill(skills_dir, "test", """
name: test_skill
description: A test skill
system_prompt: You are helpful.
tools:
  - read_file
temperature: 0.3
tags:
  - testing
""")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert "test_skill" in skills
        skill = skills["test_skill"]
        assert skill.name == "test_skill"
        assert skill.description == "A test skill"
        assert skill.tools == ["read_file"]
        assert skill.temperature == 0.3
        assert skill.tags == ["testing"]

    def test_load_minimal_skill(self, skills_dir):
        _write_skill(skills_dir, "minimal", """
name: minimal
description: Minimal skill
system_prompt: Be helpful.
""")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()

        assert "minimal" in skills
        skill = skills["minimal"]
        assert skill.tools == []
        assert skill.temperature == 0.7
        assert skill.tags == []

    def test_missing_required_field(self, skills_dir):
        _write_skill(skills_dir, "bad", """
name: bad_skill
description: Missing system_prompt
""")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()
        # Should skip invalid skill
        assert "bad_skill" not in skills

    def test_ignores_underscore_files(self, skills_dir):
        _write_skill(skills_dir, "_schema", """
name: should_ignore
description: Schema file
system_prompt: ignored
""")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()
        assert len(skills) == 0

    def test_load_multiple_skills(self, skills_dir):
        for i in range(3):
            _write_skill(skills_dir, f"skill_{i}", f"""
name: skill_{i}
description: Skill number {i}
system_prompt: You are skill {i}.
""")
        loader = SkillLoader(skills_dir)
        skills = loader.load_all()
        assert len(skills) == 3

    def test_empty_directory(self, tmp_dir):
        empty_dir = tmp_dir / "empty"
        empty_dir.mkdir()
        loader = SkillLoader(empty_dir)
        skills = loader.load_all()
        assert len(skills) == 0

    def test_nonexistent_directory(self, tmp_dir):
        loader = SkillLoader(tmp_dir / "nonexistent")
        skills = loader.load_all()
        assert len(skills) == 0
