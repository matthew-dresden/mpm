"""Functional tests for mpm install path variants (real subprocess, no mocks).

Exercises the CLI end-to-end via subprocess against real temporary directories
to verify path resolution and error behaviour without any patching.

Covers:
  - AC-TEST-001: auto-discovery finds .mpm in CWD or ancestor
  - AC-TEST-002: relative path .mpm resolved to absolute (regression guard E0-INSTALL-RELATIVE)
  - AC-TEST-003: absolute path accepted unchanged
  - AC-TEST-004: relative subdir path resolved correctly
  - AC-TEST-005: missing .mpm exits 1 with ".mpm file not found" message
  - AC-CHANNEL-001: stdout vs stderr discipline -- errors go to stderr, normal output to stdout
"""

import pathlib

import pytest

from tests.functional.conftest import _run_mpm
from tests.conftest import write_mpmenv


@pytest.mark.functional
class TestInstallAutoDiscoveryFunctional:
    """AC-TEST-001: auto-discovers .mpm in CWD or ancestor via real subprocess."""

    def test_install_no_arg_finds_mpmenv_in_cwd(self, tmp_path: pathlib.Path) -> None:
        """install with no arg discovers .mpm in cwd and attempts to proceed past path resolution."""
        write_mpmenv(tmp_path)
        result = _run_mpm("install", cwd=tmp_path)

        assert ".mpm file not found" not in result.stderr, (
            f"Auto-discovery should have found .mpm in cwd. stderr={result.stderr!r}"
        )
        assert "mpm install: found" in result.stdout, (
            f"Expected auto-discovery success message in stdout. stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_install_no_arg_finds_mpmenv_in_ancestor(self, tmp_path: pathlib.Path) -> None:
        """install with no arg discovers .mpm two levels above cwd."""
        write_mpmenv(tmp_path)
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        result = _run_mpm("install", cwd=deep)
        assert ".mpm file not found" not in result.stderr, (
            f"Auto-discovery should have found .mpm in ancestor. stderr={result.stderr!r}"
        )
        assert "mpm install: found" in result.stdout, (
            f"Expected auto-discovery success message in stdout. stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_install_no_arg_missing_mpmenv_exits_1(self, tmp_path: pathlib.Path) -> None:
        """AC-TEST-005: install with no arg in directory without .mpm exits 1."""
        empty = tmp_path / "empty"
        empty.mkdir()
        result = _run_mpm("install", cwd=empty)
        assert result.returncode == 1
        assert ".mpm" in result.stderr, f"Expected '.mpm' in stderr when no .mpm found. stderr={result.stderr!r}"


@pytest.mark.functional
class TestInstallRelativePathFunctional:
    """AC-TEST-002: relative path .mpm resolved to absolute."""

    def test_install_relative_path_dot_mpm_succeeds_past_file_resolution(self, tmp_path: pathlib.Path) -> None:
        """install .mpm (relative) finds the file and proceeds past path resolution."""
        write_mpmenv(tmp_path)
        result = _run_mpm("install", ".mpm", cwd=tmp_path)

        assert ".mpm file not found" not in result.stderr, (
            f"Relative '.mpm' should resolve to the file in cwd. stderr={result.stderr!r}"
        )

    def test_install_relative_path_missing_exits_1_with_not_found_message(self, tmp_path: pathlib.Path) -> None:
        """install nonexistent relative path exits 1 with '.mpm file not found'."""
        result = _run_mpm("install", ".mpm", cwd=tmp_path)
        assert result.returncode == 1
        assert ".mpm file not found" in result.stderr, (
            f"Expected '.mpm file not found' in stderr. stderr={result.stderr!r}"
        )


@pytest.mark.functional
class TestInstallAbsolutePathFunctional:
    """AC-TEST-003: absolute path accepted unchanged."""

    def test_install_absolute_path_resolves_correctly(self, tmp_path: pathlib.Path) -> None:
        """install /abs/.mpm finds the file and proceeds past path resolution."""
        mpmenv = write_mpmenv(tmp_path)
        result = _run_mpm("install", str(mpmenv))
        assert ".mpm file not found" not in result.stderr, (
            f"Absolute path should resolve the file. stderr={result.stderr!r}"
        )

    def test_install_nonexistent_absolute_path_exits_1_with_not_found(self, tmp_path: pathlib.Path) -> None:
        """install /nonexistent/.mpm exits 1 with '.mpm file not found'."""
        nonexistent = str(tmp_path / "does_not_exist" / ".mpm")
        result = _run_mpm("install", nonexistent)
        assert result.returncode == 1
        assert ".mpm file not found" in result.stderr, (
            f"Expected '.mpm file not found' in stderr for nonexistent absolute path. stderr={result.stderr!r}"
        )


@pytest.mark.functional
class TestInstallRelativeSubdirPathFunctional:
    """AC-TEST-004: relative subdir path resolved correctly."""

    def test_install_relative_subdir_path_resolves_correctly(self, tmp_path: pathlib.Path) -> None:
        """install subdir/.mpm resolves the subdir relative path correctly."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        write_mpmenv(subdir)
        result = _run_mpm("install", "subdir/.mpm", cwd=tmp_path)
        assert ".mpm file not found" not in result.stderr, (
            f"Relative subdir path 'subdir/.mpm' should resolve the file. stderr={result.stderr!r}"
        )

    def test_install_relative_subdir_path_missing_exits_1(self, tmp_path: pathlib.Path) -> None:
        """install subdir/.mpm when file is missing exits 1 with '.mpm file not found'."""
        result = _run_mpm("install", "subdir/.mpm", cwd=tmp_path)
        assert result.returncode == 1
        assert ".mpm file not found" in result.stderr, (
            f"Expected '.mpm file not found' for missing subdir/.mpm. stderr={result.stderr!r}"
        )


@pytest.mark.functional
class TestInstallChannelDiscipline:
    """AC-CHANNEL-001: stdout vs stderr discipline for CLI install errors."""

    def test_not_found_error_goes_to_stderr_not_stdout(self, tmp_path: pathlib.Path) -> None:
        """AC-CHANNEL-001: '.mpm file not found' error must appear on stderr, not stdout."""
        empty = tmp_path / "empty"
        empty.mkdir()
        result = _run_mpm("install", cwd=empty)
        assert result.returncode == 1
        assert ".mpm" in result.stderr, f"Error must be on stderr. stderr={result.stderr!r}"
        assert ".mpm file not found" not in result.stdout, f"Error must NOT leak to stdout. stdout={result.stdout!r}"

    def test_explicit_missing_path_error_goes_to_stderr_not_stdout(self, tmp_path: pathlib.Path) -> None:
        """AC-CHANNEL-001: explicit missing .mpm path error goes to stderr, not stdout."""
        nonexistent = str(tmp_path / "ghost" / ".mpm")
        result = _run_mpm("install", nonexistent)
        assert result.returncode == 1
        assert ".mpm file not found" in result.stderr, f"Error must be on stderr. stderr={result.stderr!r}"
        assert ".mpm file not found" not in result.stdout, f"Error must NOT leak to stdout. stdout={result.stdout!r}"

    def test_successful_autodiscovery_prints_found_to_stdout(self, tmp_path: pathlib.Path) -> None:
        """AC-CHANNEL-001: successful auto-discovery prints found path to stdout."""
        write_mpmenv(tmp_path)
        result = _run_mpm("install", cwd=tmp_path)

        assert "mpm install: found" in result.stdout, (
            f"Auto-discovery 'found' message must be on stdout not stderr. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
