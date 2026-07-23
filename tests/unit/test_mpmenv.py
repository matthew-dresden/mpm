"""Tests for the mpmenv parser module."""

import os
import pathlib
import stat

import pytest

from mpm_cli.core.mpmenv import (
    _check_write_permission,
    parse_mpmenv,
    validate_sources,
)


def _block(
    alias: str,
    *,
    url: str = "https://example.com",
    ref: str = "main",
    path: str = "meta.xml",
    name: str | None = None,
    gitbase: str = "https://example.com",
) -> str:
    """Render a complete alias-keyed .mpm source block (spec Section 5.1).

    Every required structural suffix (_URL, _REF, _PATH, _NAME) is emitted, plus
    an optional _GITBASE env-var line (one member of the open per-dependency
    env-var set). ``name`` defaults to the alias when not given.
    """
    manifest_name = alias if name is None else name
    return (
        f"MPM_SOURCE_{alias}_URL={url}\n"
        f"MPM_SOURCE_{alias}_REF={ref}\n"
        f"MPM_SOURCE_{alias}_PATH={path}\n"
        f"MPM_SOURCE_{alias}_NAME={manifest_name}\n"
        f"MPM_SOURCE_{alias}_GITBASE={gitbase}\n"
    )


@pytest.mark.unit
class TestValidParsing:
    """Verify valid .mpm parsing."""

    def test_parses_mpm_sources(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build") + _block("marketplaces", path="mp.xml"))
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["build", "marketplaces"]
        assert "build" in result["sources"]
        assert "marketplaces" in result["sources"]

    def test_surfaces_ref_name_gitbase_keys(self, tmp_path: pathlib.Path) -> None:
        """Each parsed source dict surfaces ref / name / gitbase (no 'revision')."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            _block(
                "build",
                url="https://example.com/org/build.git",
                ref=">=1.0.0,<2.0.0",
                path="repo-specs/build.xml",
                name="build-manifest",
                gitbase="https://example.com/org",
            )
        )
        result = parse_mpmenv(mpmenv)
        source = result["sources"]["build"]
        assert source["url"] == "https://example.com/org/build.git"
        assert source["ref"] == ">=1.0.0,<2.0.0"
        assert source["path"] == "repo-specs/build.xml"
        assert source["name"] == "build-manifest"
        assert source["env"]["GITBASE"] == "https://example.com/org"
        assert "gitbase" not in source, "_GITBASE is now collected into source['env'], not a top-level key"
        assert "revision" not in source

    def test_parses_globals(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("REPO_URL=https://example.com\nREPO_REV=v2.0.0\n" + _block("build"))
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["REPO_URL"] == "https://example.com"
        assert result["globals"]["REPO_REV"] == "v2.0.0"

    def test_parses_per_alias_marketplace_true(self, tmp_path: pathlib.Path) -> None:
        """An explicit per-alias MPM_SOURCE_<alias>_MARKETPLACE=true parses to True
        on that source only (spec Section 5.1 / FR-17).
        """
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build") + "MPM_SOURCE_build_MARKETPLACE=true\n" + _block("plain", path="plain.xml"))
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["build"]["marketplace"] is True

        assert result["sources"]["plain"]["marketplace"] is False

        assert "MPM_SOURCE_build_MARKETPLACE" not in result["globals"]
        assert "MPM_MARKETPLACE_INSTALL" not in result

    def test_per_alias_marketplace_case_insensitive_true(self, tmp_path: pathlib.Path) -> None:
        """The per-alias flag parse is case-insensitive for the true token."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build") + "MPM_SOURCE_build_MARKETPLACE=TRUE\n")
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["build"]["marketplace"] is True

    def test_per_alias_marketplace_false_tolerated(self, tmp_path: pathlib.Path) -> None:
        """A hand-written MPM_SOURCE_<alias>_MARKETPLACE=false is tolerated on read
        and parses to False (mpm never emits it, but reads it without error).
        """
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build") + "MPM_SOURCE_build_MARKETPLACE=false\n")
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["build"]["marketplace"] is False
        assert "MPM_SOURCE_build_MARKETPLACE" not in result["globals"]


@pytest.mark.unit
class TestShellExpansion:
    """Verify ${VAR} expansion."""

    def test_expands_home(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("CLAUDE_DIR=${HOME}/.claude\n" + _block("build"))
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["CLAUDE_DIR"] == f"{os.environ['HOME']}/.claude"

    def test_undefined_var_raises(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("BAD=${UNDEFINED_XYZ_12345}\n" + _block("build"))
        with pytest.raises(ValueError, match="UNDEFINED_XYZ_12345"):
            parse_mpmenv(mpmenv)


@pytest.mark.unit
class TestEnvOverrides:
    """Verify environment variable overrides."""

    def test_env_overrides_file(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("REPO_REV=v1.0.0\n" + _block("build"))
        monkeypatch.setenv("REPO_REV", "override")
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["REPO_REV"] == "override"

    def test_marketplace_dir_adopted_from_os_env_when_absent_from_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE_MARKETPLACES_DIR is resolved from the OS env when the .mpm omits it.

        CLAUDE_MARKETPLACES_DIR is a single, environment-specific path (12-factor),
        so it is adopted from the OS environment rather than requiring a hand-edited
        .mpm line that ``mpm add`` never writes.
        """
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build"))
        monkeypatch.setenv("CLAUDE_MARKETPLACES_DIR", "/env/marketplaces")
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["CLAUDE_MARKETPLACES_DIR"] == "/env/marketplaces"

    def test_marketplace_dir_absent_from_both_is_not_in_globals(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When neither the .mpm nor the OS env defines it, the key is not injected (no default)."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build"))
        monkeypatch.delenv("CLAUDE_MARKETPLACES_DIR", raising=False)
        result = parse_mpmenv(mpmenv)
        assert "CLAUDE_MARKETPLACES_DIR" not in result["globals"]

    def test_marketplace_dir_file_value_overrides_os_env(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit .mpm CLAUDE_MARKETPLACES_DIR value takes precedence over the OS env value."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("CLAUDE_MARKETPLACES_DIR=/from/file\n" + _block("build"))
        monkeypatch.setenv("CLAUDE_MARKETPLACES_DIR", "/from/env")
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["CLAUDE_MARKETPLACES_DIR"] == "/from/file"


@pytest.mark.unit
class TestValidation:
    """Verify validation errors."""

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_mpmenv(pathlib.Path("/nonexistent/.mpm"))

    def test_missing_sources_raises(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("REPO_URL=https://example.com\n")
        with pytest.raises(ValueError, match="No sources found"):
            parse_mpmenv(mpmenv)

    def test_missing_source_var_raises(self, tmp_path: pathlib.Path) -> None:
        """A URL-only source is partial: discovery names the missing required key."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            "MPM_SOURCE_build_URL=https://example.com\n"
            "MPM_SOURCE_build_REF=main\n"
            "MPM_SOURCE_build_PATH=meta.xml\n"
            "MPM_SOURCE_build_GITBASE=https://example.com\n"
        )

        with pytest.raises(ValueError, match="MPM_SOURCE_build_NAME"):
            parse_mpmenv(mpmenv)

    def test_partial_source_without_url_raises(self, tmp_path: pathlib.Path) -> None:
        """A non-URL suffix without a URL names the exact missing URL var."""
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_SOURCE_build_REF=main\n")
        with pytest.raises(ValueError, match="MPM_SOURCE_build_URL is required but not set"):
            parse_mpmenv(mpmenv)

    def test_validate_sources_direct(self) -> None:
        expanded = {
            "MPM_SOURCE_test_URL": "https://example.com",
            "MPM_SOURCE_test_REF": "main",
            "MPM_SOURCE_test_PATH": "meta.xml",
            "MPM_SOURCE_test_NAME": "test",
            "MPM_SOURCE_test_GITBASE": "https://example.com",
        }
        validate_sources(expanded, ["test"])

    def test_validate_sources_missing(self) -> None:
        expanded = {"MPM_SOURCE_test_URL": "https://example.com"}
        with pytest.raises(ValueError, match="MPM_SOURCE_test_REF"):
            validate_sources(expanded, ["test"])


@pytest.mark.unit
class TestEdgeCases:
    """Verify edge case handling."""

    def test_comments_ignored(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("# A comment\n" + _block("build"))
        result = parse_mpmenv(mpmenv)
        for key in result.get("globals", {}):
            assert not key.startswith("#")

    def test_value_with_equals(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build", url="https://example.com?a=1"))
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["build"]["url"] == "https://example.com?a=1"

    def test_mpm_sources_present_raises_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text("MPM_SOURCES=build\n" + _block("build"))
        with pytest.raises(ValueError, match="no longer supported"):
            parse_mpmenv(mpmenv)

    def test_auto_discovery_alphabetical_order(self, tmp_path: pathlib.Path) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(
            _block("beta", url="https://example.com/beta.git") + _block("alpha", url="https://example.com/alpha.git")
        )
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["alpha", "beta"]

    def test_marketplace_defaults_false(self, tmp_path: pathlib.Path) -> None:
        """A source block with no _MARKETPLACE line defaults its marketplace flag to
        False (absence == false), and there is no global marketplace key.
        """
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build"))
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["build"]["marketplace"] is False
        assert "MPM_MARKETPLACE_INSTALL" not in result

    def test_bom_prefixed_file_parses_clean_keys(self, tmp_path: pathlib.Path) -> None:
        """BOM-prefixed .mpm file must parse with no leading U+FEFF on any key."""
        content = _block("build")
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

        result = parse_mpmenv(mpmenv)

        for key in result["globals"]:
            assert "\ufeff" not in key, f"BOM codepoint found in globals key: {key!r}"
        for key in result["sources"]:
            assert "\ufeff" not in key, f"BOM codepoint found in source name: {key!r}"
        assert result["MPM_SOURCES"] == ["build"]
        assert result["sources"]["build"]["url"] == "https://example.com"

    def test_bom_and_no_bom_produce_equal_mappings(self, tmp_path: pathlib.Path) -> None:
        """Files with and without a UTF-8 BOM must yield identical parsed results."""
        content = _block("alpha", url="https://example.com/alpha.git")
        with_bom = tmp_path / ".mpm_bom"
        with_bom.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

        without_bom = tmp_path / ".mpm_no_bom"
        without_bom.write_bytes(content.encode("utf-8"))

        result_bom = parse_mpmenv(with_bom)
        result_plain = parse_mpmenv(without_bom)

        assert result_bom == result_plain


@pytest.mark.unit
class TestPosixWritePermission:
    """Verify the POSIX mode-bit .mpm write-permission control."""

    @pytest.mark.parametrize(
        ("mode_bits", "expected_fragment"),
        [
            (stat.S_IWGRP, "group-writable"),
            (stat.S_IWOTH, "world-writable"),
            (stat.S_IWGRP | stat.S_IWOTH, "group-writable and world-writable"),
        ],
    )
    def test_rejects_group_or_world_writable(
        self,
        tmp_path: pathlib.Path,
        mode_bits: int,
        expected_fragment: str,
    ) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build"))
        mpmenv.chmod(stat.S_IRUSR | stat.S_IWUSR | mode_bits)
        with pytest.raises(ValueError, match=expected_fragment):
            _check_write_permission(mpmenv)

    def test_accepts_owner_only_writable(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build"))
        mpmenv.chmod(stat.S_IRUSR | stat.S_IWUSR)

        _check_write_permission(mpmenv)

    def test_parse_mpmenv_rejects_world_writable_end_to_end(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        mpmenv = tmp_path / ".mpm"
        mpmenv.write_text(_block("build"))
        mpmenv.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IWOTH)
        with pytest.raises(ValueError, match="insecure permissions"):
            parse_mpmenv(mpmenv)
