"""JSON-backed storage for projects and prompts.

Persists data to ``backend/data/projects.json`` and ``backend/data/prompts.json``
using atomic writes. A project has a one-to-many relationship with prompts;
deleting a project cascades to its prompts.
"""

import datetime
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
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    description: str = ""
    content: str = ""


class PromptVersion(BaseModel):
    """A timestamped snapshot of a prompt captured on save.

    Attributes:
        id: Unique identifier for the snapshot.
        prompt_id: The prompt this version belongs to.
        version: Timestamp string used as the version label.
        name: Prompt name at save time.
        description: Prompt description at save time.
        content: Prompt body at save time.
        score: Best-practices score (0-100) at save time.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt_id: str
    version: str
    name: str
    description: str = ""
    content: str = ""
    score: int = 0


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
    project_id: str, name: str, description: str = "", content: str = ""
) -> Prompt:
    """Create and persist a new prompt."""
    prompt = Prompt(
        project_id=project_id,
        name=name,
        description=description,
        content=content,
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
) -> Prompt | None:
    """Update a prompt; return ``None`` when not found."""
    prompts = _read(_PROMPTS_FILE)
    for item in prompts:
        if item["id"] == prompt_id:
            item["name"] = name
            item["description"] = description
            item["content"] = content
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
        score=score,
    )
    items = _read(_VERSIONS_FILE)
    items.append(version.model_dump())
    _write(_VERSIONS_FILE, items)
    return version


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


def _delete_versions(prompt_ids: set[str]) -> None:
    """Remove all snapshots belonging to ``prompt_ids``."""
    items = _read(_VERSIONS_FILE)
    kept = [i for i in items if i["prompt_id"] not in prompt_ids]
    if len(kept) != len(items):
        _write(_VERSIONS_FILE, kept)
