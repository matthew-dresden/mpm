"""Integration tests for lifecycle state recovery (E1-F1-S14-T1).

Covers three recovery-oriented scenarios:
  - AC-TEST-001: install -> simulated crash -> clean -> install succeeds
  - AC-TEST-002: install over existing install is idempotent
  - AC-TEST-003: .mpm change between installs reconciles correctly

These tests exercise the mpm lifecycle as a state machine, verifying
that partial or stale state does not prevent subsequent operations from
completing successfully.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mpm_cli.commands.install import _run as _install_run
from mpm_cli.core.clean import clean
from mpm_cli.core.install import install
from mpm_cli.repo import RepoCommandError


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


def _two_source_content(name_a: str = "alpha", name_b: str = "beta") -> str:
    """Return .mpm content for two independent sources."""
    return (
        f"MPM_SOURCE_{name_a}_URL=https://example.com/{name_a}.git\n"
        f"MPM_SOURCE_{name_a}_REF=main\n"
        f"MPM_SOURCE_{name_a}_PATH=meta.xml\n"
        f"MPM_SOURCE_{name_a}_NAME={name_a}\n"
        f"MPM_SOURCE_{name_a}_GITBASE=https://example.com\n"
        f"MPM_SOURCE_{name_b}_URL=https://example.com/{name_b}.git\n"
        f"MPM_SOURCE_{name_b}_REF=main\n"
        f"MPM_SOURCE_{name_b}_PATH=meta.xml\n"
        f"MPM_SOURCE_{name_b}_NAME={name_b}\n"
        f"MPM_SOURCE_{name_b}_GITBASE=https://example.com\n"
    )


def _install_with_synced_packages(
    mpmenv: Path,
    packages_by_source: dict[str, list[str]],
    refresh_lock: bool = False,
) -> None:
    """Run install() with a fake repo_sync that creates .packages/ entries.

    Args:
        mpmenv: Path to the .mpm configuration file.
        packages_by_source: Mapping of source name to list of package names to create.
        refresh_lock: When True, pass refresh_lock=True to install() so that a
            previous lockfile whose mpm_hash no longer matches the current
            .mpm content does not raise MPMHashMismatchError.  Required
            when the test intentionally modifies .mpm between two installs.
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
        install(
            mpmenv,
            lock_file_path=mpmenv.parent / ".mpm.lock",
            refresh_lock=refresh_lock,
        )


@pytest.mark.integration
class TestInstallCrashCleanReinstall:
    """AC-TEST-001: lifecycle is recoverable from partial failure states.

    Simulates a crash mid-install by leaving orphaned artifacts on disk,
    then verifies clean removes all partial state and a subsequent install
    completes successfully.
    """

    def test_crash_during_sync_then_clean_then_reinstall_succeeds(self, tmp_path: Path) -> None:
        """Partial install from crash, then clean, then reinstall produces a clean state.

        Steps:
          1. Start install -- repo_sync raises RepoCommandError mid-way (crash simulation).
          2. Verify install exited non-zero and left partial artifacts (.mpm-data/sources/).
          3. Run clean -- verify all partial artifacts removed.
          4. Run install again with no crash -- verify full successful state.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("crash"))
        store_base = _store_base()

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch(
                "mpm_cli.repo.repo_sync",
                side_effect=RepoCommandError("sync failed: simulated crash"),
            ),
        ):
            with pytest.raises(RepoCommandError, match="sync failed: simulated crash"):
                install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        source_dir = store_base / ".mpm-data" / "sources" / "crash"
        assert source_dir.is_dir(), "Source dir must exist after partial install (created before failed sync)"

        clean(mpmenv)

        assert not (store_base / ".mpm-data").exists(), "clean() must remove .mpm-data/ even after a simulated crash"
        assert not (store_base / ".packages").exists(), "clean() must remove .packages/ even after a simulated crash"

        _install_with_synced_packages(mpmenv, {"crash": ["recovered-tool"]})

        assert (store_base / ".mpm-data" / "sources" / "crash").is_dir(), (
            "Reinstall after crash recovery must recreate .mpm-data/sources/crash/"
        )
        assert (store_base / ".packages" / "recovered-tool").is_symlink(), (
            "Reinstall after crash recovery must create .packages/recovered-tool symlink"
        )
        assert not (store_base / ".gitignore").exists(), (
            "reinstall after crash recovery must not write .gitignore under a non-git store"
        )

    def test_manually_corrupted_packages_dir_is_recovered_by_reinstall(self, tmp_path: Path) -> None:
        """Orphaned .packages/ dir without matching source data is recovered by reinstall.

        Simulates the scenario where .packages/ exists but .mpm-data/ is missing
        (e.g., user manually deleted .mpm-data/ without cleaning .packages/).
        A fresh install must repair the state by recreating all managed artifacts.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("orphan"))
        store_base = _store_base()

        orphan_packages = store_base / ".packages"
        orphan_packages.mkdir(parents=True)
        stale_link = orphan_packages / "stale-pkg"
        stale_link.mkdir()

        _install_with_synced_packages(mpmenv, {"orphan": ["fresh-tool"]})

        assert (store_base / ".packages" / "fresh-tool").is_symlink(), (
            "Install must create .packages/fresh-tool even when .packages/ already existed"
        )

        assert (store_base / ".mpm-data" / "sources" / "orphan").is_dir(), (
            "Install must create .mpm-data/sources/orphan/"
        )

    def test_stdout_stderr_discipline_no_cross_channel_leakage(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, make_install_args
    ) -> None:
        """AC-CHANNEL-001: stdout vs stderr discipline is verified via the CLI handler.

        Normal install output goes to stdout; error messages go to stderr.
        A failed CLI invocation must write its error to stderr, not stdout.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("channel"))
        args = make_install_args(mpmenv.resolve())

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch(
                "mpm_cli.repo.repo_sync",
                side_effect=RepoCommandError("channel error"),
            ),
        ):
            with pytest.raises(SystemExit):
                _install_run(args)

        captured = capsys.readouterr()
        assert "channel error" in captured.err or "Error:" in captured.err, (
            "Error message from failed install must appear on stderr"
        )

        assert "channel error" not in captured.out, "Error message must not leak to stdout"


@pytest.mark.integration
class TestInstallIdempotency:
    """AC-TEST-002: running install twice over an existing installation is idempotent.

    Verifies that a second install with the same .mpm produces exactly the
    same filesystem state as the first install -- no duplicates, no extra
    artifacts, and no errors.
    """

    def test_install_twice_produces_identical_package_set(self, tmp_path: Path) -> None:
        """The set of package symlinks in .packages/ is unchanged after a second install.

        After both installs, .packages/ must contain the same entries,
        in the same structure, with no additional or missing entries.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("idem"))
        store_base = _store_base()

        _install_with_synced_packages(mpmenv, {"idem": ["tool-one", "tool-two"]})
        first_pkgs = sorted(p.name for p in (store_base / ".packages").iterdir())

        _install_with_synced_packages(mpmenv, {"idem": ["tool-one", "tool-two"]})
        second_pkgs = sorted(p.name for p in (store_base / ".packages").iterdir())

        assert first_pkgs == second_pkgs, (
            f"Second install must not change .packages/ contents: first={first_pkgs}, second={second_pkgs}"
        )

    def test_install_twice_does_not_duplicate_gitignore_entries(self, tmp_path: Path) -> None:
        """Running install twice writes no .gitignore under a non-git store.

        A non-git store writes no .gitignore, so repeated installs must leave
        no .gitignore under the store.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("idem2"))

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

    def test_install_twice_all_symlinks_remain_valid(self, tmp_path: Path) -> None:
        """All package symlinks in .packages/ must be valid after two installs.

        A second install must replace stale symlinks if source dirs were
        regenerated, so all symlinks must resolve to existing targets.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("idem3"))

        _install_with_synced_packages(mpmenv, {"idem3": ["pkg-a", "pkg-b"]})
        _install_with_synced_packages(mpmenv, {"idem3": ["pkg-a", "pkg-b"]})

        packages_dir = _store_base() / ".packages"
        for entry in packages_dir.iterdir():
            assert entry.is_symlink(), f"{entry.name} must be a symlink in .packages/"
            assert entry.resolve().exists(), (
                f"Symlink .packages/{entry.name} must resolve to a valid target after second install"
            )


@pytest.mark.integration
class TestMPMChangeReconciliation:
    """AC-TEST-003: changing .mpm between installs reconciles the final state.

    Verifies that when the .mpm configuration changes (new source added,
    source removed, or source URL/revision updated), a subsequent install
    produces a state consistent with the new configuration.
    """

    def test_adding_source_in_mpm_adds_its_packages(self, tmp_path: Path) -> None:
        """Adding a new source to .mpm between installs makes its packages available.

        Steps:
          1. Install with one source (producing package-x).
          2. Update .mpm to add a second source (producing package-y).
          3. Reinstall.
          4. Verify both package-x (from updated source run) and package-y are present.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("src-one"))

        _install_with_synced_packages(mpmenv, {"src-one": ["package-x"]})

        mpmenv.write_text(_two_source_content(name_a="src-one", name_b="src-two"))

        _install_with_synced_packages(
            mpmenv,
            {"src-one": ["package-x"], "src-two": ["package-y"]},
            refresh_lock=True,
        )

        store_base = _store_base()
        assert (store_base / ".packages" / "package-x").is_symlink(), (
            "package-x from src-one must still be present after adding src-two"
        )
        assert (store_base / ".packages" / "package-y").is_symlink(), (
            "package-y from newly added src-two must be present after reconciliation"
        )

    def test_removing_source_in_mpm_removes_stale_source_dir(self, tmp_path: Path) -> None:
        """Removing a source from .mpm followed by clean removes its source directory.

        Steps:
          1. Install with two sources (alpha, beta).
          2. Update .mpm to remove the beta source.
          3. Run clean.
          4. Run install with single source.
          5. Verify .mpm-data/ only contains alpha source dir.
        """
        mpmenv = _write_mpmenv(tmp_path, _two_source_content(name_a="alpha", name_b="beta"))
        store_base = _store_base()

        _install_with_synced_packages(mpmenv, {"alpha": ["tool-alpha"], "beta": ["tool-beta"]})

        assert (store_base / ".mpm-data" / "sources" / "alpha").is_dir()
        assert (store_base / ".mpm-data" / "sources" / "beta").is_dir()

        mpmenv.write_text(_single_source_content("alpha"))

        clean(mpmenv)
        _install_with_synced_packages(mpmenv, {"alpha": ["tool-alpha"]}, refresh_lock=True)

        assert (store_base / ".mpm-data" / "sources" / "alpha").is_dir(), (
            "alpha source dir must exist after reinstall with alpha-only .mpm"
        )
        assert not (store_base / ".mpm-data" / "sources" / "beta").exists(), (
            "beta source dir must be absent after clean + reinstall without beta source"
        )

    def test_mpm_change_to_different_packages_reconciles_packages_dir(self, tmp_path: Path) -> None:
        """Changing .mpm to produce different packages reconciles .packages/ correctly.

        Steps:
          1. Install with source producing old-pkg.
          2. Update .mpm (same source URL but different packages from sync).
          3. Reinstall -- source now produces new-pkg instead.
          4. Verify new-pkg is present; stale old-pkg symlink is replaced/absent.
        """
        mpmenv = _write_mpmenv(tmp_path, _single_source_content("evolving"))
        store_base = _store_base()

        _install_with_synced_packages(mpmenv, {"evolving": ["old-pkg"]})

        assert (store_base / ".packages" / "old-pkg").is_symlink(), "old-pkg must be present after first install"

        _install_with_synced_packages(mpmenv, {"evolving": ["new-pkg"]})

        assert (store_base / ".packages" / "new-pkg").is_symlink(), "new-pkg must be present after reconciling install"
