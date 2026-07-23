"""Unit tests for mpm_cli.completions.source_names -- AC-TEST-001.

Covers: happy path, empty .mpm, malformed .mpm (no MPM_SOURCE_*_URL keys),
missing file, prefix filter, MPM_COMPLETION_ENABLED=0.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from mpm_cli.completions.source_names import (
    _extract_source_names,
    _handle,
    _resolve_mpm_file,
    complete,
)


def _write_mpm(path: Path, content: str) -> None:
    """Write content to path with mode 0600 (owner-read/write only)."""
    path.write_text(content)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


@pytest.mark.unit
class TestExtractSourceNames:
    """_extract_source_names() reads MPM_SOURCE_<name>_URL keys from raw text."""

    def test_three_sources_returned_sorted(self) -> None:
        """Happy path: three MPM_SOURCE_*_URL keys return three sorted names."""
        content = (
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n"
        )
        assert _extract_source_names(content) == ["bar", "baz", "foo"]

    def test_empty_content_returns_empty(self) -> None:
        """No MPM_SOURCE_*_URL keys -> empty list."""
        assert _extract_source_names("") == []

    def test_comments_and_blanks_ignored(self) -> None:
        """Comments and blank lines are skipped."""
        content = (
            "# This is a comment\n"
            "\n"
            "MPM_SOURCE_alpha_URL=https://example.com/alpha\n"
            "MPM_SOURCE_REVISION=should-not-appear\n"
        )
        assert _extract_source_names(content) == ["alpha"]

    def test_non_url_keys_ignored(self) -> None:
        """MPM_SOURCE_<name>_REVISION and _PATH keys are not emitted."""
        content = (
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_foo_REVISION=abc123\n"
            "MPM_SOURCE_foo_PATH=vendor/foo\n"
        )
        assert _extract_source_names(content) == ["foo"]

    def test_malformed_no_url_keys_returns_empty(self) -> None:
        """File with no MPM_SOURCE_*_URL keys returns empty list (malformed)."""
        content = "GITBASE=https://example.com\nMPM_MARKETPLACE_INSTALL=false\n"
        assert _extract_source_names(content) == []

    def test_name_is_normalized_portion(self) -> None:
        """The <name> in MPM_SOURCE_<name>_URL is returned as-is (already normalized)."""
        content = "MPM_SOURCE_my_source_URL=https://example.com/repo\n"
        assert _extract_source_names(content) == ["my_source"]

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("MPM_SOURCE_a_URL=val", ["a"]),
            ("MPM_SOURCE_a_b_c_URL=val", ["a_b_c"]),
            ("MPM_SOURCE__URL=val", []),
        ],
        ids=["single-char", "multi-underscore", "empty-name"],
    )
    def test_parametrized_edge_cases(self, line: str, expected: list[str]) -> None:
        """Parametrized edge cases for _extract_source_names."""
        assert _extract_source_names(line) == expected


@pytest.mark.unit
class TestResolveMPMFile:
    """_resolve_mpm_file() returns a Path based on MPM_MPM_FILE env var."""

    def test_uses_env_var_when_set(self, tmp_path: Path) -> None:
        """MPM_MPM_FILE env var is used when set."""
        custom = str(tmp_path / "custom.mpm")
        with patch.dict(os.environ, {"MPM_MPM_FILE": custom}):
            assert _resolve_mpm_file() == Path(custom)

    def test_defaults_to_dot_mpm(self) -> None:
        """When MPM_MPM_FILE is not set, defaults to ./.mpm."""
        env_without = {k: v for k, v in os.environ.items() if k != "MPM_MPM_FILE"}
        with patch.dict(os.environ, env_without, clear=True):
            result = _resolve_mpm_file()
        assert result == Path("./.mpm")


@pytest.mark.unit
class TestCompleteDisabled:
    """MPM_COMPLETION_ENABLED=0 causes complete() to return [] immediately."""

    def test_disabled_returns_empty(self, tmp_path: Path) -> None:
        """MPM_COMPLETION_ENABLED=0 -> empty list, no file read attempted."""
        mpm_path = tmp_path / ".mpm"

        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "0",
                "MPM_MPM_FILE": str(mpm_path),
            },
        ):
            result = complete("")
        assert result == []

    def test_disabled_does_not_write_log(self, tmp_path: Path) -> None:
        """MPM_COMPLETION_ENABLED=0 does not touch completion-errors.log."""
        log_path = tmp_path / "completion-errors.log"
        mpm_path = tmp_path / ".mpm"
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "0",
                "MPM_MPM_FILE": str(mpm_path),
                "MPM_COMPLETION_LOG": str(log_path),
                "MPM_HOME": str(tmp_path),
            },
        ):
            complete("")
        assert not log_path.exists()


@pytest.mark.unit
class TestCompleteHappyPath:
    """complete() returns sorted, prefix-filtered source names from .mpm."""

    def test_three_sources_no_prefix(self, tmp_path: Path) -> None:
        """AC-FUNC-001: three sources, empty prefix -> all three sorted."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n",
        )
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = complete("")
        assert result == ["bar", "baz", "foo"]

    def test_prefix_filter(self, tmp_path: Path) -> None:
        """AC-FUNC-002: prefix 'f' returns only entries starting with 'f'."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n",
        )
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = complete("f")
        assert result == ["foo"]

    def test_normalized_names_emitted(self, tmp_path: Path) -> None:
        """AC-FUNC-003: names are already normalized (MPM_SOURCE_<name>_URL)."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_my_source_URL=https://example.com/my-source\n",
        )
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = complete("")
        assert result == ["my_source"]

    @pytest.mark.parametrize(
        "prefix,expected",
        [
            ("", ["bar", "baz", "foo"]),
            ("b", ["bar", "baz"]),
            ("ba", ["bar", "baz"]),
            ("bar", ["bar"]),
            ("x", []),
            ("foo", ["foo"]),
        ],
        ids=["empty", "b-prefix", "ba-prefix", "bar-exact", "no-match", "foo-exact"],
    )
    def test_prefix_filter_parametrized(self, tmp_path: Path, prefix: str, expected: list[str]) -> None:
        """Parametrized prefix-filter coverage."""
        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\n"
            "MPM_SOURCE_bar_URL=https://example.com/bar\n"
            "MPM_SOURCE_baz_URL=https://example.com/baz\n",
        )
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = complete(prefix)
        assert result == expected


@pytest.mark.unit
class TestCompleteMissingFile:
    """complete() returns empty and logs when MPM_MPM_FILE does not exist."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """AC-FUNC-004: missing file -> empty stdout, exit 0 (no exception raised)."""
        mpm = tmp_path / "nonexistent.mpm"
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = complete("")
        assert result == []

    def test_missing_file_writes_log_entry(self, tmp_path: Path) -> None:
        """AC-FUNC-004: missing file writes FileNotFoundError to completion-errors.log."""
        mpm = tmp_path / "nonexistent.mpm"
        log_path = tmp_path / "completion-errors.log"
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_COMPLETION_LOG": str(log_path),
                "MPM_HOME": str(tmp_path),
            },
        ):
            complete("")
        assert log_path.exists()
        content = log_path.read_text()
        assert "__complete_source_names_in_mpm" in content
        assert "FileNotFoundError" in content
        assert str(mpm) in content


@pytest.mark.unit
class TestCompleteMalformedFile:
    """complete() with a .mpm that has no MPM_SOURCE_*_URL keys."""

    def test_malformed_returns_empty(self, tmp_path: Path) -> None:
        """AC-FUNC-005: .mpm with no MPM_SOURCE_*_URL -> empty stdout."""
        mpm = tmp_path / ".mpm"
        _write_mpm(mpm, "GITBASE=https://example.com\nMPM_MARKETPLACE_INSTALL=false\n")
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = complete("")
        assert result == []

    def test_malformed_writes_log_entry(self, tmp_path: Path) -> None:
        """AC-FUNC-005: malformed .mpm writes a structured log entry."""
        mpm = tmp_path / ".mpm"
        _write_mpm(mpm, "GITBASE=https://example.com\n")
        log_path = tmp_path / "completion-errors.log"
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_COMPLETION_LOG": str(log_path),
                "MPM_HOME": str(tmp_path),
            },
        ):
            complete("")
        assert log_path.exists()
        content = log_path.read_text()
        assert "__complete_source_names_in_mpm" in content
        assert "ValueError" in content


@pytest.mark.unit
class TestHandle:
    """_handle() calls complete() and writes one name per line to stdout."""

    def test_handle_prints_names(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """_handle() with three-source .mpm prints sorted names to stdout."""
        import argparse

        mpm = tmp_path / ".mpm"
        _write_mpm(
            mpm,
            "MPM_SOURCE_foo_URL=https://example.com/foo\nMPM_SOURCE_bar_URL=https://example.com/bar\n",
        )
        args = argparse.Namespace(current_token="")
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = _handle(args)
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "bar\nfoo\n"

    def test_handle_returns_zero(self, tmp_path: Path) -> None:
        """_handle() always returns 0 even when no names found."""
        import argparse

        mpm = tmp_path / "missing.mpm"
        args = argparse.Namespace(current_token="")
        with patch.dict(
            os.environ,
            {
                "MPM_COMPLETION_ENABLED": "1",
                "MPM_MPM_FILE": str(mpm),
                "MPM_HOME": str(tmp_path),
            },
        ):
            result = _handle(args)
        assert result == 0
