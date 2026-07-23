"""Full install lifecycle with mocked repo Python API.

3.0.0 store model (spec Section 7.1 / FR-15): the install artifacts
(``.mpm-data/sources/<name>/`` and the aggregated ``.packages/`` symlinks)
live under the shared ``MPM_HOME`` store at ``<MPM_HOME>/store``, not under
the project directory. A store ``.gitignore`` is written only when the store
sits inside a git working tree. Each test sets
``MPM_HOME`` to an isolated temp dir and resolves the store base via
``resolve_workspace_base_dir`` so the assertions point at the real artifact
location.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mpm_cli.commands.install import _run as _install_run
from mpm_cli.core.install import install, resolve_workspace_base_dir
from tests.conftest import write_manifest_for_sync


def _write_mpmenv(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def _isolated_store(monkeypatch: pytest.MonkeyPatch, mpm_home: Path) -> Path:
    """Point MPM_HOME at ``mpm_home`` and return the resolved store base.

    The store base is ``<MPM_HOME>/store`` (the single location shared by
    install and clean), where the ``.mpm-data/`` source workspaces and the
    aggregated ``.packages/`` symlinks are written.
    """
    mpm_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MPM_HOME", str(mpm_home))
    return resolve_workspace_base_dir()


@pytest.mark.functional
class TestInstallLifecycle:
    def test_single_source_creates_dirs_and_symlinks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

        def fake_repo_init(repo_dir: str, url: str, revision: str, manifest_path: str, repo_rev: str = "") -> None:
            write_manifest_for_sync(Path(repo_dir), sub_path=manifest_path)

        def fake_repo_sync(repo_dir: str, **kwargs) -> None:
            packages = Path(repo_dir) / ".packages" / "pkg-a"
            packages.mkdir(parents=True, exist_ok=True)
            (packages / "file.txt").write_text("content")

        with (
            patch("mpm_cli.repo.repo_init", side_effect=fake_repo_init),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=fake_repo_sync),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert (store / ".mpm-data" / "sources" / "build").is_dir()
        assert (store / ".packages" / "pkg-a").is_symlink()
        assert not (store / ".gitignore").exists()

    def test_two_sources_aggregate_without_collision(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _isolated_store(monkeypatch, tmp_path / "home")
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_alpha_URL=https://example.com/alpha.git\n"
                "MPM_SOURCE_alpha_REF=main\n"
                "MPM_SOURCE_alpha_PATH=meta.xml\n"
                "MPM_SOURCE_alpha_NAME=alpha\n"
                "MPM_SOURCE_alpha_GITBASE=https://example.com\n"
                "MPM_SOURCE_bravo_URL=https://example.com/bravo.git\n"
                "MPM_SOURCE_bravo_REF=main\n"
                "MPM_SOURCE_bravo_PATH=meta.xml\n"
                "MPM_SOURCE_bravo_NAME=bravo\n"
                "MPM_SOURCE_bravo_GITBASE=https://example.com\n"
            ),
        )

        init_calls: list[str] = []
        sync_calls: list[str] = []

        def fake_repo_init(repo_dir: str, url: str, revision: str, manifest_path: str, repo_rev: str = "") -> None:
            init_calls.append(repo_dir)
            write_manifest_for_sync(Path(repo_dir), sub_path=manifest_path)

        def fake_repo_sync(repo_dir: str, **kwargs) -> None:
            sync_calls.append(repo_dir)
            source_name = Path(repo_dir).name
            packages = Path(repo_dir) / ".packages" / f"pkg-{source_name}"
            packages.mkdir(parents=True, exist_ok=True)

        with (
            patch("mpm_cli.repo.repo_init", side_effect=fake_repo_init),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=fake_repo_sync),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert len(init_calls) == 2
        assert len(sync_calls) == 2
        assert (store / ".packages" / "pkg-alpha").is_symlink()
        assert (store / ".packages" / "pkg-bravo").is_symlink()

    def test_collision_detection_exits(self, tmp_path: Path, make_install_args) -> None:
        mpmenv = _write_mpmenv(
            tmp_path / ".mpm",
            (
                "MPM_SOURCE_alpha_URL=https://example.com/alpha.git\n"
                "MPM_SOURCE_alpha_REF=main\n"
                "MPM_SOURCE_alpha_PATH=meta.xml\n"
                "MPM_SOURCE_alpha_NAME=alpha\n"
                "MPM_SOURCE_alpha_GITBASE=https://example.com\n"
                "MPM_SOURCE_bravo_URL=https://example.com/bravo.git\n"
                "MPM_SOURCE_bravo_REF=main\n"
                "MPM_SOURCE_bravo_PATH=meta.xml\n"
                "MPM_SOURCE_bravo_NAME=bravo\n"
                "MPM_SOURCE_bravo_GITBASE=https://example.com\n"
            ),
        )

        def fake_repo_sync(repo_dir: str, **kwargs) -> None:
            packages = Path(repo_dir) / ".packages" / "collider"
            packages.mkdir(parents=True, exist_ok=True)

        args = make_install_args(mpmenv.resolve())
        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=fake_repo_sync),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _install_run(args)
        assert exc_info.value.code == 1

    def test_gitignore_preexisting_left_unchanged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Install leaves a pre-existing store ``.gitignore`` untouched for a non-git store.

        The store here is an isolated temp dir that is not inside a git working
        tree, so install writes no ``.gitignore`` and must not append to, rewrite,
        or otherwise modify one a caller placed there beforehand.
        """
        store = _isolated_store(monkeypatch, tmp_path / "home")

        preexisting = ".packages/\n"
        (store / ".gitignore").write_text(preexisting)
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

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert (store / ".gitignore").read_text() == preexisting
