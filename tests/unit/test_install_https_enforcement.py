"""Unit tests for HTTPS enforcement wiring in the install module.

Tests that _run_install calls _enforce_remote_url_policy with the correct
arguments derived from the MPM_ALLOW_INSECURE_REMOTES environment variable.

AC-TEST-001 coverage: wiring test asserting install calls the policy enforcer
with the correct args from env.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

from mpm_cli.core.install import _run_install
from mpm_cli.core.remote_url import InsecureRemoteUrlError


def _write_mpm(directory: pathlib.Path, url: str, scheme: str = "http") -> pathlib.Path:
    """Write a minimal .mpm file pointing at the given URL.

    Args:
        directory: Directory in which to create the .mpm file.
        url: The source URL to write.
        scheme: Not used -- kept for readability at call sites.

    Returns:
        Absolute path to the written .mpm file.
    """
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        f"MPM_MARKETPLACE_INSTALL=false\n"
        f"MPM_SOURCE_mysource_URL={url}\n"
        f"MPM_SOURCE_mysource_REF=main\n"
        f"MPM_SOURCE_mysource_PATH=repo-specs/manifest.xml\n"
        f"MPM_SOURCE_mysource_NAME=mysource\n"
        f"MPM_SOURCE_mysource_GITBASE=https://example.com\n"
    )
    return mpmenv.resolve()


@pytest.mark.unit
class TestInstallEnforcesHttpsPolicy:
    """Tests that _run_install calls _enforce_remote_url_policy for each source URL."""

    def test_policy_enforcer_called_on_absent_lockfile_path(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_enforce_remote_url_policy is called for each source URL on the absent-lockfile path."""
        monkeypatch.delenv("MPM_ALLOW_INSECURE_REMOTES", raising=False)
        mpmenv = _write_mpm(tmp_path, "https://example.com/repo.git")
        lockfile_path = tmp_path / ".mpm.lock"

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha") as mock_resolve,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
            patch("mpm_cli.core.install._walk_includes") as mock_walk,
            patch("mpm_cli.core.install._include_tree_to_entries", return_value=[]),
            patch("mpm_cli.core.install.aggregate_symlinks", return_value={}),
            patch("mpm_cli.core.install.update_gitignore"),
            patch("mpm_cli.core.install._emit_install_state"),
            patch("mpm_cli.core.install._enforce_remote_url_policy") as mock_policy,
        ):
            from mpm_cli.core.install import _RefResolution

            mock_resolve.return_value = _RefResolution(sha="a" * 40, resolved_ref="refs/heads/main")
            mock_walk.return_value = MagicMock(includes=[])

            _run_install(
                mpmenv_path=mpmenv,
                lockfile_path=lockfile_path,
            )

        mock_policy.assert_called()

    def test_policy_enforcer_called_with_allow_insecure_false_by_default(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When MPM_ALLOW_INSECURE_REMOTES is unset, allow_insecure=False is passed."""
        monkeypatch.delenv("MPM_ALLOW_INSECURE_REMOTES", raising=False)
        mpmenv = _write_mpm(tmp_path, "https://example.com/repo.git")
        lockfile_path = tmp_path / ".mpm.lock"

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha") as mock_resolve,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
            patch("mpm_cli.core.install._walk_includes") as mock_walk,
            patch("mpm_cli.core.install._include_tree_to_entries", return_value=[]),
            patch("mpm_cli.core.install.aggregate_symlinks", return_value={}),
            patch("mpm_cli.core.install.update_gitignore"),
            patch("mpm_cli.core.install._emit_install_state"),
            patch("mpm_cli.core.install._enforce_remote_url_policy") as mock_policy,
        ):
            from mpm_cli.core.install import _RefResolution

            mock_resolve.return_value = _RefResolution(sha="a" * 40, resolved_ref="refs/heads/main")
            mock_walk.return_value = MagicMock(includes=[])

            _run_install(
                mpmenv_path=mpmenv,
                lockfile_path=lockfile_path,
            )

        for c in mock_policy.call_args_list:
            assert c.kwargs.get("allow_insecure") is False or (len(c.args) >= 2 and c.args[1] is False)

    def test_policy_enforcer_called_with_allow_insecure_true_when_env_set(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When MPM_ALLOW_INSECURE_REMOTES=1, allow_insecure=True is passed."""
        monkeypatch.setenv("MPM_ALLOW_INSECURE_REMOTES", "1")
        mpmenv = _write_mpm(tmp_path, "https://example.com/repo.git")
        lockfile_path = tmp_path / ".mpm.lock"

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha") as mock_resolve,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
            patch("mpm_cli.core.install._walk_includes") as mock_walk,
            patch("mpm_cli.core.install._include_tree_to_entries", return_value=[]),
            patch("mpm_cli.core.install.aggregate_symlinks", return_value={}),
            patch("mpm_cli.core.install.update_gitignore"),
            patch("mpm_cli.core.install._emit_install_state"),
            patch("mpm_cli.core.install._enforce_remote_url_policy") as mock_policy,
        ):
            from mpm_cli.core.install import _RefResolution

            mock_resolve.return_value = _RefResolution(sha="a" * 40, resolved_ref="refs/heads/main")
            mock_walk.return_value = MagicMock(includes=[])

            _run_install(
                mpmenv_path=mpmenv,
                lockfile_path=lockfile_path,
            )

        any_true = any(
            c.kwargs.get("allow_insecure") is True or (len(c.args) >= 2 and c.args[1] is True)
            for c in mock_policy.call_args_list
        )
        assert any_true, "Expected at least one call with allow_insecure=True"

    def test_http_url_raises_insecure_error_by_default(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When source URL is HTTP and env var unset, InsecureRemoteUrlError is raised."""
        monkeypatch.delenv("MPM_ALLOW_INSECURE_REMOTES", raising=False)
        mpmenv = _write_mpm(tmp_path, "http://example.com/repo.git")
        lockfile_path = tmp_path / ".mpm.lock"

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha") as mock_resolve,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
            patch("mpm_cli.core.install._walk_includes") as mock_walk,
        ):
            from mpm_cli.core.install import _RefResolution

            mock_resolve.return_value = _RefResolution(sha="a" * 40, resolved_ref="refs/heads/main")
            mock_walk.return_value = MagicMock(includes=[])

            with pytest.raises(InsecureRemoteUrlError):
                _run_install(
                    mpmenv_path=mpmenv,
                    lockfile_path=lockfile_path,
                )

    def test_http_url_allowed_when_env_var_set_to_one(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When source URL is HTTP and MPM_ALLOW_INSECURE_REMOTES=1, no error is raised."""
        monkeypatch.setenv("MPM_ALLOW_INSECURE_REMOTES", "1")
        mpmenv = _write_mpm(tmp_path, "http://example.com/repo.git")
        lockfile_path = tmp_path / ".mpm.lock"

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha") as mock_resolve,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
            patch("mpm_cli.core.install._walk_includes") as mock_walk,
            patch("mpm_cli.core.install._include_tree_to_entries", return_value=[]),
            patch("mpm_cli.core.install.aggregate_symlinks", return_value={}),
            patch("mpm_cli.core.install.update_gitignore"),
            patch("mpm_cli.core.install._emit_install_state"),
        ):
            from mpm_cli.core.install import _RefResolution

            mock_resolve.return_value = _RefResolution(sha="a" * 40, resolved_ref="refs/heads/main")
            mock_walk.return_value = MagicMock(includes=[])

            _run_install(
                mpmenv_path=mpmenv,
                lockfile_path=lockfile_path,
            )


@pytest.mark.unit
class TestLockfileConsistentMissingSourceRaisesConsistencyError:
    """Under LOCKFILE_CONSISTENT state, a source absent from the lockfile is a hard error."""

    def test_source_missing_from_lockfile_raises_consistency_error(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If a .mpm source has no lockfile entry under LOCKFILE_CONSISTENT, a fail-fast error is raised.

        This guards the mpm_hash consistency invariant: if the hash matched but a source
        is absent from the lockfile, .mpm.lock was edited out of sync with .mpm. A hard
        ``LockfileConsistencyError`` (no ``BUG:`` string) is raised, preferable to silently
        falling back to the .mpm URL.
        """
        monkeypatch.delenv("MPM_ALLOW_INSECURE_REMOTES", raising=False)

        mpmenv = _write_mpm(tmp_path, "https://example.com/repo.git")
        lockfile_path = tmp_path / ".mpm.lock"

        from mpm_cli.core.install import _mpm_hash
        from mpm_cli.core.lockfile import (
            CURRENT_SCHEMA_VERSION,
            Lockfile,
            LockfileConsistencyError,
            write_lockfile,
        )

        mpm_hash_val = _mpm_hash(mpmenv)
        lf = Lockfile(
            schema_version=CURRENT_SCHEMA_VERSION,
            generated_at="2026-01-01T00:00:00Z",
            generator="mpm-cli/test",
            mpm_hash=mpm_hash_val,
            sources=[],
        )
        write_lockfile(lf, lockfile_path)

        with pytest.raises(LockfileConsistencyError) as excinfo:
            _run_install(
                mpmenv_path=mpmenv,
                lockfile_path=lockfile_path,
            )
        rendered = str(excinfo.value)
        assert "mysource" in rendered
        assert "missing from .mpm.lock" in rendered
        assert "BUG:" not in rendered
