"""Integration tests for automatic .mpm source discovery (12 tests).

Exercises find_mpmenv() by creating real directory trees and verifying that
the discovery walk behaves correctly across directory levels and edge cases.
"""

from pathlib import Path

import pytest

from mpm_cli.core.discover import find_mpmenv


def _write_mpmenv(directory: Path) -> Path:
    """Write a minimal .mpm file in directory and return its path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        "MPM_SOURCE_s_URL=https://example.com/s.git\nMPM_SOURCE_s_REF=main\nMPM_SOURCE_s_PATH=m.xml\nMPM_SOURCE_s_NAME=s\nMPM_SOURCE_s_GITBASE=https://example.com\n"
    )
    return mpmenv


@pytest.mark.integration
class TestFindMPMenvCurrentDir:
    """Verify discovery within the start directory itself."""

    def test_finds_in_start_dir(self, tmp_path: Path) -> None:
        expected = _write_mpmenv(tmp_path)
        result = find_mpmenv(start_dir=tmp_path)
        assert result == expected.resolve()

    def test_returns_absolute_path(self, tmp_path: Path) -> None:
        _write_mpmenv(tmp_path)
        result = find_mpmenv(start_dir=tmp_path)
        assert result.is_absolute()

    def test_uses_cwd_when_no_start_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        expected = _write_mpmenv(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = find_mpmenv()
        assert result == expected.resolve()


@pytest.mark.integration
class TestFindMPMenvParentTraversal:
    """Verify discovery traversal walks up the directory tree."""

    def test_finds_one_level_up(self, tmp_path: Path) -> None:
        expected = _write_mpmenv(tmp_path)
        child = tmp_path / "child"
        child.mkdir()
        result = find_mpmenv(start_dir=child)
        assert result == expected.resolve()

    def test_finds_two_levels_up(self, tmp_path: Path) -> None:
        expected = _write_mpmenv(tmp_path)
        grandchild = tmp_path / "a" / "b"
        grandchild.mkdir(parents=True)
        result = find_mpmenv(start_dir=grandchild)
        assert result == expected.resolve()

    def test_finds_three_levels_up(self, tmp_path: Path) -> None:
        expected = _write_mpmenv(tmp_path)
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = find_mpmenv(start_dir=deep)
        assert result == expected.resolve()

    def test_stops_at_nearest_ancestor(self, tmp_path: Path) -> None:
        _write_mpmenv(tmp_path)
        child = tmp_path / "child"
        child.mkdir()
        nearest = _write_mpmenv(child)
        result = find_mpmenv(start_dir=child)
        assert result == nearest.resolve()


@pytest.mark.integration
class TestFindMPMenvNotFound:
    """Verify fail-fast behaviour when no .mpm is found."""

    def test_raises_file_not_found(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            find_mpmenv(start_dir=empty)

    def test_error_message_mentions_mpm_add(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="mpm add"):
            find_mpmenv(start_dir=empty)

    def test_error_message_mentions_start_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match=str(empty)):
            find_mpmenv(start_dir=empty)

    def test_ignores_directory_named_dot_mpm(self, tmp_path: Path) -> None:
        mpm_dir = tmp_path / ".mpm"
        mpm_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            find_mpmenv(start_dir=tmp_path)

    def test_suggests_explicit_path_in_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="explicit path"):
            find_mpmenv(start_dir=empty)
