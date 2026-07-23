# mpm Exit Codes

Canonical exit-code reference for the `mpm` CLI. All subcommands
follow the table below. Use this document in CI scripts to map exit
codes to pipeline actions.

## Canonical exit codes

| Code | Meaning | When emitted |
| ---- | ------- | ------------ |
| `0` | Success | Command completed successfully. |
| `1` | Runtime / usage error | Application-level failure (see below). |
| `2` | argparse error | Invalid command-line arguments (including a removed/unknown subcommand). |

**No deprecated-invocation exit code.** mpm 3.0.0 removed `mpm
bootstrap` and `mpm list` outright; neither is a registered subcommand,
so invoking them produces an argparse `invalid choice` usage error (exit
`2`) rather than a dedicated deprecation code. The `EXIT_CODE_DEPRECATED`
(`3`) constant remains defined in the source but is not emitted by any
command.

**Future codes reserved.** Exit codes 3 and above are unassigned.
mpm will not emit them without a corresponding spec change.

### Code `0` -- success

The command ran and all work completed without error.

### Code `1` -- runtime / usage / resolution error

An application-level error occurred. Examples: filesystem error,
network error, resolution failure, validation failure, or malformed
input that the application detected after argument parsing succeeded.
Check stderr for an `ERROR:` line with the specific cause.

### Code `2` -- argparse usage error

Command-line arguments were invalid. argparse emits this when a
required positional is missing, an unknown flag is supplied, a flag
value fails type conversion, or a removed/unknown subcommand (such as
`mpm bootstrap` or `mpm list`) is named. Correct the invocation and
retry. For removed commands, see
[docs/migration-to-add.md](migration-to-add.md).

## Per-subcommand reference

The table shows which codes each subcommand can emit.
`y` = the code is reachable. `--` = not reachable.

| Subcommand | `0` | `1` | `2` |
| ---------- | --- | --- | --- |
| `mpm search` | y | y | y |
| `mpm add` | y | y | y |
| `mpm remove` | y | y | y |
| `mpm outdated` | y | y | y |
| `mpm why` | y | y | y |
| `mpm catalog audit` | y | y | y |
| `mpm validate xml` | y | y | y |
| `mpm validate marketplace` | y | y | y |
| `mpm validate metadata` | y | y | y |
| `mpm validate lockfile` | y | y | y |
| `mpm install` | y | y | y |
| `mpm doctor` | y | y | y |
| `mpm marketplace` | y | y | y |
| `mpm clean` | y | y | y |
| `mpm completion` | y | y | y |
| `mpm repo` | y | y | y |

Removed commands (`mpm bootstrap`, `mpm list`) are not registered
subcommands; invoking them yields the argparse `invalid choice` usage
error (exit `2`). See the note below.

### Notes on `mpm clean`

`mpm clean` exits `0` on a successful teardown, `1` on a runtime error
(for example, a missing `.mpm` file, or a dependency with
`MPM_SOURCE_<alias>_MARKETPLACE=true` while no `CLAUDE_MARKETPLACES_DIR`
is defined), and `2` on an argparse error.
The `--orphans` flag does not introduce a new exit code: it only changes
what cleanup is performed (additionally pruning orphaned-source
marketplaces from `~/.claude` before the normal teardown), not which codes
the command can emit.

### Notes on removed commands (`mpm bootstrap`, `mpm list`)

`mpm bootstrap` and `mpm list` were **removed in mpm 3.0.0** (a
breaking change). There is **no compatibility shim**: neither is a
registered subcommand. Every invocation -- any args, any flags,
including `--help`/`-h`, `mpm bootstrap list`, and bare `mpm
bootstrap` -- fails at argument parsing with an argparse `invalid choice`
usage error and exits with status `2`. No work is performed; the
filesystem and manifest repo are never read.

`mpm list` was renamed to `mpm search`; `mpm bootstrap`'s
catalog-discovery and add functionality is replaced by `mpm search` +
`mpm add` + `mpm install`.

See [docs/migration-to-add.md](migration-to-add.md)
for the full migration guide.

## Using this table in CI

### Removed commands fail with exit 2

`mpm bootstrap` and `mpm list` are no longer registered subcommands,
so a script that calls either fails immediately with the argparse
`invalid choice` usage error (exit `2`). This forces migration at the CI
/ script boundary and prevents stale tooling from running silently.

If your CI pipeline surfaces this error, update the script to use the
replacement command (`mpm add` / `mpm search`). Follow the migration
guide at
[docs/migration-to-add.md](migration-to-add.md).

### Distinguish argparse errors from runtime errors

Exit `2` indicates the CLI was called with invalid arguments (wrong
flag name, missing required positional). Exit `1` indicates the
arguments were valid but the command failed at runtime (network error,
resolution error, file not found).

In shell scripts, check the exit code explicitly when you want to
separate "operator mistyped the command" from "the command ran but the
catalog was unavailable":

```bash
#!/usr/bin/env bash
set -euo pipefail

mpm search
rc=$?

case $rc in
  0) echo "OK" ;;
  1) echo "ERROR: runtime failure -- check stderr" >&2; exit 1 ;;
  2) echo "ERROR: bad arguments (or removed command) -- check syntax" >&2; exit 2 ;;
  *) echo "ERROR: unexpected exit code $rc" >&2; exit 1 ;;
esac
```

### `mpm install` and lockfile drift

`mpm install` treats the committed lockfile as authoritative by
default. Plain `mpm install` runs the consistency check before
resolving and exits `1` (fail fast) on any drift between `.mpm` and
`.mpm.lock` -- an alias-set drift or a per-alias ref-spec mismatch --
and never mutates the lockfile. To reconcile a drifted pair, run
`mpm install --reconcile`: it prunes removed sources, resolves
added/changed sources, replays unchanged ones, rewrites the lock, and
exits `0`. `mpm install --refresh-lock` forces a full rebuild and exits
`0` on success. `--strict-lock` additionally fails on an orphaned lock
entry that survives a `mpm_hash` match. See
[docs/lockfile.md -- Install reconcile model](lockfile.md#install-reconcile-model).

### Gate on `mpm doctor` for workspace health checks

`mpm doctor` exits `1` when any health-check finding reaches
severity ERROR. Wire it as a required CI gate to catch stale lockfiles
and unreachable catalog sources before a build proceeds:

```yaml
- name: Workspace health check
  env:
    MPM_CATALOG_SOURCES: >-
      https://example.com/org/manifest-repo.git@main
  run: mpm doctor
```

Any non-zero exit blocks the pipeline and prints the failing findings
to stderr.

## See also

- [docs/list-and-add.md](list-and-add.md) -- `mpm search`, `mpm add`,
  `mpm remove`
- [docs/outdated-and-why.md](outdated-and-why.md) -- `mpm outdated`,
  `mpm why`
- [docs/cli/doctor.md](cli/doctor.md) -- `mpm doctor`
- [docs/cli/catalog-audit.md](cli/catalog-audit.md) --
  `mpm catalog audit`
- [docs/cli/validate.md](cli/validate.md) -- `mpm validate`
- [docs/lockfile.md](lockfile.md) -- lockfile format consumed by
  `mpm install`, `mpm doctor`, `mpm outdated`, `mpm why`
- [docs/migration-to-add.md](migration-to-add.md)
  -- full migration guide for `mpm bootstrap` users
