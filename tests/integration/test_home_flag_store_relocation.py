"""Integration tests for the shared MPM_HOME store under item 12.

Two end-to-end install behaviors are asserted:

1. The removed ``MPM_WORKSPACE_DIR`` and ``MPM_CACHE_DIR`` env vars have NO
   effect: with them set to junk paths, ``install`` still places ``.packages/``
   and ``.mpm-data/`` under ``<MPM_HOME>/store`` and never touches the junk
   paths or the project directory.

2. The ``--home`` global flag, threaded through ``cli.main`` ->
   ``_apply_global_flags`` -> ``MPM_HOME`` env, relocates the store to the
   flag path even when ``MPM_HOME`` env points elsewhere (precedence
   flag > env). Artifacts land under ``<flag-home>/store``, not under the env
   home and not beside ``.mpm``.

Repo / network operations are patched to no-ops so the install runs hermetically
and deterministically.
"""

import pathlib
from unittest.mock import patch

import pytest

from mpm_cli.cli import main
from mpm_cli.constants import MPM_HOME_STORE_SUBDIR
from mpm_cli.core.include_walker import IncludeTree
from mpm_cli.core.install import _RefResolution, install


_FAKE_SHA = "a" * 40
_FAKE_REF_RESOLUTION = _RefResolution(sha=_FAKE_SHA, resolved_ref="refs/heads/main")


def _store_dir(mpm_home: pathlib.Path) -> pathlib.Path:
    """Return the artifact store directory for a given MPM_HOME root."""
    return mpm_home / MPM_HOME_STORE_SUBDIR


def _url_mpmenv(directory: pathlib.Path, source_name: str = "build") -> pathlib.Path:
    """Write a minimal URL-based .mpm file and return its resolved path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        f"MPM_SOURCE_{source_name}_URL=https://example.com/{source_name}.git\n"
        f"MPM_SOURCE_{source_name}_REF=main\n"
        f"MPM_SOURCE_{source_name}_PATH=meta.xml\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://example.com\n",
        encoding="utf-8",
    )
    return mpmenv.resolve()


def _install_patches() -> tuple:
    """Return the context-manager patches that make install() hermetic."""
    return (
        patch("mpm_cli.repo.repo_init"),
        patch("mpm_cli.repo.repo_envsubst"),
        patch("mpm_cli.repo.repo_sync"),
        patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=_FAKE_REF_RESOLUTION),
        patch(
            "mpm_cli.core.install._walk_includes",
            return_value=IncludeTree(path=pathlib.Path("meta.xml")),
        ),
    )


def _run_install_direct(mpmenv: pathlib.Path, lock_path: pathlib.Path) -> None:
    """Run install() directly with repo operations patched to no-ops."""
    p_init, p_env, p_sync, p_ref, p_walk = _install_patches()
    with p_init, p_env, p_sync, p_ref, p_walk:
        install(mpmenv, lock_file_path=lock_path)


@pytest.mark.integration
class TestRemovedVarsHaveNoEffect:
    """MPM_WORKSPACE_DIR / MPM_CACHE_DIR are removed: junk values do nothing."""

    def test_junk_removed_vars_do_not_relocate_store(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Artifacts land under <MPM_HOME>/store regardless of the removed vars."""
        mpm_home = tmp_path / "mpm_home"
        store = _store_dir(mpm_home)
        junk_workspace = tmp_path / "junk_workspace"
        junk_cache = tmp_path / "junk_cache"
        project = tmp_path / "project"
        project.mkdir()

        monkeypatch.setenv("MPM_HOME", str(mpm_home))
        monkeypatch.setenv("MPM_WORKSPACE_DIR", str(junk_workspace))
        monkeypatch.setenv("MPM_CACHE_DIR", str(junk_cache))

        mpmenv = _url_mpmenv(project)
        lock_path = project / ".mpm.lock"

        _run_install_direct(mpmenv, lock_path)

        assert (store / ".mpm-data").exists(), "install must place .mpm-data/ under <MPM_HOME>/store"
        assert (store / ".packages").exists(), "install must place .packages/ under <MPM_HOME>/store"
        assert not junk_workspace.exists(), "MPM_WORKSPACE_DIR is removed and must have no effect"
        assert not junk_cache.exists(), "MPM_CACHE_DIR is removed and must have no effect"
        assert not (project / ".packages").exists(), "install must NOT write artifacts beside .mpm"
        assert not (project / ".mpm-data").exists(), "install must NOT write artifacts beside .mpm"


@pytest.mark.integration
class TestHomeFlagRelocatesStoreEndToEnd:
    """The --home flag (via cli.main) wins over MPM_HOME env for the store path."""

    def test_home_flag_wins_over_env_for_store(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """mpm --home <flag> install places artifacts under <flag>/store, not <env>/store."""
        flag_home = tmp_path / "flag_home"
        env_home = tmp_path / "env_home"
        flag_store = _store_dir(flag_home)
        env_store = _store_dir(env_home)
        project = tmp_path / "project"
        project.mkdir()

        monkeypatch.setenv("MPM_HOME", str(env_home))
        monkeypatch.setenv("MPM_SKIP_UPDATE_CHECK", "1")

        mpmenv = _url_mpmenv(project)

        p_init, p_env, p_sync, p_ref, p_walk = _install_patches()
        with p_init, p_env, p_sync, p_ref, p_walk:
            main(["--home", str(flag_home), "install", str(mpmenv)])

        assert (flag_store / ".mpm-data").exists(), "--home must relocate the store to the flag path"
        assert (flag_store / ".packages").exists(), "--home must relocate the store to the flag path"
        assert not env_store.exists(), "the MPM_HOME env store must be unused when --home is given"
        assert not (project / ".packages").exists(), "install must NOT write artifacts beside .mpm"
