"""Construct an LLM provider from env + agent config."""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        env = parent / ".env"
        if env.is_file():
            load_dotenv(env)
            return
        if (parent / "pyproject.toml").is_file():
            load_dotenv(parent / ".env")
            return


def create_llm(provider: str | None = None, model: str | None = None):
    _load_dotenv()
    name = (provider or os.environ.get("AGENTGW_LLM_PROVIDER") or "openai").lower()
    model = model or os.environ.get("AGENTGW_LLM_MODEL")

    if name == "openai":
        from agentgw.llm.openai_provider import OpenAIProvider

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return OpenAIProvider(api_key=api_key, default_model=model or "gpt-4o-mini")

    if name == "anthropic":
        from agentgw.llm.anthropic_provider import AnthropicProvider

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        return AnthropicProvider(
            api_key=api_key,
            default_model=model or "claude-3-5-sonnet-20241022",
        )

    if name in {"xai", "grok"}:
        from agentgw.llm.xai_provider import XAIProvider

        api_key = os.environ.get("XAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("XAI_API_KEY is not set")
        return XAIProvider(api_key=api_key, default_model=model or "grok-beta")

    raise ValueError(f"Unknown LLM provider: {name}. Use openai, anthropic, or xai.")
