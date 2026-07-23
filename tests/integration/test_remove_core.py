"""Integration tests for the 'mpm remove' core path.

Invokes 'mpm remove <name>' end-to-end against a fixture .mpm file
and asserts on the resulting file content and process output.

Covers:
- Entry-name input path (Foo-Bar -> foo_bar)
- Source-name input path (foo_bar stays as foo_bar)
- Non-contiguous lines removed while other content preserved byte-for-byte
- Fewer-than-structural-keys hard error with spec-canonical wording
- Missing .mpm file hard error
- Multi-source atomicity (all-or-nothing)
- Summary line on stdout
- AC-CYCLE-001 evidence (hand-written interleaved fixture)

AC-TEST-002, AC-CYCLE-001
"""

import pathlib
import subprocess
import sys
import textwrap

import pytest


def _run_mpm(
    args: list[str],
    cwd: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the mpm CLI via the current Python interpreter."""
    return subprocess.run(
        [sys.executable, "-m", "mpm_cli"] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


_STANDARD_HEADER = textwrap.dedent("""\
    GITBASE=https://example.com
    OTHER_VAR=kept
""")

_FOO_BAR_BLOCK = textwrap.dedent("""\
    MPM_SOURCE_foo_bar_URL=https://example.com/foo.git
    MPM_SOURCE_foo_bar_REF=refs/tags/1.0.0
    MPM_SOURCE_foo_bar_PATH=repo-specs/foo-marketplace.xml
    MPM_SOURCE_foo_bar_NAME=foo_bar
    MPM_SOURCE_foo_bar_GITBASE=https://example.com
""")


def _mpm_simple(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a simple contiguous .mpm file and return its path."""
    mpm_file = tmp_path / ".mpm"
    mpm_file.write_text(_STANDARD_HEADER + _FOO_BAR_BLOCK)
    return mpm_file


def _mpm_interleaved(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write an interleaved .mpm file per AC-CYCLE-001 specification.

    Layout:
      standard header
      MPM_SOURCE_foo_bar_URL
      unrelated MPM_SOURCE_baz_URL
      MPM_SOURCE_foo_bar_REF
      comment
      MPM_SOURCE_foo_bar_PATH
      remaining foo_bar + baz block keys
    """
    content = (
        _STANDARD_HEADER
        + "MPM_SOURCE_foo_bar_URL=https://example.com/foo.git\n"
        + "MPM_SOURCE_baz_URL=https://example.com/baz.git\n"
        + "MPM_SOURCE_foo_bar_REF=refs/tags/1.0.0\n"
        + "# trailing comment about baz\n"
        + "MPM_SOURCE_foo_bar_PATH=repo-specs/foo-marketplace.xml\n"
        + "MPM_SOURCE_foo_bar_NAME=foo_bar\n"
        + "MPM_SOURCE_foo_bar_GITBASE=https://example.com\n"
        + "MPM_SOURCE_baz_REF=refs/tags/2.0.0\n"
        + "MPM_SOURCE_baz_PATH=repo-specs/baz-marketplace.xml\n"
        + "MPM_SOURCE_baz_NAME=baz\n"
        + "MPM_SOURCE_baz_GITBASE=https://example.com\n"
    )
    mpm_file = tmp_path / ".mpm"
    mpm_file.write_text(content)
    return mpm_file


@pytest.mark.integration
class TestRemoveCoreHappyPath:
    """End-to-end happy-path scenarios."""

    def test_source_name_input_removes_block(self, tmp_path: pathlib.Path) -> None:
        """'mpm remove foo_bar' removes the foo_bar block from .mpm."""
        mpm_file = _mpm_simple(tmp_path)

        result = _run_mpm(["remove", "foo_bar", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        content = mpm_file.read_text()
        assert "MPM_SOURCE_foo_bar_URL" not in content
        assert "MPM_SOURCE_foo_bar_REF" not in content
        assert "MPM_SOURCE_foo_bar_PATH" not in content
        assert "MPM_SOURCE_foo_bar_NAME" not in content
        assert "MPM_SOURCE_foo_bar_GITBASE" not in content

    def test_entry_name_input_removes_block(self, tmp_path: pathlib.Path) -> None:
        """'mpm remove Foo-Bar' normalises to foo_bar and removes the block."""
        mpm_file = _mpm_simple(tmp_path)

        result = _run_mpm(["remove", "Foo-Bar", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        content = mpm_file.read_text()
        assert "MPM_SOURCE_foo_bar_URL" not in content
        assert "MPM_SOURCE_foo_bar_REF" not in content
        assert "MPM_SOURCE_foo_bar_PATH" not in content
        assert "MPM_SOURCE_foo_bar_NAME" not in content
        assert "MPM_SOURCE_foo_bar_GITBASE" not in content

    def test_header_preserved_after_removal(self, tmp_path: pathlib.Path) -> None:
        """Non-source config lines survive removal; no marketplace header is left behind.

        ``foo_bar`` is a plain (non-marketplace) source: the fixture carries no
        ``MPM_SOURCE_<alias>_MARKETPLACE=true`` flag, so the auto-managed
        ``CLAUDE_MARKETPLACES_DIR`` header is never present and ``mpm remove``
        leaves the remaining ``GITBASE`` / ``OTHER_VAR`` config lines intact.
        """
        mpm_file = _mpm_simple(tmp_path)

        result = _run_mpm(["remove", "foo_bar", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        content = mpm_file.read_text()
        assert "GITBASE=https://example.com" in content
        assert "OTHER_VAR=kept" in content
        assert "CLAUDE_MARKETPLACES_DIR" not in content

    def test_stdout_summary_names_removed_keys(self, tmp_path: pathlib.Path) -> None:
        """stdout names the four structural removed keys; the optional _GITBASE
        env-var line is still removed from the file even though the summary names
        only the structural keys.
        """
        mpm_file = _mpm_simple(tmp_path)

        result = _run_mpm(["remove", "foo_bar", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0
        assert "MPM_SOURCE_foo_bar_URL" in result.stdout
        assert "MPM_SOURCE_foo_bar_REF" in result.stdout
        assert "MPM_SOURCE_foo_bar_PATH" in result.stdout
        assert "MPM_SOURCE_foo_bar_NAME" in result.stdout
        assert "MPM_SOURCE_foo_bar_GITBASE" not in mpm_file.read_text(), (
            "the optional _GITBASE env-var line must be removed along with the structural block"
        )


@pytest.mark.integration
class TestRemoveCoreACCycle001:
    """AC-CYCLE-001 evidence: interleaved fixture, both input forms, re-run error."""

    def test_interleaved_removes_foo_bar_lines_only(self, tmp_path: pathlib.Path) -> None:
        """Five non-contiguous foo_bar lines removed; baz block + comments preserved."""
        mpm_file = _mpm_interleaved(tmp_path)

        result = _run_mpm(["remove", "Foo-Bar", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        content = mpm_file.read_text()

        assert "MPM_SOURCE_foo_bar_URL" not in content
        assert "MPM_SOURCE_foo_bar_REF" not in content
        assert "MPM_SOURCE_foo_bar_PATH" not in content
        assert "MPM_SOURCE_foo_bar_NAME" not in content
        assert "MPM_SOURCE_foo_bar_GITBASE" not in content

        assert "MPM_SOURCE_baz_URL=https://example.com/baz.git" in content
        assert "MPM_SOURCE_baz_REF=refs/tags/2.0.0" in content
        assert "MPM_SOURCE_baz_PATH=repo-specs/baz-marketplace.xml" in content
        assert "MPM_SOURCE_baz_NAME=baz" in content
        assert "MPM_SOURCE_baz_GITBASE=https://example.com" in content

        assert "GITBASE=https://example.com" in content

        assert "# trailing comment about baz" in content

    def test_interleaved_stdout_summary_present(self, tmp_path: pathlib.Path) -> None:
        """Summary line names the four structural removed keys."""
        mpm_file = _mpm_interleaved(tmp_path)

        result = _run_mpm(["remove", "Foo-Bar", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0
        assert "MPM_SOURCE_foo_bar_URL" in result.stdout
        assert "MPM_SOURCE_foo_bar_REF" in result.stdout
        assert "MPM_SOURCE_foo_bar_PATH" in result.stdout
        assert "MPM_SOURCE_foo_bar_NAME" in result.stdout

    def test_rerun_on_clean_file_produces_fewer_than_structural_error(self, tmp_path: pathlib.Path) -> None:
        """Re-running remove on an already-clean file produces spec-canonical hard error."""
        mpm_file = _mpm_interleaved(tmp_path)

        first = _run_mpm(["remove", "Foo-Bar", "--mpm-file", str(mpm_file)])
        assert first.returncode == 0, f"First remove failed: {first.stderr!r}"

        second = _run_mpm(["remove", "foo_bar", "--mpm-file", str(mpm_file)])
        assert second.returncode != 0, "Expected non-zero exit on second remove"
        assert "foo_bar" in second.stderr
        assert "not fully present in .mpm" in second.stderr
        assert "found 0 of 4 expected" in second.stderr


@pytest.mark.integration
class TestRemoveCoreErrorPaths:
    """Error-path end-to-end scenarios."""

    def test_missing_mpm_file_exits_nonzero(self, tmp_path: pathlib.Path) -> None:
        """'mpm remove' exits non-zero when .mpm file is absent."""
        mpm_file = tmp_path / ".mpm"

        result = _run_mpm(["remove", "foo_bar", "--mpm-file", str(mpm_file)])

        assert result.returncode != 0
        assert str(mpm_file) in result.stderr
        assert "nothing to remove" in result.stderr

    @pytest.mark.parametrize(
        "found_count",
        [0, 1, 2, 3],
        ids=["found=0", "found=1", "found=2", "found=3"],
    )
    def test_fewer_than_structural_keys_exits_nonzero(self, found_count: int, tmp_path: pathlib.Path) -> None:
        """Fewer than the 4 structural keys produces non-zero exit with spec-canonical error."""
        suffixes = ["_URL", "_REF", "_PATH", "_NAME"]
        lines = ["GITBASE=x\n"] + [f"MPM_SOURCE_foo_bar{suffix}=value\n" for suffix in suffixes[:found_count]]
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text("".join(lines))

        result = _run_mpm(["remove", "foo_bar", "--mpm-file", str(mpm_file)])

        assert result.returncode != 0
        assert "foo_bar" in result.stderr
        assert f"found {found_count} of 4 expected" in result.stderr

    def test_atomicity_file_unchanged_when_one_name_fails(self, tmp_path: pathlib.Path) -> None:
        """Multi-remove: if one name fails, the file is not written."""
        content = (
            "GITBASE=x\n"
            "MPM_SOURCE_foo_bar_URL=https://example.com/foo.git\n"
            "MPM_SOURCE_foo_bar_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_foo_bar_PATH=repo-specs/foo-marketplace.xml\n"
            "MPM_SOURCE_foo_bar_NAME=foo_bar\n"
            "MPM_SOURCE_foo_bar_GITBASE=https://example.com\n"
        )
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(content)

        result = _run_mpm(
            [
                "remove",
                "foo_bar",
                "nonexistent",
                "--mpm-file",
                str(mpm_file),
            ]
        )

        assert result.returncode != 0
        assert mpm_file.read_text() == content

    def test_multi_source_all_removed_when_all_valid(self, tmp_path: pathlib.Path) -> None:
        """Multi-remove with two valid names removes both blocks in one pass."""
        content = (
            "GITBASE=x\n"
            "MPM_SOURCE_foo_bar_URL=https://example.com/foo.git\n"
            "MPM_SOURCE_foo_bar_REF=refs/tags/1.0.0\n"
            "MPM_SOURCE_foo_bar_PATH=repo-specs/foo-marketplace.xml\n"
            "MPM_SOURCE_foo_bar_NAME=foo_bar\n"
            "MPM_SOURCE_foo_bar_GITBASE=https://example.com\n"
            "MPM_SOURCE_baz_qux_URL=https://example.com/baz.git\n"
            "MPM_SOURCE_baz_qux_REF=refs/tags/2.0.0\n"
            "MPM_SOURCE_baz_qux_PATH=repo-specs/baz-marketplace.xml\n"
            "MPM_SOURCE_baz_qux_NAME=baz_qux\n"
            "MPM_SOURCE_baz_qux_GITBASE=https://example.com\n"
        )
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(content)

        result = _run_mpm(
            [
                "remove",
                "foo_bar",
                "baz_qux",
                "--mpm-file",
                str(mpm_file),
            ]
        )

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        remaining = mpm_file.read_text()
        assert "MPM_SOURCE_foo_bar_" not in remaining
        assert "MPM_SOURCE_baz_qux_" not in remaining
        assert "GITBASE=x" in remaining

    def test_help_exits_zero(self) -> None:
        """'mpm remove --help' exits 0 with help text."""
        result = _run_mpm(["remove", "--help"])
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "--mpm-file" in combined
        assert "MPM_MPM_FILE" in combined


_MARKETPLACES_DIR_HEADER = "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces"


def _marketplace_block(alias: str) -> str:
    """Return the .mpm block for one marketplace-flagged source alias.

    Args:
        alias: The canonical source alias.

    Returns:
        The block text (trailing newline) including the ``_MARKETPLACE=true`` flag.
    """
    return (
        f"MPM_SOURCE_{alias}_URL=https://example.com/{alias}.git\n"
        f"MPM_SOURCE_{alias}_REF=refs/tags/1.0.0\n"
        f"MPM_SOURCE_{alias}_PATH=repo-specs/{alias}-marketplace.xml\n"
        f"MPM_SOURCE_{alias}_NAME={alias}\n"
        f"MPM_SOURCE_{alias}_MARKETPLACE=true\n"
    )


@pytest.mark.integration
class TestRemovePrunesMarketplacesDirHeader:
    """remove of the last marketplace dependency prunes the auto-managed header (Feature A)."""

    def test_remove_last_marketplace_prunes_header(self, tmp_path: pathlib.Path) -> None:
        """Removing the only marketplace source drops the CLAUDE_MARKETPLACES_DIR header."""
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(_MARKETPLACES_DIR_HEADER + "\n" + _marketplace_block("only_mp"))

        result = _run_mpm(["remove", "only_mp", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        content = mpm_file.read_text()
        assert "MPM_SOURCE_only_mp_" not in content
        assert "CLAUDE_MARKETPLACES_DIR" not in content, (
            "the header must be pruned once the last _MARKETPLACE=true dependency is removed"
        )

    def test_remove_one_of_two_marketplaces_keeps_header(self, tmp_path: pathlib.Path) -> None:
        """Removing one of two marketplace sources keeps the header (one remains)."""
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            _MARKETPLACES_DIR_HEADER + "\n" + _marketplace_block("first_mp") + _marketplace_block("second_mp")
        )

        result = _run_mpm(["remove", "first_mp", "--mpm-file", str(mpm_file)])

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        content = mpm_file.read_text()
        assert "MPM_SOURCE_first_mp_" not in content
        assert "MPM_SOURCE_second_mp_MARKETPLACE=true" in content
        assert content.count("CLAUDE_MARKETPLACES_DIR") == 1, (
            "the header must remain while a _MARKETPLACE=true dependency still exists"
        )

    def test_remove_keeps_cwd_clean_no_mpm_data(self, tmp_path: pathlib.Path) -> None:
        """remove serialises under MPM_HOME, leaving no .mpm-data in the project CWD (Feature B)."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(_MARKETPLACES_DIR_HEADER + "\n" + _marketplace_block("only_mp"))

        result = _run_mpm(["remove", "only_mp", "--mpm-file", str(mpm_file)], cwd=workspace)

        assert result.returncode == 0, f"stderr: {result.stderr!r}"
        assert not (workspace / ".mpm-data").exists(), (
            "mpm remove must not create a .mpm-data lock dir in the project CWD"
        )
        assert mpm_file.exists()
