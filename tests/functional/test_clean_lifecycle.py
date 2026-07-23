"""Full clean lifecycle with mocked uninstall.

3.0.0 store model (spec Section 7.1 / FR-15): ``clean`` removes the install
artifacts (``.packages/`` and ``.mpm-data/``) from the shared ``MPM_HOME``
store at ``<MPM_HOME>/store``, the same location ``install`` writes them, not
from the project directory. Each test sets ``MPM_HOME`` to an isolated temp
dir and resolves the store base via ``resolve_workspace_base_dir``.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mpm_cli.core.clean import clean
from mpm_cli.core.install import resolve_workspace_base_dir


def _write_mpmenv(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def _isolated_store(monkeypatch: pytest.MonkeyPatch, mpm_home: Path) -> Path:
    """Point MPM_HOME at ``mpm_home`` and return the resolved store base.

    The store base is ``<MPM_HOME>/store`` -- the single location shared by
    install and clean for the ``.packages/`` and ``.mpm-data/`` artifacts.
    """
    mpm_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MPM_HOME", str(mpm_home))
    return resolve_workspace_base_dir()


@pytest.mark.functional
class TestCleanLifecycle:
    def test_clean_removes_packages_and_mpm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _isolated_store(monkeypatch, tmp_path / "home")
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_build_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_build_REF=main\n"
                "MPM_SOURCE_build_PATH=meta.xml\n"
                "MPM_SOURCE_build_NAME=build\n"
                "MPM_SOURCE_build_GITBASE=https://example.com\n"
            ),
        )
        (store / ".packages" / "pkg").mkdir(parents=True)
        (store / ".mpm-data" / "sources" / "build").mkdir(parents=True, exist_ok=True)

        clean(mpmenv)

        assert not (store / ".packages").exists()

    def test_clean_purge_removes_config_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """mpm clean --purge deletes the project .mpm and .mpm.lock after the normal teardown."""
        store = _isolated_store(monkeypatch, tmp_path / "home")
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_build_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_build_REF=main\n"
                "MPM_SOURCE_build_PATH=meta.xml\n"
                "MPM_SOURCE_build_NAME=build\n"
                "MPM_SOURCE_build_GITBASE=https://example.com\n"
            ),
        )
        (store / ".packages" / "pkg").mkdir(parents=True)

        clean(mpmenv, purge=True)

        assert not (store / ".packages").exists()
        assert not mpmenv.exists(), "--purge must delete the .mpm file"

    def test_clean_purge_all_removes_home_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """mpm clean --purge-all deletes the config files and removes the whole MPM_HOME store dir."""
        home = tmp_path / "home"
        store = _isolated_store(monkeypatch, home)
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_build_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_build_REF=main\n"
                "MPM_SOURCE_build_PATH=meta.xml\n"
                "MPM_SOURCE_build_NAME=build\n"
                "MPM_SOURCE_build_GITBASE=https://example.com\n"
            ),
        )
        assert store.exists()

        clean(mpmenv, purge=True, purge_home=True)

        assert not mpmenv.exists(), "--purge-all must delete the .mpm file"
        assert not home.exists(), "--purge-all must remove the entire MPM_HOME store directory"

    def test_clean_with_marketplace_runs_uninstall(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _isolated_store(monkeypatch, tmp_path / "home")
        mp_dir = tmp_path / "marketplaces"
        mp_dir.mkdir()
        (mp_dir / "some-file.txt").write_text("data")

        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_build_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_build_REF=main\n"
                "MPM_SOURCE_build_PATH=meta.xml\n"
                "MPM_SOURCE_build_NAME=build\n"
                "MPM_SOURCE_build_GITBASE=https://example.com\n"
                "MPM_SOURCE_build_MARKETPLACE=true\n"
                f"CLAUDE_MARKETPLACES_DIR={mp_dir}\n"
            ),
        )

        packages_dir = store / ".packages"
        packages_dir.mkdir(parents=True)
        (store / ".mpm-data" / "sources" / "build").mkdir(parents=True, exist_ok=True)

        with patch("mpm_cli.core.clean.uninstall_marketplace_plugins") as mock_uninstall:
            clean(mpmenv)
            mock_uninstall.assert_called_once_with(mp_dir)

        assert not mp_dir.exists()
        assert not packages_dir.exists()

    def test_clean_without_marketplace_skips_uninstall(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _isolated_store(monkeypatch, tmp_path / "home")
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_build_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_build_REF=main\n"
                "MPM_SOURCE_build_PATH=meta.xml\n"
                "MPM_SOURCE_build_NAME=build\n"
                "MPM_SOURCE_build_GITBASE=https://example.com\n"
            ),
        )
        (store / ".packages" / "pkg").mkdir(parents=True)
        (store / ".mpm-data" / "sources" / "build").mkdir(parents=True, exist_ok=True)

        with patch("mpm_cli.core.clean.uninstall_marketplace_plugins") as mock_uninstall:
            clean(mpmenv)
            mock_uninstall.assert_not_called()

        assert not (store / ".packages").exists()

    def test_clean_idempotent_on_already_clean(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _isolated_store(monkeypatch, tmp_path / "home")
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_build_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_build_REF=main\n"
                "MPM_SOURCE_build_PATH=meta.xml\n"
                "MPM_SOURCE_build_NAME=build\n"
                "MPM_SOURCE_build_GITBASE=https://example.com\n"
            ),
        )

        clean(mpmenv)

        assert not (store / ".packages").exists()
