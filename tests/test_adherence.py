"""Offline unit tests for the SDK-based adherence module.

These tests exercise only the pure, offline behaviour of
``backend.adherence`` and the ``chat.run_tool_*`` helpers: score mappers,
the eval-frame contract builders, the no-tool-call short-circuit, and
``run_all`` orchestration. No Azure or network access is involved; the two
paths that would construct an Azure AI Evaluation SDK judge are either
short-circuited (empty ``calls``) or replaced with async fakes via
``monkeypatch``. ``pytest-asyncio`` is not installed, so coroutines are
driven with ``asyncio.run(...)``.
"""

import asyncio

from backend import adherence, chat, store


def _prompt(name, code=""):
    """Build a lightweight stored prompt for the test."""
    return store.Prompt(
        project_id="proj",
        name=name,
        description=f"{name} description",
        content=f"{name} content",
        code=code,
    )


# --- chat.run_tool_names / run_tool_definitions -----------------------------


def test_run_tool_names_only_code_bearing():
    # Arrange: one prompt with code, one without.
    prompts = [
        _prompt("localized-time", code="print('hi')"),
        _prompt("no-code-skill", code=""),
    ]

    # Act
    names = chat.run_tool_names(prompts)

    # Assert: only the code-bearing prompt produces a run_* entry.
    assert len(names) == 1
    assert names[0].startswith("run_")


def test_run_tool_definitions_shape_and_names():
    # Arrange
    prompts = [
        _prompt("localized-time", code="print('hi')"),
        _prompt("no-code-skill", code=""),
    ]

    # Act
    defs = chat.run_tool_definitions(prompts)
    names = chat.run_tool_names(prompts)

    # Assert: one entry, matching run_tool_names, with the expected schema.
    assert len(defs) == 1
    entry = defs[0]
    assert set(entry) >= {"name", "description", "parameters"}
    assert entry["name"] == names[0]
    assert isinstance(entry["description"], str)
    user_input = entry["parameters"]["properties"]["user_input"]
    assert user_input["type"] == "string"


# --- score / rating / contract mappers --------------------------------------


def test_scale_1_5_maps_endpoints():
    # Assert: (score - 1) / 4 * 100 lands 1->0, 3->50, 5->100.
    assert adherence._scale_1_5(1) == 0
    assert adherence._scale_1_5(3) == 50
    assert adherence._scale_1_5(5) == 100


def test_rating_adherence_bands():
    # Assert: band boundaries and the None -> Unavailable case.
    assert adherence._rating_adherence(80) == "Adherent"
    assert adherence._rating_adherence(100) == "Adherent"
    assert adherence._rating_adherence(50) == "Partial"
    assert adherence._rating_adherence(79) == "Partial"
    assert adherence._rating_adherence(49) == "Off-track"
    assert adherence._rating_adherence(0) == "Off-track"
    assert adherence._rating_adherence(None) == "Unavailable"


def test_contract_findings():
    # Act: a perfect score yields no findings; a zero score yields one.
    good = adherence._contract(100, "all good", "adherence")
    bad = adherence._contract(0, "nothing ran", "tool-call")

    # Assert
    assert good["score"] == 100
    assert good["findings"] == []

    assert bad["score"] == 0
    assert len(bad["findings"]) == 1
    finding = bad["findings"][0]
    assert finding["type"] == "tool-call"
    assert finding["severity"] == "high"


def test_unavailable_contract():
    # Act
    contract = adherence._unavailable_contract("could not run")

    # Assert
    assert contract["score"] is None
    assert contract["rating"] == "Unavailable"
    assert contract["findings"] == []


def test_as_dict_coercions():
    # Assert: mappings pass through, JSON strings parse, empties -> {}.
    assert adherence._as_dict('{"a":1}') == {"a": 1}
    assert adherence._as_dict({"b": 2}) == {"b": 2}
    assert adherence._as_dict("") == {}
    assert adherence._as_dict(None) == {}


# --- _response_with_tools surfacing -----------------------------------------


def test_response_with_tools_surfaces_calls_and_results():
    # Arrange: one captured tool call with parsed arguments and a result.
    calls = {
        "call-1": {
            "name": "run_localized_time",
            "arguments": '{"user_input": "what time"}',
            "result": "Friday, 3 July 2026",
        }
    }

    # Act
    response = adherence._response_with_tools("Friday, 3 July 2026", calls)

    # Assert: an agent message list with the tool call, its result, and text.
    assert isinstance(response, list)
    assert response[0]["role"] == "assistant"
    call_item = response[0]["content"][0]
    assert call_item["type"] == "tool_call"
    assert call_item["tool_call_id"] == "call-1"
    assert call_item["name"] == "run_localized_time"
    assert call_item["arguments"] == {"user_input": "what time"}
    tool_msg = response[1]
    assert tool_msg["role"] == "tool"
    assert tool_msg["content"][0]["tool_result"] == "Friday, 3 July 2026"
    assert response[-1]["content"][0]["text"] == "Friday, 3 July 2026"


def test_response_with_tools_plain_string_without_calls():
    # Assert: no captured tool call returns the answer unchanged.
    assert adherence._response_with_tools("hi", {}) == "hi"
    # A call missing a name is ignored (kept off the transcript).
    assert adherence._response_with_tools("hi", {"c": {"name": None}}) == "hi"


# --- evaluate_tool_calls offline no-call path --------------------------------


def test_evaluate_tool_calls_no_call_offline():
    # Arrange: no tool calls were made; the SDK evaluator must not be built.
    tool_defs = [{"name": "run_x", "description": "d", "parameters": {}}]

    # Act
    result = asyncio.run(adherence.evaluate_tool_calls("q", {}, tool_defs))

    # Assert: a score-0 tool-call contract with exactly one finding.
    assert result["score"] == 0
    assert result["rating"] == "Off-track"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["type"] == "tool-call"


# --- run_all ordering + tools-card gating ------------------------------------


def _install_async_fakes(monkeypatch):
    """Replace the three SDK-backed judges with fixed-contract async fakes."""

    async def fake_skill(query, response, context, tool_definitions=None):
        return {
            "score": 90,
            "rating": "Adherent",
            "color": "c",
            "summary": "skill",
            "findings": [],
        }

    async def fake_task(query, response, tool_definitions=None):
        return {
            "score": 70,
            "rating": "Partial",
            "color": "c",
            "summary": "task",
            "findings": [],
        }

    async def fake_tools(query, calls, tool_definitions):
        return {
            "score": 50,
            "rating": "Partial",
            "color": "c",
            "summary": "tools",
            "findings": [],
        }

    monkeypatch.setattr(adherence, "skill_adherence", fake_skill)
    monkeypatch.setattr(adherence, "task_adherence", fake_task)
    monkeypatch.setattr(adherence, "evaluate_tool_calls", fake_tools)


def test_run_all_orders_frames_with_tools(monkeypatch):
    # Arrange: fakes for every judge and a code-bearing prompt.
    _install_async_fakes(monkeypatch)
    prompts = [_prompt("localized-time", code="print('hi')")]

    # Act
    frames = asyncio.run(adherence.run_all("q", "a", prompts, {}))

    # Assert: three ordered frames, each carrying a title.
    assert [f["key"] for f in frames] == ["skill", "task", "tools"]
    assert all(f["title"] for f in frames)


def test_run_all_omits_tools_without_code(monkeypatch):
    # Arrange: only no-code prompts, so the tools card is gated off.
    _install_async_fakes(monkeypatch)
    prompts = [_prompt("no-code-skill", code="")]

    # Act
    frames = asyncio.run(adherence.run_all("q", "a", prompts, {}))

    # Assert
    assert [f["key"] for f in frames] == ["skill", "task"]
