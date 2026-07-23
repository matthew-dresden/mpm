"""Integration tests for signal handling during mpm install and sync.

Covers:
  - AC-TEST-001: SIGTERM mid-install results in exit 143 and cleanup
  - AC-TEST-002: SIGINT mid-sync results in exit 130 and restore
  - AC-TEST-003: SIGHUP behaves per default handler

AC-FUNC-001: Signals produce graceful termination with cleanup contracts.
AC-CHANNEL-001: stdout vs stderr discipline is verified (no cross-channel leakage).
"""

import os
import pathlib
import signal
import subprocess
import sys
import threading
from unittest.mock import patch

import pytest

from mpm_cli.core.install import install


fcntl = pytest.importorskip("fcntl")


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"


_SIGNAL_WAIT_TIMEOUT = 30


_STARTUP_MARKER_TIMEOUT = 20


_RETRY_SLEEP_MARKER = "sleeping"


_EXIT_SIGTERM = 128 + signal.SIGTERM


_EXIT_SIGINT = 128 + signal.SIGINT


def _build_subprocess_env(extra_env: "dict[str, str] | None" = None) -> dict[str, str]:
    """Build an environment dict for subprocess-based tests.

    Ensures PYTHONPATH includes the source tree, REPO_TRACE is disabled,
    and PYTHONUNBUFFERED=1 so stdout lines arrive in real time rather than
    only when the subprocess pipe closes.

    Args:
        extra_env: Additional environment variables merged on top of os.environ.

    Returns:
        A dict suitable for passing as subprocess env.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    src_str = str(_SRC_DIR)
    entries = [src_str] + [p for p in existing.split(os.pathsep) if p and p != src_str]
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.setdefault("REPO_TRACE", "0")

    env["PYTHONUNBUFFERED"] = "1"
    if extra_env:
        env.update(extra_env)
    return env


def _write_mpmenv(directory: pathlib.Path, source_name: str = "primary") -> pathlib.Path:
    """Write a minimal single-source .mpm file and return its absolute path.

    The URL is intentionally unreachable so that the embedded repo tool fails
    the first git fetch and enters its retry-sleep phase, giving the test a
    reliable window in which to send a signal to the blocked process.

    Args:
        directory: Directory in which to create the .mpm file.
        source_name: Source name embedded in MPM_SOURCE_* keys.

    Returns:
        Absolute path to the written .mpm file.
    """
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        f"MPM_MARKETPLACE_INSTALL=false\n"
        f"MPM_SOURCE_{source_name}_URL=https://example.com/{source_name}.git\n"
        f"MPM_SOURCE_{source_name}_REF=main\n"
        f"MPM_SOURCE_{source_name}_PATH=repo-specs/manifest.xml\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://example.com\n",
        encoding="utf-8",
    )
    return mpmenv.resolve()


def _start_mpm_install(
    mpmenv: pathlib.Path,
    extra_env: "dict[str, str] | None" = None,
) -> subprocess.Popen:
    """Start a mpm install subprocess and return the Popen handle.

    Args:
        mpmenv: Absolute path to the .mpm config file.
        extra_env: Additional environment variables for the subprocess.

    Returns:
        Running Popen instance with captured stdout and stderr.
    """
    env = _build_subprocess_env(extra_env)
    return subprocess.Popen(
        [sys.executable, "-m", "mpm_cli", "install", str(mpmenv)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _wait_for_retry_sleep(proc: subprocess.Popen, timeout: float = _STARTUP_MARKER_TIMEOUT) -> bool:
    """Read proc stdout until the repo tool's retry-sleep line appears or timeout.

    The embedded repo tool emits a line containing "sleeping" when it fails the
    first git fetch and waits before retrying. With PYTHONUNBUFFERED=1 set by
    _build_subprocess_env(), this line arrives in real time, allowing the test
    to detect the exact moment the process enters its blocked sleep state.

    Args:
        proc: Running subprocess with captured stdout (text mode).
        timeout: Maximum seconds to wait for the retry-sleep marker.

    Returns:
        True if the marker appeared before the timeout, False otherwise.
    """
    found = threading.Event()

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if _RETRY_SLEEP_MARKER in line.lower():
                found.set()
                return
            if proc.poll() is not None:
                return

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    return found.wait(timeout=timeout)


@pytest.mark.integration
class TestSigtermMidInstall:
    """AC-TEST-001: SIGTERM mid-install results in exit 143 and cleanup.

    Sends SIGTERM to a running mpm install subprocess while it is blocked
    in the repo tool's retry-sleep phase and verifies:
      - The process exits with code 143 (128 + SIGTERM) so that shell callers
        can distinguish signal termination from a regular application error.
      - The install lock file is released by the OS on process exit (cleanup).
      - No Python tracebacks appear on stdout (AC-CHANNEL-001).
    """

    def test_sigterm_mid_install_exits_143(self, tmp_path: pathlib.Path) -> None:
        """SIGTERM during install exits with code 143 (128 + SIGTERM).

        Starts mpm install and waits until the repo tool's retry-sleep phase
        is reached (a reliable indicator of a blocked mid-install state).
        Sends SIGTERM and asserts the process exits with returncode 143.
        """
        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip(
                "Subprocess did not reach the retry-sleep phase within "
                f"{_STARTUP_MARKER_TIMEOUT}s; cannot send SIGTERM at the "
                "correct install phase."
            )

        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail(f"mpm install did not terminate within {_SIGNAL_WAIT_TIMEOUT}s after SIGTERM")

        assert proc.returncode == _EXIT_SIGTERM, (
            f"Expected exit code {_EXIT_SIGTERM} (128 + SIGTERM) after SIGTERM, "
            f"got {proc.returncode}. "
            "mpm install must install a SIGTERM handler that exits with "
            "128 + signal.SIGTERM so shell scripts can detect signal termination."
        )

    def test_sigterm_releases_install_lock(self, tmp_path: pathlib.Path) -> None:
        """SIGTERM during install releases the install lock file (cleanup).

        After the install process is killed by SIGTERM, the kernel releases
        all file locks held by the process. A subsequent install attempt must
        be able to acquire the lock without blocking indefinitely.
        """
        from mpm_cli.constants import INSTALL_LOCK_FILENAME

        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip("Subprocess did not reach the retry-sleep phase")

        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        lock_path = tmp_path / ".mpm-data" / INSTALL_LOCK_FILENAME
        if lock_path.exists():
            with open(lock_path, "w", encoding="utf-8") as lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                except BlockingIOError:
                    pytest.fail(
                        "Install lock is still held after SIGTERM-killed process. "
                        "The kernel must release file locks on process exit, "
                        "including signal-killed exits."
                    )

    def test_sigterm_stdout_contains_no_traceback(self, tmp_path: pathlib.Path) -> None:
        """SIGTERM during install does not leak a Python traceback to stdout.

        AC-CHANNEL-001: stdout must contain only progress messages. A signal
        handler that exits with os._exit(128 + signum) must not allow the
        Python runtime to write an exception traceback to stdout.
        """
        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip("Subprocess did not reach the retry-sleep phase")

        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        stdout = proc.stdout.read() if proc.stdout else ""
        assert "Traceback" not in stdout, f"Python traceback leaked to stdout after SIGTERM. stdout={stdout!r}"


@pytest.mark.integration
class TestSigintMidSync:
    """AC-TEST-002: SIGINT mid-sync results in exit 130 and restore.

    Sends SIGINT to a running mpm install subprocess while it is blocked
    in the repo tool's retry-sleep phase and verifies:
      - The process exits with code 130 (128 + SIGINT) so that shell callers
        can distinguish keyboard-interrupt termination from a regular error.
      - The project directory is in a restorable state: a subsequent install
        (with patched repo ops) succeeds without errors.
      - No progress messages appear on stderr (AC-CHANNEL-001).
    """

    def test_sigint_mid_sync_exits_130(self, tmp_path: pathlib.Path) -> None:
        """SIGINT during sync exits with code 130 (128 + SIGINT).

        Starts mpm install, waits until the retry-sleep phase, then sends
        SIGINT. The process must exit with returncode 130.
        """
        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip("Subprocess did not reach the retry-sleep phase")

        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail(f"mpm install did not terminate within {_SIGNAL_WAIT_TIMEOUT}s after SIGINT")

        assert proc.returncode == _EXIT_SIGINT, (
            f"Expected exit code {_EXIT_SIGINT} (128 + SIGINT) after SIGINT, "
            f"got {proc.returncode}. "
            "mpm install must propagate the SIGINT exit code (130) so that "
            "shell scripts and CI systems can detect interrupt-driven termination."
        )

    def test_sigint_mid_sync_state_is_restorable(self, tmp_path: pathlib.Path) -> None:
        """SIGINT during sync leaves the project state restorable.

        After SIGINT terminates a mpm install, a subsequent install()
        in-process (with patched repo ops) must succeed and produce a
        consistent filesystem state.
        """
        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip("Subprocess did not reach the retry-sleep phase")

        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert (tmp_path / ".packages").is_dir(), (
            ".packages/ must exist after install retry following SIGINT interruption"
        )
        assert (tmp_path / ".mpm-data" / "sources" / "primary").is_dir(), (
            ".mpm-data/sources/primary/ must exist after install retry"
        )

    def test_sigint_stderr_contains_no_progress_lines(self, tmp_path: pathlib.Path) -> None:
        """SIGINT during install does not leak progress messages to stderr.

        AC-CHANNEL-001: progress output belongs on stdout; error messages
        belong on stderr. No progress line (e.g., 'mpm install: parsing')
        must appear on stderr when the install is interrupted by SIGINT.
        """
        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip("Subprocess did not reach the retry-sleep phase")

        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        stderr = proc.stderr.read() if proc.stderr else ""
        assert "mpm install: parsing" not in stderr, (
            f"Progress message leaked to stderr after SIGINT. stderr={stderr!r}"
        )


@pytest.mark.integration
class TestSighupDefaultHandler:
    """AC-TEST-003: SIGHUP behaves per default handler.

    Sends SIGHUP to a running mpm install subprocess and verifies the
    process terminates as expected from the default SIGHUP disposition
    (process termination on POSIX). mpm must not install a custom SIGHUP
    handler that suppresses or alters this behavior.
    """

    def test_sighup_terminates_process_via_default_handler(self, tmp_path: pathlib.Path) -> None:
        """SIGHUP terminates the mpm process via the default signal handler.

        The default disposition for SIGHUP on POSIX systems is to terminate
        the process. The process must exit with a returncode consistent with
        signal termination: Python reports -signal.SIGHUP (-1) for a process
        killed directly by the OS with no custom handler installed.
        """
        mpmenv = _write_mpmenv(tmp_path, "primary")
        proc = _start_mpm_install(mpmenv)

        reached = _wait_for_retry_sleep(proc, timeout=_STARTUP_MARKER_TIMEOUT)
        if not reached:
            proc.kill()
            proc.wait()
            pytest.skip("Subprocess did not reach the retry-sleep phase")

        proc.send_signal(signal.SIGHUP)
        try:
            proc.wait(timeout=_SIGNAL_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail(f"mpm install did not terminate within {_SIGNAL_WAIT_TIMEOUT}s after SIGHUP")

        assert proc.returncode == -(signal.SIGHUP), (
            f"Expected SIGHUP default termination (returncode {-(signal.SIGHUP)}), "
            f"got {proc.returncode}. "
            "SIGHUP must not be intercepted; the default handler must terminate "
            "the process."
        )

    def test_sighup_no_custom_handler_installed_at_import(self) -> None:
        """Importing mpm_cli.cli does not install a custom SIGHUP handler.

        mpm must not call signal.signal(SIGHUP, ...) at module import time.
        This white-box check ensures the SIGHUP disposition remains at its
        pre-import value after loading the CLI module.
        """
        original_sighup = signal.getsignal(signal.SIGHUP)

        import importlib

        import mpm_cli.cli

        importlib.reload(mpm_cli.cli)

        after_import_sighup = signal.getsignal(signal.SIGHUP)

        assert original_sighup == after_import_sighup, (
            f"mpm_cli.cli changed the SIGHUP handler on import. "
            f"Before: {original_sighup!r}, After: {after_import_sighup!r}. "
            "SIGHUP must retain its default disposition."
        )
