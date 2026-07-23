"""AD (Auto-Discovery) scenarios from `docs/integration-testing.md` §15.

Each scenario exercises `mpm install` / `mpm clean` auto-discovery of the
`.mpm` file by walking up the directory tree when no explicit path is given.
All fixtures are built from local bare git repos via `file://` URLs so no
network access is required.

Scenarios automated:
- AD-01: mpm install (no arg) in directory with .mpm
- AD-02: mpm install in subdirectory, .mpm in parent
- AD-03: mpm install with no .mpm anywhere
- AD-04: mpm install .mpm (explicit) still works
- AD-05: mpm clean (no arg) in directory with .mpm
- AD-06: mpm clean in subdirectory, .mpm in parent
- AD-07: mpm install /explicit/path/.mpm overrides discovery
- AD-08: mpm install prints which .mpm was found
"""

from __future__ import annotations

import os
import pathlib

import pytest

from tests.scenarios.conftest import (
    make_plain_repo,
    run_mpm,
    write_mpmenv,
)


def _build_pkg_alpha(fixtures_dir: pathlib.Path) -> pathlib.Path:
    """Create a bare content repo for pkg-alpha under fixtures_dir/content-repos.

    Returns the bare repo path (fixtures_dir/content-repos/pkg-alpha.git).
    """
    content_dir = fixtures_dir / "content-repos"
    content_dir.mkdir(parents=True, exist_ok=True)
    return make_plain_repo(
        content_dir,
        "pkg-alpha",
        {
            "src/main.py": 'print("alpha")\n',
            "README.md": "# Alpha Package\n",
        },
    )


def _build_manifest_primary(
    fixtures_dir: pathlib.Path,
    pkg_alpha_bare: pathlib.Path,
) -> pathlib.Path:
    """Create a bare manifest repo containing repo-specs/remote.xml and alpha-only.xml.

    The remote.xml fetch URL points at the directory that *contains* the pkg-alpha
    bare repo (i.e. `pkg_alpha_bare.parent`) so the repo tool resolves the project
    `name="pkg-alpha"` to `<fetch>/pkg-alpha`.

    Returns the bare manifest repo path.
    """
    manifest_dir = fixtures_dir / "manifest-repos"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    content_fetch_url = pkg_alpha_bare.parent.as_uri()

    remote_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        f'  <remote name="local" fetch="{content_fetch_url}" />\n'
        '  <default remote="local" revision="main" sync-j="4" />\n'
        "</manifest>\n"
    )

    alpha_only_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        '  <include name="repo-specs/remote.xml" />\n'
        '  <project name="pkg-alpha" path=".packages/pkg-alpha" remote="local" revision="main" />\n'
        "</manifest>\n"
    )

    return make_plain_repo(
        manifest_dir,
        "manifest-primary",
        {
            "repo-specs/remote.xml": remote_xml,
            "repo-specs/alpha-only.xml": alpha_only_xml,
        },
    )


def _build_ad_fixtures(fixtures_dir: pathlib.Path) -> pathlib.Path:
    """Build all fixtures needed by the AD scenarios.

    Returns the bare manifest-primary repo path.
    """
    pkg_alpha_bare = _build_pkg_alpha(fixtures_dir)
    return _build_manifest_primary(fixtures_dir, pkg_alpha_bare)


def _write_ad_mpmenv(work_dir: pathlib.Path, manifest_bare: pathlib.Path) -> pathlib.Path:
    """Write a .mpm referencing the alpha-only.xml manifest into work_dir."""
    return write_mpmenv(
        work_dir,
        [
            (
                "primary",
                manifest_bare.as_uri(),
                "main",
                "repo-specs/alpha-only.xml",
            )
        ],
        marketplace_install="false",
    )


@pytest.mark.scenario
class TestAD:
    def test_ad_01_install_no_arg_in_dir_with_mpm(self, tmp_path: pathlib.Path) -> None:
        """AD-01: mpm install (no arg) in directory with .mpm."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        work_dir = tmp_path / "test-ad01"
        work_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        _write_ad_mpmenv(work_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        result = run_mpm(
            "install",
            cwd=work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "mpm install: done" in result.stdout, f"stdout={result.stdout!r}"
        assert (store_base / ".packages" / "pkg-alpha").exists(), (
            f".packages/pkg-alpha not found under store {store_base}"
        )

    def test_ad_02_install_from_subdirectory(self, tmp_path: pathlib.Path) -> None:
        """AD-02: mpm install in subdirectory, .mpm in parent."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        parent_dir = tmp_path / "test-ad02"
        child_dir = parent_dir / "child"
        parent_dir.mkdir()
        child_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        _write_ad_mpmenv(parent_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        result = run_mpm(
            "install",
            cwd=child_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "mpm install: done" in result.stdout, f"stdout={result.stdout!r}"

        assert (store_base / ".packages" / "pkg-alpha").exists(), (
            f".packages/pkg-alpha not found under store {store_base}"
        )

    def test_ad_03_install_with_no_mpm_anywhere(self, tmp_path: pathlib.Path) -> None:
        """AD-03: mpm install with no .mpm anywhere -- must fail with exit 1."""
        work_dir = tmp_path / "test-ad03"
        work_dir.mkdir()

        result = run_mpm("install", cwd=work_dir)

        assert result.returncode != 0, "expected non-zero exit when no .mpm exists but got 0"
        combined = result.stderr + result.stdout
        assert ".mpm" in combined, f"expected '.mpm' in stderr/stdout but got: {combined!r}"

    def test_ad_04_install_explicit_mpm_arg(self, tmp_path: pathlib.Path) -> None:
        """AD-04: mpm install .mpm (explicit relative path) still works."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        work_dir = tmp_path / "test-ad04"
        work_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        _write_ad_mpmenv(work_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        result = run_mpm(
            "install",
            ".mpm",
            cwd=work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "mpm install: done" in result.stdout, f"stdout={result.stdout!r}"
        assert (store_base / ".packages" / "pkg-alpha").exists(), (
            f".packages/pkg-alpha not found under store {store_base}"
        )

    def test_ad_05_clean_no_arg_in_dir_with_mpm(self, tmp_path: pathlib.Path) -> None:
        """AD-05: mpm clean (no arg) in directory with .mpm removes artifacts."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        work_dir = tmp_path / "test-ad05"
        work_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        _write_ad_mpmenv(work_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        install_result = run_mpm(
            "install",
            ".mpm",
            cwd=work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"install failed: stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )

        result = run_mpm("clean", cwd=work_dir)

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "mpm clean: done" in result.stdout, f"stdout={result.stdout!r}"
        assert not (store_base / ".packages").exists(), f".packages/ still exists after clean under store {store_base}"
        assert not (store_base / ".mpm-data").exists(), f".mpm-data/ still exists after clean under store {store_base}"

    def test_ad_06_clean_from_subdirectory(self, tmp_path: pathlib.Path) -> None:
        """AD-06: mpm clean in subdirectory, .mpm in parent."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        parent_dir = tmp_path / "test-ad06"
        child_dir = parent_dir / "child"
        parent_dir.mkdir()
        child_dir.mkdir()
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        _write_ad_mpmenv(parent_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        install_result = run_mpm(
            "install",
            ".mpm",
            cwd=parent_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )
        assert install_result.returncode == 0, (
            f"install failed: stdout={install_result.stdout!r}\nstderr={install_result.stderr!r}"
        )

        result = run_mpm("clean", cwd=child_dir)

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "mpm clean: done" in result.stdout, f"stdout={result.stdout!r}"
        assert not (store_base / ".packages").exists(), f".packages/ still exists under store {store_base}"
        assert not (store_base / ".mpm-data").exists(), f".mpm-data/ still exists under store {store_base}"

    def test_ad_07_explicit_path_overrides_discovery(self, tmp_path: pathlib.Path) -> None:
        """AD-07: mpm install /explicit/path/.mpm ignores cwd's .mpm."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        cwd_dir = tmp_path / "test-ad07-cwd"
        cwd_dir.mkdir()

        explicit_dir = tmp_path / "test-ad07-explicit"
        explicit_dir.mkdir()
        _write_ad_mpmenv(explicit_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        result = run_mpm(
            "install",
            str(explicit_dir / ".mpm"),
            cwd=cwd_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert "mpm install: done" in result.stdout, f"stdout={result.stdout!r}"

        assert (store_base / ".packages" / "pkg-alpha").exists(), (
            f".packages/pkg-alpha not found under store {store_base}"
        )
        assert not (cwd_dir / ".packages").exists(), f".packages/ unexpectedly created in cwd {cwd_dir}"

    def test_ad_08_install_prints_found_mpm_path(self, tmp_path: pathlib.Path) -> None:
        """AD-08: mpm install prints 'found' and the path to the discovered .mpm."""
        fixtures_dir = tmp_path / "fixtures"
        manifest_bare = _build_ad_fixtures(fixtures_dir)
        work_dir = tmp_path / "test-ad08"
        work_dir.mkdir()
        _write_ad_mpmenv(work_dir, manifest_bare)

        catalog_source = f"{manifest_bare.as_uri()}@main"
        result = run_mpm(
            "install",
            cwd=work_dir,
            extra_env={"MPM_CATALOG_SOURCE": catalog_source, "MPM_ALLOW_INSECURE_REMOTES": "1"},
        )

        assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        combined = result.stdout + result.stderr
        assert "found" in combined.lower(), f"expected 'found' in combined output but got: {combined!r}"
        assert ".mpm" in combined, f"expected .mpm path in output but got: {combined!r}"
