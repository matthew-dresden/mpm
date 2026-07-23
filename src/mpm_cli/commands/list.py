"""mpm list subcommand: inventory of declared vs installed sources.

Reconciles the sources declared in ``.mpm`` against the sources recorded in
``.mpm.lock`` and prints one row per source with a status tag:

  - ``installed``     -- the alias is present in BOTH ``.mpm`` and ``.mpm.lock``.
  - ``not-installed`` -- the alias is declared in ``.mpm`` but absent from the
    lock (declared, not yet installed -- run ``mpm install``).
  - ``orphan``        -- the alias is present in ``.mpm.lock`` but no longer
    declared in ``.mpm`` (installed, undeclared).

This is the flat inventory verb (like ``pip list`` / ``npm ls`` / ``poetry
show``); it complements ``mpm why`` (the dependency graph), ``mpm outdated``
(version staleness), and ``mpm validate lockfile`` (which fails on the same
declared-vs-installed drift this command merely reports).

The declared/installed partition reuses
``core.lockfile.reconcile_declared_installed`` -- the non-raising core of the
``check_lockfile_consistency`` check that ``mpm install`` and
``mpm validate lockfile`` enforce.
"""

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass, field

from mpm_cli.constants import (
    BRANCH_SHA_TRUNCATION_LENGTH,
    MPM_MPM_FILE_ENV,
    MPM_LIST_COLUMN_REF,
    MPM_LIST_COLUMN_SOURCE,
    MPM_LIST_COLUMN_STATUS,
    MPM_LIST_JSON_INDENT,
    MPM_LIST_NO_LOCKFILE_NOTE,
    MPM_LIST_NO_SOURCES_NOTE,
    MPM_LIST_OUTPUT_FORMAT,
    MPM_LIST_OUTPUT_FORMAT_CHOICES,
    MPM_LIST_OUTPUT_FORMAT_DEFAULT,
    MPM_LIST_OUTPUT_FORMAT_JSON,
    MPM_LIST_OUTPUT_FORMAT_TABLE,
    MPM_LIST_REF_UNRESOLVED,
    MPM_LIST_SCOPE_DIRECT,
    MPM_LIST_SCOPE_TRANSITIVE,
    MPM_LIST_STATUS_CHOICES,
    MPM_LIST_STATUS_INSTALLED,
    MPM_LIST_STATUS_NOT_INSTALLED,
    MPM_LIST_STATUS_ORPHAN,
    MPM_LIST_TREE_INDENT,
    MPM_LOCK_FILE,
    REVISION_REF_PREFIXES,
)
from mpm_cli.core.discover import find_mpmenv
from mpm_cli.core.mpmenv import NoSourcesError, parse_mpmenv
from mpm_cli.core.lockfile import (
    LockfileSchemaError,
    LockfileValidationError,
    SourceEntry,
    SourceReconciliation,
    read_lockfile,
    reconcile_declared_installed,
)
from mpm_cli.utils.lock_file_path import derive_lock_file_path


@dataclass
class _ListRow:
    """One rendered inventory row for a single source alias.

    Fields:
        alias: The source alias (the ``.mpm`` / ``.mpm.lock`` key).
        status: One of ``installed`` / ``not-installed`` / ``orphan``.
        name: The source name (from the lock for installed/orphan, from
            ``.mpm`` for not-installed).
        url: The credential-free source URL, or empty when unknown.
        ref_spec: The declared / locked ref constraint (e.g. ``1.0.0``, ``*``,
            ``main``).
        resolved_ref: The resolved ref recorded in the lock, or empty for a
            not-installed source.
        resolved_sha: The resolved commit SHA from the lock, or empty for a
            not-installed source.
        projects: The transitive package rows under this source (populated for
            ``--tree`` / JSON), each a dict with name/url/resolved_ref/
            resolved_sha/scope.
    """

    alias: str
    status: str
    name: str
    url: str
    ref_spec: str
    resolved_ref: str
    resolved_sha: str
    projects: list[dict] = field(default_factory=list)


def _emit_error(detail: object) -> None:
    """Print an error to stderr with exactly one ``ERROR: `` prefix.

    Some mpm exceptions (lockfile validation / consistency, and other command
    layers) already embed a leading ``ERROR:`` / ``Error:`` in their message.
    This normalises the prefix so the user never sees a doubled
    ``ERROR: ERROR:`` -- a clean, actionable line every time.

    Args:
        detail: The exception or message body to report.
    """
    text = str(detail)
    for prefix in ("ERROR:", "Error:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].lstrip()
            break
    print(f"ERROR: {text}", file=sys.stderr)


def _resolve_mpm_file(provided: pathlib.Path | None) -> pathlib.Path:
    """Resolve the ``.mpm`` path from the flag/env or by walking up from cwd.

    When ``provided`` is None, auto-discovers the nearest ``.mpm`` by walking
    up the directory tree (the same discovery ``mpm install`` uses). When
    provided, resolves it and fails fast if it does not name an existing file.

    Args:
        provided: Explicit ``.mpm`` path from ``--mpm-file`` / the
            MPM_MPM_FILE env var, or None for auto-discovery.

    Returns:
        The resolved absolute path to the ``.mpm`` file.

    Raises:
        FileNotFoundError: If auto-discovery finds no ``.mpm`` file, or the
            explicit path does not name an existing file.
    """
    if provided is None:
        return find_mpmenv()

    resolved = provided.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f".mpm file not found: {resolved}")
    return resolved


def _clean_ref(ref: str) -> str:
    """Strip a known ``refs/...`` prefix from a ref for compact display.

    Args:
        ref: A ref string that may carry a ``refs/tags/`` / ``refs/heads/`` /
            ``refs/remotes/origin/`` prefix.

    Returns:
        The ref with the first matching prefix removed, or the ref unchanged.
    """
    for prefix in REVISION_REF_PREFIXES:
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def _ref_display(row: _ListRow) -> str:
    """Render the REF column for a row: cleaned ref plus a short resolved SHA.

    Args:
        row: The row to render.

    Returns:
        The resolved ref (or declared ref-spec) with the truncated resolved SHA
        appended in parentheses when a SHA is present.
    """
    base = _clean_ref(row.resolved_ref) or row.ref_spec or MPM_LIST_REF_UNRESOLVED
    if row.resolved_sha:
        return f"{base} ({row.resolved_sha[:BRANCH_SHA_TRUNCATION_LENGTH]})"
    return base


def _entry_projects(entry: SourceEntry) -> list[dict]:
    """Collect the transitive package rows recorded for a lock source entry.

    Prefers the rich ``projects`` list (name + URL + resolved ref/SHA); falls
    back to the ``content_pins`` list (name + resolved SHA only) when a lock was
    written without populated projects.

    Args:
        entry: A resolved ``.mpm.lock`` source entry.

    Returns:
        A list of transitive package dicts, each tagged ``scope=transitive``.
    """
    projects: list[dict] = []
    if entry.projects:
        for project in entry.projects:
            projects.append(
                {
                    "name": project.name,
                    "url": project.url,
                    "resolved_ref": project.resolved_ref,
                    "resolved_sha": project.resolved_sha,
                    "scope": MPM_LIST_SCOPE_TRANSITIVE,
                }
            )
        return projects

    for pin in entry.content_pins:
        projects.append(
            {
                "name": pin.name,
                "url": "",
                "resolved_ref": "",
                "resolved_sha": pin.resolved_sha,
                "scope": MPM_LIST_SCOPE_TRANSITIVE,
            }
        )
    return projects


def _installed_or_orphan_row(alias: str, status: str, entry: SourceEntry) -> _ListRow:
    """Build a row for a lock-backed source (installed or orphan).

    Args:
        alias: The source alias.
        status: ``installed`` or ``orphan``.
        entry: The matching ``.mpm.lock`` source entry.

    Returns:
        The populated :class:`_ListRow`.
    """
    return _ListRow(
        alias=alias,
        status=status,
        name=entry.name,
        url=entry.url,
        ref_spec=entry.ref_spec,
        resolved_ref=entry.resolved_ref,
        resolved_sha=entry.resolved_sha,
        projects=_entry_projects(entry),
    )


def _not_installed_row(alias: str, declared: dict) -> _ListRow:
    """Build a row for a declared-but-not-installed source.

    Args:
        alias: The source alias.
        declared: The ``.mpm`` source dict (``url`` / ``ref`` / ``name`` ...).

    Returns:
        The populated :class:`_ListRow` (no resolved fields, no projects).
    """
    return _ListRow(
        alias=alias,
        status=MPM_LIST_STATUS_NOT_INSTALLED,
        name=declared["name"],
        url=declared["url"],
        ref_spec=declared["ref"],
        resolved_ref="",
        resolved_sha="",
        projects=[],
    )


def _build_rows(
    reconciliation: SourceReconciliation,
    declared_sources: dict,
    lock_by_alias: dict[str, SourceEntry],
) -> list[_ListRow]:
    """Assemble the alphabetically-sorted inventory rows from the reconciliation.

    Args:
        reconciliation: The declared-vs-installed partition.
        declared_sources: The ``.mpm`` ``sources`` mapping (alias -> dict).
        lock_by_alias: Lock source entries keyed by alias.

    Returns:
        The rows, sorted by alias, with each source tagged by its status.
    """
    rows: list[_ListRow] = []
    for alias in reconciliation.installed:
        rows.append(_installed_or_orphan_row(alias, MPM_LIST_STATUS_INSTALLED, lock_by_alias[alias]))
    for alias in reconciliation.not_installed:
        rows.append(_not_installed_row(alias, declared_sources[alias]))
    for alias in reconciliation.orphaned:
        rows.append(_installed_or_orphan_row(alias, MPM_LIST_STATUS_ORPHAN, lock_by_alias[alias]))
    rows.sort(key=lambda row: row.alias)
    return rows


def _project_detail(project: dict) -> str:
    """Render a transitive package's ref/SHA detail for the tree view.

    Args:
        project: A transitive package dict from :func:`_entry_projects`.

    Returns:
        The cleaned resolved ref with the truncated SHA appended when present.
    """
    base = _clean_ref(project["resolved_ref"]) or MPM_LIST_REF_UNRESOLVED
    sha = project["resolved_sha"]
    if sha:
        return f"{base} ({sha[:BRANCH_SHA_TRUNCATION_LENGTH]})"
    return base


def _format_list_table(rows: list[_ListRow], show_tree: bool) -> str:
    """Format inventory rows as a fixed-width ASCII table (SOURCE | REF | STATUS).

    Column widths are computed from the widest value (including the header) so
    the output is deterministic. When ``show_tree`` is set, each source's
    transitive packages are printed indented beneath its row.

    Args:
        rows: The rows to render.
        show_tree: When True, append transitive package lines under each source.

    Returns:
        A multi-line string ending with a trailing newline.
    """
    headers = (MPM_LIST_COLUMN_SOURCE, MPM_LIST_COLUMN_REF, MPM_LIST_COLUMN_STATUS)
    cells = [(row.alias, _ref_display(row), row.status) for row in rows]

    col_widths = [len(header) for header in headers]
    for row_cells in cells:
        for index, cell in enumerate(row_cells):
            col_widths[index] = max(col_widths[index], len(cell))

    def _fmt_row(values: tuple[str, ...]) -> str:
        return " | ".join(value.ljust(col_widths[index]) for index, value in enumerate(values))

    lines: list[str] = [_fmt_row(headers), "-+-".join("-" * width for width in col_widths)]
    for row, row_cells in zip(rows, cells):
        lines.append(_fmt_row(row_cells))
        if show_tree:
            for project in row.projects:
                detail = _project_detail(project)
                suffix = f"  {project['url']}" if project["url"] else ""
                lines.append(f"{MPM_LIST_TREE_INDENT}{project['name']}  {detail}{suffix}")

    return "\n".join(lines) + "\n"


def _build_list_payload(rows: list[_ListRow], show_tree: bool) -> dict:
    """Build the JSON-serialisable payload for the inventory rows.

    Args:
        rows: The rows to serialise.
        show_tree: When True, include each source's transitive ``projects`` list.

    Returns:
        A dict ``{"sources": [ {alias, status, name, url, ref_spec,
        resolved_ref, resolved_sha, scope, projects?}, ... ]}``.
    """
    sources: list[dict] = []
    for row in rows:
        obj: dict = {
            "alias": row.alias,
            "status": row.status,
            "name": row.name,
            "url": row.url,
            "ref_spec": row.ref_spec,
            "resolved_ref": row.resolved_ref,
            "resolved_sha": row.resolved_sha,
            "scope": MPM_LIST_SCOPE_DIRECT,
        }
        if show_tree:
            obj["projects"] = row.projects
        sources.append(obj)
    return {"sources": sources}


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Register the 'list' subcommand on the top-level argparse subparsers.

    Args:
        subparsers: The subparsers action from the top-level parser.
    """
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "list",
        add_help=True,
        help="List declared vs installed sources and their status.",
        description=(
            "Reconcile the sources declared in .mpm against the sources recorded in\n"
            ".mpm.lock and print one row per source with a status tag:\n\n"
            "  installed      declared in .mpm AND present in .mpm.lock\n"
            "  not-installed  declared in .mpm but not yet installed (run 'mpm install')\n"
            "  orphan         present in .mpm.lock but no longer declared in .mpm\n\n"
            "By default every source is shown (the declared/installed union). Use\n"
            "--declared to show only declared sources, --status to filter to one tag,\n"
            "and --tree to expand each installed source to its transitive packages."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--declared",
        dest="declared",
        action="store_true",
        default=False,
        help=(
            "Show only sources declared in .mpm (installed and not-installed); "
            "omit orphan sources that are in .mpm.lock but no longer declared."
        ),
    )

    parser.add_argument(
        "--tree",
        dest="tree",
        action="store_true",
        default=False,
        help="Expand each installed source to its transitive packages (from .mpm.lock).",
    )

    parser.add_argument(
        "--status",
        dest="status",
        default=None,
        choices=MPM_LIST_STATUS_CHOICES,
        metavar="<status>",
        help=(f"Filter to sources with the given status: {', '.join(MPM_LIST_STATUS_CHOICES)}."),
    )

    parser.add_argument(
        "--format",
        dest="format",
        default=os.environ.get(MPM_LIST_OUTPUT_FORMAT, MPM_LIST_OUTPUT_FORMAT_DEFAULT),
        choices=MPM_LIST_OUTPUT_FORMAT_CHOICES,
        metavar="<format>",
        help=(
            f"Output format: '{MPM_LIST_OUTPUT_FORMAT_TABLE}' (default) or "
            f"'{MPM_LIST_OUTPUT_FORMAT_JSON}'. "
            f"Overridden by the {MPM_LIST_OUTPUT_FORMAT} environment variable; "
            "the CLI flag takes precedence when both are set."
        ),
    )

    parser.add_argument(
        "--mpm-file",
        dest="mpm_file",
        default=os.environ.get(MPM_MPM_FILE_ENV),
        metavar="<path>",
        help=(
            "Path to the .mpm file. "
            "Defaults to auto-discovery (walk up from the current directory). "
            f"Overridden by the {MPM_MPM_FILE_ENV} environment variable; "
            "the CLI flag takes precedence when both are set."
        ),
    )

    parser.add_argument(
        "--lock-file",
        dest="lock_file",
        default=None,
        metavar="<path>",
        help=(
            "Path to the .mpm.lock file. "
            "Defaults to <mpm-file>.lock. "
            f"Overridden by the {MPM_LOCK_FILE} environment variable; "
            "the CLI flag takes precedence when both are set."
        ),
    )

    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute the 'mpm list' command.

    Reads ``.mpm`` (declared) and ``.mpm.lock`` (installed), reconciles them,
    and prints a status-tagged inventory. Exit code is 0 on success (including
    the empty and not-yet-installed states); 1 on an unresolvable path, an
    unreadable/malformed lock, or an unrecognised env-var format.

    Args:
        args: Parsed argparse namespace with ``declared``, ``tree``, ``status``,
            ``format``, ``mpm_file``, and ``lock_file`` attributes.

    Returns:
        The process exit code (0 or 1).
    """
    if args.format not in MPM_LIST_OUTPUT_FORMAT_CHOICES:
        _emit_error(
            f"{MPM_LIST_OUTPUT_FORMAT}={args.format!r} is not a recognised format; "
            f"expected one of {', '.join(MPM_LIST_OUTPUT_FORMAT_CHOICES)}."
        )
        return 1

    provided_mpm = pathlib.Path(args.mpm_file) if args.mpm_file else None
    try:
        mpm_path = _resolve_mpm_file(provided_mpm)
    except FileNotFoundError as exc:
        _emit_error(exc)
        return 1

    env_lock = os.environ.get(MPM_LOCK_FILE)
    provided_lock = pathlib.Path(args.lock_file) if args.lock_file else None
    lock_file_path = derive_lock_file_path(mpm_path, provided_lock, env_lock)
    lock_was_explicit = provided_lock is not None or bool(env_lock)

    try:
        parsed = parse_mpmenv(mpm_path)
        mpm_aliases = list(parsed["MPM_SOURCES"])
        mpm_ref_specs = {alias: data["ref"] for alias, data in parsed["sources"].items()}
        declared_sources = parsed["sources"]
    except NoSourcesError:
        mpm_aliases = []
        mpm_ref_specs = {}
        declared_sources = {}
    except (FileNotFoundError, ValueError, OSError) as exc:
        _emit_error(exc)
        return 1

    lockfile = None
    if lock_file_path.is_file():
        try:
            lockfile = read_lockfile(lock_file_path)
        except (LockfileSchemaError, LockfileValidationError, ValueError, OSError, KeyError) as exc:
            _emit_error(exc)
            return 1
    elif lock_was_explicit:
        _emit_error(
            f"lock file not found: {lock_file_path}\n"
            f"  Provide a valid path via --lock-file or the {MPM_LOCK_FILE} env var, "
            "or run 'mpm install' to generate it."
        )
        return 1

    if lockfile is not None:
        reconciliation = reconcile_declared_installed(mpm_aliases, mpm_ref_specs, lockfile)
        lock_by_alias = {source.alias: source for source in lockfile.sources}
    else:
        reconciliation = SourceReconciliation(
            installed=[],
            not_installed=sorted(set(mpm_aliases)),
            orphaned=[],
            duplicates=[],
            ref_mismatches=[],
        )
        lock_by_alias = {}

    rows = _build_rows(reconciliation, declared_sources, lock_by_alias)

    if args.declared:
        rows = [row for row in rows if row.status != MPM_LIST_STATUS_ORPHAN]
    if args.status is not None:
        rows = [row for row in rows if row.status == args.status]

    if args.format == MPM_LIST_OUTPUT_FORMAT_JSON:
        from mpm_cli.cli import _emit_json_payload

        _emit_json_payload(_build_list_payload(rows, args.tree), sort_keys=False, indent=MPM_LIST_JSON_INDENT)
        return 0

    if lockfile is None and not lock_was_explicit and mpm_aliases:
        print(MPM_LIST_NO_LOCKFILE_NOTE, file=sys.stderr)

    if not rows:
        if not mpm_aliases and lockfile is None:
            print(MPM_LIST_NO_SOURCES_NOTE, file=sys.stderr)
        return 0

    print(_format_list_table(rows, args.tree), end="")
    return 0
