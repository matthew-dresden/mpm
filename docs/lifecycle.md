# Lifecycle

## Install Lifecycle (`mpm install`)

```text
1. Parse .mpm, auto-discover sources from MPM_SOURCE_<alias>_URL patterns
2. Validate MPM_SOURCE_<alias>_* variables
3. If any source sets MPM_SOURCE_<alias>_MARKETPLACE=true:
   mkdir -p CLAUDE_MARKETPLACES_DIR, clean contents
4. For each source in alphabetical order:
   a. mkdir -p .mpm-data/sources/<name>/
   b. mpm_cli.repo.repo_init(source_dir, url, revision, manifest_path)
      -- direct Python API call, no subprocess
   c. mpm_cli.repo.repo_envsubst(source_dir, {GITBASE, CLAUDE_MARKETPLACES_DIR})
      -- direct Python API call, no subprocess
   d. mpm_cli.repo.repo_sync(source_dir)
      -- direct Python API call, fail-fast on RepoCommandError
5. Aggregate: symlink .mpm-data/sources/<name>/.packages/* -> .packages/
6. Collision check: fail-fast if duplicate package names
7. Conditional store .gitignore safety net: only when the shared MPM_HOME
   store sits inside a git working tree, write <MPM_HOME>/store/.gitignore
   containing "*". Outside a git repo (the default ~/.mpm-home) no
   .gitignore is written.
8. If any source sets MPM_SOURCE_<alias>_MARKETPLACE=true:
   locate claude binary, discover marketplace entries and plugins,
   register marketplaces, install plugins via claude CLI
9. Reconcile marketplace ownership (per-source registered_marketplaces ledgers):
   auto-unregister any marketplace recorded in the previous lockfile
   that no current source registers (e.g. a source dropped from .mpm,
   or its MPM_SOURCE_<alias>_MARKETPLACE flag toggled off), then write
   the lockfile with each source's registered_marketplaces refreshed
```

All repo operations (init, envsubst, sync) are direct Python API calls into `mpm_cli.repo`.
No external binaries are invoked; no PATH lookups are performed.

Step 9 compares the union of every source's recorded
`registered_marketplaces` in the existing lockfile (`OLD`) against the
marketplaces attributed to the current sources this run (`NEW`). Any name
in `OLD` but not in `NEW` is an orphan and is unregistered from `~/.claude`
via `claude plugin marketplace remove`. Removal candidates come only from
the lockfile ledgers, so a marketplace mpm never recorded is never
touched. See
[docs/lockfile.md -- Marketplace ownership and pruning](lockfile.md#marketplace-ownership-and-pruning).

## Clean Lifecycle (`mpm clean`)

```text
1. Resolve .mpm symlinks (mpmenv_path.resolve())
2. Parse .mpm
3. If --orphans: prune orphaned-source marketplaces (see below), then continue
4. If a marketplace was registered (from .mpm.lock marketplace_registered,
   else any source's .mpm MPM_SOURCE_<alias>_MARKETPLACE flag):
   a. Uninstall marketplace plugins via claude CLI
   b. rm -rf CLAUDE_MARKETPLACES_DIR
5. rm -rf .packages/ (ignore_errors)
6. rm -rf .mpm-data/ (ignore_errors)
7. If --purge or --purge-all: delete this project's .mpm and .mpm.lock
8. If --purge-all: remove the MPM_HOME store dir (store/, cache/, empty root)
```

Steps execute in this specific order: uninstalling plugins first ensures
Claude Code's registry is clean. Removing marketplaces before deleting
symlinks ensures the CLI can resolve paths during removal.

### `mpm clean --orphans`

With `--orphans`, before the normal teardown mpm unregisters the
marketplaces of orphaned sources -- `[[sources]]` entries recorded in
`.mpm.lock` whose `name` no longer appears in the current `.mpm`
(removed via `mpm remove` but not yet reconciled by `mpm install`).
Each such marketplace is unregistered from `~/.claude` via
`claude plugin marketplace remove`. Removal candidates come only from the
orphaned sources' per-source `registered_marketplaces` ledgers, and a
marketplace also provided by a still-referenced source is retained, so the
keep-set and user-managed marketplaces are never touched. Plain
`mpm clean` (without `--orphans`) leaves this teardown path unchanged.
See
[docs/lockfile.md -- Marketplace ownership and pruning](lockfile.md#marketplace-ownership-and-pruning).

### `mpm clean --purge`

With `--purge`, after the normal teardown mpm also deletes this project's
`.mpm` and `.mpm.lock` files -- a full removal of the project's mpm
configuration. Both deletions are no-ops when the file is already absent.

### `mpm clean --purge-all`

With `--purge-all`, mpm does everything `--purge` does and additionally
removes the shared `MPM_HOME` store directory (default `~/.mpm-home`)
used by every project. To avoid destroying unrelated data behind a
misconfigured `MPM_HOME`, `--purge-all` removes only mpm-owned content:
it refuses (fail-fast) when `MPM_HOME` resolves to the filesystem root,
your home directory, or a parent of your home or current directory, and
otherwise removes only the `store/` and `cache/` subdirectories and then the
home root itself, and only when that root is left empty. Any non-mpm
entries in the home root are kept, with a warning.

Because removing the shared store is machine-global, `--purge-all` runs even
when no `.mpm` project is present (for example right after `--purge` deleted
it): mpm skips the project teardown, removes only the shared store, and
applies the same safety refusals. Plain `mpm clean` and `--purge` without
`--purge-all` still require a discoverable `.mpm`.

## Directory Structure After Install

```text
project/
  .mpm                                # Configuration (committed)
  Makefile                              # Catalog entry file (committed)
  .mpm-data/                          # MPM state (do not commit)
    sources/
      build/                            # Source workspace
        .packages/
          mpm-python-lint/
      marketplaces/                     # Source workspace
        .packages/
          mpm-claude-marketplaces-example-dev-lint/
  .packages/                            # Aggregated symlinks (do not commit)
    mpm-python-lint -> ../.mpm-data/sources/build/.packages/mpm-python-lint
    mpm-claude-marketplaces-example-dev-lint -> ../.mpm-data/sources/marketplaces/.packages/...
```
