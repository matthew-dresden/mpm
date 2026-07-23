"""Integration tests for 'mpm add --dry-run', '--force', and collision-error path.

Builds a temporary local file:// manifest-repo fixture with PEP 440-valid
git tags and invokes 'mpm add' via subprocess.run.

Covers:
- --dry-run: stdout diff shape, no file modification, exit 0
- --force: existing block overwritten, surrounding content preserved
- Collision-error path: spec-canonical error message, non-zero exit
- Within-request collision: 'mpm add a a' hard error
- AC-CYCLE-001 evidence: full end-to-end cycle with entry-a and entry-b

AC-TEST-002, AC-CYCLE-001
"""

import hashlib
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest


_GIT_USER_NAME = "Test User"
_GIT_USER_EMAIL = "test@example.com"


_MARKETPLACE_XML_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <manifest>
      <catalog-metadata>
        <name>{name}</name>
        <display-name>{name} Display</display-name>
        <description>Integration test entry for {name}.</description>
        <version>1.0.0</version>
        <type>plugin</type>
        <owner-name>Integration Tester</owner-name>
        <owner-email>integration@example.com</owner-email>
        <keywords>integration, test</keywords>
      </catalog-metadata>
    </manifest>
""")


def _git(args: list[str], cwd: pathlib.Path) -> None:
    """Run a git command in cwd, raising RuntimeError on non-zero exit."""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args!r} failed in {cwd!r}:\n  stdout: {result.stdout!r}\n  stderr: {result.stderr!r}")


def _init_git_work_dir(work_dir: pathlib.Path) -> None:
    """Initialise a git working directory with test user config."""
    _git(["init", "-b", "main"], cwd=work_dir)
    _git(["config", "user.name", _GIT_USER_NAME], cwd=work_dir)
    _git(["config", "user.email", _GIT_USER_EMAIL], cwd=work_dir)


def _clone_as_bare(work_dir: pathlib.Path, bare_dir: pathlib.Path) -> pathlib.Path:
    """Clone work_dir into a bare repository and return the bare path."""
    _git(["clone", "--bare", str(work_dir), str(bare_dir)], cwd=work_dir.parent)
    return bare_dir.resolve()


def _create_manifest_repo_with_tags(
    base: pathlib.Path,
    entry_names: list[str],
    tags: list[str],
) -> pathlib.Path:
    """Create a bare manifest repo with marketplace XML files and git tags."""
    work_dir = base / "manifest-work"
    work_dir.mkdir(parents=True, exist_ok=True)
    _init_git_work_dir(work_dir)

    repo_specs_dir = work_dir / "repo-specs"
    repo_specs_dir.mkdir()
    (repo_specs_dir / ".gitkeep").write_text("")

    for name in entry_names:
        xml_path = repo_specs_dir / f"{name}-marketplace.xml"
        xml_path.write_text(_MARKETPLACE_XML_TEMPLATE.format(name=name))

    _git(["add", "."], cwd=work_dir)
    _git(["commit", "-m", "Add marketplace entries"], cwd=work_dir)

    for tag in tags:
        _git(["tag", "-a", tag, "-m", f"Release {tag}"], cwd=work_dir)

    bare_dir = _clone_as_bare(work_dir, base / "manifest-bare.git")
    return bare_dir.resolve()


def _run_mpm(
    args: list[str],
    extra_env: dict[str, str] | None = None,
    cwd: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the mpm entry point via the same Python interpreter."""
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "mpm_cli"] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def _sha256(path: pathlib.Path) -> str:
    """Return the SHA-256 hex digest of a file's content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
class TestAddDryRun:
    """mpm add --dry-run prints a diff and makes no on-disk change."""

    def test_dry_run_exits_0(self, tmp_path: pathlib.Path) -> None:
        """mpm add --dry-run exits 0 even when no collision."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_dry_run_stdout_has_plus_prefixed_lines(self, tmp_path: pathlib.Path) -> None:
        """--dry-run stdout shows '+' prefixed lines for each added triple line."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
            ],
            cwd=workspace,
        )
        assert "+MPM_SOURCE_entry_a_URL=" in result.stdout
        assert "+MPM_SOURCE_entry_a_REF=" in result.stdout
        assert "+MPM_SOURCE_entry_a_PATH=" in result.stdout

    def test_dry_run_does_not_modify_file_content(self, tmp_path: pathlib.Path) -> None:
        """File content is unchanged after --dry-run (verified by SHA-256)."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        original_content = (
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
        )
        mpm_file.write_text(original_content)
        sha_before = _sha256(mpm_file)
        mtime_before = mpm_file.stat().st_mtime

        _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
            ],
            cwd=workspace,
        )

        sha_after = _sha256(mpm_file)
        mtime_after = mpm_file.stat().st_mtime
        assert sha_before == sha_after, "File content changed during --dry-run"
        assert mtime_before == mtime_after, "File mtime changed during --dry-run"

    def test_dry_run_force_shows_minus_for_removed_lines(self, tmp_path: pathlib.Path) -> None:
        """--dry-run --force shows '-' prefixed lines for existing triple being replaced."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"

        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )
        sha_before = _sha256(mpm_file)

        result = _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
                "--force",
            ],
            cwd=workspace,
        )

        assert result.returncode == 0, f"Expected exit 0.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"

        assert "-MPM_SOURCE_entry_a_REF=refs/tags/1.0.0" in result.stdout
        assert "+MPM_SOURCE_entry_a_REF=refs/tags/1.0.0" in result.stdout
        assert "+MPM_SOURCE_entry_a_NAME=entry-a" in result.stdout

        assert _sha256(mpm_file) == sha_before, "File content changed during --dry-run --force"


_CLAUDE_MARKETPLACES_DIR_HEADER = "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces"


@pytest.mark.integration
class TestAddMarketplaceDryRun:
    """mpm add <claude-marketplace> --dry-run previews the header but writes nothing (Feature A)."""

    def test_dry_run_previews_marketplaces_dir_header_line(self, tmp_path: pathlib.Path) -> None:
        """The dry-run diff includes a +CLAUDE_MARKETPLACES_DIR=... preview line for a marketplace entry."""
        from tests.integration.test_add_core import _create_marketplace_manifest_repo

        bare = _create_marketplace_manifest_repo(
            tmp_path / "repo",
            entry_name="mp-entry",
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"

        result = _run_mpm(
            [
                "add",
                "mp-entry",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert f"+{_CLAUDE_MARKETPLACES_DIR_HEADER}" in result.stdout, (
            f"Expected the marketplace header preview line in the dry-run diff; got:\n{result.stdout!r}"
        )

    def test_dry_run_does_not_create_or_modify_file(self, tmp_path: pathlib.Path) -> None:
        """A marketplace --dry-run leaves an absent .mpm absent (no header write)."""
        from tests.integration.test_add_core import _create_marketplace_manifest_repo

        bare = _create_marketplace_manifest_repo(
            tmp_path / "repo",
            entry_name="mp-entry",
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"

        result = _run_mpm(
            [
                "add",
                "mp-entry",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert not mpm_file.exists(), "mpm add --dry-run must not create the .mpm file"

    def test_dry_run_leaves_existing_file_byte_unchanged(self, tmp_path: pathlib.Path) -> None:
        """A marketplace --dry-run against an existing headerless .mpm leaves it byte-for-byte unchanged."""
        from tests.integration.test_add_core import _create_marketplace_manifest_repo

        bare = _create_marketplace_manifest_repo(
            tmp_path / "repo",
            entry_name="mp-entry",
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text("GITBASE=<YOUR_GIT_ORG_BASE_URL>\n")
        sha_before = _sha256(mpm_file)
        mtime_before = mpm_file.stat().st_mtime

        result = _run_mpm(
            [
                "add",
                "mp-entry",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert _sha256(mpm_file) == sha_before, "File content changed during marketplace --dry-run"
        assert mpm_file.stat().st_mtime == mtime_before, "File mtime changed during marketplace --dry-run"
        assert "CLAUDE_MARKETPLACES_DIR" not in mpm_file.read_text(), (
            "the dry-run must not write the header into the file"
        )


@pytest.mark.integration
class TestAddForce:
    """mpm add --force overwrites an existing block preserving line order."""

    def test_force_exits_0(self, tmp_path: pathlib.Path) -> None:
        """mpm add --force exits 0 when an existing block is overwritten."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a@==2.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--force",
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, f"Expected exit 0.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"

    def test_force_overwrites_existing_block(self, tmp_path: pathlib.Path) -> None:
        """--force re-add of the same source@ref overwrites and normalises the block.

        3.0.0: --force overwrites a re-add of the SAME package (same source@ref),
        keeping the alias keyed by the bare alias and re-pinning the block with
        the full normalised keys (_NAME/_GITBASE added). A different-ref re-add
        would auto-suffix instead, so the re-add uses the existing ref (==1.0.0).
        """
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--force",
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, f"--force re-add must exit 0.\nstderr: {result.stderr!r}"

        content = mpm_file.read_text()

        assert "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0" in content
        assert "MPM_SOURCE_entry_a_NAME=entry-a" in content

        assert "MPM_SOURCE_entry_a_manifest_bare_URL" not in content

    def test_force_preserves_surrounding_content(self, tmp_path: pathlib.Path) -> None:
        """--force preserves header and other blocks byte-for-byte."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a", "entry-b"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_b_URL=file://{bare}\n"
            "MPM_SOURCE_entry_b_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_b_PATH=repo-specs/entry-b-marketplace.xml\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )

        _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--force",
            ],
            cwd=workspace,
        )

        content = mpm_file.read_text()

        assert "GITBASE=" in content

        assert "MPM_SOURCE_entry_b_REF=refs/tags/1.0.0" in content

        assert "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0" in content
        assert "MPM_SOURCE_entry_a_NAME=entry-a" in content


@pytest.mark.integration
class TestAddCollisionError:
    """mpm add without --force exits non-zero with a spec-canonical message."""

    def test_collision_exits_nonzero(self, tmp_path: pathlib.Path) -> None:
        """Re-adding an existing entry without --force exits non-zero."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )
        assert result.returncode != 0

    def test_collision_error_message_names_existing_and_new(self, tmp_path: pathlib.Path) -> None:
        """Error message names existing URL/revision and requested URL/revision."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )

        assert "entry_a" in result.stderr
        assert "refs/tags/1.0.0" in result.stderr
        assert "==1.0.0" in result.stderr

    def test_collision_error_references_force_or_remove(self, tmp_path: pathlib.Path) -> None:
        """Error message references --force or 'mpm remove'."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )

        result = _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )
        assert "--force" in result.stderr or "mpm remove" in result.stderr

    def test_collision_does_not_modify_file(self, tmp_path: pathlib.Path) -> None:
        """File is not modified when a collision error occurs."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0", "2.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        original_content = (
            "GITBASE=<YOUR_GIT_ORG_BASE_URL>\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            "MPM_MARKETPLACE_INSTALL=<true|false>\n"
            "\n"
            f"MPM_SOURCE_entry_a_URL=file://{bare}\n"
            "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_entry_a_PATH=repo-specs/entry-a-marketplace.xml\n"
        )
        mpm_file.write_text(original_content)
        sha_before = _sha256(mpm_file)

        _run_mpm(
            [
                "add",
                "entry-a@==1.0.0",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )

        assert _sha256(mpm_file) == sha_before, "File was modified on collision error"


@pytest.mark.integration
class TestAddWithinRequestCollision:
    """mpm add a a exits non-zero before any catalog work."""

    def test_same_name_twice_exits_nonzero(self, tmp_path: pathlib.Path) -> None:
        """mpm add a a exits non-zero before catalog resolution."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        result = _run_mpm(
            [
                "add",
                "entry-a",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
            ],
            cwd=workspace,
        )
        assert result.returncode != 0

    def test_same_name_twice_error_names_the_entry(self, tmp_path: pathlib.Path) -> None:
        """Error message names the duplicated entry."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        result = _run_mpm(
            [
                "add",
                "entry-a",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
            ],
            cwd=workspace,
        )
        assert "entry_a" in result.stderr or "entry-a" in result.stderr

    def test_normalised_same_name_exits_nonzero(self, tmp_path: pathlib.Path) -> None:
        """Two entries normalising to the same source name is a hard error."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        result = _run_mpm(
            [
                "add",
                "entry-a",
                "Entry-A",
                "--catalog-source",
                f"file://{bare}@main",
            ],
            cwd=workspace,
        )
        assert result.returncode != 0


@pytest.mark.integration
class TestAddCycleEvidence:
    """AC-CYCLE-001: Full end-to-end cycle with entry-a and entry-b.

    Steps:
    1. Build fixture manifest repo with entry-a and entry-b tagged at 1.0.0.
    2. mpm add entry-a => triple written.
    3. mpm add entry-a (collision) => hard error with spec-canonical message.
    4. mpm add entry-a --force => existing block overwritten, file otherwise byte-identical.
    5. mpm add entry-a --dry-run (collision) => dry-run diff, no file modification.
    6. mpm add entry-a entry-a => within-request hard error.
    """

    def test_full_cycle(self, tmp_path: pathlib.Path) -> None:
        """Full AC-CYCLE-001 evidence: add, collision, force, dry-run, within-request."""
        bare = _create_manifest_repo_with_tags(
            tmp_path / "repo",
            entry_names=["entry-a", "entry-b"],
            tags=["1.0.0"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"

        result = _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, f"Step 2 failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        content_after_add = mpm_file.read_text()
        assert "MPM_SOURCE_entry_a_URL=" in content_after_add
        assert "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0" in content_after_add
        assert "MPM_SOURCE_entry_a_PATH=" in content_after_add
        assert "MPM_SOURCE_entry_a_NAME=" in content_after_add
        assert "MPM_SOURCE_entry_a_GITBASE=" not in content_after_add, (
            "this entry's manifest references no ${GITBASE}, so add writes no env-var line"
        )

        result2 = _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )
        assert result2.returncode != 0, "Expected non-zero exit on collision"
        assert "entry_a" in result2.stderr
        assert "refs/tags/1.0.0" in result2.stderr

        assert "--force" in result2.stderr or "mpm remove" in result2.stderr

        result3 = _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--force",
            ],
            cwd=workspace,
        )
        assert result3.returncode == 0, f"Step 4 failed.\nstdout: {result3.stdout!r}\nstderr: {result3.stderr!r}"
        content_after_force = mpm_file.read_text()

        assert "MPM_SOURCE_entry_a_REF=refs/tags/1.0.0" in content_after_force

        sha_before_dry = _sha256(mpm_file)
        result4 = _run_mpm(
            [
                "add",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
                "--dry-run",
                "--force",
            ],
            cwd=workspace,
        )
        assert result4.returncode == 0, f"Step 5 failed.\nstdout: {result4.stdout!r}\nstderr: {result4.stderr!r}"
        assert "+MPM_SOURCE_entry_a_" in result4.stdout
        sha_after_dry = _sha256(mpm_file)
        assert sha_before_dry == sha_after_dry, "File changed during dry-run"

        result5 = _run_mpm(
            [
                "add",
                "entry-a",
                "entry-a",
                "--catalog-source",
                f"file://{bare}@main",
                "--mpm-file",
                str(mpm_file),
            ],
            cwd=workspace,
        )
        assert result5.returncode != 0, "Expected non-zero exit for within-request collision"
        assert "entry_a" in result5.stderr or "entry-a" in result5.stderr
