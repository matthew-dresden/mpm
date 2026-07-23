"""Clean subcommand handler."""

import pathlib
import sys

from mpm_cli.core.clean import clean, remove_mpm_home_store
from mpm_cli.core.discover import find_mpmenv


def register(subparsers) -> None:
    """Register the clean subcommand.

    Args:
        subparsers: The subparsers object from the parent parser.
    """
    parser = subparsers.add_parser(
        "clean",
        add_help=True,
        help="Full teardown: uninstall, remove dirs",
        description=(
            "Execute the full MPM clean lifecycle.\n\n"
            "If any dependency set MPM_SOURCE_<alias>_MARKETPLACE=true, runs\n"
            "the uninstall script and removes the marketplace directory. Then\n"
            "removes .packages/ and .mpm-data/ directories and prunes the\n"
            "content-addressed entries from the shared MPM_HOME store.\n\n"
            "With --orphans, before the normal teardown mpm also unregisters\n"
            "any mpm-owned marketplaces recorded in .mpm.lock that are no\n"
            "longer referenced by .mpm (pruning them from ~/.claude).\n\n"
            "With --purge, mpm also deletes this project's .mpm and\n"
            ".mpm.lock files. With --purge-all, it additionally removes the\n"
            "shared MPM_HOME store directory (default ~/.mpm-home); this\n"
            "runs even when no .mpm project is present."
        ),
        epilog=(
            "Example:\n"
            "  mpm clean             # auto-discovers .mpm\n"
            "  mpm clean .mpm      # explicit path\n"
            "  mpm clean --orphans   # also unregister orphaned marketplaces\n"
            "  mpm clean --purge     # also delete .mpm and .mpm.lock\n"
            "  mpm clean --purge-all # also remove the MPM_HOME store dir"
        ),
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mpmenv_path",
        nargs="?",
        default=None,
        type=pathlib.Path,
        help="Path to the .mpm configuration file (default: auto-discover from current directory)",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        default=False,
        help=(
            "Also unregister mpm-owned marketplaces no longer referenced by "
            ".mpm/.mpm.lock (prunes them from ~/.claude)."
        ),
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        default=False,
        help=(
            "Also delete this project's .mpm and .mpm.lock files after the "
            "normal teardown (full removal of the project's mpm config)."
        ),
    )
    parser.add_argument(
        "--purge-all",
        action="store_true",
        default=False,
        help=(
            "Everything --purge does, and also remove the shared mpm home store "
            "directory (MPM_HOME, default ~/.mpm-home) used by all projects. "
            "Runs even when no .mpm project is present (removes only the shared store)."
        ),
    )
    parser.set_defaults(func=_run)


def _purge_home_only() -> None:
    """Remove only the shared mpm home store when no project ``.mpm`` is present.

    ``mpm clean --purge-all`` is machine-global: it must still tear down the
    shared ``MPM_HOME`` store even when there is no discoverable project
    ``.mpm`` (e.g. right after ``mpm clean --purge`` deleted it). Delegates to
    ``remove_mpm_home_store`` so all safety refusals (the filesystem root, the
    user home directory, an ancestor of the home or current directory) are
    preserved exactly as in the in-``clean()`` path.
    """
    print("mpm clean --purge-all: no .mpm project found; removing only the shared mpm home store...")
    remove_mpm_home_store()


def _run(args) -> None:
    """Execute the clean command.

    Args:
        args: Parsed arguments with mpmenv_path.
    """
    if args.mpmenv_path is None:
        try:
            args.mpmenv_path = find_mpmenv()
        except FileNotFoundError as exc:
            if args.purge_all:
                _purge_home_only()
                return
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"mpm clean: found {args.mpmenv_path}")

    args.mpmenv_path = args.mpmenv_path.resolve()
    if not args.mpmenv_path.is_file():
        if args.purge_all:
            _purge_home_only()
            return
        print(f"Error: .mpm file not found: {args.mpmenv_path}", file=sys.stderr)
        sys.exit(1)

    try:
        clean(
            args.mpmenv_path,
            orphans=args.orphans,
            purge=(args.purge or args.purge_all),
            purge_home=args.purge_all,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
