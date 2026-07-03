"""Adherence evaluations for agent replies.

Scores whether an agent's reply followed the skill instructions it was given,
whether it actually fulfilled the user's request, and whether the executable
``run_*`` skill tools that were expected to run were actually invoked with
sensible arguments.

All three graded dimensions are backed by the Microsoft Azure AI Evaluation SDK
(:mod:`azure.ai.evaluation`): skill and task adherence use
:class:`~azure.ai.evaluation.TaskAdherenceEvaluator` (a binary pass/fail judge
in 1.17.0) and tool-call adherence uses
:class:`~azure.ai.evaluation.ToolCallAccuracyEvaluator` (a 1-5 judge). Each
evaluator builds its own Azure OpenAI judge client from the app's
managed-identity settings (no API key) and the sync credential from
:func:`backend.chat.build_sync_credential`. The SDK evaluators are synchronous,
so every ``__call__`` is dispatched through :func:`asyncio.to_thread` to avoid
blocking the event loop. The JSON/colour helpers from :mod:`backend.agenteval`
are reused so the eval-frame contract stays identical to the skill-clash card;
``agenteval`` does not import this module, so there is no import cycle.
"""

import asyncio
import json
import logging
import math
import re

from azure.ai.evaluation import (
    TaskAdherenceEvaluator,
    ToolCallAccuracyEvaluator,
)

from backend import agenteval, chat, config

logger = logging.getLogger("agent_skill_portal.adherence")

# The Unavailable colour mirrors backend/agenteval.py:129-137. agenteval._color
# only accepts an int score, so the gray literal is used directly rather than
# agenteval._color(None).
_GRAY = "hsl(220, 9%, 60%)"

# The Azure AI Evaluation SDK judges call Azure OpenAI over the classic
# ``/openai/deployments/{deployment}/chat/completions?api-version=`` path, which
# requires a dated api-version. The app's ``AZURE_OPENAI_API_VERSION`` may be the
# v1 value ``"preview"`` (used by the chat agent), which 404s on that path, so a
# dated fallback is used for the judge client.
_JUDGE_API_VERSION = "2024-10-21"


def _model_config() -> dict:
    """Build the managed-identity Azure OpenAI model config for the judges.

    Reads the app's Azure OpenAI settings and returns a
    :class:`~azure.ai.evaluation.AzureOpenAIModelConfiguration`-shaped dict with
    no ``api_key`` so the SDK authenticates the judge model with the sync
    credential from :func:`backend.chat.build_sync_credential` (managed
    identity). Called lazily inside the evaluators so importing this module
    never requires Azure configuration.

    Returns:
        dict: ``{"azure_endpoint", "azure_deployment", "api_version"}``.
    """
    settings = config.load_settings()
    api_version = settings.api_version
    if not re.match(r"^\d{4}-\d{2}-\d{2}", api_version or ""):
        api_version = _JUDGE_API_VERSION
    return {
        "azure_endpoint": settings.endpoint,
        "azure_deployment": settings.chat_model,
        "api_version": api_version,
    }


def _as_dict(arguments) -> dict:
    """Coerce captured tool-call ``arguments`` into a dict.

    Args:
        arguments: Either an already-decoded mapping or a JSON string captured
            from the streamed tool call.

    Returns:
        dict: ``arguments`` unchanged when it is already a mapping, the parsed
        object when it is a JSON string, or an empty dict when it is empty or
        cannot be parsed.
    """
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            parsed = json.loads(arguments)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _scale_1_5(score: float) -> int:
    """Map a 1-5 evaluator score onto a 0-100 scale.

    Uses ``(score - 1) / 4 * 100`` so the evaluator's default pass threshold of
    3 lands at 50 (1 -> 0, 3 -> 50, 5 -> 100).

    Args:
        score: A raw 1-5 evaluator score.

    Returns:
        int: The rounded 0-100 score.
    """
    return round((score - 1) / 4 * 100)


def _rating_adherence(score) -> str:
    """Map a 0-100 adherence score to a human-readable rating.

    Args:
        score: A 0-100 integer score, or ``None`` when the check did not run.

    Returns:
        str: ``"Adherent"``, ``"Partial"``, ``"Off-track"``, or ``"Unavailable"``.
    """
    if score is None:
        return "Unavailable"
    if score >= 80:
        return "Adherent"
    if score >= 50:
        return "Partial"
    return "Off-track"


def _contract(score100: int, reason: str, kind: str) -> dict:
    """Build the eval-frame contract for a graded adherence dimension.

    Args:
        score100: The 0-100 adherence score.
        reason: The evaluator's reasoning text (truncated for the summary).
        kind: The finding type to emit (``"adherence"`` or ``"tool-call"``).

    Returns:
        dict: ``{score, rating, color, summary, findings}``. Exactly one finding
        (``high`` severity below 40, otherwise ``medium``) is added only when
        ``score100`` is below 60.
    """
    findings: list[dict] = []
    if score100 < 60:
        findings.append(
            {
                "type": kind,
                "severity": "high" if score100 < 40 else "medium",
                "skills": [],
                "detail": reason,
            }
        )
    return {
        "score": score100,
        "rating": _rating_adherence(score100),
        "color": agenteval._color(score100),
        "summary": reason[:200],
        "findings": findings,
    }


def _unavailable_contract(summary: str) -> dict:
    """Return the "check could not run" contract used on any failure path.

    Mirrors the failure contract emitted by
    :func:`backend.agenteval.evaluate_combination`.

    Args:
        summary: A short, human-readable reason the check is unavailable.

    Returns:
        dict: A contract with a ``None`` score, gray colour, and no findings.
    """
    return {
        "score": None,
        "rating": "Unavailable",
        "color": _GRAY,
        "summary": summary,
        "findings": [],
    }


async def _task_adherence(query, response: str) -> dict:
    """Run the SDK task-adherence judge and map it onto the contract.

    Args:
        query: The judge ``query`` — either a plain user request string or a
            message list carrying skill instructions as a system message.
        response: The agent's reply to judge.

    Returns:
        dict: The eval-frame contract; the Unavailable contract when the judge
        fails, is "not applicable", or returns no score.
    """
    evaluator = TaskAdherenceEvaluator(
        _model_config(),
        credential=chat.build_sync_credential(),
        is_reasoning_model=True,
    )
    try:
        result = await asyncio.to_thread(
            lambda: evaluator(query=query, response=response)
        )
    except Exception:
        logger.exception("Task adherence judge failed")
        return _unavailable_contract("Adherence unavailable.")

    if (
        result.get("task_adherence_status") == "not applicable"
        or result.get("task_adherence") is None
    ):
        return _unavailable_contract("Adherence not applicable.")

    passed = bool(result.get("task_adherence_passed"))
    return _contract(
        100 if passed else 0,
        str(result.get("task_adherence_reason", "")),
        "adherence",
    )


async def skill_adherence(query: str, response: str, context: str) -> dict:
    """Judge whether ``response`` followed the skill instructions in ``context``.

    The skill instructions ride in a ``system`` message inside the judge
    ``query`` so :class:`~azure.ai.evaluation.TaskAdherenceEvaluator` measures
    adherence to those instructions rather than general answer quality.

    Args:
        query: The user's request.
        response: The agent's reply to judge.
        context: The combined skill instructions the agent was given.

    Returns:
        dict: The eval-frame contract from :func:`_task_adherence`.
    """
    return await _task_adherence(
        [
            {"role": "system", "content": context},
            {"role": "user", "content": query},
        ],
        response,
    )


async def task_adherence(query: str, response: str) -> dict:
    """Judge whether ``response`` actually fulfilled the user's ``query``.

    Args:
        query: The user's request.
        response: The agent's reply to judge.

    Returns:
        dict: The eval-frame contract from :func:`_task_adherence`.
    """
    return await _task_adherence(query, response)


async def evaluate_tool_calls(
    query: str, calls: dict, tool_definitions: list[dict]
) -> dict:
    """Score whether the expected ``run_*`` tools were called correctly.

    When the agent invoked no tools, a score-0 ``tool-call`` contract is
    returned without constructing the SDK evaluator (a fully offline path).
    Otherwise the actually-invoked tool calls are scored against the supplied
    ``tool_definitions`` with
    :class:`~azure.ai.evaluation.ToolCallAccuracyEvaluator`.

    Args:
        query: The user's request (the judge's ``query``).
        calls: A mapping of call id to ``{"name": str, "arguments": ...}`` for
            each tool the agent actually invoked.
        tool_definitions: The OpenAI-style ``run_*`` tool schemas the agent was
            offered (required by the evaluator).

    Returns:
        dict: ``{score, rating, color, summary, findings}``; the Unavailable
        contract when the judge fails, is "not applicable", or returns no score.
    """
    made = [
        {
            "type": "tool_call",
            "tool_call_id": call_id,
            "name": c["name"],
            "arguments": _as_dict(c.get("arguments")),
        }
        for call_id, c in calls.items()
        if c.get("name")
    ]
    if not made:
        return _contract(
            0,
            "The agent did not call the expected run_<skill> tool.",
            "tool-call",
        )

    evaluator = ToolCallAccuracyEvaluator(
        _model_config(),
        credential=chat.build_sync_credential(),
        is_reasoning_model=True,
    )
    try:
        result = await asyncio.to_thread(
            lambda: evaluator(
                query=query,
                tool_definitions=tool_definitions,
                tool_calls=made,
            )
        )
    except Exception:
        logger.exception("Tool-call judge failed")
        return _unavailable_contract("Tool-call adherence unavailable.")

    score = result.get("tool_call_accuracy") or result.get(
        "tool_call_accuracy_score"
    )
    if (
        result.get("tool_call_accuracy_status") == "not applicable"
        or score is None
        or (isinstance(score, float) and math.isnan(score))
    ):
        return _unavailable_contract("Tool-call adherence not applicable.")

    return _contract(
        _scale_1_5(float(score)),
        str(result.get("tool_call_accuracy_reason", "")),
        "tool-call",
    )


async def run_all(query: str, answer: str, prompts, calls: dict) -> list[dict]:
    """Run every adherence evaluation and return ordered contract frames.

    Runs the skill-adherence and task-adherence judges, and — only when the
    supplied prompts contribute executable ``run_*`` tools — the tool-call
    adherence check.

    Args:
        query: The user's request.
        answer: The agent's final reply.
        prompts: A single prompt object or a list of them, each exposing
            ``name``, ``content``, and optionally ``code``.
        calls: A mapping of call id to ``{"name": str, "arguments": ...}`` for
            each tool the agent actually invoked.

    Returns:
        list[dict]: Ordered eval-frame dicts, each ``{"key", "title", **contract}``
        for ``skill``, ``task``, and (when applicable) ``tools``.
    """
    plist = prompts if isinstance(prompts, list) else [prompts]
    skill_ctx = "\n\n".join((getattr(p, "content", "") or "") for p in plist)

    frames: list[dict] = [
        {
            "key": "skill",
            "title": "Skill adherence",
            **await skill_adherence(query, answer, skill_ctx),
        },
        {
            "key": "task",
            "title": "Task adherence",
            **await task_adherence(query, answer),
        },
    ]

    tool_defs = chat.run_tool_definitions(plist)
    if tool_defs:
        frames.append(
            {
                "key": "tools",
                "title": "Tool-call adherence",
                **await evaluate_tool_calls(query, calls, tool_defs),
            }
        )

    return frames
