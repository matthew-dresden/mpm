"""Install subcommand: parse .mpm config and run core install lifecycle.

Parses the .mpm configuration file and delegates to the core install logic.
No pipx or external tool management is performed.
"""

import os
import pathlib
import sys
import warnings

from mpm_cli.constants import MPM_LOCK_FILE as _MPM_LOCK_FILE_ENV
from mpm_cli.core.discover import find_mpmenv
from mpm_cli.core.install import InstallError, install
from mpm_cli.core.lockfile import LockfileConsistencyError
from mpm_cli.repo import RepoCommandError
from mpm_cli.utils.lock_file_path import derive_lock_file_path


_LEGACY_REPO_URL_ENV = "REPO_URL"
_LEGACY_REPO_REV_ENV = "REPO_REV"


_LEGACY_ENV_DEPRECATION_MSG = (
    "{var_list} environment variable(s) are deprecated and no longer used by 'mpm install'. "
    "Use --catalog-source to specify a remote catalog source instead."
)


def _warn_if_legacy_env_vars_set() -> None:
    """Emit a single DeprecationWarning if REPO_URL and/or REPO_REV are set.

    The legacy REPO_URL and REPO_REV environment variables are no longer
    used by mpm install. Users should migrate to --catalog-source.
    A single combined warning is emitted when either or both variables are
    present so that CI pipelines configured with -W error::DeprecationWarning
    can detect the stale configuration.

    The same message is also written directly to sys.stderr so that end users
    and CI logs see the migration notice regardless of Python's active warning
    filter (Python suppresses DeprecationWarning by default in subprocess
    contexts without a -W flag).
    """
    repo_url = os.environ.get(_LEGACY_REPO_URL_ENV)
    repo_rev = os.environ.get(_LEGACY_REPO_REV_ENV)

    if not repo_url and not repo_rev:
        return

    set_vars = [v for v, val in ((_LEGACY_REPO_URL_ENV, repo_url), (_LEGACY_REPO_REV_ENV, repo_rev)) if val]
    var_list = " and ".join(set_vars)
    message = _LEGACY_ENV_DEPRECATION_MSG.format(var_list=var_list)
    warnings.warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    print(message, file=sys.stderr)


def register(subparsers) -> None:
    """Register the install subcommand.

    Args:
        subparsers: The subparsers object from the parent parser.
    """
    parser = subparsers.add_parser(
        "install",
        add_help=True,
        help="Full install lifecycle: multi-source manifest sync and marketplace setup",
        description=(
            "Execute the full MPM install lifecycle.\n\n"
            "Parses the .mpm configuration file, then runs repo init/envsubst/sync\n"
            "for each source defined in the .mpm file. Aggregates packages into\n"
            ".packages/ via symlinks."
        ),
        epilog="Example:\n  mpm install           # auto-discovers .mpm\n  mpm install .mpm    # explicit path",
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mpmenv_path",
        nargs="?",
        default=None,
        type=pathlib.Path,
        help="Path to the .mpm configuration file (default: auto-discover from current directory)",
    )

    refresh_group = parser.add_mutually_exclusive_group()
    refresh_group.add_argument(
        "--refresh-lock",
        action="store_true",
        default=False,
        help=(
            "Ignore the existing lockfile, re-resolve every transitive version from "
            "scratch against the committed .mpm source declarations, and overwrite "
            ".mpm.lock with the new state."
        ),
    )
    refresh_group.add_argument(
        "--refresh-lock-source",
        metavar="NAME",
        default=None,
        help=(
            "Re-resolve exactly one top-level source's full chain from the committed "
            ".mpm while preserving every other source's lockfile entries verbatim. "
            "NAME may be a source name (the MPM_SOURCE_<name> key) or a catalog "
            "entry name resolved via derive_source_name."
        ),
    )

    parser.add_argument(
        "--reconcile",
        action="store_true",
        default=False,
        help=(
            "Opt in to the lenient npm-install reconcile when .mpm and "
            ".mpm.lock have drifted. By default a drifted pair fails fast "
            "(exit 1) without mutating the lock. With this flag, mpm prunes "
            "orphaned lock entries, re-resolves added or changed sources, "
            "replays unchanged sources, and rewrites .mpm.lock on success. "
            "Use --refresh-lock to rebuild the entire lock from scratch instead."
        ),
    )
    parser.add_argument(
        "--strict-lock",
        action="store_true",
        default=False,
        help=(
            "Upgrade orphaned lock entries to a hard error in the consistent "
            "state. An orphaned lock entry is a source present in .mpm.lock "
            "but absent from .mpm (e.g. after 'mpm remove'). Drift between "
            ".mpm and .mpm.lock already fails fast by default; this flag "
            "additionally fails on an orphan that survives a mpm_hash match. "
            "Remediation: restore the missing MPM_SOURCE_<name>_* triples in "
            ".mpm, or run with --reconcile to prune."
        ),
    )
    parser.add_argument(
        "--strict-drift",
        action="store_true",
        default=False,
        help=(
            "Upgrade branch drift to a hard error in the consistent state. "
            "Branch drift occurs when the lockfile records a SHA for a "
            "branch-shaped source but the branch's current tip on the remote is "
            "a different SHA. Without this flag, the locked SHA is reused and an "
            "info-line is emitted (the content pin is replayed). With this flag, "
            "mpm exits with an error listing every drifted source. "
            "Remediation: run 'mpm install --refresh-lock-source <source>' "
            "to accept the new branch tip."
        ),
    )

    parser.add_argument(
        "--lock-file",
        metavar="PATH",
        default=None,
        type=pathlib.Path,
        help=(
            "Path to the lock file. Defaults to <mpm-file>.lock (derived from "
            "--mpm-file). The MPM_LOCK_FILE environment variable is consulted "
            "when this flag is absent; the CLI flag takes precedence when both are set."
        ),
    )

    parser.set_defaults(func=_run)


def _run(args) -> int | None:
    """Execute the install command.

    Resolves the .mpm path (walking up from cwd when not provided), parses
    and validates the configuration, then delegates to core.install().

    Parse/validate failures are converted to a non-zero exit with a clear
    stderr message so the CLI boundary preserves fail-fast semantics.

    Emits a DeprecationWarning if the legacy REPO_URL or REPO_REV environment
    variables are set so existing CI workflows receive a clear migration signal.

    Args:
        args: Parsed arguments with mpmenv_path.
    """
    from mpm_cli.core.mpmenv import parse_mpmenv

    _warn_if_legacy_env_vars_set()

    if args.mpmenv_path is None:
        try:
            args.mpmenv_path = find_mpmenv()
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"mpm install: found {args.mpmenv_path}")

    args.mpmenv_path = args.mpmenv_path.resolve()
    if not args.mpmenv_path.is_file():
        print(f"Error: .mpm file not found: {args.mpmenv_path}", file=sys.stderr)
        sys.exit(1)

    try:
        parse_mpmenv(args.mpmenv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    lock_file_path = derive_lock_file_path(
        args.mpmenv_path,
        args.lock_file,
        os.environ.get(_MPM_LOCK_FILE_ENV),
    )

    try:
        install(
            args.mpmenv_path,
            lock_file_path=lock_file_path,
            refresh_lock=args.refresh_lock,
            refresh_lock_source=args.refresh_lock_source,
            strict_lock=args.strict_lock,
            strict_drift=args.strict_drift,
            reconcile=args.reconcile,
        )
    except (InstallError, LockfileConsistencyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, RepoCommandError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    return None
