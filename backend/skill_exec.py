"""Sandboxed execution of a skill's self-contained Python.

Runs authored code in an isolated child interpreter (``python -I``)
with a hard timeout, a scrubbed environment, and (on POSIX) CPU and
process-count resource limits. Inputs are delivered as a JSON
document on stdin; the result is whatever the code prints to stdout.
This is intended for a local, single-user dev studio: it is deliberate
code execution, not a security boundary for hostile input.
"""

import contextlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import resource  # POSIX only
except ImportError:  # pragma: no cover - Windows dev
    resource = None

logger = logging.getLogger("agent_skill_portal.skill_exec")

_CPU_SECONDS = 2
_MAX_OUTPUT_CHARS = 20000


def _without_debugger_injection() -> contextlib.AbstractContextManager:
    """Stop an attached debugger from hijacking the sandbox subprocess.

    When the server runs under the VS Code Python debugger, ``pydevd``
    monkey-patches ``subprocess`` to rewrite every child ``python`` launch
    so it boots the debugger and connects back to the IDE. That rewrite
    defeats this sandbox: the child is started with a scrubbed environment
    and ``-I`` isolation, so the injected bootstrap cannot load and instead
    hangs or crashes before the skill's code ever runs. ``pydevd`` exposes a
    public context manager to opt a single call out of that patching; when
    no debugger is attached (for example in production) ``pydevd`` is not
    importable and this becomes a no-op.
    """
    try:
        from pydevd import skip_subprocess_arg_patch
    except Exception:  # pragma: no cover - debugger not attached
        return contextlib.nullcontext()
    return skip_subprocess_arg_patch()


def _apply_limits() -> None:
    """Best-effort POSIX resource limits for the child process.

    Only limits that are safe when forking from a large parent are
    applied. ``RLIMIT_AS`` is deliberately not set: it caps the virtual
    address space, which the child inherits from the (potentially large)
    server process, so shrinking it below the already-mapped size would
    stop the child from launching. Runaway code is bounded instead by
    ``RLIMIT_CPU`` and the wall-clock timeout.
    """
    if resource is None:
        return
    for limit, value in (
        (resource.RLIMIT_CPU, (_CPU_SECONDS, _CPU_SECONDS)),
        (resource.RLIMIT_NPROC, (0, 0)),
    ):
        try:
            resource.setrlimit(limit, value)
        except (ValueError, OSError):  # not always permitted; ignore
            pass


def run(code: str, inputs: dict, timeout: float = 5.0) -> str:
    """Execute ``code`` in an isolated subprocess, returning stdout.

    Args:
        code: The skill's self-contained Python source.
        inputs: JSON-serialisable data delivered to the code on stdin.
        timeout: Wall-clock seconds before the child is killed.

    Returns:
        The child's trimmed stdout on success, or a ``[skill error]
        ...`` string on failure.
    """
    if not (code or "").strip():
        return "[skill error] this skill has no code to run"
    tmp = Path(tempfile.mkstemp(prefix="skill_", suffix=".py")[1])
    try:
        tmp.write_text(code, encoding="utf-8")
        with _without_debugger_injection():
            proc = subprocess.run(
                [sys.executable, "-I", str(tmp)],
                input=json.dumps(inputs),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={"PATH": os.environ.get("PATH", "")},
                preexec_fn=(_apply_limits if resource is not None else None),
            )
    except subprocess.TimeoutExpired:
        return "[skill error] execution timed out"
    except Exception:  # pragma: no cover - defensive
        logger.exception("skill execution failed to launch")
        return "[skill error] could not start execution"
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:_MAX_OUTPUT_CHARS]
        return f"[skill error] {stderr}"
    return (proc.stdout or "").strip()[:_MAX_OUTPUT_CHARS]
