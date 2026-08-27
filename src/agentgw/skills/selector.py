"""Choose which skills get full bodies (L2) vs catalog-only (L1)."""

from __future__ import annotations

import re

from agentgw.harness.spec import SkillRecord

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    """
    a an the and or to for of in on at by with from as is are was were be
    this that it its if when then use using used should can may help how
    what your you we they them their task agent skill skills please just
    """.split()
)

EXPLICIT_RE = re.compile(
    r"(?:^|\s)[/\$]([a-z0-9]+(?:-[a-z0-9]+)*)\b",
    re.IGNORECASE,
)


def select_skills(
    message: str,
    skills: list[SkillRecord],
    *,
    always: list[str] | None = None,
    max_activated: int = 3,
) -> list[SkillRecord]:
    """Return skills whose full SKILL.md body should be injected this turn."""
    always_set = set(always or [])
    explicit = {m.group(1).lower() for m in EXPLICIT_RE.finditer(message)}
    msg_l = message.lower()
    scored: list[tuple[float, SkillRecord]] = []

    for skill in skills:
        if skill.name in always_set or _metadata_always(skill):
            scored.append((1_000.0, skill))
            continue
        if skill.disable_model_invocation and skill.name not in explicit:
            continue
        if skill.name in explicit or f"/{skill.name}" in msg_l or f"${skill.name}" in msg_l:
            scored.append((900.0, skill))
            continue
        if re.search(rf"\b{re.escape(skill.name)}\b", msg_l):
            scored.append((800.0, skill))
            continue
        score = _overlap_score(msg_l, skill)
        if score > 0:
            scored.append((score, skill))

    scored.sort(key=lambda item: item[0], reverse=True)
    chosen: list[SkillRecord] = []
    seen: set[str] = set()
    for score, skill in scored:
        if skill.name in seen:
            continue
        # Keyword overlap must clear a small bar unless it was explicit/always.
        if score < 2.0:
            continue
        chosen.append(skill)
        seen.add(skill.name)
        if len(chosen) >= max_activated:
            break
    return chosen


def _metadata_always(skill: SkillRecord) -> bool:
    meta = skill.metadata
    if meta.get("always") is True:
        return True
    for key in ("openclaw", "clawdbot"):
        nested = meta.get(key)
        if isinstance(nested, dict) and nested.get("always") is True:
            return True
    return False


def _overlap_score(message: str, skill: SkillRecord) -> float:
    msg_tokens = _tokens(message)
    desc_tokens = _tokens(skill.description)
    extra = skill.metadata.get("when_to_use") or skill.metadata.get("when-to-use")
    if extra:
        desc_tokens |= _tokens(str(extra))
    if not msg_tokens or not desc_tokens:
        return 0.0
    overlap = msg_tokens & desc_tokens
    if not overlap:
        return 0.0
    strong = {t for t in overlap if len(t) >= 4}
    if not strong and len(overlap) < 2:
        return 0.0
    return float(len(overlap) + len(strong))


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1}
