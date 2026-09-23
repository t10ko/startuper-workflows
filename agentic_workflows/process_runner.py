import contextlib
import os
import shutil
import signal
import subprocess
from typing import IO, Any, cast

from agentic_workflows.exceptions import EnvironmentFaultError

# What a caller may pass for a child stream: an fd, a text or binary stream,
# or None for Popen's default. Every real file object is one of the two IO
# forms, so the union is complete without IO[Any].
type _StreamTarget = int | IO[str] | IO[bytes] | None


def resolve_executable(cmd: list[str]) -> list[str]:
    """The command with its executable resolved to a full PATH path.

    The repository's single executable-resolution point (REQ-302): the
    runners resolve through here before spawning, and the admission gate
    resolves through this same function, so a gate that passed cannot be
    followed by a call site that cannot find the binary (REQ-312).

    Raises:
        ValueError: If the command list is empty.
        EnvironmentFaultError: If the executable is not found in the system
            PATH -- the machine's setup, never a vendor fault (REQ-301).
    """
    if not cmd:
        raise ValueError("Command list cannot be empty")

    resolved_path = shutil.which(cmd[0])

    if not resolved_path:
        raise EnvironmentFaultError(cmd[0])

    return [resolved_path, *cmd[1:]]


def run_safe_process(
    cmd: list[str], **kwargs: object
) -> subprocess.CompletedProcess[Any]:
    """
    Run a subprocess safely by resolving the full path of the executable.

    Args:
        cmd: List of strings representing the command and its arguments.
        **kwargs: Additional keyword arguments to pass to subprocess.run.

    Returns:
        CompletedProcess instance.

    Raises:
        ValueError: If the command list is empty.
        EnvironmentFaultError: If the executable is not found in the system PATH.
    """
    safe_cmd = resolve_executable(cmd)

    return cast(Any, subprocess.run)(
        safe_cmd, check=kwargs.pop("check", False), **kwargs
    )


def run_safe_process_group(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    stdout: _StreamTarget = None,
    stderr: _StreamTarget = None,
    timeout: float | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Run a command in its own process group; kill the WHOLE group on timeout.

    subprocess.run's timeout handler kills only the direct child, so a child
    with descendants of its own orphans them (measured: a spawned ``sleep``
    grandchild survives its parent's timeout kill, and ``uv run`` forks
    rather than execs, so a shard's pytest is itself a grandchild). Starting
    the child as its own group leader makes ``os.killpg`` address the whole
    tree -- every descendant still in the group, which is all of them unless
    one calls setsid/setpgid itself. SIGKILL so no handler can ignore it.
    This is a sibling of run_safe_process rather than its default because the
    new group also detaches the child from the caller's terminal signal
    group: Ctrl+C no longer reaches an interactive child.

    Raises:
        ValueError: If the command list is empty.
        EnvironmentFaultError: If the executable is not found in the system PATH.
    """
    safe_cmd = resolve_executable(cmd)
    process = subprocess.Popen(
        safe_cmd,
        start_new_session=True,
        env=env,
        stdout=stdout,
        stderr=stderr,
    )
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
        raise
    returncode = process.wait()  # communicate already reaped; typed int here
    completed = subprocess.CompletedProcess(safe_cmd, returncode, out, err)
    if check and returncode:
        raise subprocess.CalledProcessError(returncode, safe_cmd, out, err)
    return completed


def _kill_process_group(process: subprocess.Popen[Any]) -> None:
    """Kill the child's whole process group, then reap the child itself."""
    # The group exited between the timeout firing and the kill.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()
