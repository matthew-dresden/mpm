"""Basic edge-case tests for the .mpm file parser.

Covers:
- AC-TEST-001: empty .mpm file raises ValueError with 'no sources' message
- AC-TEST-002: whitespace-only .mpm file raises ValueError
- AC-TEST-003: UTF-8 BOM prefix is stripped without error
- AC-TEST-004: CRLF line endings normalized to LF (parsed correctly)
- AC-TEST-005: comment lines (# prefix) are ignored
"""

import pathlib

import pytest

from mpm_cli.core.mpmenv import parse_mpmenv


_VALID_SOURCE_LINES = (
    "MPM_SOURCE_build_URL=https://example.com\n"
    "MPM_SOURCE_build_REF=main\n"
    "MPM_SOURCE_build_PATH=meta.xml\n"
    "MPM_SOURCE_build_NAME=build\n"
    "MPM_SOURCE_build_GITBASE=https://example.com\n"
)


@pytest.mark.unit
class TestEmptyFile:
    """AC-TEST-001: empty .mpm file raises ValueError with 'no sources' message."""

    def test_empty_file_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """A completely empty .mpm file must raise ValueError with 'No sources found'."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("")
        with pytest.raises(ValueError, match="No sources found"):
            parse_mpmenv(mpmenv)

    def test_empty_file_error_message_includes_hint(self, tmp_path: pathlib.Path) -> None:
        """The error message must include guidance about the required MPM_SOURCE_<name>_URL pattern."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("")
        with pytest.raises(ValueError, match="MPM_SOURCE_"):
            parse_mpmenv(mpmenv)


@pytest.mark.unit
class TestWhitespaceOnlyFile:
    """AC-TEST-002: whitespace-only .mpm file raises ValueError."""

    @pytest.mark.parametrize(
        "content",
        [
            "   ",
            "\t",
            "\n",
            "  \n  \n  ",
            "\t\n\t\n",
            "   \t   \n",
        ],
    )
    def test_whitespace_only_raises_value_error(self, tmp_path: pathlib.Path, content: str) -> None:
        """A .mpm file containing only whitespace must raise ValueError with 'No sources found'."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(content)
        with pytest.raises(ValueError, match="No sources found"):
            parse_mpmenv(mpmenv)


@pytest.mark.unit
class TestUtf8BomStripping:
    """AC-TEST-003: UTF-8 BOM prefix is stripped without error."""

    def test_bom_prefixed_file_parses_without_error(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file with a UTF-8 BOM prefix (EF BB BF) must parse successfully."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(b"\xef\xbb\xbf" + _VALID_SOURCE_LINES.encode("utf-8"))
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["build"]

    def test_bom_not_present_in_parsed_keys(self, tmp_path: pathlib.Path) -> None:
        """No BOM codepoint (U+FEFF) must appear in any parsed key after BOM stripping."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(b"\xef\xbb\xbf" + _VALID_SOURCE_LINES.encode("utf-8"))
        result = parse_mpmenv(mpmenv)
        for source_name in result["MPM_SOURCES"]:
            assert "\ufeff" not in source_name, f"BOM found in source name: {source_name!r}"
        for key in result.get("globals", {}):
            assert "\ufeff" not in key, f"BOM found in globals key: {key!r}"

    def test_bom_prefixed_and_plain_files_produce_equal_results(self, tmp_path: pathlib.Path) -> None:
        """Files with and without a UTF-8 BOM must yield identical parsed results."""
        with_bom = tmp_path / ".mpm_bom"
        with_bom.write_bytes(b"\xef\xbb\xbf" + _VALID_SOURCE_LINES.encode("utf-8"))

        without_bom = tmp_path / ".mpm_plain"
        without_bom.write_bytes(_VALID_SOURCE_LINES.encode("utf-8"))

        assert parse_mpmenv(with_bom) == parse_mpmenv(without_bom)

    def test_bom_only_file_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """A file that contains only the UTF-8 BOM bytes must raise ValueError (no sources)."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(b"\xef\xbb\xbf")
        with pytest.raises(ValueError, match="No sources found"):
            parse_mpmenv(mpmenv)


@pytest.mark.unit
class TestCrlfLineEndings:
    """AC-TEST-004: CRLF line endings normalized to LF (parsed correctly)."""

    def test_crlf_file_parses_correctly(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file written with CRLF (\\r\\n) line endings must parse identically to LF."""
        crlf_content = _VALID_SOURCE_LINES.replace("\n", "\r\n")
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(crlf_content.encode("utf-8"))
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["build"]
        assert result["sources"]["build"]["url"] == "https://example.com"
        assert result["sources"]["build"]["ref"] == "main"
        assert result["sources"]["build"]["path"] == "meta.xml"

    def test_crlf_and_lf_produce_equal_results(self, tmp_path: pathlib.Path) -> None:
        """Files with CRLF and LF endings must yield identical parsed results."""
        lf_file = tmp_path / ".mpm_lf"
        lf_file.write_bytes(_VALID_SOURCE_LINES.encode("utf-8"))

        crlf_file = tmp_path / ".mpm_crlf"
        crlf_file.write_bytes(_VALID_SOURCE_LINES.replace("\n", "\r\n").encode("utf-8"))

        assert parse_mpmenv(lf_file) == parse_mpmenv(crlf_file)

    def test_crlf_with_global_key_parses_correctly(self, tmp_path: pathlib.Path) -> None:
        """Global keys in CRLF files must be parsed with correct key and value (no \\r in value)."""
        content = "EXTRA_VAR=some_value\r\n" + _VALID_SOURCE_LINES.replace("\n", "\r\n")
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(content.encode("utf-8"))
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["EXTRA_VAR"] == "some_value"
        assert "\r" not in result["globals"]["EXTRA_VAR"]

    def test_mixed_line_endings_parse_correctly(self, tmp_path: pathlib.Path) -> None:
        """A file mixing CRLF and LF line endings must parse all keys correctly."""
        content = (
            "MPM_SOURCE_build_URL=https://example.com\r\n"
            "MPM_SOURCE_build_REF=main\n"
            "MPM_SOURCE_build_PATH=meta.xml\r\n"
            "MPM_SOURCE_build_NAME=build\r\n"
            "MPM_SOURCE_build_GITBASE=https://example.com\r\n"
        )
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(content.encode("utf-8"))
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["build"]
        assert result["sources"]["build"]["ref"] == "main"


@pytest.mark.unit
class TestCommentLines:
    """AC-TEST-005: comment lines (# prefix) are ignored."""

    def test_comment_line_at_top_ignored(self, tmp_path: pathlib.Path) -> None:
        """A leading comment line must not appear in parsed output."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("# This is a top-level comment\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        for key in result.get("globals", {}):
            assert not key.startswith("#"), f"Comment line leaked into globals: {key!r}"

    def test_comment_line_inline_ignored(self, tmp_path: pathlib.Path) -> None:
        """Comment lines interspersed with real entries must be fully ignored."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "# Header comment\n"
            "MPM_SOURCE_build_URL=https://example.com\n"
            "# URL comment\n"
            "MPM_SOURCE_build_REF=main\n"
            "# Revision comment\n"
            "MPM_SOURCE_build_PATH=meta.xml\n"
            "MPM_SOURCE_build_NAME=build\n"
            "MPM_SOURCE_build_GITBASE=https://example.com\n"
            "# Trailing comment\n"
        )
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["build"]

    def test_comment_only_file_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file containing only comments must raise ValueError (no sources)."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("# First comment\n# Second comment\n# Third comment\n")
        with pytest.raises(ValueError, match="No sources found"):
            parse_mpmenv(mpmenv)

    @pytest.mark.parametrize(
        "comment_line",
        [
            "# simple comment",
            "#no space after hash",
            "# comment with = sign inside",
            "# KEY=value comment",
        ],
    )
    def test_various_comment_formats_are_ignored(self, tmp_path: pathlib.Path, comment_line: str) -> None:
        """Comments in various formats must never be parsed as key-value pairs."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(comment_line + "\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        for key in result.get("globals", {}):
            assert not key.startswith("#"), f"Comment leaked as key: {key!r}"
