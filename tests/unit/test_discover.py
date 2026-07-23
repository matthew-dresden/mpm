"""Tests for .mpm file auto-discovery."""

from pathlib import Path

import pytest

from mpm_cli.core.discover import find_mpmenv


@pytest.mark.unit
class TestFindMPMenvInCurrentDir:
    def test_finds_mpmenv_in_start_dir(self, tmp_path: Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_MARKETPLACE_INSTALL=false\n")

        result = find_mpmenv(start_dir=tmp_path)
        assert result == mpmenv.resolve()

    def test_returns_absolute_path(self, tmp_path: Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_MARKETPLACE_INSTALL=false\n")

        result = find_mpmenv(start_dir=tmp_path)
        assert result.is_absolute()


@pytest.mark.unit
class TestFindMPMenvInParent:
    def test_finds_mpmenv_one_level_up(self, tmp_path: Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_MARKETPLACE_INSTALL=false\n")
        child = tmp_path / "subdir"
        child.mkdir()

        result = find_mpmenv(start_dir=child)
        assert result == mpmenv.resolve()

    def test_finds_mpmenv_two_levels_up(self, tmp_path: Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_MARKETPLACE_INSTALL=false\n")
        grandchild = tmp_path / "a" / "b"
        grandchild.mkdir(parents=True)

        result = find_mpmenv(start_dir=grandchild)
        assert result == mpmenv.resolve()


@pytest.mark.unit
class TestFindMPMenvNearest:
    def test_stops_at_nearest(self, tmp_path: Path) -> None:
        root_mpmenv = tmp_path / ".mpm"
        root_mpmenv.write_text("root\n")
        child = tmp_path / "subdir"
        child.mkdir()
        child_mpmenv = child / ".mpm"
        child_mpmenv.write_text("child\n")

        result = find_mpmenv(start_dir=child)
        assert result == child_mpmenv.resolve()


@pytest.mark.unit
class TestFindMPMenvNotFound:
    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="No .mpm file found"):
            find_mpmenv(start_dir=empty_dir)

    def test_error_message_includes_start_dir(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(FileNotFoundError, match=str(empty_dir)):
            find_mpmenv(start_dir=empty_dir)

    def test_error_message_suggests_mpm_add(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="mpm add"):
            find_mpmenv(start_dir=empty_dir)


@pytest.mark.unit
class TestFindMPMenvDefaultDir:
    def test_uses_cwd_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_MARKETPLACE_INSTALL=false\n")
        monkeypatch.chdir(tmp_path)

        result = find_mpmenv()
        assert result == mpmenv.resolve()

    def test_ignores_directories_named_mpm(self, tmp_path: Path) -> None:
        mpm_dir = tmp_path / ".mpm"
        mpm_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            find_mpmenv(start_dir=tmp_path)
