# Configuration (.mpm)

## Global options

The following flags are accepted by every `mpm` command as global
options placed before the subcommand name
(e.g., `mpm --quiet install`):

| Flag          | Description                                  |
|---------------|----------------------------------------------|
| `--quiet`     | Suppress all output except errors. Sets the  |
|               | root logger to WARNING level.                |
| `--verbose`   | Enable debug-level output. Sets the root     |
|               | logger to DEBUG level.                       |
| `--no-color`  | Disable ANSI color output unconditionally.   |

### Mutual exclusion: --quiet and --verbose

`--quiet` and `--verbose` are mutually exclusive. Passing both flags
at the same time causes argparse to exit immediately with a non-zero
code and an error message on stderr. There is no fallback or silent
suppression -- this is a hard error per spec Section 7.

```bash
# ERROR: argument --verbose: not allowed with argument --quiet
mpm --quiet --verbose install .mpm
```

### Color output: --no-color and the NO\_COLOR environment variable

Color output is controlled by the following precedence chain
(highest wins):

1. `--no-color` flag -- always disables color when passed, regardless
   of the `NO_COLOR` environment variable or TTY state.
2. `NO_COLOR` environment variable -- when set to any non-empty value,
   disables color output following the <https://no-color.org>
   convention.
3. TTY auto-detection -- color is enabled by default when stdout is a
   TTY and neither of the above conditions applies.

```bash
# Disable color via flag (highest precedence)
mpm --no-color install .mpm

# Disable color via environment variable
NO_COLOR=1 mpm install .mpm

# --no-color wins even when NO_COLOR is empty
NO_COLOR= mpm --no-color install .mpm
```

The `.mpm` file is a shell-compatible KEY=VALUE configuration file
that drives the MPM lifecycle.

## Format

```properties
# Comments start with #
KEY=VALUE
KEY_WITH_EXPANSION=${HOME}/.some-path
```

- Lines starting with `#` are comments
- Blank lines are ignored
- Lines without `=` are ignored
- Only the first `=` splits key from value (values may contain `=`)
- Trailing whitespace is trimmed

## Shell Variable Expansion

Values can reference environment variables using `${VAR}` syntax:

```properties
CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces
```

If the referenced variable is not set in the environment, parsing
fails with a descriptive error.

## Placeholder Validation

`mpm install` scans the `.mpm` file for unresolved template
placeholders **before** running `repo envsubst`. Any value matching
the regex `<[A-Z_|]+>` is treated as an unfilled placeholder and
causes an immediate hard failure.

### What triggers the check

The pattern `<[A-Z_|]+>` matches angle-bracket-delimited tokens
containing only uppercase ASCII letters, underscores, and pipe
characters. Examples that trigger the check:

- `<YOUR_GIT_ORG_BASE_URL>`
- `<TRUE_OR_FALSE>`
- `<GITBASE|OTHER>`

Values written by `mpm add` in older releases sometimes contained
these literal strings as stand-in prompts that users were expected to
replace before running `mpm install`.

### Error format

When one or more placeholders are detected, `mpm install` exits
with a non-zero code and prints each finding to stderr:

```text
ERROR: .mpm contains unresolved placeholders
       -- resolve each before running mpm install
  Line 4: MPM_SOURCE_build_GITBASE=<YOUR_GIT_ORG_BASE_URL>
```

Each line reports the line number and the full `KEY=VALUE` line as it
appears in the `.mpm` file so the operator can locate it
immediately.

### Remediation

Three paths are available, listed in decreasing order of preference:

1. **Re-run `mpm add`** -- `mpm add` auto-derives the per-dependency
   `MPM_SOURCE_<alias>_GITBASE` from the catalog-source URL. Re-running
   `mpm add` overwrites the stale placeholder lines without manual
   editing.

2. **Set the corresponding environment variable** -- if the
   placeholder represents a value that should come from the
   environment, set the variable before invoking `mpm install`:

   ```bash
   export GITBASE=https://github.com/your-org
   mpm install .mpm
   ```

3. **Hand-edit `.mpm`** -- open the file and replace each
   placeholder with a concrete value:

   ```properties
   # Before (triggers error):
   MPM_SOURCE_build_GITBASE=<YOUR_GIT_ORG_BASE_URL>

   # After (valid):
   MPM_SOURCE_build_GITBASE=https://github.com/your-org
   ```

### Worked example

Given a `.mpm` file with the following content at line 4:

```properties
# .mpm
MPM_SOURCE_build_URL=${MPM_SOURCE_build_GITBASE}/build.git
MPM_SOURCE_build_REF=main
MPM_SOURCE_build_PATH=repo-specs/meta.xml
MPM_SOURCE_build_GITBASE=<YOUR_GIT_ORG_BASE_URL>
```

Running `mpm install .mpm` before resolving the placeholder
produces:

```text
ERROR: .mpm contains unresolved placeholders
       -- resolve each before running mpm install
  Line 5: MPM_SOURCE_build_GITBASE=<YOUR_GIT_ORG_BASE_URL>
```

After correcting the line:

```properties
MPM_SOURCE_build_GITBASE=https://github.com/your-org
```

`mpm install .mpm` proceeds normally.

## Environment Variable Reference

The sections below group every environment variable by function.
Each entry shows the variable name, its default, and a description.
Cross-references:

- Shell completion cache layout:
  [docs/shell-completion.md](shell-completion.md)
- Lockfile precedence and format:
  [docs/lockfile.md](lockfile.md)
- Git authentication setup:
  [docs/git-auth-setup.md](git-auth-setup.md)

---

### Catalog source

**No default catalog source.** Post-bootstrap-deprecation, the
bundled fallback catalog has been removed. One of `--catalog-source`
or `MPM_CATALOG_SOURCES` is required for catalog-requiring commands.
There is no rc-file mechanism; configuration is explicit via CLI flag
or environment variable only.

**`MPM_CATALOG_SOURCES`** (default: unset) -- One or more catalog
repositories, each in `url[@ref]` form, given as a newline-delimited
list (one entry per line). Specifies the catalog repositories used by
catalog-requiring commands. A command that resolves a catalog uses the
single configured entry; `--catalog-source` overrides it.

```bash
export MPM_CATALOG_SOURCES=\
  https://github.com/example-org/mpm-catalog.git@main
mpm search
```

**Precedence (highest to lowest):**

1. `--catalog-source` CLI flag
2. `MPM_CATALOG_SOURCES` environment variable

These are the only two layers. There is no lockfile or `.mpm`
fallback: the schema-v5 lockfile carries no catalog block, and `.mpm`
records no catalog source.

**Optional `@ref` and default-branch resolution.** The `@ref` portion of a
catalog source is optional (`url[@ref]`). When a catalog source is given
without `@ref`, `mpm add` and `mpm search` resolve a default branch and
print a yellow `WARNING` naming the branch and suggesting you pin `@<ref>` to
silence it. The branch is chosen by this precedence (highest to lowest):

1. An inline `@ref` on the source (when present, no default-branch resolution
   happens).
2. The `--catalog-default-branch <name>` CLI flag (available on `mpm add`
   and `mpm search`).
3. The `MPM_CATALOG_DEFAULT_BRANCH` environment variable (default: `main`).
4. The literal value `auto`, which resolves the remote's `HEAD` symref via
   `git ls-remote --symref`.

**`MPM_CATALOG_DEFAULT_BRANCH`** (default: `main`) -- The default branch
used by `mpm add` / `mpm search` when a catalog source omits `@ref` and
no `--catalog-default-branch` flag is passed. Set it to `auto` to resolve the
remote's `HEAD` symref instead of assuming `main`.

When neither source is set, a catalog-requiring command (`mpm search`,
`mpm add`, `mpm outdated`, `mpm why`, `mpm catalog audit`) exits
with a hard error and remediation text. See
[docs/catalogs-explained.md](catalogs-explained.md) for details.

**`mpm install` is hermetic.** Install never reads a catalog source: it
does not accept `--catalog-source`, and a populated `MPM_CATALOG_SOURCES`
is ignored. Install is driven solely by the committed `.mpm` and
`.mpm.lock`, so it neither resolves nor records a catalog source and
never raises a catalog-source mismatch.

See [docs/architecture.md](architecture.md) for the full precedence
logic.

**Shell-profile leakage warning.** If `MPM_CATALOG_SOURCES` is set
in a shell profile (e.g., `~/.bashrc`, `~/.zshrc`, `~/.profile`),
it leaks into every shell session including unrelated workspaces.
A catalog source set for project A silently applies to project B
if both are opened in the same shell. To avoid cross-workspace
contamination, set `MPM_CATALOG_SOURCES` in workspace-specific
tooling (e.g., a `.envrc` loaded by direnv) rather than in shell
profiles. Alternatively, always pass `--catalog-source` explicitly
on the command line.

---

### Resolver behavior

These variables control how the resolver fetches, resolves, and
validates dependency information.

**`MPM_RESOLVE_TIMEOUT`** (default: `30`) -- Timeout in seconds for
each `git ls-remote` call in `mpm install`, `mpm outdated`,
`mpm why`, and `mpm doctor`. Bounded per call; not a global wall
clock. Defined in `src/mpm_cli/constants.py`.

**`MPM_MANIFEST_FILE`** (default: `./.mpm`) -- Default `.mpm` file
path. It supplies the default target for `mpm add` / `mpm remove`
writes and the default `--mpm-file` value for the commands that accept
that flag (`mpm add`, `mpm remove`, `mpm doctor`). On `mpm install`
and `mpm validate lockfile` the `.mpm` path is given as a positional
argument (these commands do not expose a `--mpm-file` flag). The
`--mpm-file` CLI flag takes precedence over this variable when both are
set.

**`MPM_LIST_FORMAT`** (default: `names`) -- Default output format
for `mpm search`. Supported values: `names`, `json`. Overridden by
`--format` CLI flag.

**`MPM_LIST_LIMIT`** (default: `50`) -- Default cap on the number
of entries returned by `mpm search -A`. Overridden by
`--limit N` / `--no-limit` CLI flags.

**`MPM_TREE_NO_FILTER_THRESHOLD`** (default: `20`) -- Entry count
above which `mpm search --tree` requires a filter argument. Without a
filter, `mpm search --tree` exits with an error suggesting `--regex`,
`<substring>`, or `--max-depth 0`. Override with
`--no-filter-required`.

**`MPM_LIST_OUTPUT_FORMAT`** (default: `table`) -- Default output
format for `mpm list` (the declared-vs-installed inventory command).
Supported values: `table`, `json`. Overridden by the `--format` CLI
flag. Distinct from `MPM_LIST_FORMAT` above, which configures
`mpm search`'s output.

**`MPM_LIST_JSON_INDENT`** (default: `2`) -- Number of spaces per
indentation level in JSON output from `mpm list --format json`. Must
be a non-negative integer parseable by Python `int()`.

**`MPM_OUTDATED_FORMAT`** (default: `table`) -- Default output
format for `mpm outdated`. Currently only `table` is supported.
Overridden by `--format` CLI flag.

**`MPM_WHY_FORMAT`** (default: `text`) -- Default output format for
`mpm why`. Supported values: `text` (human-readable arrow-separated
chains) and `json` (machine-readable JSON array). Overridden by
`--format` CLI flag.

**`MPM_WHY_JSON_INDENT`** (default: `2`) -- Number of spaces per
indentation level in JSON output from `mpm why --format json`. Must
be a non-negative integer parseable by Python `int()`.

**`MPM_WHY_SUGGEST_MAX_DISTANCE`** (default: `3`) -- Maximum
Levenshtein edit distance for closest-match suggestions when
`mpm why` cannot find the requested argument. Must be a
non-negative integer.

**`MPM_WHY_SUGGEST_TOP_N`** (default: `3`) -- Maximum number of
closest-match suggestions displayed on not-found. Results are sorted
ascending by edit distance, ties broken lexicographically. Must be a
non-negative integer.

**`MPM_ALLOW_INSECURE_REMOTES`** (default: unset) -- When set to
exactly `1`, disables the insecure-remote URL security check in
`mpm install`. All remote URL schemes (HTTP, `file://`, `git://`,
etc.) are accepted without error. Any value other than `1` is treated
as unset. See the security rationale below.

#### MPM\_ALLOW\_INSECURE\_REMOTES -- security rationale

mpm enforces a trust model (spec Section 3.6) that requires all
`<remote>` fetch URLs in resolved manifests to use HTTPS or SSH. Plain
HTTP, `file://`, `git://`, and other unencrypted schemes are rejected
by default because they expose dependency resolution to network-level
interception and tampering.

**Allowed unconditionally:**

- `https://...` -- encrypted, authenticated.
- `git@host:org/repo.git` -- SCP-style SSH; encrypted, key-authed.
- `ssh://...` -- explicit SSH; encrypted, key-authenticated.

**Rejected by default (allowed only with `MPM_ALLOW_INSECURE_REMOTES=1`):**

- `http://...` -- unencrypted; interceptable in transit.
- `file://...` -- local path; no network-level guarantees.
- Any other scheme (`git://`, `ftp://`, custom schemes, empty URL).

**Override:** Set `MPM_ALLOW_INSECURE_REMOTES=1` to disable the
check. Only the exact string `1` enables it. Values such as `true`,
`yes`, `on`, or `0` do NOT enable the override.

```bash
# Default: HTTP remote rejected
mpm install .mpm  # exits 1 if any <remote> uses http://

# Override: HTTP remote accepted
MPM_ALLOW_INSECURE_REMOTES=1 mpm install .mpm
```

The check also runs on the lockfile-consistent replay path: even if a
lockfile was recorded with an HTTP URL, `mpm install` rejects it.
See [docs/lockfile.md](lockfile.md) for details on replay enforcement.

---

### File paths

These variables control where mpm reads and writes its key files.

**`MPM_LOCK_FILE`** (default: derived) -- Override the lock file
path. When set to a non-empty value, mpm reads and writes the lock
file at this path instead of the default derived from `--mpm-file`
(i.e. `<mpm-file-path>.lock`). The `--lock-file` CLI flag takes
precedence when both are set. An empty-string value is treated as
unset. See [docs/lockfile.md](lockfile.md) for the full precedence
chain.

**Lock file resolution order (highest wins):**

1. `--lock-file` CLI flag
2. `MPM_LOCK_FILE` environment variable
3. Default derived from `--mpm-file`: `./.mpm` becomes
   `./.mpm.lock`; `./alt.mpm` becomes `./alt.mpm.lock`.

**`MPM_HOME`** (default: `~/.mpm-home`) -- Single root directory that
subsumes the former per-user cache-dir override and the former
per-workspace artifact-dir override. The cache subtree lives at
`${MPM_HOME}/cache/` and the store subtree at `${MPM_HOME}/store/`.
An unwritable resolved home fails fast with an actionable message
(no silent relocation). Owner-private modes `0700` / `0600` still apply
to cache files. See
[Shell Completion -- Cache layout](shell-completion.md#cache-layout).

**`MPM_HOME` resolution order (highest wins):**

1. `--home` / `--store-dir <path>` global CLI flag (when supplied).
2. `MPM_HOME` environment variable (when non-empty).
3. `~/.mpm-home` -- default when the env var is unset and no flag is given.

The `--home` (alias `--store-dir`) flag is a global option accepted on
every command; when supplied it overrides `MPM_HOME` for that
invocation.

```bash
# Store cache and artifacts under a non-default home
export MPM_HOME=/tmp/my-mpm-home

# Or per-invocation, overriding the env var and the default
mpm --home /tmp/my-mpm-home install
```

---

### Lockfile

These variables control lockfile-related behaviour. See
[docs/lockfile.md](lockfile.md) for the full lockfile reference
including format, semantics, schema migration, and conflict
resolution.

**`MPM_GIT_LS_REMOTE_TIMEOUT`** (default: `30`) -- Timeout in
seconds for `git ls-remote` calls used by SHA reachability checks and
ref resolution in the install engine. Defined in
`src/mpm_cli/constants.py`.

The `MPM_RESOLVE_TIMEOUT` variable (documented under
[Resolver behavior](#resolver-behavior)) also governs `git ls-remote`
calls during lockfile resolution.

---

### Concurrency

`mpm install`, `mpm add`, `mpm remove`, `mpm marketplace`, and
`mpm doctor --refresh-completion-cache` use an exclusive file lock
(`fcntl.flock(LOCK_EX)`) on a `.mpm-install.lock` to serialize concurrent
invocations against the same `.mpm` file. The lock lives in the shared
`MPM_HOME` store under `${MPM_HOME}/store/.locks/<address>/`, keyed by a
hash of the resolved `.mpm` path, so concurrent edits to the same file
serialize while the project directory stays clean: the working directory holds
only `.mpm` (and `.mpm.lock` after the first install), never a
`.mpm-data/` lock directory. The kernel releases the lock on process exit
(graceful or crash); a leftover `.mpm-install.lock` file on disk is harmless.

The following variables control how `mpm doctor --prune-cache`
handles stale lock files and cache entries.

**`MPM_CACHE_PRUNE_AGE_DAYS`** (default: `30`) -- Files under
`${MPM_HOME}/cache` whose last-access time is older than this many
days are removed by `mpm doctor --prune-cache`. Reports what was
pruned. Must be a positive integer. Values of 0 or below are rejected
with a clear error at startup.

**`MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH`** (default: `4`) --
Maximum directory depth below the current working directory that
`mpm doctor --prune-cache` searches for stale
`.mpm-data/.mpm-install.lock` files. Bounds filesystem traversal
to prevent wandering the entire filesystem in a misconfigured
workspace. Must be a positive integer.

**`MPM_DOCTOR_STALE_LOCK_AGE_HOURS`** (default: `1`) -- Minimum
age in hours for a `.mpm-data/.mpm-install.lock` file to be
considered stale by `mpm doctor --prune-cache`. Stale locks are
reported as advisory findings only -- doctor never deletes them.
`fcntl.flock` self-cleans on process exit, so a leftover file is
harmless. Must be a positive integer.

```bash
# Use the default 30-day threshold
mpm doctor --prune-cache

# Prune files not accessed in the last 7 days
MPM_CACHE_PRUNE_AGE_DAYS=7 mpm doctor --prune-cache

# Restrict stale-lock scan to 2 levels deep
MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH=2 mpm doctor --prune-cache

# Treat locks older than 4 hours as stale
MPM_DOCTOR_STALE_LOCK_AGE_HOURS=4 mpm doctor --prune-cache
```

---

### Completion cache

These variables control the shell-completion cache. See
[docs/shell-completion.md](shell-completion.md) for the full cache
layout and lifecycle description.

**`MPM_COMPLETION_ENABLED`** (default: `1`) -- When set to `0`,
all shell completion helpers return an empty candidate list
immediately without invoking the `mpm` subprocess. Set to `0` to
disable dynamic completion lookups globally (for example in
restricted environments or when completion latency is a concern). Any
value other than `0` is treated as enabled.

```bash
# Disable all mpm completion lookups
export MPM_COMPLETION_ENABLED=0

# Re-enable (default behaviour)
export MPM_COMPLETION_ENABLED=1
```

**`MPM_COMPLETION_TIMEOUT`** (default: `2`) -- Timeout in seconds
applied to each `mpm __complete_*` subprocess call made by the
shell completion preamble helpers. When `timeout`(1) is available on
`$PATH`, it wraps the subprocess call with this value. When
`timeout`(1) is not available, mpm's own internal subprocess
timeout (also bounded by this variable) applies. Must be a positive
integer.

```bash
# Use a 5-second timeout for completion lookups
export MPM_COMPLETION_TIMEOUT=5

# Use the default 2-second timeout
unset MPM_COMPLETION_TIMEOUT
```

**`MPM_COMPLETION_REFRESH_BG`** (default: `1`) -- When set to `1`,
a background subprocess is spawned after a stale-but-present cache
read to refresh the cache asynchronously. Set to `0` to disable
background refresh (completions then become stale until the TTL
expires and the next Tab press triggers a synchronous fetch).

```bash
# Disable background refresh
export MPM_COMPLETION_REFRESH_BG=0
```

**`MPM_COMPLETION_CACHE_TTL`** (default: `300`) -- Cache
time-to-live in seconds. A cached completion result whose
`fetched_at.txt` is within this age is returned immediately without a
remote fetch. When the age exceeds the TTL, a background refresh is
spawned (if `MPM_COMPLETION_REFRESH_BG=1`).

```bash
# Extend TTL to 10 minutes
export MPM_COMPLETION_CACHE_TTL=600
```

**`MPM_ACCESSED_AT_COALESCE_SEC`** (default: `60`) -- Coalescing
window in seconds for `accessed_at.txt` updates. A read that occurs
within this many seconds of the last `accessed_at` write does not
rewrite the file. This bounds I/O during rapid tab-pressing without
losing access-time tracking for cache pruning.

```bash
# Coalesce accessed_at writes within a 5-minute window
export MPM_ACCESSED_AT_COALESCE_SEC=300
```

**`MPM_COMPLETION_LOG`** (default: `${MPM_HOME}/cache/completion-errors.log`)
-- Path to the append-only completion-errors log. When unset, errors
are written to `completion-errors.log` directly under
`${MPM_HOME}/cache`. The file is created with mode `0600` and its
parent directory with mode `0700`.

```bash
# Redirect completion errors to a custom path
export MPM_COMPLETION_LOG=/var/log/mpm-completion-errors.log
```

**`MPM_COMPLETION_ERRORS_REPORT_LIMIT`** (default: `5`) -- Maximum
number of completion error lines surfaced by `mpm doctor` (subcheck
7). Must be a positive integer.

---

### Update check

mpm performs a best-effort PyPI check for a newer `missing-package-manager` release
and prints an upgrade hint when one is available. The check is cached and
never blocks a command on failure. When an upgrade is available the banner
is yellow with the current (installed) version in red and the latest
version in green. When a check is attempted but the network is unreachable,
a red `no internet access -- could not check for updates` notice is printed
to stderr at most once per cache window.

**`MPM_SKIP_UPDATE_CHECK`** (default: unset) -- When set to exactly `1`,
the PyPI update-available check is skipped entirely. The global
`--no-update-check` flag has the same effect for a single invocation.

```bash
# Skip the update check for one run
mpm --no-update-check install .mpm

# Skip it for the whole session
export MPM_SKIP_UPDATE_CHECK=1
```

**`MPM_UPDATE_CHECK_TTL`** (default: `10800`) -- Seconds the cached
"latest version" result is considered fresh before the next check refetches
it (default 3 hours). Must be a positive integer.

**`MPM_UPDATE_CONNECT_TIMEOUT`** (default: `2`) -- Connect timeout in
seconds for the PyPI request. Must be a positive integer.

**`MPM_UPDATE_READ_TIMEOUT`** (default: `3`) -- Read timeout in seconds
for the PyPI request. Must be a positive integer.

**`MPM_UPDATE_BODY_SIZE_CAP`** (default: `204800`) -- Maximum number of
response bytes read from the PyPI JSON endpoint. Must be a positive
integer.

---

### Retry policy

mpm retries `git ls-remote` calls on transient errors. Auth-failure
patterns skip retries immediately; see
[docs/git-auth-setup.md](git-auth-setup.md) for authentication
configuration. The auth-error patterns (`GIT_AUTH_ERROR_PATTERNS`) are
internal constants, not environment variables.

**`MPM_GIT_RETRY_COUNT`** (default: `3`) -- Number of
`git ls-remote` retry attempts on transient errors. Auth-error
patterns (e.g., "Authentication", "Permission denied") skip retries
regardless of this value. Must be a non-negative integer. Defined in
`src/mpm_cli/constants.py`.

**`MPM_GIT_RETRY_DELAY`** (default: `1`) -- Seconds to wait
between `git ls-remote` retry attempts. Must be a non-negative
integer. Defined in `src/mpm_cli/constants.py`.

```bash
# Increase retry attempts for unreliable networks
MPM_GIT_RETRY_COUNT=5 mpm install .mpm

# Increase wait between retries
MPM_GIT_RETRY_DELAY=3 mpm install .mpm
```

---

## Multi-Source Groups

Sources are alias-keyed: each is auto-discovered from a
`MPM_SOURCE_<alias>_URL` variable and processed in alphabetical order
by alias. Each source block carries the required structural suffixes
`_{URL,REF,PATH,NAME}`, plus an open, optional set of per-dependency
env-var suffixes (`MPM_SOURCE_<alias>_<VAR>`) used to resolve `${VAR}`
placeholders in that source's manifest at install time:

```properties
MPM_SOURCE_build_URL=${MPM_SOURCE_build_GITBASE}/build-repo.git
MPM_SOURCE_build_REF=main
MPM_SOURCE_build_PATH=repo-specs/meta.xml
MPM_SOURCE_build_NAME=build
MPM_SOURCE_build_GITBASE=https://github.com/org

MPM_SOURCE_marketplaces_URL=${MPM_SOURCE_marketplaces_GITBASE}/mp-repo.git
MPM_SOURCE_marketplaces_REF=main
MPM_SOURCE_marketplaces_PATH=repo-specs/marketplaces.xml
MPM_SOURCE_marketplaces_NAME=marketplaces
MPM_SOURCE_marketplaces_GITBASE=https://github.com/org
```

Each source requires the `_URL`, `_REF`, `_PATH`, and `_NAME` suffixed
variables. The per-dependency env-var suffixes (`_GITBASE` above, or any
other `${VAR}` name) are OPTIONAL and open-ended: `mpm add` writes one
line per `${VAR}` the entry's manifest actually references (the `GITBASE`
var is auto-derived from the source URL; every other var name is written
empty for you to fill in), and writes none when the manifest references no
`${VAR}`. At install time each declared var is injected into that source's
manifest substitution; an unresolved `${VAR}` after substitution fails the
install fast, naming the `MPM_SOURCE_<alias>_<VAR>` key to set.

---

## Per-dependency marketplace install flag

There is no global marketplace-install toggle. Marketplace install is a
per-dependency setting stored in `.mpm` as
`MPM_SOURCE_<alias>_MARKETPLACE=true`. Absence of the line is the
canonical "disabled" state; mpm never writes `=false` itself.

When `MPM_SOURCE_<alias>_MARKETPLACE=true` for a dependency:

- `mpm install` registers that dependency's marketplace plugin under
  `CLAUDE_MARKETPLACES_DIR` and records the registration in the
  per-source `registered_marketplaces` ledger in `.mpm.lock`.
- `mpm clean` unregisters the plugins mpm recorded and removes the
  marketplace directory it used.

Manage the flag with the `mpm marketplace` subcommand, which edits only
`.mpm` (it never touches `.mpm.lock` and performs no re-resolution):

```bash
# Enable marketplace install for one dependency (writes =true)
mpm marketplace enable <alias>

# Disable it (removes the =true line)
mpm marketplace disable <alias>

# Show each dependency, its catalog <type>, and its effective setting
mpm marketplace status
mpm marketplace status --all
```

### Auto-managed `CLAUDE_MARKETPLACES_DIR` header

The global `CLAUDE_MARKETPLACES_DIR` header is auto-managed alongside the
per-dependency marketplace flags, so the canonical
`mpm add <claude-marketplace> ; mpm install` workflow needs no manual
edit:

- `mpm add` of a `claude-marketplace` entry and `mpm marketplace enable`
  insert `CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces` once, as the
  first non-comment line, when it is absent.
- `mpm remove` and `mpm marketplace disable` prune the line once the last
  `MPM_SOURCE_<alias>_MARKETPLACE=true` dependency is gone; it is re-added
  automatically on the next add or enable.
- A hand-set custom value is preserved (never duplicated, never clobbered);
  set the line by hand only to override the directory.

See [docs/lockfile.md](lockfile.md#marketplace-ownership-and-pruning) for
how the per-source ledger drives marketplace pruning.

---

## mpm repo Subcommand

The `mpm repo` subcommand exposes mpm's repo subsystem for direct
manifest operations, allowing direct invocation of any `repo`
subcommand (such as `init`, `sync`, `version`, `help`) without
requiring a separate `repo` installation.

### MPM\_REPO\_DIR

**`MPM_REPO_DIR`** (default: `.repo`) -- Path to the `.repo`
working directory used by `mpm repo`. Corresponds to the
`--repo-dir` flag on the `mpm repo` subcommand.

### Usage

```bash
# Initialize a manifest repository
mpm repo init -u <url> -b <branch> -m <manifest>

# Sync all projects
mpm repo sync --jobs=4

# Show the status of checked-out projects
mpm repo status

# Use a custom .repo directory
MPM_REPO_DIR=/path/to/workspace/.repo mpm repo status

# Equivalent via flag
mpm repo --repo-dir /path/to/workspace/.repo status
```
