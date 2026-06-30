"""Chat (SSE) and agent-evaluation API routes for the Azure OpenAI agent.

Exposes a streaming chat endpoint that builds a per-request agent from one or
more stored skill prompts, plus an endpoint that scores how well the selected
skills combine (conflicts, contradictions, overlaps).
"""
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import agenteval, chat, store

logger = logging.getLogger("agent_skill_portal.chat")
router = APIRouter()


class EvaluateIn(BaseModel):
    """Request body for evaluating how a set of skills combine."""

    prompt_ids: list[str] = []


def _load_prompts(prompt_ids: list[str]) -> list:
    """Fetch existing prompts for the given ids, skipping any that are missing."""
    return [p for p in (store.get_prompt(pid) for pid in prompt_ids) if p is not None]


@router.get("/chat")
def stream_chat(
    q: str = Query(...),
    prompt_ids: list[str] | None = Query(default=None),
    prompt_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream an agent reply for ``q`` using one or more skills' instructions.

    Args:
        q: The user's question.
        prompt_ids: Identifiers of the skills to combine into the agent.
        prompt_id: Single-skill fallback for backward compatibility.

    Returns:
        StreamingResponse: A ``text/event-stream`` of ``data:`` lines.

    Raises:
        HTTPException: 404 when none of the requested skills exist.
    """
    ids = list(prompt_ids or ([] if prompt_id is None else [prompt_id]))
    prompts = _load_prompts(ids)
    if not prompts:
        raise HTTPException(status_code=404, detail="No matching skills found")

    agent = chat.build_agent(prompts)

    async def event_source():
        try:
            async for chunk in agent.run(q, stream=True):
                text = getattr(chunk, "text", None)
                if text:
                    for line in text.split("\n"):
                        yield f"data: {line}\n"
                    yield "\n"
        except Exception:
            logger.exception("Chat agent run failed for skills %s", ids)
            yield "data: [ERROR]\n\n"
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
