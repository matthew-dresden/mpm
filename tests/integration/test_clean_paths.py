"""Integration tests for mpm clean path resolution and auto-discovery (6 tests).

Verifies the CLI boundary behaviour of the clean command for:
  - AC-TEST-001: auto-discovery of .mpm from CWD or ancestor
  - AC-TEST-002: relative path .mpm resolved to absolute (regression guard E0-INSTALL-RELATIVE clean variant)
  - AC-TEST-003: absolute path accepted unchanged
  - AC-TEST-004: missing .mpm exits 1 with stderr message
  - AC-FUNC-001: clean CLI boundary mirrors install CLI boundary for path resolution
  - AC-CHANNEL-001: stdout vs stderr discipline verified (no cross-channel leakage)
"""

import pathlib
from unittest.mock import patch

import pytest

from mpm_cli.cli import main
from mpm_cli.core.discover import find_mpmenv
from tests.conftest import write_mpmenv


@pytest.mark.integration
class TestCleanAutoDiscovery:
    """AC-TEST-001: auto-discovery of .mpm from CWD."""

    def test_clean_auto_discovers_mpmenv_in_cwd(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-TEST-001: clean with no path argument discovers .mpm in cwd and invokes clean."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            main(["clean"])

        mock_clean.assert_called_once()
        called_path: pathlib.Path = mock_clean.call_args[0][0]
        assert called_path.is_absolute()
        assert called_path.name == ".mpm"
        assert called_path.parent == tmp_path.resolve()

    def test_clean_auto_discovers_mpmenv_in_ancestor(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-TEST-001: clean with no path argument discovers .mpm two levels above cwd."""
        write_mpmenv(tmp_path)
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)

        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            main(["clean"])

        mock_clean.assert_called_once()
        called_path: pathlib.Path = mock_clean.call_args[0][0]
        assert called_path == (tmp_path / ".mpm").resolve()


@pytest.mark.integration
class TestCleanRelativePath:
    """AC-TEST-002 and AC-FUNC-001: relative path resolved to absolute before core clean."""

    def test_relative_path_dot_mpm_resolved_to_absolute(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-TEST-002: 'mpm clean .mpm' resolves to absolute and invokes clean."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            main(["clean", ".mpm"])

        mock_clean.assert_called_once()
        called_path: pathlib.Path = mock_clean.call_args[0][0]
        assert called_path.is_absolute(), "CLI must resolve relative .mpm to absolute before invoking clean()"
        assert called_path == (tmp_path / ".mpm").resolve()

    def test_relative_path_resolves_to_absolute_before_core(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-FUNC-001: clean() receives an absolute Path regardless of relative CLI argument."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        received_paths: list[pathlib.Path] = []

        def capture_path(
            path: pathlib.Path, orphans: bool = False, purge: bool = False, purge_home: bool = False
        ) -> None:
            received_paths.append(path)

        with patch("mpm_cli.commands.clean.clean", side_effect=capture_path):
            main(["clean", ".mpm"])

        assert len(received_paths) == 1
        assert received_paths[0].is_absolute(), (
            "AC-FUNC-001: CLI boundary must resolve relative paths to absolute before invoking clean()"
        )


@pytest.mark.integration
class TestCleanAbsolutePath:
    """AC-TEST-003: absolute path accepted and passed through correctly."""

    def test_absolute_path_accepted_and_passed_to_clean(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """AC-TEST-003: 'mpm clean /abs/.mpm' accepted and passed as absolute to clean()."""
        mpmenv = write_mpmenv(tmp_path)
        absolute_path = str(mpmenv)
        assert pathlib.Path(absolute_path).is_absolute()

        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            main(["clean", absolute_path])

        mock_clean.assert_called_once()
        called_path: pathlib.Path = mock_clean.call_args[0][0]
        assert called_path.is_absolute()
        assert called_path == mpmenv.resolve()


@pytest.mark.integration
class TestCleanMissingMPMenv:
    """AC-TEST-004 and AC-CHANNEL-001: missing .mpm exits 1 with stderr message only."""

    def test_missing_mpmenv_auto_discovery_exits_1_with_stderr_message(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """AC-TEST-004: 'mpm clean' with missing .mpm exits 1 with error on stderr."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as exc_info:
            main(["clean"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert ".mpm" in captured.err, f"Expected '.mpm' in stderr, got: {captured.err!r}"
        assert captured.out == "", (
            f"AC-CHANNEL-001: error output must go to stderr only, not stdout; stdout={captured.out!r}"
        )

    def test_explicit_missing_path_exits_1_with_stderr_message(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """AC-TEST-004: 'mpm clean /nonexistent/.mpm' exits 1 with '.mpm file not found' on stderr."""
        nonexistent = str(tmp_path / "nonexistent" / ".mpm")

        with pytest.raises(SystemExit) as exc_info:
            main(["clean", nonexistent])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert ".mpm file not found" in captured.err, f"Expected '.mpm file not found' in stderr, got: {captured.err!r}"
        assert captured.out == "", (
            f"AC-CHANNEL-001: error output must go to stderr only, not stdout; stdout={captured.out!r}"
        )

    def test_auto_discovery_success_message_goes_to_stdout(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """AC-CHANNEL-001: discovery success message goes to stdout, not stderr."""
        write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch("mpm_cli.commands.clean.clean"):
            main(["clean"])

        captured = capsys.readouterr()
        assert captured.err == "", f"AC-CHANNEL-001: no error output expected on success; stderr={captured.err!r}"
        assert "clean" in captured.out.lower() or ".mpm" in captured.out, (
            f"AC-CHANNEL-001: success discovery message expected on stdout; stdout={captured.out!r}"
        )

    def test_auto_discovery_find_mpmenv_contract_matches(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-FUNC-001: path passed to clean() equals find_mpmenv() result from the same cwd."""
        write_mpmenv(tmp_path)
        child = tmp_path / "sub"
        child.mkdir()
        monkeypatch.chdir(child)

        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            main(["clean"])

        mock_clean.assert_called_once()
        called_path: pathlib.Path = mock_clean.call_args[0][0]
        assert called_path == find_mpmenv(start_dir=child)


@pytest.mark.integration
class TestCleanPurgeAllWithoutMPM:
    """``mpm clean --purge-all`` removes the shared home store even with no ``.mpm``."""

    def test_purge_all_removes_home_store_when_no_mpm(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no discoverable ``.mpm`` but an existing MPM_HOME store, --purge-all removes it."""
        home_store = tmp_path / "mpmhome"
        (home_store / "store").mkdir(parents=True)
        (home_store / "cache").mkdir(parents=True)
        monkeypatch.setenv("MPM_HOME", str(home_store))

        workdir = tmp_path / "elsewhere"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        main(["clean", "--purge-all"])

        assert not home_store.exists(), "--purge-all must remove the MPM_HOME store even with no .mpm"

    def test_purge_all_without_mpm_refuses_when_home_store_is_user_home(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The standalone path preserves the safety refusal: MPM_HOME == $HOME exits 1, nothing removed."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("MPM_HOME", str(fake_home))

        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        with pytest.raises(SystemExit) as exc_info:
            main(["clean", "--purge-all"])

        assert exc_info.value.code == 1
        assert fake_home.exists(), "the refusal must leave $HOME intact"
