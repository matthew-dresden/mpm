"""Parametrised snapshot harness for ``mpm --help`` output.

Drives each command's ``--help`` output through ``subprocess.run`` and diffs
the captured stdout against a fixture file on disk (byte-for-byte). A failing
assertion names the fixture path and the captured-bytes length so operators can
regenerate the fixture deterministically.

Fixture files live under ``tests/fixtures/help/``. Each file contains the
verbatim stdout that ``python -m mpm_cli [subcommand...] --help`` must
produce.

Naming convention:
- ``mpm-toplevel.txt`` -- top-level ``mpm --help``
- ``mpm-<command>.txt`` -- ``mpm <command> --help``
- ``mpm-<group>-<subcommand>.txt`` -- ``mpm <group> <subcommand> --help``

See ``tests/fixtures/help/README.md`` for the full regeneration procedure.

All tests are decorated with ``@pytest.mark.functional``.
"""

import os
import pathlib
import sys
import subprocess

import pytest


_FIXTURES_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent / "fixtures" / "help"


_HELP_CASES: list[tuple[str, tuple[str, ...], str]] = [
    ("mpm-toplevel", (), "mpm-toplevel.txt"),
    ("mpm-search", ("search",), "mpm-search.txt"),
    ("mpm-marketplace", ("marketplace",), "mpm-marketplace.txt"),
    ("mpm-add", ("add",), "mpm-add.txt"),
    ("mpm-remove", ("remove",), "mpm-remove.txt"),
    ("mpm-list", ("list",), "mpm-list.txt"),
    ("mpm-clean", ("clean",), "mpm-clean.txt"),
    ("mpm-outdated", ("outdated",), "mpm-outdated.txt"),
    ("mpm-why", ("why",), "mpm-why.txt"),
    ("mpm-install", ("install",), "mpm-install.txt"),
    ("mpm-doctor", ("doctor",), "mpm-doctor.txt"),
    ("mpm-catalog", ("catalog",), "mpm-catalog.txt"),
    ("mpm-catalog-audit", ("catalog", "audit"), "mpm-catalog-audit.txt"),
    ("mpm-completion", ("completion",), "mpm-completion.txt"),
]


def _clean_env() -> dict[str, str]:
    """Return a subprocess environment with deterministic rendering settings.

    Produces a copy of ``os.environ`` with:

    - ``NO_COLOR=1`` -- disables ANSI colour codes from the mpm output layer
      and from the terminal library (strips colour regardless of TTY state).
    - ``MPM_CATALOG_SOURCES`` removed -- prevents any ambient catalog-source
      override from bleeding into the help text.
    - ``COLUMNS=80`` -- pins the terminal width so argparse wraps at a fixed
      column count and output is identical across hosts with different
      ``$COLUMNS`` or ``TIOCGWINSZ`` values.

    Returns:
        A new dict (os.environ is not mutated).
    """
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    env.pop("MPM_CATALOG_SOURCES", None)
    env["COLUMNS"] = "80"
    return env


@pytest.mark.functional
@pytest.mark.parametrize(
    "case_id,argv,fixture_name",
    _HELP_CASES,
    ids=[row[0] for row in _HELP_CASES],
)
def test_help_snapshot(case_id: str, argv: tuple[str, ...], fixture_name: str) -> None:
    """Byte-for-byte snapshot test for ``mpm [subcommand...] --help`` output.

    For each row in ``_HELP_CASES``:

    1. Reads the fixture file bytes.
    2. Invokes ``python -m mpm_cli [*argv] --help`` via subprocess.
    3. Asserts exit code 0.
    4. Asserts stderr is empty.
    5. Asserts stdout matches the fixture bytes exactly.

    On mismatch, the assertion message includes the fixture path and the
    captured-bytes length to guide regeneration.

    Args:
        case_id: Unique identifier for this snapshot case (used as the
            pytest parametrize ID).
        argv: Tuple of CLI tokens prepended before ``--help``.
        fixture_name: File name inside ``_FIXTURES_DIR`` containing the
            expected stdout bytes.
    """
    fixture_path = _FIXTURES_DIR / fixture_name
    expected_bytes = fixture_path.read_bytes()

    cmd = [sys.executable, "-m", "mpm_cli", *argv, "--help"]
    result = subprocess.run(cmd, capture_output=True, check=False, env=_clean_env())

    assert result.returncode == 0, (
        f"[{case_id}] expected exit code 0, got {result.returncode}.\n  stderr: {result.stderr!r}"
    )

    assert result.stderr == b"", (
        f"[{case_id}] expected empty stderr, got {len(result.stderr)} bytes.\n  stderr: {result.stderr!r}"
    )

    assert result.stdout == expected_bytes, (
        f"[{case_id}] stdout does not match fixture.\n"
        f"  fixture: {fixture_path}\n"
        f"  fixture bytes: {len(expected_bytes)}\n"
        f"  captured bytes: {len(result.stdout)}\n"
        f"  To regenerate: python -m mpm_cli {' '.join(argv)} --help "
        f"> {fixture_path}"
    )
