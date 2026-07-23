"""Integration tests for mpm clean lifecycle using embedded Python API (8 tests).

Verifies that clean removes repo-managed files, preserves non-repo files, and
that the full install -> clean roundtrip works correctly. Also covers error
paths: invalid manifest, corrupt state, and marketplace-enabled vs disabled.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mpm_cli.core.clean import clean
from mpm_cli.core.install import install


def _store_base() -> Path:
    """Return the shared artifact store base (``<MPM_HOME>/store``).

    install()/clean() create and remove ``.packages/`` and ``.mpm-data/``
    under the shared store, not beside the project ``.mpm``.
    The ``_isolate_mpm_home`` autouse fixture points MPM_HOME at a fresh
    per-test temporary directory.
    """
    return Path(os.environ["MPM_HOME"]) / "store"


def _write_mpmenv(directory: Path, content: str) -> Path:
    """Write a .mpm file in directory and return its path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(content)
    return mpmenv


def _minimal_mpmenv_content(name: str = "primary") -> str:
    """Return minimal .mpm content for a single source."""
    return (
        f"MPM_SOURCE_{name}_URL=https://example.com/repo.git\n"
        f"MPM_SOURCE_{name}_REF=main\n"
        f"MPM_SOURCE_{name}_PATH=meta.xml\n"
        f"MPM_SOURCE_{name}_NAME={name}\n"
        f"MPM_SOURCE_{name}_GITBASE=https://example.com\n"
    )


@pytest.mark.integration
class TestCleanRemovesRepoManagedFiles:
    """AC-FUNC-007: Clean removes repo-managed files (.packages/, .mpm-data/)."""

    def test_clean_removes_repo_managed_files(self, tmp_path: Path) -> None:
        """Verify that clean() removes .packages/ and .mpm-data/ directories
        created by install.
        """
        mpmenv = _write_mpmenv(tmp_path, _minimal_mpmenv_content())
        store_base = _store_base()
        (store_base / ".packages" / "some-pkg").mkdir(parents=True)
        (store_base / ".mpm-data" / "sources" / "primary").mkdir(parents=True)
        (store_base / ".mpm-data" / "sources" / "primary" / "metadata.txt").write_text("data")

        clean(mpmenv)

        assert not (store_base / ".packages").exists(), ".packages/ should be removed by clean()"
        assert not (store_base / ".mpm-data").exists(), ".mpm-data/ should be removed by clean()"


@pytest.mark.integration
class TestCleanPreservesNonRepoFiles:
    """AC-FUNC-008: Clean preserves files not managed by repo (e.g. user files)."""

    def test_clean_preserves_non_repo_files(self, tmp_path: Path) -> None:
        """Verify that clean() does not remove files that were not created by install:
        - .mpm configuration file
        - .gitignore
        - User source files
        """
        mpmenv = _write_mpmenv(tmp_path, _minimal_mpmenv_content())
        store_base = _store_base()
        (tmp_path / ".gitignore").write_text(".packages/\n.mpm-data/\n")
        user_file = tmp_path / "src" / "main.py"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("# user code\n")

        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        clean(mpmenv)

        assert mpmenv.is_file(), ".mpm configuration file must survive clean()"
        assert (tmp_path / ".gitignore").is_file(), ".gitignore must survive clean()"
        assert user_file.is_file(), "User source files must survive clean()"


@pytest.mark.integration
class TestInstallCleanRoundtrip:
    """AC-FUNC-009: Full install -> clean roundtrip leaves project in clean state."""

    def test_install_then_clean_roundtrip(self, tmp_path: Path) -> None:
        """Verify the full roundtrip: install creates managed artifacts,
        clean removes them, leaving the project directory in a clean state
        with only the .mpm file remaining.
        """
        mpmenv = _write_mpmenv(tmp_path, _minimal_mpmenv_content())

        def fake_repo_sync(repo_dir: str, **kwargs) -> None:
            pkg_dir = Path(repo_dir) / ".packages" / "tool-a"
            pkg_dir.mkdir(parents=True, exist_ok=True)
            (pkg_dir / "tool-a.sh").write_text("#!/bin/sh\necho hello\n")

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync", side_effect=fake_repo_sync),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        store_base = _store_base()
        assert (store_base / ".packages" / "tool-a").is_symlink(), "install() should create a symlink in .packages/"
        assert (store_base / ".mpm-data" / "sources" / "primary").is_dir(), (
            "install() should create .mpm-data/sources/primary/"
        )

        clean(mpmenv)

        assert not (store_base / ".packages").exists(), "clean() should remove .packages/ after install"
        assert not (store_base / ".mpm-data").exists(), "clean() should remove .mpm-data/ after install"
        assert mpmenv.is_file(), "clean() must not remove the .mpm configuration file"


@pytest.mark.integration
class TestCleanErrorPaths:
    """AC-FUNC-010: Error paths -- invalid manifest, missing git, corrupt state."""

    def test_clean_invalid_manifest_raises_value_error(self, tmp_path: Path) -> None:
        """Verify that clean() raises ValueError when .mpm has no valid source
        definitions. The CLI command handler converts this to SystemExit(1).
        """
        mpmenv = _write_mpmenv(
            tmp_path,
            "# This .mpm has no sources -- invalid\nREPO_REV=v1.0.0\n",
        )
        with pytest.raises(ValueError, match="No sources found"):
            clean(mpmenv)

    def test_clean_missing_mpmenv_raises_file_not_found(self, tmp_path: Path) -> None:
        """Verify that clean() raises FileNotFoundError when .mpm does not exist."""
        missing = tmp_path / ".mpm"
        with pytest.raises(FileNotFoundError):
            clean(missing)

    def test_clean_corrupt_mpm_data_is_still_removed(self, tmp_path: Path) -> None:
        """Verify that clean() removes .mpm-data/ even when its contents are
        in a corrupt/unexpected state (e.g. unexpected nested files).
        """
        mpmenv = _write_mpmenv(tmp_path, _minimal_mpmenv_content())
        store_base = _store_base()
        corrupt_dir = store_base / ".mpm-data" / "sources" / "primary" / "unexpected-subdir"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "corrupt.bin").write_bytes(b"\x00\xff\xfe")

        clean(mpmenv)

        assert not (store_base / ".mpm-data").exists(), (
            "clean() must remove .mpm-data/ even when contents are in unexpected state"
        )

    def test_clean_idempotent_when_already_clean(self, tmp_path: Path) -> None:
        """Verify that clean() succeeds (is idempotent) when .packages/ and
        .mpm-data/ do not exist.
        """
        mpmenv = _write_mpmenv(tmp_path, _minimal_mpmenv_content())
        store_base = _store_base()

        assert not (store_base / ".packages").exists()
        assert not (store_base / ".mpm-data").exists()

        clean(mpmenv)

        assert not (store_base / ".packages").exists()
        assert not (store_base / ".mpm-data").exists()


@pytest.mark.integration
class TestCleanMarketplaceBehavior:
    """AC-FUNC-007, AC-FUNC-008: Marketplace clean behaviors."""

    def test_clean_marketplace_false_skips_uninstall(self, tmp_path: Path) -> None:
        """Verify that when MPM_MARKETPLACE_INSTALL is absent (defaults to false),
        the marketplace uninstall function is never invoked.
        """
        mpmenv = _write_mpmenv(tmp_path, _minimal_mpmenv_content())
        store_base = _store_base()
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        with patch("mpm_cli.core.clean.uninstall_marketplace_plugins") as mock_uninstall:
            clean(mpmenv)
            mock_uninstall.assert_not_called()

        assert not (store_base / ".packages").exists(), (
            ".packages/ should still be removed even when marketplace uninstall is skipped"
        )

    def test_clean_marketplace_true_removes_marketplace_dir(self, tmp_path: Path) -> None:
        """Verify that when MPM_MARKETPLACE_INSTALL=true, clean() removes
        the marketplace directory in addition to .packages/ and .mpm-data/.
        """
        marketplace_dir = tmp_path / "marketplaces"
        marketplace_dir.mkdir()
        (marketplace_dir / "some-marketplace-file.txt").write_text("marketplace data")

        mpmenv = _write_mpmenv(
            tmp_path,
            (
                f"CLAUDE_MARKETPLACES_DIR={marketplace_dir}\n"
                "MPM_SOURCE_primary_URL=https://example.com/repo.git\n"
                "MPM_SOURCE_primary_REF=main\n"
                "MPM_SOURCE_primary_PATH=meta.xml\n"
                "MPM_SOURCE_primary_NAME=primary\n"
                "MPM_SOURCE_primary_GITBASE=https://example.com\n"
                "MPM_SOURCE_primary_MARKETPLACE=true\n"
            ),
        )
        store_base = _store_base()
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        with patch("mpm_cli.core.clean.uninstall_marketplace_plugins"):
            clean(mpmenv)

        assert not marketplace_dir.exists(), (
            "clean() should remove CLAUDE_MARKETPLACES_DIR when MPM_MARKETPLACE_INSTALL=true"
        )
        assert not (store_base / ".packages").exists(), (
            ".packages/ should be removed during clean with marketplace=true"
        )
