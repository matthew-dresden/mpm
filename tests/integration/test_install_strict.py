"""Integration tests for --strict-lock and --strict-drift flags.

AC-TEST-002: Builds a fixture git repo with a branch-shaped source, runs
a baseline install, advances the branch tip on the fixture remote, then
exercises strict-drift mode against the updated remote.

AC-CYCLE-001: End-to-end cycle documented in TDD Cycle Log:
  - Fixture git repo with branch `main` at SHA `aaaa` (real SHA).
  - Baseline install records lockfile with the baseline SHA.
  - Advance fixture's `main` to a new commit (SHA changes).
  - `mpm install` (no flag) exits 0 with the drift info-line in stdout.
  - `mpm install --strict-drift` exits non-zero with BranchDriftError.
  - `mpm install --refresh-lock-source <source>` rewrites lockfile with
    the new SHA.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from mpm_cli.core.install import (
    BranchDriftError,
    OrphanedLockEntryError,
    _RefResolution,
    install,
)
from mpm_cli.core.mpm_hash import mpm_hash as _compute_mpm_hash
from mpm_cli.core.lockfile import read_lockfile
from mpm_cli.core.metadata import derive_source_name
from tests.integration.test_add_core import _create_manifest_repo_with_tags


@pytest.fixture(autouse=True)
def _mock_resolve_ref_to_sha():
    """Override: let the test's own patch handle _resolve_ref_to_sha."""
    yield


@pytest.fixture(autouse=True)
def _mock_check_sha_reachable():
    """Override: let the test's own subprocess.run patches handle reachability."""
    yield


def _git(*args: str, cwd: pathlib.Path) -> str:
    """Run a git command and return stdout. Raises RuntimeError on non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def _sha_for_ref(repo_path: pathlib.Path, ref: str) -> str:
    """Return the SHA that ref resolves to in the given repo."""
    return _git("rev-parse", ref, cwd=repo_path)


def _build_branch_fixture_repo(base_dir: pathlib.Path, name: str) -> tuple[pathlib.Path, str]:
    """Create a fixture git repo with one commit on branch `main`.

    Returns:
        (repo_path, baseline_sha) -- path to the repo and the initial commit SHA.
    """
    repo = base_dir / name
    repo.mkdir()
    _git("init", cwd=repo)
    _git("checkout", "-b", "main", cwd=repo)
    (repo / "README.md").write_text(f"{name} initial\n")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-m", "initial commit", cwd=repo)
    sha = _sha_for_ref(repo, "refs/heads/main")
    return repo, sha


def _advance_branch(repo: pathlib.Path) -> str:
    """Add a new commit to advance the branch tip. Returns the new SHA."""
    readme = repo / "README.md"
    readme.write_text(readme.read_text() + "updated\n")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-m", "advance branch", cwd=repo)
    return _sha_for_ref(repo, "refs/heads/main")


def _write_mpm(directory: pathlib.Path, source_name: str, remote_url: str) -> pathlib.Path:
    """Write a minimal .mpm pointing at a branch-shaped source.

    Bare filesystem paths are coerced to ``file://`` URLs so the URL parser
    introduced by E1-F2-S1-T1 accepts them; the autouse
    ``_default_allow_insecure_remotes`` fixture in conftest then permits the
    non-HTTPS/SSH scheme through ``_enforce_remote_url_policy``.
    """
    if remote_url.startswith("/"):
        remote_url = f"file://{remote_url}"
    mpm_path = directory / ".mpm"
    mpm_path.write_text(
        f"MPM_MARKETPLACE_INSTALL=false\n"
        f"MPM_SOURCE_{source_name}_URL={remote_url}\n"
        f"MPM_SOURCE_{source_name}_REF=main\n"
        f"MPM_SOURCE_{source_name}_PATH=manifest.xml\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://example.com\n"
    )
    mpm_path.chmod(0o600)
    return mpm_path


def _write_mpm_with_orphan(
    directory: pathlib.Path,
    active_source: str,
    active_url: str,
) -> pathlib.Path:
    """Write a .mpm with one active source (for orphan tests)."""
    return _write_mpm(directory, active_source, active_url)


def _run_install_with_fake_catalog(
    mpm_path: pathlib.Path,
    fixture_repo: pathlib.Path,
    baseline_sha: str,
    **kwargs,
) -> None:
    """Run install() hermetically against a local fixture source repo.

    install() is hermetic (schema v4, spec Section 5.2 / FR-7): it resolves no
    catalog source, so ``catalog_source`` is always None.  _resolve_ref_to_sha
    for the local fixture SOURCE repo uses the real git binary (the fixture repos
    are local paths on disk); any unexpected URL is a fail-fast error.

    The repo init/envsubst/sync operations are patched to no-ops because the
    fixture repos are minimal git repos without real manifest files.

    Args:
        mpm_path: Path to the .mpm file.
        fixture_repo: Path to the fixture source repository.
        baseline_sha: Unused for catalog resolution (retained for call-site
            readability); the source SHA comes from the real fixture repo.
        **kwargs: Additional keyword arguments forwarded to install().
    """

    def _resolve_ref_to_sha_side_effect(url: str, ref: str) -> _RefResolution:
        if str(url) in (str(fixture_repo), f"file://{fixture_repo}"):
            result = subprocess.run(
                ["git", "ls-remote", str(fixture_repo), ref],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise ValueError(f"git ls-remote failed: {result.stderr}")
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    matched_sha, matched_ref = parts[0], parts[1]
                    if matched_ref == ref or matched_ref.endswith(f"/{ref}"):
                        return _RefResolution(sha=matched_sha, resolved_ref=matched_ref)
            raise ValueError(f"ref {ref!r} not found in {fixture_repo}")
        raise ValueError(f"unexpected URL passed to _resolve_ref_to_sha: {url!r}")

    def _check_sha_reachable_side_effect(url: str, sha: str, source_name: str) -> None:
        if str(url) in (str(fixture_repo), f"file://{fixture_repo}"):
            result = subprocess.run(
                ["git", "ls-remote", str(fixture_repo)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                from mpm_cli.core.install import LockfileUnreachableShaError

                raise LockfileUnreachableShaError(source_name=source_name, sha=sha, remote_url=url)

            sha_found = any(line.split("\t")[0] == sha for line in result.stdout.strip().splitlines() if "\t" in line)
            if not sha_found:
                from mpm_cli.core.install import LockfileUnreachableShaError

                raise LockfileUnreachableShaError(source_name=source_name, sha=sha, remote_url=url)

    with (
        patch(
            "mpm_cli.core.install._resolve_ref_to_sha",
            side_effect=_resolve_ref_to_sha_side_effect,
        ),
        patch(
            "mpm_cli.core.install._check_sha_reachable",
            side_effect=_check_sha_reachable_side_effect,
        ),
        patch("mpm_cli.core.install.run_repo_init"),
        patch("mpm_cli.core.install.run_repo_envsubst"),
        patch("mpm_cli.core.install.run_repo_sync"),
    ):
        install(mpm_path, lock_file_path=mpm_path.parent / ".mpm.lock", **kwargs)


@pytest.mark.integration
class TestStrictDriftEndToEnd:
    """AC-TEST-002: full strict-drift cycle against a real fixture git repo.

    This test is marked integration because it executes real git commands
    against a local fixture repository created in tmp_path.
    """

    def test_strict_drift_raises_with_correct_shas(self, tmp_path: pathlib.Path) -> None:
        """Baseline install -> advance branch -> strict-drift raises BranchDriftError.

        The error message must contain the EXACT baseline SHA and the new SHA.
        """
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        fixture_repo, baseline_sha = _build_branch_fixture_repo(repos_dir, "source-alpha")
        mpm_path = _write_mpm(project_dir, "alpha", str(fixture_repo))

        _run_install_with_fake_catalog(
            mpm_path,
            fixture_repo,
            baseline_sha,
            strict_lock=False,
            strict_drift=False,
        )

        lock_path = project_dir / ".mpm.lock"
        baseline_lf = read_lockfile(lock_path)
        locked_sha = baseline_lf.sources[0].resolved_sha
        assert locked_sha == baseline_sha, f"Locked SHA {locked_sha!r} != baseline {baseline_sha!r}"

        new_sha = _advance_branch(fixture_repo)
        assert new_sha != locked_sha, "Expected branch to advance to a new SHA"

        with pytest.raises(BranchDriftError) as exc_info:
            _run_install_with_fake_catalog(
                mpm_path,
                fixture_repo,
                baseline_sha,
                strict_lock=False,
                strict_drift=True,
            )

        error_msg = str(exc_info.value)
        assert locked_sha in error_msg, f"Error message missing locked SHA {locked_sha!r}"
        assert new_sha in error_msg, f"Error message missing new SHA {new_sha!r}"
        assert "alpha" in error_msg

    def test_no_strict_flag_emits_drift_info_line(self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
        """Without --strict-drift, branch drift emits info-line and exits 0."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        fixture_repo, baseline_sha = _build_branch_fixture_repo(repos_dir, "source-beta")
        mpm_path = _write_mpm(project_dir, "beta", str(fixture_repo))

        _run_install_with_fake_catalog(
            mpm_path,
            fixture_repo,
            baseline_sha,
            strict_lock=False,
            strict_drift=False,
        )

        new_sha = _advance_branch(fixture_repo)
        capsys.readouterr()

        _run_install_with_fake_catalog(
            mpm_path,
            fixture_repo,
            baseline_sha,
            strict_lock=False,
            strict_drift=False,
        )

        captured = capsys.readouterr()

        assert "branch drift: beta:" in captured.out
        assert "reusing locked SHA" in captured.out
        assert new_sha in captured.out or baseline_sha in captured.out

    def test_refresh_lock_source_updates_lockfile_after_drift(self, tmp_path: pathlib.Path) -> None:
        """After drift, --refresh-lock-source rewrites lockfile with the new SHA."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        fixture_repo, baseline_sha = _build_branch_fixture_repo(repos_dir, "source-gamma")
        mpm_path = _write_mpm(project_dir, "gamma", str(fixture_repo))

        _run_install_with_fake_catalog(
            mpm_path,
            fixture_repo,
            baseline_sha,
            strict_lock=False,
            strict_drift=False,
        )

        new_sha = _advance_branch(fixture_repo)

        _run_install_with_fake_catalog(
            mpm_path,
            fixture_repo,
            baseline_sha,
            refresh_lock_source="gamma",
            strict_lock=False,
            strict_drift=False,
        )

        lock_path = project_dir / ".mpm.lock"
        updated_lf = read_lockfile(lock_path)
        updated_sha = updated_lf.sources[0].resolved_sha
        assert updated_sha == new_sha, f"Expected lockfile to record new SHA {new_sha!r}, got {updated_sha!r}"


@pytest.mark.integration
class TestStrictLockEndToEnd:
    """Strict-lock cycle: orphaned lock entries raise hard errors.

    The orphaned lock entry scenario occurs when the lockfile contains a source
    that is absent from the current .mpm, BUT the mpm_hash still matches.
    In practice this can occur if the lockfile was manually edited to add an
    extra [[sources]] entry without updating the mpm_hash, or when using
    tools that bypass the normal install flow.

    We simulate this by writing a lockfile manually: compute the mpm_hash
    for the current (single-source) .mpm, then write a lockfile that contains
    BOTH the active source AND an orphaned source entry, using the computed
    mpm_hash.  This produces a LOCKFILE_CONSISTENT state with an orphan.
    """

    def _write_lockfile_with_orphan(
        self,
        lock_path: pathlib.Path,
        mpm_hash: str,
        active_name: str,
        active_url: str,
        active_sha: str,
        orphan_name: str,
        orphan_url: str,
        orphan_sha: str,
    ) -> None:
        """Write a schema-v4 lockfile with one active source and one orphaned source.

        The v4 lock is alias-keyed and carries no [catalog] block (spec Section 5.2).
        Bare filesystem paths are coerced to ``file://`` URLs so the URL parser
        introduced by E1-F2-S1-T1 accepts the locked URLs when the install
        engine re-validates them.
        """
        if active_url.startswith("/"):
            active_url = f"file://{active_url}"
        if orphan_url.startswith("/"):
            orphan_url = f"file://{orphan_url}"
        lock_path.write_text(
            f"schema_version = 5\n"
            f'generated_at = "2026-01-15T00:00:00Z"\n'
            f'generator = "mpm-cli/test"\n'
            f'mpm_hash = "{mpm_hash}"\n'
            f"marketplace_registered = false\n"
            f'marketplace_dir = ""\n'
            f"\n"
            f"[[sources]]\n"
            f'alias = "{active_name}"\n'
            f'name = "{active_name}"\n'
            f'url = "{active_url}"\n'
            f'ref_spec = "main"\n'
            f'resolved_ref = "refs/heads/main"\n'
            f'resolved_sha = "{active_sha}"\n'
            f'path = "manifest.xml"\n'
            f"\n"
            f"[[sources]]\n"
            f'alias = "{orphan_name}"\n'
            f'name = "{orphan_name}"\n'
            f'url = "{orphan_url}"\n'
            f'ref_spec = "main"\n'
            f'resolved_ref = "refs/heads/main"\n'
            f'resolved_sha = "{orphan_sha}"\n'
            f'path = "manifest.xml"\n'
        )

    def test_strict_lock_raises_orphaned_error(self, tmp_path: pathlib.Path) -> None:
        """strict-lock raises OrphanedLockEntryError when lockfile has orphaned source.

        This test simulates a LOCKFILE_CONSISTENT state with an orphaned entry by
        manually writing a lockfile that includes an extra source entry not present
        in the current .mpm, but using the correct mpm_hash for the current .mpm.
        """
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        fixture_alpha, sha_alpha = _build_branch_fixture_repo(repos_dir, "source-alpha2")
        fixture_orphan, sha_orphan = _build_branch_fixture_repo(repos_dir, "source-orphan")

        mpm_path = project_dir / ".mpm"
        mpm_path.write_text(
            f"MPM_MARKETPLACE_INSTALL=false\n"
            f"MPM_SOURCE_alpha_URL=file://{fixture_alpha}\n"
            f"MPM_SOURCE_alpha_REF=main\n"
            f"MPM_SOURCE_alpha_PATH=manifest.xml\n"
            f"MPM_SOURCE_alpha_NAME=alpha\n"
            f"MPM_SOURCE_alpha_GITBASE=https://example.com\n"
        )
        mpm_path.chmod(0o600)

        from mpm_cli.core.mpm_hash import mpm_hash as compute_hash

        real_hash = compute_hash(mpm_path)

        lock_path = project_dir / ".mpm.lock"
        self._write_lockfile_with_orphan(
            lock_path,
            mpm_hash=real_hash,
            active_name="alpha",
            active_url=str(fixture_alpha),
            active_sha=sha_alpha,
            orphan_name="ghost",
            orphan_url=str(fixture_orphan),
            orphan_sha=sha_orphan,
        )

        fake_ref = _RefResolution(sha=sha_alpha, resolved_ref="refs/heads/main")

        def _check_reachable(url: str, sha: str, source_name: str) -> None:
            return None

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=fake_ref),
            patch("mpm_cli.core.install._check_sha_reachable", side_effect=_check_reachable),
            patch("mpm_cli.core.install.subprocess.run") as mock_run,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
            pytest.raises(OrphanedLockEntryError) as exc_info,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=f"{sha_alpha}\trefs/heads/main\n")
            install(
                mpm_path,
                lock_file_path=mpm_path.parent / ".mpm.lock",
                strict_lock=True,
            )

        error_msg = str(exc_info.value)
        assert "ghost" in error_msg

        assert "MPM_SOURCE_" in error_msg or "--strict-lock" in error_msg

    def test_strict_lock_default_prunes_orphan(self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
        """Without --strict-lock, orphaned entries are pruned with info-line."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        fixture_alpha, sha_alpha = _build_branch_fixture_repo(repos_dir, "source-alpha3")
        fixture_orphan, sha_orphan = _build_branch_fixture_repo(repos_dir, "source-orphan2")

        mpm_path = project_dir / ".mpm"
        mpm_path.write_text(
            f"MPM_MARKETPLACE_INSTALL=false\n"
            f"MPM_SOURCE_alpha_URL=file://{fixture_alpha}\n"
            f"MPM_SOURCE_alpha_REF=main\n"
            f"MPM_SOURCE_alpha_PATH=manifest.xml\n"
            f"MPM_SOURCE_alpha_NAME=alpha\n"
            f"MPM_SOURCE_alpha_GITBASE=https://example.com\n"
        )
        mpm_path.chmod(0o600)

        from mpm_cli.core.mpm_hash import mpm_hash as compute_hash

        real_hash = compute_hash(mpm_path)

        lock_path = project_dir / ".mpm.lock"
        self._write_lockfile_with_orphan(
            lock_path,
            mpm_hash=real_hash,
            active_name="alpha",
            active_url=str(fixture_alpha),
            active_sha=sha_alpha,
            orphan_name="ghost",
            orphan_url=str(fixture_orphan),
            orphan_sha=sha_orphan,
        )

        fake_ref = _RefResolution(sha=sha_alpha, resolved_ref="refs/heads/main")

        with (
            patch("mpm_cli.core.install._resolve_ref_to_sha", return_value=fake_ref),
            patch("mpm_cli.core.install._check_sha_reachable"),
            patch("mpm_cli.core.install.subprocess.run") as mock_run,
            patch("mpm_cli.core.install.run_repo_init"),
            patch("mpm_cli.core.install.run_repo_envsubst"),
            patch("mpm_cli.core.install.run_repo_sync"),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout=f"{sha_alpha}\trefs/heads/main\n")
            install(
                mpm_path,
                lock_file_path=mpm_path.parent / ".mpm.lock",
                strict_lock=False,
            )

        captured = capsys.readouterr()
        assert "pruned orphaned lock entry: ghost" in captured.out

        updated_lf = read_lockfile(lock_path)
        source_names = [s.name for s in updated_lf.sources]
        assert "ghost" not in source_names
        assert "alpha" in source_names


@pytest.mark.integration
class TestStrictLockOrphanErrorMessage:
    """Verify that --strict-lock error names each orphan source and includes remediation.

    DEFECT-011: the error message produced by OrphanedLockEntryError must contain
    the normalized orphan source name, the substring '--strict-lock', the substring
    'mpm remove', and a count-prefixed noun phrase that is grammatically correct
    for singular (1 orphaned lockfile entry:) and plural (N orphaned lockfile entries:).

    Each test constructs a LOCKFILE_CONSISTENT state manually: a .mpm with only
    the active source, a lockfile with the correct mpm_hash for that .mpm but
    containing additional orphaned [[sources]] entries. Running
    'mpm install --strict-lock' as a subprocess surfaces the error on stderr.
    """

    def _write_mpm_single_source(
        self,
        directory: pathlib.Path,
        source_name: str,
        source_url: str,
    ) -> pathlib.Path:
        """Write .mpm with a single source triple and return the path.

        Args:
            directory: Directory in which to create the .mpm file.
            source_name: The MPM_SOURCE_<name> key suffix (already normalized).
            source_url: URL for the source; bare paths are coerced to file://.
        """
        if source_url.startswith("/"):
            source_url = f"file://{source_url}"
        mpm_path = directory / ".mpm"
        mpm_path.write_text(
            f"MPM_MARKETPLACE_INSTALL=false\n"
            f"MPM_SOURCE_{source_name}_URL={source_url}\n"
            f"MPM_SOURCE_{source_name}_REF=main\n"
            f"MPM_SOURCE_{source_name}_PATH=manifest.xml\n"
            f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
            f"MPM_SOURCE_{source_name}_GITBASE=https://example.com\n"
        )
        mpm_path.chmod(0o600)
        return mpm_path

    def _write_lockfile_with_orphans(
        self,
        lock_path: pathlib.Path,
        mpm_hash: str,
        active_name: str,
        active_url: str,
        active_sha: str,
        orphan_entries: list[tuple[str, str, str]],
    ) -> None:
        """Write a schema-v4 lockfile with correct mpm_hash but extra orphaned source entries.

        The lockfile is in the LOCKFILE_CONSISTENT state (hash matches the current
        .mpm) but contains additional alias-keyed [[sources]] entries that are
        absent from the current .mpm, making them orphans detectable by
        --strict-lock.  The v4 lock carries no [catalog] block (spec Section 5.2).

        Args:
            lock_path: Path at which to write the lockfile.
            mpm_hash: The mpm_hash that matches the current .mpm content.
            active_name: Source name for the non-orphaned active entry.
            active_url: URL for the active source; bare paths coerced to file://.
            active_sha: Resolved SHA for the active source.
            orphan_entries: List of (name, url, sha) tuples for orphaned entries.
        """
        if active_url.startswith("/"):
            active_url = f"file://{active_url}"

        active_block = (
            f"[[sources]]\n"
            f'alias = "{active_name}"\n'
            f'name = "{active_name}"\n'
            f'url = "{active_url}"\n'
            f'ref_spec = "main"\n'
            f'resolved_ref = "refs/heads/main"\n'
            f'resolved_sha = "{active_sha}"\n'
            f'path = "manifest.xml"\n'
        )

        orphan_blocks = []
        for orphan_name, orphan_url, orphan_sha in orphan_entries:
            if orphan_url.startswith("/"):
                orphan_url = f"file://{orphan_url}"
            orphan_blocks.append(
                f"[[sources]]\n"
                f'alias = "{orphan_name}"\n'
                f'name = "{orphan_name}"\n'
                f'url = "{orphan_url}"\n'
                f'ref_spec = "main"\n'
                f'resolved_ref = "refs/heads/main"\n'
                f'resolved_sha = "{orphan_sha}"\n'
                f'path = "manifest.xml"\n'
            )

        body = (
            f"schema_version = 5\n"
            f'generated_at = "2026-01-15T00:00:00Z"\n'
            f'generator = "mpm-cli/test"\n'
            f'mpm_hash = "{mpm_hash}"\n'
            f"marketplace_registered = false\n"
            f'marketplace_dir = ""\n'
            f"\n" + active_block
        )
        for block in orphan_blocks:
            body += "\n" + block

        lock_path.write_text(body)

    def _run_strict_lock_install(
        self,
        project_dir: pathlib.Path,
    ) -> subprocess.CompletedProcess[str]:
        """Run 'mpm install --strict-lock' as a subprocess in project_dir.

        Args:
            project_dir: The working directory containing the .mpm file.

        Returns:
            The completed subprocess result with stdout and stderr captured.
        """
        env = dict(os.environ)
        env["MPM_ALLOW_INSECURE_REMOTES"] = "1"

        env.pop("MPM_CATALOG_SOURCES", None)
        return subprocess.run(
            [sys.executable, "-m", "mpm_cli", "install", "--strict-lock"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(project_dir),
        )

    def test_error_names_each_orphan_source_and_remediation(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """--strict-lock stderr must contain orphan name, 'mpm install --reconcile', and 'mpm remove'.

        Spec reference: spec Section 4 E26 Failing test.

        DEFECT-011 root cause: the OrphanedLockEntryError message must include both
        remediation paths ('mpm install --reconcile' to prune and 'mpm remove' to
        drop the source) so the operator can resolve the orphan either way.

        Setup:
        - Two bare repos: catA (entry 'source-delta') and catB (entry 'source-echo').
        - .mpm with only source-delta active.
        - Lockfile with correct mpm_hash for that .mpm, but also containing
          a source-echo orphaned entry (simulating the state after 'mpm remove'
          was not followed by a lockfile prune).
        """
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        cat_a_bare = _create_manifest_repo_with_tags(
            repos_dir / "catA",
            entry_names=["source-delta"],
            tags=["1.0.0"],
        )
        cat_b_bare = _create_manifest_repo_with_tags(
            repos_dir / "catB",
            entry_names=["source-echo"],
            tags=["1.0.0"],
        )

        active_entry_name = "source-delta"
        orphan_entry_name = "source-echo"
        active_source_key = derive_source_name(active_entry_name)
        expected_orphan_name = derive_source_name(orphan_entry_name)

        placeholder_sha = "a" * 40

        mpm_path = self._write_mpm_single_source(
            project_dir,
            source_name=active_source_key,
            source_url=str(cat_a_bare),
        )

        real_hash = _compute_mpm_hash(mpm_path)

        lock_path = project_dir / ".mpm.lock"
        self._write_lockfile_with_orphans(
            lock_path,
            mpm_hash=real_hash,
            active_name=active_source_key,
            active_url=str(cat_a_bare),
            active_sha=placeholder_sha,
            orphan_entries=[(expected_orphan_name, str(cat_b_bare), placeholder_sha)],
        )

        result = self._run_strict_lock_install(project_dir)

        stderr = result.stderr
        assert result.returncode != 0, (
            f"Expected non-zero exit for strict-lock orphan, got 0.\nstdout: {result.stdout!r}\nstderr: {stderr!r}"
        )
        assert expected_orphan_name in stderr, (
            f"Expected orphan name {expected_orphan_name!r} in stderr.\nstderr: {stderr!r}"
        )
        assert "mpm install --reconcile" in stderr, (
            f"Expected 'mpm install --reconcile' in stderr (remediation hint).\nstderr: {stderr!r}"
        )
        assert "mpm remove" in stderr, f"Expected 'mpm remove' in stderr (alternative remediation).\nstderr: {stderr!r}"

    @pytest.mark.parametrize(
        ("orphan_count", "expected_word"),
        [(1, "entry:"), (2, "entries:")],
    )
    def test_error_grammatically_correct_for_single_vs_multiple_orphans(
        self,
        tmp_path: pathlib.Path,
        orphan_count: int,
        expected_word: str,
    ) -> None:
        """Singular/plural count prefix is grammatically correct in --strict-lock stderr.

        For 1 orphan: stderr contains '1 orphaned lockfile entry:'.
        For 2 orphans: stderr contains '2 orphaned lockfile entries:'.

        Spec reference: spec Section 4 E26 Edge cases.

        DEFECT-011 root cause: the current error message has no count-prefixed phrase;
        both parametrized cases fail RED because neither expected substring is present.
        """
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        cat_active_bare = _create_manifest_repo_with_tags(
            repos_dir / "cat-active",
            entry_names=["source-foxtrot"],
            tags=["1.0.0"],
        )
        active_source_key = derive_source_name("source-foxtrot")

        orphan_entries: list[tuple[str, str, str]] = []
        placeholder_sha = "b" * 40
        for idx in range(orphan_count):
            orphan_entry_name = f"source-golf-{idx}"
            orphan_bare = _create_manifest_repo_with_tags(
                repos_dir / f"cat-orphan-{idx}",
                entry_names=[orphan_entry_name],
                tags=["1.0.0"],
            )
            orphan_source_key = derive_source_name(orphan_entry_name)
            orphan_entries.append((orphan_source_key, str(orphan_bare), placeholder_sha))

        placeholder_active_sha = "c" * 40
        mpm_path = self._write_mpm_single_source(
            project_dir,
            source_name=active_source_key,
            source_url=str(cat_active_bare),
        )

        real_hash = _compute_mpm_hash(mpm_path)

        lock_path = project_dir / ".mpm.lock"
        self._write_lockfile_with_orphans(
            lock_path,
            mpm_hash=real_hash,
            active_name=active_source_key,
            active_url=str(cat_active_bare),
            active_sha=placeholder_active_sha,
            orphan_entries=orphan_entries,
        )

        result = self._run_strict_lock_install(project_dir)

        stderr = result.stderr
        assert result.returncode != 0, (
            f"Expected non-zero exit for strict-lock with {orphan_count} orphan(s), got 0.\n"
            f"stdout: {result.stdout!r}\nstderr: {stderr!r}"
        )
        expected_phrase = f"{orphan_count} orphaned lockfile {expected_word}"
        assert expected_phrase in stderr, (
            f"Expected {expected_phrase!r} in stderr for {orphan_count} orphan(s).\nstderr: {stderr!r}"
        )


@pytest.mark.integration
class TestStrictLockDefaultAutoPrune:
    """'mpm install --reconcile' prunes orphaned lockfile entries.

    DEFECT-014: when B's MPM_SOURCE_B_* triple is removed from .mpm but
    B still exists in .mpm.lock, 'mpm install --reconcile' should exit 0,
    emit one INFO line per orphan ('pruned orphaned lock entry: <name>'), and
    rewrite .mpm.lock without the orphaned entry.

    Removing B's triple changes the mpm_hash and drops B's alias, so a plain
    'mpm install' (no flags) now fails fast (exit 1) without mutating the lock;
    the lenient prune+replay reconcile is opt-in via --reconcile, which prunes
    the orphan, replays the surviving sources, writes the pruned lockfile, and
    exits 0.  ('mpm install --strict-lock' on a same-hash orphan would instead
    raise OrphanedLockEntryError without mutating.)

    The tests in this class run 'mpm install' as a subprocess so that they
    exercise the real CLI entry point and capture stdout/stderr + exit code.
    MPM_ALLOW_INSECURE_REMOTES=1 is passed to permit file:// URLs used by
    the synthetic bare repos.
    """

    def _run_mpm(
        self,
        args: list[str],
        cwd: pathlib.Path,
    ) -> subprocess.CompletedProcess[str]:
        """Run the mpm CLI as a subprocess, capturing output.

        Args:
            args: Arguments to pass to 'mpm' (e.g. ['add', 'entry-a', ...]).
            cwd: Working directory for the subprocess.

        Returns:
            Completed subprocess result with stdout and stderr captured.
        """
        env = dict(os.environ)
        env["MPM_ALLOW_INSECURE_REMOTES"] = "1"

        env.pop("MPM_CATALOG_SOURCES", None)
        return subprocess.run(
            [sys.executable, "-m", "mpm_cli"] + args,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd),
        )

    def _mpm_add(
        self,
        entry_name: str,
        catalog_source: str,
        workspace: pathlib.Path,
    ) -> None:
        """Run 'mpm add <entry_name> --catalog-source <catalog_source>'.

        Raises RuntimeError if the command exits non-zero.

        Args:
            entry_name: Catalog entry name to add.
            catalog_source: Catalog source in '<url>@<ref>' form.
            workspace: Working directory containing the .mpm file.
        """
        result = self._run_mpm(
            ["add", entry_name, "--catalog-source", catalog_source],
            cwd=workspace,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"mpm add {entry_name!r} failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
            )

    def _mpm_install(
        self,
        workspace: pathlib.Path,
        extra_args: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run 'mpm install [extra_args]' and return the completed process.

        Does NOT raise on non-zero exit; the caller inspects returncode.

        Args:
            workspace: Working directory containing the .mpm file.
            extra_args: Optional additional arguments (e.g. ['--strict-lock']).

        Returns:
            Completed subprocess result.
        """
        args = ["install"] + (extra_args or [])
        return self._run_mpm(args, cwd=workspace)

    def _remove_source_triple(
        self,
        mpm_path: pathlib.Path,
        source_name: str,
    ) -> None:
        """Remove the MPM_SOURCE_<source_name>_* lines from .mpm.

        Reads the file, filters out the per-source key lines (the four
        structural keys URL, REF, PATH, NAME, plus any optional env-var line),
        and writes back the remainder.  Raises RuntimeError if fewer than the
        four structural lines are removed (guard against misconfigured test
        setup). The catalog manifest these tests use references no ${VAR}, so
        mpm add writes only the four structural keys (no _GITBASE line).

        The source_name must match the token written by 'mpm add' exactly,
        which is the derive_source_name() output (lowercase, hyphens -> underscores).
        The prefix check is case-sensitive to match the file verbatim.

        Args:
            mpm_path: Path to the .mpm file.
            source_name: Normalized source name token as written by mpm add
                (e.g. 'entry_beta' for entry 'entry-beta').
        """
        lines = mpm_path.read_text().splitlines(keepends=True)
        prefix = f"MPM_SOURCE_{source_name}_"
        filtered = [ln for ln in lines if not ln.startswith(prefix)]
        removed_count = len(lines) - len(filtered)
        if removed_count < 4:
            raise RuntimeError(
                f"Expected to remove the 4 structural MPM_SOURCE_{source_name}_* lines from "
                f"{mpm_path}; only removed {removed_count}. "
                f"Check that mpm add wrote all four structural keys for {source_name!r}."
            )
        mpm_path.write_text("".join(filtered))
        mpm_path.chmod(0o600)

    def test_default_install_prunes_orphan_with_info_line(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """'mpm install --reconcile' prunes a single orphan, emits INFO line, exits 0.

        Spec reference: spec Section 4 E34 Failing test.

        Removing B's triple from .mpm changes the mpm_hash and drops B's
        alias.  Plain 'mpm install' would now fail fast on the drift; the
        --reconcile opt-in reconciles instead: it prunes the orphaned B entry,
        replays the surviving sources, and writes the pruned lockfile -- exiting 0
        and emitting the 'pruned orphaned lock entry:' INFO line.

        Setup:
        - Create two separate bare catalog repos (A and B) via
          _create_manifest_repo_with_tags.
        - mpm add entry-a using A's catalog repo.
        - mpm add entry-b using B's catalog repo.
        - mpm install (builds .mpm.lock with both sources).
        - Remove B's MPM_SOURCE_<b_key>_* triple from .mpm.
        - mpm install --reconcile -- the GREEN assertion target.

        Assertions:
        - exit_code == 0.
        - 'pruned orphaned lock entry:' in stdout.
        - derived B orphan name present on the same info line.
        - B's source name absent from the post-run .mpm.lock.
        """
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        bare_a = _create_manifest_repo_with_tags(
            repos_dir / "cat-a",
            entry_names=["entry-alpha"],
            tags=["1.0.0"],
        )
        bare_b = _create_manifest_repo_with_tags(
            repos_dir / "cat-b",
            entry_names=["entry-beta"],
            tags=["1.0.0"],
        )

        a_source_name = derive_source_name("entry-alpha")
        b_source_name = derive_source_name("entry-beta")

        catalog_a = f"file://{bare_a}@main"
        catalog_b = f"file://{bare_b}@main"

        self._mpm_add("entry-alpha", catalog_a, workspace)
        self._mpm_add("entry-beta", catalog_b, workspace)

        install_result = self._mpm_install(workspace)
        assert install_result.returncode == 0, (
            f"Initial mpm install failed (exit {install_result.returncode}).\n"
            f"stdout: {install_result.stdout!r}\nstderr: {install_result.stderr!r}"
        )

        mpm_path = workspace / ".mpm"
        lock_path = workspace / ".mpm.lock"
        assert lock_path.exists(), ".mpm.lock was not created by the initial install"

        initial_lock = read_lockfile(lock_path)
        initial_names = [s.name for s in initial_lock.sources]
        assert b_source_name in initial_names, (
            f"Expected {b_source_name!r} in initial lockfile sources: {initial_names!r}"
        )

        self._remove_source_triple(mpm_path, b_source_name)

        mpm_content = mpm_path.read_text()
        assert f"MPM_SOURCE_{b_source_name}_URL" not in mpm_content, "B's URL line should have been removed from .mpm"
        assert f"MPM_SOURCE_{a_source_name}_URL" in mpm_content, "A's URL line must remain in .mpm after removing B"

        second_result = self._mpm_install(workspace, extra_args=["--reconcile"])
        stdout = second_result.stdout

        assert second_result.returncode == 0, (
            f"Expected exit 0 after auto-prune; got {second_result.returncode}.\n"
            f"stdout: {stdout!r}\nstderr: {second_result.stderr!r}"
        )
        assert "pruned orphaned lock entry:" in stdout, (
            f"Expected 'pruned orphaned lock entry:' info line in stdout.\nstdout: {stdout!r}"
        )
        assert b_source_name in stdout, (
            f"Expected orphan name {b_source_name!r} on the info line in stdout.\nstdout: {stdout!r}"
        )

        post_run_lock = read_lockfile(lock_path)
        post_run_names = [s.name for s in post_run_lock.sources]
        assert b_source_name not in post_run_names, (
            f"Expected {b_source_name!r} to be absent from post-run lockfile.\nPost-run sources: {post_run_names!r}"
        )
        assert a_source_name in post_run_names, (
            f"Expected {a_source_name!r} to remain in post-run lockfile.\nPost-run sources: {post_run_names!r}"
        )

    @pytest.mark.parametrize("orphan_count", [1, 2, 3])
    def test_default_install_emits_one_info_line_per_orphan(
        self,
        tmp_path: pathlib.Path,
        orphan_count: int,
    ) -> None:
        """'mpm install --reconcile' emits exactly N INFO lines for N orphans, exits 0.

        Spec reference: spec Section 4 E34 Edge cases.

        For each value in [1, 2, 3] orphan count:
        - Build workspace with 1 active source + orphan_count orphan sources.
        - Install to create the lockfile.
        - Remove all orphan source triples from .mpm.
        - Run mpm install --reconcile.
        - Assert exactly orphan_count occurrences of 'pruned orphaned lock entry:'.
        - Assert exit_code == 0.
        - Assert zero orphan source names remain in the post-run .mpm.lock.

        Args:
            tmp_path: Pytest temporary directory fixture.
            orphan_count: Number of orphan sources to build and verify (1, 2, or 3).
        """
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        bare_active = _create_manifest_repo_with_tags(
            repos_dir / "cat-active",
            entry_names=["entry-active"],
            tags=["1.0.0"],
        )
        active_source_name = derive_source_name("entry-active")
        catalog_active = f"file://{bare_active}@main"
        self._mpm_add("entry-active", catalog_active, workspace)

        orphan_source_names: list[str] = []
        for idx in range(orphan_count):
            entry_name = f"entry-orphan-{idx}"
            bare_orphan = _create_manifest_repo_with_tags(
                repos_dir / f"cat-orphan-{idx}",
                entry_names=[entry_name],
                tags=["1.0.0"],
            )
            catalog_orphan = f"file://{bare_orphan}@main"
            self._mpm_add(entry_name, catalog_orphan, workspace)
            orphan_source_names.append(derive_source_name(entry_name))

        install_result = self._mpm_install(workspace)
        assert install_result.returncode == 0, (
            f"Initial install failed (exit {install_result.returncode}).\n"
            f"stdout: {install_result.stdout!r}\nstderr: {install_result.stderr!r}"
        )

        lock_path = workspace / ".mpm.lock"
        mpm_path = workspace / ".mpm"
        assert lock_path.exists(), ".mpm.lock was not created by initial install"

        for orphan_name in orphan_source_names:
            self._remove_source_triple(mpm_path, orphan_name)

        second_result = self._mpm_install(workspace, extra_args=["--reconcile"])
        stdout = second_result.stdout

        assert second_result.returncode == 0, (
            f"Expected exit 0 with {orphan_count} orphan(s); got {second_result.returncode}.\n"
            f"stdout: {stdout!r}\nstderr: {second_result.stderr!r}"
        )

        info_prefix = "pruned orphaned lock entry:"
        info_line_count = stdout.count(info_prefix)
        assert info_line_count == orphan_count, (
            f"Expected exactly {orphan_count} '{info_prefix}' line(s) in stdout; "
            f"got {info_line_count}.\nstdout: {stdout!r}"
        )

        post_run_lock = read_lockfile(lock_path)
        post_run_names = [s.name for s in post_run_lock.sources]

        for orphan_name in orphan_source_names:
            assert orphan_name not in post_run_names, (
                f"Expected orphan {orphan_name!r} to be absent from post-run lockfile.\n"
                f"Post-run sources: {post_run_names!r}"
            )
        assert active_source_name in post_run_names, (
            f"Expected active source {active_source_name!r} to remain in post-run lockfile.\n"
            f"Post-run sources: {post_run_names!r}"
        )
