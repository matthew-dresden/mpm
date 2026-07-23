"""Integration tests for DEFECT-003: placeholder handling in `mpm add` and `mpm install`.

Failing (RED) tests that assert:

1. `mpm add` does NOT write literal `<YOUR_GIT_ORG_BASE_URL>` or `<true|false>`
   placeholders into the generated `.mpm` file; instead it derives GITBASE from
   the catalog-source URL (scheme + authority).

2. `mpm install` FAILS FAST with an "unresolved placeholder" diagnostic (naming
   the offending `.mpm` line number) when the `.mpm` file contains a literal
   `<...>` placeholder value.

Both defects are described in DEFECT-003 (spec/defect-resolution-and-fixture-automation-2026-06/spec.md).

Both tests use the synthetic-fixture helper `_create_manifest_repo_with_tags` from
`tests.integration.test_add_core` and inherit all autouse fixtures defined in
`tests/integration/conftest.py` (URL-scheme policy bypass, ref-resolution mocks,
manifest auto-create). No manual setup of those fixtures is required in the test
bodies.

Spec reference: spec/defect-resolution-and-fixture-automation-2026-06/spec.md
Section 4 E28 (Failing test + Verification + Edge cases), Section 3.1 (synthetic-
fixture helpers), Section 3.2 (autouse fixtures).
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

from tests.integration.test_add_core import (
    _create_manifest_repo_with_tags,
    _run_mpm,
)


@pytest.mark.integration
class TestMPMAddNoPlaceholders:
    """mpm add must derive GITBASE from the catalog URL, not write literal placeholders."""

    def test_add_does_not_write_yourgitorgbaseurl_placeholder(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """mpm add never writes literal `<YOUR_GIT_ORG_BASE_URL>` / `<true|false>`.

        Asserts the DEFECT-003 conditions plus the generalized env-var behavior:

        1. The generated `.mpm` does NOT contain the literal string
           ``<YOUR_GIT_ORG_BASE_URL>``.
        2. The generated `.mpm` does NOT contain the literal string
           ``<true|false>``.
        3. This entry's manifest references no ``${GITBASE}`` placeholder, so add
           writes NO ``MPM_SOURCE_foo_GITBASE=`` line at all (the env-var line is
           emitted only when the manifest needs the var). The four structural keys
           are still written.

        The derived-GITBASE value for a manifest that DOES reference ``${GITBASE}``
        is covered by the dedicated detection test in test_add_env_var_detection.py.
        """
        bare = _create_manifest_repo_with_tags(
            tmp_path / "catalog",
            entry_names=["foo"],
            tags=["1.0.0"],
        )
        catalog_source = f"file://{bare}@main"

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        result = _run_mpm(
            [
                "add",
                "foo",
                "--catalog-source",
                catalog_source,
            ],
            cwd=workspace,
        )
        assert result.returncode == 0, (
            f"mpm add exited {result.returncode} (expected 0).\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        mpm_file = workspace / ".mpm"
        assert mpm_file.exists(), f".mpm file was not created at {mpm_file}."
        content = mpm_file.read_text()

        assert "<YOUR_GIT_ORG_BASE_URL>" not in content, (
            "mpm add wrote the literal placeholder <YOUR_GIT_ORG_BASE_URL> "
            "into .mpm (DEFECT-003).\n"
            f"Actual .mpm content:\n{content}"
        )

        assert "<true|false>" not in content, (
            "mpm add wrote the literal placeholder <true|false> "
            "into .mpm (DEFECT-003). Expected a concrete boolean value instead.\n"
            f"Actual .mpm content:\n{content}"
        )

        assert "MPM_SOURCE_foo_GITBASE=" not in content, (
            "this entry's manifest references no ${GITBASE}, so add must write no "
            f"per-dependency env-var line.\nActual .mpm content:\n{content}"
        )
        assert "MPM_SOURCE_foo_URL=" in content
        assert "MPM_SOURCE_foo_NAME=foo" in content


@pytest.mark.integration
class TestMPMInstallRejectsUnresolvedPlaceholder:
    """mpm install must fail fast when .mpm contains a literal `<...>` placeholder."""

    def test_install_fails_fast_when_mpm_header_contains_placeholder(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """mpm install exits non-zero + emits 'unresolved placeholder' diagnostic.

        Asserts three independent conditions, each of which can fail individually:

        1. `mpm install` exits with a non-zero status code.
        2. stderr contains the substring ``"unresolved placeholder"``.
        3. stderr names the 1-indexed line number of the offending ``GITBASE`` line.

        The `.mpm` is hand-written with:
        - ``GITBASE=<YOUR_GIT_ORG_BASE_URL>`` on line 1 (the offending placeholder)
        - A complete five-key ``MPM_SOURCE_foo_*`` block so the parser succeeds
          and install reaches the placeholder-validator step rather than failing
          on missing source variables.

        Against unfixed code the test fails because `mpm install` passes the
        literal placeholder through to `repo sync` and fails with a 404 or
        git-remote error, not with a structured "unresolved placeholder" diagnostic
        (DEFECT-003).
        """
        bare = _create_manifest_repo_with_tags(
            tmp_path / "catalog",
            entry_names=["foo"],
            tags=["1.0.0"],
        )
        catalog_source = f"file://{bare}@main"

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        mpm_content = textwrap.dedent(f"""\
            GITBASE=<YOUR_GIT_ORG_BASE_URL>
            CLAUDE_MARKETPLACES_DIR=${{HOME}}/.claude-marketplaces
            MPM_MARKETPLACE_INSTALL=false

            MPM_SOURCE_foo_URL={catalog_source}
            MPM_SOURCE_foo_REF=refs/heads/main
            MPM_SOURCE_foo_PATH=repos/foo
            MPM_SOURCE_foo_NAME=foo
            MPM_SOURCE_foo_GITBASE=https://example.com
            """)
        mpm_file = workspace / ".mpm"
        mpm_file.write_text(mpm_content)

        offending_line_number = 1

        env = dict(os.environ)
        env.pop("MPM_CATALOG_SOURCES", None)

        result = subprocess.run(
            [sys.executable, "-m", "mpm_cli", "install"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(workspace),
        )

        assert result.returncode != 0, (
            "mpm install exited 0 when the .mpm file contains the literal "
            "placeholder GITBASE=<YOUR_GIT_ORG_BASE_URL> (DEFECT-003). "
            "Expected a non-zero exit with an 'unresolved placeholder' diagnostic.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        assert "unresolved placeholder" in result.stderr, (
            "mpm install did not emit 'unresolved placeholder' on stderr "
            "when .mpm contains GITBASE=<YOUR_GIT_ORG_BASE_URL> (DEFECT-003).\n"
            f"  exit code: {result.returncode}\n"
            f"  stderr   : {result.stderr!r}"
        )

        assert str(offending_line_number) in result.stderr, (
            f"mpm install stderr does not name the offending line number "
            f"({offending_line_number}) from .mpm (DEFECT-003).\n"
            f"  exit code: {result.returncode}\n"
            f"  stderr   : {result.stderr!r}"
        )
