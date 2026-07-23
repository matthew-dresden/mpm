# mpm install

Operator-facing reference for `mpm install` -- the command that
resolves and installs the dependencies declared in `.mpm` and pins
them in `.mpm.lock`.

For the canonical environment-variable table see
[docs/configuration.md](configuration.md).
For lifecycle details see [docs/lifecycle.md](lifecycle.md).

---

## Synopsis

```text
mpm install [--reconcile]
              [--refresh-lock | --refresh-lock-source <name>]
              [--strict-lock] [--strict-drift]
              [--lock-file <path>]
              [<mpmenv_path>]
```

## How it works

`mpm install` is **hermetic** (spec Section 4.3 / FR-14): it reads
only the committed `.mpm` file and its `.mpm.lock`, fetches every
declared source, resolves the transitive include/project graph, and
publishes the result into the shared `MPM_HOME` store. It does **not**
resolve or record a catalog source: the `--catalog-source` flag is not
accepted (passing it exits non-zero), and a populated
`MPM_CATALOG_SOURCES` environment variable is ignored, not read.

A catalog source is needed only by the discovery commands (`mpm
search`, `mpm add`, `mpm outdated`, `mpm why`, `mpm catalog
audit`). You supply it there; `mpm add` writes the resolved,
alias-keyed `MPM_SOURCE_<alias>_*` blocks into `.mpm`, and from then
on `mpm install` works from those blocks with no catalog source.

On first run -- or when `--refresh-lock` is passed -- the lockfile
`.mpm.lock` is written at schema v5. Subsequent runs in a consistent
state install directly from the lockfile without re-resolving.

## The reconcile model

`mpm install` treats the committed lockfile as authoritative by default
(npm-ci style); the lenient reconcile is opt-in via `--reconcile`:

- **Lockfile consistent** (`.mpm.lock` present and its `mpm_hash`
  matches `.mpm`): replay the pinned SHAs verbatim. No re-resolution.
- **Lockfile drifted** (`.mpm.lock` present but `.mpm` has changed,
  e.g. after editing `.mpm`): by default this is a hard error -- the
  consistency check runs before resolving and exits `1` without mutating
  the lock. Pass `--reconcile` to prune orphaned entries, resolve
  added/changed sources fresh, replay unchanged ones, and rewrite the
  lock once on success.
- **No lockfile**: resolve everything from `.mpm` and write
  `.mpm.lock`.

To re-resolve from scratch, pass `--refresh-lock`. To re-resolve exactly
one top-level source while preserving every other lockfile entry, pass
`--refresh-lock-source <name>`.

## Where artifacts live

`mpm install` publishes fetched data into the shared `MPM_HOME`
store, content-addressed and deduped across projects:

- The store root resolves with precedence `--home` / `--store-dir`
  flag > `MPM_HOME` environment variable > the default `~/.mpm-home`.
- The store directory is created if absent. If it cannot be created or is
  not writable, `mpm install` exits non-zero with an actionable
  message naming the path and the `MPM_HOME` variable -- there is no
  silent fallback.
- `mpm clean` resolves the same store root, so it removes exactly what
  `mpm install` wrote.
- The default store root is `~/.mpm-home`. Earlier versions defaulted to
  `~/.mpm`, which collided with a project `.mpm` file when running mpm
  from your home directory. A leftover `~/.mpm` directory from an older
  install is unused and safe to delete (`rm -rf ~/.mpm`).

The legacy per-project `.packages/` / `.mpm-data/` locations and their
`MPM_WORKSPACE_DIR` / `MPM_CACHE_DIR` environment variables were
removed; the shared `MPM_HOME` store subsumes them.

## Flags

| Flag | Description |
|------|-------------|
| `--reconcile` | Opt in to the lenient reconcile when `.mpm` and `.mpm.lock` have drifted: prune orphaned entries, re-resolve added/changed sources, replay unchanged ones, and rewrite `.mpm.lock` on success. Without this flag a drifted pair fails fast. |
| `--refresh-lock` | Ignore the existing lockfile, re-resolve every transitive version from scratch against the committed `.mpm`, and overwrite `.mpm.lock`. |
| `--refresh-lock-source <name>` | Re-resolve exactly one top-level source's full chain while preserving every other source's lockfile entries verbatim. `<name>` may be the `MPM_SOURCE_<name>` alias or a catalog entry name. |
| `--strict-lock` | Additionally fail on an orphaned lock entry that survives a `mpm_hash` match (a source in `.mpm.lock` but absent from `.mpm`). Ordinary drift already fails the default install (see [Orphaned lockfile entries](#orphaned-lockfile-entries)). |
| `--strict-drift` | Promote branch drift (a locked SHA differing from the branch's current tip) to a hard error instead of reusing the locked SHA. |
| `--lock-file <path>` | Path to the lock file (default: `<mpm-file>.lock`; env `MPM_LOCK_FILE`). |

`mpm install` accepts no `--catalog-source` flag: it is hermetic.

## Orphaned lockfile entries

An orphaned lockfile entry is a `[[sources]]` row in `.mpm.lock` whose
alias no longer has a matching `MPM_SOURCE_<alias>_URL` block in
`.mpm`. This happens when a source is removed from `.mpm` (for
example, via `mpm remove`) but the lockfile has not yet been updated to
reflect that removal.

### Default behaviour: fail fast

By default, `mpm install` detects orphaned lockfile entries (an
alias-set drift) with the consistency check that runs **before** any
resolution, exits `1`, and **never mutates the lockfile**. The error
enumerates every orphaned source by name and points at the remediation
flags:

```text
ERROR: .mpm and .mpm.lock alias sets differ.
  Present in .mpm.lock but not declared in .mpm: alpha
  Remediation: run 'mpm install --reconcile' to reconcile .mpm.lock
  with the current .mpm declarations, or 'mpm install --refresh-lock'
  to rebuild the lock from scratch.
```

### Opt-in prune path: --reconcile

To prune the orphans and rewrite the lock, pass `--reconcile`:

```bash
mpm install --reconcile
```

With `--reconcile`, `mpm install` removes each orphan from the
in-memory lockfile and emits one INFO line per orphan:

```text
pruned orphaned lock entry: alpha
```

The lockfile is then rewritten without the orphaned entry and installation
continues normally. `--strict-lock` goes the other way: it additionally
fails on an orphan that survives a `mpm_hash` match. For options to
resolve a strict-lock error, see
[docs/troubleshooting.md -- 15. Strict-lock Orphan Errors](troubleshooting.md#15-strict-lock-orphan-errors).

### Worked example

Suppose your `.mpm` file originally declares a source aliased `my_lib`, and
`mpm add` has already been run so `.mpm.lock` contains the corresponding
entry. You then remove the source:

```bash
mpm remove my_lib
```

The next bare `mpm install` fails fast on the drift. Reconcile it with:

```bash
mpm install --reconcile
```

which prunes the orphan:

```text
pruned orphaned lock entry: my_lib
```

Installation then completes with the remaining declared sources.

## See also

- [docs/lockfile.md](lockfile.md) -- lockfile format and lifecycle.
- [docs/list-and-add.md](list-and-add.md) -- `mpm search`, `mpm add`, and `mpm remove`.
- [docs/configuration.md](configuration.md) -- full environment-variable reference.
- [docs/catalogs-explained.md](catalogs-explained.md) -- what a manifest repo is and how to find one.
