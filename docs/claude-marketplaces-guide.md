# Claude Code Marketplaces Guide

This guide documents the Claude Code marketplace architecture used by MPM
to manage, distribute, and install Claude Code marketplace plugins.

---

## Marketplace Manifest Structure

Marketplace manifest files are named `*-marketplace.xml` (e.g.,
`claude-history-marketplace.xml`). Each manifest includes shared remote
definitions via `<include>` and declares its `<project>` entries.

Manifests support cascading `<include>` chains where each level includes its
parent, enabling shared remote definitions, common project entries, and layered
composition. Currently marketplace manifests use a flat structure (each includes
`remote.xml` directly), but cascading hierarchies are fully supported.

### Naming Convention

A catalog entry is any `*.xml` file under `repo-specs/` that contains a
`<catalog-metadata>` block. The filename is unrestricted: `*-marketplace.xml`
is a common convention, but `widget.xml` or `my-tool.xml` work equally well.
The `mpm validate marketplace` command discovers every such entry under
`repo-specs/`. Files with no `<catalog-metadata>` block (e.g., shared includes
like `remote.xml`, `packages.xml`) are not entries and are not validated as
marketplace manifests -- they are still checked by `mpm validate xml`.

### Example Manifest

```xml
<manifest>
  <include name="repo-specs/git-connection/remote.xml" />

  <project name="mpm-claude-marketplaces"
           path=".packages/mpm-claude-marketplaces-common-claude-tools-history"
           remote="origin"
           revision="main">
    <linkfile src="common/claude-tools/history"
              dest="${CLAUDE_MARKETPLACES_DIR}/mpm-claude-marketplaces-common-claude-tools-history" />
  </project>
</manifest>
```

---

## Path Flattening Algorithm

Each marketplace project in the hierarchy must have a unique `path` attribute.
The path flattening algorithm converts the hierarchical directory structure
into a flat project path with a namespace prefix.

### Naming Pattern

```text
.packages/mpm-claude-marketplaces-{hierarchy-prefix}-{marketplace-name}
```

### Flattening Examples

| Hierarchy Level | Flattened Path |
|---|---|
| CLI (leaf) | `.packages/mpm-claude-marketplaces-example-cli-agent` |
| Argparse | `.packages/mpm-claude-marketplaces-example-argparse-scaffold` |
| Make | `.packages/mpm-claude-marketplaces-example-make-utils` |
| Python | `.packages/mpm-claude-marketplaces-example-python-helpers` |
| Development | `.packages/mpm-claude-marketplaces-example-dev-lint` |
| Example | `.packages/mpm-claude-marketplaces-example-example-tools` |

### Uniqueness Validation

The validation command (`mpm validate marketplace`) checks that all
`<project path="...">` values are unique across all manifests. This prevents
path collisions when aggregating from multiple sources. If two manifests
define the same path, validation fails with a clear error identifying the
duplicate.

---

## Linkfile Symlink Chain

Linkfiles are XML elements within `<project>` tags that create symlinks from
cloned package directories to a centralized Claude Code marketplaces directory.
This allows Claude Code to discover and load marketplace plugins at runtime.

### Linkfile Structure

```xml
<project name="mpm-claude-marketplaces"
         path=".packages/mpm-claude-marketplaces-example-dev-lint"
         remote="origin"
         revision="refs/tags/example/development/dev-lint/1.0.0">
  <linkfile src="common/example/development/dev-lint"
            dest="${CLAUDE_MARKETPLACES_DIR}/mpm-claude-marketplaces-example-dev-lint" />
</project>
```

### How Linkfiles Work

1. **Source (`src`)** -- A relative path within the cloned package repository
   pointing to the marketplace plugin directory
2. **Destination (`dest`)** -- Must use the `${CLAUDE_MARKETPLACES_DIR}`
   environment variable, resolved at install time by `repo envsubst`
3. **Execution** -- When `repo sync` runs, it creates a symlink from the
   destination to the source package directory
4. **Discovery** -- Claude Code scans `${CLAUDE_MARKETPLACES_DIR}` to find
   all registered marketplace plugins

### Validation Rules

All linkfile `dest` attributes must start with `${CLAUDE_MARKETPLACES_DIR}/`.
The following patterns are rejected:

- Absolute paths (e.g., `/opt/marketplaces/...`)
- Relative paths (e.g., `.packages/...`)
- Bare names without the variable prefix

---

## Install and Uninstall Lifecycle

The marketplace install/uninstall lifecycle is controlled per source by the
`MPM_SOURCE_<alias>_MARKETPLACE` flag in `.mpm`. When any source sets it
to `true`, MPM manages Claude Code marketplace plugin registration and
unregistration. Toggle it with `mpm marketplace enable <alias>` /
`mpm marketplace disable <alias>`, or inspect the effective setting with
`mpm marketplace status`.

The global `CLAUDE_MARKETPLACES_DIR` header that `mpm install` needs is
auto-managed: `mpm add` of a `claude-marketplace` entry and
`mpm marketplace enable` insert
`CLAUDE_MARKETPLACES_DIR=${HOME}/.claude-marketplaces` once when it is absent,
and `mpm remove` / `mpm marketplace disable` prune it once the last
marketplace dependency is gone. Hand-set the line only to override the
directory; a custom value is preserved and never clobbered. So the canonical
`mpm add <claude-marketplace> ; mpm install` flow works with no manual
edit to `.mpm`.

### Install Lifecycle

When a user runs `mpm install .mpm`:

1. **Parse `.mpm`** -- Read configuration and validate required variables
2. **Prepare marketplace directory** -- Create `${CLAUDE_MARKETPLACES_DIR}`
   if it does not exist; clear existing contents for a clean slate
3. **For each source in alphabetical order:**
   - Run `repo init` with the source URL, revision, and manifest path
   - Run `repo envsubst` to resolve `${CLAUDE_MARKETPLACES_DIR}` and
     `${GITBASE}` placeholders
   - Run `repo sync` to clone packages and create linkfile symlinks
4. **Aggregate symlinks** -- Create symlinks in `.packages/` for each
   source's packages
5. **Collision detection** -- Fail immediately if two sources produce the
   same package name
6. **Install plugins** -- The MPM CLI locates the `claude` binary, discovers
   marketplace entries and plugins, registers marketplaces, and installs
   plugins via the Claude Code CLI

### Uninstall Lifecycle

When a user runs `mpm clean .mpm`, the order is
critical -- uninstall plugins before removing files:

1. **Uninstall plugins** -- The MPM CLI locates the `claude` binary, discovers
   marketplace entries and plugins, uninstalls each plugin, and removes
   marketplace registrations via the Claude Code CLI
2. **Remove marketplace directory** -- Delete `${CLAUDE_MARKETPLACES_DIR}`
   to prevent stale plugin references
3. **Remove `.packages/`** -- Delete all synced package directories
4. **Remove `.mpm-data/`** -- Delete MPM state directory

### Failure Handling

- If any marketplace registration or plugin install fails, `mpm install`
  aborts immediately with an actionable error message
- If any plugin uninstall or marketplace removal fails, `mpm clean` aborts
  immediately with an actionable error message
- All failures surface clear diagnostics identifying the failed step
