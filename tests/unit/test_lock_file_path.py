"""Unit tests for derive_lock_file_path -- lock-file path precedence chain.

Tests the six precedence cases from AC-FUNC-001 through AC-FUNC-006:
  (a) CLI wins over env and derivation.
  (b) Env wins over derivation when CLI is absent.
  (c) Derivation applies when CLI and env are both absent.
  (d) Non-default --mpm-file derives sibling lockfile.
  (e) Explicit --lock-file with non-default --mpm-file still wins.
  (f) Empty-string env-var is treated as unset (falls through to derivation).
"""

from pathlib import Path

import pytest

from mpm_cli.utils.lock_file_path import derive_lock_file_path


@pytest.mark.unit
@pytest.mark.parametrize(
    "mpm_file, cli_lock_file, env_lock_file, expected",
    [
        (
            Path("./.mpm"),
            None,
            None,
            Path("./.mpm.lock"),
        ),
        (
            Path("./alt.mpm"),
            None,
            None,
            Path("./alt.mpm.lock"),
        ),
        (
            Path("./.mpm"),
            Path("./explicit.lock"),
            None,
            Path("./explicit.lock"),
        ),
        (
            Path("./.mpm"),
            None,
            "./env.lock",
            Path("./env.lock"),
        ),
        (
            Path("./.mpm"),
            Path("./explicit.lock"),
            "./env.lock",
            Path("./explicit.lock"),
        ),
        (
            Path("./.mpm"),
            None,
            "",
            Path("./.mpm.lock"),
        ),
    ],
)
def test_derive_lock_file_path_precedence(
    mpm_file: Path,
    cli_lock_file: Path | None,
    env_lock_file: str | None,
    expected: Path,
) -> None:
    """derive_lock_file_path respects the three-tier precedence chain for all six cases."""
    result = derive_lock_file_path(mpm_file, cli_lock_file, env_lock_file)
    assert result == expected, (
        f"derive_lock_file_path({mpm_file!r}, {cli_lock_file!r}, {env_lock_file!r}) "
        f"returned {result!r}; expected {expected!r}"
    )


@pytest.mark.unit
def test_derive_lock_file_path_non_default_mpm_file_with_explicit_cli() -> None:
    """AC-FUNC-003 extended: explicit --lock-file with non-default --mpm-file still wins."""
    result = derive_lock_file_path(
        Path("/some/path/myproject.mpm"),
        Path("/other/explicit.lock"),
        None,
    )
    assert result == Path("/other/explicit.lock"), f"CLI path must win over derivation; got {result!r}"


@pytest.mark.unit
def test_derive_lock_file_path_non_default_mpm_file_derives_sibling() -> None:
    """AC-FUNC-002 extended: absolute non-default mpm file derives sibling .lock."""
    result = derive_lock_file_path(
        Path("/workspace/project/.mpm-custom"),
        None,
        None,
    )
    assert result == Path("/workspace/project/.mpm-custom.lock"), (
        f"Sibling derivation must append .lock suffix; got {result!r}"
    )


@pytest.mark.unit
def test_derive_lock_file_path_env_wins_over_derivation_non_default_mpm() -> None:
    """AC-FUNC-004 extended: env wins over derivation with non-default mpm file."""
    result = derive_lock_file_path(
        Path("./alt.mpm"),
        None,
        "/tmp/from-env.lock",
    )
    assert result == Path("/tmp/from-env.lock"), f"Env path must win over derivation; got {result!r}"


@pytest.mark.unit
def test_derive_lock_file_path_whitespace_only_env_is_not_empty() -> None:
    """Whitespace-only env-var is NOT empty -- it is treated as a literal path."""
    result = derive_lock_file_path(Path("./.mpm"), None, "  ")
    assert result == Path("  "), "A whitespace-only env value is a non-empty string; it must be used as-is"
