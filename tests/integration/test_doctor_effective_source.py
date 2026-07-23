"""Integration tests for 'mpm doctor' effective catalog source resolution (subcheck 6).

Drives the full CLI via subprocess with controlled environment variables for
each catalog-source precedence combination.

AC-TEST-002: Integration tests in this file cover all precedence combinations
and assert stdout contains the resolved value AND the provenance suffix.
AC-CYCLE-001: End-to-end cycle test with a leaked MPM_CATALOG_SOURCES env var.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from tests.conftest import (
    write_mpm_doctor_integration as _write_mpm,
    write_lockfile_doctor_integration as _write_lockfile,
)


def _run_mpm_doctor(
    mpm_file: pathlib.Path,
    *,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run 'mpm doctor' via subprocess with controlled environment.

    Starts from a clean copy of os.environ with MPM_CATALOG_SOURCES stripped,
    then applies extra_env on top. This ensures tests start with a predictable
    environment regardless of what the operator's shell has exported.

    Args:
        mpm_file: Path to the .mpm file to pass as --mpm-file.
        extra_env: Additional environment variables to set before running.
        extra_args: Additional CLI arguments (beyond --mpm-file).

    Returns:
        The completed process object with stdout, stderr, and returncode.
    """
    env = dict(os.environ)

    env.pop("MPM_CATALOG_SOURCES", None)
    if extra_env:
        env.update(extra_env)

    cmd = [sys.executable, "-m", "mpm_cli", "doctor", "--mpm-file", str(mpm_file)]
    if extra_args:
        cmd.extend(extra_args)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_minimal_mpm(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a minimal .mpm file and return its path."""
    return _write_mpm(tmp_path, "src", "https://example.com/org/repo.git")


@pytest.mark.integration
class TestDoctorEffectiveSourceEnvVarOnly:
    """mpm doctor with only MPM_CATALOG_SOURCES set prints env var value + provenance."""

    def test_env_var_value_appears_in_stdout(self, tmp_path: pathlib.Path) -> None:
        """Stdout contains the MPM_CATALOG_SOURCES value."""
        env_value = "https://env.example.com/repo.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": env_value},
        )

        assert env_value in result.stdout

    def test_env_var_provenance_suffix_in_stdout(self, tmp_path: pathlib.Path) -> None:
        """Stdout contains the env-var provenance suffix."""
        env_value = "https://env.example.com/repo.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": env_value},
        )

        assert "(from MPM_CATALOG_SOURCES env var)" in result.stdout


@pytest.mark.integration
class TestDoctorEffectiveSourceCliWins:
    """mpm doctor --catalog-source wins over MPM_CATALOG_SOURCES when both are set."""

    def test_cli_value_appears_in_stdout(self, tmp_path: pathlib.Path) -> None:
        """Stdout contains the --catalog-source CLI flag value, not the env var value."""
        cli_value = "https://cli.example.com/repo.git@main"
        env_value = "https://env.example.com/repo.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": env_value},
            extra_args=["--catalog-source", cli_value],
        )

        assert cli_value in result.stdout

    def test_cli_provenance_suffix_in_stdout(self, tmp_path: pathlib.Path) -> None:
        """Stdout contains the CLI-flag provenance suffix when both CLI and env var are set."""
        cli_value = "https://cli.example.com/repo.git@main"
        env_value = "https://env.example.com/repo.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": env_value},
            extra_args=["--catalog-source", cli_value],
        )

        assert "(from --catalog-source CLI flag)" in result.stdout

    def test_env_value_absent_from_stdout_when_cli_wins(self, tmp_path: pathlib.Path) -> None:
        """Env var value does not appear in stdout when CLI flag overrides it."""
        cli_value = "https://cli.example.com/repo.git@main"
        env_value = "https://env.example.com/repo.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": env_value},
            extra_args=["--catalog-source", cli_value],
        )

        assert env_value not in result.stdout


@pytest.mark.integration
class TestDoctorEffectiveSourceLockfilePresent:
    """A present v4 lockfile does not contribute a catalog source to provenance."""

    def _write_v4_lockfile(self, directory: pathlib.Path, mpm_hash_val: str) -> pathlib.Path:
        """Write a schema-v4 .mpm.lock with one source and no [catalog] block."""
        return _write_lockfile(
            directory,
            mpm_hash_val=mpm_hash_val,
            source_name="src",
            url="https://example.com/org/repo.git",
            revision_spec="main",
            resolved_sha="a" * 40,
        )

    def test_lockfile_present_reports_none_configured(self, tmp_path: pathlib.Path) -> None:
        """With only a v4 lockfile (no CLI flag, no env var), doctor reports none configured.

        Under schema v4 the lockfile carries no catalog source, so it cannot stand
        in for the removed [catalog].source tier: the effective source is none.
        """
        from mpm_cli.core.mpm_hash import mpm_hash

        mpm_file = _write_minimal_mpm(tmp_path)
        real_hash = mpm_hash(mpm_file)
        self._write_v4_lockfile(tmp_path, real_hash)

        result = _run_mpm_doctor(mpm_file)

        assert "(none configured)" in result.stdout

    def test_lockfile_present_no_lockfile_catalog_provenance(self, tmp_path: pathlib.Path) -> None:
        """The removed lockfile-catalog provenance suffix never appears with a v4 lock."""
        from mpm_cli.core.mpm_hash import mpm_hash

        mpm_file = _write_minimal_mpm(tmp_path)
        real_hash = mpm_hash(mpm_file)
        self._write_v4_lockfile(tmp_path, real_hash)

        result = _run_mpm_doctor(mpm_file)

        assert "(from .mpm.lock [catalog].source)" not in result.stdout

    def test_env_var_wins_over_present_lockfile(self, tmp_path: pathlib.Path) -> None:
        """MPM_CATALOG_SOURCES supplies the effective source even when a v4 lockfile is present.

        Confirms the lockfile does not pre-empt the env-var tier: with a v4 lock on
        disk and MPM_CATALOG_SOURCES set, the env-var value (and its provenance
        suffix) is what doctor reports.
        """
        from mpm_cli.core.mpm_hash import mpm_hash

        env_value = "https://env.example.com/repo.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)
        real_hash = mpm_hash(mpm_file)
        self._write_v4_lockfile(tmp_path, real_hash)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": env_value},
        )

        assert env_value in result.stdout
        assert "(from MPM_CATALOG_SOURCES env var)" in result.stdout


@pytest.mark.integration
class TestDoctorEffectiveSourceNoneConfigured:
    """mpm doctor reports 'none configured' when no catalog source is available."""

    def test_none_configured_in_stdout(self, tmp_path: pathlib.Path) -> None:
        """Stdout contains 'none configured' indicator when no source is set."""
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(mpm_file)

        assert "(none configured)" in result.stdout

    def test_none_configured_mentions_commands_will_fail(self, tmp_path: pathlib.Path) -> None:
        """Stdout mentions that commands requiring a catalog source will fail."""
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(mpm_file)

        assert "commands requiring" in result.stdout or "will fail" in result.stdout


@pytest.mark.integration
class TestDoctorEffectiveSourceLeakedEnvVar:
    """mpm doctor surfaces MPM_CATALOG_SOURCES leakage from a shell profile.

    This is the primary user-facing purpose of subcheck 6 (spec Section 3.6):
    an operator in a workspace that should NOT use a particular catalog can
    run 'mpm doctor' and see, via the provenance suffix, that their env var
    is leaking into the session.
    """

    def test_leaked_value_appears_in_stdout(self, tmp_path: pathlib.Path) -> None:
        """The leaked MPM_CATALOG_SOURCES value appears in stdout."""
        leaked_value = "https://example.invalid/leaked.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": leaked_value},
        )

        assert leaked_value in result.stdout

    def test_leaked_env_var_provenance_is_surfaced(self, tmp_path: pathlib.Path) -> None:
        """Provenance suffix names the env var so the operator sees the leakage.

        AC-CYCLE-001: Set MPM_CATALOG_SOURCES to a leaked value in the environment;
        run mpm doctor in a workspace that should NOT use that catalog;
        assert stdout's provenance suffix names the env var.
        """
        leaked_value = "https://example.invalid/leaked.git@main"
        mpm_file = _write_minimal_mpm(tmp_path)

        result = _run_mpm_doctor(
            mpm_file,
            extra_env={"MPM_CATALOG_SOURCES": leaked_value},
        )

        assert "(from MPM_CATALOG_SOURCES env var)" in result.stdout
