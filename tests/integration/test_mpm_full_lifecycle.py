"""Full lifecycle integration tests for mpm install/clean scenarios (10 tests).

Covers end-to-end mpm lifecycle scenarios:
  - Install -> clean roundtrip (clean state after full cycle)
  - Multi-source installation (repo + marketplace sources)
  - Source collision detection (duplicate project names across sources)
  - Auto-discovery workflow (detect manifests, install, verify)
  - Recovery from partial failure (failed sync mid-install)
  - Re-install over existing installation (idempotency)
  - Filesystem state at each lifecycle stage
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mpm_cli.core.clean import clean
from mpm_cli.core.discover import find_mpmenv
from mpm_cli.core.install import install


def _store_base() -> Path:
    """Return the shared artifact store base (``<MPM_HOME>/store``).

    install()/clean() create and remove ``.packages/`` and ``.mpm-data/``
    under the shared store, not beside the project ``.mpm``. install() writes
    a ``.gitignore`` under the store only when the store is inside a git working
    tree; the isolated per-test store here is not, so no ``.gitignore`` appears.
    The ``_isolate_mpm_home`` autouse fixture points MPM_HOME at a fresh
    per-test temporary directory.
    """
    return Path(os.environ["MPM_HOME"]) / "store"


def _write_mpmenv(directory: Path, content: str) -> Path:
    """Write a .mpm file in directory and return its path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(content)
    return mpmenv


def _single_source_content(name: str = "primary") -> str:
    """Return minimal .mpm content for a single source."""
    return (
        f"MPM_SOURCE_{name}_URL=https://example.com/{name}.git\n"
        f"MPM_SOURCE_{name}_REF=main\n"
        f"MPM_SOURCE_{name}_PATH=meta.xml\n"
        f"MPM_SOURCE_{name}_NAME={name}\n"
        f"MPM_SOURCE_{name}_GITBASE=https://example.com\n"
    )


def _two_source_content() -> str:
    """Return .mpm content for two independent sources."""
    return (
        "MPM_SOURCE_repo_URL=https://example.com/repo.git\n"
        "MPM_SOURCE_repo_REF=main\n"
        "MPM_SOURCE_repo_PATH=meta.xml\n"
        "MPM_SOURCE_repo_NAME=repo\n"
        "MPM_SOURCE_repo_GITBASE=https://example.com\n"
        "MPM_SOURCE_marketplace_URL=https://example.com/marketplace.git\n"
        "MPM_SOURCE_marketplace_REF=main\n"
        "MPM_SOURCE_marketplace_PATH=marketplace.xml\n"
        "MPM_SOURCE_marketplace_NAME=marketplace\n"
        "MPM_SOURCE_marketplace_GITBASE=https://example.com\n"
    )


def _install_with_synced_packages(mpmenv: Path, packages_by_source: dict[str, list[str]]) -> None:
    """Run install() with a fake repo_sync that creates .packages/ entries.

    Args:
        mpmenv: Path to the .mpm configuration file.
        packages_by_source: Mapping of source name to list of package names to create.
    """

    def fake_repo_sync(repo_dir: str, **kwargs) -> None:
        repo_path = Path(repo_dir)
        pkg_dir = repo_path / ".packages"

        source_name = repo_path.name
        for pkg_name in packages_by_source.get(source_name, []):
            tool_dir = pkg_dir / pkg_name
            tool_dir.mkdir(parents=True, exist_ok=True)
            (tool_dir / f"{pkg_name}.sh").write_text(f"#!/bin/sh\necho {pkg_name}\n")

    with (
        patch("mpm_cli.repo.repo_init"),
        patch("mpm_cli.repo.repo_envsubst"),
        patch("mpm_cli.repo.repo_sync", side_effect=fake_repo_sync),
    ):
        install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")


@pytest.mark.integration
class TestInstallCleanRoundtripLifecycle:
    """Verify that a full install -> clean roundtrip restores the project to a clean state."""

    def test_roundtrip_filesystem_state_is_clean_after_cycle(self, tmp_path: Path) -> None:
        """After install and clean, no repo-managed artifacts remain on disk.

        Filesystem state after roundtrip:
          - .mpm: present (config file, not managed by repo)
          - .packages/: absent
          - .mpm-data/: absent
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())
        store_base = _store_base()

        _install_with_synced_packages(mpmenv, {"primary": ["tool-x"]})

        assert (store_base / ".packages").is_dir(), ".packages/ must exist after install"
        assert (store_base / ".mpm-data" / "sources" / "primary").is_dir(), (
            ".mpm-data/sources/primary/ must exist after install"
        )

        clean(mpmenv)

        assert not (store_base / ".packages").exists(), ".packages/ must be absent after clean"
        assert not (store_base / ".mpm-data").exists(), ".mpm-data/ must be absent after clean"
        assert mpmenv.is_file(), ".mpm config file must survive the full roundtrip"

    def test_roundtrip_gitignore_survives_clean(self, tmp_path: Path) -> None:
        """A non-git store writes no .gitignore, and clean does not create one.

        install() only writes <store>/.gitignore when the store is inside a git
        working tree. The isolated temp store here is not in a git repo, so no
        .gitignore is written by install, and clean must not create one either.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())
        store_base = _store_base()

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert not (store_base / ".gitignore").exists(), "install() must not write .gitignore under a non-git store"

        clean(mpmenv)

        assert not (store_base / ".gitignore").exists(), "clean must not create a .gitignore under the store"


@pytest.mark.integration
class TestMultiSourceInstallLifecycle:
    """Verify that install handles multiple sources producing disjoint package sets."""

    def test_multi_source_creates_separate_source_dirs(self, tmp_path: Path) -> None:
        """Each source gets its own isolated directory under .mpm-data/sources/.

        Verifies both directories are created and non-overlapping.
        """
        mpmenv = _write_mpmenv(tmp_path, _two_source_content())

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        store_base = _store_base()
        assert (store_base / ".mpm-data" / "sources" / "marketplace").is_dir(), (
            ".mpm-data/sources/marketplace/ must be created for the marketplace source"
        )
        assert (store_base / ".mpm-data" / "sources" / "repo").is_dir(), (
            ".mpm-data/sources/repo/ must be created for the repo source"
        )

    def test_multi_source_repo_init_called_once_per_source(self, tmp_path: Path) -> None:
        """repo_init is invoked exactly once for each declared source.

        With two sources (marketplace, repo), repo_init must be called twice.
        """
        mpmenv = _write_mpmenv(tmp_path, _two_source_content())

        with (
            patch("mpm_cli.repo.repo_init") as mock_init,
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert mock_init.call_count == 2, (
            f"repo_init must be called once per source (2 sources), but was called {mock_init.call_count} times"
        )

    def test_multi_source_packages_aggregated_into_packages_dir(self, tmp_path: Path) -> None:
        """Packages from all sources are symlinked into the top-level .packages/.

        Each source contributes a unique package; both appear in .packages/.
        """
        mpmenv = _write_mpmenv(tmp_path, _two_source_content())

        _install_with_synced_packages(
            mpmenv,
            {"marketplace": ["plugin-a"], "repo": ["tool-b"]},
        )

        store_base = _store_base()
        assert (store_base / ".packages" / "plugin-a").is_symlink(), (
            "plugin-a from marketplace source must be symlinked in .packages/"
        )
        assert (store_base / ".packages" / "tool-b").is_symlink(), (
            "tool-b from repo source must be symlinked in .packages/"
        )


@pytest.mark.integration
class TestSourceCollisionDetection:
    """Verify that install propagates ValueError when two sources produce the same package name."""

    def test_collision_propagates_value_error(self, tmp_path: Path) -> None:
        """When two sources declare a package with the same name, install propagates ValueError.

        Filesystem state at error: source dirs created, .packages/ partially populated.
        """
        mpmenv = _write_mpmenv(tmp_path, _two_source_content())

        def fake_repo_sync_collision(repo_dir: str, **kwargs) -> None:
            pkg_dir = Path(repo_dir) / ".packages" / "shared-tool"
            pkg_dir.mkdir(parents=True, exist_ok=True)
            (pkg_dir / "tool.sh").write_text("#!/bin/sh\necho shared\n")

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=fake_repo_sync_collision),
        ):
            with pytest.raises(ValueError, match="Package collision"):
                install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")


@pytest.mark.integration
class TestAutoDiscoveryWorkflow:
    """Verify the auto-discovery -> install -> verify workflow."""

    def test_auto_discovery_finds_mpmenv_and_install_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Discover .mpm via find_mpmenv, pass it to install(), verify artifacts.

        Workflow:
          1. Write .mpm in tmp_path
          2. Set cwd to a subdirectory
          3. find_mpmenv() resolves to the parent's .mpm
          4. install() creates .mpm-data/ under the shared store
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())
        store_base = _store_base()
        subdir = tmp_path / "workspace" / "project"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        discovered = find_mpmenv(start_dir=subdir)

        assert discovered == mpmenv.resolve(), f"find_mpmenv must discover {mpmenv.resolve()}, but found {discovered}"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(discovered, lock_file_path=discovered.parent / ".mpm.lock")

        assert (store_base / ".mpm-data" / "sources" / "primary").is_dir(), (
            "install() must create .mpm-data/sources/primary/ under the shared store"
        )
        assert not (store_base / ".gitignore").exists(), "install() must not write .gitignore under a non-git store"


@pytest.mark.integration
class TestPartialFailureRecovery:
    """Verify that a failed sync mid-install propagates the error and clean is re-runnable."""

    def test_failed_sync_raises_repo_command_error(self, tmp_path: Path) -> None:
        """When repo_sync raises RepoCommandError, install propagates it immediately.

        The first source's directory is created before sync fails.
        """
        from mpm_cli.repo import RepoCommandError

        mpmenv = _write_mpmenv(tmp_path, _single_source_content())

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=RepoCommandError("sync failed: network error")),
        ):
            with pytest.raises(RepoCommandError, match="sync failed: network error"):
                install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

    def test_clean_succeeds_after_partial_install(self, tmp_path: Path) -> None:
        """clean() can remove partial install artifacts left by a failed install.

        After a failed install, source dirs may exist but packages may be incomplete.
        clean() must not raise and must remove all managed dirs.
        """
        from mpm_cli.repo import RepoCommandError

        mpmenv = _write_mpmenv(tmp_path, _single_source_content())

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=RepoCommandError("sync failed: timeout")),
        ):
            with pytest.raises(RepoCommandError):
                install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        store_base = _store_base()

        assert (store_base / ".mpm-data" / "sources" / "primary").is_dir(), (
            "Source dir must exist after partial install (created before failed sync)"
        )

        clean(mpmenv)

        assert not (store_base / ".mpm-data").exists(), "clean() must remove .mpm-data/ even after a partial install"
        assert not (store_base / ".packages").exists(), "clean() must remove .packages/ even after a partial install"


@pytest.mark.integration
class TestReinstallIdempotency:
    """Verify that running install twice produces the same final state as running it once."""

    def test_reinstall_over_existing_does_not_duplicate_packages(self, tmp_path: Path) -> None:
        """Running install twice over an existing installation must not duplicate symlinks.

        After the second install, .packages/ must contain exactly the same entries
        as after the first install -- no duplicates.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())
        store_base = _store_base()

        _install_with_synced_packages(mpmenv, {"primary": ["tool-alpha", "tool-beta"]})
        first_pkg_names = sorted(p.name for p in (store_base / ".packages").iterdir())

        _install_with_synced_packages(mpmenv, {"primary": ["tool-alpha", "tool-beta"]})
        second_pkg_names = sorted(p.name for p in (store_base / ".packages").iterdir())

        assert first_pkg_names == second_pkg_names, (
            f"Re-installing must not change .packages/ contents: first={first_pkg_names}, second={second_pkg_names}"
        )

    def test_reinstall_gitignore_not_duplicated(self, tmp_path: Path) -> None:
        """Running install twice writes no .gitignore under a non-git store.

        A non-git store writes no .gitignore, so repeated installs must leave
        no .gitignore under the store to duplicate entries into.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")
            assert not (_store_base() / ".gitignore").exists(), (
                "install() must not write .gitignore under a non-git store"
            )
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert not (_store_base() / ".gitignore").exists(), (
            "a second install must not write .gitignore under a non-git store"
        )


@pytest.mark.integration
class TestFilesystemStateAtLifecycleStages:
    """Verify the exact filesystem state at each mpm lifecycle stage."""

    def test_filesystem_state_after_install_stage(self, tmp_path: Path) -> None:
        """After install completes, the expected filesystem artifacts must be present.

        Required artifacts:
          - .mpm: config file (pre-existing, untouched)
          - .mpm-data/sources/<name>/: source workspace directories
          - .packages/: aggregated package symlinks directory
          - .gitignore: absent under a non-git store
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())
        store_base = _store_base()

        _install_with_synced_packages(mpmenv, {"primary": ["some-tool"]})

        assert mpmenv.is_file(), ".mpm config must still exist after install"
        source_dir = store_base / ".mpm-data" / "sources" / "primary"
        assert source_dir.is_dir(), ".mpm-data/sources/primary/ must exist after install"
        assert (store_base / ".packages").is_dir(), ".packages/ must exist after install"
        assert not (store_base / ".gitignore").exists(), "install() must not write .gitignore under a non-git store"
        assert (store_base / ".packages" / "some-tool").is_symlink(), (
            ".packages/some-tool must be a symlink after install"
        )

    def test_filesystem_state_during_multi_source_install(self, tmp_path: Path) -> None:
        """After multi-source install, both source workspaces and all packages are present.

        With sources 'marketplace' and 'repo', each producing one package:
          - .mpm-data/sources/marketplace/ exists
          - .mpm-data/sources/repo/ exists
          - .packages/plugin-mp is a symlink from marketplace
          - .packages/tool-repo is a symlink from repo
        """
        mpmenv = _write_mpmenv(tmp_path, _two_source_content())

        _install_with_synced_packages(
            mpmenv,
            {"marketplace": ["plugin-mp"], "repo": ["tool-repo"]},
        )

        store_base = _store_base()
        assert (store_base / ".mpm-data" / "sources" / "marketplace").is_dir()
        assert (store_base / ".mpm-data" / "sources" / "repo").is_dir()
        assert (store_base / ".packages" / "plugin-mp").is_symlink()
        assert (store_base / ".packages" / "tool-repo").is_symlink()

    def test_filesystem_state_after_clean_stage(self, tmp_path: Path) -> None:
        """After clean completes, repo-managed artifacts are absent; config is preserved.

        Expected post-clean state:
          - .mpm: present
          - .packages/: absent
          - .mpm-data/: absent
          - .gitignore: absent (never written under a non-git store)
          - user-created files: present and unmodified
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content())
        store_base = _store_base()
        user_script = tmp_path / "build.sh"
        user_script.write_text("#!/bin/sh\necho build\n")

        _install_with_synced_packages(mpmenv, {"primary": ["some-tool"]})
        clean(mpmenv)

        assert mpmenv.is_file(), ".mpm must survive clean"
        assert not (store_base / ".packages").exists(), ".packages/ must be absent after clean"
        assert not (store_base / ".mpm-data").exists(), ".mpm-data/ must be absent after clean"
        assert not (store_base / ".gitignore").exists(), (
            "no .gitignore is written under a non-git store, and clean must not create one"
        )
        assert user_script.is_file(), "user files must survive clean unmodified"
        assert user_script.read_text() == "#!/bin/sh\necho build\n"
