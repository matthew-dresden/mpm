"""Centralized constants for the mpm-cli package.

All module-level constants live here to avoid hard-coded values
scattered across source files.
"""

import os
import pathlib
import re


def _env_int(var: str, default: int) -> int:
    """Read *var* from the environment and return it as an integer.

    Returns *default* when the variable is unset (absent from the environment).
    Raises ``SystemExit`` with a clear, actionable message naming the offending
    variable when the value is present but cannot be parsed as an integer
    (including an empty string).
    """
    raw = os.environ.get(var)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"ERROR: {var} must be an integer; got {raw!r}")


EXIT_CODE_DEPRECATED = 3


MARKETPLACE_DIR_PREFIX = "${CLAUDE_MARKETPLACES_DIR}/"


REVISION_EXISTENCE_REQUIRED_ENV_VAR = "MPM_VALIDATE_REQUIRE_EXISTENCE"


REFS_TAGS_RE = re.compile(r"^refs/tags/(?:.+/)?\d+\.\d+\.\d+$")
CONSTRAINT_RE = re.compile(r"^(~=|>=|<=|>|<)\d+\.\d+\.\d+$")


PEP440_OPERATORS = ("~=", ">=", "<=", "!=", "==", ">", "<")


TAG_ERROR_DISPLAY_CAP = 10


SOURCE_PREFIX = "MPM_SOURCE_"
SOURCE_URL_SUFFIX = "_URL"
SOURCE_REF_SUFFIX = "_REF"
SOURCE_PATH_SUFFIX = "_PATH"
SOURCE_NAME_SUFFIX = "_NAME"
SOURCE_NON_URL_SUFFIXES = (
    SOURCE_REF_SUFFIX,
    SOURCE_PATH_SUFFIX,
    SOURCE_NAME_SUFFIX,
)
SOURCE_SUFFIXES = (SOURCE_URL_SUFFIX,) + SOURCE_NON_URL_SUFFIXES
SUFFIX_TO_KEY = {
    SOURCE_URL_SUFFIX: "url",
    SOURCE_REF_SUFFIX: "ref",
    SOURCE_PATH_SUFFIX: "path",
    SOURCE_NAME_SUFFIX: "name",
}


SOURCE_MARKETPLACE_SUFFIX = "_MARKETPLACE"
SOURCE_MARKETPLACE_KEY = "marketplace"


SOURCE_ENV_KEY = "env"
SOURCE_GITBASE_VAR = "GITBASE"
SOURCE_RESERVED_SUFFIXES = SOURCE_SUFFIXES + (SOURCE_MARKETPLACE_SUFFIX,)


MARKETPLACE_FLAG_TRUE = "true"


CATALOG_TYPE_CLAUDE_MARKETPLACE = "claude-marketplace"
SHELL_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


MPM_HOME_ENV_VAR = "MPM_HOME"


MPM_HOME_DIR_NAME = ".mpm-home"


MPM_HOME_STORE_SUBDIR = "store"


MPM_HOME_STORE_ENTRIES_SUBDIR = "entries"


MPM_HOME_STORE_LOCKS_SUBDIR = ".locks"


MPM_HOME_STORE_TMP_SUBDIR = ".tmp"


MPM_HOME_STORE_GITIGNORE_ENTRY = "*"


MPM_HOME_CACHE_SUBDIR = "cache"


def resolve_mpm_home(override: "pathlib.Path | None" = None) -> pathlib.Path:
    """Resolve the shared mpm home root directory.

    Resolution precedence (highest wins), per spec Section 7.1:
    0. The ``--home`` / ``--store-dir`` CLI flag, passed here as *override*,
       when it is not ``None``.
    1. The ``MPM_HOME`` environment variable, when set to a non-empty value.
    2. The default ``Path.home() / MPM_HOME_DIR_NAME`` (i.e. ``~/.mpm-home``).

    The default is derived from the real user home directory at call time; no
    absolute path is hard-coded. The returned path is NOT created here -- the
    caller that needs a writable directory (the store base dir, the cache dir)
    is responsible for creation and for failing fast on an unwritable target.

    The ``--home`` / ``--store-dir`` CLI flag override (precedence step 0) is
    threaded by the command layer: ``cli_args._apply_global_flags`` resolves the
    parsed flag and injects it into ``MPM_HOME`` in the process environment
    before any reader runs, so callers that do not have direct access to the
    parsed namespace still observe the flag value through the env var. Passing
    *override* directly to this helper is the equivalent in-process path and is
    used by the resolution unit tests.

    Args:
        override: An explicit mpm home path that wins over both the env var
            and the default when provided (the ``--home`` / ``--store-dir``
            flag value). ``None`` (the default) defers to the env var and the
            built-in default.

    Returns:
        A ``pathlib.Path`` to the resolved mpm home root.
    """
    if override is not None:
        return pathlib.Path(override)
    raw = os.environ.get(MPM_HOME_ENV_VAR)
    if raw:
        return pathlib.Path(raw)
    return pathlib.Path.home() / MPM_HOME_DIR_NAME


CATALOG_SOURCES_ENV_VAR = "MPM_CATALOG_SOURCES"


CATALOG_DEFAULT_BRANCH_ENV_VAR = "MPM_CATALOG_DEFAULT_BRANCH"


CATALOG_DEFAULT_BRANCH_DEFAULT = "main"


CATALOG_DEFAULT_BRANCH_AUTO = "auto"


SYMREF_HEADS_PREFIX = "refs/heads/"


SYMREF_LINE_PREFIX = "ref: "


CATALOG_DEFAULT_BRANCH_SYMREF_ABSENT_ERROR_TEMPLATE = (
    "ERROR: cannot resolve the default branch for {url}: the remote did not\n"
    "advertise a HEAD symref (ls-remote --symref returned no 'ref: refs/heads/...'\n"
    "line). Set MPM_CATALOG_DEFAULT_BRANCH or --catalog-default-branch to an\n"
    "explicit branch, or pin @<ref> on the source."
)


CATALOG_DEFAULT_BRANCH_WARN_TEMPLATE = (
    "WARNING: no ref pinned for {url}; using default branch '{branch}'. "
    "Pin @<ref> on the source to silence this warning."
)


MARKETPLACE_DIR_GLOBAL_KEY = "CLAUDE_MARKETPLACES_DIR"


ANSI_YELLOW = "\033[33m"
ANSI_RESET = "\033[0m"


MISSING_CATALOG_ERROR_TEMPLATE = (
    "ERROR: {command} requires a catalog source.\n"
    "Provide one of:\n"
    "  --catalog-source <git-url>@<ref>       # e.g. --catalog-source https://example.com/org/manifest-repo.git@main\n"
    "  MPM_CATALOG_SOURCES=<git-url>@<ref>  # set as env var (one entry per line), then re-run\n"
    "\n"
    "The CLI flag takes precedence when both are set.\n"
    "A catalog source identifies a manifest repo (a git repository whose\n"
    "repo-specs/ directory exposes installable mpm dependencies).\n"
    "See docs/catalogs-explained.md for what a manifest repo is and how to find one.\n"
    "See docs/configuration.md for the full configuration reference."
)


LIST_EMPTY_CATALOG_NOTE = "manifest repo contains 0 entries"


SEARCH_NO_MATCHES_NOTE = "no matches"


SEARCH_UNREACHABLE_SOURCE_WARN_TEMPLATE = "WARNING: skipping unreachable catalog source {source}: {reason}"


MPMENV_FILENAME = ".mpm"


REPO_RESTART_RETRIES_DEFAULT = 3


MPM_REPO_DIR_ENV = "MPM_REPO_DIR"
MPMENV_REPO_DIR_DEFAULT = ".repo"


SELFUPDATE_EMBEDDED_MESSAGE = "selfupdate is not available -- upgrade mpm instead: pipx upgrade missing-package-manager"


MPM_PYPI_PROJECT_NAME = "missing-package-manager"
MPM_PYPI_JSON_URL = "https://pypi.org/pypi/missing-package-manager/json"


MPM_UPDATE_UPGRADE_COMMAND = "pipx upgrade missing-package-manager"


MPM_SKIP_UPDATE_CHECK_ENV = "MPM_SKIP_UPDATE_CHECK"


MPM_SKIP_UPDATE_CHECK_TRUE = "1"


MPM_UPDATE_CHECK_TTL_ENV = "MPM_UPDATE_CHECK_TTL"
MPM_UPDATE_CHECK_TTL: int = _env_int(MPM_UPDATE_CHECK_TTL_ENV, 10800)
if MPM_UPDATE_CHECK_TTL <= 0:
    raise SystemExit(f"ERROR: {MPM_UPDATE_CHECK_TTL_ENV} must be a positive integer; got {MPM_UPDATE_CHECK_TTL}")


MPM_UPDATE_CONNECT_TIMEOUT_ENV = "MPM_UPDATE_CONNECT_TIMEOUT"
MPM_UPDATE_CONNECT_TIMEOUT: int = _env_int(MPM_UPDATE_CONNECT_TIMEOUT_ENV, 2)
if MPM_UPDATE_CONNECT_TIMEOUT <= 0:
    raise SystemExit(
        f"ERROR: {MPM_UPDATE_CONNECT_TIMEOUT_ENV} must be a positive integer; got {MPM_UPDATE_CONNECT_TIMEOUT}"
    )


MPM_UPDATE_READ_TIMEOUT_ENV = "MPM_UPDATE_READ_TIMEOUT"
MPM_UPDATE_READ_TIMEOUT: int = _env_int(MPM_UPDATE_READ_TIMEOUT_ENV, 3)
if MPM_UPDATE_READ_TIMEOUT <= 0:
    raise SystemExit(f"ERROR: {MPM_UPDATE_READ_TIMEOUT_ENV} must be a positive integer; got {MPM_UPDATE_READ_TIMEOUT}")


MPM_UPDATE_BODY_SIZE_CAP_ENV = "MPM_UPDATE_BODY_SIZE_CAP"
MPM_UPDATE_BODY_SIZE_CAP: int = _env_int(MPM_UPDATE_BODY_SIZE_CAP_ENV, 200 * 1024)
if MPM_UPDATE_BODY_SIZE_CAP <= 0:
    raise SystemExit(
        f"ERROR: {MPM_UPDATE_BODY_SIZE_CAP_ENV} must be a positive integer; got {MPM_UPDATE_BODY_SIZE_CAP}"
    )


MPM_UPDATE_CHECK_CACHE_SUBDIR = "update-check"


MPM_UPDATE_CHECK_VERSION_FILENAME = "latest.txt"


ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"


MPM_UPDATE_ALERT_TEMPLATE = "A new release of mpm is available: {current} -> {latest}.\nRun '{command}' to upgrade."


MPM_UPDATE_NO_INTERNET_NOTICE = "mpm: no internet access -- could not check for updates."


GIT_RETRY_COUNT_ENV_VAR = "MPM_GIT_RETRY_COUNT"
GIT_RETRY_DELAY_ENV_VAR = "MPM_GIT_RETRY_DELAY"
GIT_RETRY_COUNT_DEFAULT = 3
GIT_RETRY_DELAY_DEFAULT = 1


GIT_AUTH_ERROR_PATTERNS = ("Authentication", "Permission denied")


MPM_GIT_LS_REMOTE_TIMEOUT: int = _env_int("MPM_GIT_LS_REMOTE_TIMEOUT", 30)


INSTALL_LOCK_FILENAME = ".mpm-install.lock"


MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS: int = _env_int("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", 30)
if MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS <= 0:
    raise SystemExit(
        f"ERROR: MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS must be a positive integer; "
        f"got {MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS}"
    )


MPM_COMPLETION_CACHE_DIR = "completion-cache"


MPM_COMPLETION_ERRORS_REPORT_LIMIT: int = _env_int("MPM_COMPLETION_ERRORS_REPORT_LIMIT", 5)
if MPM_COMPLETION_ERRORS_REPORT_LIMIT <= 0:
    raise SystemExit(
        f"ERROR: MPM_COMPLETION_ERRORS_REPORT_LIMIT must be a positive integer; "
        f"got {MPM_COMPLETION_ERRORS_REPORT_LIMIT}"
    )


MPM_COMPLETION_CACHE_TTL = 300


MPM_COMPLETION_TIMEOUT = 2


MPM_COMPLETION_REFRESH_BG = 1


MPM_COMPLETION_REFRESH_BG_ENV = "MPM_COMPLETION_REFRESH_BG"


MPM_COMPLETION_ENABLED = 1


MPM_ACCESSED_AT_COALESCE_SEC = 60


MPM_COMPLETION_LOG_ENV = "MPM_COMPLETION_LOG"


MPM_COMPLETION_ERRORS_LOG_FILENAME = "completion-errors.log"


MPM_STATIC_COMPLETION_SEARCH_PATHS: tuple[tuple[str, str], ...] = (
    ("bash", os.path.expanduser("~/.local/share/bash-completion/completions/mpm")),
    ("bash", "/etc/bash_completion.d/mpm"),
    ("zsh", os.path.expanduser("~/.zsh/completions/_mpm")),
    ("zsh", "/usr/local/share/zsh/site-functions/_mpm"),
    ("zsh", "/usr/share/zsh/vendor-completions/_mpm"),
)


MPM_STALE_COMPLETION_SCRIPT_WARNING = (
    "Stale {shell_name} completion script: {path} does not match the output of "
    "'mpm completion {shell_name}'. Re-run 'mpm completion {shell_name} > {path}' "
    "to update it."
)


MPM_HOME_CACHE_DIR_MODE = 0o700


MPM_CACHE_PRUNE_AGE_DAYS: int = _env_int("MPM_CACHE_PRUNE_AGE_DAYS", 30)
if MPM_CACHE_PRUNE_AGE_DAYS <= 0:
    raise SystemExit(f"ERROR: MPM_CACHE_PRUNE_AGE_DAYS must be a positive integer; got {MPM_CACHE_PRUNE_AGE_DAYS}")


MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH: int = _env_int("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", 4)
if MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH <= 0:
    raise SystemExit(
        f"ERROR: MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH must be a positive integer; "
        f"got {MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH}"
    )


MPM_DOCTOR_STALE_LOCK_AGE_HOURS: int = _env_int("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", 1)
if MPM_DOCTOR_STALE_LOCK_AGE_HOURS <= 0:
    raise SystemExit(
        f"ERROR: MPM_DOCTOR_STALE_LOCK_AGE_HOURS must be a positive integer; got {MPM_DOCTOR_STALE_LOCK_AGE_HOURS}"
    )


MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS: int = _env_int("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", 160)
if MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS <= 0:
    raise SystemExit(
        f"ERROR: MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS must be a positive integer; "
        f"got {MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS}"
    )


_MPM_RESOLVE_TIMEOUT_ENV = "MPM_RESOLVE_TIMEOUT"


_MPM_RESOLVE_TIMEOUT_DEFAULT = 30


NO_COLOR_ENV = "NO_COLOR"


_NO_COLOR_ACTIVE: bool = False


COMPLETION_MAX_ENTRY_LEN = 128


COMPLETION_UNSAFE_CHARS: frozenset[str] = frozenset(" \t\n\r;|&$`")


SHELL_METACHARS: frozenset[str] = frozenset("|&;<>(){}$`\\\"'")


RECOMMENDED_CHAR_RE = re.compile(r"^[a-zA-Z0-9_-]*$")


MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE = RECOMMENDED_CHAR_RE


MPM_TREE_NO_FILTER_THRESHOLD: int = _env_int("MPM_TREE_NO_FILTER_THRESHOLD", 20)


MPM_LIST_LIMIT: int = _env_int("MPM_LIST_LIMIT", 50)


MPM_SEARCH_MAX_WORKERS: int = _env_int("MPM_SEARCH_MAX_WORKERS", 8)
if MPM_SEARCH_MAX_WORKERS <= 0:
    raise ValueError(f"ERROR: MPM_SEARCH_MAX_WORKERS must be a positive integer; got {MPM_SEARCH_MAX_WORKERS}")


MPM_MPM_FILE_ENV = "MPM_MPM_FILE"


MPM_LOCK_FILE = "MPM_LOCK_FILE"


MPM_ALLOW_INSECURE_REMOTES = "MPM_ALLOW_INSECURE_REMOTES"


MPM_MPM_FILE_DEFAULT = "./.mpm"


MPM_HEADER_GITBASE = "GITBASE=<YOUR_GIT_ORG_BASE_URL>"
MPM_HEADER_CLAUDE_MARKETPLACES_DIR = "CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces"


REVISION_REF_PREFIX_TAGS = "refs/tags/"
REVISION_REF_PREFIX_HEADS = "refs/heads/"
REVISION_REF_PREFIX_REMOTES = "refs/remotes/origin/"


REVISION_REF_PREFIXES: tuple[str, ...] = (
    REVISION_REF_PREFIX_REMOTES,
    REVISION_REF_PREFIX_HEADS,
    REVISION_REF_PREFIX_TAGS,
)


REVISION_CLASSIFICATION_VERSION = "version"


REVISION_CLASSIFICATION_BRANCH = "branch"


MPM_OUTDATED_FORMAT = "MPM_OUTDATED_FORMAT"


MPM_OUTDATED_FORMAT_DEFAULT = "table"


MPM_OUTDATED_FORMAT_JSON = "json"


MPM_WHY_FORMAT_JSON = "json"


MPM_OUTDATED_JSON_INDENT: int = _env_int("MPM_OUTDATED_JSON_INDENT", 2)


BRANCH_SHA_TRUNCATION_LENGTH = 12


SHA1_HEX_LENGTH = 40
SHA256_HEX_LENGTH = 64


MPM_WHY_FORMAT = "MPM_WHY_FORMAT"


MPM_WHY_FORMAT_DEFAULT = "text"


MPM_WHY_JSON_INDENT: int = _env_int("MPM_WHY_JSON_INDENT", 2)
if MPM_WHY_JSON_INDENT < 0:
    raise SystemExit(f"ERROR: MPM_WHY_JSON_INDENT must be a non-negative integer; got {MPM_WHY_JSON_INDENT}")


MPM_LIST_OUTPUT_FORMAT = "MPM_LIST_OUTPUT_FORMAT"


MPM_LIST_OUTPUT_FORMAT_TABLE = "table"


MPM_LIST_OUTPUT_FORMAT_JSON = "json"


MPM_LIST_OUTPUT_FORMAT_DEFAULT = MPM_LIST_OUTPUT_FORMAT_TABLE


MPM_LIST_OUTPUT_FORMAT_CHOICES: tuple[str, ...] = (
    MPM_LIST_OUTPUT_FORMAT_TABLE,
    MPM_LIST_OUTPUT_FORMAT_JSON,
)


MPM_LIST_JSON_INDENT: int = _env_int("MPM_LIST_JSON_INDENT", 2)
if MPM_LIST_JSON_INDENT < 0:
    raise SystemExit(f"ERROR: MPM_LIST_JSON_INDENT must be a non-negative integer; got {MPM_LIST_JSON_INDENT}")


MPM_LIST_STATUS_INSTALLED = "installed"


MPM_LIST_STATUS_NOT_INSTALLED = "not-installed"


MPM_LIST_STATUS_ORPHAN = "orphan"


MPM_LIST_STATUS_CHOICES: tuple[str, ...] = (
    MPM_LIST_STATUS_INSTALLED,
    MPM_LIST_STATUS_NOT_INSTALLED,
    MPM_LIST_STATUS_ORPHAN,
)


MPM_LIST_SCOPE_DIRECT = "direct"


MPM_LIST_SCOPE_TRANSITIVE = "transitive"


MPM_LIST_COLUMN_SOURCE = "SOURCE"


MPM_LIST_COLUMN_REF = "REF"


MPM_LIST_COLUMN_STATUS = "STATUS"


MPM_LIST_REF_UNRESOLVED = "-"


MPM_LIST_TREE_INDENT = "  "


MPM_LIST_NO_SOURCES_NOTE = "no dependencies declared in .mpm (add one with 'mpm add')"


MPM_LIST_NO_LOCKFILE_NOTE = "no .mpm.lock found -- declared sources are not installed yet (run 'mpm install')"


MPM_CATALOG_AUDIT_VALID_CHECKS: frozenset[str] = frozenset(
    {
        "metadata",
        "source-name-derivation",
        "entry-name-uniqueness",
        "remote-url",
        "tag-format",
    }
)


MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS: int = _env_int("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", 3600)
if MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS <= 0:
    raise SystemExit(
        f"ERROR: MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS must be a positive integer; "
        f"got {MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS}"
    )


MPM_CATALOG_AUDIT_CACHE_SUBDIR = "catalog-audit"


MPM_CATALOG_AUDIT_FORMAT_ENV = "MPM_CATALOG_AUDIT_FORMAT"


MPM_CATALOG_AUDIT_FORMAT_DEFAULT = "text"


MPM_CATALOG_AUDIT_FORMAT_JSON = "json"


MPM_CATALOG_METADATA_REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "display-name",
    "description",
    "version",
)


MPM_CATALOG_METADATA_RECOMMENDED_FIELDS: tuple[str, ...] = (
    "type",
    "owner-name",
    "owner-email",
    "keywords",
)


MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT: int = _env_int("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", 50)
if MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT <= 0:
    raise SystemExit(
        f"ERROR: MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT must be a positive integer; "
        f"got {MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT}"
    )


MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE = (
    "{remaining} additional non-PEP-440 tag(s) not listed above. "
    "Run 'mpm catalog audit --check tag-format' for the full list."
)


MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE = "strict mode: {count} warning(s) treated as errors"


MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE = (
    "Legacy catalog/ directory detected; this directory is unused by "
    "mpm >= {version} and should be deleted; "
    "see docs/migration-to-add.md"
)


FINDING_SEVERITY_OK = "ok"
FINDING_SEVERITY_FAIL = "fail"
FINDING_SEVERITY_INFO = "info"


FINDING_PREFIX_OK = "[ok]"
FINDING_PREFIX_FAIL = "[fail]"
FINDING_PREFIX_INFO = "[info]"


WHY_SCOPE_TOP_LEVEL = "top_level"


WHY_SCOPE_TRANSITIVE = "transitive"


MPM_WHY_SUGGEST_MAX_DISTANCE: int = _env_int("MPM_WHY_SUGGEST_MAX_DISTANCE", 3)
if MPM_WHY_SUGGEST_MAX_DISTANCE < 0:
    raise SystemExit(
        f"ERROR: MPM_WHY_SUGGEST_MAX_DISTANCE must be a non-negative integer; got {MPM_WHY_SUGGEST_MAX_DISTANCE}"
    )


MPM_WHY_SUGGEST_TOP_N: int = _env_int("MPM_WHY_SUGGEST_TOP_N", 3)
if MPM_WHY_SUGGEST_TOP_N < 0:
    raise SystemExit(f"ERROR: MPM_WHY_SUGGEST_TOP_N must be a non-negative integer; got {MPM_WHY_SUGGEST_TOP_N}")


MPM_COMPLETER_COMMAND_PREFIX = "__complete"
