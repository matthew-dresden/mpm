"""TC-install scenarios from `docs/integration-testing.md` §27.

Each scenario exercises top-level `mpm install` surface area.

Scenarios automated:
- TC-install-01: auto-discover walks parent tree
- TC-install-02: explicit path bypasses auto-discover
- TC-install-03: REPO_URL env emits deprecation warning
- TC-install-04: REPO_REV env emits deprecation warning
"""

from __future__ import annotations

import os
import pathlib

import pytest

from tests.scenarios.conftest import (
    mpm_clean,
    make_plain_repo,
    run_mpm,
    write_mpmenv,
)


def _build_manifest_fixture(base: pathlib.Path) -> pathlib.Path:
    """Build a bare manifest repo containing repo-specs/alpha-only.xml.

    Returns the bare manifest repo path so callers can reference it in
    MPM_SOURCE_*_URL.
    """
    content_repos = base / "content-repos"
    manifest_repos = base / "manifest-repos"
    content_repos.mkdir(parents=True)
    manifest_repos.mkdir(parents=True)

    make_plain_repo(content_repos, "pkg-alpha", {"README.md": "# pkg-alpha\n"})
    content_url = content_repos.as_uri()

    remote_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        f'  <remote name="local" fetch="{content_url}/" />\n'
        '  <default remote="local" revision="main" />\n'
        "</manifest>\n"
    )
    alpha_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        '  <include name="repo-specs/remote.xml" />\n'
        '  <project name="pkg-alpha" path=".packages/pkg-alpha"'
        ' remote="local" revision="main" />\n'
        "</manifest>\n"
    )

    return make_plain_repo(
        manifest_repos,
        "manifest-primary",
        {
            "repo-specs/remote.xml": remote_xml,
            "repo-specs/alpha-only.xml": alpha_xml,
        },
    )


@pytest.mark.scenario
class TestTCInstall:
    def test_tc_install_01_auto_discover_walks_parent_tree(self, tmp_path: pathlib.Path) -> None:
        """TC-install-01: install from a subdirectory discovers .mpm in the parent tree."""
        manifest_bare = _build_manifest_fixture(tmp_path / "fixtures")

        project_root = tmp_path / "tc-inst-01"
        project_root.mkdir()

        write_mpmenv(
            project_root,
            sources=[
                (
                    "a",
                    manifest_bare.as_uri(),
                    "main",
                    "repo-specs/alpha-only.xml",
                )
            ],
            marketplace_install="false",
        )

        sub_deep = project_root / "sub" / "deep"
        sub_deep.mkdir(parents=True)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        install_result = run_mpm(
            "install",
            cwd=sub_deep,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        assert (store_base / ".packages" / "pkg-alpha").is_symlink(), ".packages/pkg-alpha symlink not found in store"

        clean_result = mpm_clean(project_root)
        assert clean_result.returncode == 0, f"clean exited {clean_result.returncode}\nstdout={clean_result.stdout!r}"

    def test_tc_install_02_explicit_path_bypasses_auto_discover(self, tmp_path: pathlib.Path) -> None:
        """TC-install-02: mpm install <path> uses the explicit env file, not auto-discover."""
        manifest_bare = _build_manifest_fixture(tmp_path / "fixtures")

        work_dir = tmp_path / "tc-inst-02"
        work_dir.mkdir()

        mpm_file = work_dir / "my.mpm"
        write_mpmenv(
            work_dir,
            sources=[
                (
                    "a",
                    manifest_bare.as_uri(),
                    "main",
                    "repo-specs/alpha-only.xml",
                )
            ],
            marketplace_install="false",
        )

        (work_dir / ".mpm").rename(mpm_file)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        install_result = run_mpm(
            "install",
            str(mpm_file),
            cwd=work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        assert (store_base / ".packages" / "pkg-alpha").is_symlink(), (
            ".packages/pkg-alpha symlink not found in store after explicit-path install"
        )

        clean_result = run_mpm("clean", str(mpm_file), cwd=work_dir)
        assert clean_result.returncode == 0, f"clean exited {clean_result.returncode}\nstdout={clean_result.stdout!r}"

    def test_tc_install_03_repo_url_deprecation_warning(self, tmp_path: pathlib.Path) -> None:
        """TC-install-03: mpm install emits a deprecation warning when REPO_URL is set."""
        manifest_bare = _build_manifest_fixture(tmp_path / "fixtures")

        work_dir = tmp_path / "tc-inst-03"
        work_dir.mkdir()

        write_mpmenv(
            work_dir,
            sources=[
                (
                    "a",
                    manifest_bare.as_uri(),
                    "main",
                    "repo-specs/alpha-only.xml",
                )
            ],
            marketplace_install="false",
        )

        env = dict(os.environ)
        env["REPO_URL"] = "https://example.com/repo.git"
        env["MPM_CATALOG_SOURCE"] = f"{manifest_bare.as_uri()}@main"
        env["MPM_ALLOW_INSECURE_REMOTES"] = "1"

        install_result = run_mpm("install", ".mpm", cwd=work_dir, env=env)
        assert install_result.returncode == 0, (
            f"install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        combined = install_result.stdout + install_result.stderr
        assert "deprecat" in combined.lower(), (
            f"Expected a deprecation warning mentioning REPO_URL in output: {combined!r}"
        )

        mpm_clean(work_dir)

    def test_tc_install_04_repo_rev_deprecation_warning(self, tmp_path: pathlib.Path) -> None:
        """TC-install-04: mpm install emits a deprecation warning when REPO_REV is set."""
        manifest_bare = _build_manifest_fixture(tmp_path / "fixtures")

        work_dir = tmp_path / "tc-inst-04"
        work_dir.mkdir()

        write_mpmenv(
            work_dir,
            sources=[
                (
                    "a",
                    manifest_bare.as_uri(),
                    "main",
                    "repo-specs/alpha-only.xml",
                )
            ],
            marketplace_install="false",
        )

        env = dict(os.environ)
        env["REPO_REV"] = "v1.2.3"
        env["MPM_CATALOG_SOURCE"] = f"{manifest_bare.as_uri()}@main"
        env["MPM_ALLOW_INSECURE_REMOTES"] = "1"

        install_result = run_mpm("install", ".mpm", cwd=work_dir, env=env)
        assert install_result.returncode == 0, (
            f"install exited {install_result.returncode}\n"
            f"stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )
        combined = install_result.stdout + install_result.stderr
        assert "deprecat" in combined.lower(), (
            f"Expected a deprecation warning mentioning REPO_REV in output: {combined!r}"
        )

        mpm_clean(work_dir)
