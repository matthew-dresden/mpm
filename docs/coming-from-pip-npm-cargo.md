# Coming From pip / npm / cargo

If you already work with another package manager, this guide maps the concepts
and commands you know onto the mpm model.

## Audience

This guide is for engineers who are comfortable with one or more of:

- **pip / Python packaging** (`pip`, `pipenv`, `poetry`, `uv`)
- **npm / Node.js packaging** (`npm`, `yarn`, `pnpm`)
- **cargo / Rust packaging** (`cargo`)

...and who want to understand how the same operations map to mpm.

## Translation table

| Concept | pip | npm | cargo | mpm |
| --- | --- | --- | --- | --- |
| Install deps | pip install -r req.txt | npm ci | cargo build | mpm install |
| Declare file | req.txt | pkg.json | Cargo.toml | .mpm |
| Lockfile | Pipfile.lock | pkg-lock.json | Cargo.lock | .mpm.lock |
| Registry | PyPI | npm registry | crates.io | manifest repo |
| Search | pip search | npm search | cargo search | mpm search |
| Add | pip install x==1.0 | npm i x@1.0 | cargo add x@1.0 | mpm add x@1.0 |
| Outdated | pip list -o | npm outdated | cargo outdated | mpm outdated |
| List installed | pip list | npm ls | cargo tree | mpm list |

## Where the model differs

**mpm has no central registry.**

In pip, npm, and cargo there is a well-known central index (PyPI, npm registry,
crates.io) that every user connects to by default. You can mirror or proxy it,
but the central instance exists and its URL is baked into the tooling.

mpm deliberately has no such central instance. Instead:

- Each workspace declares its own **catalog source** -- a git repository URL
  that acts as the package catalog for that workspace.
- The catalog source is chosen by the operator (your team, your organization)
  and configured per workspace.
- There is no mpm-operated registry, no shared public index, and no default
  URL embedded in the tool.

This means:

- Two teams can use different catalogs without conflicting.
- A catalog can be hosted on any git provider (or a self-hosted server).
- Catalog contents are versioned, auditable, and entirely under your control.
- `mpm search` and `mpm add` operate against YOUR configured catalog, not a
  shared global one.

For details on how to configure and point to a catalog, see
[Catalogs explained](catalogs-explained.md).

## Worked translation example

The scenario: **add `package-a` at version `1.4.2` to the current project.**

### pip

```shell
pip install "package-a==1.4.2"
# Then pin it:
pip freeze > requirements.txt
```

### npm

```shell
npm install package-a@1.4.2
# package.json and package-lock.json are updated automatically.
```

### cargo

```shell
cargo add package-a --version 1.4.2
# Cargo.toml and Cargo.lock are updated automatically.
```

### mpm

```shell
# Ensure your workspace is configured with a catalog source first:
# MPM_CATALOG_SOURCES=https://example.com/org/manifest-repo.git@main

mpm add package-a@1.4.2
# .mpm and .mpm.lock are updated automatically.
```

The mpm command follows the same pattern as the others: declare the package
name and version constraint, and the tool resolves, fetches, and pins the
result.

## See also

- [list-and-add.md](list-and-add.md) -- Full reference for `mpm search` and
  `mpm add`.
- [lockfile.md](lockfile.md) -- How `.mpm.lock` is structured and when it is
  regenerated.
- [catalogs-explained.md](catalogs-explained.md) -- How catalog sources work,
  how to configure them, and how to author your own.
