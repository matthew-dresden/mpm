"""Dynamic completer for source names defined in the .mpm file.

Implements the `mpm __complete_source_names_in_mpm <current-token>` hidden
subcommand (spec Section 11.3 row 2).

Public API::

    complete(current_token: str) -> list[str]

Resolution chain:
1. If MPM_COMPLETION_ENABLED=0, return [] immediately (no cache touch, no file read).
2. Resolve the .mpm file path from ${MPM_MPM_FILE} (default: ./.mpm).
3. Read the file and extract all MPM_SOURCE_<name>_URL keys.
4. Emit each <name> portion sorted alphabetically.
5. Filter by prefix-match against current_token.

Normalization contract (spec Section 11.3 row 2):
The <name> portion of MPM_SOURCE_<name>_URL is the normalized source name.
It is NOT derived at completion time -- it is read directly from the key.
Normalization (derive_source_name) was applied at 'mpm add' time and is
one-way and lossy. The original entry name cannot be recovered.

Failure contract (spec Section 11.3):
- stdout is empty on any error.
- Every error path appends a structured line to completion-errors.log.
- MPM_COMPLETION_ENABLED=0 does NOT touch the cache or log.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from mpm_cli.completions.cache import log_completion_error
from mpm_cli.constants import (
    MPM_COMPLETION_ENABLED,
    MPM_MPM_FILE_DEFAULT,
    MPM_MPM_FILE_ENV,
    SOURCE_PREFIX,
    SOURCE_URL_SUFFIX,
)

_COMPLETER_NAME = "__complete_source_names_in_mpm"


_SOURCE_URL_RE = re.compile(
    r"^" + re.escape(SOURCE_PREFIX) + r"(.+)" + re.escape(SOURCE_URL_SUFFIX) + r"\s*=",
)


def _resolve_mpm_file() -> Path:
    """Return the Path to the active .mpm file.

    Resolution order (highest wins):
    1. ${MPM_MPM_FILE} environment variable.
    2. ./.mpm (MPM_MPM_FILE_DEFAULT).

    Returns:
        Path to the .mpm file (may or may not exist on disk).
    """
    env_val = os.environ.get(MPM_MPM_FILE_ENV)
    if env_val:
        return Path(env_val)
    return Path(MPM_MPM_FILE_DEFAULT)


def _extract_source_names(content: str) -> list[str]:
    """Parse MPM_SOURCE_<name>_URL keys from raw .mpm file text.

    Scans each line for the pattern MPM_SOURCE_<name>_URL=... and
    returns the sorted list of non-empty <name> portions.

    Args:
        content: Raw text content of the .mpm file.

    Returns:
        Sorted list of source names extracted from MPM_SOURCE_<name>_URL keys.
        Returns an empty list when no such keys are found.
    """
    names: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _SOURCE_URL_RE.match(stripped)
        if m:
            name = m.group(1)
            if name:
                names.append(name)
    return sorted(names)


def complete(current_token: str) -> list[str]:
    """Return source names from the .mpm file that start with current_token.

    Resolution contract:
    1. MPM_COMPLETION_ENABLED=0 -> return [].
    2. Read the .mpm file from ${MPM_MPM_FILE} (default: ./.mpm).
    3. Extract MPM_SOURCE_<name>_URL keys; return sorted <name> list.
    4. Filter by prefix (case-sensitive).
    5. On any error: log to completion-errors.log and return [].

    Args:
        current_token: Completion prefix to filter by.

    Returns:
        Sorted list of matching source names, or [] on any error.
    """
    enabled = int(os.environ.get("MPM_COMPLETION_ENABLED", MPM_COMPLETION_ENABLED))
    if enabled == 0:
        return []

    mpm_path = _resolve_mpm_file()

    try:
        content = mpm_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        log_completion_error(_COMPLETER_NAME, exc)
        return []

    names = _extract_source_names(content)
    if not names:
        log_completion_error(
            _COMPLETER_NAME,
            ValueError(f"No MPM_SOURCE_*_URL keys found in {mpm_path}"),
        )
        return []

    return [n for n in names if n.startswith(current_token)]


def register(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> None:
    """Register the hidden ``__complete_source_names_in_mpm`` subcommand.

    The subcommand is hidden from ``mpm --help`` via ``help=argparse.SUPPRESS``.

    Args:
        subparsers: The top-level argparse subparsers action.
    """
    parser: argparse.ArgumentParser = subparsers.add_parser(
        _COMPLETER_NAME,
        help=argparse.SUPPRESS,
        description="Internal hidden subcommand for shell completion of .mpm source names.",
    )
    parser.add_argument(
        "current_token",
        nargs="?",
        default="",
        metavar="<prefix>",
        help="Completion prefix to filter results.",
    )
    parser.set_defaults(func=_handle)


def _handle(args: argparse.Namespace) -> int:
    """Argparse entry point for ``__complete_source_names_in_mpm``.

    Calls ``complete()`` and prints one name per line to stdout.
    Always exits 0 -- the completer is failure-quiet on stdout.

    Args:
        args: Parsed argparse namespace. ``args.current_token`` is the
            completion prefix.

    Returns:
        Always 0.
    """
    names = complete(args.current_token)
    for name in names:
        sys.stdout.write(f"{name}\n")
    return 0
