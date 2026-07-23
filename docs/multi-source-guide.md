# Multi-Source MPM Guide

This guide documents how MPM supports multiple manifest sources,
enabling teams to compose packages from different repositories
and organizations.

---

> **Recommended: use `mpm add` to create `MPM_SOURCE_*` triples.**
> Running `mpm add <name>@<spec> --catalog-source <url>@<ref>`
> is the preferred way to add a new `MPM_SOURCE_<name>_{URL,REF,PATH}`
> triple to `.mpm`. The command handles source-name normalization
> (lowercase, replace `-` with `_`) automatically, resolves the default
> spec to the manifest repo's latest PEP 440 tag when no `@<spec>` is
> given, and performs collision detection before writing the file --
> all of which are error-prone to reproduce by hand.
>
> See `docs/list-and-add.md` for the full `mpm add` reference, and
> `docs/catalogs-explained.md` for a first-time on-ramp to finding a
> catalog source.
>
> **When hand-writing remains valid:** hand-editing the `MPM_SOURCE_*`
> triples directly is still appropriate for two edge cases:
>
> - You need a `MPM_SOURCE_<name>_PATH` that overrides the default
>   path declared in `<catalog-metadata>` (for example, pointing at a
>   secondary manifest file inside the same repo).
> - You are pinning a bare branch name to a project that is not tracked
>   by any `<catalog-metadata>`-aware manifest repo, so `mpm search`
>   cannot discover it.
>
> Outside these cases, prefer `mpm add` to keep `.mpm` consistent
> and free of normalization or collision errors.

---

## Named Source Format (.mpm)

MPM auto-discovers sources from `MPM_SOURCE_<name>_URL` variable
patterns in `.mpm`. Each source is defined by four required variables
(plus an optional `_MARKETPLACE` toggle and an open set of per-dependency
env-var lines) following the `MPM_SOURCE_<name>_<property>` naming
convention:

|Suffix|Required?|Purpose|
|---|---|---|
|`_URL`|Required|Git repository URL for the manifest source|
|`_REF`|Required|Branch name, exact tag ref, or PEP 440 version constraint|
|`_PATH`|Required|Path to the entry-point manifest XML within the repository|
|`_NAME`|Required|Original catalog entry name for the source (written by `mpm add`)|
|`_MARKETPLACE`|Optional|Set to `true` to enable the Claude marketplace lifecycle for this source; absence means disabled (mpm never writes `=false`)|
|`_<VAR>`|Optional|Per-dependency env var (e.g. `_GITBASE`) supplying one `${VAR}` the source's manifest references; `GITBASE` is auto-derived from the source URL by `mpm add`|

Sources are processed in alphabetical order by name.

See the [.mpm variable reference](../README.md#mpm-variable-reference)
for the full variable table.

### Source Naming Convention

The `<name>` in `MPM_SOURCE_<name>_URL` is a free-form identifier --
MPM extracts it by stripping the `MPM_SOURCE_` prefix and the `_URL`
suffix, treating everything in between as the source name. The name has
no semantic meaning to the CLI; it is purely organizational.

**The CLI treats all sources identically.** Every source goes through the
same processing pipeline: `repo init` → `repo envsubst` → `repo sync`.
The source name does not influence how the CLI processes it. What a source
delivers is determined entirely by its **manifest content**.

A source delivers build packages when its manifest contains `<project>`
entries that clone package repositories into `.packages/`. A source
delivers marketplace plugins when its manifest contains `<project>` entries
with `<linkfile>` elements that create symlinks into
`${CLAUDE_MARKETPLACES_DIR}`. It is the symlink destination -- not the
source name -- that causes the synced content to be recognized as a
marketplace plugin. When any source sets
`MPM_SOURCE_<alias>_MARKETPLACE=true`, the CLI scans the entire
`${CLAUDE_MARKETPLACES_DIR}` directory after all sources have synced and
installs every plugin found there, regardless of which source created the
symlink.

### Recommended Naming Convention

Choose source names that describe what the source provides. This makes
`.mpm` files self-documenting for humans and AI agents without needing
to inspect the manifest XML content. Common prefixes include:

|Prefix|Purpose|
|---|---|
|`build`|Build tooling packages (linting, formatting, conventions)|
|`marketplaces`|Claude Code marketplace plugins|
|`pipelines`|CI/CD pipeline packages|
|`runners`|Task runner packages|
|`tf-deploy-templates`|Terraform deployment templates|
|`sonarqube-config`|SonarQube configuration packages|

These prefixes are conventions, not requirements. Any descriptive name
that communicates the source's purpose to your team is appropriate.

When multiple sources serve the same concern, append a hyphenated qualifier
to distinguish them (e.g., `build-core`, `build-infra`,
`marketplaces-core`, `marketplaces-team`, `pipelines-ci`, `pipelines-cd`).

**Use hyphens to create descriptive, multi-word source names.** Hyphens
keep the three-field structure (`MPM_SOURCE_` + `<name>` + `_SUFFIX`)
visually unambiguous:

```text
MPM_SOURCE_<name>_URL
     ^1         ^2    ^3

Field 1: MPM_SOURCE_   (fixed prefix)
Field 2: <name>          (free-form identifier -- use hyphens for multi-word names)
Field 3: _URL            (fixed suffix: _URL, _REF, _PATH, or _MARKETPLACE)
```

**Single source per concern:**

```properties
MPM_SOURCE_build_URL=...
MPM_SOURCE_marketplaces_URL=...
MPM_SOURCE_pipelines_URL=...
```

**Multiple sources per concern -- hyphenate the name:**

```properties
MPM_SOURCE_build-core_URL=...
MPM_SOURCE_build-infra_URL=...
MPM_SOURCE_marketplaces-core_URL=...
MPM_SOURCE_marketplaces-team_URL=...
MPM_SOURCE_pipelines-ci_URL=...
MPM_SOURCE_pipelines-cd_URL=...
```

There is no limit on the number of sources. The CLI discovers all
`MPM_SOURCE_<name>_URL` keys, extracts each `<name>`, and processes
them in alphabetical order.

> **Note:** Underscores within the name (e.g., `MPM_SOURCE_build_core_URL`)
> also work -- the parser strips only the known prefix and suffix. However,
> hyphens are recommended because they visually distinguish the source name
> from the surrounding underscore-delimited fields.

### Example: Single Build and Marketplace Source

```properties
# Sources are auto-discovered from MPM_SOURCE_<name>_URL patterns.
# No explicit source list is needed -- names are extracted from _URL keys
# and processed in alphabetical order.

# Build tools source -- pinned to exact tag
MPM_SOURCE_build_URL=https://example.com/org/mpm-build-tools.git
MPM_SOURCE_build_REF=refs/tags/2.0.0
MPM_SOURCE_build_PATH=repo-specs/build-meta.xml
MPM_SOURCE_build_NAME=mpm-build-tools

# Marketplace source -- compatible release constraint (>=1.1.0, <1.2.0)
MPM_SOURCE_marketplaces_URL=https://example.com/org/mpm-marketplace.git
MPM_SOURCE_marketplaces_REF=refs/tags/~=1.1.0
MPM_SOURCE_marketplaces_PATH=repo-specs/common/plugins/plugins-marketplace.xml
MPM_SOURCE_marketplaces_NAME=mpm-marketplace

# CLAUDE_MARKETPLACES_DIR is the single workspace-wide marketplace path
# (resolved from the OS environment when omitted here). Each source's
# ${GITBASE} is auto-derived per dependency into MPM_SOURCE_<alias>_GITBASE
# by mpm add; there is no global GITBASE.
CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces
```

### Example: Multiple Build and Marketplace Sources

When a project needs packages from several repositories, add additional
sources with hyphenated names. Each source gets its own isolated workspace
and all packages are aggregated into a unified `.packages/` directory.

```properties
# Build sources -- each points to a different manifest repository
MPM_SOURCE_build-core_URL=https://example.com/org/mpm-build-core.git
MPM_SOURCE_build-core_REF=refs/tags/~=2.0.0
MPM_SOURCE_build-core_PATH=repo-specs/build-meta.xml
MPM_SOURCE_build-core_NAME=mpm-build-core

MPM_SOURCE_build-infra_URL=https://example.com/org/mpm-build-infra.git
MPM_SOURCE_build-infra_REF=refs/tags/>=1.0.0,<2.0.0
MPM_SOURCE_build-infra_PATH=repo-specs/build-meta.xml
MPM_SOURCE_build-infra_NAME=mpm-build-infra

MPM_SOURCE_build-security_URL=https://example.com/org/mpm-build-security.git
MPM_SOURCE_build-security_REF=refs/tags/~=1.4.0
MPM_SOURCE_build-security_PATH=repo-specs/build-meta.xml
MPM_SOURCE_build-security_NAME=mpm-build-security

# Marketplace sources -- each provides Claude Code plugins and opts in to
# the marketplace lifecycle with its own per-source MPM_SOURCE_<alias>_MARKETPLACE flag
MPM_SOURCE_marketplaces-core_URL=https://example.com/org/mpm-marketplace-core.git
MPM_SOURCE_marketplaces-core_REF=main
MPM_SOURCE_marketplaces-core_PATH=repo-specs/common/core/core-marketplace.xml
MPM_SOURCE_marketplaces-core_NAME=mpm-marketplace-core
MPM_SOURCE_marketplaces-core_MARKETPLACE=true

MPM_SOURCE_marketplaces-team_URL=https://example.com/org/mpm-marketplace-team.git
MPM_SOURCE_marketplaces-team_REF=main
MPM_SOURCE_marketplaces-team_PATH=repo-specs/common/team/team-marketplace.xml
MPM_SOURCE_marketplaces-team_NAME=mpm-marketplace-team
MPM_SOURCE_marketplaces-team_MARKETPLACE=true

# CLAUDE_MARKETPLACES_DIR is the single workspace-wide marketplace path
# (resolved from the OS environment when omitted here). Each source's
# ${GITBASE} is auto-derived per dependency into MPM_SOURCE_<alias>_GITBASE
# by mpm add; there is no global GITBASE.
CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces
```

Processing order (alphabetical): `build-core` → `build-infra` →
`build-security` → `marketplaces-core` → `marketplaces-team`.

`MPM_SOURCE_<name>_REF` accepts a branch name, an exact tag ref,
or a PEP 440 constraint. When a constraint is used, the CLI resolves it
against available tags before passing the result to `repo init -b`. Using
the `refs/tags/` prefix is recommended -- it scopes resolution to tags
and produces a full ref path compatible with `repo init`. See
[version-resolution.md](version-resolution.md) for all supported
operators and syntax.

Sources are auto-discovered from `MPM_SOURCE_<name>_URL` variable
patterns and processed in alphabetical order by name. Environment
variables override `.mpm` file values, allowing the same configuration
to work across environments.

---

## Source Isolation

Each source is initialized and synced in its own isolated directory
under `.mpm-data/sources/<name>/`. This prevents sources from interfering
with each other.

### Directory Structure

Each source name becomes a directory under `.mpm-data/sources/`:

```text
.mpm-data/
└── sources/
    ├── build-core/               # From MPM_SOURCE_build-core_*
    │   ├── .repo/
    │   └── .packages/
    │       └── mpm-build-conventions/
    ├── build-infra/              # From MPM_SOURCE_build-infra_*
    │   ├── .repo/
    │   └── .packages/
    │       └── mpm-terraform-modules/
    ├── marketplaces-core/        # From MPM_SOURCE_marketplaces-core_*
    │   ├── .repo/
    │   └── .packages/
    │       └── mpm-claude-marketplaces-example-dev-lint/
    └── marketplaces-team/        # From MPM_SOURCE_marketplaces-team_*
        ├── .repo/
        └── .packages/
            └── mpm-claude-marketplaces-team-tools/
```

### Why Isolation Matters

- Each source gets its own `repo init` / `repo sync` cycle
- Sources cannot overwrite each other's `.repo/` metadata
- Failures in one source do not corrupt another source's state
- Sources can use different manifest URLs, revisions, and paths

---

## Symlink Aggregation

After all sources are synced, MPM aggregates their packages into
a single top-level `.packages/` directory using symlinks. This gives
consumers a unified view of all packages regardless of which source
provided them.

### Aggregation Process

1. For each source in alphabetical order, scan
   `.mpm-data/sources/<name>/.packages/`
2. For each package directory found, create a symlink in the top-level
   `.packages/`
3. The symlink points from `.packages/<pkg-name>` to
   `.mpm-data/sources/<name>/.packages/<pkg-name>`

### Result

```text
.packages/                         # Unified view (symlinks)
├── mpm-build-conventions
│   -> .mpm-data/sources/build-core/.packages/mpm-build-conventions
├── mpm-terraform-modules
│   -> .mpm-data/sources/build-infra/.packages/mpm-terraform-modules
├── mpm-claude-marketplaces-example-dev-lint
│   -> .mpm-data/sources/marketplaces-core/.packages/...
└── mpm-claude-marketplaces-team-tools
    -> .mpm-data/sources/marketplaces-team/.packages/...
```

Consumers reference packages from `.packages/` without needing to know
which source provided them.

---

## Collision Detection

MPM's install conflict check is keyed on the package **destination path**
(`.packages/<name>`), not on the repository URL. Two sources may fetch the
**same repository at different commits** as long as their `<project>` entries
land at **different** destination paths -- this is the mono-repo case: install
any version of package A and any version of package B even when both live in the
same repo under different per-package tags. The only hard error is two sources
resolving the **same** `.packages/<name>` slot to **different content**.

When two sources produce a package at the same destination with different
content, MPM detects the collision and fails immediately with an actionable
error message.

### How It Works

A pre-flight check (`mpm install`) groups every source's resolved content pins
by destination path; a path claimed with more than one content SHA is a
`PackagePathConflictError` (the same path at the same SHA is a benign duplicate).
During symlink aggregation, MPM additionally tracks which source provided each
package name as an on-disk backstop: if a package name already exists from a
previous source, aggregation aborts with an error identifying both the
conflicting sources and the duplicate package name.

### Example Error

```text
Error: Package collision for 'mpm-shared-utils':
  provided by source 'build-core' and source 'build-infra'
```

### Resolution

- Rename one of the conflicting packages in its manifest
- Remove the duplicate from one source
- Remove the `MPM_SOURCE_<name>_*` variables for the source with the
  unwanted duplicate

Collision detection runs after all sources are synced, ensuring that
the error is caught before any consumer code runs.
