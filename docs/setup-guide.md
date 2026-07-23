# Setup Guide

Step-by-step instructions for setting up MPM in new and existing projects.

## Prerequisites

- Git
- Bash shell
- Python 3.11+
- Internet access (to clone package repositories)

**For all projects:** The `mpm` CLI tool must be installed first.

For end-user / production use (isolated CLI from PyPI):

```bash
pipx install missing-package-manager
```

For local development on the mpm repository itself, install it
in editable mode against the local source tree:

```bash
pip install -e .
```

(`pipx` keeps the CLI isolated in its own venv. Install it with
`python3 -m pip install --user pipx && pipx ensurepath` if it is not
already on your PATH. Editable mode is documented for mpm
contributors; see `CONTRIBUTING.md`.)

The `mpm repo` subsystem (`mpm repo init`, `mpm repo sync`, etc.)
is part of the `mpm` CLI. See the [MPM README](../README.md) for
full CLI documentation.

## New Project Setup

### 1. Add Catalog Entries to Your Project

> **Note:** `mpm bootstrap` was removed in mpm 3.0.0 (a breaking
> change). There is no compatibility shim: `bootstrap` is no longer a
> registered subcommand, so `mpm bootstrap` exits non-zero with an
> argparse `invalid choice: 'bootstrap'` error. Use the commands below
> instead. See [docs/migration-to-add.md](migration-to-add.md).

Search the catalog and add an entry to your `.mpm` with `mpm search` and
`mpm add`. A catalog source is required, supplied via `--catalog-source
'<git_url>@<ref>'` or the `MPM_CATALOG_SOURCES` environment variable (ref can
be a branch, tag, `latest`, or a PEP 440 version constraint such as
`>=2.0.0,<3.0.0`):

```bash
mpm search --catalog-source '<git_url>@<ref>'        # search the catalog
mpm add mpm --catalog-source '<git_url>@<ref>'   # add an entry to .mpm
```

`mpm add` writes the entry into `.mpm`, creating `.mpm` for you if it does
not yet exist.

### 2. Review `.mpm` (Optional)

The `.mpm` file is populated by `mpm add` with values from your
organization's catalog entry. You may want to review the source URLs and paths
before installing.

All `.mpm` values can be overridden by environment variables of the same name (useful for CI/CD pipelines).

### 3. Run mpm install

```bash
mpm install
```

### 4. Verify

Confirm that `.packages/` was created and contains the expected package directories. Check that any symlinks defined in the manifest are present in your project root.

## Existing Project Migration

For existing projects, follow the same steps above but adapt your existing build configuration to include MPM's catalog entry files alongside your current setup.

## Troubleshooting

### `mpm: command not found`

The `mpm` CLI must be installed before running any `mpm` command.
Install it with `pipx install missing-package-manager` (production) or `pip install -e .`
(local development on this repository). The `mpm repo` subsystem is part of
the `mpm` CLI -- there is no separate tool to install.

### `mpm install` fails with `manifest needs ${VAR} but no value was provided`

A source's manifest references a `${VAR}` placeholder that has no value. Set the
matching per-dependency key in `.mpm`: `MPM_SOURCE_<alias>_<VAR>=<value>`
(for example `MPM_SOURCE_<alias>_GITBASE=https://github.com/your-org`). `mpm
add` writes these lines automatically (auto-deriving `GITBASE` and leaving other
vars empty); fill in any empty value before re-running `mpm install`.

### `mpm repo sync` fails with authentication errors

Ensure `git` can authenticate with the Git hosting provider for your package repositories (SSH keys or credential helper).
