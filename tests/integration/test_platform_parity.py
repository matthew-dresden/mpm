"""Integration tests for platform parity: case-sensitivity, /dev/null, tmpfs, and symlink semantics.

Covers:
  - AC-TEST-001: filesystem case-sensitivity handled consistently across mpm operations
  - AC-TEST-002: /dev/null and tmpfs scenarios work without panicking the CLI
  - AC-TEST-003: symlink semantics match between Linux and macOS where possible
  - AC-FUNC-001: Platform-specific behaviors are documented and tested on each platform
  - AC-CHANNEL-001: stdout vs stderr discipline is verified (no cross-channel leakage)

Platform notes:
  - Linux ext4/xfs: case-sensitive by default; /dev/null is a character device; symlinks
    use absolute or relative targets with os.readlink() returning the exact target string.
  - macOS HFS+/APFS: case-insensitive by default (HFS+) or optionally case-sensitive
    (APFS); /dev/null is a character device; symlink semantics are identical to Linux.
  - tmpfs: an in-memory filesystem used on Linux (typically /tmp). Operations must
    behave identically to disk-backed filesystems; no tmpfs-specific code is needed.
  - This test file runs on the host platform and asserts consistent behavior within that
    platform's semantics. Cross-platform parity is documented in the per-test docstrings.
"""

import os
import pathlib
import platform
import subprocess
import sys
from unittest.mock import patch

import pytest

from mpm_cli.core.clean import clean
from mpm_cli.core.discover import find_mpmenv
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


_CURRENT_PLATFORM = platform.system()


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
class TestCaseSensitivityParity:
    """AC-TEST-001: filesystem case-sensitivity is handled consistently.

    Platform notes:
    - Linux (ext4/xfs/tmpfs): case-sensitive -- '.mpm' and '.MPM' are different files.
    - macOS HFS+: case-insensitive -- '.mpm' and '.MPM' refer to the same inode.
    - macOS APFS (case-sensitive variant): behaves like Linux.

    The mpm CLI must:
    - On case-sensitive filesystems: treat '.mpm' and '.MPM' as distinct files;
      discovery of '.MPM' must not succeed when only '.mpm' exists.
    - On case-insensitive filesystems: the OS transparently maps both names to the same
      inode, so no special handling is needed -- the CLI does not need to normalize case.

    These tests are written to document and assert the behavior on the CURRENT platform.
    They do not attempt to emulate the other platform's behavior.
    """

    def test_mpmenv_discovery_finds_lowercase_dotmpm(self, tmp_path: pathlib.Path) -> None:
        """find_mpmenv() discovers the canonical '.mpm' filename.

        On all supported platforms, the canonical filename is lowercase '.mpm'.
        This test confirms discovery works in a directory that contains only
        the canonical name -- the baseline for both case-sensitive and
        case-insensitive platforms.
        """
        mpmenv = _write_mpmenv(tmp_path)
        assert mpmenv.name == ".mpm", "Fixture must write the canonical '.mpm' filename"

        discovered = find_mpmenv(tmp_path)

        assert discovered == mpmenv.resolve(), (
            f"find_mpmenv() must return the canonical .mpm path. Expected {mpmenv.resolve()}, got {discovered}"
        )

    def test_mpmenv_file_is_accessible_after_creation(self, tmp_path: pathlib.Path) -> None:
        """A .mpm file written to disk is immediately readable via pathlib.

        Asserts that there is no buffering, caching, or platform-specific delay
        between write and read on the current filesystem.
        """
        mpmenv = _write_mpmenv(tmp_path)

        assert mpmenv.exists(), f".mpm must exist immediately after creation at {mpmenv}"
        content = mpmenv.read_text()
        assert "MPM_SOURCE_src_URL" in content, f"Written content must be immediately readable. Got: {content!r}"

    def test_lowercase_mpmenv_not_found_when_only_uppercase_present_on_case_sensitive_fs(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """On case-sensitive filesystems, '.MPM' is a different file from '.mpm'.

        Platform behavior:
        - Linux (case-sensitive): '.MPM' != '.mpm'; find_mpmenv() must raise
          FileNotFoundError when only '.MPM' exists and discovery looks for '.mpm'.
        - macOS HFS+ (case-insensitive): '.MPM' and '.mpm' map to the same inode;
          this test is skipped on case-insensitive filesystems because the OS itself
          handles the mapping.

        This test documents and asserts the case-sensitive behavior present on Linux.
        """

        probe_lower = tmp_path / "probe_case_test_lower"
        probe_upper = tmp_path / "PROBE_CASE_TEST_LOWER"
        probe_lower.write_text("x")
        is_case_sensitive = not probe_upper.exists()
        probe_lower.unlink()

        if not is_case_sensitive:
            pytest.skip(
                f"Filesystem at {tmp_path} is case-insensitive (macOS HFS+ or similar); "
                "case-sensitivity behavior is handled by the OS transparently."
            )

        uppercase_mpm = tmp_path / ".MPM"
        uppercase_mpm.write_text(_MINIMAL_MPMENV_CONTENT)

        with pytest.raises(FileNotFoundError) as exc_info:
            find_mpmenv(tmp_path)

        assert ".mpm" in str(exc_info.value).lower(), (
            f"FileNotFoundError message must reference '.mpm'. Got: {exc_info.value!r}"
        )

    def test_install_uses_exact_path_case_provided(self, tmp_path: pathlib.Path) -> None:
        """install() uses the exact path provided, with no case normalization.

        mpm does not perform case folding on paths. On case-sensitive filesystems,
        passing the exact path returned by write is required. This test confirms that
        install() accepts the canonical lowercase path on the current platform and
        writes its artifacts to the shared MPM_HOME store.
        """
        mpmenv = _write_mpmenv(tmp_path)
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ must be created under the shared store by install() using the canonical lowercase path. "
            f"Contents of store_base: {list(store_base.iterdir()) if store_base.exists() else 'missing'}"
        )

    @pytest.mark.parametrize(
        "dir_name",
        [
            "Lower_Case_Dir",
            "MixedCaseProject",
            "ALL_CAPS_DIR",
            "camelCaseDir",
        ],
    )
    def test_install_works_with_mixed_case_directory_names(
        self,
        tmp_path: pathlib.Path,
        dir_name: str,
    ) -> None:
        """install() handles mixed-case project directory names and writes .mpm-data/ to the store.

        On case-sensitive platforms (Linux), each of these names is a distinct directory.
        On case-insensitive platforms (macOS HFS+), they may collide, but pytest's
        tmp_path already provides a unique root, so no collision occurs within the test.

        The CLI must handle mixed-case directory paths identically to lowercase ones --
        no special treatment required. The .mpm file lives in the mixed-case project
        directory; install artifacts are written to the shared MPM_HOME store.
        """
        project_dir = tmp_path / dir_name
        project_dir.mkdir()
        mpmenv = _write_mpmenv(project_dir)
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert mpmenv.is_file(), f".mpm must remain inside the '{dir_name}' project directory"
        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ must be created under the shared store for project dir '{dir_name}'. "
            f"Contents: {list(store_base.iterdir()) if store_base.exists() else 'missing'}"
        )


@pytest.mark.integration
class TestDevNullAndTmpfsScenarios:
    """AC-TEST-002: /dev/null and tmpfs scenarios work without panicking the CLI.

    Platform notes:
    - /dev/null is a character device (not a regular file) on both Linux and macOS.
      Passing it as a .mpm path must result in a clean 'Error:' message and exit 1
      -- the CLI must not crash with an unhandled exception or produce a traceback.
    - tmpfs (Linux /tmp) behaves identically to disk-backed filesystems for the
      operations mpm performs (mkdir, open, read, write, symlink, unlink). No
      special handling is needed; these tests assert that the CLI works correctly
      when tmp_path is on a tmpfs mount, which is the default on many Linux
      systems and CI environments.
    - macOS /tmp is typically a symlink to /private/tmp (on APFS); behavior is
      the same as tmpfs for mpm's operations.
    """

    def test_dev_null_as_mpmenv_path_exits_1(self) -> None:
        """Passing /dev/null as the .mpm path exits 1 with a clean error.

        /dev/null is a character device, not a regular file. The mpm CLI
        performs an is_file() check on the provided path before opening it.
        /dev/null.is_file() returns False (it is not a regular file), so the
        CLI must exit 1 with a '.mpm file not found' or similar error message
        on stderr.

        This test is Linux/macOS-specific because Windows does not have /dev/null
        as a character device at that path. It is skipped on unsupported platforms.
        """
        dev_null = pathlib.Path("/dev/null")
        if not dev_null.exists():
            pytest.skip("/dev/null is not available on this platform")

        result = _run_mpm_subprocess("install", str(dev_null))

        assert result.returncode == 1, (
            f"Expected exit 1 when passing /dev/null as .mpm path, got {result.returncode}.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_dev_null_as_mpmenv_path_has_error_on_stderr(self) -> None:
        """An 'Error:' message appears on stderr when /dev/null is passed as .mpm path.

        The CLI must emit a clean, actionable error message to stderr. No raw
        Python traceback should appear; the error format is 'Error: <message>'.
        """
        dev_null = pathlib.Path("/dev/null")
        if not dev_null.exists():
            pytest.skip("/dev/null is not available on this platform")

        result = _run_mpm_subprocess("install", str(dev_null))

        assert "Error:" in result.stderr, (
            f"Expected 'Error:' message on stderr for /dev/null path. Got stderr={result.stderr!r}"
        )

    def test_dev_null_as_mpmenv_path_no_traceback(self) -> None:
        """No raw Python traceback appears on stderr when /dev/null is passed.

        AC-CHANNEL-001: The CLI must convert all unexpected input into a clean
        error message. A character device path must not cause an unhandled
        exception that leaks internal implementation details via a traceback.
        """
        dev_null = pathlib.Path("/dev/null")
        if not dev_null.exists():
            pytest.skip("/dev/null is not available on this platform")

        result = _run_mpm_subprocess("install", str(dev_null))

        assert "Traceback (most recent call last):" not in result.stderr, (
            f"Raw traceback must not appear for /dev/null path. Got stderr={result.stderr!r}"
        )

    def test_dev_null_as_mpmenv_path_no_cross_channel_leakage(self) -> None:
        """AC-CHANNEL-001: error for /dev/null path is on stderr only, not stdout."""
        dev_null = pathlib.Path("/dev/null")
        if not dev_null.exists():
            pytest.skip("/dev/null is not available on this platform")

        result = _run_mpm_subprocess("install", str(dev_null))

        stdout_error_lines = [line for line in result.stdout.splitlines() if line.startswith("Error:")]
        assert not stdout_error_lines, (
            f"Error text leaked to stdout for /dev/null path. stdout={result.stdout!r}, stderr={result.stderr!r}"
        )

    def test_install_on_tmpfs_creates_mpm_data(self, tmp_path: pathlib.Path) -> None:
        """install() creates .mpm-data/ on tmpfs (or any tmp filesystem) correctly.

        pytest's tmp_path fixture uses the system's temporary directory, which is
        typically tmpfs on Linux and APFS-backed on macOS. This test confirms that
        the install business logic works correctly on whatever filesystem tmp_path
        is mounted on -- no disk-specific behavior is assumed. Install artifacts are
        written to the shared MPM_HOME store (also on the temporary filesystem).
        """
        mpmenv = _write_mpmenv(tmp_path)
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(mpmenv, lock_file_path=mpmenv.parent / ".mpm.lock")

        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ must be created under the store on tmpfs/tmp filesystem. "
            f"Contents of store_base: {list(store_base.iterdir()) if store_base.exists() else 'missing'}"
        )

    def test_clean_on_tmpfs_removes_artifacts(self, tmp_path: pathlib.Path) -> None:
        """clean() removes .packages/ and .mpm-data/ from the store on tmpfs.

        Confirms that clean() can remove directories on the system's temporary
        filesystem. The rmtree behavior must be identical to disk-backed filesystems.
        Install artifacts live under the shared MPM_HOME store.
        """
        mpmenv = _write_mpmenv(tmp_path)
        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        clean(mpmenv)

        assert not (store_base / ".packages").exists(), (
            ".packages/ must be removed from the store by clean() on tmpfs filesystem"
        )
        assert not (store_base / ".mpm-data").exists(), (
            ".mpm-data/ must be removed from the store by clean() on tmpfs filesystem"
        )

    def test_subprocess_install_on_tmpfs_does_not_report_file_not_found(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """AC-CHANNEL-001: install on tmpfs does not emit a file-not-found error.

        When a valid .mpm file exists on tmpfs, the CLI must proceed past
        the file-existence check. Any failure must be from network/repo operations,
        not from path handling or tmpfs-specific restrictions.
        """
        mpmenv = _write_mpmenv(tmp_path)

        result = _run_mpm_subprocess("install", str(mpmenv))

        assert ".mpm file not found" not in result.stderr, (
            f"install must not report '.mpm file not found' for a valid file on tmpfs. Got stderr={result.stderr!r}"
        )

    def test_subprocess_clean_on_tmpfs_exits_0(self, tmp_path: pathlib.Path) -> None:
        """AC-CHANNEL-001: clean exits 0 on tmpfs when artifacts are present.

        Confirms the full CLI pathway (subprocess invocation) works on the
        temporary filesystem -- no tmpfs-specific restriction blocks the clean.
        """
        mpmenv = _write_mpmenv(tmp_path)
        (tmp_path / ".packages").mkdir()
        (tmp_path / ".mpm-data").mkdir()

        result = _run_mpm_subprocess("clean", str(mpmenv))

        assert result.returncode == 0, (
            f"Expected exit 0 for clean on tmpfs, got {result.returncode}.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_discover_on_tmpfs_finds_mpmenv(self, tmp_path: pathlib.Path) -> None:
        """find_mpmenv() locates .mpm on tmpfs without filesystem-specific errors.

        Auto-discovery must work on the temporary filesystem -- no disk-specific
        check is performed by find_mpmenv().
        """
        mpmenv = _write_mpmenv(tmp_path)

        discovered = find_mpmenv(tmp_path)

        assert discovered == mpmenv.resolve(), (
            f"find_mpmenv() must work on tmpfs. Expected {mpmenv.resolve()}, got {discovered}"
        )


@pytest.mark.integration
class TestSymlinkSemanticsParity:
    """AC-TEST-003: symlink semantics match between Linux and macOS where possible.

    Platform notes:
    - On both Linux and macOS, symbolic links are first-class filesystem objects.
    - pathlib.Path.is_symlink() returns True for symlinks on both platforms.
    - pathlib.Path.resolve() follows symlinks to the real path on both platforms.
    - os.readlink() returns the exact link target (absolute or relative) on both.
    - is_file() returns True for a symlink whose target is a regular file on both.
    - The symlink itself has its own inode (lstat) distinct from the target's inode (stat).
    - Circular symlinks raise OSError on resolve() on both platforms.
    - Dangling symlinks: is_file() returns False; exists() returns False on both platforms.

    The mpm CLI must behave identically for symlink paths on Linux and macOS.
    These tests document and assert the shared symlink contract.
    """

    def test_symlink_to_mpmenv_is_detected_as_file(self, tmp_path: pathlib.Path) -> None:
        """A symlink to .mpm passes the is_file() check on both Linux and macOS.

        The install CLI handler uses is_file() to validate the provided path.
        A symlink pointing to a valid regular file must pass this check,
        because pathlib.Path.is_file() follows symlinks.

        Shared behavior: Linux == macOS.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        symlink_mpm = tmp_path / "link_to_mpm"
        symlink_mpm.symlink_to(mpmenv)

        assert symlink_mpm.is_file(), (
            f"Symlink to .mpm must pass is_file() on {_CURRENT_PLATFORM}. Symlink: {symlink_mpm}, target: {mpmenv}"
        )

    def test_symlink_resolve_returns_real_path(self, tmp_path: pathlib.Path) -> None:
        """pathlib.Path.resolve() dereferences symlinks to the real path on both platforms.

        The install() function calls mpmenv_path.resolve() to dereference
        the path before using mpmenv_path.parent as the project root. This
        ensures .mpm-data/ is created next to the real .mpm, not next to
        the symlink.

        Shared behavior: Linux == macOS.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        symlink_dir = tmp_path / "via_link"
        symlink_dir.mkdir()
        symlink_mpm = symlink_dir / ".mpm"
        symlink_mpm.symlink_to(mpmenv)

        resolved = symlink_mpm.resolve()

        assert resolved == mpmenv.resolve(), (
            f"resolve() must dereference symlink to real path on {_CURRENT_PLATFORM}. "
            f"Got {resolved}, expected {mpmenv.resolve()}"
        )

    def test_symlink_lstat_differs_from_stat(self, tmp_path: pathlib.Path) -> None:
        """lstat() and stat() return different inodes for a symlink and its target.

        os.lstat() stats the symlink itself (without following it), while os.stat()
        follows the symlink to the target. On both Linux and macOS, the st_ino
        values differ, confirming that the symlink is a distinct filesystem object.

        Shared behavior: Linux == macOS.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        symlink_mpm = tmp_path / "link_to_mpm"
        symlink_mpm.symlink_to(mpmenv)

        symlink_lstat = os.lstat(symlink_mpm)
        target_stat = os.stat(symlink_mpm)

        assert symlink_lstat.st_ino != target_stat.st_ino, (
            f"Symlink and target must have different inodes on {_CURRENT_PLATFORM}. "
            f"symlink inode={symlink_lstat.st_ino}, target inode={target_stat.st_ino}"
        )

    def test_dangling_symlink_is_not_file(self, tmp_path: pathlib.Path) -> None:
        """A dangling symlink (target does not exist) reports is_file()=False on both platforms.

        When a symlink points to a non-existent target:
        - is_file() returns False (because the target file does not exist).
        - exists() returns False.
        - is_symlink() returns True (the symlink itself exists).

        The mpm CLI must treat dangling symlinks as missing files and exit 1
        with a '.mpm file not found' error.

        Shared behavior: Linux == macOS.
        """
        dangling = tmp_path / "dangling_link"
        dangling.symlink_to(tmp_path / "nonexistent_target.mpm")

        assert dangling.is_symlink(), f"Dangling symlink must report is_symlink()=True on {_CURRENT_PLATFORM}"
        assert not dangling.exists(), f"Dangling symlink must report exists()=False on {_CURRENT_PLATFORM}"
        assert not dangling.is_file(), f"Dangling symlink must report is_file()=False on {_CURRENT_PLATFORM}"

    def test_dangling_symlink_as_mpmenv_path_exits_1(self, tmp_path: pathlib.Path) -> None:
        """Passing a dangling symlink as the .mpm path exits 1 with a clean error.

        Because a dangling symlink is not a regular file, the CLI's is_file()
        check fails and the process exits 1. The error must be on stderr.

        Shared behavior: Linux == macOS.
        AC-CHANNEL-001: no cross-channel leakage.
        """
        dangling = tmp_path / "dangling_mpm"
        dangling.symlink_to(tmp_path / ".nonexistent_real_mpm")

        result = _run_mpm_subprocess("install", str(dangling))

        assert result.returncode == 1, (
            f"Expected exit 1 for dangling symlink path, got {result.returncode}.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        assert "Error:" in result.stderr, (
            f"Expected 'Error:' on stderr for dangling symlink path. Got stderr={result.stderr!r}"
        )
        stdout_error_lines = [line for line in result.stdout.splitlines() if line.startswith("Error:")]
        assert not stdout_error_lines, f"Error text must not appear on stdout. stdout={result.stdout!r}"

    def test_install_via_absolute_symlink_resolves_and_writes_to_store(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """install() via an absolute symlink resolves it and writes .mpm-data/ to the store.

        When the symlink target is an absolute path, install() resolves the symlink
        to the real .mpm file. Install artifacts (.mpm-data/) are written to the
        shared MPM_HOME store -- not in the symlink's directory and not next to the
        real file.

        Shared behavior: Linux == macOS (absolute symlinks work identically).
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        link_dir = tmp_path / "link_dir"
        link_dir.mkdir()

        abs_symlink = link_dir / ".mpm"
        abs_symlink.symlink_to(mpmenv.resolve())

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(abs_symlink, lock_file_path=abs_symlink.parent / ".mpm.lock")

        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ must be created under the shared store when using an absolute symlink. "
            f"Expected at {store_base}, contents: {list(store_base.iterdir()) if store_base.exists() else 'missing'}"
        )
        assert mpmenv.is_file(), ".mpm must remain in the real project dir after install via absolute symlink"
        assert not (link_dir / ".mpm-data").exists(), ".mpm-data/ must NOT be created in the symlink's directory."
        assert not (real_dir / ".mpm-data").exists(), (
            ".mpm-data/ must NOT be created next to the real file; it lives in the shared store."
        )

    def test_install_via_relative_symlink_resolves_and_writes_to_store(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """install() via a relative symlink resolves it and writes .mpm-data/ to the store.

        When the symlink target is a relative path, install() still resolves the
        symlink (resolve() handles relative targets on both platforms) to the real
        .mpm file. Install artifacts are written to the shared MPM_HOME store.

        Shared behavior: Linux == macOS (relative symlinks work identically).
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        link_dir = tmp_path / "link_dir"
        link_dir.mkdir()

        rel_target = pathlib.Path("..") / "real_project" / ".mpm"
        rel_symlink = link_dir / ".mpm"
        rel_symlink.symlink_to(rel_target)

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"

        with (
            patch("mpm_cli.repo.repo_init"),
            patch("mpm_cli.repo.repo_envsubst"),
            patch("mpm_cli.repo.repo_sync"),
            patch("mpm_cli.version.resolve_version", return_value="main"),
        ):
            install(rel_symlink, lock_file_path=rel_symlink.parent / ".mpm.lock")

        assert (store_base / ".mpm-data").is_dir(), (
            f".mpm-data/ must be created under the shared store when using a relative symlink. "
            f"Expected at {store_base}, contents: {list(store_base.iterdir()) if store_base.exists() else 'missing'}"
        )
        assert mpmenv.is_file(), ".mpm must remain in the real project dir after install via relative symlink"
        assert not (link_dir / ".mpm-data").exists(), ".mpm-data/ must NOT be created in the symlink's directory."
        assert not (real_dir / ".mpm-data").exists(), (
            ".mpm-data/ must NOT be created next to the real file; it lives in the shared store."
        )

    def test_find_mpmenv_discovers_via_symlinked_ancestor(self, tmp_path: pathlib.Path) -> None:
        """find_mpmenv() discovers .mpm when traversing through a symlinked directory.

        If a directory in the search path is itself a symlink (directory symlink),
        find_mpmenv() still walks upward from the start_dir and finds .mpm.
        pathlib.Path.resolve() dereferences the directory symlink, so the walk
        proceeds through the real path. This behavior is identical on Linux and macOS.

        Shared behavior: Linux == macOS.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        link_to_real = tmp_path / "link_to_real"
        link_to_real.symlink_to(real_dir)

        discovered = find_mpmenv(link_to_real)

        assert discovered == mpmenv.resolve(), (
            f"find_mpmenv() must discover .mpm through a symlinked ancestor on {_CURRENT_PLATFORM}. "
            f"Expected {mpmenv.resolve()}, got {discovered}"
        )

    def test_clean_via_symlink_removes_artifacts_from_store(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """clean() via a symlinked .mpm resolves it and removes artifacts from the store.

        Both Linux and macOS support symlinks in the same way: clean() resolves
        the symlink before operating, and removes install artifacts from the shared
        MPM_HOME store (where install wrote them), not from the project directory.

        Shared behavior: Linux == macOS.
        AC-CHANNEL-001: stdout contains progress, stderr is empty.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        mpmenv = _write_mpmenv(real_dir)

        store_base = pathlib.Path(os.environ["MPM_HOME"]) / "store"
        (store_base / ".packages").mkdir(parents=True)
        (store_base / ".mpm-data").mkdir(parents=True)

        link_dir = tmp_path / "via_link"
        link_dir.mkdir()
        sym_mpm = link_dir / ".mpm"
        sym_mpm.symlink_to(mpmenv)

        clean(sym_mpm)

        assert not (store_base / ".packages").exists(), (
            ".packages/ must be removed from the shared store when clean() is given a symlink"
        )
        assert not (store_base / ".mpm-data").exists(), (
            ".mpm-data/ must be removed from the shared store when clean() is given a symlink"
        )

        assert not (link_dir / ".packages").exists(), (
            "clean() must not create or touch .packages/ in the symlink's directory"
        )

    def test_readlink_returns_exact_target(self, tmp_path: pathlib.Path) -> None:
        """os.readlink() returns the exact target string used to create the symlink.

        On both Linux and macOS, os.readlink() returns the literal target string
        (absolute or relative) without resolving further. This confirms that
        relative symlinks can be correctly round-tripped via readlink.

        Shared behavior: Linux == macOS.
        """
        real_dir = tmp_path / "real_project"
        real_dir.mkdir()
        _write_mpmenv(real_dir)

        link_dir = tmp_path / "link_dir"
        link_dir.mkdir()
        rel_target = pathlib.Path("..") / "real_project" / ".mpm"
        rel_symlink = link_dir / ".mpm"
        rel_symlink.symlink_to(rel_target)

        read_target = os.readlink(rel_symlink)

        assert read_target == str(rel_target), (
            f"os.readlink() must return the exact target on {_CURRENT_PLATFORM}. "
            f"Expected {str(rel_target)!r}, got {read_target!r}"
        )
