import signal
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agentic_workflows.exceptions import EnvironmentFaultError
from agentic_workflows.process_runner import (
    resolve_executable,
    run_safe_process,
    run_safe_process_group,
)


def test_run_safe_process_resolves_path():
    with patch("shutil.which") as mock_which, patch("subprocess.run") as mock_run:
        mock_which.return_value = "/usr/bin/echo"
        mock_run.return_value = MagicMock(returncode=0)

        result = run_safe_process(["echo", "test"], capture_output=True)

        mock_which.assert_called_once_with("echo")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        kwargs = mock_run.call_args[1]
        assert args[0] == "/usr/bin/echo"
        assert args[1] == "test"
        assert kwargs["capture_output"] is True
        assert result.returncode == 0


def test_resolve_executable_returns_the_full_path():
    """The resolver returns the command with argv[0] swapped for the PATH hit."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/echo"

        assert resolve_executable(["echo", "test"]) == ["/usr/bin/echo", "test"]


def test_resolve_executable_raises_the_environment_fault_when_missing():
    """REQ-302: the repository's single resolution point signals an absent
    binary with the environment fault, not a vendor-classifiable
    ``RuntimeError``."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None

        with pytest.raises(EnvironmentFaultError, match="nonexistent"):
            resolve_executable(["nonexistent"])


def test_run_safe_process_missing_binary():
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None

        with pytest.raises(EnvironmentFaultError, match="nonexistent"):
            run_safe_process(["nonexistent"])


def test_the_missing_binary_fault_is_not_catchable_as_a_runtime_error():
    """REQ-301: the fault a missing binary raises must sit outside the
    transient classifications -- ``RuntimeError`` is a member of both vendor
    tuples, so the old raise made every one of them admit a local fault."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None

        with pytest.raises(EnvironmentFaultError) as exc_info:
            run_safe_process(["nonexistent"])

    assert not isinstance(exc_info.value, RuntimeError)


def test_the_gate_mechanism_and_both_runners_hold_one_fault():
    """REQ-312 (mechanism half): the gate resolves a binary through the same
    public ``resolve_executable`` the call sites reach through the two
    runners, so a gate that passed cannot be followed by a call site that
    cannot find the binary. Patching the stdlib resolver moves all three
    identically: same class, same message."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None

        with pytest.raises(EnvironmentFaultError) as gate_fault:
            resolve_executable(["ffprobe"])
        with pytest.raises(EnvironmentFaultError) as run_fault:
            run_safe_process(["ffprobe"])
        with pytest.raises(EnvironmentFaultError) as group_fault:
            run_safe_process_group(["ffprobe"])

    assert str(gate_fault.value) == str(run_fault.value) == str(group_fault.value)


def test_run_safe_process_empty_args():
    with pytest.raises(ValueError, match="Command list cannot be empty"):
        run_safe_process([])


def test_run_safe_process_group_runs_the_child_in_its_own_group() -> None:
    """The group runner routes through Popen with the child as group leader."""
    with patch("shutil.which") as mock_which, patch("subprocess.Popen") as mock_popen:
        mock_which.return_value = "/usr/bin/echo"
        process = MagicMock()
        process.communicate.return_value = ("out", "err")
        # The runner reads the exit code from wait(), not the Popen attribute.
        process.wait.return_value = 0
        mock_popen.return_value = process

        result = run_safe_process_group(["echo", "test"])

        mock_popen.assert_called_once()
        assert mock_popen.call_args.kwargs["start_new_session"] is True
        process.communicate.assert_called_once_with(timeout=None)
        assert result.returncode == 0


def test_run_safe_process_group_kills_the_whole_group_on_timeout() -> None:
    """A timeout kills the group -- the direct-child kill would orphan a tree.

    Measured (logs/task45-red-orphan-evidence.log): subprocess.run's timeout
    handler kills only the direct child and a spawned grandchild survives it;
    ``uv run`` forks rather than execs, so a shard's pytest is itself a
    grandchild. The group kill is what takes the whole tree (REQ-011a).
    """
    with (
        patch("shutil.which") as mock_which,
        patch("subprocess.Popen") as mock_popen,
        patch("os.killpg") as mock_killpg,
    ):
        mock_which.return_value = "/usr/bin/sleep"
        process = MagicMock()
        process.pid = 4242
        process.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="sleep", timeout=1
        )
        mock_popen.return_value = process

        with pytest.raises(subprocess.TimeoutExpired):
            run_safe_process_group(["sleep", "5"], timeout=1)

        mock_killpg.assert_called_once_with(4242, signal.SIGKILL)
        process.wait.assert_called_once_with()
        assert mock_popen.call_args.kwargs["start_new_session"] is True
