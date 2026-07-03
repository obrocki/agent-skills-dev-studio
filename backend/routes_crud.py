"""CRUD API routes for projects and prompts.

The router is mounted under ``/api`` by ``backend.main``; paths here are
relative (``/projects``, ``/prompts``) to avoid a duplicated prefix.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import store, validate

router = APIRouter()


class ProjectIn(BaseModel):
    """Request body for creating or updating a project."""

    name: str


class PromptIn(BaseModel):
    """Request body for creating or updating a prompt."""

    project_id: str
    name: str
    description: str = ""
    content: str = ""
    code: str = ""


class PromptSaveResult(BaseModel):
    """Response for a prompt save: the prompt, its validation, and the snapshot."""

    prompt: store.Prompt
    validation: dict
    version: store.PromptVersion


class PromptDraft(BaseModel):
    """Request body for validating an unsaved draft."""

    name: str = ""
    description: str = ""
    content: str = ""


@router.get("/projects", response_model=list[store.Project])
def get_projects() -> list[store.Project]:
    return store.list_projects()


@router.post("/projects", response_model=store.Project, status_code=201)
def create_project(body: ProjectIn) -> store.Project:
    return store.create_project(body.name)


@router.put("/projects/{project_id}", response_model=store.Project)
def update_project(project_id: str, body: ProjectIn) -> store.Project:
    project = store.update_project(project_id, body.name)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    if not store.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@router.get(
    "/projects/{project_id}/prompts", response_model=list[store.Prompt]
)
def get_project_prompts(project_id: str) -> list[store.Prompt]:
    return store.list_prompts(project_id)


@router.post("/prompts", response_model=store.Prompt, status_code=201)
def create_prompt(body: PromptIn) -> store.Prompt:
    return store.create_prompt(
        body.project_id, body.name, body.description, body.content, body.code
    )


@router.get("/prompts/{prompt_id}", response_model=store.Prompt)
def get_prompt(prompt_id: str) -> store.Prompt:
    prompt = store.get_prompt(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.put("/prompts/{prompt_id}", response_model=PromptSaveResult)
def update_prompt(prompt_id: str, body: PromptIn) -> PromptSaveResult:
    prompt = store.update_prompt(
        prompt_id, body.name, body.description, body.content, body.code
    )
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    result = validate.validate_skill(
        prompt.name, prompt.description, prompt.content
    )
    version = store.add_version(prompt, result["score"])
    return PromptSaveResult(prompt=prompt, validation=result, version=version)


@router.post("/prompts/validate")
def validate_draft(body: PromptDraft) -> dict:
    """Validate an unsaved draft so the editor can show a live rating."""
    return validate.validate_skill(body.name, body.description, body.content)


@router.get("/prompts/{prompt_id}/validate")
def validate_prompt(prompt_id: str) -> dict:
    prompt = store.get_prompt(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return validate.validate_skill(
        prompt.name, prompt.description, prompt.content
    )


@router.get(
    "/prompts/{prompt_id}/versions", response_model=list[store.PromptVersion]
)
def get_versions(prompt_id: str) -> list[store.PromptVersion]:
    # Recompute each snapshot's score against the current rules so history stays consistent.
    return [
        v.model_copy(
            update={
                "score": validate.validate_skill(
                    v.name, v.description, v.content
                )["score"]
            }
        )
        for v in store.list_versions(prompt_id)
    ]


@router.delete("/prompts/{prompt_id}/versions/{version_id}", status_code=204)
def delete_version(prompt_id: str, version_id: str) -> None:
    if not store.delete_version(prompt_id, version_id):
        raise HTTPException(status_code=404, detail="Version not found")


@router.delete("/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: str) -> None:
    if not store.delete_prompt(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
