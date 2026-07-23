"""Integration tests for mpmenv.yaml parsing (20 tests).

Exercises the full parse_mpmenv() pipeline -- reading, env override,
shell-variable expansion, source auto-discovery, and validation -- using
real temporary .mpm files.
"""

import os
import pathlib

import pytest

from mpm_cli.core.mpmenv import parse_mpmenv, validate_sources


def _write_mpmenv(path: pathlib.Path, content: str) -> pathlib.Path:
    """Write content to a .mpm file at path and return its absolute path."""
    mpmenv = path / ".mpm"
    mpmenv.write_text(content)
    return mpmenv


@pytest.mark.integration
class TestMPMenvParsingSingleSource:
    """Verify single-source .mpm parsing produces correct structure."""

    def test_single_source_parsed(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_build_URL=https://example.com/build.git\n"
            "MPM_SOURCE_build_REF=main\n"
            "MPM_SOURCE_build_PATH=default.xml\n"
            "MPM_SOURCE_build_NAME=build\n"
            "MPM_SOURCE_build_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["build"]
        assert "build" in result["sources"]

    def test_source_url_field_present(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["s"]["url"] == "https://example.com/s.git"

    def test_source_revision_field_present(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=v1.0.0\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["s"]["ref"] == "v1.0.0"

    def test_source_path_field_present(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=repo-specs/manifest.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["s"]["path"] == "repo-specs/manifest.xml"

    def test_marketplace_install_defaults_false(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["s"]["marketplace"] is False

    def test_marketplace_install_true(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n"
            "MPM_SOURCE_s_MARKETPLACE=true\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["s"]["marketplace"] is True


@pytest.mark.integration
class TestMPMenvParsingMultiSource:
    """Verify multi-source .mpm parsing and alphabetical ordering."""

    def test_two_sources_discovered(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_alpha_URL=https://example.com/a.git\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=m.xml\n"
            "MPM_SOURCE_alpha_NAME=alpha\n"
            "MPM_SOURCE_alpha_GITBASE=https://example.com\n"
            "MPM_SOURCE_beta_URL=https://example.com/b.git\n"
            "MPM_SOURCE_beta_REF=main\n"
            "MPM_SOURCE_beta_PATH=m.xml\n"
            "MPM_SOURCE_beta_NAME=beta\n"
            "MPM_SOURCE_beta_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["alpha", "beta"]

    def test_sources_sorted_alphabetically(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_zzz_URL=https://example.com/z.git\n"
            "MPM_SOURCE_zzz_REF=main\n"
            "MPM_SOURCE_zzz_PATH=m.xml\n"
            "MPM_SOURCE_zzz_NAME=zzz\n"
            "MPM_SOURCE_zzz_GITBASE=https://example.com\n"
            "MPM_SOURCE_aaa_URL=https://example.com/a.git\n"
            "MPM_SOURCE_aaa_REF=main\n"
            "MPM_SOURCE_aaa_PATH=m.xml\n"
            "MPM_SOURCE_aaa_NAME=aaa\n"
            "MPM_SOURCE_aaa_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["aaa", "zzz"]

    def test_globals_extracted_correctly(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "REPO_REV=v2.0.0\n"
            "GITBASE=https://github.com/\n"
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["REPO_REV"] == "v2.0.0"
        assert result["globals"]["GITBASE"] == "https://github.com/"


@pytest.mark.integration
class TestMPMenvParsingShellExpansion:
    """Verify ${VAR} expansion in .mpm values."""

    def test_expands_home_variable(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "CLAUDE_DIR=${HOME}/.claude\n"
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        expected = os.environ.get("HOME", "")
        assert result["globals"]["CLAUDE_DIR"] == f"{expected}/.claude"

    def test_undefined_var_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "BAD=${UNDEFINED_MPM_TEST_VAR_XYZ_12345}\n"
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        with pytest.raises(ValueError, match="UNDEFINED_MPM_TEST_VAR_XYZ_12345"):
            parse_mpmenv(mpmenv)


@pytest.mark.integration
class TestMPMenvParsingEnvOverrides:
    """Verify environment variable overrides take precedence over file values."""

    def test_env_overrides_file_value(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "REPO_REV=v1.0.0\n"
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        monkeypatch.setenv("REPO_REV", "v99.0.0")
        result = parse_mpmenv(mpmenv)
        assert result["globals"]["REPO_REV"] == "v99.0.0"


@pytest.mark.integration
class TestMPMenvParsingValidation:
    """Verify fail-fast validation errors."""

    def test_missing_file_raises_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_mpmenv(pathlib.Path("/nonexistent/.mpm"))

    def test_no_sources_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(tmp_path, "REPO_REV=v1.0.0\n")
        with pytest.raises(ValueError, match="No sources found"):
            parse_mpmenv(mpmenv)

    def test_missing_ref_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        with pytest.raises(ValueError, match="MPM_SOURCE_s_REF"):
            parse_mpmenv(mpmenv)

    def test_mpm_sources_key_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCES=build\n"
            "MPM_SOURCE_build_URL=https://example.com/b.git\n"
            "MPM_SOURCE_build_REF=main\n"
            "MPM_SOURCE_build_PATH=m.xml\n"
            "MPM_SOURCE_build_NAME=build\n"
            "MPM_SOURCE_build_GITBASE=https://example.com\n",
        )
        with pytest.raises(ValueError, match="no longer supported"):
            parse_mpmenv(mpmenv)

    def test_validate_sources_passes_for_complete_source(self) -> None:
        expanded = {
            "MPM_SOURCE_ok_URL": "https://example.com/ok.git",
            "MPM_SOURCE_ok_REF": "main",
            "MPM_SOURCE_ok_PATH": "m.xml",
            "MPM_SOURCE_ok_NAME": "ok",
            "MPM_SOURCE_ok_GITBASE": "https://example.com",
        }
        validate_sources(expanded, ["ok"])

    def test_missing_url_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_REF=main\nMPM_SOURCE_s_PATH=m.xml\n",
        )
        with pytest.raises(ValueError, match=r"MPM_SOURCE_\w+_URL"):
            parse_mpmenv(mpmenv)

    def test_missing_path_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\nMPM_SOURCE_s_REF=main\n",
        )
        with pytest.raises(ValueError, match="MPM_SOURCE_s_PATH"):
            parse_mpmenv(mpmenv)

    def test_validate_sources_raises_for_missing_path(self) -> None:
        expanded = {
            "MPM_SOURCE_t_URL": "https://example.com/t.git",
            "MPM_SOURCE_t_REF": "main",
        }
        with pytest.raises(ValueError, match="MPM_SOURCE_t_PATH"):
            validate_sources(expanded, ["t"])
