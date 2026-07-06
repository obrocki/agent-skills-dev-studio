"""Chat (SSE) and agent-evaluation API routes for the Azure OpenAI agent.

Exposes a streaming chat endpoint that builds a per-request agent from one or
more stored skill prompts, plus an endpoint that scores how well the selected
skills combine (conflicts, contradictions, overlaps).
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import adherence, agenteval, chat, store, validate

logger = logging.getLogger("agent_skill_portal.chat")
router = APIRouter()


def _now() -> str:
    """Return a stable UTC timestamp string for streamed chat events."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sse_log(level: str, message: str) -> str:
    """Format one activity-log entry as a named ``log`` server-sent event.

    These frames ride the same stream as the reply text but carry an
    ``event: log`` name so the browser routes them to the activity panel via a
    dedicated listener, leaving the assistant message that ``onmessage``
    assembles untouched.

    Args:
        level: A severity/category tag ("info", "tool", "done", "error", …)
            used by the client to colour the entry.
        message: The human-readable status line to display.

    Returns:
        str: A ready-to-yield SSE frame terminated by a blank line.
    """
    payload = json.dumps(
        {
            "level": level,
            "msg": message,
            "t": _now(),
        }
    )
    return f"event: log\ndata: {payload}\n\n"


def _sse_eval(payload: dict) -> str:
    """Format one adherence-evaluation result as a named ``eval`` SSE event.

    Args:
        payload: A single contract result dict (``key``, ``title``, ``score``,
            ``rating``, ``color``, ``summary`` and ``findings``).

    Returns:
        str: A ready-to-yield SSE frame terminated by a blank line.
    """
    return f"event: eval\ndata: {json.dumps(payload)}\n\n"


def _sse_history(payload: dict) -> str:
    """Format persisted history metadata as a named SSE event."""
    return f"event: history\ndata: {json.dumps(payload)}\n\n"


def _tool_log(
    content, seen_calls: set[str], seen_results: set[str]
) -> str | None:
    """Build a one-shot log frame for a tool call or result content item.

    Streaming updates deliver a single tool invocation across several
    fragments (the name arrives first, then the arguments accumulate); the
    ``seen_*`` sets make sure each call and its result are announced exactly
    once rather than on every fragment.

    Args:
        content: A framework ``Content`` item from a streamed chunk.
        seen_calls: Call identifiers already announced as "calling".
        seen_results: Call identifiers already announced as "finished".

    Returns:
        str | None: An SSE ``log`` frame, or ``None`` when this item needs no
        new entry.
    """
    ctype = getattr(content, "type", None)
    if ctype == "function_call":
        name = getattr(content, "name", None)
        key = getattr(content, "call_id", None) or name
        if name and key not in seen_calls:
            seen_calls.add(key)
            return _sse_log("tool", f"Calling tool: {name}")
    elif ctype == "function_result":
        key = getattr(content, "call_id", None)
        if key and key not in seen_results:
            seen_results.add(key)
            exception = getattr(content, "exception", None)
            if exception:
                return _sse_log("error", f"Tool error: {exception}")
            return _sse_log("tool", "Tool finished.")
    return None


class EvaluateIn(BaseModel):
    """Request body for evaluating how a set of skills combine."""

    prompt_ids: list[str] = []


def _load_prompts(prompt_ids: list[str]) -> list:
    """Fetch existing prompts for the given ids, skipping any that are missing."""
    return [
        p
        for p in (store.get_prompt(pid) for pid in prompt_ids)
        if p is not None
    ]


def _prompt_version_refs(prompts: list[store.Prompt]) -> list[dict]:
    """Anchor prompts to saved snapshots so later comparisons stay stable."""
    refs = []
    for prompt in prompts:
        score = validate.validate_skill(
            prompt.name, prompt.description, prompt.content
        )["score"]
        version = store.ensure_prompt_version(prompt, score)
        refs.append(
            {
                "prompt_id": prompt.id,
                "prompt_name": prompt.name,
                "version_id": version.id,
                "version": version.version,
            }
        )
    return refs


def _tool_calls_payload(calls: dict[str, dict]) -> list[dict]:
    """Serialise captured tool invocations into stable saved records."""
    payload = []
    for call_id in sorted(calls):
        item = calls[call_id]
        payload.append(
            {
                "call_id": call_id,
                "name": item.get("name"),
                "arguments": item.get("arguments"),
                "result": item.get("result"),
                "error": item.get("error"),
            }
        )
    return payload


@router.get("/chat")
def stream_chat(
    q: str = Query(...),
    prompt_ids: list[str] | None = Query(default=None),
    prompt_id: str | None = Query(default=None),
    time_zone: str | None = Query(default=None),
    locale: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream an agent reply for ``q`` using one or more skills' instructions.

    Args:
        q: The user's question.
        prompt_ids: Identifiers of the skills to combine into the agent.
        prompt_id: Single-skill fallback for backward compatibility.
        time_zone: The caller's IANA time zone, threaded to skill executors.
        locale: The caller's BCP 47 locale, threaded to skill executors.

    Returns:
        StreamingResponse: A ``text/event-stream`` of ``data:`` lines.

    Raises:
        HTTPException: 404 when none of the requested skills exist.
    """
    ids = list(prompt_ids or ([] if prompt_id is None else [prompt_id]))
    prompts = _load_prompts(ids)
    if not prompts:
        raise HTTPException(status_code=404, detail="No matching skills found")

    agent = chat.build_agent(prompts, time_zone=time_zone, locale=locale)
    prompt_names = [getattr(prompt, "name", "") or "unnamed" for prompt in prompts]
    prompt_versions = _prompt_version_refs(prompts)
    tool_names = chat.run_tool_names(prompts)
    skill_names = ", ".join(
        (getattr(p, "name", "") or "").strip() or "unnamed" for p in prompts
    )[:160]

    async def event_source():
        seen_calls: set[str] = set()
        seen_results: set[str] = set()
        answering = False
        full_reply: list[str] = []
        calls: dict[str, dict] = {}
        ran_ok = False
        run_start_time = _now()
        pre_run_eval = {
            "score": None,
            "rating": "Unavailable",
            "summary": "Compatibility check did not complete.",
            "findings": [],
        }
        yield _sse_log(
            "info",
            f"Assembling agent from {len(prompts)} skill(s): {skill_names}.",
        )
        yield _sse_log("info", "Anchoring prompt snapshots and scoring the setup…")
        try:
            pre_run_eval = await agenteval.evaluate_combination(prompts)
        except Exception:
            logger.exception("Pre-run evaluation failed for skills %s", ids)
            yield _sse_log(
                "error",
                "Compatibility check failed — continuing without a saved pre-run score.",
            )
        yield _sse_log(
            "info", "Contacting Azure OpenAI and streaming the reply…"
        )
        try:
            async for chunk in agent.run(q, stream=True):
                for content in getattr(chunk, "contents", None) or []:
                    frame = _tool_log(content, seen_calls, seen_results)
                    if frame:
                        yield frame
                    ctype = getattr(content, "type", None)
                    if ctype == "function_call":
                        name = getattr(content, "name", None)
                        key = getattr(content, "call_id", None) or name
                        slot = calls.setdefault(
                            key, {"name": None, "arguments": ""}
                        )
                        if name:
                            slot["name"] = name
                        arguments = getattr(content, "arguments", None)
                        if isinstance(arguments, str):
                            slot["arguments"] += arguments
                        elif arguments is not None:
                            slot["arguments"] = arguments
                    elif ctype == "function_result":
                        key = getattr(content, "call_id", None)
                        slot = calls.setdefault(
                            key, {"name": None, "arguments": ""}
                        )
                        slot["error"] = getattr(content, "exception", None)
                        slot["result"] = getattr(content, "result", None)
                text = getattr(chunk, "text", None)
                if text:
                    full_reply.append(text)
                    if not answering:
                        answering = True
                        yield _sse_log(
                            "info", "Model is composing the answer…"
                        )
                    for line in text.split("\n"):
                        yield f"data: {line}\n"
                    yield "\n"
            yield _sse_log("done", "Reply complete.")
            ran_ok = True
        except Exception:
            logger.exception("Chat agent run failed for skills %s", ids)
            yield _sse_log("error", "The agent run failed — see server logs.")
            yield "data: [ERROR]\n\n"
            ran_ok = False
        if ran_ok:
            yield _sse_log("info", "Evaluating the run…")
            try:
                payloads = await adherence.run_all(
                    q, "".join(full_reply), prompts, calls
                )
                for payload in payloads:
                    yield _sse_eval(payload)
                revision, turn = store.save_chat_turn(
                    query=q,
                    answer="".join(full_reply),
                    prompt_ids=ids,
                    prompt_names=prompt_names,
                    prompt_versions=prompt_versions,
                    tool_names=tool_names,
                    tool_calls=_tool_calls_payload(calls),
                    pre_run_evaluation=pre_run_eval,
                    evaluations=payloads,
                    created_at=run_start_time,
                )
                yield _sse_history(
                    {
                        "revision": store.revision_summary(revision),
                        "turn": turn.model_dump(),
                    }
                )
            except Exception:
                logger.exception(
                    "Post-run evaluation/persistence failed for skills %s", ids
                )
                yield _sse_log(
                    "error",
                    "Evaluation or history persistence failed — see server logs.",
                )
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/agents/evaluate")
async def evaluate_agent(body: EvaluateIn) -> dict:
    """Score how well the selected skills combine into one agent.

    Args:
        body: The skill ids to evaluate together.

    Returns:
        dict: ``score`` (0-100 or ``None``), ``rating``, ``color``, ``summary``
        and a ``findings`` list of detected conflicts, contradictions, or
        overlaps.
    """
    return await agenteval.evaluate_combination(_load_prompts(body.prompt_ids))


@router.get("/health")
async def health() -> dict:
    """Probe the Azure OpenAI endpoint/model and report its status.

    Returns:
        dict: ``status``, ``detail``, ``endpoint`` and ``model`` describing
        whether the managed-identity model call succeeded.
    """
    return await chat.check_health()
