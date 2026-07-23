"""Repo subcommand: passthrough to mpm's repo subsystem.

Delegates all trailing arguments to repo_run() from the Python API layer.
Supports the full repo subcommand surface (init, sync, envsubst, etc.) by
forwarding arbitrary argv to the repo dispatcher without interpretation.

The repo directory is resolved using documented precedence:

1. ``--repo-dir=<flag>`` wins when present.
2. ``MPM_REPO_DIR`` env var is used when the flag is absent.
3. Falls back to the compiled-in default when neither is set.
"""

import argparse
import os
import sys
from typing import Optional

from mpm_cli.constants import MPM_REPO_DIR_ENV, MPMENV_REPO_DIR_DEFAULT
from mpm_cli.repo import RepoCommandError, repo_run


def resolve_repo_dir(
    flag_value: Optional[str],
    env: Optional[dict] = None,
) -> str:
    """Resolve the repo directory using documented flag-wins-over-env precedence.

    Applies the following resolution order, then converts the result to an
    absolute path via :func:`os.path.abspath`:

    1. If ``flag_value`` is not ``None``, use it (flag wins).
    2. If ``MPM_REPO_DIR`` is present in ``env``, use its value.
    3. Use :data:`~mpm_cli.constants.MPMENV_REPO_DIR_DEFAULT`.

    The absolute-path conversion is required because
    :class:`~mpm_cli.repo.manifest_xml.RepoClient` (and its parent
    :class:`~mpm_cli.repo.manifest_xml.XmlManifest`) enforce that the
    derived ``manifest_file`` path is absolute, raising
    :class:`~mpm_cli.repo.error.ManifestParseError` otherwise.

    Args:
        flag_value: The value supplied to ``--repo-dir``, or ``None`` when the
            flag was not provided.
        env: Mapping used for environment-variable lookup. When ``None``,
            :data:`os.environ` is used. Pass an explicit dict in unit tests to
            avoid reading the real process environment.

    Returns:
        The resolved absolute path to the ``.repo`` directory.
    """
    if env is None:
        env = os.environ
    if flag_value is not None:
        return os.path.abspath(flag_value)
    return os.path.abspath(env.get(MPM_REPO_DIR_ENV, MPMENV_REPO_DIR_DEFAULT))


def register(subparsers) -> None:
    """Register the repo subcommand.

    Adds a ``repo`` sub-parser that captures all trailing arguments using
    argparse.REMAINDER and passes them to the repo dispatcher.

    Args:
        subparsers: The subparsers object from the parent parser.
    """
    parser = subparsers.add_parser(
        "repo",
        add_help=True,
        help="Run a mpm repo subcommand (manifest-driven sync)",
        description=(
            "Run mpm's repo subcommands.\n\n"
            "All trailing arguments after 'mpm repo' are passed verbatim to\n"
            "the repo dispatcher. Use 'mpm repo --help' to see this help,\n"
            "or 'mpm repo help' to see the per-subcommand help.\n\n"
            "Examples:\n"
            "  mpm repo init -u <url> -b <branch> -m <manifest>\n"
            "  mpm repo sync --jobs=4\n"
            "  mpm repo status\n"
            "  mpm repo help"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo-dir",
        dest="repo_dir",
        default=None,
        help=(
            f"Path to the .repo directory for the repo tool (default: ${{MPM_REPO_DIR}} or {MPMENV_REPO_DIR_DEFAULT!r})"
        ),
    )
    parser.add_argument(
        "repo_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded verbatim to the repo tool",
    )
    parser.set_defaults(func=_run)


def _run(args) -> None:
    """Execute the repo passthrough command.

    Resolves the repo directory via :func:`resolve_repo_dir`, extracts the
    trailing arguments from ``args.repo_args``, and delegates them to
    repo_run(). Propagates the exit code from repo_run() directly via
    sys.exit().

    Args:
        args: Parsed arguments with repo_args (list of trailing argv) and
            repo_dir (``--repo-dir`` flag value, or ``None`` when not supplied).
    """
    repo_dir = resolve_repo_dir(flag_value=args.repo_dir)
    try:
        exit_code = repo_run(args.repo_args, repo_dir=repo_dir)
    except RepoCommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code if exc.exit_code is not None else 1)
    sys.exit(exit_code)
