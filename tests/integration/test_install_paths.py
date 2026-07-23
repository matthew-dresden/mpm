"""Integration tests for mpm install path resolution and auto-discovery (9 tests).

Verifies the CLI boundary behaviour of the install command for:
  - AC-TEST-001: auto-discovery of .mpm from CWD or ancestor
  - AC-TEST-002: relative path .mpm resolved to absolute (regression guard E0-INSTALL-RELATIVE)
  - AC-TEST-003: absolute path accepted unchanged
  - AC-TEST-004: relative subdir path resolved correctly
  - AC-TEST-005: missing .mpm exits 1 with ".mpm file not found" message
  - AC-FUNC-001: CLI boundary resolves relative manifests to absolute before invoking parser
  - AC-FUNC-002: auto-discovery walk matches find_mpmenv() contract
"""

import pathlib
from unittest.mock import patch

import pytest

from mpm_cli.cli import main
from mpm_cli.core.discover import find_mpmenv
from tests.conftest import write_mpmenv


@pytest.mark.integration
class TestInstallAutoDiscovery:
    """AC-TEST-001 and AC-FUNC-002: auto-discovery from CWD and ancestors."""

    def test_install_auto_discovers_mpmenv_in_cwd(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install with no path argument discovers .mpm in cwd and invokes install."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install"])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path.is_absolute()
        assert called_path.name == ".mpm"
        assert called_path.parent == tmp_path.resolve()

    def test_install_auto_discovers_mpmenv_in_ancestor(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install with no path argument discovers .mpm two levels above cwd."""
        write_mpmenv(tmp_path)
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install"])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path == (tmp_path / ".mpm").resolve()

    def test_auto_discovery_result_matches_find_mpmenv_contract(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-FUNC-002: auto-discovery path passed to install() equals find_mpmenv() result."""
        write_mpmenv(tmp_path)
        child = tmp_path / "sub"
        child.mkdir()
        monkeypatch.chdir(child)

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install"])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path == find_mpmenv(start_dir=child)


@pytest.mark.integration
class TestInstallRelativePath:
    """AC-TEST-002 and AC-FUNC-001: relative path resolved to absolute before parser."""

    def test_relative_path_dot_mpm_resolved_to_absolute(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-TEST-002: 'mpm install .mpm' resolves to absolute and invokes install."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install", ".mpm"])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path.is_absolute(), "CLI must resolve relative .mpm to absolute before invoking install()"
        assert called_path == (tmp_path / ".mpm").resolve()

    def test_relative_path_resolves_to_absolute_before_parser(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-FUNC-001: install() receives an absolute Path regardless of relative CLI argument."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        received_paths: list[pathlib.Path] = []

        def capture_path(path: pathlib.Path, **kwargs: object) -> None:
            received_paths.append(path)

        with patch("mpm_cli.commands.install.install", side_effect=capture_path):
            main(["install", ".mpm"])

        assert len(received_paths) == 1
        assert received_paths[0].is_absolute(), (
            "AC-FUNC-001: CLI boundary must resolve relative paths to absolute before invoking install()"
        )


@pytest.mark.integration
class TestInstallAbsolutePath:
    """AC-TEST-003: absolute path accepted and passed through correctly."""

    def test_absolute_path_accepted_and_passed_to_install(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """AC-TEST-003: 'mpm install /abs/.mpm' accepted and passed as absolute to install()."""
        mpmenv = write_mpmenv(tmp_path)
        absolute_path = str(mpmenv)
        assert pathlib.Path(absolute_path).is_absolute()

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install", absolute_path])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path.is_absolute()
        assert called_path == mpmenv.resolve()


@pytest.mark.integration
class TestInstallRelativeSubdirPath:
    """AC-TEST-004: relative subdir path resolved correctly."""

    def test_relative_subdir_path_resolved_correctly(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-TEST-004: 'mpm install subdir/.mpm' resolves relative subdir to absolute."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        write_mpmenv(subdir)
        monkeypatch.chdir(tmp_path)

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install", "subdir/.mpm"])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path.is_absolute()
        assert called_path == (subdir / ".mpm").resolve()


@pytest.mark.integration
class TestInstallMissingMPMenv:
    """AC-TEST-005: missing .mpm exits 1 with clear error message."""

    def test_missing_mpmenv_exits_1_with_not_found_message(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """AC-TEST-005: 'mpm install' with missing .mpm exits 1 with '.mpm file not found'."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["install"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No .mpm file found" in captured.err, f"Expected 'No .mpm file found' in stderr, got: {captured.err!r}"

    def test_explicit_missing_path_exits_1_with_not_found_message(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """AC-TEST-005: 'mpm install /nonexistent/.mpm' exits 1 with '.mpm file not found'."""
        nonexistent = str(tmp_path / "nonexistent" / ".mpm")

        with pytest.raises(SystemExit) as exc_info:
            main(["install", nonexistent])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert ".mpm file not found" in captured.err, f"Expected '.mpm file not found' in stderr, got: {captured.err!r}"
