# mpm repo

The `mpm repo` subcommand is mpm's manifest-driven sync engine. It reads an XML manifest
that lists git projects, clones them into a `.repo/projects/*` object store, and checks them
out into their declared paths. Everything described here is part of mpm -- there is no
separate tool to install.

At the Python level the same engine is available as the `mpm_cli.repo` package, with the
stable public API documented in `src/mpm_cli/repo/__init__.py`: `repo_init`, `repo_envsubst`,
`repo_sync`, and `repo_run`. `mpm install` uses this API directly; `mpm repo <subcommand>`
exposes it as a CLI.

## Contents

- [Manifest format](./manifest-format.md) -- the XML schema for `<manifest>`, `<remote>`,
  `<project>`, `<linkfile>`, `<copyfile>`, `<include>`, and related elements, plus MPM's
  PEP 440 version constraint syntax in `<project revision>`.
- [Internal filesystem layout](./internal-fs-layout.md) -- the `.repo/` directory structure
  and how mpm stores the object database and working trees.
- [Repo hooks](./repo-hooks.md) -- authoring and enabling project hooks that run during sync
  (pre-upload, post-sync).
- [Smart sync](./smart-sync.md) -- manifest-server-backed sync flow for teams that publish
  build-tested manifest snapshots.
- [Python support](./python-support.md) -- supported Python versions and hook interpreter
  policy.
- [Windows notes](./windows.md) -- platform-specific considerations for Windows users.

## When to read this

- Authoring a manifest repository -- start with the [manifest format](./manifest-format.md).
- Debugging a sync failure -- start with the [internal filesystem layout](./internal-fs-layout.md).
- Writing project-level hooks that run during sync -- [repo hooks](./repo-hooks.md).
- Running a manifest server for faster builds -- [smart sync](./smart-sync.md).

## When to read something else

- High-level mpm overview: [../../README.md](../../README.md).
- `.mpm` configuration file reference: [../configuration.md](../configuration.md).
- `mpm install` and `mpm clean` lifecycle: [../lifecycle.md](../lifecycle.md) and
  [../how-it-works.md](../how-it-works.md).
- PEP 440 version resolution in `.mpm`: [../version-resolution.md](../version-resolution.md).
