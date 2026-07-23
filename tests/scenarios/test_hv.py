"""HV (Help/Version) scenarios from `docs/integration-testing.md` §2.

Each scenario invokes `mpm` with help/version flags and asserts the
documented Pass criteria (exit code + stdout substring). Mirrors a human
running the doc's bash blocks one-by-one.

Scenarios automated:
- HV-01: Top-level help -- `mpm --help`
- HV-02: Version flag -- `mpm --version`
- HV-03: Install subcommand help -- `mpm install --help`
- HV-04: Clean subcommand help -- `mpm clean --help`
- HV-05: Validate subcommand help -- `mpm validate --help`
- HV-06: Validate xml sub-subcommand help -- `mpm validate xml --help`
- HV-07: Validate marketplace sub-subcommand help -- `mpm validate marketplace --help`
- HV-08: Bootstrap subcommand help -- `mpm bootstrap --help`
  (bootstrap was removed entirely in 3.0.0; it is no longer a registered
  command, so argparse rejects it as an unknown command -- exit 2 with an
  `invalid choice: 'bootstrap'` usage error on stderr and no stdout)
"""

from __future__ import annotations

import re

import pytest

from tests.scenarios.conftest import run_mpm


@pytest.mark.scenario
class TestHV:
    def test_hv_01_top_level_help(self) -> None:
        result = run_mpm("--help")
        assert result.returncode == 0, f"stderr={result.stderr!r}"

        for token in ("install", "clean", "validate", "search"):
            assert token in result.stdout, f"missing {token!r} in stdout"

    def test_hv_02_version_flag(self) -> None:
        result = run_mpm("--version")
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert re.search(r"mpm \d+\.\d+\.\d+", result.stdout), f"stdout does not match `mpm X.Y.Z`: {result.stdout!r}"

    def test_hv_03_install_help(self) -> None:
        result = run_mpm("install", "--help")
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert "mpmenv_path" in result.stdout

    def test_hv_04_clean_help(self) -> None:
        result = run_mpm("clean", "--help")
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert "mpmenv_path" in result.stdout

    def test_hv_05_validate_help(self) -> None:
        result = run_mpm("validate", "--help")
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert "xml" in result.stdout
        assert "marketplace" in result.stdout

    def test_hv_06_validate_xml_help(self) -> None:
        result = run_mpm("validate", "xml", "--help")
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert "--repo-root" in result.stdout

    def test_hv_07_validate_marketplace_help(self) -> None:
        result = run_mpm("validate", "marketplace", "--help")
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert "--repo-root" in result.stdout

    def test_hv_08_bootstrap_help(self) -> None:
        result = run_mpm("bootstrap", "--help")
        assert result.returncode == 2, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        assert result.stdout == "", f"Expected empty stdout, got: {result.stdout!r}"
        assert "invalid choice: 'bootstrap'" in result.stderr, (
            f"stderr must name 'bootstrap' as an invalid choice: {result.stderr!r}"
        )
