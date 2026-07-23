"""Unit tests for the mpm list command constants.

Verifies constants.py defines the MPM_LIST_* output-format, status, scope,
column, note, and JSON-indent constants with the correct values, and that no
inline string literals for the status / scope / format tokens appear in
commands/list.py (CLAUDE.md NO HARD-CODED VALUES).
"""

from __future__ import annotations

import pathlib
import re

import pytest

from mpm_cli import constants


@pytest.mark.unit
class TestListConstants:
    """The MPM_LIST_* constants exist with the expected values."""

    def test_output_format_env_and_values(self) -> None:
        """The output-format env name and its table/json values are defined."""
        assert constants.MPM_LIST_OUTPUT_FORMAT == "MPM_LIST_OUTPUT_FORMAT"
        assert constants.MPM_LIST_OUTPUT_FORMAT_TABLE == "table"
        assert constants.MPM_LIST_OUTPUT_FORMAT_JSON == "json"
        assert constants.MPM_LIST_OUTPUT_FORMAT_DEFAULT == constants.MPM_LIST_OUTPUT_FORMAT_TABLE

    def test_output_format_choices(self) -> None:
        """The output-format choices tuple carries exactly table then json."""
        assert constants.MPM_LIST_OUTPUT_FORMAT_CHOICES == ("table", "json")

    def test_distinct_from_search_list_constants(self) -> None:
        """The list command's format env must not collide with search's MPM_LIST_FORMAT / MPM_LIST_LIMIT."""
        assert constants.MPM_LIST_OUTPUT_FORMAT != "MPM_LIST_FORMAT"
        assert hasattr(constants, "MPM_LIST_LIMIT")
        assert constants.MPM_LIST_OUTPUT_FORMAT != constants.MPM_LIST_LIMIT

    def test_status_values(self) -> None:
        """The three status tags are defined with hyphenated values."""
        assert constants.MPM_LIST_STATUS_INSTALLED == "installed"
        assert constants.MPM_LIST_STATUS_NOT_INSTALLED == "not-installed"
        assert constants.MPM_LIST_STATUS_ORPHAN == "orphan"

    def test_status_choices(self) -> None:
        """The status-choices tuple carries the three tags in canonical order."""
        assert constants.MPM_LIST_STATUS_CHOICES == ("installed", "not-installed", "orphan")

    def test_scope_values(self) -> None:
        """The direct/transitive scope tags are defined."""
        assert constants.MPM_LIST_SCOPE_DIRECT == "direct"
        assert constants.MPM_LIST_SCOPE_TRANSITIVE == "transitive"

    def test_column_headers(self) -> None:
        """The table column headers are defined."""
        assert constants.MPM_LIST_COLUMN_SOURCE == "SOURCE"
        assert constants.MPM_LIST_COLUMN_REF == "REF"
        assert constants.MPM_LIST_COLUMN_STATUS == "STATUS"

    def test_json_indent_is_non_negative_int(self) -> None:
        """The JSON indent is a non-negative integer."""
        assert isinstance(constants.MPM_LIST_JSON_INDENT, int)
        assert constants.MPM_LIST_JSON_INDENT >= 0

    def test_notes_defined(self) -> None:
        """The empty and no-lockfile stderr notes are defined."""
        assert isinstance(constants.MPM_LIST_NO_SOURCES_NOTE, str)
        assert isinstance(constants.MPM_LIST_NO_LOCKFILE_NOTE, str)
        assert constants.MPM_LIST_NO_SOURCES_NOTE
        assert constants.MPM_LIST_NO_LOCKFILE_NOTE


@pytest.mark.unit
class TestListConstantsNoInlineLiterals:
    """No bare status / scope / format string literals appear in commands/list.py."""

    @pytest.fixture
    def list_py_source(self) -> str:
        """Read the source of commands/list.py for inspection."""
        src_root = pathlib.Path(__file__).parent.parent.parent / "src" / "mpm_cli"
        list_path = src_root / "commands" / "list.py"
        assert list_path.exists(), f"commands/list.py not found at {list_path}"
        return list_path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("token", ["installed", "not-installed", "orphan", "direct", "transitive", "table", "json"])
    def test_no_inline_token_literal(self, list_py_source: str, token: str) -> None:
        """The token must not appear as a bare quoted string literal in list.py."""
        literal_pattern = re.compile(rf"""(?<!\w)['"]{re.escape(token)}['"]""")
        matches = literal_pattern.findall(list_py_source)
        assert not matches, (
            f"Found bare {token!r} string literal(s) in commands/list.py. "
            "Use the corresponding MPM_LIST_* constant instead. "
            f"Matched {len(matches)} occurrence(s)."
        )

    def test_list_imports_list_constants(self, list_py_source: str) -> None:
        """commands/list.py must reference the MPM_LIST_* status and format constants."""
        assert "MPM_LIST_STATUS_CHOICES" in list_py_source
        assert "MPM_LIST_OUTPUT_FORMAT_CHOICES" in list_py_source
