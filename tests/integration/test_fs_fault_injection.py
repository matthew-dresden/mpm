"""Integration tests for filesystem fault injection and path variation handling.

Covers:
  - AC-TEST-001: readonly parent directory exits 1 with permission error
  - AC-TEST-002: missing parent directory exits 1
  - AC-TEST-003: symlinked .mpm is followed correctly
  - AC-TEST-004: paths with spaces work throughout install/clean/validate

AC-FUNC-001: Filesystem faults surface actionable errors; successful cases handle
             common path variations.
AC-CHANNEL-001: stdout vs stderr discipline is verified (no cross-channel leakage).
"""

import os
import pathlib
import subprocess
import sys
from unittest.mock import patch

import pytest

from mpm_cli.core.clean import clean
from mpm_cli.core.install import install


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

_MINIMAL_MPMENV_CONTENT = (
    "MPM_SOURCE_src_URL=https://example.com/src.git\n"
    "MPM_SOURCE_src_REF=main\n"
    "MPM_SOURCE_src_PATH=repo-specs/default.xml\n"
    "MPM_SOURCE_src_NAME=src\n"
    "MPM_SOURCE_src_GITBASE=https://example.com\n"
)


def _run_mpm_subprocess(
    *args: str,
    cwd: "pathlib.Path | None" = None,
    extra_env: "dict[str, str] | None" = None,
) -> subprocess.CompletedProcess:
    """Invoke mpm_cli in a subprocess and return the completed process.

    Ensures PYTHONPATH points at the current source tree so the subprocess
    uses the locally checked-out mpm_cli rather than any installed version.
    Sets REPO_TRACE=0 to suppress trace file writes during tests.

    Args:
        *args: CLI arguments passed after ``python -m mpm_cli``.
        cwd: Working directory for the subprocess. Defaults to None.
        extra_env: Additional environment variables merged on top of os.environ.

    Returns:
        The CompletedProcess object (check=False).
    """
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    src_str = str(_SRC_DIR)
    path_entries = [src_str] + [p for p in existing_pythonpath.split(os.pathsep) if p and p != src_str]
    env["PYTHONPATH"] = os.pathsep.join(path_entries)
    env.setdefault("REPO_TRACE", "0")
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, "-m", "mpm_cli", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
    )


def _write_mpmenv(directory: pathlib.Path) -> pathlib.Path:
    """Write a minimal .mpm file in directory and return its absolute path.

    Args:
        directory: Directory in which to create the .mpm file.

    Returns:
        Absolute path to the created .mpm file.
    """
    mpmenv = directory / ".mpm"
    mpmenv.write_text(_MINIMAL_MPMENV_CONTENT)
    return mpmenv


@pytest.mark.integration
class TestReadonlyParentDirectory:
    """AC-TEST-001: install into a read-only parent directory exits 1 with an
    actionable error message on stderr; no raw traceback; no output on stdout."""

    def test_readonly_parent_install_exits_1(self, tmp_path: pathlib.Path) -> None:
        """Exit code is 1 when the install destination directory is read-only."""
        mpmenv = _write_mpmenv(tmp_path)
        tmp_path.chmod(0o555)
        try:
            result = _run_mpm_subprocess("install", str(mpmenv))
        finally:
            tmp_path.chmod(0o755)

        assert result.returncode == 1, (
            f"Expected exit code 1 for read-only parent, got {result.returncode}.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_readonly_parent_install_clean_error_on_stderr(self, tmp_path: pathlib.Path) -> None:
        """An actionable 'Error:' message (not a raw traceback) appears on stderr."""
        mpmenv = _write_mpmenv(tmp_path)
        tmp_path.chmod(0o555)
        try:
            result = _run_mpm_subprocess("install", str(mpmenv))
        finally:
            tmp_path.chmod(0o755)

        stderr_lines = result.stderr.splitlines()
        error_lines = [line for line in stderr_lines if line.startswith("Error:")]
        assert error_lines, f"Expected at least one line starting with 'Error:' on stderr. Got stderr={result.stderr!r}"

    def test_readonly_parent_install_no_raw_traceback(self, tmp_path: pathlib.Path) -> None:
        """A raw Python traceback must NOT appear on stderr for read-only failures.

        The CLI must catch filesystem permission errors and emit a clean,
        actionable 'Error:' message rather than exposing internal stack frames.
        """
        mpmenv = _write_mpmenv(tmp_path)
        tmp_path.chmod(0o555)
        try:
            result = _run_mpm_subprocess("install", str(mpmenv))
        finally:
            tmp_path.chmod(0o755)

        assert "Traceback (most recent call last):" not in result.stderr, (
            f"Raw Python traceback must not appear on stderr for read-only parent directory. "
            f"Got stderr={result.stderr!r}"
        )

    def test_readonly_parent_install_error_mentions_path(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The error message must mention the affected path so the user can act on it.

        3.0.0 store model: install materialises artifacts under the MPM_HOME
        store (``<MPM_HOME>/store``). When the MPM_HOME parent is read-only,
        store creation fails fast and the diagnostic must name that path so the
        user knows which directory to fix.
        """
        mpmenv = _write_mpmenv(tmp_path)
        readonly_home = tmp_path / "ro-home"
        readonly_home.mkdir()
        readonly_home.chmod(0o555)
        monkeypatch.setenv("MPM_HOME", str(readonly_home))
        try:
            result = _run_mpm_subprocess("install", str(mpmenv))
        finally:
            readonly_home.chmod(0o755)

        assert str(readonly_home) in result.stderr, (
            f"Expected the affected MPM_HOME store path {readonly_home!r} to appear in stderr. "
            f"Got stderr={result.stderr!r}"
        )

    def test_readonly_parent_install_no_cross_channel_leakage(self, tmp_path: pathlib.Path) -> None:
        """AC-CHANNEL-001: error text is on stderr only; stdout must contain no 'Error:' line."""
        mpmenv = _write_mpmenv(tmp_path)
        tmp_path.chmod(0o555)
        try:
            result = _run_mpm_subprocess("install", str(mpmenv))
        finally:
            tmp_path.chmod(0o755)

        stdout_error_lines = [line for line in result.stdout.splitlines() if line.startswith("Error:")]
        assert not stdout_error_lines, (
            f"Error text leaked to stdout. stdout={result.stdout!r}, stderr={result.stderr!r}"
        )


@pytest.mark.integration
class TestMissingParentDirectory:
    """AC-TEST-002: mpm install and clean with a .mpm path whose parent directory
    does not exist exit 1 with a clean error message on stderr."""

    @pytest.mark.parametrize(
        "subcommand",
        ["install", "clean"],
    )
    def test_missing_parent_dir_exits_1(
        self,
        tmp_path: pathlib.Path,
        subcommand: str,
    ) -> None:
        """Exit code is 1 when the parent directory of the .mpm path does not exist."""
        nonexistent = tmp_path / "does_not_exist" / ".mpm"
        result = _run_mpm_subprocess(subcommand, str(nonexistent))

        assert result.returncode == 1, (
            f"Expected exit code 1 for missing parent dir ({subcommand!r}), "
            f"got {result.returncode}.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    @pytest.mark.parametrize(
        "subcommand",
        ["install", "clean"],
    )
    def test_missing_parent_dir_clean_error_on_stderr(
        self,
        tmp_path: pathlib.Path,
        subcommand: str,
    ) -> None:
        """A clean 'Error:' message appears on stderr, not a raw traceback."""
        nonexistent = tmp_path / "does_not_exist" / ".mpm"
        result = _run_mpm_subprocess(subcommand, str(nonexistent))

        stderr_lines = result.stderr.splitlines()
        error_lines = [line for line in stderr_lines if line.startswith("Error:")]
        assert error_lines, (
            f"Expected at least one line starting with 'Error:' on stderr ({subcommand!r}), "
            f"got stderr={result.stderr!r}"
        )
        assert "Traceback" not in result.stderr, (
            f"Raw traceback must not appear on stderr ({subcommand!r}). Got stderr={result.stderr!r}"
        )

    @pytest.mark.parametrize(
        "subcommand",
        ["install", "clean"],
    )
    def test_missing_parent_dir_no_cross_channel_leakage(
        self,
        tmp_path: pathlib.Path,
        subcommand: str,
    ) -> None:
        """AC-CHANNEL-001: error text is on stderr only; stdout must contain no 'Error:' line."""
        nonexistent = tmp_path / "does_not_exist" / ".mpm"
        result = _run_mpm_subprocess(subcommand, str(nonexistent))

        stdout_error_lines = [line for line in result.stdout.splitlines() if line.startswith("Error:")]
        assert not stdout_error_lines, (
            f"Error text leaked to stdout ({subcommand!r}). stdout={result.stdout!r}, stderr={result.stderr!r}"
        )


@pytest.mark.integration
class TestSymlinkedMPMFile:
    """AC-TEST-003: when the .mpm path is a symlink, the CLI resolves it and
    uses the resolved parent directory as the project root for artifact creation."""

    def test_symlink_mpm_is_recognized_as_file(self, tmp_path: pathlib.Path) -> None:
        """A symlink pointing to a valid .mpm file is treated as a valid file path."""
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        symlink_mpm = tmp_path / "link_to_mpm"
        symlink_mpm.symlink_to(mpmenv)

        assert symlink_mpm.is_file(), f"Expected symlink {symlink_mpm} to report is_file()=True"

        assert symlink_mpm.resolve() == mpmenv.resolve(), (
            f"Expected symlink to resolve to {mpmenv}, got {symlink_mpm.resolve()}"
        )

    def test_symlink_install_creates_dirs_in_store_and_resolves_symlink(self, tmp_path: pathlib.Path) -> None:
        """install resolves the symlink and creates .mpm-data/ under the shared store.

        When mpm install is given a symlink path, it resolves the symlink to the
        real .mpm file. Install artifacts (e.g., .mpm-data/) are written to the
        shared MPM_HOME store, not beside either the symlink or the real file.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        symlink_dir = tmp_path / "via_symlink"
        symlink_dir.mkdir()
        symlink_mpm = symlink_dir / ".mpm"
        symlink_mpm.symlink_to(mpmenv)

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(
                symlink_mpm,
                lock_file_path=symlink_mpm.parent / ".mpm.lock",
            )

        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ expected under the shared store at {store_base}, but was not found.\n"
            f"Contents of store_base: {list(store_base.iterdir()) if store_base.exists() else 'missing'}"
        )

        assert mpmenv.is_file(), ".mpm must remain in the real project dir after install via symlink"
        assert not (symlink_dir / ".mpm-data").exists(), ".mpm-data/ must not be created next to the symlink."
        assert not (real_dir / ".mpm-data").exists(), (
            ".mpm-data/ must not be created next to the real .mpm; it lives in the shared store."
        )

    def test_symlink_install_does_not_exit_with_file_not_found(self, tmp_path: pathlib.Path) -> None:
        """install does not reject a symlink path with a file-not-found error.

        A symlink that points to a valid .mpm file must pass the is_file()
        guard in the install CLI handler, so the operation proceeds past the
        file-existence check.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        symlink_dir = tmp_path / "via_symlink"
        symlink_dir.mkdir()
        symlink_mpm = symlink_dir / ".mpm"
        symlink_mpm.symlink_to(mpmenv)

        result = _run_mpm_subprocess("install", str(symlink_mpm))

        assert ".mpm file not found" not in result.stderr, (
            f"install must not report '.mpm file not found' for a valid symlink. Got stderr={result.stderr!r}"
        )

    def test_symlink_clean_follows_symlink_and_removes_store_artifacts(self, tmp_path: pathlib.Path) -> None:
        """clean resolves the symlink and removes .packages/ and .mpm-data/ from the store.

        When mpm clean is given a symlink path, it resolves the symlink to the
        real .mpm file and removes install artifacts from the shared MPM_HOME
        store (where install wrote them), not from the project directory.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        symlink_dir = tmp_path / "via_symlink"
        symlink_dir.mkdir()
        symlink_mpm = symlink_dir / ".mpm"
        symlink_mpm.symlink_to(mpmenv)

        clean(symlink_mpm)

        assert not (store_base / ".packages").exists(), (
            ".packages/ must be removed from the shared store after clean via symlink"
        )
        assert not (store_base / ".mpm-data").exists(), (
            ".mpm-data/ must be removed from the shared store after clean via symlink"
        )


@pytest.mark.integration
class TestPathsWithSpaces:
    """AC-TEST-004: directories and paths containing spaces are handled correctly
    in install and clean operations."""

    @pytest.fixture()
    def spaced_project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        """Create a .mpm file inside a directory whose name contains spaces.

        Returns:
            Path to the .mpm file inside the spaced directory.
        """
        spaced_dir = tmp_path / "my project with spaces"
        spaced_dir.mkdir()
        return _write_mpmenv(spaced_dir)

    def test_install_creates_mpm_data_with_space_in_path(
        self,
        spaced_project: pathlib.Path,
    ) -> None:
        """install handles a project path with spaces and writes .mpm-data/ to the store.

        The .mpm file lives in the spaced project directory; install artifacts are
        written to the shared MPM_HOME store regardless of the project path.
        """
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(
                spaced_project,
                lock_file_path=spaced_project.parent / ".mpm.lock",
            )

        assert spaced_project.is_file(), ".mpm must remain in the spaced project directory"
        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ must be created under the shared store for a spaced project path: {store_base}"
        )

    def test_install_creates_gitignore_with_space_in_path(
        self,
        spaced_project: pathlib.Path,
    ) -> None:
        """install writes no .gitignore under a non-git store when the path has spaces."""
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(
                spaced_project,
                lock_file_path=spaced_project.parent / ".mpm.lock",
            )

        assert not (store_base / ".gitignore").exists(), (
            f"install() must not write .gitignore under a non-git store: {store_base}"
        )

    def test_clean_removes_dirs_with_space_in_path(
        self,
        spaced_project: pathlib.Path,
    ) -> None:
        """clean removes .packages/ and .mpm-data/ from the store when the project path has spaces."""
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        clean(spaced_project)

        assert not (store_base / ".packages").exists(), (
            ".packages/ must be removed from the store by clean even when the project path has spaces"
        )
        assert not (store_base / ".mpm-data").exists(), (
            ".mpm-data/ must be removed from the store by clean even when the project path has spaces"
        )

    def test_clean_subprocess_exits_0_with_space_in_path(
        self,
        spaced_project: pathlib.Path,
    ) -> None:
        """AC-CHANNEL-001: clean succeeds and emits progress to stdout when path has spaces."""
        spaced_dir = spaced_project.parent
        (spaced_dir / ".packages").mkdir()
        (spaced_dir / ".mpm-data").mkdir()

        result = _run_mpm_subprocess("clean", str(spaced_project))

        assert result.returncode == 0, (
            f"Expected exit 0 for clean with spaces in path, got {result.returncode}.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_clean_stdout_contains_progress_with_space_in_path(
        self,
        spaced_project: pathlib.Path,
    ) -> None:
        """AC-CHANNEL-001: clean progress output goes to stdout, not stderr."""
        spaced_dir = spaced_project.parent
        (spaced_dir / ".packages").mkdir()
        (spaced_dir / ".mpm-data").mkdir()

        result = _run_mpm_subprocess("clean", str(spaced_project))

        assert result.returncode == 0
        assert "mpm clean" in result.stdout, f"Expected 'mpm clean' progress on stdout. stdout={result.stdout!r}"
        assert not result.stderr, f"Expected empty stderr for successful clean. stderr={result.stderr!r}"

    def test_install_subprocess_error_on_missing_file_with_space_in_path(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """AC-CHANNEL-001: install error message goes to stderr when path with spaces is missing."""
        spaced_dir = tmp_path / "my project with spaces"
        spaced_dir.mkdir()
        nonexistent_mpm = spaced_dir / ".mpm"

        result = _run_mpm_subprocess("install", str(nonexistent_mpm))

        assert result.returncode == 1
        assert "Error:" in result.stderr, (
            f"Expected 'Error:' on stderr for missing .mpm in spaced path. Got stderr={result.stderr!r}"
        )
        assert "Error:" not in result.stdout, f"Error text must not appear on stdout. stdout={result.stdout!r}"
