"""Advanced edge-case tests for the .mpm parser.

Covers:
- AC-TEST-001: duplicate keys produce a clear error
- AC-TEST-002: = in values is split only on the first =
- AC-TEST-003: quoted values are handled consistently
- AC-TEST-004: permission-denied on .mpm read raises with file path
"""

import pathlib
import stat

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
class TestDuplicateKeys:
    """AC-TEST-001: duplicate keys produce a clear error."""

    def test_duplicate_global_key_raises(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file with the same global key defined twice must raise ValueError."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "REPO_URL=https://first.example.com\nREPO_URL=https://second.example.com\n" + _VALID_SOURCE_LINES
        )
        with pytest.raises(ValueError, match="Duplicate key 'REPO_URL'"):
            parse_mpmenv(mpmenv)

    def test_duplicate_source_key_raises(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file with the same source variable defined twice must raise ValueError."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://first.example.com\n"
            "MPM_SOURCE_build_URL=https://second.example.com\n"
            "MPM_SOURCE_build_REF=main\n"
            "MPM_SOURCE_build_PATH=meta.xml\n"
            "MPM_SOURCE_build_NAME=build\n"
            "MPM_SOURCE_build_GITBASE=https://example.com\n"
        )
        with pytest.raises(ValueError, match="Duplicate key 'MPM_SOURCE_build_URL'"):
            parse_mpmenv(mpmenv)

    @pytest.mark.parametrize(
        "key",
        [
            "SOME_KEY",
            "MPM_SOURCE_alpha_URL",
            "MPM_MARKETPLACE_INSTALL",
        ],
    )
    def test_any_duplicate_key_raises(self, tmp_path: pathlib.Path, key: str) -> None:
        """Any key appearing more than once must raise ValueError."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(f"{key}=first_value\n{key}=second_value\n" + _VALID_SOURCE_LINES)
        with pytest.raises(ValueError, match=f"Duplicate key '{key}'"):
            parse_mpmenv(mpmenv)

    def test_unique_keys_do_not_raise(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file with all unique keys must parse without error."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("REPO_URL=https://example.com\nREPO_REV=main\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["REPO_URL"] == "https://example.com"
        assert result["globals"]["REPO_REV"] == "main"


@pytest.mark.unit
class TestEqualsInValues:
    """AC-TEST-002: = in values is split only on the first =."""

    def test_value_with_multiple_equals_parsed_correctly(self, tmp_path: pathlib.Path) -> None:
        """A value containing multiple = signs must keep everything after the first =."""
        mpmenv = tmp_path / ".mpm"
        url_with_equals = "https://example.com/path?token=abc&sig=xyz==pad"
        mpmenv.write_text(f"COMPLEX_URL={url_with_equals}\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["COMPLEX_URL"] == url_with_equals

    @pytest.mark.parametrize(
        "raw_line,expected_key,expected_value",
        [
            ("KEY=a=b", "KEY", "a=b"),
            ("KEY=a=b=c", "KEY", "a=b=c"),
            ("KEY=a==b", "KEY", "a==b"),
            ("KEY==leading_equals_in_value", "KEY", "=leading_equals_in_value"),
        ],
    )
    def test_first_equals_is_separator(
        self,
        tmp_path: pathlib.Path,
        raw_line: str,
        expected_key: str,
        expected_value: str,
    ) -> None:
        """The first = in a line is always the key-value separator."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(raw_line + "\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        assert result["globals"][expected_key] == expected_value


@pytest.mark.unit
class TestQuotedValues:
    """AC-TEST-003: quoted values are handled consistently."""

    @pytest.mark.parametrize(
        "raw_value,expected",
        [
            ('"double quoted"', '"double quoted"'),
            ("'single quoted'", "'single quoted'"),
            ('"with inner = sign"', '"with inner = sign"'),
            ("bare_value", "bare_value"),
        ],
    )
    def test_quotes_preserved_as_is(
        self,
        tmp_path: pathlib.Path,
        raw_value: str,
        expected: str,
    ) -> None:
        """Quoted values are not stripped of their quotes -- stored verbatim."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(f"MY_VAR={raw_value}\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["MY_VAR"] == expected

    def test_empty_value_is_empty_string(self, tmp_path: pathlib.Path) -> None:
        """A key with no value (KEY=) parses to an empty string."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("EMPTY_VAR=\n" + _VALID_SOURCE_LINES)
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["EMPTY_VAR"] == ""


@pytest.mark.unit
class TestPermissionDenied:
    """AC-TEST-004: permission-denied on .mpm read raises with file path."""

    def test_unreadable_file_raises_with_path(self, tmp_path: pathlib.Path) -> None:
        """When .mpm exists but is not readable, PermissionError includes the path."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_VALID_SOURCE_LINES)

        mpmenv.chmod(stat.S_IWRITE)
        try:
            with pytest.raises(PermissionError) as exc_info:
                parse_mpmenv(mpmenv)
            assert str(mpmenv) in str(exc_info.value)
        finally:
            mpmenv.chmod(stat.S_IRUSR | stat.S_IWUSR)
