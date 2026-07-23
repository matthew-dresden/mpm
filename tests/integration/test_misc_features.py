"""Integration tests for miscellaneous mpm features and cross-cutting concerns (24 tests).

Covers:
  - install core business logic (create_source_dirs, aggregate_symlinks,
    update_gitignore, prepare_marketplace_dir)
  - clean lifecycle teardown (remove_packages_dir, remove_mpm_dir,
    remove_marketplace_dir, clean())
  - mpmenv edge-case handling (comments, blank lines, value with equals)
  - constants module correctness (all required constants defined)
  - version module exports (mpm_cli.__version__)
  - install with mocked repo APIs
"""

import os
import pathlib
from unittest.mock import patch

import pytest

import mpm_cli
from mpm_cli.constants import (
    CATALOG_SOURCES_ENV_VAR,
    CONSTRAINT_RE,
    MPMENV_FILENAME,
    MPM_REPO_DIR_ENV,
    MARKETPLACE_DIR_PREFIX,
    PEP440_OPERATORS,
    REFS_TAGS_RE,
    SELFUPDATE_EMBEDDED_MESSAGE,
    SHELL_VAR_PATTERN,
    SOURCE_PREFIX,
    SOURCE_SUFFIXES,
)
from mpm_cli.core.clean import (
    clean,
    remove_mpm_dir,
    remove_marketplace_dir,
    remove_packages_dir,
)
from mpm_cli.core.install import (
    aggregate_symlinks,
    create_source_dirs,
    install,
    prepare_marketplace_dir,
    update_gitignore,
)
from mpm_cli.core.mpmenv import parse_mpmenv


def _write_mpmenv(path: pathlib.Path, content: str) -> pathlib.Path:
    """Write a .mpm file at path and return its absolute path."""
    mpmenv = path / ".mpm"
    mpmenv.write_text(content)
    return mpmenv


@pytest.mark.integration
class TestConstantsModule:
    """Verify all required constants are defined and have expected types."""

    def test_source_prefix_is_string(self) -> None:
        assert isinstance(SOURCE_PREFIX, str)
        assert SOURCE_PREFIX == "MPM_SOURCE_"

    def test_source_suffixes_tuple(self) -> None:
        assert "_URL" in SOURCE_SUFFIXES
        assert "_REF" in SOURCE_SUFFIXES
        assert "_PATH" in SOURCE_SUFFIXES
        assert "_NAME" in SOURCE_SUFFIXES
        assert "_GITBASE" not in SOURCE_SUFFIXES, (
            "_GITBASE is now an optional per-dependency env var, not a required structural suffix"
        )

    def test_mpmenv_filename(self) -> None:
        assert MPMENV_FILENAME == ".mpm"

    def test_marketplace_dir_prefix(self) -> None:
        assert MARKETPLACE_DIR_PREFIX.startswith("${CLAUDE_MARKETPLACES_DIR}")

    def test_pep440_operators(self) -> None:
        assert "~=" in PEP440_OPERATORS
        assert ">=" in PEP440_OPERATORS

    def test_refs_tags_re_compiled(self) -> None:
        assert REFS_TAGS_RE.match("refs/tags/org/proj/1.0.0") is not None

    def test_constraint_re_compiled(self) -> None:
        assert CONSTRAINT_RE.match("~=1.2.3") is not None

    def test_shell_var_pattern_compiled(self) -> None:
        m = SHELL_VAR_PATTERN.search("${HOME}/.config")
        assert m is not None
        assert m.group(1) == "HOME"

    def test_catalog_env_var_defined(self) -> None:
        assert isinstance(CATALOG_SOURCES_ENV_VAR, str)
        assert CATALOG_SOURCES_ENV_VAR

    def test_selfupdate_message_defined(self) -> None:
        assert isinstance(SELFUPDATE_EMBEDDED_MESSAGE, str)
        assert SELFUPDATE_EMBEDDED_MESSAGE

    def test_mpm_repo_dir_env_defined(self) -> None:
        assert isinstance(MPM_REPO_DIR_ENV, str)
        assert MPM_REPO_DIR_ENV


@pytest.mark.integration
class TestVersionExport:
    """Verify mpm_cli.__version__ is exported and non-empty."""

    def test_version_attribute_exists(self) -> None:
        assert hasattr(mpm_cli, "__version__")

    def test_version_is_non_empty_string(self) -> None:
        assert isinstance(mpm_cli.__version__, str)
        assert len(mpm_cli.__version__) > 0


@pytest.mark.integration
class TestInstallCoreLogic:
    """Verify install helper functions produce correct directory structures."""

    def test_create_source_dirs_creates_directories(self, tmp_path: pathlib.Path) -> None:
        result = create_source_dirs(["alpha", "beta"], tmp_path)
        for name in ("alpha", "beta"):
            assert (tmp_path / ".mpm-data" / "sources" / name).is_dir()
            assert name in result

    def test_aggregate_symlinks_creates_packages_dir(self, tmp_path: pathlib.Path) -> None:
        src_pkg = tmp_path / ".mpm-data" / "sources" / "build" / ".packages"
        src_pkg.mkdir(parents=True)
        (src_pkg / "my-tool").mkdir()
        aggregate_symlinks(["build"], tmp_path)
        assert (tmp_path / ".packages" / "my-tool").is_symlink()

    def test_aggregate_symlinks_collision_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        for src in ("a", "b"):
            pkg = tmp_path / ".mpm-data" / "sources" / src / ".packages"
            pkg.mkdir(parents=True)
            (pkg / "collision-pkg").mkdir()
        with pytest.raises(ValueError, match="Package collision"):
            aggregate_symlinks(["a", "b"], tmp_path)

    def test_update_gitignore_creates_file(self, tmp_path: pathlib.Path) -> None:
        update_gitignore(tmp_path, [".packages/", ".mpm-data/"])
        content = (tmp_path / ".gitignore").read_text()
        assert ".packages/" in content
        assert ".mpm-data/" in content

    def test_update_gitignore_idempotent(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".gitignore").write_text(".packages/\n.mpm-data/\n")
        update_gitignore(tmp_path, [".packages/", ".mpm-data/"])
        content = (tmp_path / ".gitignore").read_text()
        assert content.count(".packages/") == 1

    def test_prepare_marketplace_dir_creates_dir(self, tmp_path: pathlib.Path) -> None:
        mp_dir = tmp_path / "mp"
        prepare_marketplace_dir(mp_dir)
        assert mp_dir.is_dir()

    def test_prepare_marketplace_dir_clears_contents(self, tmp_path: pathlib.Path) -> None:
        mp_dir = tmp_path / "mp"
        mp_dir.mkdir()
        (mp_dir / "stale-entry").mkdir()
        prepare_marketplace_dir(mp_dir)
        assert list(mp_dir.iterdir()) == []


@pytest.mark.integration
class TestCleanLifecycle:
    """Verify clean helper functions and full clean() lifecycle."""

    def test_remove_packages_dir_removes_dir(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".packages").mkdir()
        remove_packages_dir(tmp_path)
        assert not (tmp_path / ".packages").exists()

    def test_remove_packages_dir_ok_when_missing(self, tmp_path: pathlib.Path) -> None:
        remove_packages_dir(tmp_path)

    def test_remove_mpm_dir_removes_dir(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mpm-data").mkdir()
        remove_mpm_dir(tmp_path)
        assert not (tmp_path / ".mpm-data").exists()

    def test_remove_mpm_dir_ok_when_missing(self, tmp_path: pathlib.Path) -> None:
        remove_mpm_dir(tmp_path)

    def test_remove_marketplace_dir_removes_dir(self, tmp_path: pathlib.Path) -> None:
        mp_dir = tmp_path / "mp"
        mp_dir.mkdir()
        remove_marketplace_dir(mp_dir)
        assert not mp_dir.exists()

    def test_remove_marketplace_dir_ok_when_missing(self, tmp_path: pathlib.Path) -> None:
        remove_marketplace_dir(tmp_path / "nonexistent")

    def test_clean_removes_packages_and_mpm_data(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\nMPM_SOURCE_s_REF=main\nMPM_SOURCE_s_PATH=m.xml\nMPM_SOURCE_s_NAME=s\nMPM_SOURCE_s_GITBASE=https://example.com\n",
        )

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)
        clean(mpmenv)
        assert not (store_base / ".packages").exists()
        assert not (store_base / ".mpm-data").exists()


@pytest.mark.integration
class TestMPMenvEdgeCases:
    """Verify edge-case handling in .mpm file parsing."""

    def test_comments_are_ignored(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "# This is a comment\n"
            "MPM_SOURCE_s_URL=https://example.com/s.git\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        for key in result.get("globals", {}):
            assert not key.startswith("#")

    def test_blank_lines_are_ignored(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "\n\nMPM_SOURCE_s_URL=https://example.com/s.git\n\n"
            "MPM_SOURCE_s_REF=main\n"
            "MPM_SOURCE_s_PATH=m.xml\n"
            "MPM_SOURCE_s_NAME=s\n"
            "MPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["MPM_SOURCES"] == ["s"]

    def test_value_with_embedded_equals(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com?a=1&b=2\nMPM_SOURCE_s_REF=main\nMPM_SOURCE_s_PATH=m.xml\nMPM_SOURCE_s_NAME=s\nMPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        result = parse_mpmenv(mpmenv)
        assert result["sources"]["s"]["url"] == "https://example.com?a=1&b=2"

    def test_install_with_mocked_repo_api(self, tmp_path: pathlib.Path) -> None:
        mpmenv = _write_mpmenv(
            tmp_path,
            "MPM_SOURCE_s_URL=https://example.com/s.git\nMPM_SOURCE_s_REF=main\nMPM_SOURCE_s_PATH=m.xml\nMPM_SOURCE_s_NAME=s\nMPM_SOURCE_s_GITBASE=https://example.com\n",
        )
        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        assert (store_base / ".mpm-data" / "sources" / "s").is_dir()
        assert not (store_base / ".gitignore").exists(), (
            "install must not create a .gitignore in a store that is not inside a git repo"
        )
