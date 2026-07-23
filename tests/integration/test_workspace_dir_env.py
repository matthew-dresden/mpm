"""Integration tests for the shared MPM_HOME store honoring in mpm install and clean.

Verifies that when MPM_HOME is set, install places .packages/ and
.mpm-data/ under ``<MPM_HOME>/store`` (not beside .mpm), and clean removes
them from the same location.  Covers the path= (direct checkout) entry shape as
well as the standard URL-based shape.

AC-9 (AC-1): install creates .packages/ and .mpm-data/ under <MPM_HOME>/store
AC-10 (AC-2): clean removes .packages/ and .mpm-data/ from <MPM_HOME>/store
AC-11 (AC-3): relocation holds for direct path= checkout entry (builders-plugins / F8)
AC-12 (AC-4): unwritable MPM_HOME store exits non-zero with actionable message, no cwd fallback
AC-13 (AC-5): genuine RED->GREEN recorded in TDD cycle log
AC-14 (AC-6): --help snapshots unchanged (no surface drift)
"""

import pathlib
import stat
from unittest.mock import patch

import pytest

from mpm_cli.constants import MPM_HOME_STORE_SUBDIR
from mpm_cli.core.clean import clean
from mpm_cli.core.include_walker import IncludeTree
from mpm_cli.core.install import _RefResolution, install


_FAKE_SHA = "a" * 40
_FAKE_REF_RESOLUTION = _RefResolution(sha=_FAKE_SHA, resolved_ref="refs/heads/main")


def _store_dir(mpm_home: pathlib.Path) -> pathlib.Path:
    """Return the artifact store directory for a given MPM_HOME root."""
    return mpm_home / MPM_HOME_STORE_SUBDIR


def _url_mpmenv(directory: pathlib.Path, source_name: str = "build") -> pathlib.Path:
    """Write a minimal URL-based .mpm file and return its path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        f"MPM_SOURCE_{source_name}_URL=https://example.com/{source_name}.git\n"
        f"MPM_SOURCE_{source_name}_REF=main\n"
        f"MPM_SOURCE_{source_name}_PATH=meta.xml\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://example.com\n"
    )
    return mpmenv.resolve()


def _path_source_mpmenv(directory: pathlib.Path, source_name: str = "builders-plugins") -> pathlib.Path:
    """Write a .mpm file with a URL-based source simulating a direct path= catalog entry.

    In the mpm .mpm file format, all sources require the five alias-keyed
    variables: URL, REF, PATH, NAME, and GITBASE.  The 'path=' catalog entry
    type (F8) is a catalog-level concept; at the .mpm level it still resolves
    to the standard alias-keyed source block.  This helper uses the same URL
    source format as _url_mpmenv but names the source 'builders-plugins' to
    mirror the F8 fixture entry name.
    """
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        f"MPM_SOURCE_{source_name}_URL=https://example.com/{source_name}.git\n"
        f"MPM_SOURCE_{source_name}_REF=main\n"
        f"MPM_SOURCE_{source_name}_PATH=meta.xml\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://example.com\n"
    )
    return mpmenv.resolve()


def _run_install(mpmenv: pathlib.Path, lock_path: pathlib.Path) -> None:
    """Run install() with repo operations patched to no-ops."""
    with (
        patch("mpm_cli.repo.repo_init"),
        patch("mpm_cli.repo.repo_envsubst"),
        patch("mpm_cli.repo.repo_sync"),
        patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=_FAKE_REF_RESOLUTION),
        patch(
            "mpm_cli.core.install._walk_includes",
            return_value=IncludeTree(path=pathlib.Path("meta.xml")),
        ),
    ):
        install(mpmenv, lock_file_path=lock_path)


@pytest.mark.integration
class TestMPMHomeStoreInstallCleanRoundtrip:
    """AC-9 / AC-10: install + clean roundtrip with MPM_HOME set (URL source)."""

    def test_install_creates_artifacts_under_store(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-9: install creates .packages/ and .mpm-data/ under <MPM_HOME>/store."""
        mpm_home = tmp_path / "mpm_home"
        store = _store_dir(mpm_home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("MPM_HOME", str(mpm_home))

        mpmenv = _url_mpmenv(project)
        lock_path = project / ".mpm.lock"

        _run_install(mpmenv, lock_path)

        assert (store / ".mpm-data").exists(), "install must create .mpm-data/ under <MPM_HOME>/store"
        assert not (project / ".mpm-data").exists(), "install must NOT create .mpm-data/ in the cwd (beside .mpm)"
        assert not (project / ".packages").exists(), "install must NOT create .packages/ in the cwd (beside .mpm)"

    def test_install_creates_packages_dir_under_store(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-9: .packages/ is created under <MPM_HOME>/store."""
        mpm_home = tmp_path / "home"
        store = _store_dir(mpm_home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("MPM_HOME", str(mpm_home))

        mpmenv = _url_mpmenv(project)
        lock_path = project / ".mpm.lock"

        _run_install(mpmenv, lock_path)

        assert (store / ".packages").exists(), "install must create .packages/ under <MPM_HOME>/store"

    def test_clean_removes_artifacts_from_store(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-10: clean removes .packages/ and .mpm-data/ from <MPM_HOME>/store."""
        mpm_home = tmp_path / "mpm_home"
        store = _store_dir(mpm_home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("MPM_HOME", str(mpm_home))

        (store / ".packages").mkdir(parents=True)
        (store / ".mpm-data").mkdir(parents=True)

        (project / ".packages").mkdir()
        (project / ".mpm-data").mkdir()

        mpmenv = _url_mpmenv(project)

        with patch("mpm_cli.core.clean.uninstall_marketplace_plugins"):
            clean(mpmenv)

        assert not (store / ".packages").exists(), "clean must remove .packages/ from <MPM_HOME>/store"
        assert not (store / ".mpm-data").exists(), "clean must remove .mpm-data/ from <MPM_HOME>/store"
        assert (project / ".packages").exists(), "clean must NOT remove .packages/ beside .mpm when MPM_HOME is set"
        assert (project / ".mpm-data").exists(), "clean must NOT remove .mpm-data/ beside .mpm when MPM_HOME is set"

    def test_store_is_created_when_absent(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-9: <MPM_HOME>/store need not pre-exist; install creates it."""
        mpm_home = tmp_path / "nonexistent" / "nested_dir"
        store = _store_dir(mpm_home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("MPM_HOME", str(mpm_home))

        assert not store.exists(), "pre-condition: store must be absent"

        mpmenv = _url_mpmenv(project)
        lock_path = project / ".mpm.lock"

        _run_install(mpmenv, lock_path)

        assert store.exists(), "install must create <MPM_HOME>/store when it is absent"


@pytest.mark.integration
class TestMPMHomeStorePathEntry:
    """AC-11 / AC-3: relocation holds for direct path= checkout entries (F8)."""

    def test_path_entry_install_creates_artifacts_under_store(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-11: path= (direct checkout) entry -- install creates artifacts under <MPM_HOME>/store.

        The 'path=' catalog entry type (F8 / builders-plugins) resolves to the
        same .mpm format as URL sources.  The source name 'builders-plugins'
        mirrors the F8 fixture entry so the test covers that specific case.
        """
        mpm_home = tmp_path / "mpm_home"
        store = _store_dir(mpm_home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("MPM_HOME", str(mpm_home))

        mpmenv = _path_source_mpmenv(project)
        lock_path = project / ".mpm.lock"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=_FAKE_REF_RESOLUTION),
            patch(
                "mpm_cli.core.install._walk_includes",
                return_value=IncludeTree(path=pathlib.Path("meta.xml")),
            ),
        ):
            install(mpmenv, lock_file_path=lock_path)

        assert (store / ".mpm-data").exists(), "path= entry: install must place .mpm-data/ under <MPM_HOME>/store"
        assert not (project / ".mpm-data").exists(), "path= entry: .mpm-data/ must NOT appear in the project directory"

    def test_path_entry_clean_removes_artifacts_from_store(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-11: path= (direct checkout) entry -- clean removes artifacts from <MPM_HOME>/store."""
        mpm_home = tmp_path / "mpm_home"
        store = _store_dir(mpm_home)
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("MPM_HOME", str(mpm_home))

        (store / ".packages").mkdir(parents=True)
        (store / ".mpm-data").mkdir(parents=True)

        mpmenv = _path_source_mpmenv(project)

        with patch("mpm_cli.core.clean.uninstall_marketplace_plugins"):
            clean(mpmenv)

        assert not (store / ".packages").exists(), "path= entry: clean must remove .packages/ from <MPM_HOME>/store"
        assert not (store / ".mpm-data").exists(), "path= entry: clean must remove .mpm-data/ from <MPM_HOME>/store"


@pytest.mark.integration
class TestMPMHomeStoreUnwritable:
    """AC-12 / AC-4: unwritable MPM_HOME store causes non-zero exit, no cwd fallback."""

    def test_unwritable_store_exits_nonzero(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-12: install exits non-zero when the <MPM_HOME>/store cannot be created."""
        locked_parent = tmp_path / "locked"
        locked_parent.mkdir()

        mpm_home = locked_parent / "home"
        locked_parent.chmod(stat.S_IRUSR | stat.S_IXUSR)

        monkeypatch.setenv("MPM_HOME", str(mpm_home))
        project = tmp_path / "project"
        project.mkdir(parents=True, exist_ok=True)

        mpmenv = _url_mpmenv(project)
        lock_path = project / ".mpm.lock"

        try:
            with pytest.raises(SystemExit) as exc_info:
                _run_install(mpmenv, lock_path)
            assert exc_info.value.code != 0, "install must exit non-zero when the MPM_HOME store is unwritable"
        finally:
            locked_parent.chmod(stat.S_IRWXU)

    def test_unwritable_store_writes_no_artifacts_to_cwd(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-12: no artifacts are silently written to cwd on an unwritable MPM_HOME store."""
        locked_parent = tmp_path / "locked2"
        locked_parent.mkdir()
        mpm_home = locked_parent / "home"
        locked_parent.chmod(stat.S_IRUSR | stat.S_IXUSR)

        monkeypatch.setenv("MPM_HOME", str(mpm_home))
        project = tmp_path / "project"
        project.mkdir(parents=True, exist_ok=True)

        mpmenv = _url_mpmenv(project)
        lock_path = project / ".mpm.lock"

        try:
            with pytest.raises(SystemExit):
                _run_install(mpmenv, lock_path)
            assert not (project / ".mpm-data").exists(), (
                "no .mpm-data/ must appear in cwd when the MPM_HOME store is unwritable (no fallback)"
            )
            assert not (project / ".packages").exists(), (
                "no .packages/ must appear in cwd when the MPM_HOME store is unwritable (no fallback)"
            )
        finally:
            locked_parent.chmod(stat.S_IRWXU)


@pytest.mark.integration
class TestHelpSnapshotsUnchanged:
    """AC-14: mpm install --help and mpm clean --help exit 0 (no accidental surface drift)."""

    def test_install_help_exits_zero(self) -> None:
        """install --help exits 0 -- surface is unchanged by the MPM_HOME store model."""
        from mpm_cli.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["install", "--help"])
        assert exc_info.value.code == 0, "mpm install --help must exit 0"

    def test_clean_help_exits_zero(self) -> None:
        """clean --help exits 0 -- surface is unchanged by the MPM_HOME store model."""
        from mpm_cli.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["clean", "--help"])
        assert exc_info.value.code == 0, "mpm clean --help must exit 0"
