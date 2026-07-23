# Help Fixture Files

This directory contains verbatim snapshots of `mpm --help` output, used by
the parametrised snapshot harness in `tests/functional/test_help_snapshots.py`.
Each fixture is compared byte-for-byte against the live subprocess output; a
mismatch causes the test to fail with the fixture path and captured byte-count
so you can regenerate quickly.

## Naming Convention

| Pattern | Command | Notes |
|---------|---------|-------|
| `mpm-toplevel.txt` | `mpm --help` (top-level entry point) | |
| `mpm-<command>.txt` | `mpm <command> --help` | |
| `mpm-<group>-<subcommand>.txt` | `mpm <group> <subcommand> --help` | Hyphenated filename mirrors the argv path for nested subparsers (e.g. `catalog audit` -> `mpm-catalog-audit.txt`). |

Examples:

- `mpm-toplevel.txt` -- top-level `mpm --help`
- `mpm-search.txt` -- `mpm search --help`
- `mpm-catalog.txt` -- `mpm catalog --help` (subcommand-group head)
- `mpm-catalog-audit.txt` -- `mpm catalog audit --help` (nested subparser child; hyphenated filename mirrors the `catalog audit` argv path)

## Current Fixtures

| File | Command |
|------|---------|
| `mpm-toplevel.txt` | `mpm --help` |
| `mpm-search.txt` | `mpm search --help` |
| `mpm-marketplace.txt` | `mpm marketplace --help` (per-dependency Claude marketplace flag manager; lists `enable`, `disable`, `status`) |
| `mpm-add.txt` | `mpm add --help` |
| `mpm-remove.txt` | `mpm remove --help` |
| `mpm-outdated.txt` | `mpm outdated --help` |
| `mpm-why.txt` | `mpm why --help` |
| `mpm-install.txt` | `mpm install --help` |
| `mpm-doctor.txt` | `mpm doctor --help` |
| `mpm-catalog.txt` | `mpm catalog --help` (subcommand-group head; lists `audit` as the available catalog operation) |
| `mpm-catalog-audit.txt` | `mpm catalog audit --help` (nested subparser child; covers `--check`, `--format`, Catalog source group; hyphenated filename mirrors the `catalog audit` argv path) |
| `mpm-completion.txt` | `mpm completion --help` (shell completion script emitter; covers `<shell>` positional argument) |

## Regeneration Procedure

If a fixture test fails because the CLI output changed intentionally (e.g., a
new subcommand was added), regenerate the fixture by running the command with
the deterministic environment variables and redirecting stdout:

```bash
NO_COLOR=1 COLUMNS=80 env -u MPM_CATALOG_SOURCES python -m mpm_cli --help > tests/fixtures/help/mpm-toplevel.txt
```

For a subcommand fixture:

```bash
NO_COLOR=1 COLUMNS=80 env -u MPM_CATALOG_SOURCES python -m mpm_cli <command> --help > tests/fixtures/help/mpm-<command>.txt
```

The three environment controls used during regeneration match exactly what
`_clean_env()` in the test harness sets:

- `NO_COLOR=1` -- disables ANSI colour codes for deterministic plain-text output.
- `COLUMNS=80` -- pins terminal width so argparse wraps at a fixed column count.
- `env -u MPM_CATALOG_SOURCES` -- unsets the variable so ambient catalog-source
  overrides do not affect the help text.

After regenerating, run the snapshot test to confirm the fixture matches:

```bash
uv run pytest tests/functional/test_help_snapshots.py -v -k mpm-toplevel
```

Review the diff in git before committing to confirm the change is intentional.
