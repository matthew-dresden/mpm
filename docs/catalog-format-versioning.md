# Catalog Format Versioning

## Status

The catalog-format versioning handshake is **future work** tracked in spec
Section 15 (`<catalog-format-version>` element). This document is a
placeholder so that future implementation has a stable documentation URL and
so that design intent is recorded alongside the rest of the catalog
documentation.

No version-handshake logic exists in mpm today. See
[Current behaviour](#current-behaviour) below.

## Planned scope

When the handshake is implemented, it will cover three areas:

1. **Manifest-repo-declared format version.** A manifest repository will
   declare the format version it uses, either as a `<format-version>` element
   inside `<catalog-metadata>` in the entry manifest or as a top-level
   sentinel file (e.g., `repo-specs/.mpm-catalog-version`). The exact
   mechanism is not yet decided.

2. **mpm CLI supported-version range.** Each mpm release will advertise
   the range of format versions it can read (e.g., `>=1, <3`). The range
   will be encoded in the CLI source, not hard-coded in manifests.

3. **Negotiation rule.** The rule will follow a forward-compatible-read
   approach: mpm can read any format version within its supported range
   without error. If the manifest repo declares a format version outside that
   range, mpm exits with a hard error and an actionable message telling the
   operator which mpm version supports the declared format.

## Current behaviour

mpm does **not** inspect a format version today. Manifest repositories and
the mpm CLI evolve together under a shared release cadence. If a manifest
repo uses a feature that the installed mpm version does not support, the
failure mode is an unrelated parse error or a missing-feature error -- not a
format-version hard-error.

Operators relying on this implicit coupling should be aware that a future
mpm release will introduce the formal version handshake described above.

## See also

- [catalogs-explained.md](catalogs-explained.md) -- overview of how mpm
  catalogs work and how they relate to manifest repositories.
- [creating-manifest-repos.md](creating-manifest-repos.md) -- how to author
  and maintain a manifest repository, including the `<catalog-metadata>`
  element and the `repo-specs/` directory layout.
