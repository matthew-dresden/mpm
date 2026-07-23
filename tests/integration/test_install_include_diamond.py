"""Integration tests for <include> diamond handling during mpm install.

AC-TEST-003: Integration test with a four-XML diamond fixture.
AC-CYCLE-001(b): mpm install succeeds with diamond; the resulting lockfile
has the shared XML appearing exactly once in the include tree.

Diamond structure:
  a.xml includes [b.xml, c.xml]
  b.xml includes [d.xml]
  c.xml includes [d.xml]   <- d.xml visited a second time via c
  d.xml has no includes

After install() resolves the diamond, d.xml must appear exactly once in the
lockfile's include tree (under b.xml, its first-walked position).  The lockfile
is written at .mpm.lock in the project root.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest

from mpm_cli.core.install import install, resolve_workspace_base_dir
from mpm_cli.core.lockfile import read_lockfile


def _write_manifest(path: pathlib.Path, includes: list[str]) -> None:
    """Write a minimal <manifest> XML with the given <include name=...> elements."""
    root = ET.Element("manifest")
    for name in includes:
        ET.SubElement(root, "include", name=name)
    ET.ElementTree(root).write(str(path), encoding="unicode", xml_declaration=False)


def _write_mpmenv(directory: pathlib.Path, manifest_path: str) -> pathlib.Path:
    """Write a minimal .mpm file referencing the given manifest XML path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(
        "MPM_MARKETPLACE_INSTALL=false\n"
        "MPM_SOURCE_test_URL=https://example.com/manifest.git\n"
        "MPM_SOURCE_test_REF=main\n"
        f"MPM_SOURCE_test_PATH={manifest_path}\n"
        "MPM_SOURCE_test_NAME=test\n"
        "MPM_SOURCE_test_GITBASE=https://example.com\n"
    )
    return mpmenv.resolve()


def _run_install_with_fixture_sync(
    mpmenv: pathlib.Path,
) -> None:
    """Run install() with repo operations patched to no-ops.

    The source dir must be pre-populated before calling this function so that
    _walk_includes finds the fixture XML files after the (no-op) repo sync.

    Args:
        mpmenv: Path to the .mpm configuration file.
    """
    with (
        patch("mpm_cli.repo.repo_init"),
        patch("mpm_cli.repo.repo_envsubst"),
        patch("mpm_cli.repo.repo_sync"),
    ):
        install(
            mpmenv,
            lock_file_path=mpmenv.parent / ".mpm.lock",
        )


def _count_include_entries(entries: list) -> int:
    """Count total IncludeEntry nodes in a nested list (recursive pre-order)."""
    total = 0
    for entry in entries:
        total += 1 + _count_include_entries(entry.includes)
    return total


def _collect_include_paths(entries: list) -> list[str]:
    """Collect path_in_repo values from all IncludeEntry nodes in DFS pre-order."""
    result: list[str] = []
    for entry in entries:
        result.append(entry.path_in_repo)
        result.extend(_collect_include_paths(entry.includes))
    return result


@pytest.mark.integration
class TestInstallIncludeDiamond:
    """Four-node diamond fixture exercising install() end-to-end.

    Diamond: A -> [B, C]; B -> D; C -> D.
    After install(), the lockfile must contain D exactly once under B.
    """

    def _build_diamond_fixture(
        self,
        base: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[pathlib.Path, pathlib.Path]:
        """Create .mpm and diamond XML files; return (mpmenv, source_dir).

        The source dir is pre-populated to simulate the post-sync checkout. In
        the 3.0.0 store model (spec Section 7.1 / FR-15) install materialises it
        under ``<MPM_HOME>/store/.mpm-data/sources/test/``; MPM_HOME is
        pinned to ``base/home`` and the fixtures are pre-populated there.
        """
        mpmenv = _write_mpmenv(base, manifest_path="a.xml")

        mpm_home = base / "home"
        mpm_home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("MPM_HOME", str(mpm_home))
        store = resolve_workspace_base_dir()

        source_dir = store / ".mpm-data" / "sources" / "test"
        manifest_repo = source_dir / ".repo" / "manifests"
        manifest_repo.mkdir(parents=True, exist_ok=True)

        _write_manifest(manifest_repo / "a.xml", includes=["b.xml", "c.xml"])
        _write_manifest(manifest_repo / "b.xml", includes=["d.xml"])
        _write_manifest(manifest_repo / "c.xml", includes=["d.xml"])
        _write_manifest(manifest_repo / "d.xml", includes=[])

        return mpmenv, source_dir

    def test_diamond_install_succeeds(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """install() does NOT raise for a diamond-shaped include fixture."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)

        _run_install_with_fixture_sync(mpmenv)

    def test_diamond_lockfile_written(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """install() writes a lockfile when the diamond fixture succeeds."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)
        _run_install_with_fixture_sync(mpmenv)
        lockfile_path = tmp_path / ".mpm.lock"
        assert lockfile_path.exists(), "lockfile must be written after successful install"

    def test_diamond_d_appears_exactly_once_in_lockfile(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """d.xml appears exactly once in the lockfile's include tree."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)
        _run_install_with_fixture_sync(mpmenv)

        lockfile_path = tmp_path / ".mpm.lock"
        lockfile = read_lockfile(lockfile_path)

        assert len(lockfile.sources) == 1
        source = lockfile.sources[0]

        all_paths = _collect_include_paths(source.includes)
        d_count = sum(1 for p in all_paths if p == "d.xml")
        assert d_count == 1, f"d.xml appeared {d_count} times in lockfile; expected exactly 1"

    def test_diamond_lockfile_include_count(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The lockfile contains 3 include entries total (b, d under b, c -- d deduped)."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)
        _run_install_with_fixture_sync(mpmenv)

        lockfile_path = tmp_path / ".mpm.lock"
        lockfile = read_lockfile(lockfile_path)

        source = lockfile.sources[0]
        total_includes = _count_include_entries(source.includes)

        assert total_includes == 3, f"expected 3 include entries (b, d, c); got {total_includes}"

    def test_diamond_d_under_b_not_c(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """d.xml is a child of b.xml (first-walked position), not of c.xml."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)
        _run_install_with_fixture_sync(mpmenv)

        lockfile_path = tmp_path / ".mpm.lock"
        lockfile = read_lockfile(lockfile_path)

        source = lockfile.sources[0]

        assert len(source.includes) == 2
        b_entry = source.includes[0]
        c_entry = source.includes[1]

        b_child_paths = [e.path_in_repo for e in b_entry.includes]
        assert "d.xml" in b_child_paths, "d.xml must appear under b.xml in lockfile"

        c_child_paths = [e.path_in_repo for e in c_entry.includes]
        assert "d.xml" not in c_child_paths, "d.xml must NOT appear under c.xml (deduped)"

    def test_diamond_c_has_no_children_in_lockfile(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After diamond dedup, c.xml has zero child includes in the lockfile."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)
        _run_install_with_fixture_sync(mpmenv)

        lockfile_path = tmp_path / ".mpm.lock"
        lockfile = read_lockfile(lockfile_path)

        source = lockfile.sources[0]
        c_entry = source.includes[1]
        assert c_entry.includes == [], "c.xml must have no child includes in lockfile"

    def test_diamond_dfs_order_in_lockfile(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lockfile include order matches DFS pre-order: b, d (under b), c."""
        mpmenv, _source_dir = self._build_diamond_fixture(tmp_path, monkeypatch)
        _run_install_with_fixture_sync(mpmenv)

        lockfile_path = tmp_path / ".mpm.lock"
        lockfile = read_lockfile(lockfile_path)

        source = lockfile.sources[0]
        all_paths = _collect_include_paths(source.includes)

        assert all_paths[0] == "b.xml"
        assert all_paths[1] == "d.xml"
        assert all_paths[2] == "c.xml"
        assert len(all_paths) == 3
