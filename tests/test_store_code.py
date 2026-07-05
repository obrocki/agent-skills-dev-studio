"""Unit tests for the ``code`` field roundtrip in the store.

The store module writes to JSON files under ``backend/data``. Every test
here redirects those paths to a temporary directory via ``monkeypatch``
so the real data files are never touched.
"""

import pytest

from backend import store


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    """Redirect the store's data-file paths into ``tmp_path``."""
    monkeypatch.setattr(store, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "_PROJECTS_FILE", tmp_path / "projects.json")
    monkeypatch.setattr(store, "_PROMPTS_FILE", tmp_path / "prompts.json")
    monkeypatch.setattr(
        store, "_VERSIONS_FILE", tmp_path / "prompt_versions.json"
    )
    monkeypatch.setattr(
        store, "_REVISIONS_FILE", tmp_path / "agent_revisions.json"
    )
    monkeypatch.setattr(store, "_TURNS_FILE", tmp_path / "chat_turns.json")
    return tmp_path


def test_create_update_get_roundtrips_code(isolated_store):
    # Arrange
    project = store.create_project("Demo")
    created = store.create_prompt(project.id, "example", code="print('v1')")

    # Act
    store.update_prompt(created.id, "example", code="print('v2')")
    fetched = store.get_prompt(created.id)

    # Assert
    assert fetched is not None
    assert fetched.code == "print('v2')"


def test_add_version_snapshot_includes_code(isolated_store):
    # Arrange
    project = store.create_project("Demo")
    prompt = store.create_prompt(
        project.id, "example", code="print('snapshot')"
    )

    # Act
    version = store.add_version(prompt, score=42)

    # Assert
    assert version.code == "print('snapshot')"


def test_prompt_without_code_key_defaults_to_empty():
    # Arrange: a stored dict that predates the ``code`` field.
    data = {
        "id": "abc",
        "project_id": "proj",
        "name": "legacy",
        "description": "",
        "content": "",
    }

    # Act
    prompt = store.Prompt(**data)

    # Assert
    assert prompt.code == ""


def test_ensure_prompt_version_reuses_matching_snapshot(isolated_store):
    # Arrange
    project = store.create_project("Demo")
    prompt = store.create_prompt(project.id, "example", content="body")

    # Act
    first = store.ensure_prompt_version(prompt, score=12)
    second = store.ensure_prompt_version(prompt, score=99)

    # Assert
    assert first.id == second.id
    assert len(store.list_versions(prompt.id)) == 1


def test_save_chat_turn_reuses_revision_by_fingerprint(isolated_store):
    # Arrange
    project = store.create_project("Demo")
    prompt = store.create_prompt(project.id, "example", content="body")
    version = store.ensure_prompt_version(prompt, score=75)
    pre = {
        "score": 88,
        "rating": "Compatible",
        "color": "green",
        "summary": "ok",
        "findings": [],
    }
    evals = [
        {
            "key": "skill",
            "title": "Skill adherence",
            "score": 91,
            "rating": "Adherent",
            "color": "green",
            "summary": "good",
            "findings": [],
        }
    ]
    refs = [
        {
            "prompt_id": prompt.id,
            "prompt_name": prompt.name,
            "version_id": version.id,
            "version": version.version,
        }
    ]

    # Act
    revision1, turn1 = store.save_chat_turn(
        query="q1",
        answer="a1",
        prompt_ids=[prompt.id],
        prompt_names=[prompt.name],
        prompt_versions=refs,
        tool_names=["run_example"],
        tool_calls=[],
        pre_run_evaluation=pre,
        evaluations=evals,
    )
    revision2, turn2 = store.save_chat_turn(
        query="q2",
        answer="a2",
        prompt_ids=[prompt.id],
        prompt_names=[prompt.name],
        prompt_versions=refs,
        tool_names=["run_example"],
        tool_calls=[],
        pre_run_evaluation=pre,
        evaluations=evals,
    )

    # Assert
    assert revision1.id == revision2.id
    assert turn1.revision_id == revision1.id
    assert turn2.revision_id == revision1.id
    saved = store.get_agent_revision(revision1.id)
    assert saved is not None
    assert saved.turn_count == 2


def test_compare_chat_turns_returns_score_deltas(isolated_store):
    # Arrange
    project = store.create_project("Demo")
    prompt = store.create_prompt(project.id, "example", content="body")
    version = store.ensure_prompt_version(prompt, score=50)
    refs = [
        {
            "prompt_id": prompt.id,
            "prompt_name": prompt.name,
            "version_id": version.id,
            "version": version.version,
        }
    ]
    revision, base = store.save_chat_turn(
        query="q1",
        answer="a1",
        prompt_ids=[prompt.id],
        prompt_names=[prompt.name],
        prompt_versions=refs,
        tool_names=[],
        tool_calls=[],
        pre_run_evaluation={
            "score": 60,
            "rating": "Minor issues",
            "color": "yellow",
            "summary": "base",
            "findings": [],
        },
        evaluations=[
            {
                "key": "task",
                "title": "Task adherence",
                "score": 55,
                "rating": "Partial",
                "color": "yellow",
                "summary": "base task",
                "findings": [],
            }
        ],
    )
    _, candidate = store.save_chat_turn(
        query="q2",
        answer="a2",
        prompt_ids=[prompt.id],
        prompt_names=[prompt.name],
        prompt_versions=refs,
        tool_names=[],
        tool_calls=[{"call_id": "1", "name": "run_example"}],
        pre_run_evaluation={
            "score": 80,
            "rating": "Compatible",
            "color": "green",
            "summary": "candidate",
            "findings": [],
        },
        evaluations=[
            {
                "key": "task",
                "title": "Task adherence",
                "score": 75,
                "rating": "Partial",
                "color": "green",
                "summary": "candidate task",
                "findings": [],
            }
        ],
    )

    # Act
    result = store.compare_chat_turns(base.id, candidate.id)

    # Assert
    assert revision.id == base.revision_id
    assert result is not None
    assert result["delta"]["pre_run_score"]["delta"] == 20
    assert result["delta"]["tool_calls"]["delta"] == 1
    assert result["delta"]["evaluations"][0]["delta"] == 20
