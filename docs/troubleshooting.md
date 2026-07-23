# MPM Troubleshooting Guide

This guide covers common errors and how to diagnose and resolve them.
Each scenario includes a reproducer command and a fix.

---

## 1. Unquoted PEP 440 Specs

### Symptom

The shell interprets `>` or `<` in a PEP 440 range specifier as a
file-redirect operator. The command appears to run silently but produces
no output, or you see errors like:

```text
bash: main: No such file or directory
```

Or the argument is received by mpm as an empty string, causing:

```text
ERROR: search requires a catalog source.
```

### Reproducer

Run the `add` command with the spec argument unquoted, for example
`package-a@>=1.0,<2.0` without surrounding single quotes. The shell treats
`>=` as a redirect operator, creating a file named `2.0` instead of passing
the spec to mpm.

### Fix

Quote the spec argument so the shell passes it verbatim to mpm:

```bash
mpm add 'package-a@>=1.0,<2.0' --catalog-source <url>@main
```

Double-quotes also work, but single-quotes are preferred for clarity.

### See also

- [docs/list-and-add.md](list-and-add.md) -- shell-quoting examples
- [docs/configuration.md](configuration.md)

---

## 2. Missing Catalog Source

### Symptom

Any mpm command that requires a manifest repo (`mpm search`,
`mpm add`, `mpm outdated`, `mpm why`, `mpm catalog audit`)
exits non-zero with:

```text
ERROR: <command> requires a catalog source.
Provide one of:
  --catalog-source <git-url>@<ref>      # e.g. --catalog-source https://example.com/org/manifest-repo.git@main
  MPM_CATALOG_SOURCES=<git-url>@<ref>  # set as env var, then re-run

The CLI flag takes precedence when both are set.
A catalog source identifies a manifest repo (a git repository whose
repo-specs/ directory exposes installable mpm dependencies).
See docs/catalogs-explained.md for what a manifest repo is and how to find one.
See docs/configuration.md for the full configuration reference.
```

### Reproducer

```bash
# Wrong -- no catalog source provided
mpm search
```

### Fix

Pass the catalog source via the CLI flag:

```bash
mpm search \
  --catalog-source https://example.com/org/manifest-repo.git@main
```

Or export the environment variable and re-run:

```bash
export MPM_CATALOG_SOURCES=https://example.com/org/manifest-repo.git@main
mpm search
```

`mpm install` is hermetic: it never reads a catalog source and rejects
`--catalog-source`. The catalog source is required only by `mpm search`,
`mpm add`, `mpm outdated`, `mpm why`, and `mpm catalog audit`.

### See also

- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 3. Lockfile Schema Mismatch

### Symptom

`mpm install` exits non-zero with an error indicating that the
lockfile schema version is incompatible with the running CLI. mpm 3.0.0
writes schema v5; an older v4 (or earlier) lockfile **hard-fails** -- there
is no automatic upgrade. v4 locks predate the per-source content pins and
also need regeneration:

```text
ERROR: lockfile schema v4 is incompatible with this mpm version (schema v5).
  Path: .mpm.lock
  Schema v5 adds per-source content-SHA pins ([[sources.content_pins]]) on top
  of the v4 alias-keyed source entries; older locks carry no content pins and
  are not silently upgraded.
  There is no automatic upgrade from schema v4.
  Remediation: regenerate the lockfile by running 'mpm add' to refresh the
  alias-keyed declarations, then 'mpm install' to rewrite the lock at schema v5.
```

### Reproducer

```bash
# Install with an older mpm that wrote schema version 4 (or earlier),
# then upgrade to mpm 3.0.0 and re-run:
mpm install
```

### Fix

Regenerate the lockfile at schema v5. There is no in-place upgrade and
`mpm install` is hermetic (it does not take `--catalog-source`), so refresh
the alias-keyed declarations with `mpm add`, then rewrite the lock:

```bash
# Re-add the entries so the .mpm blocks are alias-keyed (supply your catalog source):
mpm add <entry> --catalog-source https://example.com/org/manifest-repo.git@main
# Then rewrite the lockfile at schema v5:
mpm install --refresh-lock
```

A newer lockfile (schema written by a future mpm) instead fails with
`lockfile schema vN written by newer mpm; upgrade mpm.` -- upgrade
mpm to read it.

### See also

- [docs/lockfile.md](lockfile.md)
- [docs/configuration.md](configuration.md)

---

## 4. Branch Drift

### Symptom

When a source's revision is pinned to a branch name, `mpm install`
or `mpm doctor` emits a notice (or error with `--strict-drift`):

```text
branch drift: mysource: main tip abc123 differs from locked def456;
reusing locked SHA
```

With `--strict-drift`:

```text
ERROR: Branch drift detected -- locked SHAs differ from remote tips.
  Source 'mysource': branch 'main' locked at def456, remote tip is
  abc123.
  Remediation: run 'mpm install --refresh-lock-source mysource'
  to accept the new tip.
```

### Reproducer

```bash
# Pin a source to a branch, then let the branch advance on the
# remote, then re-run install:
mpm install
```

### Fix

Accept the new branch tip by re-resolving the drifted source (`mpm install`
is hermetic and resolves from the committed `.mpm`):

```bash
mpm install --refresh-lock-source mysource
```

To turn drift into a hard CI error (recommended for reproducible
builds), pass `--strict-drift`:

```bash
mpm install --strict-drift
```

### See also

- [docs/lockfile.md](lockfile.md)
- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 5. Completion Cache Corruption

### Symptom

Shell completions for `mpm` return no results or produce an error
after a partial cache write or a power loss mid-refresh. `mpm doctor`
may report:

```text
WARNING: completion cache is corrupt: malformed fetched_at timestamp
in cache index; run 'mpm doctor --refresh-completion-cache' to
rebuild.
```

Or the `index.txt` file is missing entirely, causing completions to
silently return nothing.

### Reproducer

```bash
# Interrupt a completion cache refresh mid-write:
kill -9 $(pgrep -f 'mpm doctor --refresh-completion-cache')
mpm search <TAB>
```

### Fix

Invalidate and rebuild the completion cache:

```bash
mpm doctor --refresh-completion-cache
```

This deletes the cached index and fetches a fresh copy from the
configured catalog source.

### See also

- [docs/shell-completion.md](shell-completion.md)
- [docs/configuration.md](configuration.md)

---

## 6. Missing `catalog-metadata` Block

### Symptom

`mpm search`, `mpm add`, or `mpm catalog audit` reports that a
`*-marketplace.xml` file is missing its `<catalog-metadata>` block:

```text
ERROR: manifest repo https://example.com/org/manifest-repo.git@main
has integrity issues (1); the catalog author must fix these via
'mpm catalog audit'. Affected entries:
  repo-specs/my-service-marketplace.xml: missing <catalog-metadata>
```

### Reproducer

```bash
mpm search \
  --catalog-source https://example.com/org/manifest-repo.git@main
```

Against a manifest repo where one XML file lacks `<catalog-metadata>`.

### Fix

This is a catalog-authoring issue. The operator cannot fix it from
the consumer side. Ask the catalog author to:

1. Add a `<catalog-metadata>` block to the affected XML file.
2. Run `mpm catalog audit .` to verify the fix.
3. Push a new tag or commit so consumers can reference the updated
   manifest repo.

### See also

- [docs/catalog-author-guide.md](catalog-author-guide.md)
- [docs/configuration.md](configuration.md)

---

## 7. Entry-Name Collision

### Symptom

Two `*-marketplace.xml` files in the same manifest repo declare the
same `<catalog-metadata><name>` value. `mpm search`, `mpm add`, or
`mpm catalog audit` reports:

```text
ERROR: manifest repo https://example.com/org/manifest-repo.git@main
has integrity issues (1); the catalog author must fix these via
'mpm catalog audit'. Affected entries:
  entry-name 'my-service' appears in 2 files:
    repo-specs/my-service-marketplace.xml
    repo-specs/legacy/my-service-marketplace.xml
```

### Reproducer

```bash
mpm search \
  --catalog-source https://example.com/org/manifest-repo.git@main
```

Against a manifest repo with a name collision.

### Fix

This is a catalog-authoring issue. Ask the catalog author to:

1. Rename one of the conflicting entries in its `<catalog-metadata>`.
2. Run `mpm catalog audit .` to confirm uniqueness.
3. Push an updated tag so consumers reference the fixed revision.

### See also

- [docs/catalog-author-guide.md](catalog-author-guide.md)
- [docs/configuration.md](configuration.md)

---

## 8. Git Auth Failure

### Symptom

`mpm install`, `mpm add`, or any command that performs a
`git ls-remote` or `git clone` exits non-zero with:

```text
ERROR: git authentication failed against
https://example.com/org/manifest-repo.git.
See docs/git-auth-setup.md.
<raw git stderr below>
fatal: Authentication failed for
'https://example.com/org/manifest-repo.git/'
```

Or for SSH:

```text
ERROR: git authentication failed against
git@example.com:org/manifest-repo.git.
See docs/git-auth-setup.md.
git@example.com: Permission denied (publickey).
```

### Reproducer

```bash
# Run against a repo you have no credentials for:
mpm search \
  --catalog-source https://private.example.com/org/repo.git@main
```

### Fix

mpm does not manage credentials. Configure git authentication for
the affected host in your local git client:

- HTTPS: configure a credential helper (OAuth, PAT, or OS keychain).
- SSH: ensure your SSH key is added to `ssh-agent` and the host
  accepts it.

After configuring git auth, re-run the mpm command. mpm does not
retry auth failures.

### See also

- [docs/git-auth-setup.md](git-auth-setup.md) -- platform-specific
  authentication guides
- [docs/configuration.md](configuration.md)

---

## 9. Partial Clone After SIGTERM

### Symptom

A `mpm install` that was interrupted (SIGTERM, SIGINT, or power
loss) leaves a partially-cloned project directory under
`.mpm-data/sources/<name>/`. Subsequent `mpm install` runs may
report:

```text
ERROR: clone directory .mpm-data/sources/my-service/.repo is
incomplete; the previous install was interrupted. Run
'mpm clean --orphans' to remove partial clones, then re-run
'mpm install'.
```

### Reproducer

```bash
# Interrupt install mid-clone:
mpm install &
kill -SIGTERM $!
# Re-run:
mpm install
```

### Fix

Remove partial project clones and re-run install:

```bash
mpm clean --orphans
mpm install
```

`mpm clean --orphans` removes per-project clone directories that
are not referenced by the current `.mpm` or `.mpm.lock`. The
lockfile itself is atomic (write-temp-then-rename), so it is either
complete or absent; only the per-project clone directories may be
partial.

### See also

- [docs/lockfile.md](lockfile.md)
- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 10. Zero PEP 440 Tags in Manifest Repo

### Symptom

`mpm add foo` (no `@spec`) against a manifest repo entry whose
resolution target has only non-PEP-440 git tags (e.g., `v1.0.0`,
`release-2024`) exits non-zero with:

```text
ERROR: manifest repo has no PEP 440-valid tags; pin to a branch or
SHA explicitly (e.g., 'mpm add foo@main') or ask the catalog author
to publish a release tag.
Non-PEP-440 tags found under prefix '':
  v1.0.0
  release-2024
```

### Reproducer

```bash
# Against a manifest repo with only non-PEP-440 tags:
mpm add foo \
  --catalog-source https://example.com/org/manifest-repo.git@main
```

### Fix

**Option 1: Use a branch pin.**

Explicitly specify a branch or SHA instead of relying on the default
latest-PEP-440-tag resolution:

```bash
mpm add 'foo@main' \
  --catalog-source https://example.com/org/manifest-repo.git@main
```

**Option 2: Ask the catalog author to rename tags.**

Ask the catalog author to rename the non-PEP-440 tags (e.g.,
`v1.0.0` -> `1.0.0`) so they are addressable by mpm's resolver.
After the catalog author pushes PEP-440-compliant tags, re-run
`mpm add foo` without an explicit spec.

### See also

- [docs/catalog-author-guide.md](catalog-author-guide.md)
- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 11. REPO_URL and REPO_REV Legacy Env-Var Warnings

### Symptom

`mpm install` emits a combined deprecation warning to stderr when
`REPO_URL` and/or `REPO_REV` are set. If both are set:

```text
DeprecationWarning: REPO_URL and REPO_REV environment variable(s) are
deprecated and no longer used by 'mpm install'. Use --catalog-source
to specify a remote catalog source instead.
```

If only one is set (for example, `REPO_URL` only):

```text
DeprecationWarning: REPO_URL environment variable(s) are deprecated and
no longer used by 'mpm install'. Use --catalog-source to specify a
remote catalog source instead.
```

The message is also written directly to stderr so it appears in CI logs
regardless of Python's active warning filter. The command continues to
run, but the values of `REPO_URL` and `REPO_REV` are ignored; they do
not affect resolution.

### Reproducer

```bash
REPO_URL=https://example.com/repo.git \
REPO_REV=main \
  mpm install
```

### Fix

Unset the legacy env vars from your shell and CI environment:

```bash
unset REPO_URL
unset REPO_REV
```

Then pass the catalog source explicitly via the CLI flag or env var:

```bash
mpm install \
  --catalog-source https://example.com/org/manifest-repo.git@main
```

Or export the env var:

```bash
export MPM_CATALOG_SOURCES=https://example.com/org/manifest-repo.git@main
mpm install
```

### See also

- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## See Also

The following documents provide broader context:

- [docs/configuration.md](configuration.md) -- all environment
  variables and CLI flags
- [docs/exit-codes.md](exit-codes.md) -- non-zero exit code meanings
- [docs/git-auth-setup.md](git-auth-setup.md) -- authentication
  guides for common platforms
- [docs/catalog-author-guide.md](catalog-author-guide.md) -- how to
  create and maintain a manifest repo
- [docs/lockfile.md](lockfile.md) -- lockfile schema and semantics
- [docs/shell-completion.md](shell-completion.md) -- shell completion
  setup and cache management

---

## 12. Package Destination Conflict

### Symptom

`mpm install` exits non-zero with:

```text
ERROR: Package destination conflict -- two or more sources resolve the
same package path to different content.
  Conflict for package path: .packages/shared-lib
  source_a (shared-lib): .packages/shared-lib @ aaaa...aaaa
  source_b (shared-lib): .packages/shared-lib @ bbbb...bbbb
  Remediation: remove one source or align the project revisions so
  '.packages/shared-lib' resolves to a single content SHA.
```

This fires only when two sources resolve the **same** `.packages/<name>`
slot to **different** content. Fetching the **same repository at different
commits** is fine when the `<project>` entries land at **different**
destination paths (the mono-repo case -- install any version of package A and
any version of package B from one repo).

### Reproducer

```bash
# Two sources whose <project path> both resolve to .packages/shared-lib
# at different commits:
mpm install
```

### Fix

**Option 1: Align the revisions.**

Edit `.mpm` (or the catalog manifests) so both declarations resolve the
shared `.packages/<name>` path to the same commit.

**Option 2: Remove one conflicting source.**

```bash
mpm remove <source-name>
mpm install
```

**Option 3: Give the packages distinct destination paths.**

If the two `<project>` entries are genuinely different packages, set a
distinct `<project path>` for each so they no longer share a `.packages/`
slot.

### See also

- [docs/configuration.md](configuration.md)
- [docs/lockfile.md](lockfile.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 13. Lockfile Hash Mismatch

### Symptom

```text
ERROR: .mpm has been modified since the lockfile was written.
  Lockfile mpm_hash : sha256:aabb...
  Current  mpm_hash : sha256:ccdd...
  Remediation: run 'mpm install --refresh-lock' ...
```

### Reproducer

```bash
# Edit .mpm after the last install, then re-run:
mpm install
```

### Fix

Re-resolve from scratch:

```bash
mpm install --refresh-lock \
  --catalog-source <url>@<ref>
```

Or re-resolve just the changed source:

```bash
mpm install --refresh-lock-source <name> \
  --catalog-source <url>@<ref>
```

### See also

- [docs/lockfile.md](lockfile.md)
- [docs/configuration.md](configuration.md)

---

## 14. Lockfile SHA Unreachable

### Symptom

```text
ERROR: Lockfile SHA for source '<name>' is no longer reachable.
  Source  : <name>
  SHA     : <sha>
  Remote  : <url>
  Remediation: run 'mpm install --refresh-lock-source <name>' ...
```

### Reproducer

```bash
# After a force-push or tag removal that removes the pinned commit:
mpm install
```

### Fix

```bash
mpm install --refresh-lock-source <name> \
  --catalog-source <url>@<ref>
```

### See also

- [docs/lockfile.md](lockfile.md)
- [docs/configuration.md](configuration.md)

---

## 15. Strict-lock Orphan Errors

### Symptom

A plain `mpm install` against a `.mpm` whose alias set has drifted from
`.mpm.lock` already fails fast (the consistency check runs before
resolving). `--strict-lock` additionally rejects an orphaned lock entry that
survives a `mpm_hash` match. The command exits non-zero and enumerates
every orphaned source by name. For a single orphaned entry (N == 1):

```text
ERROR: 1 orphaned lockfile entry: alpha
These lockfile entries have no matching MPM_SOURCE_*_URL triple in .mpm.

Remediation:
  Run `mpm install --reconcile` to prune, or
  restore the missing MPM_SOURCE_<name>_* triples in .mpm, or
  run `mpm remove <name>` for each orphan to clean the lockfile.
```

For two or more orphaned entries (N >= 2, names are sorted alphabetically and
joined by `,`):

```text
ERROR: 2 orphaned lockfile entries: alpha, beta
These lockfile entries have no matching MPM_SOURCE_*_URL triple in .mpm.

Remediation:
  Run `mpm install --reconcile` to prune, or
  restore the missing MPM_SOURCE_<name>_* triples in .mpm, or
  run `mpm remove <name>` for each orphan to clean the lockfile.
```

An orphaned lock entry is a `[[sources]]` row in `.mpm.lock` whose `name`
no longer appears in the current `.mpm` source declarations. This happens
when a source is removed from `.mpm` (e.g., via `mpm remove`) but the
lockfile has not yet been updated.

### Reproducer

```bash
# Remove a source from .mpm, then re-run install with --strict-lock:
mpm remove <name>
mpm install --strict-lock
```

### Fix

Three remediation options are available; pick the one that matches your intent:

- **Option 1: Reconcile (accept the removal).**
  Re-run `mpm install --reconcile`. The orphaned entries are pruned from
  the lockfile and the lock is rewritten. Use this option when the source
  removal was intentional and you want the lockfile to reflect it.

  ```bash
  mpm install --reconcile
  ```

- **Option 2: Restore the missing triples (undo the removal).**
  Re-add the `MPM_SOURCE_<name>_URL`, `MPM_SOURCE_<name>_REF`, and
  `MPM_SOURCE_<name>_PATH` triples to `.mpm` for each listed orphan name.
  Then re-run install. Use this option when the source removal was accidental.

  ```bash
  # Edit .mpm to restore the removed triples, then:
  mpm install --strict-lock
  ```

- **Option 3: Remove each orphan explicitly.**
  Run `mpm remove <name>` for each orphan listed in the error message. This
  cleans both `.mpm` and the lockfile in a single tracked operation. Use this
  option when you want a clean, auditable removal rather than a reconcile.

  ```bash
  mpm remove alpha
  mpm remove beta
  mpm install --strict-lock
  ```

### See also

- [docs/lockfile.md](lockfile.md)
- [docs/configuration.md](configuration.md)
- spec/defect-resolution-and-fixture-automation-2026-06/spec.md Section 0 (DEFECT-011)

---

## 16. Workspace Lock Contention

### Symptom

A `mpm install`, `mpm add`, `mpm remove`, or
`mpm doctor --refresh-completion-cache` invocation hangs
indefinitely without producing output.

### Reproducer

```bash
# Run two concurrent installs:
mpm install &
mpm install
```

### Fix

Use `lsof` to find the holding process:

```bash
lsof .mpm-data/.mpm-install.lock
```

Wait for the holder to finish. If the process is stale:

```bash
kill <PID>
```

After the holder exits, the waiting mpm command proceeds
automatically.

### See also

- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 17. Insecure Remote URL

### Symptom

```text
ERROR: Insecure <remote> URL detected in resolved manifest.
  Source  : mysource
  Remote  : mysource
  URL     : http://example.com/repo.git
  Remediation: Use an HTTPS or SSH <remote> URL, or set
  MPM_ALLOW_INSECURE_REMOTES=1 if this is intentional
  (the override disables the security check).
```

### Reproducer

```bash
# A source using an http:// URL:
mpm install
```

### Fix

**Option 1: Switch to HTTPS or SSH (recommended).**

```ini
MPM_SOURCE_mysource_URL=https://example.com/repo.git
```

**Option 2: Override the check (use with caution).**

```bash
MPM_ALLOW_INSECURE_REMOTES=1 mpm install .mpm
```

### See also

- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 18. Claude Marketplace Not Registered After Install

### Symptom

`mpm install` exits 0 but `claude plugin marketplace list` shows no
marketplace entries. This occurred prior to the DEFECT-004 fix because
`mpm install` cloned sources into `CLAUDE_MARKETPLACES_DIR` but never
called `claude plugin marketplace add` to register each entry with
the Claude Code CLI.

### Expected Behaviour After Fix

With the DEFECT-004 fix, every `mpm install` run that has at least one
dependency with `MPM_SOURCE_<alias>_MARKETPLACE=true` invokes:

```text
claude plugin marketplace add <absolute-path-to-marketplace-entry>
```

once per discovered marketplace directory under `CLAUDE_MARKETPLACES_DIR`.
After install completes, `claude plugin marketplace list` must show one
registered entry per source that ships a marketplace root
(`.claude-plugin/marketplace.json` present).

### Failure Mode: `claude` binary unavailable

When a `MPM_SOURCE_<alias>_MARKETPLACE=true` dependency is declared and the
`claude` binary is not on `$PATH`, `mpm install` now fails fast with exit
code 1. The exact text written to stderr is:

```text
Error: claude binary not found on $PATH. Ensure claude is installed and available.
```

This replaces the previous silent-skip behaviour (DEFECT-004). The install
does not proceed past the binary check; no partial marketplace state is left
behind.

### Diagnostic

To confirm which step failed, check the last lines of stderr from
`mpm install`. The marketplace registration summary line:

```text
Install summary: N marketplaces processed, M registered, P plugins installed
```

is written to stdout on completion. If this line does not appear, the
install failed before reaching the registration loop (typically the
missing-binary case above).

### Remediation

**Option 1: Install the `claude` CLI and re-run.**

Ensure `claude` is installed and on `$PATH`, then re-run:

```bash
mpm install
```

**Option 2: Skip marketplace registration.**

If Claude Code marketplace integration is not required in this environment,
disable the per-dependency marketplace flag on each marketplace source:

```bash
mpm marketplace disable <alias>
mpm install
```

`mpm marketplace disable` removes the `MPM_SOURCE_<alias>_MARKETPLACE` line
(absence is the canonical false). With no dependency opted in, `mpm install`
skips all `claude plugin marketplace add` invocations. The source repos are
still cloned; only the Claude Code plugin registration step is skipped. Use
`mpm marketplace status` to confirm each dependency's effective setting.

### See also

- [docs/claude-marketplaces-guide.md](claude-marketplaces-guide.md) -- marketplace setup and configuration
- [docs/configuration.md](configuration.md)
- [docs/exit-codes.md](exit-codes.md)

---

## 19. Direct-Checkout Marketplace Not Registered After Install

### Symptom

`mpm install` exits 0 and clones source repositories, but
`claude plugin marketplace list` shows no entry for a source that carries
a `.claude-plugin/marketplace.json` file and has no `<linkfile>` element
in the manifest XML (a "direct-checkout" source). This occurred prior to
the E51-F3-S1-T1 fix (BUG-3) because the marketplace registration loop
only discovered marketplace roots via the linkfile path; sources without a
linkfile were silently skipped.

### Affected Configuration

A source is a direct-checkout source when both of the following are true:

- The source's manifest XML contains no `<linkfile>` element pointing at
  a marketplace directory (or the source has no manifest XML at all).
- The cloned source directory contains `.claude-plugin/marketplace.json`
  at its root.

### Expected Behaviour After Fix (E51-F3-S1-T1)

With the BUG-3 fix, `mpm install` checks each cloned source directory
for `.claude-plugin/marketplace.json` regardless of whether a linkfile is
present. When the file is found, the source directory root is passed to:

```text
claude plugin marketplace add <absolute-path-to-source-root>
```

After install completes, `claude plugin marketplace list` shows one
registered entry for every source that ships `.claude-plugin/marketplace.json`,
including direct-checkout sources.

### Preconditions

- The source's dependency block has `MPM_SOURCE_<alias>_MARKETPLACE=true`
  (set it with `mpm marketplace enable <alias>`, or pass `--marketplace-install`
  to `mpm add` when adding the entry).
- The `claude` binary is available on `$PATH`.

### Remediation (if still missing after upgrade)

If upgrading mpm does not resolve the missing registration, re-run
install to trigger registration (`mpm install` is hermetic and resolves
from the committed `.mpm` / `.mpm.lock`):

```bash
mpm marketplace enable <alias>
mpm install
```

This re-runs the full registration loop including the direct-checkout
discovery path.

### See also

- [docs/cli.md](cli.md) -- `mpm install -- direct-checkout marketplace registration (BUG-3)` section
- [docs/claude-marketplaces-guide.md](claude-marketplaces-guide.md) -- marketplace setup and configuration
- [docs/configuration.md](configuration.md)
