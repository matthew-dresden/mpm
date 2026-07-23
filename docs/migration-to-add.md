# Migration: `mpm bootstrap` to `mpm add` / `mpm search`

This guide is the central reference for operators moving away from the
removed `mpm bootstrap` command to `mpm add`, `mpm search`, and
`mpm install`.

---

## Why this changed

`mpm bootstrap` was the original setup command. It read template
files from a `catalog/<name>/` directory inside the manifest repo (or
from a bundled catalog inside the mpm wheel itself) and copied them
into an output directory.

This model had two problems:

1. **Bundled catalog fallback.** The mpm wheel shipped a bundled
   catalog directory so that `mpm bootstrap` could run without a
   `--catalog-source`. This created an implicit, opaque default that
   was easy to misconfigure and hard to audit.

2. **Template directory coupling.** Projects accumulated a
   `catalog/<name>/` directory committed alongside the project source.
   mpm now reads all configuration from the root `.mpm` file; the
   `catalog/` directory is unused and must not exist.

`mpm bootstrap` was **removed in mpm 3.0.0** (a breaking
change). There is **no compatibility shim**: `bootstrap` is no longer a
registered subcommand, so the command name is gone entirely.

**Forced migration at the CI / script boundary.** Every `mpm
bootstrap` invocation now fails at argument parsing with an argparse
`invalid choice: 'bootstrap'` error (exit code `2`) that lists the valid
subcommands. No work is performed. Scripts that call `mpm bootstrap`
fail immediately, forcing operators to update their pipelines rather than
silently running stale tooling.

See [docs/exit-codes.md](exit-codes.md) for the full exit-code table.

---

## Command translations

| Removed command | Replacement command |
| --------------- | ------------------- |
| `mpm bootstrap <entry>` | `mpm add <entry> --catalog-source <git-url>@<ref>` |
| `mpm bootstrap list` | `mpm search --catalog-source <git-url>@<ref>` |

After adding entries, run `mpm install` to fetch them.

See [docs/list-and-add.md](list-and-add.md) for the full reference for
`mpm add` and `mpm search`, and
[docs/configuration.md](configuration.md) for `MPM_CATALOG_SOURCES`.

---

## No bootstrap flags remain

`mpm bootstrap` accepts no flags because the subcommand no longer
exists. There is nothing to translate per-flag -- argparse rejects the
`bootstrap` token before any flag is parsed. This includes:

- `--help` / `-h`
- the former `--output-dir` and `--catalog-source` flags
- any unknown flag (for example `--marketplace-install`)
- the `list` positional and any other positional

The catalog source for the replacement commands is supplied with
`--catalog-source <git-url>@<ref>` or the `MPM_CATALOG_SOURCES`
environment variable. The canonical `--catalog-source` flag definition
lives in `core/cli_args.py`; `mpm search`, `mpm add`, and the other
catalog-aware commands import it from there.

`mpm install` writes its artifacts into the shared `MPM_HOME` store
(`$MPM_HOME`, default `~/.mpm-home`); the `--home` / `--store-dir` flag
relocates the store and caches for a single invocation (precedence:
flag > `MPM_HOME` > `~/.mpm-home`). The store directory is created if
absent; an unwritable value causes a non-zero exit with an actionable
message and no silent fallback. `mpm clean` resolves the same
directory so it removes exactly what `mpm install` wrote.

See [docs/configuration.md](configuration.md) for `MPM_CATALOG_SOURCES`
and `MPM_HOME`.

---

## What happens when you run `mpm bootstrap`

`bootstrap` is no longer a registered subcommand. Running `mpm
bootstrap` (with any args or flags, including `mpm bootstrap list` and
bare `mpm bootstrap`) fails at argument parsing: argparse prints an
`invalid choice: 'bootstrap'` usage error listing the valid subcommands
and exits with code `2`. There is no compatibility shim, no crafted
deprecation message, and no exit code `3` -- the command name is simply
gone.

```text
mpm: error: argument command: invalid choice: 'bootstrap' (choose from 'add',
'catalog', 'clean', 'completion', 'doctor', 'install', 'marketplace', 'search',
'outdated', 'remove', 'validate', 'repo', 'why')
```

The same applies to `mpm list`, which was renamed to `mpm search`
with no alias: `mpm list` also exits `2` with an `invalid choice`
error.

See [docs/exit-codes.md](exit-codes.md) for the canonical exit-code
reference.

---

## How manifest repos changed

**Before (legacy model):**

- A manifest repo contained a `catalog/<name>/` directory for each
  catalog entry. This directory held pre-baked `.mpm` snippets and
  per-entry READMEs consumed by `mpm bootstrap`.
- `mpm bootstrap <name>` read from `catalog/<name>/` and copied
  files into the project's working directory.

**After (current model):**

- A manifest repo no longer has a separate `catalog/<name>/` location.
  The manifest repo **is** the catalog: each XML manifest under
  `repo-specs/` that carries a `<catalog-metadata>` block is a catalog
  entry, identified by its `<catalog-metadata><name>`. (A marketplace
  is one kind of entry; other manifest types live under `repo-specs/`
  too.)
- There is no `catalog/<name>/` directory. Catalog authors removed the
  legacy directory as part of this change.
- Consumers see the same entries via `mpm search`. No migration step is
  required for consumers beyond replacing their `mpm bootstrap`
  invocations with `mpm search` / `mpm add` / `mpm install`.

`mpm catalog audit` detects the presence of a legacy
`catalog/<name>/` directory and emits a WARN-level finding.

See [docs/catalogs-explained.md](catalogs-explained.md) for a full
explanation of the manifest-repo model.

---

## How the mpm wheel changed

The bundled catalog directory has been **removed** from the mpm
wheel.

**Consequences for operators:**

- There is no implicit default catalog source. The third-tier "bundled
  fallback" in catalog resolution no longer exists.
- Operators MUST supply a catalog source via `--catalog-source` or the
  `MPM_CATALOG_SOURCES` environment variable for every `mpm search`,
  `mpm add`, `mpm outdated`, `mpm why`, and `mpm catalog audit`
  invocation.
- Missing both `--catalog-source` and `MPM_CATALOG_SOURCES` is a hard
  error with a clear, actionable message. There is no fallback.
- `mpm install` is hermetic: it reads only `.mpm` and `.mpm.lock`,
  does not accept `--catalog-source`, and has no catalog-source fallback.

See [docs/configuration.md](configuration.md) for the full
`MPM_CATALOG_SOURCES` reference.

---

## Migration timeline

| Event | Release |
| ----- | ------- |
| Bundled catalog removed from the mpm wheel | mpm 3.0.0 (breaking change) |
| Legacy `catalog/<name>/` audit warning added | mpm 3.0.0 |
| `mpm bootstrap` removed entirely (no shim; `invalid choice` exit 2) | mpm 3.0.0 |
| `mpm list` renamed to `mpm search` (no alias; `invalid choice` exit 2) | mpm 3.0.0 |

The `bootstrap` name was removed from the CLI entirely -- it is not a
registered subcommand, so `mpm bootstrap` fails with an argparse
`invalid choice` usage error (exit `2`).

---

## See also

- [docs/list-and-add.md](list-and-add.md) -- replacement commands
  `mpm add` and `mpm search`
- [docs/catalogs-explained.md](catalogs-explained.md) -- what a
  manifest repo is and how catalog entries are structured
- [docs/exit-codes.md](exit-codes.md) -- canonical exit-code table,
  including the argparse `invalid choice` exit 2 for removed commands
- [docs/configuration.md](configuration.md) -- `MPM_CATALOG_SOURCES`
  and other environment variables
