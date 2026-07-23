# mpm doctor

Run workspace health checks against the current project directory.

## Synopsis

```bash
mpm [--no-color] doctor [--mpm-file <path>] [--lock-file <path>] [--strict-drift] [--refresh-completion-cache] [--prune-cache] [--catalog-source <git-url>@<ref>]
```

## Description

`mpm doctor` inspects a mpm workspace and reports any inconsistencies
between the `.mpm` configuration file and the `.mpm.lock` lockfile. It
is read-only when invoked without `--refresh-completion-cache` or
`--prune-cache`: it reads files and queries remote repositories but does
not modify any local state.
With `--refresh-completion-cache`, it invalidates all files under
`${MPM_HOME}/cache/completion-cache/`.
With `--prune-cache`, it removes cache files whose atime is older than
`MPM_CACHE_PRUNE_AGE_DAYS` days and reports stale install-lock advisories.
Both flags are independent and may be combined.

Exit code is 0 when all checks pass (or when only info-level findings are
emitted). Exit code is 1 when any error-level finding is detected.

## Options

`--mpm-file <path>`
: Path to the `.mpm` configuration file. Defaults to `./.mpm`. The
  `MPM_MPM_FILE` environment variable is checked when this flag is not
  supplied; the CLI flag takes precedence when both are set.

`--lock-file <path>`
: Path to the `.mpm.lock` lockfile. Defaults to `<mpm-file>.lock`
  (e.g. `./.mpm.lock`). The `MPM_LOCK_FILE` environment variable is
  checked when this flag is not supplied.

`--strict-drift`
: Promote branch-drift findings from info-level to error-level. Without
  this flag, branch-drift is reported as an informational notice and the
  command exits 0. With this flag, any detected drift causes exit code 1.
  See subcheck 4 (Branch drift) below.

`--catalog-source <git-url>@<ref>`
: Override the catalog source for this invocation. Takes the form
  `<git-url>@<ref>` where `ref` is a branch, tag, or `latest`.
  When supplied, this flag takes highest precedence in the effective
  catalog source resolution (see subcheck 6 below). Overrides the
  `MPM_CATALOG_SOURCES` environment variable. The lockfile no longer
  carries a catalog source: the current schema v5 (like v4 before it) has
  no `[catalog]` block, so the lockfile does not participate in
  catalog-source resolution.

`--refresh-completion-cache`
: Subcheck 8: Invalidate all files under `${MPM_HOME}/cache/completion-cache/`,
  recreating the directory empty with mode `0700`. Reports an info finding
  with the count of files removed. This flag is independent of the health
  checks. `MPM_HOME` resolves from the `--home` / `--store-dir` flag, the
  `MPM_HOME` env var, then the `~/.mpm-home` default, so the cache directory is
  always resolved.

`--prune-cache`
: Subcheck 10: Remove files under `${MPM_HOME}/cache` whose last-access time
  is older than `MPM_CACHE_PRUNE_AGE_DAYS` days (default 30). Reports an
  info finding with the count and total byte size pruned. Also reports any
  stale `.mpm-data/.mpm-install.lock` files (mtime older than
  `MPM_DOCTOR_STALE_LOCK_AGE_HOURS` hours) as advisory findings -- doctor
  does NOT delete them. The cache directory is resolved from `MPM_HOME`
  (flag, env var, or `~/.mpm-home` default); the stale-lock scan always runs from
  the current working directory.

## Subchecks

`mpm doctor` runs the following consistency checks in order.

### Subcheck 1: .mpm / .mpm.lock consistency

Verifies that the `.mpm` file exists at the expected path and that a
`.mpm.lock` lockfile is present.

**Error when .mpm is absent (exit 1):**

```text
ERROR: no mpm workspace in <cwd>: '.mpm' not found
  Remediation: Run 'mpm add ...' to create a .mpm file, or 'cd' to a
  directory that contains one.
```

**Info notice when .mpm.lock is absent (exit 0):**

```text
INFO: No lockfile present; run `mpm install` to generate one.
  Remediation: mpm install
```

When `.mpm.lock` is absent, subchecks 2-5 and 11 are skipped; the command
exits 0 after emitting the info notice and running subchecks 6, 7, and 9.

### Subcheck 2: Hand-edit detection (mpm_hash)

Recomputes the `mpm_hash` digest over the current `.mpm` file and
compares it with the `mpm_hash` field stored in the lockfile. A mismatch
indicates the `.mpm` file was edited directly after the last
`mpm install` run.

**Error (exit 1):**

```text
ERROR: mpm_hash mismatch: .mpm was hand-edited since the last 'mpm install'.
  Remediation: Run 'mpm install --refresh-lock' to rebuild the lockfile.
```

### Subcheck 3: Orphaned lock entries

For every source recorded in the lockfile, checks that the matching
alias-keyed `MPM_SOURCE_<alias>_{URL,REF,PATH,NAME}` block still exists in
`.mpm` (matched by alias; optional per-dependency env-var lines do not affect
presence). A source present in the lockfile but absent from `.mpm` is an
orphan (e.g. the source was removed from `.mpm` without re-running
`mpm install`).

**Error per orphan (exit 1):**

```text
ERROR: orphan lock entry: source 'X' is in .mpm.lock but absent from .mpm
  Remediation: Run 'mpm install' to prune (or 'mpm install --strict-lock'
  to keep the lockfile authoritative).
```

### Subcheck 4: Branch drift

For every lockfile entry whose `ref_spec` resolves to a branch name
(not a SHA and not a `refs/...` ref), queries
`git ls-remote refs/heads/<branch>` against the source URL and compares
the current branch tip SHA with the locked SHA.

Without `--strict-drift`, drift is reported as an info notice (exit 0):

```text
INFO: branch drift: source 'X' is locked to <old-sha> but 'main' is now at <new-sha>
  Remediation: Run 'mpm install --refresh-lock' to update the lockfile.
```

With `--strict-drift`, drift is reported as an error (exit 1):

```text
ERROR: branch drift: source 'X' is locked to <old-sha> but 'main' is now at <new-sha>
  Remediation: Run 'mpm install --refresh-lock' to update the lockfile.
```

### Subcheck 5: Dangling SHA

For every lockfile entry whose `ref_spec` is a SHA (40 or 64 lowercase
hex characters), queries `git ls-remote <url>` and verifies the locked SHA
appears in the first column of the remote's ref list. A SHA that is not
found in any ref indicates the commit was force-pushed or pruned.

Branch-pinned sources are skipped by this check (they are handled by
subcheck 4 instead).

**Error (exit 1):**

```text
ERROR: dangling SHA: <sha> is no longer reachable from <url>; the remote
may have force-pushed or pruned the commit.
  Remediation: Run 'mpm install --refresh-lock' to rebuild.
```

### Subcheck 6: Effective catalog source

Reports the effective catalog source and which configuration layer provided
it. This check always runs, regardless of whether `.mpm.lock` is present.

Resolution precedence (first non-empty wins):

1. `--catalog-source <git-url>@<ref>` CLI flag (highest priority).
2. The single source configured in the `MPM_CATALOG_SOURCES` environment
   variable. `MPM_CATALOG_SOURCES` (plural) is a newline-separated list; when
   it configures exactly one entry that entry is the effective value, and when
   it configures several the finding reports the ambiguity (single-source
   commands require `--catalog-source` to select one).
3. None -- no catalog source is configured.

Schema v4 removed the lockfile `[catalog]` block, so the lockfile does NOT
participate in catalog-source resolution. The catalog source for `mpm add`,
`mpm search`, `mpm outdated`, and `mpm why` is supplied only by the CLI
flag or the env var; `mpm install` is hermetic and does not consult a catalog
source at all.

The provenance suffix is mandatory in every output path: it tells the
operator WHERE the effective value came from, not just what the value is.
This is how operators detect `MPM_CATALOG_SOURCES` leakage from a shell
profile into an unrelated workspace (see spec Section 3.6).

**Output printed to stdout:**

When a source is configured (examples for each precedence level):

```text
Effective catalog source: https://example.com/org/catalog.git@main (from --catalog-source CLI flag)
Effective catalog source: https://example.com/org/catalog.git@main (from MPM_CATALOG_SOURCES env var)
```

When `MPM_CATALOG_SOURCES` configures more than one source, the finding
reports the ambiguity:

```text
MPM_CATALOG_SOURCES configures 2 catalog sources (https://example.com/org/a.git@main, https://example.com/org/b.git@main) (from MPM_CATALOG_SOURCES env var); single-source commands require --catalog-source to select one.
```

When no source is configured (exit 0, but commands that need a catalog will fail):

```text
Effective catalog source: (none configured); commands requiring a catalog source will fail.
```

#### Example: detecting a leaked env var

An operator has `MPM_CATALOG_SOURCES=https://corp.example.com/infra-catalog.git@main` in
their `.bashrc`, exported globally. They `cd` into an unrelated project and run
a catalog-dependent command. To check first:

```text
$ mpm doctor
...
Effective catalog source: https://corp.example.com/infra-catalog.git@main (from MPM_CATALOG_SOURCES env var)
```

The provenance suffix `(from MPM_CATALOG_SOURCES env var)` immediately reveals that
the catalog source comes from the environment, not from a local CLI flag. The
operator can then unset the variable before running any catalog-dependent
command:

```text
$ unset MPM_CATALOG_SOURCES
$ mpm doctor
...
Effective catalog source: (none configured); commands requiring a catalog source will fail.
```

Without the provenance suffix, an operator reading only the URL would not know
whether it was intentional for this project or a stale variable from another session.

### Subcheck 8: Completion-cache invalidation (--refresh-completion-cache)

When `--refresh-completion-cache` is set, all files under
`${MPM_HOME}/cache/completion-cache/` are deleted and the directory is
recreated empty with mode `0700`. This invalidates any cached completion data
so the next completion invocation rebuilds the cache from scratch.

This subcheck runs BEFORE subchecks 1-5, 7, 9, 10, and 11.

**Info finding after refresh:**

```text
INFO: Completion cache refreshed: 3 file(s) removed from /home/user/.mpm/cache/completion-cache
```

`MPM_HOME` resolves from the `--home` / `--store-dir` flag, the `MPM_HOME`
env var, then the `~/.mpm-home` default, so the completion-cache directory is
always resolved.

### Subcheck 7: Completion errors report

Reads the most recent `MPM_COMPLETION_ERRORS_REPORT_LIMIT` lines (default 5)
from `${MPM_HOME}/cache/completion-errors.log`. This log is written by shell
completion callback failures (see E7 / `docs/shell-completion.md`).

`mpm doctor` only reads this log -- it does NOT modify, truncate, or rotate it.
The cache directory is resolved from `MPM_HOME` (flag, env var, or `~/.mpm-home`
default); when the log file does not exist this subcheck reports the info notice
below.

**Info notice when the log is absent or empty:**

```text
INFO: no completion errors recorded
```

**Warning when recent errors are present:**

```text
WARN: Recent completion errors (5):
2026-01-01T12:00:00Z __complete_catalog_entries ValueError: empty response
2026-01-01T12:00:01Z __complete_source_names FileNotFoundError: .mpm not found
2026-01-01T12:00:02Z __complete_catalog_entries TimeoutError: git ls-remote timed out after 30s
2026-01-01T12:00:03Z __complete_source_names ValueError: malformed .mpm line 7
2026-01-01T12:00:04Z __complete_catalog_entries ConnectionError: name resolution failed
  Remediation: Inspect ${MPM_HOME}/cache/completion-errors.log for details.
```

When the log contains more than `MPM_COMPLETION_ERRORS_REPORT_LIMIT` lines,
only the most recent `MPM_COMPLETION_ERRORS_REPORT_LIMIT` lines are shown.
Malformed lines (no timestamp, unexpected format) are included verbatim.

### Subcheck 9: Completion-script staleness

When an operator has installed a static shell completion script (as opposed to
using the dynamic eval-time approach), this subcheck compares the on-disk
script's SHA-256 hash to a freshly generated script. If the hashes differ, the
operator's installed script is stale and should be regenerated.

Static completion script discovery uses the candidate paths from
`MPM_STATIC_COMPLETION_SEARCH_PATHS` (defined in `constants.py`). For each
path that exists on disk, the comparison is run independently. Multiple shells
(e.g., bash and zsh) may each have a stale script; one warning is emitted per
drifted script.

When no static completion scripts are installed at any candidate path, this
subcheck emits no finding (silent).
When a static script's hash matches the freshly generated output, no finding
is emitted for that shell.

**Warning when a bash script is stale (exit 0 -- warn is not error):**

```text
WARN: Stale bash completion script: /home/user/.local/share/bash-completion/completions/mpm does not match the output of 'mpm completion bash'. Re-run 'mpm completion bash > /home/user/.local/share/bash-completion/completions/mpm' to update it.
  Remediation: mpm completion bash > /home/user/.local/share/bash-completion/completions/mpm
```

**Warning when a zsh script is stale:**

```text
WARN: Stale zsh completion script: /home/user/.zsh/completions/_mpm does not match the output of 'mpm completion zsh'. Re-run 'mpm completion zsh > /home/user/.zsh/completions/_mpm' to update it.
  Remediation: mpm completion zsh > /home/user/.zsh/completions/_mpm
```

Multiple shells with stale scripts produce one warning per shell.

### Subcheck 11: Remote reachability sanity check

For every distinct remote URL recorded in the lockfile, runs
`git ls-remote --exit-code <url> HEAD` (subject to `MPM_RESOLVE_TIMEOUT`
and the retry policy). URLs are deduplicated using `canonicalize_repo_url`
before the check, so SSH and HTTPS forms of the same repository are checked
exactly once.

This check runs ONLY when `.mpm.lock` is present. If the lockfile is absent,
subcheck 1 short-circuits and subcheck 11 is skipped.

**Difference from subcheck 5 (dangling SHA):**

| | Subcheck 5 (dangling SHA) | Subcheck 11 (remote reachability) |
|---|---|---|
| What it checks | Whether a specific locked SHA is still reachable at the remote | Whether the remote URL itself is reachable at all |
| What triggers it | Non-zero `git ls-remote` exit OR SHA not in any ref's first column | Non-zero `git ls-remote --exit-code <url> HEAD` for any reason |
| Severity | **error** (exit 1) | **warning** (exit 0) |
| Retries | Subject to `MPM_GIT_RETRY_COUNT` (immediate, no inter-attempt delay) | Same retry policy; auth-error patterns skip retries |

Remote-reachability failures are deliberately warnings rather than errors.
Network connectivity is transient: a `mpm doctor` run that fails with exit 1
because the operator's network is down is not useful as a triage tool. The
warning surfaces the diagnostic -- URL, exit code, first line of stderr -- so
the operator can investigate (missing SSH key, unconfigured credential helper,
network outage, repository moved) without blocking a workspace check.

**Warning when a remote is unreachable (exit 0):**

```text
WARN: remote unreachable: https://example.com/org/repo (exit code 128); stderr: repository not found
  Remediation: Check network access and git credentials for https://example.com/org/repo. See docs/git-auth-setup.md for SSH key and credential helper setup.
```

The warning includes:

- The canonicalized URL (`.git` suffix and user-info stripped).
- The exit code returned by `git ls-remote --exit-code`.
- The first line of stderr, truncated at `MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS`
  characters (default 160) to keep output bounded.
- A remediation hint referencing `docs/git-auth-setup.md`.

**Auth errors (e.g., missing SSH key):**

Auth-error patterns matching `GIT_AUTH_ERROR_PATTERNS` (e.g., `Permission denied`,
`Authentication`) skip the retry policy to avoid credential lockouts, but still
produce the same warning finding. The operator should configure their SSH agent
or credential helper before re-running:

```text
WARN: remote unreachable: https://github.com/org/repo (exit code 128); stderr: Permission denied (publickey).
  Remediation: Check network access and git credentials for https://github.com/org/repo. See docs/git-auth-setup.md for SSH key and credential helper setup.
```

**All remotes reachable:** No finding is emitted.

### Subcheck 10: Cache pruning and stale-lock advisory (--prune-cache)

When `--prune-cache` is set, two actions occur:

**10a -- Cache prune:** All files under `${MPM_HOME}/cache` (recursively)
whose last-access time (`atime`) is older than `MPM_CACHE_PRUNE_AGE_DAYS`
days are deleted. The number of deleted files and their combined byte size are
reported as an info finding.

**10b -- Stale install-lock advisory:** The working directory is scanned
(recursively, up to `MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH` levels) for
`.mpm-data/.mpm-install.lock` files whose mtime is older than
`MPM_DOCTOR_STALE_LOCK_AGE_HOURS` hours. Each such file is reported as
an advisory info finding. Doctor does NOT delete these files; `fcntl.flock`
self-cleans on process exit, so a leftover file on disk is harmless and does
not block subsequent installs.

This subcheck runs BEFORE subchecks 1-5, 7, 9, and 11, and AFTER subcheck 8
when both flags are combined.

**Info finding after pruning 2 files totalling 4096 bytes:**

```text
INFO: Cache pruned: 2 file(s) removed (4096 bytes) with atime older than 30 days
```

**Advisory finding for a stale install lock:**

```text
INFO: Advisory: stale install lock found at /path/to/.mpm-data/.mpm-install.lock (mtime older than 1h). fcntl.flock self-cleans on process exit; this file is harmless.
```

`MPM_HOME` resolves from the `--home` / `--store-dir` flag, the `MPM_HOME`
env var, then the `~/.mpm-home` default, so the cache prune always runs against
the resolved cache directory; the stale-lock scan runs independently from the
current working directory.

**Combining both flags:**

```bash
mpm doctor --refresh-completion-cache --prune-cache
```

Refresh runs first (subcheck 8), then prune runs (subcheck 10). Both findings
are emitted. Health checks (subchecks 1-5, 6, 7, 9, 11) always run after.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MPM_MPM_FILE` | `./.mpm` | Path to the `.mpm` configuration file |
| `MPM_LOCK_FILE` | `<mpm-file>.lock` | Path to the `.mpm.lock` lockfile |
| `MPM_CATALOG_SOURCES` | (none) | Newline-separated catalog sources as `<git-url>@<ref>`; the single configured entry is the effective value, overridden by the `--catalog-source` CLI flag |
| `MPM_RESOLVE_TIMEOUT` | `30` | Timeout in seconds for each `git ls-remote` call |
| `MPM_GIT_RETRY_COUNT` | `3` | Maximum number of `git ls-remote` attempts |
| `MPM_GIT_RETRY_DELAY` | `1` | Inter-attempt delay in seconds (read by doctor; not applied to the `git ls-remote` retry path, which delegates to `git_runner.run_git_ls_remote` and uses immediate retries with no time-based delay) |
| `MPM_HOME` | `~/.mpm-home` | Shared mpm home (store + caches); cache lives under `${MPM_HOME}/cache`. Resolves from the `--home` / `--store-dir` flag, then this env var, then the `~/.mpm-home` default |
| `MPM_COMPLETION_ERRORS_REPORT_LIMIT` | `5` | Maximum number of recent completion-error log lines to display in subcheck 7 |
| `MPM_CACHE_PRUNE_AGE_DAYS` | `30` | Files older than this many days (by atime) are removed by `--prune-cache` (subcheck 10) |
| `MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH` | `4` | Maximum directory depth for the stale install-lock scan in `--prune-cache` (subcheck 10) |
| `MPM_DOCTOR_STALE_LOCK_AGE_HOURS` | `1` | Minimum lock file age in hours to qualify as stale in the advisory scan (subcheck 10) |
| `MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS` | `160` | Maximum characters from the first line of `git ls-remote` stderr included in a remote-reachability warning (subcheck 11) |

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | All checks passed (or only info-level findings) |
| `1` | One or more error-level findings detected |

## Examples

Run all health checks against the default `.mpm` file:

```bash
mpm doctor
```

Promote branch-drift findings to errors:

```bash
mpm doctor --strict-drift
```

Use a custom mpm file location:

```bash
mpm doctor --mpm-file /path/to/my/.mpm
```

Run checks with an explicit lock file path:

```bash
mpm doctor --mpm-file /path/to/.mpm --lock-file /path/to/.mpm.lock
```

Check which catalog source is active (subcheck 6) and override with a specific one:

```bash
mpm doctor --catalog-source https://example.com/org/catalog.git@main
```

Detect a leaked `MPM_CATALOG_SOURCES` env var (look for the provenance suffix in stdout):

```bash
mpm doctor
# Expected output when env var is set:
# Effective catalog source: https://corp.example.com/catalog.git@main (from MPM_CATALOG_SOURCES env var)
```

Invalidate the completion cache (removes all files under `${MPM_HOME}/cache/completion-cache/`):

```bash
mpm doctor --refresh-completion-cache
# Expected stderr output:
# INFO: Completion cache refreshed: 5 file(s) removed from /home/user/.mpm/cache/completion-cache
```

Remove stale cache files older than 30 days and check for stale install locks:

```bash
mpm doctor --prune-cache
# Expected stderr output:
# INFO: Cache pruned: 3 file(s) removed (24576 bytes) with atime older than 30 days
```

Run both refresh and prune together:

```bash
mpm doctor --refresh-completion-cache --prune-cache
```

## See Also

- `mpm install` -- Install all sources defined in `.mpm`
- `mpm install --refresh-lock` -- Rebuild the lockfile from the current `.mpm`
- `docs/lockfile.md` -- Lockfile schema reference
- `docs/configuration.md` -- Full configuration reference
