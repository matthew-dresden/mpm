"""Validate subcommand with xml, marketplace, metadata, and lockfile sub-subcommands."""

import os
import subprocess
import sys
from pathlib import Path

from mpm_cli.commands.catalog import (
    MPM_CATALOG_AUDIT_FORMAT_JSON,
    AuditFinding,
    _build_findings_payload,
    _check_entry_name_uniqueness,
    _check_metadata,
    _check_source_name_derivation,
    _format_findings,
)
from mpm_cli.constants import MPM_LOCK_FILE as _MPM_LOCK_FILE_ENV
from mpm_cli.core.discover import find_mpmenv
from mpm_cli.core.mpmenv import parse_mpmenv
from mpm_cli.core.lockfile import (
    LockfileConsistencyError,
    LockfileSchemaError,
    LockfileValidationError,
    check_lockfile_consistency,
    read_lockfile,
)
from mpm_cli.core.marketplace_validator import validate_marketplace
from mpm_cli.core.xml_validator import validate_xml
from mpm_cli.utils.lock_file_path import derive_lock_file_path


def register(subparsers) -> None:
    """Register the validate subcommand with xml, marketplace, and metadata sub-subcommands.

    Args:
        subparsers: The subparsers object from the parent parser.
    """
    validate_parser = subparsers.add_parser(
        "validate",
        add_help=True,
        help="Validate XML manifests",
        description="Validate manifest XML files for well-formedness and correctness.",
    )

    validate_subs = validate_parser.add_subparsers(
        dest="validate_command",
        title="validation targets",
        description="Available validation targets",
    )

    xml_parser = validate_subs.add_parser(
        "xml",
        add_help=True,
        help="Validate manifest XML files (well-formedness, required attributes, include chains)",
        description=(
            "Validate all XML manifest files under repo-specs/.\n\n"
            "Checks well-formedness, required attributes on <project> and <remote>\n"
            "elements, and that <include> name attributes point to existing files."
        ),
        epilog="Example:\n  mpm validate xml\n  mpm validate xml --repo-root /path/to/repo",
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    xml_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (default: auto-detect via git rev-parse)",
    )
    xml_parser.set_defaults(func=_run_xml)

    mp_parser = validate_subs.add_parser(
        "marketplace",
        add_help=True,
        help="Validate marketplace XML manifests (linkfile dest, include chains, name uniqueness, tag format)",
        description=(
            "Validate all marketplace XML manifests under repo-specs/.\n\n"
            "Checks linkfile dest attributes, include chain integrity,\n"
            "project path uniqueness, and revision tag format."
        ),
        epilog="Example:\n  mpm validate marketplace\n  mpm validate marketplace --repo-root /path/to/repo",
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    mp_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (default: auto-detect via git rev-parse)",
    )
    mp_parser.set_defaults(func=_run_marketplace)

    meta_parser = validate_subs.add_parser(
        "metadata",
        add_help=True,
        help=(
            "Check catalog metadata soft-spots (required/recommended fields, "
            "source-name derivation, entry-name uniqueness) without network access."
        ),
        description=(
            "Check every *-marketplace.xml under repo-specs/ for in-repo soft-spot "
            "violations (spec Section 3.5 rules 1, 2, 3).\n\n"
            "Checks performed:\n"
            "  - Soft-spot 1 (metadata): required fields present and non-empty,\n"
            "    no duplicate child elements, exactly one <catalog-metadata> block.\n"
            "  - Soft-spot 2 (source-name derivation): entry name normalises cleanly\n"
            "    and uses only [a-zA-Z0-9_-] characters.\n"
            "  - Soft-spot 3 (entry-name uniqueness): no two XML files share the\n"
            "    same <catalog-metadata><name> value.\n\n"
            "No network access. Does not clone. Does not call git ls-remote."
        ),
        epilog=(
            "Example:\n"
            "  mpm validate metadata\n"
            "  mpm validate metadata --repo-root /path/to/repo\n"
            "  mpm validate metadata --format json"
        ),
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    meta_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (default: auto-detect via git rev-parse)",
    )
    meta_parser.add_argument(
        "--format",
        dest="format",
        choices=("text", "json"),
        default="text",
        metavar="{text,json}",
        help=(
            "Output format. 'text' prints one finding per line with ERROR:/WARN:/INFO: "
            "prefix. 'json' prints a single JSON object {\"findings\": [...]}. Default: text."
        ),
    )
    meta_parser.set_defaults(func=_run_metadata)

    lock_parser = validate_subs.add_parser(
        "lockfile",
        add_help=True,
        help="Check .mpm <-> .mpm.lock consistency (alias uniqueness, alias set, ref-specs)",
        description=(
            "Check that the consumer-project .mpm declarations agree with the\n"
            ".mpm.lock entries (spec Section 4.5 / FR-24).\n\n"
            "Checks performed:\n"
            "  - Alias uniqueness: every source alias declared in .mpm is unique.\n"
            "  - Alias-set parity: the alias set in .mpm.lock equals the alias\n"
            "    set declared in .mpm.\n"
            "  - Ref-spec parity: each .mpm.lock entry's ref_spec matches the\n"
            "    revision declared for that alias in .mpm.\n\n"
            "Exits 0 on a consistent pair; exits non-zero with an actionable\n"
            "message on drift. This is the same check 'mpm install' runs\n"
            "implicitly before it resolves."
        ),
        epilog=(
            "Example:\n"
            "  mpm validate lockfile\n"
            "  mpm validate lockfile .mpm\n"
            "  mpm validate lockfile --lock-file /path/to/.mpm.lock"
        ),
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    lock_parser.add_argument(
        "mpmenv_path",
        nargs="?",
        default=None,
        type=Path,
        help="Path to the .mpm configuration file (default: auto-discover from current directory)",
    )
    lock_parser.add_argument(
        "--lock-file",
        metavar="PATH",
        default=None,
        type=Path,
        help=(
            "Path to the lock file. Defaults to <mpm-file>.lock (derived from the "
            ".mpm path). The MPM_LOCK_FILE environment variable is consulted when "
            "this flag is absent; the CLI flag takes precedence when both are set."
        ),
    )
    lock_parser.set_defaults(func=_run_lockfile)

    validate_parser.set_defaults(func=_run_validate_help)
    validate_parser._validate_subs = validate_subs


def _run_validate_help(args) -> None:
    """Show help when no validate sub-subcommand is given."""
    if args.validate_command is None:
        print(
            "Error: Must specify a validation target: xml, marketplace, metadata, or lockfile",
            file=sys.stderr,
        )
        sys.exit(2)


def _resolve_repo_root(provided: Path | None) -> Path:
    """Resolve repository root from argument or git.

    Args:
        provided: Explicitly provided repo root, or None for auto-detect.

    Returns:
        The resolved repository root path, always absolute.

    Raises:
        SystemExit: If auto-detection fails or the provided directory does not
            exist.
    """

    if provided is not None:
        resolved = provided.resolve()
        if not resolved.is_dir():
            print(f"Error: --repo-root directory not found: {resolved}", file=sys.stderr)
            sys.exit(1)
        return resolved

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            "Error: Could not auto-detect repo root. Run from within a git repository or use --repo-root.",
            file=sys.stderr,
        )
        sys.exit(1)

    return Path(result.stdout.strip())


def _run_xml(args) -> None:
    """Execute XML validation.

    Args:
        args: Parsed arguments with optional repo_root.
    """
    repo_root = _resolve_repo_root(args.repo_root)
    exit_code = validate_xml(repo_root)
    sys.exit(exit_code)


def _run_marketplace(args) -> None:
    """Execute marketplace validation.

    Args:
        args: Parsed arguments with optional repo_root.
    """
    repo_root = _resolve_repo_root(args.repo_root)
    exit_code = validate_marketplace(repo_root)
    sys.exit(exit_code)


def validate_metadata_command(args) -> None:
    """Execute catalog metadata validation (soft-spots 1, 2, 3) without network access.

    Runs three in-repo soft-spot checks from spec Section 3.5 against every
    ``*-marketplace.xml`` file under ``<repo_root>/repo-specs/``:

    - Soft-spot 1 (metadata): required fields present, no duplicate child elements,
      exactly one ``<catalog-metadata>`` block per file.
    - Soft-spot 2 (source-name derivation): entry name normalises cleanly via
      ``derive_source_name`` and uses only ``[a-zA-Z0-9_-]`` characters.
    - Soft-spot 3 (entry-name uniqueness): no two files share the same
      ``<catalog-metadata><name>`` value.

    Does NOT call ``git ls-remote``. No network access. No cloning.

    Exit code semantics:
    - Exit 0 if no ERROR-level findings (warnings are acceptable).
    - Exit 1 if any ERROR-level finding is produced.

    Args:
        args: Parsed arguments. Expected attributes:
            repo_root (Path | None): Optional path to the manifest repo root.
            format (str): Output format -- "text" or "json".

    Raises:
        SystemExit: Always. Exit 0 on success (no errors), exit 1 on any error finding.
    """
    repo_root = _resolve_repo_root(args.repo_root)

    findings: list[AuditFinding] = []
    findings.extend(_check_metadata(repo_root))
    findings.extend(_check_source_name_derivation(repo_root))
    findings.extend(_check_entry_name_uniqueness(repo_root))

    if args.format == MPM_CATALOG_AUDIT_FORMAT_JSON:
        from mpm_cli.cli import _emit_json_payload

        _emit_json_payload(_build_findings_payload(findings))
    else:
        formatted = _format_findings(findings, args.format)
        if formatted:
            print(formatted)

    has_error = any(f.kind == "error" for f in findings)
    sys.exit(1 if has_error else 0)


def _run_metadata(args) -> None:
    """Execute catalog metadata validation.

    Args:
        args: Parsed arguments with optional repo_root and format.
    """
    validate_metadata_command(args)


def _resolve_mpmenv_path(provided: Path | None) -> Path:
    """Resolve the ``.mpm`` file path from the argument or auto-discovery.

    When ``provided`` is None, walks up from the current directory looking for a
    ``.mpm`` file (the same discovery ``mpm install`` uses). When provided,
    resolves it to an absolute path and fails fast if it is not a file.

    Args:
        provided: Explicit ``.mpm`` path from the positional argument, or None
            for auto-discovery.

    Returns:
        The resolved absolute path to the ``.mpm`` file.

    Raises:
        SystemExit: If auto-discovery finds no ``.mpm`` file, or the explicit
            path does not name an existing file.
    """
    if provided is None:
        try:
            return find_mpmenv()
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    resolved = provided.resolve()
    if not resolved.is_file():
        print(f"Error: .mpm file not found: {resolved}", file=sys.stderr)
        sys.exit(1)
    return resolved


def validate_lockfile_command(args) -> None:
    """Check ``.mpm`` <-> ``.mpm.lock`` consistency and exit (spec Section 4.5 / FR-24).

    Resolves the ``.mpm`` path (explicit argument or auto-discovery) and the
    lock path (``--lock-file`` flag, ``MPM_LOCK_FILE`` env var, or the derived
    ``<mpm-file>.lock``), parses both, and runs the shared
    ``check_lockfile_consistency`` check from ``core/lockfile.py`` -- the same
    check ``mpm install`` runs before it resolves, so a drifted pair that this
    command reports also makes the default install fail fast (spec Section 4.3).

    Exit code semantics:
      - Exit 0 if ``.mpm`` and ``.mpm.lock`` are consistent.
      - Exit 1 on any drift (duplicate alias, alias-set drift, ref-spec drift),
        a missing/unreadable ``.mpm`` or ``.mpm.lock``, or a malformed lock.

    Args:
        args: Parsed arguments. Expected attributes:
            mpmenv_path (Path | None): Optional path to the ``.mpm`` file.
            lock_file (Path | None): Optional ``--lock-file`` override.

    Raises:
        SystemExit: Always. Exit 0 on a consistent pair, exit 1 on any error.
    """
    mpmenv_path = _resolve_mpmenv_path(args.mpmenv_path)
    lock_file_path = derive_lock_file_path(
        mpmenv_path,
        args.lock_file,
        os.environ.get(_MPM_LOCK_FILE_ENV),
    )

    try:
        parsed = parse_mpmenv(mpmenv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not lock_file_path.is_file():
        print(
            f"Error: .mpm.lock file not found: {lock_file_path}\n"
            f"  Run 'mpm install' to generate the lock for {mpmenv_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        lockfile = read_lockfile(lock_file_path)
    except (LockfileSchemaError, LockfileValidationError, OSError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    mpm_aliases = list(parsed["MPM_SOURCES"])
    mpm_ref_specs = {alias: data["ref"] for alias, data in parsed["sources"].items()}

    try:
        check_lockfile_consistency(mpm_aliases, mpm_ref_specs, lockfile)
    except LockfileConsistencyError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(f"mpm validate lockfile: {mpmenv_path} and {lock_file_path} are consistent.")
    sys.exit(0)


def _run_lockfile(args) -> None:
    """Execute .mpm <-> .mpm.lock consistency validation.

    Args:
        args: Parsed arguments with optional mpmenv_path and lock_file.
    """
    validate_lockfile_command(args)
