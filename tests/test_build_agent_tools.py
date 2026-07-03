"""Unit tests for the tool-selection contract used by ``build_agent``.

Approach: we assert the same selection logic that ``chat.build_agent``
uses internally (``_to_skills`` -> per-code ``_make_skill_tool`` named by
``_tool_name``) rather than constructing a live framework ``Agent``.
Building a real ``Agent`` requires a valid Azure OpenAI client and Entra
ID credentials, which are unavailable (and undesirable) in a unit test.
The helper below mirrors ``build_agent`` line-for-line so the contract is
exercised without any Azure or network access.
"""

from backend import chat, store


def _select_tool_names(prompts, time_zone=None, locale=None):
    """Replicate the tool selection performed inside ``build_agent``."""
    prompt_list = prompts if isinstance(prompts, list) else [prompts]
    skills = chat._to_skills(prompt_list)
    ctx = {"time_zone": time_zone, "locale": locale}
    tools = [
        chat._make_skill_tool(
            p.code, s.frontmatter.name, s.frontmatter.description, ctx
        )
        for p, s in zip(prompt_list, skills)
        if (getattr(p, "code", "") or "").strip()
    ]
    return [tool.__name__ for tool in tools]


def _prompt(name, code=""):
    """Build a lightweight stored prompt for the test."""
    return store.Prompt(
        project_id="proj",
        name=name,
        description=f"{name} description",
        content=f"{name} content",
        code=code,
    )


def test_prompt_with_code_yields_one_run_tool():
    # Arrange
    prompts = [_prompt("localized-time", code="print('hi')")]

    # Act
    names = _select_tool_names(prompts)

    # Assert
    assert len(names) == 1
    assert names[0].startswith("run_")


def test_prompt_without_code_yields_no_tools():
    # Arrange
    prompts = [_prompt("no-code-skill", code="")]

    # Act
    names = _select_tool_names(prompts)

    # Assert
    assert names == []


def test_duplicate_slugged_names_yield_distinct_tool_names():
    # Arrange: two names that slug to the same skill name.
    prompts = [
        _prompt("Localized Time", code="print('a')"),
        _prompt("localized-time", code="print('b')"),
    ]

    # Act
    names = _select_tool_names(prompts)

    # Assert
    assert len(names) == 2
    assert len(set(names)) == 2


def test_tool_names_never_collide_with_builtin_tools():
    # Arrange
    prompts = [
        _prompt("load-skill", code="print('a')"),
        _prompt("read-skill-resource", code="print('b')"),
    ]

    # Act
    names = _select_tool_names(prompts)

    # Assert
    assert "load_skill" not in names
    assert "read_skill_resource" not in names
