"""Unit tests for mpm_cli.core.mpmenv_writer.

Covers the idempotent auto-management of the ``CLAUDE_MARKETPLACES_DIR`` header:

- ensure inserts the exact literal header once, after any leading comment/blank
  preamble, preserving the file's dominant newline (LF and CRLF).
- ensure is a no-op when the header is already present, including when an operator
  has hand-set a custom value (never clobbered, never duplicated).
- the ``hold_lock=False`` path writes directly without acquiring the workspace lock.
- prune removes the header when no ``_MARKETPLACE=true`` flag remains, keeps it when
  one remains, tolerates a hand-written ``=false``, and is a no-op when absent.
- the ``"_MARKETPLACE"``-substring trap does not cause a false marketplace match on
  the ``CLAUDE_MARKETPLACES_DIR`` header itself.
"""

import pathlib
from unittest.mock import patch

import pytest

from mpm_cli.constants import (
    MPM_HEADER_CLAUDE_MARKETPLACES_DIR,
    MARKETPLACE_DIR_GLOBAL_KEY,
)
from mpm_cli.core.mpmenv_writer import (
    ensure_claude_marketplaces_dir,
    guard_mpm_file_not_dir,
    has_claude_marketplaces_dir_header,
    prune_claude_marketplaces_dir_if_unused,
)


def _read(mpm_file: pathlib.Path) -> str:
    """Return the raw text of ``mpm_file``.

    Args:
        mpm_file: Path to the ``.mpm`` file.

    Returns:
        The file content as a string.
    """
    return mpm_file.read_text(encoding="utf-8")


def _header_count(text: str) -> int:
    """Return how many lines parse to the marketplace-dir global key.

    Args:
        text: Raw ``.mpm`` content.

    Returns:
        The number of ``CLAUDE_MARKETPLACES_DIR`` lines.
    """
    count = 0
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.split("=", 1)[0].strip() == MARKETPLACE_DIR_GLOBAL_KEY:
            count += 1
    return count


@pytest.mark.unit
class TestEnsureClaudeMarketplacesDir:
    """Tests for ``ensure_claude_marketplaces_dir``."""

    def test_inserts_exact_header_once_when_absent(self, tmp_path: pathlib.Path) -> None:
        """The exact literal header is inserted exactly once when absent.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text("MPM_SOURCE_FOO_URL=https://example.com/foo.git\n", encoding="utf-8")

        changed = ensure_claude_marketplaces_dir(mpm_file)

        assert changed is True
        text = _read(mpm_file)
        assert MPM_HEADER_CLAUDE_MARKETPLACES_DIR in text
        assert _header_count(text) == 1

    def test_inserts_into_empty_file(self, tmp_path: pathlib.Path) -> None:
        """The header is created even when the file does not yet exist.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"

        changed = ensure_claude_marketplaces_dir(mpm_file)

        assert changed is True
        assert _read(mpm_file) == MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\n"

    def test_idempotent_noop_when_present(self, tmp_path: pathlib.Path) -> None:
        """A second ensure call is a no-op and never duplicates the header.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text("MPM_SOURCE_FOO_URL=https://example.com/foo.git\n", encoding="utf-8")

        first = ensure_claude_marketplaces_dir(mpm_file)
        after_first = _read(mpm_file)
        second = ensure_claude_marketplaces_dir(mpm_file)
        after_second = _read(mpm_file)

        assert first is True
        assert second is False
        assert after_first == after_second
        assert _header_count(after_second) == 1

    def test_does_not_clobber_custom_value(self, tmp_path: pathlib.Path) -> None:
        """An operator's custom header value is preserved, not overwritten.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        custom = f"{MARKETPLACE_DIR_GLOBAL_KEY}=/custom/marketplaces\n"
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(custom + "MPM_SOURCE_FOO_URL=https://example.com/foo.git\n", encoding="utf-8")

        changed = ensure_claude_marketplaces_dir(mpm_file)

        text = _read(mpm_file)
        assert changed is False
        assert "/custom/marketplaces" in text
        assert MPM_HEADER_CLAUDE_MARKETPLACES_DIR not in text
        assert _header_count(text) == 1

    def test_inserted_after_leading_comments_and_blanks(self, tmp_path: pathlib.Path) -> None:
        """The header lands after a leading comment/blank preamble, with a blank
        line separating it from the dependency block.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "# preamble comment\n\nMPM_SOURCE_FOO_URL=https://example.com/foo.git\n",
            encoding="utf-8",
        )

        ensure_claude_marketplaces_dir(mpm_file)

        lines = _read(mpm_file).splitlines()
        assert lines[0] == "# preamble comment"
        assert lines[1] == ""
        assert lines[2] == MPM_HEADER_CLAUDE_MARKETPLACES_DIR
        assert lines[3] == ""
        assert lines[4] == "MPM_SOURCE_FOO_URL=https://example.com/foo.git"

    def test_preserves_lf_newline(self, tmp_path: pathlib.Path) -> None:
        """The inserted header uses LF when the file uses LF.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_bytes(b"MPM_SOURCE_FOO_URL=https://example.com/foo.git\n")

        ensure_claude_marketplaces_dir(mpm_file)

        data = mpm_file.read_bytes()
        assert b"\r\n" not in data
        assert (MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\n").encode("utf-8") in data

    def test_preserves_crlf_newline(self, tmp_path: pathlib.Path) -> None:
        """The inserted header uses CRLF when the file uses CRLF.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_bytes(b"MPM_SOURCE_FOO_URL=https://example.com/foo.git\r\n")

        ensure_claude_marketplaces_dir(mpm_file)

        data = mpm_file.read_bytes()
        assert (MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\r\n").encode("utf-8") in data

    def test_hold_lock_false_writes_without_acquiring(self, tmp_path: pathlib.Path) -> None:
        """``hold_lock=False`` writes without acquiring the workspace lock.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text("MPM_SOURCE_FOO_URL=https://example.com/foo.git\n", encoding="utf-8")

        with patch("mpm_cli.core.mpmenv_writer.mpm_workspace_lock") as mock_lock:
            changed = ensure_claude_marketplaces_dir(mpm_file, hold_lock=False)

        assert changed is True
        mock_lock.assert_not_called()
        assert MPM_HEADER_CLAUDE_MARKETPLACES_DIR in _read(mpm_file)

    def test_hold_lock_true_acquires_lock(self, tmp_path: pathlib.Path) -> None:
        """``hold_lock=True`` acquires the workspace lock once around the write.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text("MPM_SOURCE_FOO_URL=https://example.com/foo.git\n", encoding="utf-8")

        with patch("mpm_cli.core.mpmenv_writer.mpm_workspace_lock") as mock_lock:
            ensure_claude_marketplaces_dir(mpm_file, hold_lock=True)

        mock_lock.assert_called_once()


@pytest.mark.unit
class TestPruneClaudeMarketplacesDir:
    """Tests for ``prune_claude_marketplaces_dir_if_unused``."""

    def test_removes_when_no_marketplace_remains(self, tmp_path: pathlib.Path) -> None:
        """The header is removed when no ``_MARKETPLACE=true`` flag remains.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\nMPM_SOURCE_FOO_URL=https://example.com/foo.git\n",
            encoding="utf-8",
        )

        changed = prune_claude_marketplaces_dir_if_unused(mpm_file)

        text = _read(mpm_file)
        assert changed is True
        assert _header_count(text) == 0
        assert "MPM_SOURCE_FOO_URL=https://example.com/foo.git" in text

    def test_removes_custom_value_when_no_marketplace_remains(self, tmp_path: pathlib.Path) -> None:
        """Pruning is unconditional of the header's value (custom value removed too).

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            f"{MARKETPLACE_DIR_GLOBAL_KEY}=/custom/marketplaces\nMPM_SOURCE_FOO_URL=https://example.com/foo.git\n",
            encoding="utf-8",
        )

        changed = prune_claude_marketplaces_dir_if_unused(mpm_file)

        text = _read(mpm_file)
        assert changed is True
        assert _header_count(text) == 0
        assert "/custom/marketplaces" not in text

    def test_keeps_when_true_marketplace_remains(self, tmp_path: pathlib.Path) -> None:
        """The header is kept while any ``_MARKETPLACE=true`` flag remains.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        original = (
            MPM_HEADER_CLAUDE_MARKETPLACES_DIR
            + "\nMPM_SOURCE_FOO_URL=https://example.com/foo.git\nMPM_SOURCE_FOO_MARKETPLACE=true\n"
        )
        mpm_file.write_text(original, encoding="utf-8")

        changed = prune_claude_marketplaces_dir_if_unused(mpm_file)

        assert changed is False
        assert _read(mpm_file) == original

    def test_tolerates_handwritten_false_flag(self, tmp_path: pathlib.Path) -> None:
        """A hand-written ``_MARKETPLACE=false`` does not count as remaining.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            MPM_HEADER_CLAUDE_MARKETPLACES_DIR
            + "\nMPM_SOURCE_FOO_URL=https://example.com/foo.git\nMPM_SOURCE_FOO_MARKETPLACE=false\n",
            encoding="utf-8",
        )

        changed = prune_claude_marketplaces_dir_if_unused(mpm_file)

        text = _read(mpm_file)
        assert changed is True
        assert _header_count(text) == 0
        assert "MPM_SOURCE_FOO_MARKETPLACE=false" in text

    def test_noop_when_header_absent(self, tmp_path: pathlib.Path) -> None:
        """Pruning is a no-op when the header is absent.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        original = "MPM_SOURCE_FOO_URL=https://example.com/foo.git\n"
        mpm_file.write_text(original, encoding="utf-8")

        changed = prune_claude_marketplaces_dir_if_unused(mpm_file)

        assert changed is False
        assert _read(mpm_file) == original

    def test_substring_trap_does_not_false_match(self, tmp_path: pathlib.Path) -> None:
        """The header alone is treated as no marketplace enabled (substring trap).

        ``"_MARKETPLACE"`` is a substring of ``"CLAUDE_MARKETPLACES_DIR"``; a
        substring test would wrongly keep the header. Key-equality matching prunes
        it because no source marketplace flag remains.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\n", encoding="utf-8")

        changed = prune_claude_marketplaces_dir_if_unused(mpm_file)

        assert changed is True
        assert _header_count(_read(mpm_file)) == 0

    def test_hold_lock_false_writes_without_acquiring(self, tmp_path: pathlib.Path) -> None:
        """``hold_lock=False`` prunes without acquiring the workspace lock.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\nMPM_SOURCE_FOO_URL=https://example.com/foo.git\n",
            encoding="utf-8",
        )

        with patch("mpm_cli.core.mpmenv_writer.mpm_workspace_lock") as mock_lock:
            changed = prune_claude_marketplaces_dir_if_unused(mpm_file, hold_lock=False)

        assert changed is True
        mock_lock.assert_not_called()
        assert _header_count(_read(mpm_file)) == 0


@pytest.mark.unit
class TestHasClaudeMarketplacesDirHeader:
    """Tests for the read-only ``has_claude_marketplaces_dir_header`` predicate."""

    def test_true_when_present(self, tmp_path: pathlib.Path) -> None:
        """Returns True when the header line is present.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(MPM_HEADER_CLAUDE_MARKETPLACES_DIR + "\n", encoding="utf-8")

        assert has_claude_marketplaces_dir_header(mpm_file) is True

    def test_false_when_absent_or_missing(self, tmp_path: pathlib.Path) -> None:
        """Returns False for a header-less file and for an absent file.

        Args:
            tmp_path: Pytest-provided temporary directory.
        """
        present = tmp_path / "present.mpm"
        present.write_text("MPM_SOURCE_FOO_URL=https://example.com/foo.git\n", encoding="utf-8")
        absent = tmp_path / "absent.mpm"

        assert has_claude_marketplaces_dir_header(present) is False
        assert has_claude_marketplaces_dir_header(absent) is False


@pytest.mark.unit
class TestGuardMPMFileNotDir:
    """guard_mpm_file_not_dir fails fast with an actionable message on a .mpm directory."""

    def test_directory_raises_clean_error_and_exits_one(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A .mpm directory yields the clean error naming the exact rm command, exit 1."""
        mpm_dir = tmp_path / ".mpm"
        mpm_dir.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            guard_mpm_file_not_dir(mpm_dir)

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        resolved = str(mpm_dir.resolve())
        assert "found a .mpm folder" in err
        assert resolved in err
        assert f"rm -rf {resolved}" in err
        assert "re-run your mpm command" in err
        assert "Is a directory" not in err

    def test_missing_path_is_noop(self, tmp_path: pathlib.Path) -> None:
        """A non-existent .mpm path is not a directory, so the guard returns without exiting."""
        guard_mpm_file_not_dir(tmp_path / ".mpm")

    def test_regular_file_is_noop(self, tmp_path: pathlib.Path) -> None:
        """An existing .mpm FILE is allowed; the guard only rejects a directory."""
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text("MPM_SOURCE_foo_URL=https://example.com/foo.git\n", encoding="utf-8")

        guard_mpm_file_not_dir(mpm_file)
