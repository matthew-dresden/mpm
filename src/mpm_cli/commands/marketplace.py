"""mpm marketplace subcommand: per-dependency marketplace install management.

Provides the ``mpm marketplace`` subcommand group with three operations
(spec ``specs/mpm-refinements.md`` Section 4.4 / FR-18):

- ``mpm marketplace enable <alias>`` -- write
  ``MPM_SOURCE_<alias>_MARKETPLACE=true`` into ``.mpm``.
- ``mpm marketplace disable <alias>`` -- remove the
  ``MPM_SOURCE_<alias>_MARKETPLACE`` line (absence is the canonical false;
  mpm never writes ``=false`` itself).
- ``mpm marketplace status [--all]`` -- print each dependency, its
  ``<catalog-metadata><type>``, and the effective marketplace setting, rendering
  an explicit ``=false`` and an absent line identically (both "disabled").

The command edits **only** ``.mpm``; it touches **no** ``.mpm.lock`` entry,
performs no version re-resolution, and has no ``--force`` flag, so install-time
determinism is unaffected (spec Section 4.4 / FR-17, FR-18).

Marketplace-type determination is offline (the command never clones the catalog
or hits the network): a dependency is treated as a Claude marketplace type when
its ``MPM_SOURCE_<alias>_MARKETPLACE`` line is present in ``.mpm`` in any
form (``=true`` or a hand-written ``=false``). ``mpm add`` writes that line
for a ``claude-marketplace`` catalog entry, so the line's presence is the
persistent on-disk type marker. ``enable`` on an alias that carries no such line
is therefore an enable on a non-marketplace type and fails with a pretty error;
``enable`` on an unknown alias fails with a clear error.

Spec reference: ``specs/mpm-refinements.md`` Section 4.4 (semantics, edge
cases, errors), Section 10.4 J5 (enable/disable/status journey; touches no
lock), Section 14 (``mpm marketplace --help`` advertises ``enable <alias>`` |
``disable <alias>`` | ``status [--all]``), FR-17, FR-18.
"""

import argparse
import os
import pathlib
import sys

from mpm_cli.constants import (
    CATALOG_TYPE_CLAUDE_MARKETPLACE,
    MPM_MPM_FILE_DEFAULT,
    MPM_MPM_FILE_ENV,
    MARKETPLACE_FLAG_TRUE,
    SOURCE_MARKETPLACE_SUFFIX,
    SOURCE_PREFIX,
    SOURCE_URL_SUFFIX,
)
from mpm_cli.core.install import resolve_mpm_lock_root
from mpm_cli.core.mpmenv_writer import (
    ensure_claude_marketplaces_dir,
    guard_mpm_file_not_dir,
    prune_claude_marketplaces_dir_if_unused,
)
from mpm_cli.core.metadata import derive_source_name
from mpm_cli.utils.concurrency import mpm_workspace_lock


_STATUS_ENABLED = "enabled"
_STATUS_DISABLED = "disabled"


_TYPE_UNKNOWN = "--"


_STATUS_HEADER_ALIAS = "ALIAS"
_STATUS_HEADER_TYPE = "TYPE"
_STATUS_HEADER_SETTING = "SETTING"


_STATUS_COLUMN_GAP = 2


class MarketplaceAliasError(ValueError):
    """Raised when ``enable``/``disable`` targets an alias absent from ``.mpm``.

    Spec reference: ``specs/mpm-refinements.md`` Section 4.4 ("Unknown alias ->
    clear error") + CLAUDE.md Error Handling Contract.

    Args:
        alias: The normalised alias the operator requested.
        mpm_file: The ``.mpm`` path that was searched.
    """

    def __init__(self, alias: str, mpm_file: pathlib.Path) -> None:
        self.alias = alias
        self.mpm_file = mpm_file
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"ERROR: unknown source alias {self.alias!r}: no "
            f"{SOURCE_PREFIX}{self.alias}{SOURCE_URL_SUFFIX} line in {self.mpm_file}.\n"
            "Run 'mpm marketplace status --all' to list the known aliases, or "
            "'mpm add <entry>' to add the dependency first."
        )


class NonMarketplaceTypeError(ValueError):
    """Raised when ``enable`` targets a known alias that is not a marketplace type.

    A dependency is a marketplace type (offline) when its
    ``MPM_SOURCE_<alias>_MARKETPLACE`` line is present in ``.mpm`` in any form
    (``mpm add`` writes it for a ``claude-marketplace`` catalog entry). Enabling
    an alias that carries no such line is an enable on a non-marketplace type.

    Spec reference: ``specs/mpm-refinements.md`` Section 4.4 ("``enable`` on a
    non-marketplace type -> pretty error") + CLAUDE.md Error Handling Contract.

    Args:
        alias: The normalised alias the operator requested.
        mpm_file: The ``.mpm`` path that was searched.
    """

    def __init__(self, alias: str, mpm_file: pathlib.Path) -> None:
        self.alias = alias
        self.mpm_file = mpm_file
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"ERROR: source alias {self.alias!r} is not a "
            f"'{CATALOG_TYPE_CLAUDE_MARKETPLACE}' type, so marketplace install "
            "cannot be enabled for it.\n"
            f"Only a dependency added from a '{CATALOG_TYPE_CLAUDE_MARKETPLACE}' "
            f"catalog entry carries a {SOURCE_PREFIX}{self.alias}"
            f"{SOURCE_MARKETPLACE_SUFFIX} line in {self.mpm_file}.\n"
            "Re-add it with 'mpm add <entry> --marketplace-install' if it really "
            "is a marketplace entry."
        )


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Register the 'marketplace' subcommand group on the top-level subparsers.

    Creates the ``marketplace`` subparser and registers the ``enable``,
    ``disable``, and ``status`` operations (spec Section 4.4 / FR-18). Mirrors the
    ``register(subparsers)`` contract every other command module exposes (e.g.
    ``commands/install.py``), so ``cli.py`` wires it with a single
    ``register_marketplace(subparsers)`` call.

    Args:
        subparsers: The subparsers action from the top-level parser.
    """
    marketplace_parser: argparse.ArgumentParser = subparsers.add_parser(
        "marketplace",
        add_help=True,
        help="Manage per-dependency marketplace install (enable|disable|status).",
        description=(
            "Manage the per-dependency Claude marketplace install flag in .mpm.\n\n"
            "This command edits only .mpm: it never touches .mpm.lock, performs\n"
            "no version re-resolution, and has no --force flag, so install-time\n"
            "determinism is unaffected.\n\n"
            "Subcommands:\n"
            "  enable <alias>    Write MPM_SOURCE_<alias>_MARKETPLACE=true.\n"
            "  disable <alias>   Remove the MPM_SOURCE_<alias>_MARKETPLACE line\n"
            "                    (absence is the canonical false; mpm never\n"
            "                    writes =false itself).\n"
            "  status [--all]    Show each dependency, its catalog <type>, and the\n"
            "                    effective marketplace setting. An explicit =false\n"
            "                    and an absent line render identically (disabled)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    marketplace_subparsers = marketplace_parser.add_subparsers(
        dest="marketplace_command",
        title="marketplace subcommands",
        description="Available marketplace operations",
    )

    _register_enable(marketplace_subparsers)
    _register_disable(marketplace_subparsers)
    _register_status(marketplace_subparsers)

    def _marketplace_help(args: argparse.Namespace) -> int:
        """Print the marketplace help and exit non-zero when no operation is given."""
        marketplace_parser.print_help()
        return 2

    marketplace_parser.set_defaults(func=_marketplace_help)


def _add_mpm_file_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--mpm-file`` argument to an operation subparser.

    Extracted so ``enable`` / ``disable`` / ``status`` declare the identical
    ``.mpm`` path option without duplicating the help text (DRY).

    Args:
        parser: The operation subparser to extend.
    """
    parser.add_argument(
        "--mpm-file",
        dest="mpm_file",
        default=os.environ.get(MPM_MPM_FILE_ENV, MPM_MPM_FILE_DEFAULT),
        metavar="<path>",
        help=(
            f"Path to the .mpm file to read/modify. "
            f"Defaults to '{MPM_MPM_FILE_DEFAULT}'. "
            f"Overridden by the {MPM_MPM_FILE_ENV} environment variable; "
            "the CLI flag takes precedence when both are set."
        ),
    )


def _register_enable(
    marketplace_subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> None:
    """Register the ``enable`` operation on the marketplace subparsers.

    Args:
        marketplace_subparsers: The subparsers action from the marketplace parser.
    """
    enable_parser: argparse.ArgumentParser = marketplace_subparsers.add_parser(
        "enable",
        add_help=True,
        help="Enable marketplace install for a dependency (writes =true).",
        description=(
            "Write MPM_SOURCE_<alias>_MARKETPLACE=true into .mpm for the\n"
            "named dependency. The alias must already exist in .mpm and must be a\n"
            "marketplace type (it must already carry a MPM_SOURCE_<alias>_MARKETPLACE\n"
            "line, written by 'mpm add' for a claude-marketplace catalog entry)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    enable_parser.add_argument(
        "alias",
        metavar="<alias>",
        help="The source alias to enable (canonical alias or original entry name).",
    )
    _add_mpm_file_argument(enable_parser)
    enable_parser.set_defaults(func=run_enable)


def _register_disable(
    marketplace_subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> None:
    """Register the ``disable`` operation on the marketplace subparsers.

    Args:
        marketplace_subparsers: The subparsers action from the marketplace parser.
    """
    disable_parser: argparse.ArgumentParser = marketplace_subparsers.add_parser(
        "disable",
        add_help=True,
        help="Disable marketplace install for a dependency (removes the line).",
        description=(
            "Remove the MPM_SOURCE_<alias>_MARKETPLACE line from .mpm for the\n"
            "named dependency. Absence is the canonical false; mpm never writes\n"
            "=false itself. The alias must already exist in .mpm. Disabling an\n"
            "already-disabled dependency is a no-op (exit 0)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    disable_parser.add_argument(
        "alias",
        metavar="<alias>",
        help="The source alias to disable (canonical alias or original entry name).",
    )
    _add_mpm_file_argument(disable_parser)
    disable_parser.set_defaults(func=run_disable)


def _register_status(
    marketplace_subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> None:
    """Register the ``status`` operation on the marketplace subparsers.

    Args:
        marketplace_subparsers: The subparsers action from the marketplace parser.
    """
    status_parser: argparse.ArgumentParser = marketplace_subparsers.add_parser(
        "status",
        add_help=True,
        help="Show each dependency's marketplace type and effective setting.",
        description=(
            "Print a table of every dependency in .mpm, its catalog <type>, and\n"
            "the effective marketplace setting. An explicit =false and an absent\n"
            "line render identically (both 'disabled'). With no dependencies the\n"
            "table is empty and the command exits 0."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_parser.add_argument(
        "--all",
        dest="show_all",
        action="store_true",
        default=False,
        help=(
            "Show every dependency, including those that are not a marketplace\n"
            "type. Without --all, only marketplace-typed dependencies are listed."
        ),
    )
    _add_mpm_file_argument(status_parser)
    status_parser.set_defaults(func=run_status)


def _read_lines(mpm_file: pathlib.Path) -> list[str]:
    """Read the ``.mpm`` file into a list of lines (newlines retained).

    Args:
        mpm_file: Path to the ``.mpm`` file.

    Returns:
        The file's lines with their trailing newline characters retained.

    Raises:
        FileNotFoundError: When ``mpm_file`` does not exist. The caller surfaces
            this as a clear stderr error and a non-zero exit (fail fast).
    """
    if not mpm_file.exists():
        raise FileNotFoundError(f"ERROR: no .mpm file at {mpm_file}; nothing to manage")
    return mpm_file.read_text(encoding="utf-8").splitlines(keepends=True)


def _key_of(raw_line: str) -> str | None:
    """Return the KEY token of a ``KEY=VALUE`` line, or None for a non-assignment.

    Comment lines (stripped content starting with ``#``) and lines without an
    ``=`` are not assignments and return ``None`` so they are never mistaken for a
    source key.

    Args:
        raw_line: A single line from ``.mpm`` (newline may be retained).

    Returns:
        The stripped KEY token, or ``None`` when the line is a comment, blank, or
        carries no ``=``.
    """
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def _value_of(raw_line: str) -> str:
    """Return the VALUE token (right of the first ``=``) of an assignment line.

    Args:
        raw_line: A single ``KEY=VALUE`` line from ``.mpm`` (newline may be
            retained).

    Returns:
        The stripped VALUE token.
    """
    return raw_line.strip().split("=", 1)[1].strip()


def _discover_aliases(lines: list[str]) -> list[str]:
    """Return the aliases present in ``.mpm``, ordered by first ``_URL`` line.

    An alias is discovered from its ``MPM_SOURCE_<alias>_URL`` line (the same
    discovery key the parser uses). First-seen line order is preserved so the
    status table is stable and reproducible.

    Args:
        lines: All lines of the ``.mpm`` file.

    Returns:
        The list of discovered aliases in first-seen order.
    """
    url_suffix = SOURCE_URL_SUFFIX
    aliases: list[str] = []
    seen: set[str] = set()
    for raw_line in lines:
        key = _key_of(raw_line)
        if key is None:
            continue
        if key.startswith(SOURCE_PREFIX) and key.endswith(url_suffix):
            alias = key[len(SOURCE_PREFIX) : -len(url_suffix)]
            if alias and alias not in seen:
                seen.add(alias)
                aliases.append(alias)
    return aliases


def _marketplace_line_index(lines: list[str], alias: str) -> int | None:
    """Return the index of the ``_MARKETPLACE`` line for ``alias``, or None.

    Args:
        lines: All lines of the ``.mpm`` file.
        alias: The normalised source alias.

    Returns:
        The zero-based index of the alias's ``MPM_SOURCE_<alias>_MARKETPLACE``
        line, or ``None`` when the dependency carries no such line.
    """
    target_key = f"{SOURCE_PREFIX}{alias}{SOURCE_MARKETPLACE_SUFFIX}"
    for idx, raw_line in enumerate(lines):
        if _key_of(raw_line) == target_key:
            return idx
    return None


def _normalise_alias(raw_alias: str) -> str:
    """Normalise an operator-supplied alias to the canonical source-name token.

    Accepts either the canonical alias (``foo_bar``) or the original entry name
    (``Foo-Bar``); both normalise to the same ``MPM_SOURCE_<alias>_*`` token via
    :func:`derive_source_name`, matching ``mpm remove`` (spec Section 4.3).

    Args:
        raw_alias: The operator-supplied alias or entry name.

    Returns:
        The canonical alias token.
    """
    return derive_source_name(raw_alias)


def _detect_newline(lines: list[str]) -> str:
    """Return the newline string to use when appending a new line to ``.mpm``.

    Mirrors the dominant ending of the last content line so an appended
    ``_MARKETPLACE`` line matches the file's existing convention. Defaults to
    ``\\n`` for an empty file or a final line that carries no newline.

    Args:
        lines: All lines of the ``.mpm`` file.

    Returns:
        ``"\\r\\n"`` when the last newline-terminated line is CRLF, else ``"\\n"``.
    """
    for raw_line in reversed(lines):
        if raw_line.endswith("\r\n"):
            return "\r\n"
        if raw_line.endswith("\n"):
            return "\n"
    return "\n"


def _require_known_alias(lines: list[str], alias: str, mpm_file: pathlib.Path) -> None:
    """Fail fast when ``alias`` has no source block in ``.mpm``.

    Args:
        lines: All lines of the ``.mpm`` file.
        alias: The normalised source alias.
        mpm_file: The ``.mpm`` path (for the error message).

    Raises:
        MarketplaceAliasError: When the alias is absent from ``.mpm``.
    """
    if alias not in _discover_aliases(lines):
        raise MarketplaceAliasError(alias=alias, mpm_file=mpm_file)


def _write_lines(mpm_file: pathlib.Path, lines: list[str]) -> None:
    """Write ``lines`` back to ``.mpm`` verbatim under the workspace lock.

    The exclusive workspace lock is taken before the write so a concurrent
    ``mpm install`` / ``mpm add`` cannot observe a half-written ``.mpm``.

    Args:
        mpm_file: Path to the ``.mpm`` file.
        lines: The full file content as a list of lines (newlines retained).
    """
    with mpm_workspace_lock(resolve_mpm_lock_root(mpm_file)):
        mpm_file.write_text("".join(lines), encoding="utf-8")


def run_enable(args: argparse.Namespace) -> int:
    """Entry point for ``mpm marketplace enable <alias>``.

    Writes ``MPM_SOURCE_<alias>_MARKETPLACE=true`` into ``.mpm``. The alias
    must already exist and must be a marketplace type (it must already carry a
    ``_MARKETPLACE`` line). Editing is confined to ``.mpm``; ``.mpm.lock`` is
    never read or written.

    Args:
        args: Parsed argument namespace with ``alias`` and ``mpm_file``.

    Returns:
        0 on success; exits non-zero on any validation failure.
    """
    mpm_file = pathlib.Path(args.mpm_file)
    guard_mpm_file_not_dir(mpm_file)
    alias = _normalise_alias(args.alias)

    try:
        lines = _read_lines(mpm_file)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    try:
        _require_known_alias(lines, alias, mpm_file)
    except MarketplaceAliasError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    idx = _marketplace_line_index(lines, alias)
    if idx is None:
        print(str(NonMarketplaceTypeError(alias=alias, mpm_file=mpm_file)), file=sys.stderr)
        sys.exit(1)

    enabled_line = f"{SOURCE_PREFIX}{alias}{SOURCE_MARKETPLACE_SUFFIX}={MARKETPLACE_FLAG_TRUE}"
    newline = _detect_newline(lines)
    existing_newline = "\r\n" if lines[idx].endswith("\r\n") else ("\n" if lines[idx].endswith("\n") else newline)
    lines[idx] = enabled_line + existing_newline

    _write_lines(mpm_file, lines)
    ensure_claude_marketplaces_dir(mpm_file)
    print(f"Enabled marketplace install for '{alias}' in {mpm_file}")
    return 0


def run_disable(args: argparse.Namespace) -> int:
    """Entry point for ``mpm marketplace disable <alias>``.

    Removes the ``MPM_SOURCE_<alias>_MARKETPLACE`` line from ``.mpm``; absence
    is the canonical false (mpm never writes ``=false``). The alias must already
    exist. Disabling an already-disabled dependency is a no-op that still exits 0.
    Editing is confined to ``.mpm``; ``.mpm.lock`` is never read or written.

    Args:
        args: Parsed argument namespace with ``alias`` and ``mpm_file``.

    Returns:
        0 on success; exits non-zero on any validation failure.
    """
    mpm_file = pathlib.Path(args.mpm_file)
    guard_mpm_file_not_dir(mpm_file)
    alias = _normalise_alias(args.alias)

    try:
        lines = _read_lines(mpm_file)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    try:
        _require_known_alias(lines, alias, mpm_file)
    except MarketplaceAliasError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    idx = _marketplace_line_index(lines, alias)
    if idx is None:
        print(f"Marketplace install already disabled for '{alias}' in {mpm_file}")
        return 0

    del lines[idx]
    _write_lines(mpm_file, lines)
    prune_claude_marketplaces_dir_if_unused(mpm_file)
    print(f"Disabled marketplace install for '{alias}' in {mpm_file}")
    return 0


def _effective_setting(lines: list[str], alias: str) -> str:
    """Return the effective marketplace setting token for ``alias``.

    The setting is ``enabled`` only when the alias's ``_MARKETPLACE`` line is
    present and its value parses true; an absent line and a hand-written
    ``=false`` both render ``disabled`` (spec Section 4.4: explicit ``=false`` and
    absent are identical).

    Args:
        lines: All lines of the ``.mpm`` file.
        alias: The normalised source alias.

    Returns:
        ``_STATUS_ENABLED`` or ``_STATUS_DISABLED``.
    """
    idx = _marketplace_line_index(lines, alias)
    if idx is None:
        return _STATUS_DISABLED
    if _value_of(lines[idx]).lower() == MARKETPLACE_FLAG_TRUE:
        return _STATUS_ENABLED
    return _STATUS_DISABLED


def _displayed_type(lines: list[str], alias: str) -> str:
    """Return the ``<type>`` token rendered for ``alias`` in the status table.

    The command is offline (no catalog clone, no network), so the only type signal
    available is the ``_MARKETPLACE`` line: its presence in any form marks the
    dependency as a ``claude-marketplace`` type; its absence renders the neutral
    ``_TYPE_UNKNOWN`` placeholder.

    Args:
        lines: All lines of the ``.mpm`` file.
        alias: The normalised source alias.

    Returns:
        ``CATALOG_TYPE_CLAUDE_MARKETPLACE`` when the alias carries a
        ``_MARKETPLACE`` line, else ``_TYPE_UNKNOWN``.
    """
    if _marketplace_line_index(lines, alias) is None:
        return _TYPE_UNKNOWN
    return CATALOG_TYPE_CLAUDE_MARKETPLACE


def _is_marketplace_type(lines: list[str], alias: str) -> bool:
    """Return True when ``alias`` carries a ``_MARKETPLACE`` line in ``.mpm``.

    Args:
        lines: All lines of the ``.mpm`` file.
        alias: The normalised source alias.

    Returns:
        True iff the dependency is a marketplace type (carries the line).
    """
    return _marketplace_line_index(lines, alias) is not None


def _format_status_table(rows: list[tuple[str, str, str]]) -> list[str]:
    """Format the status rows into aligned table lines (header + one line per dep).

    Column widths size to the widest cell (header or value) so the columns align.
    With no rows, only the header line is produced (an empty table).

    Args:
        rows: One ``(alias, type, setting)`` triple per dependency.

    Returns:
        The rendered table lines (no trailing newlines), header first.
    """
    header = (_STATUS_HEADER_ALIAS, _STATUS_HEADER_TYPE, _STATUS_HEADER_SETTING)
    all_rows = [header, *rows]
    alias_width = max(len(row[0]) for row in all_rows)
    type_width = max(len(row[1]) for row in all_rows)
    gap = " " * _STATUS_COLUMN_GAP

    rendered: list[str] = []
    for alias, type_token, setting in all_rows:
        rendered.append(f"{alias.ljust(alias_width)}{gap}{type_token.ljust(type_width)}{gap}{setting}")
    return rendered


def run_status(args: argparse.Namespace) -> int:
    """Entry point for ``mpm marketplace status [--all]``.

    Prints a table of each dependency, its catalog ``<type>``, and the effective
    marketplace setting. Without ``--all`` only marketplace-typed dependencies are
    listed; with ``--all`` every dependency is listed. With no dependencies the
    table is empty (header only) and the command exits 0. Reads only ``.mpm``;
    ``.mpm.lock`` is never read.

    Args:
        args: Parsed argument namespace with ``show_all`` and ``mpm_file``.

    Returns:
        0 on success; exits non-zero only when ``.mpm`` is missing.
    """
    mpm_file = pathlib.Path(args.mpm_file)
    show_all: bool = getattr(args, "show_all", False)

    try:
        lines = _read_lines(mpm_file)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    rows: list[tuple[str, str, str]] = []
    for alias in _discover_aliases(lines):
        if not show_all and not _is_marketplace_type(lines, alias):
            continue
        rows.append((alias, _displayed_type(lines, alias), _effective_setting(lines, alias)))

    for table_line in _format_status_table(rows):
        print(table_line)
    return 0
