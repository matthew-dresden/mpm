"""Shared fixtures for mpm-cli tests."""

from __future__ import annotations

import ast
import contextlib
import os
import pathlib
import shutil
import tempfile
from collections.abc import Generator

import pytest


_TMP_ROOT_ENV = "MPM_TEST_TMP_ROOT"
_TMP_ROOT_DEFAULT = "/var/tmp/mpm-test-runs"
_KEEP_TMP_ENV = "MPM_TEST_KEEP_TMP"
_XDIST_WORKER_ENV = "PYTEST_XDIST_WORKER"
_TEMP_VARS = ("TMPDIR", "TMP", "TEMP")


def _reap_dead_run_roots(parent: pathlib.Path) -> None:
    """Remove managed ``run-<pid>-*`` roots whose owning process is no longer alive.

    Recovers space leaked by a previously interrupted or killed run without ever
    touching a concurrently live run (its pid still exists), so it is safe to call
    while another test session is in progress.
    """
    if not parent.is_dir():
        return
    for child in parent.glob("run-*"):
        pid = next((int(part) for part in child.name.split("-") if part.isdigit()), None)
        if pid is None:
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            shutil.rmtree(child, ignore_errors=True)
        except PermissionError:
            continue


def pytest_configure(config: pytest.Config) -> None:
    """Point every test temp at a managed, real-filesystem run root.

    The mpm store and the vendored repo tool rely on gitlinks plus atomic
    renames that do not work on the orbstack workspace mount (fuseblk), and the
    default ``/tmp`` is a small tmpfs. So pytest's basetemp, ``tmp_path``,
    ``tmp_path_factory``, the OS tempdir that source ``tempfile.mkdtemp`` and git
    use, and any ``python -m mpm_cli`` subprocess are all redirected to a per-run
    directory under ``MPM_TEST_TMP_ROOT`` (default ``/var/tmp/mpm-test-runs``,
    an env-overridable real filesystem). The whole run root is removed in
    :func:`pytest_unconfigure`, so nothing accumulates across runs and ``/tmp`` is
    never touched. Stale roots from a crashed prior run are reaped on startup by
    dead-pid detection. Under xdist only the controller creates the root; workers
    inherit ``TMPDIR`` and ``--basetemp`` from it.
    """
    if os.environ.get(_XDIST_WORKER_ENV):
        return
    parent = pathlib.Path(os.environ.get(_TMP_ROOT_ENV, _TMP_ROOT_DEFAULT))
    parent.mkdir(parents=True, exist_ok=True)
    _reap_dead_run_roots(parent)
    run_root = parent / f"run-{os.getpid()}-{os.urandom(4).hex()}"
    run_root.mkdir(parents=True, exist_ok=True)
    for var in _TEMP_VARS:
        os.environ[var] = str(run_root)
    tempfile.tempdir = None
    if getattr(config.option, "basetemp", None) is None:
        config.option.basetemp = str(run_root / "pytest")
    config._mpm_run_root = str(run_root)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the managed run root at session end unless ``MPM_TEST_KEEP_TMP`` is set."""
    if os.environ.get(_KEEP_TMP_ENV) or os.environ.get(_XDIST_WORKER_ENV):
        return
    root = getattr(config, "_mpm_run_root", None)
    if root:
        shutil.rmtree(root, ignore_errors=True)


def _isolation_env() -> dict[str, str]:
    """Return the mandatory temp and home env floor for mpm/git subprocesses.

    A caller that passes a full replacement environment to a subprocess would
    otherwise drop ``TMPDIR``/``MPM_HOME``/``CLAUDE_CONFIG_DIR`` and let the
    child's ``tempfile.mkdtemp``, the real ``~/.mpm-home`` store, and the real
    ``~/.claude`` config escape the per-test isolation. Subprocess helpers overlay
    this floor so the isolation cannot be bypassed.
    """
    floor: dict[str, str] = {}
    for var in (*_TEMP_VARS, "MPM_HOME", "CLAUDE_CONFIG_DIR", _TMP_ROOT_ENV):
        value = os.environ.get(var)
        if value is not None:
            floor[var] = value
    return floor


_SUBPROCESS_COVERAGE_ENV_VARS: tuple[str, ...] = (
    "COV_CORE_SOURCE",
    "COV_CORE_CONFIG",
    "COV_CORE_DATAFILE",
    "COV_CORE_CONTEXT",
    "COVERAGE_PROCESS_START",
    "COVERAGE_PROCESS_CONFIG",
)


def strip_subprocess_coverage_env(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of *env* with coverage subprocess-measurement triggers removed.

    Under ``pytest --cov`` (e.g. ``make test``) pytest-cov and coverage export
    ``COV_CORE_*`` / ``COVERAGE_PROCESS_*`` so that spawned subprocesses auto-start
    coverage. A measured ``mpm`` subprocess then writes a ``.coverage-data``
    directory into its working directory -- resolved relative to the child's CWD
    on some filesystems -- which behavioural tests that inspect the child's
    filesystem (``mpm repo status --orphans``) or parse its stderr then trip over,
    non-deterministically across
    OS / filesystem. These behavioural subprocess tests do not need coverage of
    the child (the coverage gate is measured in-process on the unit tier), so the
    functional and scenario subprocess runners overlay this on the child's
    environment to keep the child deterministic without disturbing the parent
    worker's already-started in-process coverage.

    Args:
        env: The environment mapping destined for ``subprocess.run``.

    Returns:
        A shallow copy of *env* with the coverage subprocess variables removed.
    """
    cleaned = dict(env)
    for name in _SUBPROCESS_COVERAGE_ENV_VARS:
        cleaned.pop(name, None)
    return cleaned


@contextlib.contextmanager
def managed_repo_dir(tmp_path_factory: pytest.TempPathFactory, name: str) -> Generator[pathlib.Path, None, None]:
    """Yield a fresh ``tmp_path_factory`` dir and remove it on teardown.

    Session and module scoped fixtures that build real git repositories use this
    so the inode-heavy git objects are reaped promptly instead of persisting for
    the whole session inside the run root.
    """
    base = tmp_path_factory.mktemp(name)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


_TEXT_IO_METHODS = ("read_text", "write_text")


def bare_text_io_calls(source_path: pathlib.Path) -> list[tuple[int, str]]:
    """Return every bare ``.read_text()`` / ``.write_text()`` callsite in a source file.

    Parses the Python source at ``source_path`` and walks its AST for calls to
    the ``read_text`` / ``write_text`` ``pathlib.Path`` methods that do NOT pass
    an explicit ``encoding=`` keyword argument. Those bare callsites adopt the
    platform default encoding and so behave differently on Windows, which the
    utf-8 encoding sweep (AC-12 / FR-38) forbids for mpm's own source under
    ``src/mpm_cli/`` (the vendored ``repo/`` tree is out of scope).

    This is the single shared source of truth for the encoding-sweep unit tests
    (``test_add.py``, ``test_cache.py``, ``test_cached_catalogs.py``,
    ``test_install.py``); each test imports this helper rather than inlining its
    own AST walker (DRY).

    Args:
        source_path: Path to the Python source file to scan.

    Returns:
        A list of ``(lineno, method_name)`` tuples, one per bare callsite, in
        source order. ``method_name`` is ``"read_text"`` or ``"write_text"``.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    bare: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _TEXT_IO_METHODS:
            continue
        has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
        if not has_encoding:
            bare.append((node.lineno, func.attr))
    return bare


MINIMAL_MPMENV = (
    "MPM_SOURCE_s_URL=https://example.com/s.git\n"
    "MPM_SOURCE_s_REF=main\n"
    "MPM_SOURCE_s_PATH=m.xml\n"
    "MPM_SOURCE_s_NAME=s\n"
    "MPM_SOURCE_s_GITBASE=https://example.com\n"
)


DEFAULT_CATALOG_SOURCE = "https://catalog.example.com/repo.git@main"


def write_mpmenv(directory: pathlib.Path) -> pathlib.Path:
    """Write a minimal valid .mpm file in directory and return its path."""
    mpmenv = directory / ".mpm"
    mpmenv.write_text(MINIMAL_MPMENV)
    return mpmenv


def write_manifest_for_sync(directory: pathlib.Path, sub_path: str = "repo-specs/manifest.xml") -> pathlib.Path:
    """Write a minimal valid XML manifest at the repo-tool layout path inside directory.

    After ``repo init`` + ``repo sync``, manifest files live under
    ``directory/.repo/manifests/<sub_path>``.  This helper creates that directory
    structure and writes the smallest well-formed manifest that satisfies the XML
    include-walker, avoiding per-test duplication of the mkdir + write_text pattern.

    Tests that mock ``repo_init`` or ``repo_sync`` must call this helper so that
    ``install()``'s include-walker can find the manifest at the expected location.

    Args:
        directory: The source workspace directory (the path passed by install() to
            repo_init / repo_sync as ``repo_dir``).
        sub_path: Manifest path relative to the manifests repo root, matching the
            ``MPM_SOURCE_<name>_PATH`` value in the ``.mpm`` file.  Defaults
            to ``"repo-specs/manifest.xml"``.

    Returns:
        Absolute path to the written manifest file.

    Example::

        def fake_repo_init(repo_dir: str, url: str, revision: str,
                           manifest_path: str, repo_rev: str = "") -> None:
            write_manifest_for_sync(pathlib.Path(repo_dir), sub_path=manifest_path)
    """
    manifest = directory / ".repo" / "manifests" / sub_path
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<manifest></manifest>\n')
    return manifest


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"


os.environ.setdefault("REPO_TRACE", "0")


@pytest.fixture(scope="session", autouse=True)
def _subprocess_pythonpath_points_at_source_tree() -> None:
    """Ensure subprocesses spawned by tests import mpm_cli from the current source tree.

    Several test helpers invoke the CLI in a subprocess via
    ``[sys.executable, "-m", "mpm_cli", ...]``. The child Python resolves
    ``import mpm_cli`` against its own site-packages, which in some
    development environments contains a stale ``mpm_cli`` version. Prepending
    the source tree to ``PYTHONPATH`` makes ``import mpm_cli`` in the child
    resolve to the current source regardless of which venv pytest runs in.

    The fixture is session-scoped and autouse so every spawned subprocess
    inherits the modified environment without per-test opt-in.
    """
    existing = os.environ.get("PYTHONPATH", "")
    src_str = str(_SRC_DIR)
    entries = [src_str] + [p for p in existing.split(os.pathsep) if p and p != src_str]
    os.environ["PYTHONPATH"] = os.pathsep.join(entries)


@pytest.fixture()
def sample_mpmenv(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a sample two-source .mpm file."""
    mpmenv = tmp_path / ".mpm"
    mpmenv.write_text(
        "REPO_URL=https://example.com/org/repo-tool.git\n"
        "REPO_REV=v2.0.0\n"
        "GITBASE=https://example.com/org/\n"
        "CLAUDE_MARKETPLACES_DIR=.claude-marketplaces\n"
        "MPM_MARKETPLACE_INSTALL=false\n"
        "MPM_SOURCE_build_URL=https://example.com/org/build-repo.git\n"
        "MPM_SOURCE_build_REF=main\n"
        "MPM_SOURCE_build_PATH=repo-specs/common/meta.xml\n"
        "MPM_SOURCE_build_NAME=build\n"
        "MPM_SOURCE_build_GITBASE=https://example.com/org\n"
        "MPM_SOURCE_marketplaces_URL=https://example.com/org/mp-repo.git\n"
        "MPM_SOURCE_marketplaces_REF=main\n"
        "MPM_SOURCE_marketplaces_PATH=repo-specs/common/marketplaces.xml\n"
        "MPM_SOURCE_marketplaces_NAME=marketplaces\n"
        "MPM_SOURCE_marketplaces_GITBASE=https://example.com/org\n"
    )
    return mpmenv


@pytest.fixture()
def mock_git_ls_remote_output() -> str:
    """Sample git ls-remote --tags output."""
    return (
        "abc123\trefs/tags/1.0.0\n"
        "def456\trefs/tags/1.0.1\n"
        "ghi789\trefs/tags/1.1.0\n"
        "jkl012\trefs/tags/2.0.0\n"
        "mno345\trefs/tags/2.0.0^{}\n"
    )


def _make_minimal_mpm_file(tmp_path: pathlib.Path, source_name: str = "FOO") -> pathlib.Path:
    """Write a minimal .mpm file with a single source and return its path.

    Shared by unit tests (test_why_ambiguity.py) and integration tests
    (test_why_ambiguous.py) to avoid cross-layer imports.
    """
    mpm_file = tmp_path / ".mpm"
    mpm_file.write_text(
        f"GITBASE=https://github.com\n"
        f"CLAUDE_MARKETPLACES_DIR=/tmp/mkts\n"
        f"MPM_MARKETPLACE_INSTALL=false\n"
        f"MPM_SOURCE_{source_name}_URL=https://github.com/org/catalog\n"
        f"MPM_SOURCE_{source_name}_REF=main\n"
        f"MPM_SOURCE_{source_name}_PATH=./foo\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://github.com/org\n"
    )
    mpm_file.chmod(0o644)
    return mpm_file


def _write_lockfile(
    tmp_path: pathlib.Path, source_name: str, project_url: str, include_path: str | None = None
) -> pathlib.Path:
    """Write a minimal lockfile with one source, one project, and optionally one include.

    Shared by unit tests (test_why_ambiguity.py) and integration tests
    (test_why_ambiguous.py) to avoid cross-layer imports.
    """
    from mpm_cli.core.lockfile import (
        CURRENT_SCHEMA_VERSION,
        IncludeEntry,
        Lockfile,
        ProjectEntry,
        SourceEntry,
        write_lockfile,
    )
    from mpm_cli.core.url import canonicalize_repo_url

    includes = []
    if include_path:
        includes = [
            IncludeEntry(
                name="inc",
                path_in_repo=include_path,
                url="https://github.com/org/catalog",
                resolved_sha="c" * 40,
                includes=[],
            )
        ]

    lockfile = Lockfile(
        schema_version=CURRENT_SCHEMA_VERSION,
        generated_at="2024-01-01T00:00:00Z",
        generator="mpm-test",
        mpm_hash="sha256:" + "a" * 64,
        sources=[
            SourceEntry(
                alias=source_name,
                name=source_name,
                url="https://github.com/org/catalog",
                ref_spec="main",
                resolved_ref="main",
                resolved_sha="a" * 40,
                path="./foo",
                includes=includes,
                projects=[
                    ProjectEntry(
                        name="proj",
                        url=project_url,
                        canonical_url=canonicalize_repo_url(project_url),
                        ref_spec="main",
                        resolved_ref="main",
                        resolved_sha="b" * 40,
                    )
                ],
            )
        ],
    )

    lock_path = tmp_path / ".mpm.lock"
    write_lockfile(lockfile, lock_path)
    return lock_path


DOCTOR_MINIMAL_MPM_CONTENT = (
    "MPM_SOURCE_src_URL=https://example.com/org/repo.git\n"
    "MPM_SOURCE_src_REF=main\n"
    "MPM_SOURCE_src_PATH=repo-specs/meta.xml\n"
    "MPM_SOURCE_src_NAME=src\n"
    "MPM_SOURCE_src_GITBASE=https://example.com/org\n"
    "MPM_MARKETPLACE_INSTALL=false\n"
)


def write_mpm_doctor_unit(
    tmp_path: pathlib.Path,
    content: str = DOCTOR_MINIMAL_MPM_CONTENT,
) -> pathlib.Path:
    """Write a .mpm file for doctor unit tests and chmod 0o644.

    Used by tests/unit/test_doctor_consistency.py to build minimal workspaces
    for subcheck unit tests. The content parameter lets callers supply custom
    source definitions (e.g. SHA-pinned sources for dangling-SHA checks).

    Args:
        tmp_path: Directory in which to create the .mpm file.
        content: Full text of the .mpm file.

    Returns:
        Path to the written .mpm file.
    """
    mpm_file = tmp_path / ".mpm"
    mpm_file.write_text(content, encoding="utf-8")
    mpm_file.chmod(0o644)
    return mpm_file


def write_lockfile_doctor_unit(
    tmp_path: pathlib.Path,
    mpm_hash_val: str = "sha256:" + "a" * 64,
    source_names: list[str] | None = None,
    revision_specs: dict[str, str] | None = None,
    resolved_shas: dict[str, str] | None = None,
    urls: dict[str, str] | None = None,
) -> pathlib.Path:
    """Write a minimal .mpm.lock for doctor unit tests.

    Used by tests/unit/test_doctor_consistency.py. Supports multiple sources
    via the source_names, revision_specs, resolved_shas, and urls parameters.
    Defaults build a single source named 'src' with a branch-pinned revision
    (main) and a fake SHA.

    Args:
        tmp_path: Directory in which to write .mpm.lock.
        mpm_hash_val: Value to embed in the lockfile's mpm_hash field.
        source_names: Names of the sources to include. Defaults to ["src"].
        revision_specs: Per-source revision strings. Defaults to "main" for all.
        resolved_shas: Per-source resolved SHA. Defaults to "a" * 40 for all.
        urls: Per-source URL. Defaults to "https://example.com/org/repo.git" for all.

    Returns:
        Path to the written .mpm.lock file.
    """
    from mpm_cli.core.lockfile import (
        CURRENT_SCHEMA_VERSION,
        Lockfile,
        SourceEntry,
        write_lockfile,
    )

    if source_names is None:
        source_names = ["src"]
    if revision_specs is None:
        revision_specs = {name: "main" for name in source_names}
    if resolved_shas is None:
        resolved_shas = {name: "a" * 40 for name in source_names}
    if urls is None:
        urls = {name: "https://example.com/org/repo.git" for name in source_names}

    sources = [
        SourceEntry(
            alias=name,
            name=name,
            url=urls[name],
            ref_spec=revision_specs[name],
            resolved_ref=revision_specs[name],
            resolved_sha=resolved_shas[name],
            path="repo-specs/meta.xml",
        )
        for name in source_names
    ]

    lockfile = Lockfile(
        schema_version=CURRENT_SCHEMA_VERSION,
        generated_at="2024-01-01T00:00:00Z",
        generator="mpm-test",
        mpm_hash=mpm_hash_val,
        sources=sources,
    )

    lock_path = tmp_path / ".mpm.lock"
    write_lockfile(lockfile, lock_path)
    return lock_path


def write_mpm_doctor_integration(
    directory: pathlib.Path,
    source_name: str,
    url: str,
    revision: str = "main",
) -> pathlib.Path:
    """Write a .mpm file for doctor integration tests.

    Used by tests/integration/test_doctor_consistency.py. Writes a single-source
    .mpm file suitable for subprocess-driven CLI tests.

    Args:
        directory: Directory in which to create the .mpm file.
        source_name: Name of the source (used in MPM_SOURCE_<name>_* keys).
        url: Git URL for the source.
        revision: Revision spec (branch name or SHA). Defaults to "main".

    Returns:
        Path to the written .mpm file.
    """
    mpm_file = directory / ".mpm"
    mpm_file.write_text(
        f"MPM_SOURCE_{source_name}_URL={url}\n"
        f"MPM_SOURCE_{source_name}_REF={revision}\n"
        f"MPM_SOURCE_{source_name}_PATH=repo-specs/meta.xml\n"
        f"MPM_SOURCE_{source_name}_NAME={source_name}\n"
        f"MPM_SOURCE_{source_name}_GITBASE=https://example.com/org\n"
        "MPM_MARKETPLACE_INSTALL=false\n",
        encoding="utf-8",
    )
    mpm_file.chmod(0o644)
    return mpm_file


def write_lockfile_doctor_integration_multi_source(
    directory: pathlib.Path,
    mpm_hash_val: str,
    sources: list[dict],
) -> pathlib.Path:
    """Write a minimal .mpm.lock file for multiple sources (doctor integration tests).

    Shared helper used by tests/integration/test_doctor_consistency.py for test
    cases that require more than one source entry (e.g. orphan lock detection).

    Args:
        directory: Directory in which to write .mpm.lock.
        mpm_hash_val: The mpm_hash to embed in the lockfile.
        sources: List of dicts, each with keys: name, url, revision_spec, resolved_sha.

    Returns:
        Path to the written .mpm.lock file.
    """
    from mpm_cli.core.lockfile import (
        CURRENT_SCHEMA_VERSION,
        Lockfile,
        SourceEntry,
        write_lockfile,
    )

    source_entries = [
        SourceEntry(
            alias=s["name"],
            name=s["name"],
            url=s["url"],
            ref_spec=s["revision_spec"],
            resolved_ref=s["revision_spec"],
            resolved_sha=s["resolved_sha"],
            path="repo-specs/meta.xml",
        )
        for s in sources
    ]

    lockfile = Lockfile(
        schema_version=CURRENT_SCHEMA_VERSION,
        generated_at="2024-01-01T00:00:00Z",
        generator="mpm-test",
        mpm_hash=mpm_hash_val,
        sources=source_entries,
    )
    lock_path = directory / ".mpm.lock"
    write_lockfile(lockfile, lock_path)
    return lock_path


def write_lockfile_doctor_integration(
    directory: pathlib.Path,
    mpm_hash_val: str,
    source_name: str,
    url: str,
    revision_spec: str,
    resolved_sha: str,
) -> pathlib.Path:
    """Write a minimal .mpm.lock for doctor integration tests.

    Used by tests/integration/test_doctor_consistency.py. Writes a single-source
    lockfile suitable for subprocess-driven CLI tests.

    Args:
        directory: Directory in which to write .mpm.lock.
        mpm_hash_val: Value to embed in the lockfile's mpm_hash field.
        source_name: Name of the single source entry.
        url: Git URL for the source.
        revision_spec: Revision spec string (branch name or SHA).
        resolved_sha: The resolved SHA to record for the source.

    Returns:
        Path to the written .mpm.lock file.
    """
    from mpm_cli.core.lockfile import (
        CURRENT_SCHEMA_VERSION,
        Lockfile,
        SourceEntry,
        write_lockfile,
    )

    lockfile = Lockfile(
        schema_version=CURRENT_SCHEMA_VERSION,
        generated_at="2024-01-01T00:00:00Z",
        generator="mpm-test",
        mpm_hash=mpm_hash_val,
        sources=[
            SourceEntry(
                alias=source_name,
                name=source_name,
                url=url,
                ref_spec=revision_spec,
                resolved_ref=revision_spec,
                resolved_sha=resolved_sha,
                path="repo-specs/meta.xml",
            )
        ],
    )
    lock_path = directory / ".mpm.lock"
    write_lockfile(lockfile, lock_path)
    return lock_path


@pytest.fixture(autouse=True)
def _scrub_catalog_source_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Clear MPM_CATALOG_SOURCES after every test function.

    Belt-and-suspenders teardown that unconditionally deletes
    MPM_CATALOG_SOURCES from os.environ after every test, regardless of
    whether the test or any of its fixtures set it. Prevents env-var leaks
    between tests when a fixture or test directly mutates os.environ without
    using monkeypatch (which would otherwise undo changes automatically).

    The fixture is function-scoped (the default) and autouse so it runs for
    every test in the suite without per-test opt-in.
    """
    yield
    monkeypatch.delenv("MPM_CATALOG_SOURCES", raising=False)


@pytest.fixture(autouse=True)
def _isolate_mpm_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point MPM_HOME at a per-test temp dir so tests never touch the real ~/.mpm-home.

    The shared MPM_HOME store (spec Section 7.1 / Section 8 / FR-15) defaults to
    ``~/.mpm-home`` when MPM_HOME is unset. ``resolve_workspace_base_dir()`` (the
    artifact store, ``<MPM_HOME>/store``) and ``cache_dir()`` (the completion /
    catalog-audit cache, ``<MPM_HOME>/cache``) both resolve under it. Without
    isolation, every test that drives ``install`` / ``clean`` / completion caching
    would share a single real-home store and leak state between tests -- e.g. an
    end-to-end scenario reusing a prior test's repo checkout under
    ``~/.mpm-home/store/.mpm-data/sources/...``.

    This autouse fixture sets MPM_HOME to a fresh per-test temporary directory
    via ``monkeypatch.setenv`` (so it is reverted on teardown AND is inherited by
    any ``python -m mpm_cli`` subprocess the test spawns). Tests that need a
    specific MPM_HOME override it with their own ``monkeypatch.setenv`` /
    ``extra_env`` (which runs after this fixture and therefore wins); tests
    asserting the unset-default behaviour ``monkeypatch.delenv("MPM_HOME", ...)``
    likewise override it.
    """
    monkeypatch.setenv("MPM_HOME", str(tmp_path_factory.mktemp("mpm_home")))


@pytest.fixture(autouse=True)
def _isolate_claude_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point CLAUDE_CONFIG_DIR at a per-test temp dir so the real ~/.claude is never touched.

    A ``claude-marketplace`` install shells out to the real ``claude`` binary
    (``claude plugin marketplace add`` / ``plugin install`` in
    ``core/marketplace.py``); that subprocess inherits ``os.environ`` and reads
    its config from ``CLAUDE_CONFIG_DIR`` (falling back to ``~/.claude`` when
    unset). Without isolation a test that drives a real marketplace install would
    register marketplaces and plugins into the developer's real ``~/.claude``,
    each pointing at the test's temporary marketplace directory; once that temp
    directory is reaped the registrations dangle and surface as
    ``failed to load: cache-miss`` errors in Claude Code.

    This autouse fixture sets ``CLAUDE_CONFIG_DIR`` to a fresh per-test temporary
    directory (reverted on teardown via ``monkeypatch`` and inherited by every
    spawned ``claude`` and ``python -m mpm_cli`` subprocess), so marketplace
    registration is fully isolated. Tests that need a specific config override it
    with their own ``monkeypatch.setenv``.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path_factory.mktemp("claude_config")))


@pytest.fixture()
def make_install_args():
    """Factory fixture that returns a MagicMock suitable for the install CLI handler.

    Returns a callable that accepts a mpmenv path and returns a MagicMock
    suitable for passing to the install CLI handler _run(args). This allows
    integration and functional tests to invoke the CLI boundary without
    duplicating the argparse namespace setup inline.

    ``mpm install`` is hermetic (spec Section 4.3 / FR-14): it is driven solely
    by the committed ``.mpm`` (+ ``.mpm.lock``), accepts no catalog source, and
    ignores ``MPM_CATALOG_SOURCES``.  The factory therefore sets only the
    attributes the install handler actually reads (path, lock file, and the
    refresh / strict flags).

    Args: (none -- use the returned factory)

    Returns:
        A factory function that accepts mpmenv_path (Path) and returns a
        MagicMock with mpmenv_path, lock_file, and the install flags set.

    Example::

        def test_something(tmp_path, make_install_args):
            from mpm_cli.commands.install import _run
            mpmenv = tmp_path / ".mpm"
            mpmenv.write_text("...")
            args = make_install_args(mpmenv.resolve())
            with pytest.raises(SystemExit) as exc_info:
                _run(args)
            assert exc_info.value.code == 1
    """
    from unittest.mock import MagicMock

    def _factory(mpmenv_path: pathlib.Path) -> MagicMock:
        args = MagicMock()
        args.mpmenv_path = mpmenv_path
        args.lock_file = None
        args.refresh_lock = False
        args.refresh_lock_source = None
        args.strict_lock = False
        args.strict_drift = False
        return args

    return _factory


@pytest.fixture()
def _set_default_catalog_source(monkeypatch: pytest.MonkeyPatch) -> str:
    """Opt-in fixture: sets MPM_CATALOG_SOURCES to DEFAULT_CATALOG_SOURCE for one test.

    This fixture is opt-in (no ``autouse=True``).  Tests that invoke code paths
    which read ``MPM_CATALOG_SOURCES`` from the environment (e.g. subprocess-
    based tests, or tests that call ``install()`` without passing the
    ``catalog_source`` keyword argument) can request this fixture by name to
    inject the standard test value (a single source) for the duration of that test.

    The autouse ``_scrub_catalog_source_env`` fixture clears ``MPM_CATALOG_SOURCES``
    after every test; this fixture sets it fresh via ``monkeypatch.setenv`` so it
    is automatically reverted by pytest's monkeypatch teardown in addition to
    the scrubber's ``delenv`` -- belt-and-suspenders isolation.

    Returns:
        The catalog source string that was set (``DEFAULT_CATALOG_SOURCE``), so
        callers can assert against the expected value if needed.

    Example::

        def test_install_via_env(tmp_path, _set_default_catalog_source):
            from mpm_cli.core.install import install
            mpmenv = tmp_path / ".mpm"
            mpmenv.write_text("MPM_SOURCE_s_URL=https://example.com/s.git\\n...")
            # MPM_CATALOG_SOURCES is already set by the fixture
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")
    """
    monkeypatch.setenv("MPM_CATALOG_SOURCES", DEFAULT_CATALOG_SOURCE)
    return DEFAULT_CATALOG_SOURCE
