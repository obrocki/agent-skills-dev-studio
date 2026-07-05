"""JSON-backed storage for projects and prompts.

Persists data to ``backend/data/projects.json`` and ``backend/data/prompts.json``
using atomic writes. A project has a one-to-many relationship with prompts;
deleting a project cascades to its prompts.
"""

import datetime
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

_DATA_DIR = Path(__file__).resolve().parent / "data"
_PROJECTS_FILE = _DATA_DIR / "projects.json"
_PROMPTS_FILE = _DATA_DIR / "prompts.json"
_VERSIONS_FILE = _DATA_DIR / "prompt_versions.json"
_REVISIONS_FILE = _DATA_DIR / "agent_revisions.json"
_TURNS_FILE = _DATA_DIR / "chat_turns.json"


def _now() -> str:
    """Return a stable UTC timestamp string used by persisted records."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


class Project(BaseModel):
    """A container that groups related prompts.

    Attributes:
        id: Unique identifier.
        name: Human-readable project name.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str


class Prompt(BaseModel):
    """A prompt definition belonging to a project.

    Attributes:
        id: Unique identifier.
        project_id: Owning project identifier.
        name: Human-readable prompt name.
        description: Short description of the prompt's purpose.
        content: The prompt/system-instruction body.
        code: The Python skill code associated with the prompt.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    description: str = ""
    content: str = ""
    code: str = ""


class PromptVersion(BaseModel):
    """A timestamped snapshot of a prompt captured on save.

    Attributes:
        id: Unique identifier for the snapshot.
        prompt_id: The prompt this version belongs to.
        version: Timestamp string used as the version label.
        name: Prompt name at save time.
        description: Prompt description at save time.
        content: Prompt body at save time.
        code: Python skill code at save time.
        score: Best-practices score (0-100) at save time.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt_id: str
    version: str
    name: str
    description: str = ""
    content: str = ""
    code: str = ""
    score: int = 0


class PromptVersionRef(BaseModel):
    """A saved pointer to the exact prompt snapshot used in a run."""

    prompt_id: str
    prompt_name: str
    version_id: str
    version: str


class AgentRevision(BaseModel):
    """A reproducible agent configuration derived from one chat run."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    fingerprint: str
    name: str
    prompt_ids: list[str] = Field(default_factory=list)
    prompt_names: list[str] = Field(default_factory=list)
    prompt_versions: list[PromptVersionRef] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    pre_run_evaluation: dict = Field(default_factory=dict)
    evaluations: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    last_run_at: str | None = None
    turn_count: int = 0


class ChatTurn(BaseModel):
    """One persisted user/assistant exchange and its evaluations."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    revision_id: str
    created_at: str = Field(default_factory=_now)
    query: str
    answer: str
    prompt_ids: list[str] = Field(default_factory=list)
    prompt_names: list[str] = Field(default_factory=list)
    prompt_versions: list[PromptVersionRef] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    pre_run_evaluation: dict = Field(default_factory=dict)
    evaluations: list[dict] = Field(default_factory=list)


def _read(path: Path) -> list[dict]:
    """Read a JSON list from ``path``; return ``[]`` when missing or empty."""
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def _write(path: Path, items: list[dict]) -> None:
    """Atomically write ``items`` as JSON to ``path``."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(_DATA_DIR), suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(items, handle, indent=2)
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _score_of(payload: dict | None) -> int | None:
    """Return an integer score when a payload exposes one."""
    if not isinstance(payload, dict):
        return None
    try:
        score = payload.get("score")
        if score is None:
            return None
        return int(round(float(score)))
    except (TypeError, ValueError):
        return None


def _average_score(values: list[int | None]) -> int | None:
    """Return the rounded mean of the non-null scores in ``values``."""
    real = [v for v in values if v is not None]
    if not real:
        return None
    return int(round(sum(real) / len(real)))


def _normalize_finding(item: dict) -> dict:
    """Normalise one evaluation finding for stable storage and hashing."""
    return {
        "type": str(item.get("type", "")),
        "severity": str(item.get("severity", "")),
        "skills": sorted(str(s) for s in (item.get("skills") or []) if s),
        "detail": str(item.get("detail", "")),
    }


def normalize_evaluation(payload: dict) -> dict:
    """Return a stable, order-insensitive evaluation payload."""
    return {
        "key": str(payload.get("key", "")),
        "title": str(payload.get("title", "")),
        "score": _score_of(payload),
        "rating": str(payload.get("rating", "")),
        "color": str(payload.get("color", "")),
        "summary": str(payload.get("summary", "")),
        "findings": sorted(
            (
                _normalize_finding(item)
                for item in (payload.get("findings") or [])
                if isinstance(item, dict)
            ),
            key=lambda item: (
                item["type"],
                item["severity"],
                ",".join(item["skills"]),
                item["detail"],
            ),
        ),
    }


def _normalize_prompt_refs(
    prompt_versions: list[PromptVersionRef | dict],
) -> list[dict]:
    """Return prompt-version references in a stable order for hashing/storage."""
    refs = [
        ref.model_dump() if isinstance(ref, PromptVersionRef) else dict(ref)
        for ref in prompt_versions
    ]
    refs.sort(key=lambda item: (item["prompt_id"], item["version_id"]))
    return refs


def revision_fingerprint(
    prompt_ids: list[str],
    prompt_versions: list[PromptVersionRef | dict],
    tool_names: list[str],
    pre_run_evaluation: dict,
    evaluations: list[dict],
) -> str:
    """Hash the configuration and evaluation contract into one identity."""
    payload = {
        "prompt_ids": sorted(prompt_ids),
        "prompt_versions": _normalize_prompt_refs(prompt_versions),
        "tool_names": sorted(tool_names),
        "pre_run_evaluation": normalize_evaluation(pre_run_evaluation),
        "evaluations": sorted(
            (normalize_evaluation(item) for item in evaluations),
            key=lambda item: item["key"],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _default_revision_name(prompt_names: list[str]) -> str:
    """Return a readable default label for an auto-created revision."""
    if not prompt_names:
        return "Agent revision"
    head = ", ".join((name or "unnamed").strip() for name in prompt_names[:2])
    if len(prompt_names) > 2:
        head += f" +{len(prompt_names) - 2}"
    return f"{head} revision"


# --- Projects -------------------------------------------------------------


def list_projects() -> list[Project]:
    """Return all projects."""
    return [Project(**item) for item in _read(_PROJECTS_FILE)]


def create_project(name: str) -> Project:
    """Create and persist a new project."""
    project = Project(name=name)
    projects = _read(_PROJECTS_FILE)
    projects.append(project.model_dump())
    _write(_PROJECTS_FILE, projects)
    return project


def update_project(project_id: str, name: str) -> Project | None:
    """Update a project's name; return ``None`` when not found."""
    projects = _read(_PROJECTS_FILE)
    for item in projects:
        if item["id"] == project_id:
            item["name"] = name
            _write(_PROJECTS_FILE, projects)
            return Project(**item)
    return None


def delete_project(project_id: str) -> bool:
    """Delete a project and its prompts; return ``True`` when removed."""
    projects = _read(_PROJECTS_FILE)
    remaining = [item for item in projects if item["id"] != project_id]
    if len(remaining) == len(projects):
        return False
    _write(_PROJECTS_FILE, remaining)
    prompts = _read(_PROMPTS_FILE)
    removed_ids = {
        item["id"] for item in prompts if item["project_id"] == project_id
    }
    kept = [item for item in prompts if item["project_id"] != project_id]
    if len(kept) != len(prompts):
        _write(_PROMPTS_FILE, kept)
    if removed_ids:
        _delete_versions(removed_ids)
    return True


# --- Prompts --------------------------------------------------------------


def list_prompts(project_id: str | None = None) -> list[Prompt]:
    """Return all prompts, optionally filtered by ``project_id``."""
    prompts = [Prompt(**item) for item in _read(_PROMPTS_FILE)]
    if project_id is None:
        return prompts
    return [p for p in prompts if p.project_id == project_id]


def get_prompt(prompt_id: str) -> Prompt | None:
    """Return a single prompt by id; ``None`` when not found."""
    for item in _read(_PROMPTS_FILE):
        if item["id"] == prompt_id:
            return Prompt(**item)
    return None


def create_prompt(
    project_id: str,
    name: str,
    description: str = "",
    content: str = "",
    code: str = "",
) -> Prompt:
    """Create and persist a new prompt."""
    prompt = Prompt(
        project_id=project_id,
        name=name,
        description=description,
        content=content,
        code=code,
    )
    prompts = _read(_PROMPTS_FILE)
    prompts.append(prompt.model_dump())
    _write(_PROMPTS_FILE, prompts)
    return prompt


def update_prompt(
    prompt_id: str,
    name: str,
    description: str = "",
    content: str = "",
    code: str = "",
) -> Prompt | None:
    """Update a prompt; return ``None`` when not found."""
    prompts = _read(_PROMPTS_FILE)
    for item in prompts:
        if item["id"] == prompt_id:
            item["name"] = name
            item["description"] = description
            item["content"] = content
            item["code"] = code
            _write(_PROMPTS_FILE, prompts)
            return Prompt(**item)
    return None


def delete_prompt(prompt_id: str) -> bool:
    """Delete a prompt; return ``True`` when removed."""
    prompts = _read(_PROMPTS_FILE)
    remaining = [item for item in prompts if item["id"] != prompt_id]
    if len(remaining) == len(prompts):
        return False
    _write(_PROMPTS_FILE, remaining)
    _delete_versions({prompt_id})
    return True


# --- Versions -------------------------------------------------------------


def add_version(prompt: Prompt, score: int) -> PromptVersion:
    """Append a timestamped snapshot of ``prompt`` and return it."""
    version = PromptVersion(
        prompt_id=prompt.id,
        version=datetime.datetime.now().isoformat(timespec="seconds"),
        name=prompt.name,
        description=prompt.description,
        content=prompt.content,
        code=prompt.code,
        score=score,
    )
    items = _read(_VERSIONS_FILE)
    items.append(version.model_dump())
    _write(_VERSIONS_FILE, items)
    return version


def find_matching_version(prompt: Prompt) -> PromptVersion | None:
    """Return the newest saved snapshot whose content matches ``prompt``."""
    for item in reversed(_read(_VERSIONS_FILE)):
        if item["prompt_id"] != prompt.id:
            continue
        if (
            item.get("name", "") == prompt.name
            and item.get("description", "") == prompt.description
            and item.get("content", "") == prompt.content
            and item.get("code", "") == prompt.code
        ):
            return PromptVersion(**item)
    return None


def ensure_prompt_version(prompt: Prompt, score: int) -> PromptVersion:
    """Return a saved snapshot for ``prompt``, creating one when needed."""
    version = find_matching_version(prompt)
    return version if version is not None else add_version(prompt, score)


def list_versions(prompt_id: str) -> list[PromptVersion]:
    """Return snapshots for a prompt, newest first."""
    items = [
        PromptVersion(**i)
        for i in _read(_VERSIONS_FILE)
        if i["prompt_id"] == prompt_id
    ]
    return list(reversed(items))


def delete_version(prompt_id: str, version_id: str) -> bool:
    """Delete a single snapshot of ``prompt_id``; return ``True`` when removed."""
    items = _read(_VERSIONS_FILE)
    kept = [
        i
        for i in items
        if not (i["id"] == version_id and i["prompt_id"] == prompt_id)
    ]
    if len(kept) == len(items):
        return False
    _write(_VERSIONS_FILE, kept)
    return True


def list_agent_revisions() -> list[AgentRevision]:
    """Return all saved agent revisions, newest run first."""
    revisions = [AgentRevision(**item) for item in _read(_REVISIONS_FILE)]
    return sorted(
        revisions,
        key=lambda item: (item.last_run_at or item.updated_at, item.created_at),
        reverse=True,
    )


def get_agent_revision(revision_id: str) -> AgentRevision | None:
    """Return one saved agent revision by id."""
    for item in _read(_REVISIONS_FILE):
        if item["id"] == revision_id:
            return AgentRevision(**item)
    return None


def get_agent_revision_by_fingerprint(fingerprint: str) -> AgentRevision | None:
    """Return the saved revision for ``fingerprint`` when present."""
    for item in _read(_REVISIONS_FILE):
        if item.get("fingerprint") == fingerprint:
            return AgentRevision(**item)
    return None


def upsert_agent_revision(
    prompt_ids: list[str],
    prompt_names: list[str],
    prompt_versions: list[PromptVersionRef | dict],
    tool_names: list[str],
    pre_run_evaluation: dict,
    evaluations: list[dict],
    created_at: str | None = None,
) -> AgentRevision:
    """Find or create the deterministic revision for one completed run."""
    normalized_pre = normalize_evaluation(pre_run_evaluation)
    normalized_evals = [
        normalize_evaluation(item)
        for item in sorted(evaluations, key=lambda item: item.get("key", ""))
    ]
    refs = [PromptVersionRef(**ref) for ref in _normalize_prompt_refs(prompt_versions)]
    fingerprint = revision_fingerprint(
        prompt_ids,
        refs,
        tool_names,
        normalized_pre,
        normalized_evals,
    )

    revisions = _read(_REVISIONS_FILE)
    for item in revisions:
        if item.get("fingerprint") == fingerprint:
            item["updated_at"] = created_at or _now()
            _write(_REVISIONS_FILE, revisions)
            return AgentRevision(**item)

    revision = AgentRevision(
        fingerprint=fingerprint,
        name=_default_revision_name(prompt_names),
        prompt_ids=prompt_ids,
        prompt_names=prompt_names,
        prompt_versions=refs,
        tool_names=sorted(tool_names),
        pre_run_evaluation=normalized_pre,
        evaluations=normalized_evals,
        created_at=created_at or _now(),
        updated_at=created_at or _now(),
    )
    revisions.append(revision.model_dump())
    _write(_REVISIONS_FILE, revisions)
    return revision


def rename_agent_revision(revision_id: str, name: str) -> AgentRevision | None:
    """Rename a saved revision; return ``None`` when not found."""
    revisions = _read(_REVISIONS_FILE)
    for item in revisions:
        if item["id"] == revision_id:
            item["name"] = name
            item["updated_at"] = _now()
            _write(_REVISIONS_FILE, revisions)
            return AgentRevision(**item)
    return None


def list_chat_turns(revision_id: str | None = None) -> list[ChatTurn]:
    """Return persisted turns, optionally filtered by revision."""
    turns = [ChatTurn(**item) for item in _read(_TURNS_FILE)]
    if revision_id is not None:
        turns = [turn for turn in turns if turn.revision_id == revision_id]
    return sorted(turns, key=lambda item: item.created_at, reverse=True)


def get_chat_turn(turn_id: str) -> ChatTurn | None:
    """Return one persisted turn by id."""
    for item in _read(_TURNS_FILE):
        if item["id"] == turn_id:
            return ChatTurn(**item)
    return None


def add_chat_turn(
    revision_id: str,
    query: str,
    answer: str,
    prompt_ids: list[str],
    prompt_names: list[str],
    prompt_versions: list[PromptVersionRef | dict],
    tool_names: list[str],
    tool_calls: list[dict],
    pre_run_evaluation: dict,
    evaluations: list[dict],
    created_at: str | None = None,
) -> ChatTurn:
    """Persist one evaluated user/assistant exchange."""
    at = created_at or _now()
    turn = ChatTurn(
        revision_id=revision_id,
        created_at=at,
        query=query,
        answer=answer,
        prompt_ids=prompt_ids,
        prompt_names=prompt_names,
        prompt_versions=[PromptVersionRef(**ref) for ref in prompt_versions],
        tool_names=sorted(tool_names),
        tool_calls=tool_calls,
        pre_run_evaluation=normalize_evaluation(pre_run_evaluation),
        evaluations=[
            normalize_evaluation(item)
            for item in sorted(evaluations, key=lambda item: item.get("key", ""))
        ],
    )
    items = _read(_TURNS_FILE)
    items.append(turn.model_dump())
    _write(_TURNS_FILE, items)

    revisions = _read(_REVISIONS_FILE)
    for item in revisions:
        if item["id"] == revision_id:
            item["turn_count"] = int(item.get("turn_count", 0)) + 1
            item["last_run_at"] = at
            item["updated_at"] = at
            _write(_REVISIONS_FILE, revisions)
            break
    return turn


def save_chat_turn(
    query: str,
    answer: str,
    prompt_ids: list[str],
    prompt_names: list[str],
    prompt_versions: list[PromptVersionRef | dict],
    tool_names: list[str],
    tool_calls: list[dict],
    pre_run_evaluation: dict,
    evaluations: list[dict],
    created_at: str | None = None,
) -> tuple[AgentRevision, ChatTurn]:
    """Persist one completed run and return the revision and turn."""
    at = created_at or _now()
    revision = upsert_agent_revision(
        prompt_ids=prompt_ids,
        prompt_names=prompt_names,
        prompt_versions=prompt_versions,
        tool_names=tool_names,
        pre_run_evaluation=pre_run_evaluation,
        evaluations=evaluations,
        created_at=at,
    )
    turn = add_chat_turn(
        revision_id=revision.id,
        query=query,
        answer=answer,
        prompt_ids=prompt_ids,
        prompt_names=prompt_names,
        prompt_versions=prompt_versions,
        tool_names=tool_names,
        tool_calls=tool_calls,
        pre_run_evaluation=pre_run_evaluation,
        evaluations=evaluations,
        created_at=at,
    )
    return get_agent_revision(revision.id) or revision, turn


def revision_summary(revision: AgentRevision) -> dict:
    """Return a revision with aggregated turn metrics for browsing."""
    turns = list_chat_turns(revision.id)

    def eval_score(turn: ChatTurn, key: str) -> int | None:
        for item in turn.evaluations:
            if item.get("key") == key:
                return _score_of(item)
        return None

    return {
        **revision.model_dump(),
        "scores": {
            "pre_run": _average_score(
                [_score_of(turn.pre_run_evaluation) for turn in turns]
            ),
            "skill": _average_score(
                [eval_score(turn, "skill") for turn in turns]
            ),
            "task": _average_score([eval_score(turn, "task") for turn in turns]),
            "tools": _average_score(
                [eval_score(turn, "tools") for turn in turns]
            ),
        },
    }


def compare_chat_turns(baseline_id: str, candidate_id: str) -> dict | None:
    """Return two stored turns and score deltas for the compare view."""
    baseline = get_chat_turn(baseline_id)
    candidate = get_chat_turn(candidate_id)
    if baseline is None or candidate is None:
        return None

    def by_key(turn: ChatTurn) -> dict[str, dict]:
        return {
            item.get("key", ""): item
            for item in turn.evaluations
            if isinstance(item, dict)
        }

    base_evals = by_key(baseline)
    cand_evals = by_key(candidate)
    keys = sorted(set(base_evals) | set(cand_evals))
    eval_deltas = []
    for key in keys:
        left = base_evals.get(key, {})
        right = cand_evals.get(key, {})
        left_score = _score_of(left)
        right_score = _score_of(right)
        eval_deltas.append(
            {
                "key": key,
                "title": right.get("title") or left.get("title") or key,
                "baseline_score": left_score,
                "candidate_score": right_score,
                "delta": (
                    None
                    if left_score is None or right_score is None
                    else right_score - left_score
                ),
            }
        )

    base_pre = _score_of(baseline.pre_run_evaluation)
    cand_pre = _score_of(candidate.pre_run_evaluation)
    return {
        "baseline": baseline.model_dump(),
        "candidate": candidate.model_dump(),
        "delta": {
            "pre_run_score": {
                "baseline": base_pre,
                "candidate": cand_pre,
                "delta": (
                    None
                    if base_pre is None or cand_pre is None
                    else cand_pre - base_pre
                ),
            },
            "tool_calls": {
                "baseline": len(baseline.tool_calls),
                "candidate": len(candidate.tool_calls),
                "delta": len(candidate.tool_calls) - len(baseline.tool_calls),
            },
            "evaluations": eval_deltas,
        },
    }


def _delete_versions(prompt_ids: set[str]) -> None:
    """Remove all snapshots belonging to ``prompt_ids``."""
    items = _read(_VERSIONS_FILE)
    kept = [i for i in items if i["prompt_id"] not in prompt_ids]
    if len(kept) != len(items):
        _write(_VERSIONS_FILE, kept)
