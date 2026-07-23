"""IC (Install/Clean Lifecycle) scenarios from `docs/integration-testing.md` §5.

Each scenario exercises the `mpm install` / `mpm clean` end-to-end lifecycle
against on-disk bare git repos served over `file://` URLs -- no network access
required.

Scenarios automated:
- IC-01: Single source, no marketplace -- install and clean
- IC-02: Shell variable expansion (${HOME})
- IC-03: Comments and blank lines in .mpm
- IC-04: MPM_MARKETPLACE_INSTALL=false explicit
"""

from __future__ import annotations

import os
import pathlib

import pytest

from tests.scenarios.conftest import (
    mpm_clean,
    mpm_install,
    make_plain_repo,
)


def _build_fixtures(base: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Build the minimal fixture repos needed by all IC scenarios.

    Returns:
        (pkg_alpha_bare, manifest_primary_bare) -- both are bare git repo paths.

    The manifest repo contains:
      - repo-specs/remote.xml -- defines a `local` remote pointing at the
        content-repos directory (parent of pkg_alpha_bare)
      - repo-specs/alpha-only.xml -- includes remote.xml and declares the
        pkg-alpha project at path `.packages/pkg-alpha`
    """
    content_repos = base / "content-repos"
    manifest_repos = base / "manifest-repos"
    content_repos.mkdir(parents=True)
    manifest_repos.mkdir(parents=True)

    pkg_alpha_bare = make_plain_repo(
        content_repos,
        "pkg-alpha",
        {"README.md": "# pkg-alpha\n"},
    )

    content_repos_url = content_repos.as_uri()

    remote_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        f'  <remote name="local" fetch="{content_repos_url}/" />\n'
        '  <default remote="local" revision="main" sync-j="4" />\n'
        "</manifest>\n"
    )
    alpha_only_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        '  <include name="repo-specs/remote.xml" />\n'
        '  <project name="pkg-alpha" path=".packages/pkg-alpha"'
        ' remote="local" revision="main" />\n'
        "</manifest>\n"
    )

    manifest_primary_bare = make_plain_repo(
        manifest_repos,
        "manifest-primary",
        {
            "repo-specs/remote.xml": remote_xml,
            "repo-specs/alpha-only.xml": alpha_only_xml,
        },
    )

    return pkg_alpha_bare, manifest_primary_bare


def _mpmenv_content(manifest_url: str, *, extra_lines: list[str] | None = None) -> str:
    """Return the text of a minimal .mpm file pointing at the primary manifest."""
    lines = [
        "MPM_MARKETPLACE_INSTALL=false",
        f"MPM_SOURCE_primary_URL={manifest_url}",
        "MPM_SOURCE_primary_REF=main",
        "MPM_SOURCE_primary_PATH=repo-specs/alpha-only.xml",
        "MPM_SOURCE_primary_NAME=primary",
        f"MPM_SOURCE_primary_GITBASE={manifest_url}",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    return "\n".join(lines) + "\n"


def _assert_install_pass_criteria(work_dir: pathlib.Path, store_base: pathlib.Path, result) -> None:
    """Assert the standard install pass criteria documented for IC-01..IC-04.

    The committed ``.mpm`` stays in ``work_dir``; the install artifacts
    (``.packages/`` and ``.mpm-data/``) live under the shared store
    (``<MPM_HOME>/store``), passed in as ``store_base``. The store here is a
    temp dir outside any git working tree, so install writes no ``.gitignore``.
    """
    assert result.returncode == 0, (
        f"mpm install exited {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "mpm install: done" in result.stdout, f"'mpm install: done' not in stdout: {result.stdout!r}"
    assert (store_base / ".mpm-data" / "sources" / "primary").is_dir(), (
        ".mpm-data/sources/primary/ directory missing under store"
    )
    assert (store_base / ".packages").is_dir(), ".packages/ directory missing under store"
    pkg_alpha_link = store_base / ".packages" / "pkg-alpha"
    assert pkg_alpha_link.is_symlink(), ".packages/pkg-alpha is not a symlink"
    link_target = os.readlink(str(pkg_alpha_link))
    assert ".mpm-data/sources/primary" in link_target or (
        store_base / ".mpm-data" / "sources" / "primary"
    ).as_posix() in os.path.realpath(str(pkg_alpha_link)), (
        f"symlink target does not reference .mpm-data/sources/primary: {link_target!r}"
    )
    assert not (store_base / ".gitignore").exists(), (
        ".gitignore must not be written for a store outside a git working tree"
    )


def _assert_clean_pass_criteria(store_base: pathlib.Path, result) -> None:
    """Assert the standard clean pass criteria documented for IC-01.

    Install artifacts live under the shared store, so clean removes
    ``.packages/`` and ``.mpm-data/`` from ``store_base``.
    """
    assert result.returncode == 0, (
        f"mpm clean exited {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "mpm clean: done" in result.stdout, f"'mpm clean: done' not in stdout: {result.stdout!r}"
    assert not (store_base / ".packages").exists(), ".packages/ still exists after clean"
    assert not (store_base / ".mpm-data").exists(), ".mpm-data/ still exists after clean"


@pytest.mark.scenario
class TestIC:
    def test_ic_01_single_source_install_and_clean(self, tmp_path: pathlib.Path) -> None:
        """IC-01: Single source, no marketplace -- full install then clean cycle."""
        _, manifest_bare = _build_fixtures(tmp_path / "fixtures")

        work_dir = tmp_path / "test-ic01"
        work_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        manifest_url = manifest_bare.as_uri()
        (work_dir / ".mpm").write_text(_mpmenv_content(manifest_url))

        catalog_source = f"{manifest_url}@main"
        install_result = mpm_install(
            work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        _assert_install_pass_criteria(work_dir, store_base, install_result)

        clean_result = mpm_clean(work_dir)
        _assert_clean_pass_criteria(store_base, clean_result)

    def test_ic_02_shell_variable_expansion(self, tmp_path: pathlib.Path) -> None:
        """IC-02: ${HOME} in .mpm is expanded during parsing, not stored expanded."""
        _, manifest_bare = _build_fixtures(tmp_path / "fixtures")

        work_dir = tmp_path / "test-ic02"
        work_dir.mkdir()

        manifest_url = manifest_bare.as_uri()
        mpm_text = (
            "MPM_MARKETPLACE_INSTALL=false\n"
            "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces\n"
            f"MPM_SOURCE_primary_URL={manifest_url}\n"
            "MPM_SOURCE_primary_REF=main\n"
            "MPM_SOURCE_primary_PATH=repo-specs/alpha-only.xml\n"
            "MPM_SOURCE_primary_NAME=primary\n"
            f"MPM_SOURCE_primary_GITBASE={manifest_url}\n"
        )
        mpm_file = work_dir / ".mpm"
        mpm_file.write_text(mpm_text)

        assert "${HOME}" in mpm_file.read_text(), "The .mpm file should contain the literal string '${HOME}'"

        catalog_source = f"{manifest_url}@main"
        install_result = mpm_install(
            work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"mpm install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        assert "mpm install: done" in install_result.stdout, (
            f"'mpm install: done' not in stdout: {install_result.stdout!r}"
        )

        mpm_clean(work_dir)

    def test_ic_03_comments_and_blank_lines(self, tmp_path: pathlib.Path) -> None:
        """IC-03: Comments and blank lines in .mpm do not cause parsing errors."""
        _, manifest_bare = _build_fixtures(tmp_path / "fixtures")

        work_dir = tmp_path / "test-ic03"
        work_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        manifest_url = manifest_bare.as_uri()
        mpm_text = (
            "# This is a comment\n"
            "# Another comment\n"
            "\n"
            "MPM_MARKETPLACE_INSTALL=false\n"
            "\n"
            "# Blank lines above and below should be ignored\n"
            "\n"
            f"MPM_SOURCE_primary_URL={manifest_url}\n"
            "MPM_SOURCE_primary_REF=main\n"
            "MPM_SOURCE_primary_PATH=repo-specs/alpha-only.xml\n"
            "MPM_SOURCE_primary_NAME=primary\n"
            f"MPM_SOURCE_primary_GITBASE={manifest_url}\n"
            "\n"
            "# Trailing comment\n"
        )
        (work_dir / ".mpm").write_text(mpm_text)

        catalog_source = f"{manifest_url}@main"
        install_result = mpm_install(
            work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"mpm install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        assert "mpm install: done" in install_result.stdout, (
            f"'mpm install: done' not in stdout: {install_result.stdout!r}"
        )
        pkg_alpha_link = store_base / ".packages" / "pkg-alpha"
        assert pkg_alpha_link.is_symlink(), (
            ".packages/pkg-alpha symlink missing -- comments/blank lines may have broken parsing"
        )

        mpm_clean(work_dir)

    def test_ic_04_marketplace_install_false_explicit(self, tmp_path: pathlib.Path) -> None:
        """IC-04: MPM_MARKETPLACE_INSTALL=false suppresses marketplace lifecycle output."""
        _, manifest_bare = _build_fixtures(tmp_path / "fixtures")

        work_dir = tmp_path / "test-ic04"
        work_dir.mkdir()

        manifest_url = manifest_bare.as_uri()
        (work_dir / ".mpm").write_text(_mpmenv_content(manifest_url))

        catalog_source = f"{manifest_url}@main"
        install_result = mpm_install(
            work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"mpm install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        assert "mpm install: done" in install_result.stdout, (
            f"'mpm install: done' not in stdout: {install_result.stdout!r}"
        )

        for marketplace_action in (
            "mpm install: preparing marketplace directory",
            "mpm install: installing marketplace plugins",
        ):
            assert marketplace_action not in install_result.stdout, (
                f"marketplace lifecycle action found in stdout when MPM_MARKETPLACE_INSTALL=false -- "
                f"found {marketplace_action!r} in: {install_result.stdout!r}"
            )

        mpm_clean(work_dir)
