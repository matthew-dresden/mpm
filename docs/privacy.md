# Privacy

mpm collects **no usage telemetry**. There is no analytics collector, no event
emitter, no run identifier, and no opt-out to configure -- the feature does not
exist in the codebase.

## What mpm sends over the network

mpm makes only the network calls it needs to do its job, all of them driven by
your own configuration:

- **Git operations.** `git ls-remote`, `git fetch`, and `git clone` against the
  manifest repos and package repos you declare in `.mpm` (or pass on the command
  line). These go to the hosts in your own URLs, using your own git credentials.
- **PyPI update check.** A single best-effort `GET` to
  `https://pypi.org/pypi/missing-package-manager/json` to tell you when a newer
  release is available. It sends nothing but the standard HTTP request and a
  `User-Agent` of `missing-package-manager/<installed-version>`. Skip it with
  `--no-update-check` or `MPM_SKIP_UPDATE_CHECK=1`; see
  [docs/configuration.md](configuration.md) for the timeout and TTL knobs.

That is the complete list. mpm does not phone home, does not report which
commands you run, and does not transmit your manifest, lockfile, package list,
git identity, or environment anywhere.

## What mpm writes to disk

mpm stores state only under your project directory and your mpm home
(`~/.mpm-home` by default, or `MPM_HOME` / `--home`):

- `.mpm` and `.mpm.lock` in your project.
- The content-addressed store and caches under the mpm home.

Nothing in those locations is uploaded anywhere.

## Related documentation

- [docs/configuration.md](configuration.md) -- every environment variable mpm
  reads.
- [docs/cli-reference.md](cli-reference.md) -- every global flag.
- [docs/security-model.md](security-model.md) -- the trust boundaries mpm
  enforces around remote sources.
