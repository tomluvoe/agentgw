"""Load-time eligibility checks for skills (bins, env, OS)."""

from __future__ import annotations

import os
import shutil
import sys
from typing import Any

from agentgw.harness.spec import SkillRecord


def is_eligible(skill: SkillRecord, environ: dict[str, str] | None = None) -> bool:
    """Return True if the skill can run in this environment."""
    env = environ if environ is not None else dict(os.environ)
    requires = _requires_block(skill.metadata)
    if not requires:
        return True

    os_list = _as_list(requires.get("os") or skill.metadata.get("os"))
    if os_list and _platform_name() not in os_list:
        return False

    always = requires.get("always") or skill.metadata.get("always")
    if always is True:
        return True

    req = requires.get("requires") or requires
    bins = _as_list(req.get("bins") if isinstance(req, dict) else None)
    any_bins = _as_list(req.get("anyBins") if isinstance(req, dict) else None)
    env_vars = _as_list(req.get("env") if isinstance(req, dict) else None)

    for binary in bins:
        if shutil.which(binary) is None:
            return False
    if any_bins and not any(shutil.which(b) for b in any_bins):
        return False
    for var in env_vars:
        if not env.get(var):
            return False
    return True


def _requires_block(metadata: dict[str, Any]) -> dict[str, Any]:
    """Accept Agent Skills metadata plus OpenClaw nested requires if present."""
    if not metadata:
        return {}
    for key in ("openclaw", "clawdbot"):
        nested = metadata.get(key)
        if isinstance(nested, dict):
            return nested
    if "requires" in metadata or "os" in metadata or "always" in metadata:
        return metadata
    return {}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _platform_name() -> str:
    if sys.platform.startswith("darwin"):
        return "darwin"
    if sys.platform.startswith("win"):
        return "win32"
    return "linux"
