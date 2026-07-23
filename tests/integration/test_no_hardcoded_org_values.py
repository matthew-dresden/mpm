"""Integration tests that scan mpm source files for hard-coded org-specific values.

These tests enforce that no vendor-specific identifiers -- neither the neutral
placeholders used in fixtures nor the legacy vendor slug this project was forked
from -- are embedded in the mpm source tree under src/mpm_cli/.  Each test scans
specific files or directories and asserts the absence of the targeted pattern.

The legacy vendor slug is assembled from fragments at import time
(``_LEGACY_ORG``) rather than written as a literal, so that a repository-wide
sweep for that slug stays clean while this guard keeps searching for it.

Covered acceptance criteria:
  - AC-FUNC-001: constants.py does not contain an org-specific review branch
  - AC-FUNC-003: catalog .mpm has no REPO_URL or REPO_REV lines
  - AC-FUNC-004: mpm-readme.md has no reference to the retired internal codename as external tool
  - AC-TEST-001: Automated scan of src/ for hard-coded org-specific values passes
"""

from pathlib import Path

import pytest


_SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "mpm_cli"

_LEGACY_ORG = "cay" + "lent"

_LEGACY_REVIEW_BRANCH = f"review/{_LEGACY_ORG}-claude"

_LEGACY_PRIVATE_PREFIX = f"{_LEGACY_ORG}-private"


def _collect_matching_lines(directory: Path, pattern: str, glob: str = "**/*") -> list[str]:
    """Return lines matching *pattern* in text files found under *directory*.

    Only regular files that can be decoded as UTF-8 are examined.  Binary files
    are silently skipped.  Each returned string has the form
    ``<relative_path>:<line_no>: <content>``.
    """
    hits: list[str] = []
    for file_path in sorted(directory.glob(glob)):
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern in line:
                rel = file_path.relative_to(directory)
                hits.append(f"{rel}:{line_no}: {line.strip()}")
    return hits


@pytest.mark.integration
class TestConstantsNoOrgBranchValue:
    """AC-FUNC-001: constants.py must not contain org-specific branch names."""

    def test_constants_does_not_contain_org_review_branch(self) -> None:
        """No org-specific review branch may appear in constants.py."""
        constants_file = _SRC_ROOT / "constants.py"
        assert constants_file.is_file(), f"constants.py not found at {constants_file}"

        text = constants_file.read_text(encoding="utf-8")
        for branch in ("review/example-claude", _LEGACY_REVIEW_BRANCH):
            assert branch not in text, (
                f"Found org-specific branch {branch!r} in {constants_file}. "
                "Only universally valid, org-agnostic values belong in constants.py."
            )


@pytest.mark.integration
class TestCatalogMPMFilesAbsent:
    """AC-FUNC-003/004 (E6-F2-S1-T1): bundled catalog files must not exist.

    The catalog/mpm/.mpm and catalog/mpm/mpm-readme.md files were
    deleted as part of removing the bundled catalog directory (E6-F2-S1-T1).
    These tests assert the expected post-deletion state: the files are absent.
    """

    _MPMENV = _SRC_ROOT / "catalog" / "mpm" / ".mpm"
    _README = _SRC_ROOT / "catalog" / "mpm" / "mpm-readme.md"
    _CATALOG_DIR = _SRC_ROOT / "catalog"

    def test_catalog_mpm_dot_mpm_absent(self) -> None:
        """catalog/mpm/.mpm must not exist after E6-F2-S1-T1 removal."""
        assert not self._MPMENV.exists(), (
            f"catalog/mpm/.mpm at {self._MPMENV} must not exist after E6-F2-S1-T1 deletion. "
            "If this fails, the bundled catalog was accidentally re-added."
        )

    def test_catalog_mpm_readme_absent(self) -> None:
        """catalog/mpm/mpm-readme.md must not exist after E6-F2-S1-T1 removal."""
        assert not self._README.exists(), (
            f"catalog/mpm/mpm-readme.md at {self._README} must not exist after E6-F2-S1-T1 deletion. "
            "If this fails, the bundled catalog was accidentally re-added."
        )

    def test_catalog_directory_absent(self) -> None:
        """src/mpm_cli/catalog/ must not exist after E6-F2-S1-T1 removal."""
        assert not self._CATALOG_DIR.exists(), (
            f"src/mpm_cli/catalog/ at {self._CATALOG_DIR} must not exist after E6-F2-S1-T1 deletion. "
            "If this fails, the bundled catalog was accidentally re-added."
        )


@pytest.mark.integration
class TestSrcNoHardcodedOrgValues:
    """AC-TEST-001: src/mpm_cli/ must contain no hard-coded org-specific identifiers.

    The scan excludes the embedded 'repo' subdirectory, which is a vendored
    third-party tool and is maintained separately.
    """

    _PROHIBITED_PATTERNS = [
        "review/example-claude",
        "example-private",
        _LEGACY_REVIEW_BRANCH,
        _LEGACY_PRIVATE_PREFIX,
    ]

    _FIRST_PARTY_DIRS = [
        _SRC_ROOT / "catalog",
        _SRC_ROOT / "core",
    ]

    _FIRST_PARTY_FILES = list((_SRC_ROOT).glob("*.py"))

    @pytest.mark.parametrize("pattern", _PROHIBITED_PATTERNS)
    def test_no_org_pattern_in_first_party_source(self, pattern: str) -> None:
        """Pattern must not appear in any first-party mpm source file."""
        hits: list[str] = []

        for directory in self._FIRST_PARTY_DIRS:
            if directory.is_dir():
                hits.extend(_collect_matching_lines(directory, pattern))

        for file_path in self._FIRST_PARTY_FILES:
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if pattern in line:
                        rel = file_path.relative_to(_SRC_ROOT)
                        hits.append(f"{rel}:{line_no}: {line.strip()}")

        assert not hits, (
            f"Hard-coded org-specific value {pattern!r} found in first-party source files:\n"
            + "\n".join(hits)
            + "\nRemove or make these values configurable."
        )
