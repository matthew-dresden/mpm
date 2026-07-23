# Security Model

mpm is designed around a strict trust model that keeps it safe to run in
regulated, multi-tenant CI/CD environments. This document describes the
trust model from spec Section 3.6, the threat surface operators accept when
they configure a manifest repo, and the interactions mpm explicitly never
performs.

For the full specification see `spec/mpm-list-add-lock-features-spec.md`,
Section 3.6 (trust model) and Section 8 (the `docs/security-model.md` NEW
bullet).

## Trust model

`mpm` clones and reads manifest repos, resolves transitive XML manifests,
and (via `mpm install`) `git clone`s every `<project>` reference. Every
step executes git operations against URLs the catalog author controls.
**Manifest-repo content is trusted code from the operator's perspective**,
equivalent in trust level to a pip index URL or an npm registry.

This spec does NOT introduce signing, attestation, or a central allow-list.
The trust model is:

- **The operator chooses the catalog source.** Whoever can write to the
  manifest repo can change what `mpm install` fetches.

- **Provider-agnostic.** Any git URL is acceptable: any vendor-hosted git
  service, self-hosted GitOps, local `file://` paths for testing. `mpm`
  never inspects the host, never special-cases known providers, never
  reaches for a provider CLI. Operators on git providers without a public
  CLI (or behind a corporate firewall using a self-hosted git server) are
  first-class users.

- **No credential handling.** mpm NEVER prompts for credentials, NEVER
  caches them, NEVER interacts with auth providers. Every `git ls-remote`
  and `git clone` inherits the operator's local git client configuration:
  `~/.gitconfig`, credential helpers (e.g., `osxkeychain`,
  `git-credential-oauth`, `git-credential-manager`), SSH agent and
  `~/.ssh/config`, `url.insteadOf` rewrites. Auth setup is the operator's
  responsibility; see [`docs/git-auth-setup.md`](git-auth-setup.md) for
  supported configurations on common platforms.

- **HTTPS by default for `<remote>` URLs in manifests.** `mpm catalog
  audit` and existing `mpm validate marketplace` checks refuse non-HTTPS
  `<remote>` URLs unless `MPM_ALLOW_INSECURE_REMOTES=1` is explicitly
  set. SSH URLs (`git@host:org/repo.git` or `ssh://git@host/org/repo`) are
  HTTPS-equivalent for trust purposes and allowed. `file://` URLs are
  allowed only when `MPM_ALLOW_INSECURE_REMOTES=1` (intended for tests
  and local fixtures only). The operator's choice between HTTPS and SSH
  transports is handled by their git client's `url.insteadOf` rewrites;
  mpm does not see the difference.

- **The catalog source is surfaced.** `mpm doctor` prints the effective
  catalog source so the operator can verify before running side-effecting
  commands. This catches accidental leakage of `MPM_CATALOG_SOURCES` from
  a shell profile into an unrelated workspace. See
  [`docs/doctor.md`](cli/doctor.md) for the full `mpm doctor` reference.

- **Cache files are user-private.** `${MPM_HOME}/cache` and every file
  under it are created with mode `0700` (directories) and `0600` (files)
  to prevent another local user from poisoning completion candidates.

- **Completion candidates are shell-escaped.** Cached names that contain
  shell metacharacters or embedded newlines are filtered out to prevent
  them from breaking the shell completion protocol or injecting characters
  into the shell line.

See [`docs/configuration.md`](configuration.md) for the full set of
environment variables that control mpm's behaviour, including
`MPM_ALLOW_INSECURE_REMOTES`, `MPM_HOME`, and
`MPM_CATALOG_SOURCES`.

## What manifest repos can do to you

When you configure a catalog source, you are trusting that repository to the
same degree you trust a package registry. Operators should understand the
following threat surface:

- **Arbitrary `git clone` URLs.** A manifest repo can reference any
  `<remote>` URL. `mpm install` will attempt to clone every URL named in
  the resolved manifest. A compromised or malicious manifest repo can direct
  your workstation or CI runner to clone from an attacker-controlled host.

- **Arbitrary tag-name pinning.** A manifest repo controls the exact tag
  each `<project>` resolves to. A catalog author can change what a tag
  reference points to on their git host. Lockfiles pin the SHA at lock
  time; always verify the lockfile after `mpm add` or
  `mpm install --refresh-lock`.

- **Arbitrary `<include>` chain extension.** Manifest files can include
  other manifest files via `<include>`. A manifest repo can extend its
  own include graph at any time, pulling in additional manifests from the
  same or other repositories.

- **`<remote>` URL rewriting.** A `<remote>` element in a manifest file
  can map a logical name to any fetch URL. This mapping can be changed by
  the catalog author in subsequent commits.

Mitigations: pin catalog sources to a specific git SHA via
`MPM_CATALOG_SOURCES=<url>@<sha>`, review lockfile diffs before applying
them, and restrict write access to your manifest repo. See
[`docs/configuration.md`](configuration.md) for catalog-source pinning.

## What mpm does NOT do

mpm is deliberately scoped to git-binary operations only. The following
interactions are permanently out of scope:

- **No credential handling.** mpm does not prompt for credentials, store
  them, read them from environment variables such as `GITHUB_TOKEN` or
  `GITLAB_TOKEN`, or pass them to any subprocess. All authentication is
  delegated to the operator's git client (credential helpers, SSH agent).

- **No provider HTTP API calls.** mpm never contacts provider-specific
  REST or GraphQL APIs. Examples of calls mpm does not make:
  `api.github.com`, `gitlab.com/api/v4`, `bitbucket.org/!api`,
  `dev.azure.com/_apis`, `api.codecommit.*`, or any vendor-hosted
  registry endpoint.

- **No provider-CLI shell-outs.** mpm never invokes provider-specific
  command-line tools. Examples: `gh` (GitHub CLI), `glab` (GitLab CLI),
  `bb` (Bitbucket CLI), `tea` (Gitea CLI), `aws codecommit`,
  `az repos`. Every git interaction goes through the `git` binary only.

- **No interactive prompts.** mpm is non-interactive in all code paths.
  It never reads from a TTY, never pauses waiting for user input, and
  never displays a confirmation dialog. Commands that encounter an
  unrecoverable error exit immediately with a non-zero status and a
  message on stderr.

- **No implicit trust based on host.** mpm does not treat any git host
  as canonical, trusted, or special. A URL hosted on a well-known domain
  receives no additional trust relative to a self-hosted server.

## Auth-error retry-skip policy

mpm detects authentication errors in `git` stderr output for
**retry-policy purposes only**. The patterns are defined in
`GIT_AUTH_ERROR_PATTERNS` in `src/mpm_cli/constants.py` (examples:
`Authentication failed`, `Permission denied`).

When a `git ls-remote` call exits non-zero and its stderr matches one of
these patterns, mpm skips the remaining retry attempts immediately. This
avoids locking out accounts that have rate-limited or account-lock policies
on repeated failed authentication attempts.

This detection is **not** credential handling. mpm reads the stderr string
only to decide whether to retry; it does not extract, log, store, or act on
any credential material in the output.

Retry behaviour is governed by `MPM_GIT_RETRY_COUNT` (number of attempts)
and `MPM_GIT_RETRY_DELAY` (seconds between attempts). See
[`docs/configuration.md`](configuration.md) for the full reference.

## Out of scope

The following security features are explicitly out of scope for this
specification and tracked as future work (spec Section 3.6):

- Signed catalogs (e.g., in-toto attestations attached to manifest repo
  tags).
- Transparency logs for catalog mutations.
- Central registry of approved manifest repos.
- Allow-list of approved manifest repos enforced by mpm itself.

## See also

- [`docs/git-auth-setup.md`](git-auth-setup.md) -- configuring credential
  helpers, SSH agents, and `url.insteadOf` rewrites so mpm can reach
  your manifest repos without interactive prompts.
- [`docs/configuration.md`](configuration.md) -- full reference for
  environment variables including `MPM_CATALOG_SOURCES`,
  `MPM_ALLOW_INSECURE_REMOTES`, `MPM_GIT_RETRY_COUNT`,
  `MPM_GIT_RETRY_DELAY`, and `MPM_HOME`.
- [`docs/doctor.md`](cli/doctor.md) -- `mpm doctor` command reference,
  including how the effective catalog source is surfaced and what the
  remote-reachability sanity check does.
