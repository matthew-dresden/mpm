"""Integration test: the ``.mpm`` writers reject a ``.mpm`` DIRECTORY cleanly.

When a directory named ``.mpm`` occupies the path where ``mpm add`` /
``mpm remove`` / ``mpm marketplace enable|disable`` must read or write the
``.mpm`` config FILE, the bare ``IsADirectoryError`` is cryptic. The guard
``guard_mpm_file_not_dir`` detects the collision up front and prints the exact
``rm -rf <path>`` command plus a retry instruction, exiting non-zero.

This reproduces the original bug end-to-end: running mpm from a directory that
already holds a ``.mpm`` folder -- the most common cause being an orphaned
pre-rename ``~/.mpm`` home store (the default store moved to ``~/.mpm-home``).
"""

from __future__ import annotations

import pathlib

import pytest

from tests.integration.test_add_core import _run_mpm


@pytest.mark.integration
@pytest.mark.parametrize(
    "cli_args",
    [
        ["add", "history", "--catalog-source", "https://example.invalid/repo.git@main"],
        ["remove", "history"],
        ["marketplace", "enable", "history"],
        ["marketplace", "disable", "history"],
    ],
    ids=["add", "remove", "marketplace-enable", "marketplace-disable"],
)
def test_writers_reject_mpm_directory_with_clean_error(tmp_path: pathlib.Path, cli_args: list[str]) -> None:
    """Each .mpm writer emits the clean folder-collision error (not IsADirectoryError), exit 1.

    The guard runs before any catalog resolution or network access, so the bogus
    ``--catalog-source`` for the add case is never contacted.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mpm_dir = workspace / ".mpm"
    mpm_dir.mkdir()

    result = _run_mpm(cli_args, cwd=workspace)

    assert result.returncode == 1, f"{cli_args}: expected exit 1.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    assert "found a .mpm folder" in result.stderr, result.stderr
    assert f"rm -rf {mpm_dir.resolve()}" in result.stderr, result.stderr
    assert "re-run your mpm command" in result.stderr, result.stderr
    assert "Is a directory" not in result.stderr, result.stderr
