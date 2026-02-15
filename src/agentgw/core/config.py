"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5.2-2025-12-11"
    temperature: float = 0.7
    max_tokens: int = 4096


class AgentConfig(BaseModel):
    max_iterations: int = 10
    max_orchestration_depth: int = 3


class StorageConfig(BaseModel):
    sqlite_path: str = "data/agentgw.db"
    chroma_path: str = "data/chroma"
    log_dir: str = "data/logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTGW_",
        env_nested_delimiter="__",
    )

    llm: LLMConfig = LLMConfig()
    agent: AgentConfig = AgentConfig()
    storage: StorageConfig = StorageConfig()
    skills_dir: str = "skills"
    tools_modules: list[str] = ["agentgw.tools"]

    openai_api_key: str = ""

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        """Load settings from YAML file, then overlay env vars."""
        data: dict = {}
        if config_path and config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
        return cls(**data)


def get_project_root() -> Path:
    """Walk up from CWD to find pyproject.toml, or fall back to CWD."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current


def load_settings() -> Settings:
    """Load settings from the project root's config/settings.yaml."""
    root = get_project_root()
    return Settings.load(root / "config" / "settings.yaml")
