"""LF (Linkfile) scenarios from `docs/integration-testing.md` §8.

Scenarios automated:
- LF-01: Package with linkfile elements creates symlinks inside the source directory
"""

from __future__ import annotations

import os
import pathlib

import pytest

from tests.scenarios.conftest import (
    mpm_clean,
    mpm_install,
    make_plain_repo,
    write_mpmenv,
)


def _build_fixtures(base: pathlib.Path) -> pathlib.Path:
    """Build fixture repos needed by LF scenarios.

    Returns:
        manifest_linkfile_bare

    The pkg-linked content repo contains:
      - config/app-config.json
      - config/lint.toml

    The manifest-linkfile repo contains:
      - repo-specs/remote.xml
      - repo-specs/linkfile.xml  (project with two <linkfile> elements)
    """
    content_repos = base / "content-repos"
    manifest_repos = base / "manifest-repos"
    content_repos.mkdir(parents=True)
    manifest_repos.mkdir(parents=True)

    make_plain_repo(
        content_repos,
        "pkg-linked",
        {
            "config/app-config.json": '{"setting": "value"}\n',
            "config/lint.toml": "lint_rule = true\n",
            "README.md": "# Linked Package\n",
        },
    )

    content_repos_url = content_repos.as_uri()

    remote_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        f'  <remote name="local" fetch="{content_repos_url}/" />\n'
        '  <default remote="local" revision="main" sync-j="4" />\n'
        "</manifest>\n"
    )

    linkfile_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        '  <include name="repo-specs/remote.xml" />\n'
        '  <project name="pkg-linked" path=".packages/pkg-linked"'
        ' remote="local" revision="main">\n'
        '    <linkfile src="config/app-config.json" dest="app-config.json" />\n'
        '    <linkfile src="config/lint.toml" dest="lint.toml" />\n'
        "  </project>\n"
        "</manifest>\n"
    )

    manifest_linkfile_bare = make_plain_repo(
        manifest_repos,
        "manifest-linkfile",
        {
            "repo-specs/remote.xml": remote_xml,
            "repo-specs/linkfile.xml": linkfile_xml,
        },
    )

    return manifest_linkfile_bare


@pytest.mark.scenario
class TestLF:
    def test_lf_01_linkfile_elements_create_symlinks(self, tmp_path: pathlib.Path) -> None:
        """LF-01: Package with linkfile elements creates symlinks in the source directory."""
        manifest_linkfile_bare = _build_fixtures(tmp_path / "fixtures")

        work_dir = tmp_path / "test-lf01"
        work_dir.mkdir()

        manifest_url = manifest_linkfile_bare.as_uri()
        write_mpmenv(
            work_dir,
            [("linked", manifest_url, "main", "repo-specs/linkfile.xml")],
            marketplace_install="false",
        )

        catalog_source = f"{manifest_url}@main"
        result = mpm_install(
            work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )

        assert result.returncode == 0, (
            f"mpm install exited {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        assert "mpm install: done" in result.stdout, f"'mpm install: done' not in stdout: {result.stdout!r}"

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        pkg_linked_link = store_base / ".packages" / "pkg-linked"
        assert pkg_linked_link.is_symlink(), ".packages/pkg-linked is not a symlink"

        sources_linked = store_base / ".mpm-data" / "sources" / "linked"
        assert sources_linked.is_dir(), ".mpm-data/sources/linked/ directory missing"

        app_config_link = sources_linked / "app-config.json"
        assert app_config_link.is_symlink(), ".mpm-data/sources/linked/app-config.json is not a symlink"
        assert app_config_link.resolve().exists(), (
            ".mpm-data/sources/linked/app-config.json symlink does not resolve to a valid file"
        )

        lint_toml_link = sources_linked / "lint.toml"
        assert lint_toml_link.is_symlink(), ".mpm-data/sources/linked/lint.toml is not a symlink"
        assert lint_toml_link.resolve().exists(), (
            ".mpm-data/sources/linked/lint.toml symlink does not resolve to a valid file"
        )

        mpm_clean(work_dir)
