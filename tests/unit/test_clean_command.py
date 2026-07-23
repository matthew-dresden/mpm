"""Tests for the clean command handler."""

import argparse
import pathlib
import types
from unittest.mock import MagicMock, patch

import pytest

from mpm_cli.commands.clean import _run, register


@pytest.mark.unit
class TestCleanCommand:
    def test_delegates_to_core(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REVISION=main\nMPM_SOURCE_build_PATH=meta.xml\n"
        )
        args = types.SimpleNamespace(mpmenv_path=mpmenv, orphans=False, purge=False, purge_all=False)
        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            _run(args)
            mock_clean.assert_called_once_with(mpmenv, orphans=False, purge=False, purge_home=False)

    def test_delegates_orphans_flag_to_core(self, tmp_path: pathlib.Path) -> None:
        """``_run`` must forward ``args.orphans`` into ``clean(..., orphans=...)``."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REVISION=main\nMPM_SOURCE_build_PATH=meta.xml\n"
        )
        args = types.SimpleNamespace(mpmenv_path=mpmenv, orphans=True, purge=False, purge_all=False)
        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            _run(args)
            mock_clean.assert_called_once_with(mpmenv, orphans=True, purge=False, purge_home=False)

    def test_delegates_purge_flag_to_core(self, tmp_path: pathlib.Path) -> None:
        """``--purge`` forwards ``purge=True`` (and ``purge_home=False``) to clean()."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REF=main\nMPM_SOURCE_build_PATH=meta.xml\n"
        )
        args = types.SimpleNamespace(mpmenv_path=mpmenv, orphans=False, purge=True, purge_all=False)
        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            _run(args)
            mock_clean.assert_called_once_with(mpmenv, orphans=False, purge=True, purge_home=False)

    def test_purge_all_implies_purge_and_forwards_purge_home(self, tmp_path: pathlib.Path) -> None:
        """``--purge-all`` implies purge and forwards ``purge_home=True`` to clean()."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REF=main\nMPM_SOURCE_build_PATH=meta.xml\n"
        )
        args = types.SimpleNamespace(mpmenv_path=mpmenv, orphans=False, purge=False, purge_all=True)
        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            _run(args)
            mock_clean.assert_called_once_with(mpmenv, orphans=False, purge=True, purge_home=True)


@pytest.mark.unit
class TestCleanRegister:
    def test_mpmenv_path_is_optional(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean"])
        assert parsed.mpmenv_path is None

    def test_explicit_path_accepted(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean", "/tmp/test-mpmenv"])
        assert str(parsed.mpmenv_path) == "/tmp/test-mpmenv"

    def test_orphans_flag_defaults_false(self) -> None:
        """``--orphans`` is opt-in: absent from argv => ``args.orphans is False``."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean"])
        assert parsed.orphans is False

    def test_orphans_flag_parses_true(self) -> None:
        """``mpm clean --orphans`` sets ``args.orphans`` to True."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean", "--orphans"])
        assert parsed.orphans is True

    def test_purge_flags_default_false(self) -> None:
        """``--purge`` / ``--purge-all`` are opt-in: absent from argv => both False."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean"])
        assert parsed.purge is False
        assert parsed.purge_all is False

    def test_purge_flag_parses_true(self) -> None:
        """``mpm clean --purge`` sets ``args.purge`` True (purge_all stays False)."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean", "--purge"])
        assert parsed.purge is True
        assert parsed.purge_all is False

    def test_purge_all_flag_parses_true(self) -> None:
        """``mpm clean --purge-all`` sets ``args.purge_all`` True."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        parsed = parser.parse_args(["clean", "--purge-all"])
        assert parsed.purge_all is True

    def test_description_documents_store_prune(self) -> None:
        """The clean subparser description documents that it prunes the MPM_HOME store.

        ``mpm clean`` now prunes the content-addressed entries from the shared
        MPM_HOME store in addition to the per-project artifacts; the help text
        must keep that behaviour documented (doc-in-sync, spec Section 3.5).
        """
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register(subparsers)

        clean_parser = subparsers.choices["clean"]
        description = clean_parser.description or ""
        assert "store" in description.lower(), "the clean help text must document that it prunes the MPM_HOME store"


@pytest.mark.unit
class TestCleanAutoDiscovery:
    def test_no_arg_calls_find_mpmenv(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REVISION=main\nMPM_SOURCE_build_PATH=meta.xml\n"
        )
        args = MagicMock()
        args.mpmenv_path = None

        with (
            patch("mpm_cli.commands.clean.find_mpmenv", return_value=mpmenv) as mock_find,
            patch("mpm_cli.commands.clean.clean"),
        ):
            _run(args)
            mock_find.assert_called_once()

    def test_explicit_path_skips_discovery(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REVISION=main\nMPM_SOURCE_build_PATH=meta.xml\n"
        )
        args = MagicMock()
        args.mpmenv_path = mpmenv

        with (
            patch("mpm_cli.commands.clean.find_mpmenv") as mock_find,
            patch("mpm_cli.commands.clean.clean"),
        ):
            _run(args)
            mock_find.assert_not_called()

    def test_auto_discover_not_found_exits(self) -> None:
        args = MagicMock()
        args.mpmenv_path = None
        args.purge_all = False

        with (
            patch(
                "mpm_cli.commands.clean.find_mpmenv",
                side_effect=FileNotFoundError("No .mpm file found"),
            ),
            pytest.raises(SystemExit),
        ):
            _run(args)

    def test_purge_all_without_mpm_removes_home_store(self) -> None:
        """``--purge-all`` with no discoverable ``.mpm`` removes the shared store, no exit.

        The home-store teardown is machine-global, so ``mpm clean --purge-all``
        must still run ``remove_mpm_home_store`` when auto-discovery finds no
        ``.mpm`` (e.g. right after ``--purge`` deleted it), rather than failing.
        """
        args = MagicMock()
        args.mpmenv_path = None
        args.purge_all = True

        with (
            patch(
                "mpm_cli.commands.clean.find_mpmenv",
                side_effect=FileNotFoundError("No .mpm file found"),
            ),
            patch("mpm_cli.commands.clean.remove_mpm_home_store") as mock_remove,
            patch("mpm_cli.commands.clean.clean") as mock_clean,
        ):
            _run(args)

        mock_remove.assert_called_once_with()
        mock_clean.assert_not_called()

    def test_purge_all_explicit_missing_path_removes_home_store(self, tmp_path: pathlib.Path) -> None:
        """``--purge-all`` with an explicit but missing ``.mpm`` path removes the shared store."""
        args = MagicMock()
        args.mpmenv_path = tmp_path / "nope" / ".mpm"
        args.purge_all = True

        with (
            patch("mpm_cli.commands.clean.remove_mpm_home_store") as mock_remove,
            patch("mpm_cli.commands.clean.clean") as mock_clean,
        ):
            _run(args)

        mock_remove.assert_called_once_with()
        mock_clean.assert_not_called()

    def test_purge_only_without_mpm_still_exits(self) -> None:
        """``--purge`` alone (not ``--purge-all``) with no ``.mpm`` still fails fast (exit 1)."""
        args = MagicMock()
        args.mpmenv_path = None
        args.purge = True
        args.purge_all = False

        with (
            patch(
                "mpm_cli.commands.clean.find_mpmenv",
                side_effect=FileNotFoundError("No .mpm file found"),
            ),
            patch("mpm_cli.commands.clean.remove_mpm_home_store") as mock_remove,
            pytest.raises(SystemExit) as exc_info,
        ):
            _run(args)

        assert exc_info.value.code == 1
        mock_remove.assert_not_called()

    def test_clean_error_exits(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("NO_SOURCES=true\n")
        args = MagicMock()
        args.mpmenv_path = mpmenv

        with pytest.raises(SystemExit):
            _run(args)


_VALID_MPMENV = (
    "MPM_SOURCE_build_URL=https://example.com\nMPM_SOURCE_build_REVISION=main\nMPM_SOURCE_build_PATH=meta.xml\n"
)


@pytest.mark.unit
class TestCleanResolvesExplicitPath:
    """``_run`` must resolve an explicit ``mpmenv_path`` to an absolute path.

    ``mpm clean .mpm`` (relative) previously passed ``PosixPath('.mpm')``
    straight through to ``clean()``, which in turn propagates into the repo
    manifest parser where ``manifest_file`` must be absolute. The CLI handler
    must normalize at the boundary to match ``find_mpmenv()``'s contract.
    """

    def test_relative_mpmenv_path_is_resolved_to_abspath(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        """``_run`` must resolve ``PosixPath('.mpm')`` to an absolute path before clean()."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_VALID_MPMENV)
        monkeypatch.chdir(tmp_path)

        args = MagicMock()
        args.mpmenv_path = pathlib.Path(".mpm")
        args.orphans = False

        received: list[pathlib.Path] = []

        def _capture_clean(path, orphans=False, purge=False, purge_home=False):
            received.append(path)

        with patch("mpm_cli.commands.clean.clean", side_effect=_capture_clean):
            _run(args)

        assert len(received) == 1, f"clean() must be called exactly once, got {len(received)} calls"
        resolved = received[0]
        assert resolved.is_absolute(), f"clean() must receive an absolute path, got {resolved!r}"
        assert resolved == mpmenv.resolve(), (
            f"clean() must receive the resolved .mpm path {mpmenv.resolve()!r}, got {resolved!r}"
        )

    def test_absolute_mpmenv_path_is_unchanged(self, tmp_path: pathlib.Path) -> None:
        """``_run`` must pass an already-absolute path through to clean() unchanged."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_VALID_MPMENV)
        args = MagicMock()
        args.mpmenv_path = mpmenv
        args.orphans = False

        received: list[pathlib.Path] = []

        def _capture_clean(path, orphans=False, purge=False, purge_home=False):
            received.append(path)

        with patch("mpm_cli.commands.clean.clean", side_effect=_capture_clean):
            _run(args)

        assert received == [mpmenv.resolve()], f"clean() must receive the resolved absolute path, got {received!r}"

    def test_missing_relative_mpmenv_fails_fast_with_clear_message(
        self, tmp_path: pathlib.Path, monkeypatch, capsys
    ) -> None:
        """``_run`` must fail-fast with an actionable message when the .mpm file does not exist."""
        monkeypatch.chdir(tmp_path)
        args = MagicMock()
        args.mpmenv_path = pathlib.Path(".mpm")
        args.purge_all = False

        with patch("mpm_cli.commands.clean.clean") as mock_clean:
            with pytest.raises(SystemExit) as exc_info:
                _run(args)

        assert exc_info.value.code == 1, f"missing .mpm must exit 1, got {exc_info.value.code!r}"
        mock_clean.assert_not_called()
        captured = capsys.readouterr()
        assert ".mpm file not found" in captured.err, f"stderr must mention '.mpm file not found', got {captured.err!r}"
