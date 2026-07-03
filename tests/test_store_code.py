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
