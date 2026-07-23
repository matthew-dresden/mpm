"""End-to-end CLI invocation tests via subprocess."""

import pytest

from mpm_cli import __version__
from tests.functional.conftest import _run_mpm


@pytest.mark.functional
class TestMPMHelp:
    def test_top_level_help(self) -> None:
        result = _run_mpm("--help")
        assert result.returncode == 0
        assert "install" in result.stdout
        assert "clean" in result.stdout
        assert "validate" in result.stdout

    def test_install_help(self) -> None:
        result = _run_mpm("install", "--help")
        assert result.returncode == 0
        assert "mpmenv_path" in result.stdout

    def test_clean_help(self) -> None:
        result = _run_mpm("clean", "--help")
        assert result.returncode == 0
        assert "mpmenv_path" in result.stdout

    def test_validate_help(self) -> None:
        result = _run_mpm("validate", "--help")
        assert result.returncode == 0
        assert "xml" in result.stdout
        assert "marketplace" in result.stdout

    def test_validate_xml_help(self) -> None:
        result = _run_mpm("validate", "xml", "--help")
        assert result.returncode == 0
        assert "--repo-root" in result.stdout

    def test_validate_marketplace_help(self) -> None:
        result = _run_mpm("validate", "marketplace", "--help")
        assert result.returncode == 0
        assert "--repo-root" in result.stdout


@pytest.mark.functional
class TestMPMVersion:
    def test_version_flag(self) -> None:
        result = _run_mpm("--version")
        assert result.returncode == 0
        assert __version__ in result.stdout


@pytest.mark.functional
class TestMPMBadSubcommand:
    def test_no_subcommand_exits_2(self) -> None:
        result = _run_mpm()
        assert result.returncode == 2

    def test_invalid_subcommand_exits_2(self) -> None:
        result = _run_mpm("nonexistent")
        assert result.returncode == 2

    def test_install_no_arg_no_mpmenv_exits_1(self) -> None:
        result = _run_mpm("install")
        assert result.returncode == 1
        assert ".mpm" in result.stderr

    def test_clean_no_arg_no_mpmenv_exits_1(self) -> None:
        result = _run_mpm("clean")
        assert result.returncode == 1
        assert ".mpm" in result.stderr

    def test_validate_no_target_exits_2(self) -> None:
        result = _run_mpm("validate")
        assert result.returncode == 2


@pytest.mark.functional
class TestMPMRepo:
    def test_repo_is_registered_as_subcommand(self) -> None:
        """'mpm repo' must be a registered subcommand accessible from the CLI."""
        result = _run_mpm("repo", "--help")
        assert result.returncode == 0
        assert "repo" in result.stdout.lower()

    def test_repo_help_output_not_empty(self) -> None:
        """'mpm repo --help' must produce non-empty help text."""
        result = _run_mpm("repo", "--help")
        assert result.returncode == 0
        assert len(result.stdout) > 0
