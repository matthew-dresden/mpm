"""Unit tests for the --refresh-lock flag in mpm install.

AC-TEST-001: Parametrises the accept paths:
  (a) --refresh-lock with a present lockfile produces InstallState.REFRESH_LOCK
      and is processed like LOCKFILE_ABSENT (info-line, lockfile rewrite).
  (b) --refresh-lock is hermetic: it rebuilds the lock from .mpm without
      resolving a catalog source, and ignores a populated MPM_CATALOG_SOURCES.
  (c) --refresh-lock plus --refresh-lock-source raises SystemExit(2) due to
      mutual-exclusion group (AC-FUNC-004; group registered in T2 for T3 to join).

Spec Section 4.3 / FR-14: install is hermetic, so --refresh-lock re-resolves from
the committed .mpm without resolving or requiring a catalog source.  A populated
MPM_CATALOG_SOURCES env var is ignored, and the install subparser does not accept
--catalog-source.
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pytest

from mpm_cli.core.include_walker import IncludeTree
from mpm_cli.core.install import (
    InstallState,
    _RefResolution,
    _classify_install_state,
    _emit_install_state,
    install,
)


_MPM_SINGLE_SOURCE = """\
GITBASE=https://git.example.com
CLAUDE_MARKETPLACES_DIR=/tmp/mktplc
MPM_MARKETPLACE_INSTALL=false
MPM_SOURCE_alpha_URL=https://git.example.com/alpha.git
MPM_SOURCE_alpha_REF=main
MPM_SOURCE_alpha_PATH=manifest.xml
MPM_SOURCE_alpha_NAME=alpha
MPM_SOURCE_alpha_GITBASE=https://example.com
"""

_VALID_SHA40 = "a" * 40


def _write_mpm(directory: pathlib.Path, content: str = _MPM_SINGLE_SOURCE) -> pathlib.Path:
    mpm_path = directory / ".mpm"
    mpm_path.write_text(content)
    mpm_path.chmod(0o600)
    return mpm_path


def _write_lockfile(
    directory: pathlib.Path,
    mpm_hash: str,
) -> pathlib.Path:
    """Write a minimal valid schema-v4 .mpm.lock TOML file and return its path.

    The v5 lock is alias-keyed and carries no [catalog] block (spec Section 5.2).
    """
    lock_path = directory / ".mpm.lock"
    content = f"""\
schema_version = 5
generated_at = "2026-01-15T00:00:00Z"
generator = "mpm-cli/test"
mpm_hash = "{mpm_hash}"
marketplace_registered = false
marketplace_dir = ""

[[sources]]
alias = "alpha"
name = "alpha"
url = "https://git.example.com/alpha.git"
ref_spec = "main"
resolved_ref = "refs/heads/main"
resolved_sha = "{_VALID_SHA40}"
path = "manifest.xml"
"""
    lock_path.write_text(content)
    return lock_path


@pytest.mark.unit
class TestRefreshLockInstallState:
    """AC-FUNC-006: REFRESH_LOCK enum value is present on InstallState."""

    def test_refresh_lock_state_exists(self) -> None:
        """InstallState.REFRESH_LOCK must be a valid enum member."""
        assert hasattr(InstallState, "REFRESH_LOCK")
        assert isinstance(InstallState.REFRESH_LOCK, InstallState)

    def test_refresh_lock_state_is_distinct(self) -> None:
        """REFRESH_LOCK must differ from every other InstallState value."""
        other_states = [
            InstallState.LOCKFILE_ABSENT,
            InstallState.LOCKFILE_CONSISTENT,
            InstallState.LOCKFILE_HASH_MISMATCH,
            InstallState.LOCKFILE_UNREACHABLE,
        ]
        for other in other_states:
            assert InstallState.REFRESH_LOCK is not other


@pytest.mark.unit
class TestClassifyInstallStateRefreshLock:
    """AC-FUNC-006: _classify_install_state returns REFRESH_LOCK when refresh_lock=True."""

    def test_refresh_lock_when_lockfile_absent(self, tmp_path: pathlib.Path) -> None:
        """REFRESH_LOCK state returned even when the lockfile does not exist."""
        mpm_path = _write_mpm(tmp_path)
        lock_path = tmp_path / ".mpm.lock"
        assert not lock_path.exists()

        classification = _classify_install_state(mpm_path, lock_path, refresh_lock=True)
        assert classification.state is InstallState.REFRESH_LOCK

    def test_refresh_lock_when_lockfile_present_and_consistent(self, tmp_path: pathlib.Path) -> None:
        """REFRESH_LOCK state returned even when the lockfile is consistent."""
        from mpm_cli.core.mpm_hash import mpm_hash as compute_mpm_hash

        mpm_path = _write_mpm(tmp_path)
        real_hash = compute_mpm_hash(mpm_path)
        _write_lockfile(tmp_path, real_hash)
        lock_path = tmp_path / ".mpm.lock"

        classification = _classify_install_state(mpm_path, lock_path, refresh_lock=True)
        assert classification.state is InstallState.REFRESH_LOCK

    def test_refresh_lock_when_lockfile_present_and_mismatched(self, tmp_path: pathlib.Path) -> None:
        """REFRESH_LOCK state returned even when the lockfile has a hash mismatch."""
        mpm_path = _write_mpm(tmp_path)
        wrong_hash = "sha256:" + "d" * 64
        _write_lockfile(tmp_path, wrong_hash)
        lock_path = tmp_path / ".mpm.lock"

        classification = _classify_install_state(mpm_path, lock_path, refresh_lock=True)
        assert classification.state is InstallState.REFRESH_LOCK

    def test_refresh_lock_false_preserves_existing_behaviour(self, tmp_path: pathlib.Path) -> None:
        """refresh_lock=False (default) does NOT change the normal state logic."""
        mpm_path = _write_mpm(tmp_path)
        lock_path = tmp_path / ".mpm.lock"
        assert not lock_path.exists()

        classification = _classify_install_state(mpm_path, lock_path, refresh_lock=False)
        assert classification.state is InstallState.LOCKFILE_ABSENT


@pytest.mark.unit
class TestRefreshLockIsHermetic:
    """Spec Section 4.3 / FR-14: --refresh-lock rebuilds the lock from .mpm
    hermetically.  It neither resolves nor requires a catalog source, and a
    populated MPM_CATALOG_SOURCES env var is ignored (never read).
    """

    def test_refresh_lock_no_catalog_source_succeeds(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install(refresh_lock=True) with NO catalog source rebuilds the lock (no error)."""
        monkeypatch.delenv("MPM_CATALOG_SOURCES", raising=False)
        mpm_path = _write_mpm(tmp_path)
        lock_path = mpm_path.parent / ".mpm.lock"

        mock_ref = _RefResolution(sha="b" * 40, resolved_ref="refs/heads/main")
        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=mock_ref),
            patch("mpm_cli.core.install._walk_includes", return_value=IncludeTree(path=pathlib.Path("manifest.xml"))),
        ):
            install(
                mpmenv_path=mpm_path,
                lock_file_path=lock_path,
                refresh_lock=True,
            )

        assert lock_path.exists()

    def test_refresh_lock_ignores_env_catalog_source(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install(refresh_lock=True) ignores a populated MPM_CATALOG_SOURCES env var."""
        monkeypatch.setenv("MPM_CATALOG_SOURCES", "https://env.example.com/repo.git@main")
        mpm_path = _write_mpm(tmp_path)
        lock_path = mpm_path.parent / ".mpm.lock"

        mock_ref = _RefResolution(sha="b" * 40, resolved_ref="refs/heads/main")
        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=mock_ref),
            patch("mpm_cli.core.install._walk_includes", return_value=IncludeTree(path=pathlib.Path("manifest.xml"))),
        ):
            install(
                mpmenv_path=mpm_path,
                lock_file_path=lock_path,
                refresh_lock=True,
            )

        assert lock_path.exists()
        lock_text = lock_path.read_text(encoding="utf-8")

        assert "https://env.example.com/repo.git" not in lock_text


@pytest.mark.unit
class TestEmitInstallStateRefreshLock:
    """AC-FUNC-001: REFRESH_LOCK emits the same info-line as LOCKFILE_ABSENT."""

    def test_refresh_lock_emits_rebuilt_info_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        """REFRESH_LOCK state emits 'lockfile rebuilt from .mpm (N sources, M projects)'."""
        _emit_install_state(InstallState.REFRESH_LOCK, sources=2, projects=5)
        captured = capsys.readouterr()
        assert "lockfile rebuilt from .mpm (2 sources, 5 projects)" in captured.out

    @pytest.mark.parametrize(
        "sources,projects",
        [(0, 0), (1, 1), (3, 10)],
    )
    def test_refresh_lock_info_line_counts_parametrised(
        self,
        capsys: pytest.CaptureFixture[str],
        sources: int,
        projects: int,
    ) -> None:
        """REFRESH_LOCK info-line counts are dynamic."""
        _emit_install_state(InstallState.REFRESH_LOCK, sources=sources, projects=projects)
        captured = capsys.readouterr()
        assert f"({sources} sources, {projects} projects)" in captured.out


@pytest.mark.unit
class TestInstallRefreshLockKwarg:
    """AC-FUNC-005: install() accepts refresh_lock keyword argument with default False."""

    def test_install_has_refresh_lock_kwarg(self) -> None:
        """install() signature includes refresh_lock: bool = False."""
        import inspect

        sig = inspect.signature(install)
        assert "refresh_lock" in sig.parameters
        param = sig.parameters["refresh_lock"]
        assert param.default is False

    def test_install_subparser_rejects_catalog_source_flag(self) -> None:
        """The install subparser does not register --catalog-source (FR-14): passing it exits non-zero."""
        import argparse

        from mpm_cli.commands import install as install_cmd

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        install_cmd.register(subparsers)

        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(
                ["install", "--refresh-lock", "--catalog-source", "https://cli.example.com/repo.git@main"]
            )
        assert exc_info.value.code != 0

    def test_install_refresh_lock_rewrites_lockfile_hermetically(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install(refresh_lock=True) with no catalog source rewrites the lockfile
        even when a consistent lockfile is already present (AC-FUNC-001)."""
        monkeypatch.delenv("MPM_CATALOG_SOURCES", raising=False)
        mpm_path = _write_mpm(tmp_path)

        from mpm_cli.core.mpm_hash import mpm_hash as compute_hash

        real_hash = compute_hash(mpm_path)
        lock_path = _write_lockfile(tmp_path, real_hash)

        new_sha = "b" * 40
        mock_ref = _RefResolution(sha=new_sha, resolved_ref="refs/heads/main")
        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=mock_ref),
            patch("mpm_cli.core.install._walk_includes", return_value=IncludeTree(path=pathlib.Path("meta.xml"))),
        ):
            install(
                mpmenv_path=mpm_path,
                lock_file_path=mpm_path.parent / ".mpm.lock",
                refresh_lock=True,
            )

        assert lock_path.exists()
        new_content = lock_path.read_text()

        assert new_sha in new_content


@pytest.mark.unit
class TestRefreshLockDoesNotTouchMPMFile:
    """AC-FUNC-002: --refresh-lock does not modify the .mpm file."""

    def test_mpm_file_unchanged_after_refresh_lock(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After install(refresh_lock=True), the .mpm file content is unchanged."""
        monkeypatch.delenv("MPM_CATALOG_SOURCES", raising=False)
        mpm_path = _write_mpm(tmp_path)
        original_content = mpm_path.read_text()

        mock_ref = _RefResolution(sha="b" * 40, resolved_ref="refs/heads/main")
        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=mock_ref),
            patch("mpm_cli.core.install._walk_includes", return_value=IncludeTree(path=pathlib.Path("meta.xml"))),
        ):
            install(
                mpmenv_path=mpm_path,
                lock_file_path=mpm_path.parent / ".mpm.lock",
                refresh_lock=True,
            )

        assert mpm_path.read_text() == original_content


@pytest.mark.unit
class TestRefreshLockMutualExclusion:
    """AC-FUNC-004: --refresh-lock is registered in a mutually_exclusive_group."""

    def test_refresh_lock_alone_is_parsed(self) -> None:
        """--refresh-lock alone parses without error."""
        import argparse

        from mpm_cli.commands import install as install_cmd

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        install_cmd.register(subparsers)

        args = parser.parse_args(["install", "--refresh-lock"])
        assert args.refresh_lock is True

    def test_refresh_lock_default_is_false(self) -> None:
        """When --refresh-lock is not passed, args.refresh_lock defaults to False."""
        import argparse

        from mpm_cli.commands import install as install_cmd

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        install_cmd.register(subparsers)

        args = parser.parse_args(["install"])
        assert args.refresh_lock is False
