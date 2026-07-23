"""Integration tests for mpm __complete_source_names_in_mpm -- AC-TEST-002, AC-CYCLE-001.

Builds a real .mpm fixture file with three sources, sets ${MPM_MANIFEST_FILE}
to that path, invokes `mpm __complete_source_names_in_mpm` via subprocess,
and asserts stdout is the sorted list of normalized names.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


def _write_mpm(path: Path, content: str) -> None:
    """Write content to path with mode 0600 (owner-read/write only)."""
    path.write_text(content)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _run_complete(
    mpm_path: Path,
    cache_dir: Path,
    current_token: str = "",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke `mpm __complete_source_names_in_mpm <current_token>` as subprocess."""
    env = {k: v for k, v in os.environ.items()}
    env["MPM_MANIFEST_FILE"] = str(mpm_path)

    env["MPM_HOME"] = str(cache_dir)
    env["MPM_COMPLETION_ENABLED"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "mpm_cli", "__complete_source_names_in_mpm", current_token],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.integration
class TestCompleteSourceNamesSubprocess:
    """End-to-end subprocess tests for __complete_source_names_in_mpm."""

    def test_three_sources_sorted_output(self, tmp_path: Path) -> None:
        """AC-FUNC-001 / AC-CYCLE-001: three sources return sorted names, one per line."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n",
        )
        result = _run_complete(mpm, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "bar\nbaz\nfoo\n"

    def test_prefix_filter(self, tmp_path: Path) -> None:
        """AC-FUNC-002: prefix 'b' returns only 'bar' and 'baz'."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n",
        )
        result = _run_complete(mpm, tmp_path, current_token="b")
        assert result.returncode == 0
        assert result.stdout == "bar\nbaz\n"

    def test_empty_stdout_on_missing_file(self, tmp_path: Path) -> None:
        """AC-FUNC-004: missing .mpm -> empty stdout, exit 0, log entry written."""
        mpm = tmp_path / "nonexistent.mpm"
        log_path = tmp_path / "completion-errors.log"
        result = _run_complete(
            mpm,
            tmp_path,
            extra_env={"MPM_COMPLETION_LOG": str(log_path)},
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert log_path.exists()
        log_content = log_path.read_text()
        assert "FileNotFoundError" in log_content
        assert str(mpm) in log_content

    def test_empty_stdout_when_disabled(self, tmp_path: Path) -> None:
        """AC-FUNC-006: MPM_COMPLETION_ENABLED=0 -> empty stdout, exit 0."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n",
        )
        log_path = tmp_path / "completion-errors.log"
        result = _run_complete(
            mpm,
            tmp_path,
            extra_env={
                "MPM_COMPLETION_ENABLED": "0",
                "MPM_COMPLETION_LOG": str(log_path),
            },
        )
        assert result.returncode == 0
        assert result.stdout == ""

        assert not log_path.exists()

    def test_hidden_subcommand_not_in_help(self, tmp_path: Path) -> None:
        """AC-FUNC-007: __complete_source_names_in_mpm absent from mpm --help."""
        result = subprocess.run(
            [sys.executable, "-m", "mpm_cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert "__complete_source_names_in_mpm" not in result.stdout

    def test_cycle_truncated_mpm_logs_error(self, tmp_path: Path) -> None:
        """AC-CYCLE-001 second half: truncate .mpm -> empty stdout, log entry appears."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n",
        )
        log_path = tmp_path / "completion-errors.log"

        result_full = _run_complete(
            mpm,
            tmp_path,
            extra_env={"MPM_COMPLETION_LOG": str(log_path)},
        )
        assert result_full.returncode == 0
        assert result_full.stdout == "bar\nbaz\nfoo\n"

        _write_mpm(mpm, "")

        result_empty = _run_complete(
            mpm,
            tmp_path,
            extra_env={"MPM_COMPLETION_LOG": str(log_path)},
        )
        assert result_empty.returncode == 0
        assert result_empty.stdout == ""
        log_content = log_path.read_text()
        assert "ValueError" in log_content
