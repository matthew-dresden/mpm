"""Integration test: 'mpm why' closest-match suggestion on not-found.

Builds a real fixture:
  - A .mpm file referencing a top-level source named 'foo'.
  - A .mpm.lock file pinning source 'foo' -> include 'repo-specs/bar/bar.xml'
    -> project 'https://github.com/org/baz.git'.

Invokes 'mpm why <typo>' via subprocess and asserts:
  - When the argument is a one-char typo ('fooo') that falls within edit distance 3:
    - Exit code is non-zero (not found).
    - stderr contains both the not-found error and 'foo' in the suggestion list.
  - When the argument is 'xyzzy' (no close matches within distance 3):
    - Exit code is non-zero.
    - stderr contains the not-found error and "No close matches found."

AC-TEST-003, AC-CYCLE-001
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from mpm_cli.core.lockfile import (
    CURRENT_SCHEMA_VERSION,
    IncludeEntry,
    Lockfile,
    ProjectEntry,
    SourceEntry,
    write_lockfile,
)
from mpm_cli.core.url import canonicalize_repo_url


_SOURCE_NAME = "foo"
_PROJECT_NAME = "baz"
_PROJECT_URL = "https://github.com/org/baz.git"
_INCLUDE_NAME = "bar"
_INCLUDE_PATH = "repo-specs/bar/bar.xml"


_SOURCE_SHA = "a" * 40
_INCLUDE_SHA = "c" * 40
_PROJECT_SHA = "b" * 40
_MPM_HASH = "sha256:" + "a" * 64


@pytest.fixture(autouse=True)
def _mock_resolve_ref_to_sha():
    """Override: this test does not install anything -- no git calls needed."""
    yield


@pytest.fixture(autouse=True)
def _mock_check_sha_reachable():
    """Override: this test does not install anything -- no git calls needed."""
    yield


@pytest.fixture()
def why_suggestion_fixture(tmp_path: pathlib.Path):
    """Create a .mpm file and a .mpm.lock for suggestion tests.

    Tree structure:
      foo (source) -> repo-specs/bar/bar.xml (include) -> https://github.com/org/baz.git (project)
    """

    mpm_file = tmp_path / ".mpm"
    mpm_file.write_text(
        f"MPM_SOURCE_{_SOURCE_NAME}_URL=https://github.com/org/catalog\n"
        f"MPM_SOURCE_{_SOURCE_NAME}_REF=main\n"
        f"MPM_SOURCE_{_SOURCE_NAME}_PATH=./foo\n"
        f"MPM_SOURCE_{_SOURCE_NAME}_NAME={_SOURCE_NAME}\n"
        f"MPM_SOURCE_{_SOURCE_NAME}_GITBASE=https://example.com\n"
    )
    mpm_file.chmod(0o644)

    canonical_project_url = canonicalize_repo_url(_PROJECT_URL)
    lockfile = Lockfile(
        schema_version=CURRENT_SCHEMA_VERSION,
        generated_at="2024-01-01T00:00:00Z",
        generator="mpm-test",
        mpm_hash=_MPM_HASH,
        sources=[
            SourceEntry(
                alias=_SOURCE_NAME,
                name=_SOURCE_NAME,
                url="https://github.com/org/catalog",
                ref_spec="main",
                resolved_ref="main",
                resolved_sha=_SOURCE_SHA,
                path="./foo",
                includes=[
                    IncludeEntry(
                        name=_INCLUDE_NAME,
                        path_in_repo=_INCLUDE_PATH,
                        url="https://github.com/org/catalog",
                        resolved_sha=_INCLUDE_SHA,
                        includes=[],
                    )
                ],
                projects=[
                    ProjectEntry(
                        name=_PROJECT_NAME,
                        url=_PROJECT_URL,
                        canonical_url=canonical_project_url,
                        ref_spec="main",
                        resolved_ref="main",
                        resolved_sha=_PROJECT_SHA,
                    )
                ],
            )
        ],
    )
    lock_path = tmp_path / ".mpm.lock"
    write_lockfile(lockfile, lock_path)

    return tmp_path, mpm_file, lock_path


def _invoke_why(
    tmp_path: pathlib.Path,
    mpm_file: pathlib.Path,
    lock_file: pathlib.Path,
    argument: str,
) -> subprocess.CompletedProcess[str]:
    """Invoke 'mpm why <argument>' via subprocess and return the result."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mpm_cli",
            "why",
            argument,
            "--mpm-file",
            str(mpm_file),
            "--lock-file",
            str(lock_file),
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )


@pytest.mark.integration
class TestWhyNotFoundWithSuggestion:
    """Integration tests for closest-match suggestion on not-found."""

    def test_typo_in_source_name_includes_suggestion(
        self, why_suggestion_fixture: tuple[pathlib.Path, pathlib.Path, pathlib.Path]
    ) -> None:
        """'mpm why fooo' (one-char typo on source 'foo') includes 'foo' in suggestions."""
        tmp_path, mpm_file, lock_file = why_suggestion_fixture
        result = _invoke_why(tmp_path, mpm_file, lock_file, "fooo")

        assert result.returncode != 0, "Expected non-zero exit for not-found"
        assert "not found" in result.stderr.lower(), f"Expected 'not found' in stderr; got:\n{result.stderr}"
        assert "foo" in result.stderr, f"Expected source name 'foo' in suggestion list; stderr:\n{result.stderr}"

        assert "No close matches" not in result.stderr, (
            f"Expected suggestion list, not 'No close matches'; stderr:\n{result.stderr}"
        )

    def test_no_close_match_reports_no_suggestions(
        self, why_suggestion_fixture: tuple[pathlib.Path, pathlib.Path, pathlib.Path]
    ) -> None:
        """'mpm why xyzzy' (no close matches) reports 'No close matches found.'."""
        tmp_path, mpm_file, lock_file = why_suggestion_fixture
        result = _invoke_why(tmp_path, mpm_file, lock_file, "xyzzy")

        assert result.returncode != 0, "Expected non-zero exit for not-found"
        assert "not found" in result.stderr.lower(), f"Expected 'not found' in stderr; got:\n{result.stderr}"
        assert "No close matches found." in result.stderr, (
            f"Expected 'No close matches found.' in stderr; got:\n{result.stderr}"
        )

    def test_not_found_stderr_not_stdout(
        self, why_suggestion_fixture: tuple[pathlib.Path, pathlib.Path, pathlib.Path]
    ) -> None:
        """Error output goes to stderr, not stdout."""
        tmp_path, mpm_file, lock_file = why_suggestion_fixture
        result = _invoke_why(tmp_path, mpm_file, lock_file, "fooo")

        assert result.returncode != 0
        assert result.stdout == "", f"Expected empty stdout for not-found; got:\n{result.stdout}"
        assert "ERROR:" in result.stderr

    def test_successful_match_unaffected_by_suggester(
        self, why_suggestion_fixture: tuple[pathlib.Path, pathlib.Path, pathlib.Path]
    ) -> None:
        """Successful match ('foo') works normally; suggester is not invoked."""
        tmp_path, mpm_file, lock_file = why_suggestion_fixture
        result = _invoke_why(tmp_path, mpm_file, lock_file, "foo")

        assert result.returncode == 0, f"Expected exit 0 for exact source match; stderr:\n{result.stderr}"

        assert "foo" in result.stdout
        assert "not found" not in result.stderr.lower()

    def test_typo_in_xml_path_includes_suggestion(
        self, why_suggestion_fixture: tuple[pathlib.Path, pathlib.Path, pathlib.Path]
    ) -> None:
        """'mpm why repo-specs/bar/barr.xml' (one-char typo on XML path) includes XML path."""
        tmp_path, mpm_file, lock_file = why_suggestion_fixture

        result = _invoke_why(tmp_path, mpm_file, lock_file, "repo-specs/bar/barr.xml")

        assert result.returncode != 0
        assert _INCLUDE_PATH in result.stderr, (
            f"Expected include path '{_INCLUDE_PATH}' in suggestions; stderr:\n{result.stderr}"
        )

    def test_typo_in_include_name_includes_suggestion(
        self, why_suggestion_fixture: tuple[pathlib.Path, pathlib.Path, pathlib.Path]
    ) -> None:
        """'mpm why bart' (one-char typo on the include name 'bar') suggests the include name."""
        tmp_path, mpm_file, lock_file = why_suggestion_fixture

        result = _invoke_why(tmp_path, mpm_file, lock_file, "bart")

        assert result.returncode != 0
        assert "Did you mean" in result.stderr, f"Expected suggestions; stderr:\n{result.stderr}"
        suggestions = result.stderr.split("Did you mean", 1)[1]
        assert _INCLUDE_NAME in suggestions, (
            f"Expected include name '{_INCLUDE_NAME}' in suggestions; stderr:\n{result.stderr}"
        )
