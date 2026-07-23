# mpm (Missing Package Manager)

A standalone Python CLI for managing versioned DevOps automation packages
via declarative manifests.

**License:** Apache 2.0

---

## Table of Contents

- [Platform support](#platform-support)
- [Quick Start: Find and Add Dependencies](#quick-start-find-and-add-dependencies)
- [Tab Completion](#tab-completion)
- [Subcommands](#subcommands)
- [Git Authentication](#git-authentication)
- [Migration from mpm bootstrap](#migration-from-mpm-bootstrap)
- [What is MPM?](#what-is-mpm)
  - [Fully customizable](#fully-customizable)
  - [Core Purpose](#core-purpose)
- [Use Cases](#use-cases)
  - [Unify Disparate Automation](#unify-disparate-automation)
  - [Platform Engineering](#platform-engineering)
  - [Multi-Project Consistency](#multi-project-consistency)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Install the MPM CLI](#install-the-mpm-cli)
  - [Standalone Usage (No Task Runner Required)](#standalone-usage-no-task-runner-required)
  - [Integrating with Task Runners (Optional)](#integrating-with-task-runners-optional)
- [CLI Reference](#cli-reference)
  - [mpm search](#mpm-search)
  - [mpm add](#mpm-add)
  - [mpm remove](#mpm-remove)
  - [mpm install](#mpm-install)
  - [mpm clean](#mpm-clean)
  - [mpm list](#mpm-list)
  - [mpm outdated](#mpm-outdated)
  - [mpm why](#mpm-why)
  - [mpm doctor](#mpm-doctor)
  - [mpm validate](#mpm-validate)
  - [mpm catalog audit](#mpm-catalog-audit)
  - [mpm repo](#mpm-repo)
  - [mpm completion](#mpm-completion)
  - [mpm bootstrap (removed in 3.0.0)](#mpm-bootstrap-removed-in-300)
- [.mpm Variable Reference](#mpm-variable-reference)
  - [Core Variables](#core-variables)
  - [Source Variables](#source-variables)
  - [Environment Variables](#environment-variables)
  - [Example .mpm](#example-mpm)
- [Architecture](#architecture)
  - [How It Works](#how-it-works)
  - [Directory Structure After Install](#directory-structure-after-install)
  - [Multi-Source Isolation](#multi-source-isolation)
  - [Environment Variable Portability (envsubst)](#environment-variable-portability-envsubst)
- [Creating a Manifest Repository](#creating-a-manifest-repository)
  - [Structure](#structure)
  - [Catalog entry](#catalog-entry)
  - [remote.xml -- Git Remote Definition](#remotexml----git-remote-definition)
  - [packages.xml -- Package Declarations](#packagesxml----package-declarations)
  - [Entry-point manifest](#entry-point-manifest)
  - [Include Chains for Hierarchy](#include-chains-for-hierarchy)
  - [Updating Package Versions](#updating-package-versions)
- [Creating Packages](#creating-packages)
  - [Package Structure](#package-structure)
  - [Versioning](#versioning)
  - [Registering a Package](#registering-a-package)
  - [Symlinks via linkfile](#symlinks-via-linkfile)
- [Creating Marketplace Packages](#creating-marketplace-packages)
  - [Marketplace Manifest Structure](#marketplace-manifest-structure)
  - [Key Requirements](#key-requirements)
  - [Cascading Includes](#cascading-includes)
  - [Validation](#validation)
- [Manifest Features (PEP 440 Constraints)](#manifest-features-pep-440-constraints)
  - [PEP 440 Version Constraints in Manifests](#pep-440-version-constraints-in-manifests)
  - [PEP 440 Version Resolution in .mpm](#pep-440-version-resolution-in-mpm)
  - [Absolute Linkfile Destinations](#absolute-linkfile-destinations)
- [SSH Authentication Setup](#ssh-authentication-setup)
- [Developer Setup](#developer-setup)
  - [Prerequisites](#prerequisites-1)
  - [Install from Source](#install-from-source)
  - [Set Up Git Hooks](#set-up-git-hooks)
  - [Run Tests](#run-tests)
  - [Build](#build)
  - [Project Structure](#project-structure)
  - [Contributing](#contributing)
  - [CI/CD Pipeline](#cicd-pipeline)
- [Documentation](#documentation)
- [License](#license)

---

## Platform support

MPM runs on macOS and Linux. **Windows is not currently supported
(planned).** Native Windows support is on the roadmap but not yet
available; in the meantime, run mpm under WSL2 (Windows Subsystem for
Linux), where the Linux instructions throughout this documentation apply
unchanged.

The shell-completion docs describe a cross-platform PowerShell Core
(`pwsh`) completer that also runs on macOS and Linux; see
[docs/shell-completion.md](docs/shell-completion.md). PowerShell Core
support is not a claim of native Windows support.

---

## Quick Start: Find and Add Dependencies

The following five-step workflow shows how to discover, inspect, add, and
install a dependency from a remote manifest catalog -- using the placeholder
URL `https://example.com/org/manifest-repo.git@main` throughout.

**Step 1: Discover available packages.**

```bash
mpm search --catalog-source 'https://example.com/org/manifest-repo.git@main'
```

Lists every package declared in the remote catalog so you can see what is
available.

**Step 2: Inspect a package.**

```bash
mpm search my-package \
  --catalog-source 'https://example.com/org/manifest-repo.git@main' \
  --detail
```

Shows the full metadata for `my-package` -- version history, description,
and source URL.

**Step 3: Add the package at a pinned version.**

```bash
mpm add 'my-package@==1.2.3' \
  --catalog-source 'https://example.com/org/manifest-repo.git@main'
```

Writes `my-package@==1.2.3` into your `.mpm` manifest file. The `==`
prefix pins to an exact version; PEP 440 range constraints (e.g., `~=1.2.0`,
`>=1.0.0,<2.0.0`) are also accepted.

**Step 4: Install (first run writes `.mpm.lock`).**

```bash
mpm install
```

`mpm install` is hermetic: it resolves the declared packages from the
committed `.mpm` (it does not re-read the catalog), clones them into the
shared `MPM_HOME` store under `.mpm-data/sources/`, aggregates symlinks
under `.packages/` in that store, and writes `.mpm.lock` with exact
resolved versions so every subsequent install is reproducible.

**Step 5: Commit both `.mpm` and `.mpm.lock`.**

```bash
git add .mpm .mpm.lock
git commit -m "feat: add my-package 1.2.3"
```

Committing both files ensures the entire team installs the same resolved
package versions. The synced artifacts live in the shared `MPM_HOME`
store (`~/.mpm-home` by default), never in your project, so there is nothing
package-related to commit beyond `.mpm` and `.mpm.lock`.

---

## Tab Completion

MPM ships built-in shell completion for bash, zsh, and PowerShell Core
(`pwsh`) via the `mpm completion <shell>` subcommand. Run
`eval "$(mpm completion bash)"` (or `zsh`) once in your shell session, or
add it to your shell RC file, to enable tab-completion of subcommand names,
flags, and catalog entries. For PowerShell, pipe
`mpm completion powershell` into `Out-String | Invoke-Expression`. For
persistent installation and advanced options, see
[docs/shell-completion.md](docs/shell-completion.md).

---

## Subcommands

| Subcommand | Summary | Doc |
| --- | --- | --- |
| `mpm search` | List packages available in a catalog or show detail for one | [docs/list-and-add.md](docs/list-and-add.md) |
| `mpm add` | Add a package (with optional version constraint) to `.mpm` | [docs/list-and-add.md](docs/list-and-add.md) |
| `mpm remove` | Remove a package from `.mpm` | [docs/list-and-add.md](docs/list-and-add.md) |
| `mpm list` | List sources declared in `.mpm` vs installed in `.mpm.lock` (installed / not-installed / orphan) | [docs/cli-reference.md](docs/cli-reference.md#mpm-list) |
| `mpm outdated` | Show packages in `.mpm` that have newer versions available | [docs/outdated-and-why.md](docs/outdated-and-why.md) |
| `mpm why` | Explain why a specific package version was resolved | [docs/outdated-and-why.md](docs/outdated-and-why.md) |
| `mpm install` | Resolve, clone, and symlink all packages; writes `.mpm.lock` | [docs/lockfile.md](docs/lockfile.md) |
| `mpm doctor` | Diagnose the local MPM installation and report problems | [docs/doctor.md](docs/doctor.md) |
| `mpm catalog audit` | Audit a catalog for missing or malformed entries | [docs/catalog-author-guide.md](docs/catalog-author-guide.md) |
| `mpm validate xml` | Validate XML manifests under `repo-specs/` | [docs/repo/manifest-format.md](docs/repo/manifest-format.md) |
| `mpm validate marketplace` | Validate marketplace XML manifests under `repo-specs/` | [docs/repo/manifest-format.md](docs/repo/manifest-format.md) |
| `mpm validate metadata` | Validate catalog entry metadata | [docs/catalog-author-guide.md](docs/catalog-author-guide.md) |
| `mpm clean` | Remove synced packages and MPM state (`--orphans` prunes unreferenced marketplaces; `--purge` also deletes `.mpm`/`.mpm.lock`; `--purge-all` also removes the `MPM_HOME` store) | [docs/lifecycle.md](docs/lifecycle.md) |
| `mpm repo` | Low-level manifest-driven repo sync subsystem | [docs/repo/README.md](docs/repo/README.md) |
| `mpm marketplace` | Manage the per-dependency Claude marketplace install flag in `.mpm` (`enable` / `disable` / `status`) | [docs/configuration.md](docs/configuration.md) |
| `mpm completion` | Emit a shell completion script for bash, zsh, or powershell | [docs/shell-completion.md](docs/shell-completion.md) |
| `mpm bootstrap` | **removed in 3.0.0** -- not a registered subcommand (argparse `invalid choice`, exit 2); use `mpm search` / `mpm add` instead | [docs/migration-to-add.md](docs/migration-to-add.md) |

---

## Git Authentication

MPM uses the `git` binary for all remote operations and never prompts for
credentials or caches them itself -- authentication is delegated entirely to
the operator's git client (SSH keys, credential helpers, `GIT_TOKEN`, etc.).
For setup instructions covering SSH key forwarding, HTTPS token helpers, and
URL rewriting for private Git hosts, see
[docs/git-auth-setup.md](docs/git-auth-setup.md).

---

## Migration from mpm bootstrap

The `mpm bootstrap` subcommand was removed in mpm 3.0.0 (a breaking
change) -- it is no longer a registered subcommand, so `mpm bootstrap`
exits non-zero with an argparse `invalid choice` error. Its
catalog-discovery and project-scaffolding responsibilities have been
replaced by `mpm search` (discover and inspect packages) and `mpm add`
(add a pinned dependency to `.mpm`). If your workflow currently uses
`mpm bootstrap <entry>`, the
[docs/migration-to-add.md](docs/migration-to-add.md)
guide walks through the equivalent `mpm search` + `mpm add` + `mpm
install` steps and explains the lockfile model that replaces hand-editing
`.mpm`.

---

## What is MPM?

MPM is a **DevOps Platform Dependency Manager** that brings
version-controlled, reproducible automation to your projects through
declarative manifests. MPM enables you to centralize, version, and share
automation across your organization without replacing your existing tools.

**Solves a common problem:** Organizations have quality automation and operational knowledge scattered across teams -- build conventions, linting rules, security scanning, test frameworks, local dev tooling, and shared markdown documentation that work well but are not widely adopted because they are hard to discover, version, test, and distribute. MPM enables you to package this automation and share it across projects in a tested, reproducible way.

### Fully customizable

- **Public or Private** -- Use public repositories or host everything privately within your organization
- **Your Infrastructure** -- Point to your own Git repositories and package sources
- **Your Standards** -- Define your own manifests, packages, and automation
- **Portable** -- Teams retain access to automation even after external partnerships end

### Core Purpose

- **Platform Dependency Management** -- Centralize and version your DevOps automation, shared knowledge, dependencies, and standards
- **Flexible Overlay** -- Works alongside your preferred build tools and dependency managers, or standalone with no task runner at all
- **Team Standards** -- Share tested, versioned automation, tasks, and approaches across teams dynamically
- **Tool Agnostic** -- Adapts to your workflow, not the other way around

## Use Cases

### Unify Disparate Automation

Your organization has quality automation scattered across teams -- testing frameworks, linting configs, deployment scripts, security scans -- but they are not widely adopted because they are hard to find, version, and integrate. MPM lets you package this automation, version it, and make it available to all teams through simple manifests.

### Platform Engineering

Provide golden paths and paved roads to development teams. Package your organization's standards, policies, automation, and shared operational knowledge as versioned dependencies that teams can pull into their projects.

This can include CI/CD workflows, security policies, deployment automation, coding standards, architecture guidance, operational runbooks, and shared markdown knowledge bases used by both developers and AI coding agents.

### Multi-Project Consistency

Ensure the same testing, linting, security scanning, and deployment automation across projects without copy-pasting or manual synchronization.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [pipx](https://pipx.pypa.io/) on PATH
  (`python3 -m pip install --user pipx && pipx ensurepath`)
- Git
- If authenticating with Git via SSH, see
  [SSH Authentication Setup](#ssh-authentication-setup)

### Install the MPM CLI

`missing-package-manager` is published to [PyPI](https://pypi.org/project/missing-package-manager/). The
recommended install method depends on the use case:

**Production / general use** -- isolated CLI install via pipx:

```bash
pipx install missing-package-manager
```

**Local development on this repository** -- editable install into the
project's virtualenv:

```bash
pip install -e .
```

(Editable mode lets local source edits take effect immediately without
reinstalling. CI uses `pip install missing-package-manager` for ephemeral runners; see
`docs/pipeline-integration.md`.)

### Standalone Usage (No Task Runner Required)

MPM works directly from the command line. No task runner is needed. The
workflow is declarative: you discover entries in a remote catalog, add the
ones you want to `.mpm`, install them, and (optionally) clean up. Every
command that resolves a catalog needs a catalog source -- either the
`--catalog-source <url>@<ref>` flag or the `MPM_CATALOG_SOURCES`
environment variable.

```bash
# Set once in your shell rc file -- pin to the current major version
export MPM_CATALOG_SOURCES='https://github.com/your-org/your-catalog-repo.git@>=2.0.0,<3.0.0'
```

**1. Discover entries in the catalog:**

```bash
mpm search                   # all entry names, one per line
mpm search --detail          # human-readable record per entry
mpm search my-tool --detail  # narrow to entries matching a substring
```

`mpm search` reads the catalog entry manifests (any `repo-specs/**/*.xml`
file with a `<catalog-metadata>` block) in the manifest repo and prints one
catalog entry name per line.

**2. Add entries to `.mpm`:**

```bash
mpm add my-tool                       # pin to the highest available version
mpm add 'my-tool@>=1.0.0,<2.0.0'      # pin with a PEP 440 constraint
mpm add my-tool --marketplace-install # also enable the marketplace lifecycle
```

`mpm add` resolves each entry against the catalog and writes the
alias-keyed `MPM_SOURCE_<alias>_{URL,REF,PATH,NAME}` block into
`.mpm` (plus one optional `MPM_SOURCE_<alias>_<VAR>` env-var line per
`${VAR}` the entry's manifest references -- `GITBASE` auto-derived, others
empty -- and a `_MARKETPLACE=true` line for marketplace entries),
creating the file when it does not yet exist. There is no global header.

**3. Install (sync all packages, write `.mpm.lock`):**

```bash
mpm install
```

`mpm install` is hermetic: it reads only the committed `.mpm` and
`.mpm.lock` (it does not accept `--catalog-source` and ignores
`MPM_CATALOG_SOURCES`). It reconciles `.mpm` against `.mpm.lock`,
runs the repo init/envsubst/sync lifecycle for every source, aggregates
packages into `.packages/` via symlinks under the shared `MPM_HOME`
store, creates source workspaces under `.mpm-data/sources/` in that
store, and writes `.mpm.lock` with the exact resolved SHAs.

**4. Clean (full teardown):**

```bash
mpm clean              # remove .packages/, .mpm-data/, marketplace dir
mpm clean --orphans    # also prune mpm-owned marketplaces no longer referenced
```

`mpm clean` removes this project's synced packages and MPM state from
the shared `MPM_HOME` store, prunes the content-addressed entries it no
longer references, and (for any source with
`MPM_SOURCE_<alias>_MARKETPLACE=true`) uninstalls marketplace plugins.

**Important:** All synced artifacts live in the shared `MPM_HOME` store
and are never committed. Commit only `.mpm` and `.mpm.lock` to your
repository.

The `@<ref>` portion of a catalog source accepts a branch name, a tag, the
special value `latest` (which resolves to the highest PEP 440 tag), or a PEP
440 version constraint (e.g., `~=2.0.0`, `>=2.0.0,<3.0.0`). Version
constraints are resolved against the repository's git tags via
`git ls-remote`. The manifest repo IS the catalog: every `repo-specs/**/*.xml`
file carrying a `<catalog-metadata>` block is one catalog entry (the
`-marketplace.xml` suffix is a convention, not a requirement). There is no
separate `catalog/` directory.

Manifest repositories should use [semantic versioning](https://semver.org/)
for git tags. Pinning to a major version range (e.g., `>=2.0.0,<3.0.0`)
allows automatic pickup of minor and patch releases while preventing
unexpected breaking changes.

### Integrating with Task Runners (Optional)

MPM works standalone via `mpm install` and `mpm clean`. You can wrap
these commands in any build tool or task runner by creating targets that
delegate to the CLI.

### Tab Completion

MPM ships with built-in shell completion for bash, zsh, and PowerShell
Core (`pwsh`) via the `mpm completion <shell>` subcommand. The generated
script enables tab-completion of subcommand names and flags in your shell
session.

**Quick setup:**

```bash
# bash -- add to ~/.bashrc or source once in your current session
eval "$(mpm completion bash)"

# zsh -- add to ~/.zshrc
eval "$(mpm completion zsh)"
```

```powershell
# PowerShell -- add to your $PROFILE
mpm completion powershell | Out-String | Invoke-Expression
```

For persistent installation and advanced options (system-wide install,
oh-my-zsh), see `docs/shell-completion.md`.

---

## CLI Reference

```bash
mpm --help                              # Top-level help
mpm --version                           # Show version
```

Run `mpm <command> --help` for the full option list of any command. The
sections below summarise each command. A catalog source (the
`--catalog-source <url>@<ref>` flag or a single `MPM_CATALOG_SOURCES`
entry) is required by `search`, `add`, `outdated`, `why`, and
`catalog audit`. `install` is hermetic: it reads only `.mpm` and
`.mpm.lock`, does not accept `--catalog-source`, and has no lock
`[catalog]` fallback.

### mpm search

Discovers catalog entries. Prints one entry name per line to stdout, sorted
lexicographically, by reading the catalog entry manifests (any
`repo-specs/**/*.xml` file carrying a `<catalog-metadata>` block) in the
catalog source.

```bash
mpm search                       # all entry names
mpm search foo                   # substring filter (name/desc/keywords)
mpm search --regex '^foo'        # regex filter
mpm search --detail              # human-readable record per entry
mpm search --format json         # structured JSON array
mpm search --tree                # three-layer ASCII dependency tree
mpm search -A                    # walk historical tagged versions
```

Key options: `--format {names,json}`, `--detail`, `--tree` (with
`--max-depth N`, `--no-filter-required`), `-A`/`--all` (with `--limit N`,
`--no-limit`, `--since-version <spec>`), `--regex <pattern>`,
`--match-fields <csv>`. A positional `<substring>` and `--regex` are mutually
exclusive; `--format json` is incompatible with `--tree`.

### mpm add

Resolves catalog entries from the catalog source and appends the alias-keyed
`MPM_SOURCE_<alias>_{URL,REF,PATH,NAME}` block to `.mpm` (plus one optional
`MPM_SOURCE_<alias>_<VAR>` env-var line per `${VAR}` the entry's manifest
references and a `_MARKETPLACE=true` line for marketplace entries), creating the
file when absent. There is no global header.

```bash
mpm add my-tool                       # pin to highest PEP 440 tag
mpm add 'my-tool@>=1.0.0,<2.0.0'      # pin with a PEP 440 constraint
mpm add my-tool --marketplace-install # enable the marketplace lifecycle
mpm add my-tool --dry-run             # print the diff without writing
```

Each entry is `<name>` or `<name>@<spec>` (PEP 440 constraint). Key options:
`--as <alias>` (override the auto-computed alias), `--mpm-file <path>`
(default `./.mpm`, env `MPM_MANIFEST_FILE`), `--force` (overwrite an existing
block), `--dry-run`, and the mutually-exclusive `--marketplace-install` /
`--no-marketplace-install` (force the added dependency's marketplace flag,
overriding the auto-detected `<catalog-metadata><type>`).

### mpm remove

Removes the alias-keyed `MPM_SOURCE_<alias>_*` block (the structural `_URL`,
`_REF`, `_PATH`, `_NAME`, plus any optional per-dependency env-var line such as
`_GITBASE` and the optional `_MARKETPLACE`) for one or more entries from
`.mpm`.

```bash
mpm remove my-tool                      # canonical source OR entry name
mpm remove my-tool --dry-run            # preview removed lines
mpm remove my-tool --force              # skip not-fully-present sources
```

Each `<name>` may be the canonical source alias (e.g. `foo_bar`) or the
original entry name (e.g. `Foo-Bar`); both normalise to the same keys.
Removal is atomic: if any requested name is not fully present (fewer than
the expected number of block keys) and `--force` is not set, the command
exits non-zero and the file is unchanged.

### mpm install

Executes the full install lifecycle and reconciles `.mpm` against
`.mpm.lock`.

```bash
mpm install                     # auto-discover .mpm by walking up from cwd
mpm install .mpm              # explicit path to .mpm file
mpm install --reconcile         # opt in to prune/re-resolve when .mpm and .mpm.lock drift
mpm install --strict-lock       # error when an orphaned lock entry survives a hash match
mpm install --strict-drift      # error when a branch source has drifted
mpm install --refresh-lock      # re-resolve every transitive version from scratch
mpm install --refresh-lock-source NAME  # re-resolve one source's chain only
```

**Behavior:**

- Parses `.mpm`, then runs the repo init/envsubst/sync lifecycle for each
  source (alphabetical order).
- Aggregates packages into `.packages/` via symlinks under the shared
  `MPM_HOME` store; detects cross-source name collisions (fail-fast). When
  the store lives inside a git repo, writes a `.gitignore` safety net into
  the store root.
- Reconciles against `.mpm.lock` like `npm ci`: a plain `install` fails fast
  (exit 1) without mutating the lock when `.mpm` and `.mpm.lock` have
  drifted (a source added, removed, or with a changed ref). `--reconcile` opts
  in to the lenient prune-and-re-resolve (prune orphaned entries, re-resolve
  added/changed sources, replay unchanged ones, rewrite the lock on success).
  `--strict-lock` additionally rejects an orphaned lock entry that survives a
  `mpm_hash` match. Branch drift (a locked SHA differing from the branch's
  current tip) reuses the locked SHA with an info-line; `--strict-drift`
  promotes that to an error.
- **Marketplace prune:** when a source is removed from `.mpm` and the lock is
  rebuilt (via `--reconcile`, `--refresh-lock`, or `mpm clean --orphans`),
  the marketplaces that source registered are unregistered.
- For any source with `MPM_SOURCE_<alias>_MARKETPLACE=true`: runs the
  marketplace install lifecycle.

`--refresh-lock` and `--refresh-lock-source NAME` re-resolve transitive
versions from the committed `.mpm` declarations. They do not take or
require a catalog source: `mpm install` is hermetic on every path.

### mpm clean

Executes the full teardown lifecycle.

```bash
mpm clean                       # auto-discover .mpm by walking up from cwd
mpm clean .mpm                # explicit path to .mpm file
mpm clean --orphans             # also unregister orphaned marketplaces
mpm clean --purge               # also delete .mpm and .mpm.lock
mpm clean --purge-all           # also remove the MPM_HOME store directory
```

**Behavior:**

1. For any source with `MPM_SOURCE_<alias>_MARKETPLACE=true`: uninstalls
   plugins and removes the marketplace directory.
2. Removes the `.packages/` and `.mpm-data/` directories and prunes this
   project's content-addressed entries from the shared `MPM_HOME` store.

With `--orphans`, before the normal teardown mpm also unregisters any
mpm-owned marketplaces recorded in `.mpm.lock` that are no longer
referenced by `.mpm`, pruning them from `~/.claude`.

With `--purge`, mpm also deletes this project's `.mpm` and `.mpm.lock`
files. With `--purge-all`, it additionally removes the shared `MPM_HOME`
store directory (default `~/.mpm-home`), removing only mpm-owned content
(`store/`, `cache/`, and the emptied root) and refusing unsafe `MPM_HOME`
paths such as your home directory or the filesystem root.

### mpm list

Lists the sources declared in `.mpm` against those installed in `.mpm.lock`,
tagging each `installed`, `not-installed`, or `orphan` -- the mpm analogue of
`pip list` / `npm ls`.

```bash
mpm list                        # every source, declared vs installed, tagged
mpm list --declared             # only sources declared in .mpm (no orphans)
mpm list --status orphan        # only sources in the lock no longer declared
mpm list --tree                 # expand installed sources to transitive packages
mpm list --format json          # machine-readable JSON
```

A source is `installed` when it is in both files, `not-installed` when declared
but not yet locked (run `mpm install`), and `orphan` when locked but no longer
declared. Key options: `--declared`, `--tree`, `--status {installed,not-installed,orphan}`,
`--format {table,json}`, `--mpm-file`, `--lock-file`. See
[docs/cli-reference.md](docs/cli-reference.md#mpm-list).

### mpm outdated

Compares each source in `.mpm` against the catalog and emits a table of
`name | current | latest-matching-spec | latest-available | upgrade-type`.

```bash
mpm outdated                    # table output, always exits 0
mpm outdated --format json      # JSON array, one object per source
mpm outdated --fail-on-upgrade  # exit 1 when any source has an upgrade (CI gate)
```

The `current` column comes from `.mpm.lock` when present, or is
live-resolved against the catalog when absent. Key options:
`--fail-on-upgrade`, `--format {table,json}`, `--mpm-file`, `--lock-file`.

### mpm why

Explains why a transitive dependency is in the tree. Reads `.mpm`, resolves
the full dependency tree (from `.mpm.lock` when present, else live-resolves
against the catalog), and prints every chain reaching the requested node.

```bash
mpm why my-project              # by source name, repo URL, or XML path
mpm why https://example.com/org/project.git
mpm why remote                  # a transitive include, by its name
mpm why --format json my-project
```

The argument is matched four ways: a `<project>` repo URL (canonicalized), a
transitive XML manifest path (exact-string equality), a top-level source name,
or a transitive include name (the last two normalized via `derive_source_name`).
When a single logical node is reached by many chains -- for example a transitive
include pulled in by several sources -- every chain is printed; an error is
raised only when the argument matches two or more distinct interpretations. A
catalog source is required only on the live-resolve path (when `.mpm.lock` is
absent).

### mpm doctor

Diagnoses `.mpm` / `.mpm.lock` health against the current project
directory.

```bash
mpm doctor                            # run all health checks
mpm doctor --strict-drift             # promote branch-drift findings to errors
mpm doctor --refresh-completion-cache # invalidate the shell completion cache
mpm doctor --prune-cache              # prune stale cache files (age-based)
```

Reports findings including `.mpm`/`.mpm.lock` consistency (via
`mpm_hash`), hand-edit detection, orphaned lock entries, branch drift,
dangling-SHA detection, a `NO_SOURCES` finding for a zero-source `.mpm`, and
a remote-reachability sanity check (warning only). See
[docs/doctor.md](docs/doctor.md) for the full subcheck reference.

### mpm validate

Validates manifest XML files. Subcommands:

```bash
mpm validate xml          # well-formedness, attributes, include chains
mpm validate marketplace  # linkfile dest, includes, uniqueness, tag format
mpm validate metadata     # catalog-metadata soft-spots (no network access)
mpm validate lockfile     # .mpm <-> .mpm.lock consistency
```

- **`validate xml`** -- checks well-formed XML, required attributes on
  `<project>` and `<remote>`, and that `<include>` names point to existing
  files.
- **`validate marketplace`** -- checks `<linkfile dest>` attributes, include
  chain integrity, project path uniqueness, and revision tag format.
- **`validate metadata`** -- checks the `<catalog-metadata>` blocks for
  required/recommended fields, source-name derivation, and entry-name
  uniqueness, without cloning or calling git. Supports `--format {text,json}`.
- **`validate lockfile`** -- checks that the `.mpm` declarations agree with
  the `.mpm.lock` entries (alias uniqueness, alias-set parity, ref-spec
  parity) -- the same check `mpm install` runs implicitly. Accepts a
  `<mpmenv_path>` and `--lock-file PATH`.

The `xml`, `marketplace`, and `metadata` subcommands accept
`--repo-root REPO_ROOT` (default: auto-detect via `git rev-parse`).

### mpm catalog audit

Audits a manifest repo against the catalog standards contract (the five
soft-spot rules).

```bash
mpm catalog audit                       # audit the current directory
mpm catalog audit ./scratch --strict    # promote warnings to errors
mpm catalog audit https://example.com/org/repo.git@main  # audit a remote source
mpm catalog audit --check metadata,tag-format            # run a subset of checks
```

`<dir-or-source>` is a local directory (must contain `repo-specs/`) or a
remote `<git_url>@<ref>` source; defaults to `.`. Options: `--check <subset>`
(valid values: `all`, `entry-name-uniqueness`, `metadata`, `remote-url`,
`source-name-derivation`, `tag-format`), `--format {text,json}`, `--strict`.
See [docs/catalog-author-guide.md](docs/catalog-author-guide.md).

### mpm repo

Catalog-author / low-level subcommand: runs mpm's `repo` dispatcher.
All trailing arguments after `mpm repo` are forwarded verbatim to it.

```bash
mpm repo init -u <url> -b <branch> -m <manifest>
mpm repo sync --jobs=4
mpm repo help
```

`--repo-dir REPO_DIR` sets the `.repo` directory (default: `${MPM_REPO_DIR}`
or `.repo`). See [docs/repo/README.md](docs/repo/README.md).

### mpm completion

Emits the shell completion script for mpm to stdout.

```bash
mpm completion bash > /etc/bash_completion.d/mpm
mpm completion zsh  > "${fpath[1]}/_mpm"
mpm completion powershell | Out-String | Invoke-Expression
```

Target shell choices: `bash`, `zsh`, `powershell` (PowerShell Core / `pwsh`).
`cmd.exe` has no programmable tab-completion and is not a supported target.
See [docs/shell-completion.md](docs/shell-completion.md).

### mpm bootstrap (removed in 3.0.0)

`mpm bootstrap` was removed in mpm 3.0.0 (a breaking change). There is
**no compatibility shim**: `bootstrap` is no longer a registered subcommand,
so `mpm bootstrap` (with any args or flags) exits non-zero with an argparse
`invalid choice: 'bootstrap'` error that lists the valid subcommands. The
catalog model changed: a manifest repo no longer has a separate
`catalog/<name>/` location and the mpm wheel no longer bundles a catalog.
Use `mpm search` to discover entries and `mpm add` to add them. See
[docs/migration-to-add.md](docs/migration-to-add.md).

---

## .mpm Variable Reference

The `.mpm` file is a shell-compatible `KEY=VALUE` configuration file that
drives the MPM lifecycle. Lines starting with `#` are comments. Values can
reference environment variables using `${VAR}` syntax (e.g.,
`${HOME}/.claude-marketplaces`). Every `.mpm` variable can be overridden
by an environment variable of the same name, enabling CI/CD pipelines to
customize behavior without modifying the file.

### Core Variables

There is no required global header. The only global variable mpm reads is:

**`CLAUDE_MARKETPLACES_DIR`** (Auto-managed)
Directory for marketplace symlinks. Auto-added (as
`CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces`) by `mpm add` of a
`claude-marketplace` entry and by `mpm marketplace enable`, and pruned by
`mpm remove` / `mpm marketplace disable` once the last
`MPM_SOURCE_<alias>_MARKETPLACE=true` dependency is gone. Hand-set the line
only to override the directory; a custom value is preserved and never clobbered.

### Source Variables

Sources are auto-discovered from `MPM_SOURCE_<alias>_URL` variable patterns
and processed in alphabetical order by alias. Each source carries the
following alias-keyed variables:

**`MPM_SOURCE_<alias>_URL`** (Required)
Git URL for the source's manifest repository.

**`MPM_SOURCE_<alias>_REF`** (Required)
Branch, exact tag, or PEP 440 constraint (e.g. `refs/tags/~=1.1.0`) for the
source.

**`MPM_SOURCE_<alias>_PATH`** (Required)
Path to the entry-point manifest XML for the source.

**`MPM_SOURCE_<alias>_NAME`** (Required)
The original catalog entry name (the pre-normalization manifest name).

**`MPM_SOURCE_<alias>_<VAR>`** (Optional, open-ended)
Per-dependency env vars used to resolve `${VAR}` placeholders in this source's
manifest at install time. `mpm add` writes one line per `${VAR}` the entry's
manifest actually references: the var named exactly `GITBASE` is auto-derived
from the source URL (e.g. `MPM_SOURCE_<alias>_GITBASE=https://github.com/your-org`,
replacing the removed global `GITBASE` header), and every other var name is
written empty for you to fill in. An entry whose manifest references no `${VAR}`
gets no env-var line. At install time each declared var is injected into that
source's manifest substitution; if a `${VAR}` remains unresolved, install fails
fast naming the `MPM_SOURCE_<alias>_<VAR>` key to set.

**`MPM_SOURCE_<alias>_MARKETPLACE`** (Optional)
Per-source marketplace toggle. Set to `true` to enable the marketplace
lifecycle for this source; absence means `false` (mpm never writes
`=false`). Written by `mpm add --marketplace-install`; manage it with
`mpm marketplace enable` / `disable` / `status`.

### Environment Variables

**`MPM_CATALOG_SOURCES`**
Newline-delimited list of remote catalog sources, each as `url[@ref]` where
ref is a branch, tag, `latest`, or PEP 440 constraint (e.g.,
`>=2.0.0,<3.0.0`). Commands that resolve a catalog use the single configured
entry, or the `--catalog-source` flag overrides it. A catalog source is
**required** by `mpm search`, `mpm add`, `mpm outdated`, `mpm why`,
and `mpm catalog audit`. `mpm install` is hermetic: it reads only
`.mpm` and `.mpm.lock` and does not consult a catalog source.

**`MPM_HOME`**
Root of the shared mpm store and caches (default `~/.mpm-home`). The
`--home` / `--store-dir <path>` global flag overrides it for a single
invocation; precedence is flag > `MPM_HOME` > `~/.mpm-home`. Replaces the
removed `MPM_WORKSPACE_DIR` / `MPM_CACHE_DIR` variables. Synced artifacts
and the per-`.mpm` workspace lock both live under `${MPM_HOME}/store/`,
so the project directory holds only `.mpm` (plus `.mpm.lock` after the
first install) and never a `.mpm-data/` lock directory.

**`MPM_SKIP_UPDATE_CHECK`**
Set to `1` to skip the PyPI update-available check (equivalent to the
`--no-update-check` global flag).

See [docs/configuration.md](docs/configuration.md) for the full
environment-variable reference.

### Example .mpm

```properties
# Auto-added by `mpm add` of a claude-marketplace entry / `mpm marketplace
# enable`; pruned on the last `mpm remove` / `mpm marketplace disable`.
# Hand-set it only to override the directory.
CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces

# Source: build -- build tooling packages.
# The _GITBASE line below is present only because this source's manifest
# references ${GITBASE}; a manifest with fully-literal remotes has no env-var line.
MPM_SOURCE_build_URL=https://github.com/your-org/mpm-manifests.git
MPM_SOURCE_build_REF=main
MPM_SOURCE_build_PATH=repo-specs/build/meta.xml
MPM_SOURCE_build_NAME=build
MPM_SOURCE_build_GITBASE=https://github.com/your-org

# Source: marketplaces -- plugin marketplaces (per-source marketplace toggle)
MPM_SOURCE_marketplaces_URL=https://github.com/your-org/mpm-manifests.git
MPM_SOURCE_marketplaces_REF=main
MPM_SOURCE_marketplaces_PATH=repo-specs/marketplaces/meta.xml
MPM_SOURCE_marketplaces_NAME=marketplaces
MPM_SOURCE_marketplaces_GITBASE=https://github.com/your-org
MPM_SOURCE_marketplaces_MARKETPLACE=true
```

---

## Architecture

```text
                    ┌─────────────────────────┐
                    │     MPM CLI           │
                    │ (search / add / install/│
                    │   clean / validate)     │
                    └───────────┬─────────────┘
                                │
               defines          │            uses
                                v
              ┌────────────────────────────────────────┐
              │       Manifest Repository              │
              │  - Top-level dependency manifests      │
              │  - Declares relationships between      │
              │    domain and automation repos         │
              └──────────────────┬─────────────────────┘
                                 │
        references               │                references
                                 │
             v                                       v
┌───────────────────────┐                ┌────────────────────────┐
│  Package Repositories │                │ Automation Repositories│
│ (build conventions,   │                │ (shared tasks,         │
│  linting, security)   │                │  validation, scanning) │
└────────────┬──────────┘                └───────────┬────────────┘
             │                                       │
             └───────────────────┬───────────────────┘
                                 │
                                 v
                   ┌────────────────────────────┐
                   │   mpm repo subsystem     │
                   │ (manifest-driven sync with │
                   │  envsubst + PEP 440)       │
                   │ Executes manifests, syncs  │
                   │ repos, manages workspace   │
                   └────────────────────────────┘
```

### How It Works

MPM's `mpm repo` subsystem orchestrates dependencies across Git
repositories via XML manifests. Manifests define what to clone, where to
place it, and how to wire it together.

The install lifecycle follows three steps per source:

1. **`mpm repo init`** -- Clones the manifest repository. `${VARIABLE}`
   placeholders remain as-is in the XML.
2. **`mpm repo envsubst`** -- Reads variables from `.mpm` (e.g.,
   `GITBASE`) and replaces `${VARIABLE}` placeholders in all manifest XML
   files.
3. **`mpm repo sync`** -- Clones packages using the now-resolved URLs into
   `.packages/`.

After all sources are synced, MPM aggregates their packages into a single
`.packages/` directory using symlinks, giving consumers a unified view
regardless of which source provided each package.

### Directory Structure After Install

Fetched artifacts live in the shared `MPM_HOME` store
(`$MPM_HOME`, default `~/.mpm-home`), content-addressed and deduped across
projects. Only `.mpm` and `.mpm.lock` live in (and are committed to)
the project itself:

```text
project/
  .mpm                            # Configuration (committed)
  .mpm.lock                       # Resolved SHAs (committed)

$MPM_HOME/                        # Shared store (default ~/.mpm-home; not in the repo)
  store/
    .mpm-data/
      sources/
        build/                      # Isolated source workspace
          .repo/
          .packages/
            my-build-conventions/
        marketplaces/               # Isolated source workspace
          .repo/
          .packages/
            my-marketplace-plugin/
    .packages/                      # Aggregated symlinks
      my-build-conventions -> \
        ../.mpm-data/sources/build/.packages/my-build-conventions
      my-marketplace-plugin -> \
        ../.mpm-data/sources/marketplaces/.packages/my-marketplace-plugin
```

Relocate the store for a single invocation with `--home` / `--store-dir`,
or persistently with the `MPM_HOME` environment variable. When the store
happens to live inside a git repository, `mpm install` writes a
`.gitignore` safety net into the store root so fetched artifacts are never
committed.

### Multi-Source Isolation

Each source is initialized and synced in its own isolated directory under
`.mpm-data/sources/<name>/`. Sources cannot interfere with each other --
each gets its own `mpm repo init` / `mpm repo sync` cycle. If two sources
produce a package with the same name, MPM detects the collision and fails
immediately with an actionable error message.

### Environment Variable Portability (envsubst)

The `envsubst` feature makes manifests portable across organizations. Instead
of hard-coding Git URLs in manifest XML, you use `${GITBASE}` placeholders:

```xml
<!-- Portable -- resolved from .mpm at install time -->
<remote name="origin" fetch="${GITBASE}"/>
```

Each dependency carries its own org base in `MPM_SOURCE_<alias>_GITBASE`,
which is exported as `${GITBASE}` while that source's manifests are
processed. Adopting MPM for a different organization means pointing a
dependency at a different base:

```properties
MPM_SOURCE_my_dep_GITBASE=https://github.com/your-company
```

CI/CD pipelines can override a dependency's base via environment variables
without modifying `.mpm` (environment variables take precedence over
`.mpm` file values):

```bash
MPM_SOURCE_my_dep_GITBASE=https://git.internal.company.com mpm install
```

For full documentation, see [docs/how-it-works.md](docs/how-it-works.md).

---

## Creating a Manifest Repository

A manifest repository contains `repo-specs/` with XML manifests that define
what packages to sync, from which repositories, and at which versions. **The
manifest repo IS the catalog** -- there is no separate `catalog/` directory.
Each catalog entry is a single `*.xml` file under `repo-specs/` (any
filename) that carries a nested `<catalog-metadata>` block; the
`<catalog-metadata><name>` child is the entry name consumers pass to
`mpm add <name>`. See
[docs/creating-manifest-repos.md](docs/creating-manifest-repos.md) for the
full catalog-author guide and
[docs/repo/manifest-format.md](docs/repo/manifest-format.md) for the
underlying XML schema.

### Structure

```text
my-manifest-repo/
  repo-specs/
    git-connection/
      remote.xml             # Git remotes with ${GITBASE} placeholders
    my-archetype/
      my-archetype-marketplace.xml  # Catalog entry (carries <catalog-metadata>)
      packages.xml           # Package repos with pinned versions
```

### Catalog entry

Each catalog entry is an XML file under `repo-specs/` (any filename)
containing exactly one nested `<catalog-metadata>` block. Required fields are `name`,
`display-name`, `description`, and `version`; recommended fields are `type`,
`owner-name`, `owner-email`, and `keywords` (comma-separated). The legacy
flat-attribute scheme (metadata as XML attributes) is rejected.

```xml
<package>
  <catalog-metadata>
    <name>my-archetype</name>
    <display-name>My Archetype</display-name>
    <description>Build conventions and lint config for service repos.</description>
    <version>1.0.0</version>
    <type>library</type>
    <owner-name>Platform Team</owner-name>
    <owner-email>platform@example.com</owner-email>
    <keywords>build,lint,conventions</keywords>
  </catalog-metadata>
  <include name="repo-specs/my-archetype/packages.xml" />
</package>
```

`mpm validate metadata` and `mpm catalog audit` enforce the
`<catalog-metadata>` contract.

### remote.xml -- Git Remote Definition

Defines where packages are hosted using `${GITBASE}` for portability:

```xml
<manifest>
  <remote name="origin" fetch="${GITBASE}" />
  <default remote="origin" revision="refs/tags/1.0.0" />
</manifest>
```

### packages.xml -- Package Declarations

Lists each package repository, its local path, and the pinned version:

```xml
<manifest>
  <include name="repo-specs/git-connection/remote.xml" />

  <project name="my-build-conventions"
           path=".packages/my-build-conventions"
           remote="origin"
           revision="refs/tags/1.0.0" />

  <project name="my-lint-config"
           path=".packages/my-lint-config"
           remote="origin"
           revision="refs/tags/2.1.0" />
</manifest>
```

### Entry-point manifest

The `*-marketplace.xml` catalog entry is the entry point referenced by the
`MPM_SOURCE_<name>_PATH` value that `mpm add` writes into `.mpm`. It
pulls in the package declarations via `<include>`:

```xml
<package>
  <catalog-metadata>
    <!-- ... required + recommended fields ... -->
  </catalog-metadata>
  <include name="repo-specs/my-archetype/packages.xml" />
</package>
```

### Include Chains for Hierarchy

Manifests can include other manifests via `<include>` tags, forming a
hierarchy. This enables cascading configurations where common packages are
defined once and specialized packages are layered on top:

```text
my-archetype-marketplace.xml
  └── packages.xml (leaf -- e.g., specific project type)
        └── packages.xml (framework level)
              └── packages.xml (language level)
                    └── packages.xml (common/base)
```

Each level includes its parent and adds its own package entries. The
`mpm repo` subsystem recursively resolves all includes, accumulating a
unified set of packages.

### Updating Package Versions

1. Tag the package repository with the new semver version
2. Update the `revision` attribute in the corresponding `packages.xml`
3. Run `mpm validate xml` to verify manifests remain valid
4. Tag and push the manifest repository

Projects pick up the new versions on next `mpm install`.

For more details, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Creating Packages

A package is a Git repository containing automation scripts (configuration
files, shell scripts, etc.) tagged with semver versions. MPM syncs packages
to `.packages/` where build tools can discover and apply them.

### Package Structure

```text
my-package/
  automation-script.sh        # Shell scripts, config files, etc.
  config/                     # Optional: configuration files
  README.md                   # Package documentation
  CHANGELOG.md                # Version history
```

### Versioning

Use [semantic versioning](https://semver.org/) with Git tags:

- **MAJOR** -- Breaking changes (renamed tasks, removed config, changed
  behavior)
- **MINOR** -- New features (new tasks, new config options)
- **PATCH** -- Bug fixes (corrected config, fixed task behavior)

```bash
git tag -a 1.0.0 -m "Release 1.0.0"
git push origin 1.0.0
```

### Registering a Package

Add the package to a manifest's `packages.xml`:

```xml
<project name="my-package"
         path=".packages/my-package"
         remote="origin"
         revision="refs/tags/1.0.0" />
```

### Symlinks via linkfile

Some packages contain assets (configuration files, templates) that tools
expect at conventional paths. The `<linkfile>` element creates symlinks from
the package directory to the project root:

```xml
<project name="my-lint-config"
         path=".packages/my-lint-config"
         remote="origin"
         revision="refs/tags/1.0.0">
  <linkfile src="config/checkstyle/checkstyle.xml"
            dest="config/checkstyle/checkstyle.xml" />
</project>
```

After `mpm repo sync`, the project has `config/checkstyle/checkstyle.xml`
as a symlink pointing into `.packages/`. These symlinked paths should be
gitignored since they are regenerated by `mpm install`.

---

## Creating Marketplace Packages

Marketplace packages use `<linkfile>` symlinks to expose plugins to Claude
Code. They follow a cascading manifest hierarchy where each level includes
its parent, enabling shared tools across project types while adding
specialized plugins at each level.

### Marketplace Manifest Structure

```xml
<manifest>
  <!-- Include shared remote definitions -->
  <include name="repo-specs/git-connection/remote.xml" />

  <!-- Add this level's marketplace project -->
  <project name="my-marketplace-packages"
           path=".packages/my-marketplace-dev-lint"
           remote="origin"
           revision="refs/tags/development/dev-lint/1.0.0">
    <linkfile src="development/dev-lint"
              dest="${CLAUDE_MARKETPLACES_DIR}/my-marketplace-dev-lint" />
  </project>
</manifest>
```

### Key Requirements

- All `<linkfile dest>` attributes must start with
  `${CLAUDE_MARKETPLACES_DIR}/`
- Each `<project path>` must be unique across all manifests
- The per-source `MPM_SOURCE_<alias>_MARKETPLACE` flag in `.mpm` must be
  set to `true` for the marketplace source
- `CLAUDE_MARKETPLACES_DIR` must be present in `.mpm` (auto-added by
  `mpm add` / `mpm marketplace enable`; hand-set only to override the dir)

### Naming Convention

Marketplace manifest files must be named `*-marketplace.xml` (e.g.,
`claude-history-marketplace.xml`,
`immutable-audit-trail-marketplace.xml`).
The `mpm validate marketplace` command discovers files matching this
pattern under `repo-specs/`.

### Cascading Includes

Manifests support cascading `<include>` chains where each level includes its
parent. This enables shared remote definitions, common project entries, and
layered composition across project types. Currently marketplace manifests use
a flat structure (each manifest includes `remote.xml` directly), but
cascading hierarchies are fully supported when needed.

### Validation

```bash
mpm validate marketplace
```

This checks linkfile destination prefixes, include chain integrity, project
path uniqueness, and revision format validity.

For full documentation, see
[docs/claude-marketplaces-guide.md](docs/claude-marketplaces-guide.md).

---

## Manifest Features (PEP 440 Constraints)

MPM adds the following capabilities to manifest-driven sync:

### PEP 440 Version Constraints in Manifests

`<project revision>` accepts [PEP 440](https://peps.python.org/pep-0440/)
version constraint syntax in addition to a branch, tag, or commit SHA.
Constraints resolve to the best matching tag at sync time.

#### How It Works

The resolver splits the `revision` attribute at the last `/` into a tag-path
prefix and a constraint. It filters available tags by that prefix, evaluates
the constraint, and returns the highest matching version. The prefix is
optional: `refs/tags/<pep440>` (and a bare constraint such as `~=1.0.0`)
resolves against the bare `refs/tags/` namespace for single-purpose repos,
while `refs/tags/<name>/<pep440>` scopes to that namespace.

```text
revision="refs/tags/example/development/dev-lint/~=1.2.0"
         |------------- prefix ----------------| |- constraint -|

1. Filter tags starting with  refs/tags/example/development/dev-lint/
2. Parse version suffixes:    1.0.0, 1.2.0, 1.2.3, 1.3.0, 2.0.0
3. Evaluate ~=1.2.0:          1.2.0   1.2.3   (others excluded)
4. Return highest match:      refs/tags/example/development/dev-lint/1.2.3
```

#### Supported Constraint Types

| Operator | Syntax | Meaning |
| --- | --- | --- |
| Patch-compatible | `~=1.2.0` | `>=1.2.0, <1.3.0` (any patch in 1.2.x) |
| Range | `>=1.0.0,<2.0.0` | Any version up to (not including) 2.0.0 |
| Wildcard | `*` | Any available version (selects the latest) |
| Exact | `==1.2.3` | Only version 1.2.3 |
| Minimum | `>=1.0.0` | 1.0.0 or higher |
| Exclusion | `!=1.0.1` | Any version except 1.0.1 |

#### XML Escaping

Certain characters are reserved in XML and must be escaped inside
attribute values. The most common case is `<` in range constraints:

| Character | Escape | When required |
| --- | --- | --- |
| `<` | `&lt;` | Always (reserved XML character) |
| `&` | `&amp;` | Always (reserved XML character) |
| `"` | `&quot;` | Inside `"` delimited attributes |
| `'` | `&apos;` | Inside `'` delimited attributes |
| `>` | `&gt;` | Optional (`>` also valid in attributes) |

Example with range constraint:

```xml
<project name="my-package"
         path=".packages/my-package"
         remote="origin"
         revision="refs/tags/my-package/>=1.0.0,&lt;2.0.0" />
```

### PEP 440 Version Resolution in .mpm

The CLI supports PEP 440 constraint syntax in `MPM_SOURCE_<alias>_REF`
entries in `.mpm`. Constraints are resolved against available git tags
before being passed to the sync engine.

#### Supported Operators

| Operator | Syntax | Meaning |
| --- | --- | --- |
| Compatible release | `~=1.2.0` | `>=1.2.0, <1.3.0` |
| Range | `>=1.0.0,<2.0.0` | Any version in range |
| Exact | `==1.2.3` | Only 1.2.3 |
| Minimum | `>=1.0.0` | 1.0.0 or higher |
| Exclusion | `!=1.0.1` | Any version except 1.0.1 |
| Wildcard | `*` | Latest available |

Plain strings without PEP 440 operators pass through unchanged.

#### Prefixed Constraints (MPM_SOURCE_\<alias\>_REF)

Source refs support an optional `refs/tags/` prefix. This is recommended
because the resolved value is passed to `mpm repo init -b`, which accepts
full ref paths:

```properties
# Resolves to refs/tags/1.1.2 -- works directly with mpm repo init -b
MPM_SOURCE_build_REF=refs/tags/~=1.1.0

# Namespaced -- only considers tags under that path
MPM_SOURCE_build_REF=refs/tags/dev/python/my-lib/~=1.2.0

# Also supported -- resolves against all tags
MPM_SOURCE_build_REF=~=1.1.0
```

For full details, see [docs/version-resolution.md](docs/version-resolution.md).

### Absolute Linkfile Destinations

`<linkfile dest>` accepts absolute paths after `envsubst` expansion, enabling
marketplace symlinks to directories outside the project (e.g.,
`${CLAUDE_MARKETPLACES_DIR}/...`).

---

## SSH Authentication Setup

MPM uses HTTPS Git URLs internally. If you authenticate with GitHub via SSH
instead of HTTPS tokens, configure Git to rewrite HTTPS URLs to SSH globally:

```bash
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

This tells Git to use SSH for all `github.com` requests, which MPM's
`git clone`, `git ls-remote`, and `mpm repo` commands will then use
automatically.

**Note:** The `--global` flag is required. Using `--local` will not work
because `mpm repo` operates in its own working directories with their own
local Git configuration.

For other Git hosts, adjust the URL accordingly:

```bash
git config --global url."git@gitlab.com:".insteadOf "https://gitlab.com/"
git config --global \
  url."git@bitbucket.org:".insteadOf "https://bitbucket.org/"
```

To verify the configuration:

```bash
git config --global --get-regexp url
```

---

## Developer Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### Install from Source

```bash
make install-dev
```

### Set Up Git Hooks

```bash
make install-hooks
```

### Run Tests

```bash
make test              # All tests with coverage
make test-unit         # Unit tests only
make test-integration  # Integration tests (modules end-to-end)
make test-functional   # Functional tests (CLI via subprocess)
make test-scenarios    # End-to-end scenario tests
make test-cov          # Tests with coverage report
```

### Build

```bash
make publish       # Clean, build, and check distribution
```

### Project Structure

```text
src/mpm_cli/
  cli.py              # Entry point
  commands/           # Subcommand implementations
  core/               # Core logic (install, clean, mpm parsing, lockfile)
  completions/        # Shell-completion generators
  utils/              # Shared helpers
  repo/               # mpm repo subsystem (manifest sync, PEP 440)
tests/                # Unit and functional tests
docs/                 # Configuration, lifecycle, version resolution docs
pyproject.toml        # Package config (hatchling, entry point: mpm)
```

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit conventions, PR process,
and how the automated release pipeline works.

### CI/CD Pipeline

This project uses a fully automated SDLC pipeline:

1. **PR Validation** -- Lint, build, test (90% coverage), security scan on
   every PR
2. **Main Branch Validation** -- Full validation + CodeQL on merge to main
3. **Manual QA Approval** -- Human gate before release
4. **Automated Release** -- Semantic versioning from conventional commit
   prefixes, changelog generation, tagging
5. **PyPI Publishing** -- Automated publish via OIDC trusted publishing

PR titles must follow
[Conventional Commits](https://www.conventionalcommits.org/) format
(e.g., `feat: add feature`, `fix: resolve bug`) as they drive automatic
version bumps.

---

## Documentation

- [How It Works](docs/how-it-works.md) -- Technical deep-dive into MPM
  internals
- [Setup Guide](docs/setup-guide.md) -- Step-by-step setup for new and
  existing projects
- [Configuration](docs/configuration.md) -- `.mpm` format and variable
  expansion
- [Lifecycle](docs/lifecycle.md) -- Install and clean lifecycle step-by-step
- [Multi-Source Guide](docs/multi-source-guide.md) -- Configuring multiple
  manifest sources
- [Version Resolution](docs/version-resolution.md) -- PEP 440 resolver
  details
- [Creating Manifest Repos](docs/creating-manifest-repos.md) -- Authoring
  manifest repositories
- [Creating Packages](docs/creating-packages.md) -- Authoring individual
  package repositories
- [Claude Marketplaces Guide](docs/claude-marketplaces-guide.md) --
  Marketplace architecture and plugin lifecycle
- [Pipeline Integration](docs/pipeline-integration.md) -- Using MPM tasks
  in CI/CD pipelines
- [Integration Testing](docs/integration-testing.md) -- End-to-end CLI test
  plan
- [mpm repo reference](docs/repo/README.md) -- Manifest format, `.repo/`
  layout, hooks, smart sync, Python support (Windows is not currently
  supported; see [Platform support](#platform-support) and use WSL2)
- [Contributing](CONTRIBUTING.md) -- How to create and maintain MPM
  packages and marketplaces
- [Privacy](docs/privacy.md) -- mpm collects no usage telemetry; what it does
  and does not send over the network

---

## License

Apache 2.0. See [LICENSE](LICENSE).
