# mpm search, add, and remove

Operator-facing reference for three core dependency-management
commands: `mpm search`, `mpm add`, and `mpm remove`.

For first-time setup see
[docs/catalogs-explained.md](catalogs-explained.md)
(created by E8-F1-S1-T01).
For the canonical environment-variable table see
[docs/configuration.md](configuration.md).

---

## mpm search

Discover catalog entries available in a manifest repo.

### list -- Synopsis

```text
mpm search [--catalog-source <git-url>@<ref>]
           [<substring>]
           [--detail] [--tree] [--max-depth N]
           [-A | --all] [--limit N | --no-limit]
           [--since-version <spec>]
           [--regex <pattern>] [--match-fields <csv>]
           [--format {names,json}]
           [--no-filter-required]
           [--no-color]
```

### list -- How it works

`mpm search` clones the manifest repo identified by
`--catalog-source` (or `MPM_CATALOG_SOURCES`) and walks every
`repo-specs/**/*.xml` file. One entry is emitted per XML file whose
`<catalog-metadata>` block contains the required fields (the filename is
unrestricted -- the `-marketplace.xml` suffix is a convention, not a
requirement). Entry name = `<catalog-metadata><name>`.

The legacy `catalog/<name>/` directory inside a manifest repo is
ignored; `mpm search` reads only the XML manifests.

### list -- Default output

```text
$ mpm search \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
package-a
package-b
package-c
```

One entry name per line. Output is streamed line-by-line; large
manifest repos do not buffer the full result in memory. The output
is pipeable directly into `mpm add`.

### list -- Flags

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--detail` | off | Per-entry name, type, description, version. |
| `--tree` | off | Dependency tree per entry. Excl. -A/--all. |
| `--max-depth N` | unlimited | Cap tree depth. 0 = entry only. |
| `-A`, `--all` | off | Walk historical versions. Excl. --tree. |
| `--limit N` | `50` | Cap for -A/--all. |
| `--no-limit` | off | Remove -A/--all cap. |
| `--since-version spec` | none | Restrict -A/--all to PEP 440 spec. |
| `--format {names,json}` | `names` | Output format. Env: MPM_LIST_FORMAT. |
| `substr` (positional) | none | Filter entries by substring. |
| `--regex pattern` | none | Filter by regex on same four fields. |
| `--match-fields csv` | all | Narrow filter fields. Requires a filter. |
| `--no-filter-required` | off | Skip filter for --tree on large catalogs. |
| `--catalog-source url[@ref]` | env | Catalog source; `@ref` optional. Env: MPM_CATALOG_SOURCES |
| `--catalog-default-branch name` | env | Branch used when the catalog source omits `@ref`. Env: MPM_CATALOG_DEFAULT_BRANCH (default `main`; `auto` = remote HEAD). |
| `--no-color` | auto | Disable color output. |

### list -- Mutually exclusive combinations

The following combinations are hard errors:

| Combination | Error |
| ----------------------------------------- | ------ |
| `--tree` + `-A`/`--all` | Hard error |
| `--match-fields` without filter | Hard error |

`--tree` + `-A`/`--all`:

```text
ERROR: --tree and -A/--all are mutually exclusive. Use --tree for dependency tree rendering, or -A/--all to list all available versions. These flags cannot be combined.
```

`--match-fields` without `<substring>` or `--regex`:

```text
ERROR: --match-fields requires a filter. Supply a positional <substring> or --regex <pattern> together with --match-fields.
```

### list -- Output format examples

**`--format names` (default)**

```text
$ mpm search \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
package-a
package-b
package-c
```

**`--format json`**

```json
[
  {"name": "package-a"},
  {"name": "package-b"},
  {"name": "package-c"}
]
```

**`--detail --format json`**

```json
[
  {
    "name": "package-a",
    "display-name": "Package A",
    "description": "Example dependency",
    "version": "1.4.2",
    "type": "library"
  }
]
```

### list -- Streaming behaviour

The default `names` format streams one line at a time as each XML
file is read. No full in-memory buffering.

`--tree` requires a filter when the catalog has more entries than
`MPM_TREE_NO_FILTER_THRESHOLD` (default 20). Without a filter:

```text
ERROR: --tree requires a filter for catalogs with more than
20 entries. Provide a <substring>, --regex <pattern>,
--max-depth 0, or pass --no-filter-required to override.
```

### list -- Zero-match behaviour

When a filter returns zero entries, the command exits 0 with empty
stdout. A note is written to stderr:

```text
0 entries match filter
```

### list -- Empty manifest repo

When the manifest repo exposes zero installable catalog entries (no
`repo-specs/**/*.xml` file carries a complete `<catalog-metadata>`
block), the command exits 0 with empty stdout and a note to stderr:

```text
manifest repo contains 0 entries
```

### list -- `-A`/`--all` worked example

```text
$ mpm search -A --limit 3 \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
package-a@2.10.0
package-a@2.9.1
package-a@2.9.0
package-b@1.5.0
package-b@1.4.0
package-b@1.3.0
```

`--format json` for the same invocation emits an array of
`{name, version, ref, sha}` objects:

```json
[
  {
    "name": "package-a",
    "version": "2.10.0",
    "ref": "refs/tags/2.10.0",
    "sha": "abc1234..."
  }
]
```

### list -- Error scenarios

#### list error 1 -- Missing catalog source

Reproducer:

```bash
mpm search
```

Expected message:

```text
ERROR: search requires a catalog source.
Provide one of:
  --catalog-source <git-url>@<ref>       # e.g. --catalog-source https://example.com/org/manifest-repo.git@main
  MPM_CATALOG_SOURCES=<git-url>@<ref>  # set as env var (one entry per line), then re-run

The CLI flag takes precedence when both are set.
A catalog source identifies a manifest repo (a git repository whose
repo-specs/ directory exposes installable mpm dependencies).
See docs/catalogs-explained.md for what a manifest repo is and how to find one.
See docs/configuration.md for the full configuration reference.
```

#### list error 2 -- `--match-fields` without filter

Reproducer:

```bash
mpm search --match-fields name \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Expected message:

```text
ERROR: --match-fields requires a filter. Supply a positional <substring> or --regex <pattern> together with --match-fields.
```

#### list error 3 -- `--tree` with `-A`/`--all`

Reproducer:

```bash
mpm search --tree -A \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Expected message:

```text
ERROR: --tree and -A/--all are mutually exclusive. Use --tree for dependency tree rendering, or -A/--all to list all available versions. These flags cannot be combined.
```

---

## mpm add

Add one or more catalog entries to a `.mpm` file.

### add -- Synopsis

```text
mpm add [--catalog-source <git-url>@<ref>]
          <name>[@<spec>] [<name>[@<spec>] ...]
          [--as <alias>]
          [--mpm-file <path>]
          [--force]
          [--dry-run]
          [--marketplace-install | --no-marketplace-install]
```

### add -- How it works

`mpm add` locates the named catalog entries in the resolved
manifest repo, derives a local alias for each, and appends an
alias-keyed `MPM_SOURCE_<alias>_{URL,REF,PATH,NAME}` block to the
target `.mpm` file. It then resolves the entry's manifest (its
`<include>` chain plus embedded remotes) and appends one optional
`MPM_SOURCE_<alias>_<VAR>` env-var line per `${VAR}` placeholder the
entry's `<project>` depends on -- the `GITBASE` var auto-derived from
the source URL, every other var name written empty -- and no env-var
line at all when the manifest references no `${VAR}`. A
`MPM_SOURCE_<alias>_MARKETPLACE=true` line is added for marketplace-type
entries. If the file does not yet exist, it is created; no global header
is written -- each per-dependency block carries its own optional env-var
lines, and there is no global `[catalog]` block or
`MPM_MARKETPLACE_INSTALL` header (both removed in 3.0.0).

`mpm add` does **not** validate `<remote>` resolvability
(soft-spot 4) or tag-format PEP 440 compliance (soft-spot 5).
Those checks belong to `mpm catalog audit`. A successful
`mpm add` does not guarantee a successful install.

### add -- Argument shape

```text
<name>[@<spec>]
```

- `<name>` must match a `<catalog-metadata><name>` value in
  the resolved manifest repo.
- `@<spec>` is optional. Default: the highest PEP 440-valid git
  tag in the entry's tag namespace (see "Default spec resolution").
- Multiple `<name>[@<spec>]` arguments may be supplied in one
  invocation.

### add -- Default spec resolution

When `@<spec>` is omitted, `mpm add` queries the manifest
repo via `git ls-remote --tags` for the highest PEP 440-valid
git tag in the entry's `refs/tags/<name>/` namespace, falling
back to the bare `refs/tags/<pep440>` namespace when the entry
has no namespaced tags. If zero PEP 440-valid tags exist:

```text
ERROR: manifest repo has no PEP 440-valid tags; pin to a
branch or SHA explicitly
(e.g., 'mpm add foo@main') or ask the catalog author to
publish a release tag.
```

### add -- Explicit spec forms

**PEP 440 constraint** -- `==1.4.2`, `~=1.2`, `>=1.0` --
Resolves to the highest matching tag via `_resolve_constraint_from_tags`.

**PEP 440 range** -- `>=1.0,<2.0` --
Must be shell-quoted. See "Shell quoting" below.

**Bare PEP 440 version** -- `1.4.2` --
Resolves to `refs/tags/1.4.2`.

**Branch name** -- `main` --
Passes through to git as-is. Git resolves to `refs/heads/main`.

**Full git ref** -- `refs/tags/v1.0.0` --
Passes through unchanged.

**Raw SHA (40 or 64 hex)** -- `abc123...` --
Passes through unchanged; git resolves to the commit.

For the complete resolution rules see
`docs/version-resolution.md`.

### add -- Shell quoting for PEP 440 specs

PEP 440 range specifiers contain `>` and `<`, which the shell
interprets as redirection operators. Always quote the full
`<name>@<spec>` argument:

```bash
# Single quotes (recommended) -- quote the full <name>@<spec> argument
mpm add 'package-a@>=1.0,<2.0' \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main

# Single quotes work for any range style, e.g. ~=
mpm add 'package-a@~=1.2' \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Do NOT omit the quotes: `package-a@>=1.0,<2.0` passed without quotes causes the
shell to treat `>=` as a redirect operator, breaking the command silently.

Failing to quote a range spec causes the shell to redirect
stderr before mpm runs. mpm emits a friendly error when it
detects the resulting empty argument, but the shell-level
redirection may still create or truncate files in the working
directory.

### add -- Source-name derivation

The source name written into the `.mpm` triple is derived from
the entry name by a deterministic one-way normalization
(spec Section 1.1):

1. Lowercase the entry name.
2. Replace every `-` with `_`.

This normalization is applied unconditionally. The same input
always yields the same output.

Examples:

| Entry name | Derived alias |
| ---------- | ------------- |
| `package-a` | `package_a` |
| `Package-A` | `package_a` |
| `MyTool` | `mytool` |
| `my-cool-lib` | `my_cool_lib` |

Worked example: `Package-A` normalizes to `package_a`.

The normalized alias appears in the `MPM_SOURCE_<alias>_*` block
keys. `mpm add` writes the normalized form verbatim, unless
`--as <alias>` overrides it or a cross-source collision triggers a
deterministic auto-suffix.

### add -- File creation

When the target `.mpm` file does not exist, `mpm add` creates
it and writes the alias-keyed source block(s) directly. **No global
header is written** in 3.0.0: there is no `[catalog]` block, no
global `GITBASE=` line, and no `MPM_MARKETPLACE_INSTALL=` line.
Any per-org base is recorded per dependency in
`MPM_SOURCE_<alias>_GITBASE`, derived automatically from the
catalog-source URL -- but only when the entry's manifest actually
references `${GITBASE}` (see the env-var block below).

### add -- Written block

For each added entry, `mpm add` appends an alias-keyed structural block:

```bash
MPM_SOURCE_<alias>_URL=<manifest_repo_url>
MPM_SOURCE_<alias>_REF=<resolved_spec>
MPM_SOURCE_<alias>_PATH=<path_to_marketplace_xml>
MPM_SOURCE_<alias>_NAME=<manifest_name>
```

It then appends one optional env-var line per `${VAR}` placeholder the
entry's manifest references (resolved through the entry's `<include>`
chain and the `<remote>` its `<project>` depends on). The var named
exactly `GITBASE` is auto-derived from the catalog-source URL; every
other var name is written empty for you to fill in:

```bash
MPM_SOURCE_<alias>_GITBASE=<derived_org_base>   # only if the manifest uses ${GITBASE}
MPM_SOURCE_<alias>_<OTHER_VAR>=                 # only if the manifest uses ${OTHER_VAR}
```

An entry whose manifest references no `${VAR}` gets no env-var line. For
a marketplace-type entry (or when `--marketplace-install` is passed), a
trailing `_MARKETPLACE` line is appended:

```bash
MPM_SOURCE_<alias>_MARKETPLACE=true
```

Output confirms the structural keys written (full key names, in canonical
suffix order):

```text
Wrote MPM_SOURCE_package_a_URL, MPM_SOURCE_package_a_REF, MPM_SOURCE_package_a_PATH, MPM_SOURCE_package_a_NAME to ./.mpm
```

A `--force` overwrite of an existing alias prints `Overwrote ... in ./.mpm`.

### add -- Lockfile interaction

`mpm add` only edits `.mpm`; it does not resolve or write the
lockfile. The next plain `mpm install` reconciles the new source into
the lockfile (resolving it fresh while preserving the locked SHAs of
unchanged sources), so the `mpm add` then `mpm install` loop "just
works" without any flag -- including when an `add` and a `remove` happen
between two installs. See
[docs/lockfile.md -- Install reconcile model](lockfile.md#install-reconcile-model).

### add -- Flags

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--catalog-source url[@ref]` | env | Catalog source; `@ref` optional. Env: MPM_CATALOG_SOURCES. |
| `--catalog-default-branch name` | env | Branch used when the catalog source omits `@ref`. Env: MPM_CATALOG_DEFAULT_BRANCH (default `main`; `auto` = remote HEAD). |
| `--as alias` | auto | Override the auto-computed local alias (single entry only). Charset `[A-Za-z0-9_]`, no `__` run. |
| `--mpm-file path` | `./.mpm` | Target file. Env: MPM_MPM_FILE. |
| `--force` | off | Re-add an existing alias (same source@ref): overwrite the block and re-pin its lock entry. Without it, a re-add is a hard error. |
| `--dry-run` | off | Print diff without modifying any file. Exit 0. |
| `--marketplace-install` | auto | Force `MPM_SOURCE_<alias>_MARKETPLACE=true` (errors if the entry is not a `claude-marketplace` type). Excl. `--no-marketplace-install`. |
| `--no-marketplace-install` | auto | Force the `_MARKETPLACE` line to be omitted. Excl. `--marketplace-install`. |

### add -- `--dry-run` semantics

With `--dry-run`, `mpm add` prints the diff that would be
written to the target file and exits 0 without modifying any
file:

```text
--- ./.mpm (existing)
+++ ./.mpm (proposed)
@@ ...
+MPM_SOURCE_package_a_URL=https://example.com/org/manifest-repo.git
+MPM_SOURCE_package_a_REF===1.4.2
+MPM_SOURCE_package_a_PATH=repo-specs/package-a/package-a-marketplace.xml
+MPM_SOURCE_package_a_NAME=package-a
+MPM_SOURCE_package_a_GITBASE=https://example.com/org
```

The trailing `_GITBASE` line appears only because this entry's manifest
references `${GITBASE}`; an entry with fully-literal remotes shows only the
four structural lines.

When a `--force` overwrite replaces an existing block, the diff also
shows the removed lines with a `-` prefix.

### add -- Collision behaviour

Alias collisions are classified into three cases:

#### add -- Within-request collision (hard error)

When two entries in the same `mpm add` invocation normalize to the
same alias, the command exits with a hard error before touching the
file. See "add error 4 -- Within-request alias collision" below.

#### add -- Cross-source collision (auto-suffixed, never an error)

When the requested entry's manifest name sanitizes to an alias already
mapped to a **different** source, the alias is auto-suffixed
deterministically and the add succeeds -- with or without `--force`. Use
`--as <alias>` to choose an explicit alias instead.

#### add -- Same-alias re-add (hard error without `--force`)

When the target `.mpm` already maps the alias to the **same**
source@ref, `mpm add` treats it as a re-add and exits with a hard
error (showing a diff and a remediation hint) unless `--force` is passed.
See "add error 5 -- Re-adding an existing alias without `--force`" below.
With `--force`, the existing block is overwritten and its lock entry is
re-pinned.

### add -- Error scenarios

#### add error 1 -- Unquoted PEP 440 range

Reproducer: run the `add` command with the spec argument unquoted, e.g.
`package-a@>=1.0,<2.0` passed without surrounding single quotes. The shell
treats `>=` as a redirect operator and the spec is never received by mpm.

Expected message (shell creates an empty redirection target):

```text
ERROR: received an empty spec argument. PEP 440 range
specifiers contain > and < which the shell treats as
redirection. Quote the argument:
mpm add 'package-a@>=1.0,<2.0'
```

#### add error 2 -- Missing catalog source

Reproducer:

```bash
mpm add package-a
```

Expected message:

```text
ERROR: add requires a catalog source.
Provide one of:
  --catalog-source <git-url>@<ref>       # e.g. --catalog-source https://example.com/org/manifest-repo.git@main
  MPM_CATALOG_SOURCES=<git-url>@<ref>  # set as env var (one entry per line), then re-run

The CLI flag takes precedence when both are set.
A catalog source identifies a manifest repo (a git repository whose
repo-specs/ directory exposes installable mpm dependencies).
See docs/catalogs-explained.md for what a manifest repo is and how to find one.
See docs/configuration.md for the full configuration reference.
```

#### add error 3 -- Zero PEP 440 tags and no `@<spec>`

Reproducer (manifest repo has no PEP 440-valid tags):

```bash
mpm add package-a \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Expected message (the example tag is always `foo@main`, regardless of the
requested entry name):

```text
ERROR: manifest repo has no PEP 440-valid tags; pin to a branch or SHA explicitly (e.g., 'mpm add foo@main') or ask the catalog author to publish a release tag.
```

#### add error 4 -- Within-request alias collision

When two entries in the same invocation normalize to the same alias:

```bash
mpm add package-a Package-A \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Expected message:

```text
ERROR: within-request collision: 'package-a' and 'Package-A' both normalise to source name 'package_a'.
Remove duplicate entries from your command arguments.
```

> A *cross-source* collision (two different sources whose manifest names
> sanitize to the same alias) is NOT an error -- it is auto-suffixed
> deterministically, with or without `--force`. Only a within-request
> duplicate and a same-alias re-add (below) are errors.

#### add error 5 -- Re-adding an existing alias without `--force`

Reproducer (when alias `package_a` already maps to the same source@ref):

```bash
mpm add 'package-a@==1.5.0' \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Expected message (the diff lines show the existing block followed by a
remediation hint):

```text
ERROR: source alias 'package_a' is already mapped to https://example.com/org/manifest-repo.git/repo-specs/package-a/package-a-marketplace.xml (ref ==1.4.2); this is a re-add of an existing package.
-MPM_SOURCE_package_a_URL=https://example.com/org/manifest-repo.git
-MPM_SOURCE_package_a_REF===1.4.2
-MPM_SOURCE_package_a_PATH=repo-specs/package-a/package-a-marketplace.xml
+MPM_SOURCE_package_a_URL=https://example.com/org/manifest-repo.git
+MPM_SOURCE_package_a_REF===1.5.0
+MPM_SOURCE_package_a_PATH=repo-specs/package-a/package-a-marketplace.xml
Use --force to overwrite and re-pin its lock entry, or 'mpm remove package_a' first.
```

With `--force`, the existing block is overwritten and its lock entry is
re-pinned (the dependency's `_NAME` is preserved).

#### add error 6 -- Entry with manifest integrity issues

Reproducer (the entry's manifest XML has integrity issues):

```bash
mpm add broken-entry \
    --catalog-source \
    https://example.com/org/manifest-repo.git@main
```

Expected message (one preceding `ERROR:` line per offending XML path,
followed by the summary):

```text
ERROR: manifest repo `https://example.com/org/manifest-repo.git@main` has integrity issues in the following XML paths: repo-specs/broken-entry/broken-entry-marketplace.xml
```

---

## mpm remove

Remove one or more named source blocks from a `.mpm` file.

### remove -- Synopsis

```text
mpm remove [--mpm-file <path>]
             <name> [<name> ...]
             [--force]
             [--dry-run]
             [--no-color]
```

### remove -- Alias or entry name

`mpm remove` accepts **either** the alias (the `<alias>` token in
`MPM_SOURCE_<alias>_*` keys) or the original entry name. Both forms
are normalized via the same derivation rule (lowercase + replace `-`
with `_`).

Worked example:

```bash
# Both remove the same alias block:
mpm remove package-a   # entry name
mpm remove package_a   # alias (normalized form)
```

### remove -- Behaviour

1. Read the `.mpm` file. Fail-fast if the file is missing.
2. For each `<name>`, normalize to the alias and locate every line of
   that alias' block: the structural keys
   `MPM_SOURCE_<normalized>_{URL,REF,PATH,NAME}=...`, plus any optional
   per-dependency env-var line (e.g. `_GITBASE`) and the optional
   `_MARKETPLACE` flag. These lines may be non-contiguous in hand-written
   `.mpm` files. They are removed wherever they appear, preserving the
   order of remaining content.
3. **Atomicity:** all requested aliases are validated first. Presence is
   judged by the required STRUCTURAL keys only. If ANY requested alias is
   missing a required structural key (fewer than 4 present), the command
   exits non-zero and the file is NOT modified -- either every requested
   removal succeeds or nothing changes. The error is:
   `source 'X' (normalized form 'Y') not fully present in
   .mpm; found <n> of 4 expected MPM_SOURCE_<Y>_* keys`.
4. Comments adjacent to removed keys are not removed
   automatically; all other content is preserved byte-for-byte
   except for the removed block lines.

### remove -- Line-ending preservation

`mpm remove` writes the file back with these rules:

| Condition | Behaviour |
| --------- | --------- |
| LF only | LF preserved throughout |
| CRLF only | CRLF preserved throughout |
| Mixed LF and CRLF | Normalized to LF; warning to stderr |
| Trailing newline | File ends with exactly one `\n` |
| 3 or more consecutive blank lines | Collapsed to 2 |

Mixed line-ending warning:

```text
WARNING: mixed line endings detected; normalizing to LF
```

### remove -- Non-contiguous block handling

The alias' block lines -- `MPM_SOURCE_<alias>_{URL,REF,PATH,NAME}` plus
any optional env-var (e.g. `_GITBASE`) and `_MARKETPLACE` line -- are
removed wherever they appear in the file, even if they are not adjacent.
All other content (including interleaved comments and other keys) is
preserved in its original order.

### remove -- Flags

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--mpm-file path` | `./.mpm` | Target file. Env: MPM_MPM_FILE. |
| `--force` | off | Silently skip aliases not fully present (clean up partially-orphaned entries). Known aliases are still removed atomically. |
| `--dry-run` | off | Print the lines that would be removed (each with a `-` prefix); makes no on-disk change. Exit 0. |

### remove -- `--dry-run` semantics

With `--dry-run`, `mpm remove` prints what would be removed
and exits 0 without modifying any file:

```text
-MPM_SOURCE_package_a_URL=https://example.com/org/manifest-repo.git
-MPM_SOURCE_package_a_REF===1.4.2
-MPM_SOURCE_package_a_PATH=repo-specs/package-a/package-a-marketplace.xml
-MPM_SOURCE_package_a_NAME=package-a
-MPM_SOURCE_package_a_GITBASE=https://example.com/org
```

The `_GITBASE` line is shown here because this block declared it; a block
with no optional env-var line removes only its four structural lines.

### remove -- Lockfile interaction

If `.mpm.lock` exists and references the removed source, the
next `mpm install` detects the orphan and reconciles by
default: it prunes the orphan, replays the surviving sources,
and rewrites the lockfile (the `npm install` model). With
`--strict-lock` on `mpm install`, the orphan is a hard error
and the lockfile is not mutated (the `npm ci` model). See
[docs/lockfile.md -- Install reconcile model](lockfile.md#install-reconcile-model).

If the removed source had registered a marketplace (recorded in its
per-source `registered_marketplaces` ledger), the next `mpm install`
also auto-unregisters that marketplace from `~/.claude` as part of the
reconcile -- unless another still-referenced source provides the same
marketplace, in which case it is retained. To prune the orphaned
marketplace explicitly without a reinstall, run `mpm clean --orphans`.
See
[docs/lockfile.md -- Marketplace ownership and pruning](lockfile.md#marketplace-ownership-and-pruning).

### remove -- Error scenarios

#### remove error 1 -- Unknown alias without `--force`

Reproducer:

```bash
mpm remove nonexistent-entry
```

Expected message:

```text
ERROR: source alias 'nonexistent-entry' (normalized form 'nonexistent_entry') not fully present in .mpm; found 0 of 5 expected MPM_SOURCE_nonexistent_entry_* keys
```

Pass `--force` to silently skip aliases that are not fully present.

#### remove error 2 -- Missing `.mpm` file

Reproducer:

```bash
mpm remove package-a
```

Expected message (when no `.mpm` exists):

```text
ERROR: no .mpm file at .mpm; nothing to remove
```

---

## Environment variables

The following environment variables affect `mpm search`,
`mpm add`, and `mpm remove`. For the full configuration
reference see [docs/configuration.md](configuration.md).

**`MPM_CATALOG_SOURCES`** -- `search`, `add`

Catalog source as `<git-url>@<ref>`. CLI flag
`--catalog-source` takes precedence when both are set.

**`MPM_LIST_FORMAT`** -- `search`

Default output format (`names` or `json`). Overridden by
`--format`.

**`MPM_LIST_LIMIT`** -- `search`

Default `-A`/`--all` cap. Default value: `50`. Overridden
by `--limit` or `--no-limit`.

**`MPM_TREE_NO_FILTER_THRESHOLD`** -- `search`

Entry count above which `--tree` requires a filter. Default:
`20`.

**`MPM_MPM_FILE`** -- `add`, `remove`

Default target file path. Default: `./.mpm`. Overridden by
`--mpm-file`.

**`NO_COLOR`** -- all commands

When set to any non-empty value, disables color output.

**`MPM_GIT_RETRY_COUNT`** -- `search`, `add`

Number of `git ls-remote` retries on transient errors.
Default: `3`.

**`MPM_GIT_RETRY_DELAY`** -- `search`, `add`

Seconds between `git ls-remote` retries. Default: `1`.
