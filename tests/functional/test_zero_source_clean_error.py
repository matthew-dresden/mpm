"""Functional tests: a zero-source .mpm must produce a clean error, not a crash.

A `.mpm` file that declares no sources (no
``MPM_SOURCE_<name>_{URL,REVISION,PATH}`` triples) is invalid. The parser
(`parse_mpmenv` -> `_discover_source_names`) correctly raises ``ValueError``.
Historically that exception escaped the per-command handlers (e.g. via
`doctor`'s `mpm_hash` recomputation, `outdated`'s top-level
`parse_mpmenv`, and `why`'s live-resolve path) and leaked a raw Python
traceback to stderr with a non-zero exit.

These subprocess tests assert the spec-canonical contract for every entry
command: a non-zero exit code, a clean human-readable error on stderr, and
NO Python traceback / no ``BUG:`` marker on either stream.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.conftest import write_lockfile_doctor_unit
from tests.functional.conftest import _run_mpm


_ZERO_SOURCE_MPM = "# zero-source workspace -- no MPM_SOURCE_* triples\nMPM_MARKETPLACE_INSTALL=false\n"


_FAKE_CATALOG_SOURCE = "file:///does/not/matter@main"


_TRACEBACK_MARKER = "Traceback (most recent call last)"
_BUG_MARKER = "BUG:"


def _write_zero_source_mpm(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a zero-source .mpm into tmp_path and return its path."""
    mpm = tmp_path / ".mpm"
    mpm.write_text(_ZERO_SOURCE_MPM, encoding="utf-8")
    return mpm


def _assert_clean_error(result, *, command: str) -> None:
    """Assert the subprocess result is a clean, traceback-free error.

    Args:
        result: The CompletedProcess returned by _run_mpm.
        command: The command name, used only in failure diagnostics.
    """
    assert result.returncode != 0, (
        f"'mpm {command}' on a zero-source .mpm must exit non-zero; "
        f"got {result.returncode}.\n  stdout: {result.stdout!r}\n  stderr: {result.stderr!r}"
    )
    assert _TRACEBACK_MARKER not in result.stderr, (
        f"'mpm {command}' leaked a Python traceback to stderr:\n{result.stderr}"
    )
    assert _TRACEBACK_MARKER not in result.stdout, (
        f"'mpm {command}' leaked a Python traceback to stdout:\n{result.stdout}"
    )
    assert _BUG_MARKER not in result.stderr, f"'mpm {command}' emitted a BUG: marker:\n{result.stderr}"
    assert _BUG_MARKER not in result.stdout, f"'mpm {command}' emitted a BUG: marker:\n{result.stdout}"
    combined_lower = (result.stderr + result.stdout).lower()
    assert "no sources" in combined_lower or "error" in combined_lower, (
        f"'mpm {command}' produced no recognizable clean error.\n"
        f"  stdout: {result.stdout!r}\n  stderr: {result.stderr!r}"
    )


@pytest.mark.functional
class TestZeroSourceCleanError:
    """Every entry command must fail cleanly on a zero-source .mpm."""

    def test_doctor_zero_source_no_traceback(self, tmp_path: pathlib.Path) -> None:
        mpm = _write_zero_source_mpm(tmp_path)
        write_lockfile_doctor_unit(tmp_path)
        result = _run_mpm("doctor", "--mpm-file", str(mpm))
        _assert_clean_error(result, command="doctor")

        assert "no sources" in result.stderr.lower(), f"stderr={result.stderr!r}"

    def test_install_zero_source_no_traceback(self, tmp_path: pathlib.Path) -> None:
        mpm = _write_zero_source_mpm(tmp_path)
        result = _run_mpm("install", str(mpm))
        _assert_clean_error(result, command="install")

    def test_clean_zero_source_no_traceback(self, tmp_path: pathlib.Path) -> None:
        mpm = _write_zero_source_mpm(tmp_path)
        result = _run_mpm("clean", str(mpm))
        _assert_clean_error(result, command="clean")

    def test_why_zero_source_no_traceback(self, tmp_path: pathlib.Path) -> None:
        mpm = _write_zero_source_mpm(tmp_path)
        result = _run_mpm(
            "why",
            "any-target",
            "--mpm-file",
            str(mpm),
            "--catalog-source",
            _FAKE_CATALOG_SOURCE,
        )
        _assert_clean_error(result, command="why")

    def test_outdated_zero_source_no_traceback(self, tmp_path: pathlib.Path) -> None:
        mpm = _write_zero_source_mpm(tmp_path)
        result = _run_mpm(
            "outdated",
            "--mpm-file",
            str(mpm),
            "--catalog-source",
            _FAKE_CATALOG_SOURCE,
        )
        _assert_clean_error(result, command="outdated")
