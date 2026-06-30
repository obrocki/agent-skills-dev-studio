"""LLM-as-judge evaluation for combined skills.

Scores whether several skill prompts can be merged into one agent without
conflicts, contradictions, or excessive overlap. Reuses the same managed
identity Azure OpenAI client as the chat agent — no API key and no extra SDKs.
"""
import json
import logging
import re

from backend import chat

logger = logging.getLogger("agent_skill_portal.eval")

_JUDGE_INSTRUCTIONS = (
    "You review whether several AI agent 'skills' (system prompts) can be combined "
    "into ONE agent that follows all of them at once.\n"
    "Check for:\n"
    "- conflict: rules that cannot all be satisfied (e.g. 'only discuss cooking' vs 'only discuss weather').\n"
    "- contradiction: directly opposing instructions.\n"
    "- overlap: redundant or duplicated scope.\n"
    "- gap: ambiguity created only by combining them.\n\n"
    "Reply with ONLY a JSON object (no prose, no markdown fences) of the form:\n"
    '{"score": <int 0-100, 100 = fully compatible>, '
    '"rating": "Compatible|Minor issues|Conflicting", '
    '"summary": "<one short sentence>", '
    '"findings": [{"type": "conflict|contradiction|overlap|gap", '
    '"severity": "high|medium|low", "skills": ["<skill name>", ...], '
    '"detail": "<short explanation>"}]}\n'
    "Scoring: start at 100; subtract a lot for high-severity conflicts or contradictions, "
    "some for medium, a little for overlaps or gaps. Use an empty findings list when the "
    "skills combine cleanly."
)


def _rating(score: int) -> str:
    """Map a 0-100 score to a human-readable rating."""
    if score >= 85:
        return "Compatible"
    if score >= 60:
        return "Minor issues"
    return "Conflicting"


def _color(score: int) -> str:
    """Return an HSL colour from red (conflicting) to green (compatible)."""
    hue = round(120 * score / 100)
    return f"hsl({hue}, 70%, 45%)"


def _format_skills(prompts: list) -> str:
    """Serialise skills into a single prompt for the judge."""
    parts = [
        f"### {getattr(p, 'name', 'skill')}\n{(getattr(p, 'content', '') or '').strip()}"
        for p in prompts
    ]
    return "Skills to combine into one agent:\n\n" + "\n\n".join(parts)


def _parse_json(text: str) -> dict:
    """Extract the first JSON object from the model's reply."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    raw = match.group(0) if match else (text or "")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize(data: dict) -> dict:
    """Clamp and shape the judge output into the response contract."""
    try:
        score = int(round(float(data.get("score", 100))))
    except (TypeError, ValueError):
        score = 100
    score = max(0, min(100, score))

    findings = []
    for item in data.get("findings") or []:
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "type": str(item.get("type", "issue")),
                "severity": str(item.get("severity", "medium")),
                "skills": [str(s) for s in (item.get("skills") or []) if s],
                "detail": str(item.get("detail", "")),
            }
        )

    return {
        "score": score,
        "rating": str(data.get("rating") or _rating(score)),
        "color": _color(score),
        "summary": str(data.get("summary", "")),
        "findings": findings,
    }


async def evaluate_combination(prompts: list) -> dict:
    """Score how well the given skill prompts combine into one agent.

    Args:
        prompts: Skill objects exposing ``name`` and ``content``.

    Returns:
        dict: ``score`` (0-100, or ``None`` when the check could not run),
        ``rating``, ``color``, ``summary`` and a ``findings`` list of detected
        conflicts, contradictions, or overlaps. Fewer than two skills with
        content returns a perfect, empty result.
    """
    real = [p for p in prompts if p is not None and (getattr(p, "content", "") or "").strip()]
    if len(real) < 2:
        return {
            "score": 100,
            "rating": "Compatible",
            "color": _color(100),
            "summary": "Add two or more skills with content to check for conflicts.",
            "findings": [],
        }

    agent = chat.make_agent(_JUDGE_INSTRUCTIONS, "Skill Conflict Reviewer")
    try:
        result = await agent.run(_format_skills(real))
    except Exception:
        logger.exception("Conflict evaluation failed for %d skills", len(real))
        return {
            "score": None,
            "rating": "Unavailable",
            "color": "hsl(220, 9%, 60%)",
            "summary": "Conflict check is unavailable right now.",
            "findings": [],
        }

    text = getattr(result, "text", None) or str(result)
    return _normalize(_parse_json(text))
