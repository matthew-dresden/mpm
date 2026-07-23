"""Regression guard for E0-INSTALL-RELATIVE: mpm install .mpm relative path.

Bug reference: E0-INSTALL-RELATIVE -- when the user runs 'mpm install .mpm'
with a relative path argument, the path was passed as-is to downstream code that
enforces an absolute path requirement. Specifically, XmlManifest.__init__ in
src/mpm_cli/repo/manifest_xml.py line 409-410 asserts:

    if manifest_file != os.path.abspath(manifest_file):
        raise ManifestParseError("manifest_file must be abspath")

Before the fix, the relative Path('.mpm') flowed through install._run() into
parse_mpmenv() and install() without being converted to an absolute path, causing
ManifestParseError at the parser boundary. After the fix, install._run() calls
args.mpmenv_path.resolve() at the CLI boundary before invoking any downstream
code, so a relative '.mpm' argument is always resolved to an absolute path
regardless of the calling working directory.

Root cause: install._run() did not call .resolve() on the explicit
mpmenv_path argument (the auto-discovery path is already absolute because
find_mpmenv() returns an absolute path, but an explicit relative argument
bypassed the absolute-path requirement).

Fix: install._run() calls args.mpmenv_path = args.mpmenv_path.resolve()
immediately after the auto-discovery branch, before any downstream calls. This
converts a relative path like '.mpm' to the fully-resolved absolute path.

This regression guard asserts that:
1. Passing a relative '.mpm' Path to _run() resolves it to an absolute path
   before invoking install() (AC-TEST-001, AC-TEST-002).
2. The resolved path is correct -- it equals the absolute path to the .mpm
   file in the working directory (AC-TEST-001).
3. The resolve() call in install._run() is structurally present in the source
   so any future removal of the line is immediately detected (AC-FUNC-001).
4. Stdout vs stderr discipline: no error appears on stdout when the relative
   path resolves correctly (AC-CHANNEL-001).
"""

import inspect
import pathlib
from unittest.mock import patch

import pytest

import mpm_cli.commands.install as install_module
from mpm_cli.commands.install import _run
from tests.conftest import write_mpmenv


def _make_args(mpmenv_path: pathlib.Path) -> object:
    """Return a minimal args namespace with mpmenv_path set."""
    from unittest.mock import MagicMock

    args = MagicMock()
    args.mpmenv_path = mpmenv_path
    return args


@pytest.mark.unit
def test_regression_relative_mpm_path_resolved_to_absolute_before_install(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-TEST-001 / AC-TEST-002: relative '.mpm' Path is resolved to absolute before install().

    This test reproduces the exact bug condition from E0-INSTALL-RELATIVE:
    install._run() receives a relative pathlib.Path('.mpm') as the
    mpmenv_path argument (matching what argparse produces when the user
    types 'mpm install .mpm'). Before the fix, this relative path was
    forwarded as-is to parse_mpmenv() and install(), which eventually
    reached XmlManifest.__init__ where it triggered:

        ManifestParseError("manifest_file must be abspath")

    After the fix, args.mpmenv_path = args.mpmenv_path.resolve() runs
    at the CLI boundary, converting the relative path to an absolute path
    that satisfies the downstream abspath requirement.

    This test verifies the fix is in place by:
    1. Arranging a real .mpm file in tmp_path.
    2. Changing the working directory to tmp_path so that Path('.mpm').resolve()
       produces the correct absolute path.
    3. Passing a relative Path('.mpm') to _run() via mocked args.
    4. Asserting that install() receives an absolute path, not the relative one.

    If this test fails (install receives a non-absolute path), the resolve()
    call in install._run() has been removed and E0-INSTALL-RELATIVE has regressed.

    AC-TEST-001, AC-TEST-002
    """
    write_mpmenv(tmp_path)
    monkeypatch.chdir(tmp_path)

    relative_path = pathlib.Path(".mpm")
    assert not relative_path.is_absolute(), "Test setup: .mpm must be a relative path for this test."

    received_paths: list[pathlib.Path] = []

    def _capture_install(path: pathlib.Path, **kwargs) -> None:
        received_paths.append(path)

    args = _make_args(relative_path)

    with patch("mpm_cli.commands.install.install", side_effect=_capture_install):
        with patch("mpm_cli.core.mpmenv.parse_mpmenv"):
            _run(args)

    assert len(received_paths) == 1, (
        "E0-INSTALL-RELATIVE regression: install() was not called exactly once. "
        f"install() call count: {len(received_paths)}"
    )

    received = received_paths[0]
    assert received.is_absolute(), (
        "E0-INSTALL-RELATIVE regression: install() received a non-absolute path. "
        f"Got {received!r}. "
        "The args.mpmenv_path.resolve() call in install._run() has been removed "
        "or moved after the install() invocation. "
        "Restore 'args.mpmenv_path = args.mpmenv_path.resolve()' immediately "
        "after the auto-discovery branch in src/mpm_cli/commands/install.py."
    )

    expected_absolute = (tmp_path / ".mpm").resolve()
    assert received == expected_absolute, (
        "E0-INSTALL-RELATIVE regression: install() received the wrong absolute path. "
        f"Expected {expected_absolute!r}, got {received!r}. "
        "The resolve() call must convert relative '.mpm' to the path of the "
        ".mpm file in the calling working directory."
    )


@pytest.mark.unit
def test_regression_relative_subdir_mpm_resolved_to_absolute(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-TEST-002: relative subdir path 'subdir/.mpm' is resolved to absolute.

    Verifies the exact bug condition with a relative path that includes a
    subdirectory component, e.g. 'mpm install subdir/.mpm'. Both simple
    '.mpm' and 'subdir/.mpm' relative forms must be resolved to absolute
    paths before reaching any downstream code.

    Arrange: Write .mpm in a subdirectory of tmp_path. chdir to tmp_path.
    Act: Pass relative pathlib.Path('subdir/.mpm') to _run().
    Assert: install() receives an absolute path matching subdir/.mpm resolved
            from tmp_path.

    AC-TEST-002
    """
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    write_mpmenv(subdir)
    monkeypatch.chdir(tmp_path)

    relative_path = pathlib.Path("subdir/.mpm")
    assert not relative_path.is_absolute(), "Test setup: path must be relative."

    received_paths: list[pathlib.Path] = []

    def _capture_install(path: pathlib.Path, **kwargs) -> None:
        received_paths.append(path)

    args = _make_args(relative_path)

    with patch("mpm_cli.commands.install.install", side_effect=_capture_install):
        with patch("mpm_cli.core.mpmenv.parse_mpmenv"):
            _run(args)

    assert len(received_paths) == 1, (
        f"E0-INSTALL-RELATIVE regression: install() not called once for subdir path. call count: {len(received_paths)}"
    )

    received = received_paths[0]
    assert received.is_absolute(), (
        "E0-INSTALL-RELATIVE regression: install() received non-absolute path for "
        f"'subdir/.mpm' relative argument. Got {received!r}."
    )

    expected_absolute = (tmp_path / "subdir" / ".mpm").resolve()
    assert received == expected_absolute, (
        "E0-INSTALL-RELATIVE regression: install() received wrong resolved path. "
        f"Expected {expected_absolute!r}, got {received!r}."
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "rel_mpm_str",
    [
        ".mpm",
        "./subdir/.mpm",
    ],
    ids=["simple_dot_mpm", "subdir_dot_mpm"],
)
def test_regression_install_receives_absolute_path_for_relative_inputs(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    rel_mpm_str: str,
) -> None:
    """AC-TEST-002: Both relative '.mpm' forms are resolved to absolute paths.

    Parametrized over the two relative path forms that the original
    E0-INSTALL-RELATIVE bug affected. In both cases, install() must receive
    an absolute path, never the original relative Path object.

    If this test fails for any parametrized case, the resolve() call in
    install._run() is not covering that relative path variant.

    AC-TEST-002
    """
    rel_path = pathlib.Path(rel_mpm_str)
    assert not rel_path.is_absolute(), f"Test setup error: {rel_mpm_str!r} must be relative."

    mpm_file = (tmp_path / rel_path).resolve()
    mpm_file.parent.mkdir(parents=True, exist_ok=True)
    mpm_file.write_text(
        "MPM_SOURCE_s_URL=https://example.com/s.git\n"
        "MPM_SOURCE_s_REF=main\n"
        "MPM_SOURCE_s_PATH=m.xml\n"
        "MPM_SOURCE_s_NAME=s\n"
        "MPM_SOURCE_s_GITBASE=https://example.com\n"
    )
    monkeypatch.chdir(tmp_path)

    received_paths: list[pathlib.Path] = []

    def _capture(path: pathlib.Path, **kwargs) -> None:
        received_paths.append(path)

    args = _make_args(rel_path)

    with patch("mpm_cli.commands.install.install", side_effect=_capture):
        with patch("mpm_cli.core.mpmenv.parse_mpmenv"):
            _run(args)

    assert len(received_paths) == 1, f"E0-INSTALL-RELATIVE regression [{rel_mpm_str!r}]: install() not called once."

    received = received_paths[0]
    assert received.is_absolute(), (
        f"E0-INSTALL-RELATIVE regression [{rel_mpm_str!r}]: install() received "
        f"non-absolute path {received!r}. The .resolve() call is missing."
    )


@pytest.mark.unit
def test_regression_current_code_passes_absolute_path_to_install(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-TEST-003: Current fixed code resolves relative '.mpm' to an absolute path.

    Verifies that the existing fix is functionally correct: when _run() is called
    with a relative Path('.mpm') from a directory where .mpm exists, install()
    is called with an absolute path equal to the resolved .mpm file.

    This is the positive assertion that the fix works end-to-end: the relative
    path resolves to an absolute path and install() receives the correct file.

    AC-TEST-003
    """
    mpmenv = write_mpmenv(tmp_path)
    monkeypatch.chdir(tmp_path)

    received_paths: list[pathlib.Path] = []

    def _capture_install(path: pathlib.Path, **kwargs) -> None:
        received_paths.append(path)

    args = _make_args(pathlib.Path(".mpm"))

    with patch("mpm_cli.commands.install.install", side_effect=_capture_install):
        with patch("mpm_cli.core.mpmenv.parse_mpmenv"):
            _run(args)

    assert len(received_paths) == 1
    received = received_paths[0]

    assert received.is_absolute(), (
        "AC-TEST-003: The current fix is not resolving the path to absolute. "
        f"Got {received!r}. Check src/mpm_cli/commands/install.py _run()."
    )

    assert received == mpmenv.resolve(), (
        "AC-TEST-003: The resolved path does not match the expected .mpm location. "
        f"Expected {mpmenv.resolve()!r}, got {received!r}."
    )


@pytest.mark.unit
def test_regression_resolve_call_present_in_install_run_source() -> None:
    """AC-FUNC-001: args.mpmenv_path.resolve() is present in install._run source.

    Inspects the source of install._run() to confirm that the .resolve() call
    used to convert a relative path to absolute is still in place. If this test
    fails, the structural fix for E0-INSTALL-RELATIVE has been removed from
    install._run() and the bug would regress for any relative '.mpm' argument.

    The exact pattern expected is 'args.mpmenv_path = args.mpmenv_path.resolve()'
    which converts any relative pathlib.Path to its resolved absolute counterpart.

    AC-FUNC-001
    """
    source = inspect.getsource(_run)

    assert "args.mpmenv_path.resolve()" in source, (
        "E0-INSTALL-RELATIVE regression guard: args.mpmenv_path.resolve() is no "
        "longer present in install._run(). The fix that converts a relative '.mpm' "
        "path to an absolute path before invoking parse_mpmenv() and install() has "
        "been removed. Restore the following line in install._run() before the "
        "parse_mpmenv() call:\n"
        "    args.mpmenv_path = args.mpmenv_path.resolve()"
    )


@pytest.mark.unit
def test_regression_resolve_precedes_parse_and_install_in_source() -> None:
    """Invariant guard: resolve() precedes parse_mpmenv() and install() in _run source.

    Invariant under guard: catalog-source resolution (args.mpmenv_path.resolve())
    happens BEFORE .mpm is parsed (parse_mpmenv()) AND BEFORE the core
    install() is invoked, ensuring every downstream call always receives an
    absolute path regardless of whether --catalog-source was supplied.

    How this exercises the invariant under the new install state machine
    (src/mpm_cli/core/install.py): _run() is the CLI boundary for
    'mpm install'. When the operator supplies a relative .mpm path, _run()
    must resolve the path before delegating to parse_mpmenv() and then to
    install(). This test inspects the source of _run() and asserts that the
    character positions satisfy:
        resolve_pos < parse_pos < install_pos
    so that any future refactor that moves the resolve() call after either
    downstream call is immediately caught.

    install is hermetic (spec Section 4.3 / FR-14): _run() does not thread a
    catalog source into install().  The install() call in the state machine is
    formatted as a multi-line call: install(\n    args.mpmenv_path, ...). The
    test locates the install invocation by searching for the keyword argument
    'refresh_lock=args.refresh_lock' that is unique to the install() invocation.

    AC-FUNC-001
    """
    source = inspect.getsource(_run)

    resolve_pos = source.find("args.mpmenv_path.resolve()")
    parse_pos = source.find("parse_mpmenv(")

    install_pos = source.find("refresh_lock=args.refresh_lock")

    assert resolve_pos != -1, (
        "E0-INSTALL-RELATIVE regression guard: resolve() call not found in _run. "
        "See AC-FUNC-001 guard in test_regression_resolve_call_present_in_install_run_source."
    )
    assert parse_pos != -1, (
        "E0-INSTALL-RELATIVE regression guard: parse_mpmenv() call not found in _run. "
        "The install command must call parse_mpmenv() to validate the .mpm file."
    )
    assert install_pos != -1, (
        "E0-INSTALL-RELATIVE regression guard: refresh_lock=args.refresh_lock keyword "
        "argument not found in _run. The install() call must be present so the ordering "
        "invariant can be checked. Check that install() is called in "
        "src/mpm_cli/commands/install.py."
    )

    assert resolve_pos < parse_pos, (
        "E0-INSTALL-RELATIVE regression guard: resolve() appears AFTER parse_mpmenv() "
        "in _run. The path must be resolved to absolute before parse_mpmenv() is called, "
        f"otherwise parse_mpmenv() may receive a relative path. "
        f"resolve() position: {resolve_pos}, parse_mpmenv() position: {parse_pos}"
    )

    assert resolve_pos < install_pos, (
        "E0-INSTALL-RELATIVE regression guard: resolve() appears AFTER install() in _run. "
        "The path must be resolved before install() is invoked. "
        f"resolve() position: {resolve_pos}, install() position: {install_pos}"
    )


@pytest.mark.unit
def test_regression_relative_path_success_no_error_on_stdout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """AC-CHANNEL-001: resolving a relative '.mpm' path does not produce errors on stdout.

    When _run() receives a relative '.mpm' path that resolves to an existing
    file, no error message must appear on stdout. Errors must be written to
    stderr only. This verifies the channel discipline: the resolve() fix must
    not introduce any output on stdout.

    AC-CHANNEL-001
    """
    write_mpmenv(tmp_path)
    monkeypatch.chdir(tmp_path)

    args = _make_args(pathlib.Path(".mpm"))

    with patch("mpm_cli.commands.install.install"):
        with patch("mpm_cli.core.mpmenv.parse_mpmenv"):
            _run(args)

    captured = capsys.readouterr()
    assert "Error" not in captured.out, (
        "AC-CHANNEL-001: An 'Error' message appeared on stdout when resolving a "
        "valid relative '.mpm' path. Error output must go to stderr only. "
        f"stdout content: {captured.out!r}"
    )
    assert ".mpm file not found" not in captured.out, (
        "AC-CHANNEL-001: '.mpm file not found' error leaked to stdout. "
        "All error messages must be written to stderr via print(..., file=sys.stderr). "
        f"stdout content: {captured.out!r}"
    )


@pytest.mark.unit
def test_regression_missing_relative_path_error_goes_to_stderr(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """AC-CHANNEL-001: missing relative '.mpm' error goes to stderr, not stdout.

    When _run() receives a relative '.mpm' path that resolves to a
    non-existent file, the error message must appear on stderr and must NOT
    appear on stdout. This verifies channel discipline for the error path.

    Arrange: Empty tmp_path (no .mpm). chdir to tmp_path.
    Act: Pass relative Path('.mpm') to _run() -- file does not exist.
    Assert: SystemExit(1) raised; error on stderr; nothing on stdout.

    AC-CHANNEL-001
    """
    monkeypatch.chdir(tmp_path)

    args = _make_args(pathlib.Path(".mpm"))

    with pytest.raises(SystemExit) as exc_info:
        _run(args)

    assert exc_info.value.code == 1, (
        f"AC-CHANNEL-001: Expected SystemExit(1) for missing relative '.mpm'. Got exit code {exc_info.value.code!r}."
    )

    captured = capsys.readouterr()

    assert ".mpm file not found" in captured.err, (
        f"AC-CHANNEL-001: '.mpm file not found' error must appear on stderr. stderr content: {captured.err!r}"
    )

    assert ".mpm file not found" not in captured.out, (
        f"AC-CHANNEL-001: '.mpm file not found' error must NOT appear on stdout. stdout content: {captured.out!r}"
    )


@pytest.mark.unit
def test_regression_install_module_has_run_function() -> None:
    """Structural guard: install module exposes _run callable.

    Verifies that the _run function still exists in mpm_cli.commands.install.
    If _run is renamed or removed, the install command entry point is broken
    and the regression guards above would all fail to import.

    AC-FUNC-001
    """
    assert hasattr(install_module, "_run"), (
        "E0-INSTALL-RELATIVE regression guard: _run is no longer present in "
        "mpm_cli.commands.install. The install command entry point has been "
        "renamed or removed. Restore _run() in src/mpm_cli/commands/install.py."
    )
    assert callable(install_module._run), (
        "E0-INSTALL-RELATIVE regression guard: install_module._run is not callable. "
        "Expected a function, got {type(install_module._run)!r}."
    )
