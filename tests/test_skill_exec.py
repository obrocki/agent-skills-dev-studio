"""Unit tests for the sandboxed skill executor.

These tests run authored Python in an isolated child interpreter. They
require no Azure or network access.
"""

from backend import skill_exec


def test_run_returns_stdin_value_verbatim():
    # Arrange: code that reads a JSON value from stdin and prints it.
    code = "import json, sys\nprint(json.load(sys.stdin)['message'])\n"

    # Act
    result = skill_exec.run(code, {"message": "hello world"})

    # Assert
    assert result == "hello world"


def test_run_returns_timeout_error_on_infinite_loop():
    # Arrange: code that never terminates on its own.
    code = "while True:\n    pass\n"

    # Act: use a short timeout so the child is killed quickly.
    result = skill_exec.run(code, {}, timeout=0.5)

    # Assert: a string is returned (not an exception raised).
    assert isinstance(result, str)
    assert result.startswith("[skill error]")
    assert "timed out" in result


def test_run_returns_error_string_on_non_zero_exit():
    # Arrange: code that raises, producing a non-zero exit code.
    code = "raise RuntimeError('boom')\n"

    # Act
    result = skill_exec.run(code, {})

    # Assert
    assert isinstance(result, str)
    assert result.startswith("[skill error]")


def test_run_returns_no_code_error_for_empty_code():
    # Arrange: whitespace-only code has nothing to execute.
    # Act
    result = skill_exec.run("   \n\t ", {})

    # Assert
    assert result == "[skill error] this skill has no code to run"
