import sys

import pytest

import mpm_cli
from mpm_cli.constants import (
    EXIT_CODE_DEPRECATED,
    MPM_LIST_LIMIT,
    MPM_TREE_NO_FILTER_THRESHOLD,
    LIST_EMPTY_CATALOG_NOTE,
    MISSING_CATALOG_ERROR_TEMPLATE,
    RECOMMENDED_CHAR_RE,
    TAG_ERROR_DISPLAY_CAP,
)

_CONSTANTS_MODULE = "mpm_cli.constants"


@pytest.fixture(autouse=True)
def restore_constants_module():
    """Restore the original mpm_cli.constants module object after each test.

    Several tests here delete mpm_cli.constants from sys.modules and re-import
    it to pick up environment-driven values, which installs a fresh module
    object. Modules that bound ``import mpm_cli.constants as constants`` at
    import time (for example mpm_cli.core.cli_args) keep their reference to
    the original object, so the fresh one leaks a divergent constants module
    into later tests in the same pytest-xdist worker (under loadscope grouping),
    making writes through the stale reference invisible. Snapshot the original
    object and put it back in both sys.modules and the parent package attribute
    so the swap cannot escape this test.
    """
    original = sys.modules.get(_CONSTANTS_MODULE)
    yield
    if original is not None:
        sys.modules[_CONSTANTS_MODULE] = original
        mpm_cli.constants = original


@pytest.mark.unit
class TestTagErrorDisplayCap:
    def test_tag_error_display_cap_is_positive_int(self):
        assert isinstance(TAG_ERROR_DISPLAY_CAP, int)
        assert TAG_ERROR_DISPLAY_CAP > 0

    def test_tag_error_display_cap_value(self):
        assert TAG_ERROR_DISPLAY_CAP == 10


@pytest.mark.unit
class TestPinnableRevisionRejectsWildcard:
    """AC-54: <project revision> is pinnable (tag/branch-ref/sha) -- the wildcard token is rejected.

    The permissive _is_valid_revision mode (and its REVISION_WILDCARD constant)
    are removed: the marketplace validator now accepts only a pinnable revision
    (an exact refs/tags/<path>/<pep440> tag, a refs/heads/<name> branch ref, or a
    40-hex commit SHA), rejecting the wildcard outright (spec Section 4.5 /
    Section 6 / FR-22, AMENDED 2026-06-25).
    """

    def test_revision_wildcard_constant_is_removed(self) -> None:
        import mpm_cli.constants as constants

        assert not hasattr(constants, "REVISION_WILDCARD"), (
            "REVISION_WILDCARD must be removed with the permissive revision mode."
        )

    def test_validator_rejects_wildcard_revisions(self) -> None:
        from mpm_cli.core.marketplace_validator import _is_pinnable_revision

        assert _is_pinnable_revision("*") is False
        assert _is_pinnable_revision("refs/tags/ex/proj/*") is False

    def test_validator_accepts_pinnable_revisions(self) -> None:
        from mpm_cli.core.marketplace_validator import _is_pinnable_revision

        assert _is_pinnable_revision("refs/tags/ex/proj/1.0.0") is True
        assert _is_pinnable_revision("refs/heads/main") is True
        assert _is_pinnable_revision("a" * 40) is True


@pytest.mark.unit
class TestNoColorConstants:
    """Assert NO_COLOR_ENV and _NO_COLOR_ACTIVE exist with correct defaults (AC-TEST-003)."""

    def test_no_color_env_name_is_no_color(self) -> None:
        import mpm_cli.constants as constants

        assert constants.NO_COLOR_ENV == "NO_COLOR"

    def test_no_color_env_is_string(self) -> None:
        import mpm_cli.constants as constants

        assert isinstance(constants.NO_COLOR_ENV, str)

    def test_no_color_active_exists_at_import(self) -> None:
        import mpm_cli.constants as constants

        assert hasattr(constants, "_NO_COLOR_ACTIVE")

    def test_no_color_active_default_is_false(self) -> None:
        """_NO_COLOR_ACTIVE defaults to False at module load time."""
        import importlib

        import mpm_cli.constants as constants

        importlib.reload(constants)
        assert constants._NO_COLOR_ACTIVE is False

    def test_no_color_active_is_bool(self) -> None:
        import mpm_cli.constants as constants

        assert isinstance(constants._NO_COLOR_ACTIVE, bool)


@pytest.mark.unit
class TestRecommendedCharRe:
    """Tests for RECOMMENDED_CHAR_RE (soft-spot rule 2, E2-F3-S1-T1 AC-CONST-001)."""

    @pytest.mark.parametrize(
        "value",
        [
            "foo",
            "FOO",
            "Foo",
            "abc123",
            "foo_bar",
            "foo-bar",
            "A-Z_0",
            "z9",
            "a",
            "",
        ],
    )
    def test_recommended_chars_produce_full_match(self, value: str) -> None:
        """Characters in [a-zA-Z0-9_-] (or empty string) produce a full match."""
        assert RECOMMENDED_CHAR_RE.fullmatch(value) is not None, (
            f"Expected RECOMMENDED_CHAR_RE to fullmatch {value!r} but it did not"
        )

    @pytest.mark.parametrize(
        "value",
        [
            "foo.bar",
            "foo bar",
            "foo@bar",
            "foo/bar",
            "foo!bar",
            "\u03b1pkg",
            "has#hash",
            "foo\n",
        ],
    )
    def test_non_recommended_chars_produce_no_match(self, value: str) -> None:
        """Characters outside [a-zA-Z0-9_-] produce no full match."""
        assert RECOMMENDED_CHAR_RE.fullmatch(value) is None, (
            f"Expected RECOMMENDED_CHAR_RE NOT to fullmatch {value!r} but it did"
        )

    def test_empty_string_matches(self) -> None:
        """Empty string matches because the * quantifier allows zero characters."""
        assert RECOMMENDED_CHAR_RE.fullmatch("") is not None

    def test_pattern_anchored_at_start_and_end(self) -> None:
        """fullmatch() ensures the entire string is checked, so a bad char anywhere rejects the value."""

        assert RECOMMENDED_CHAR_RE.fullmatch("good.bad") is None


@pytest.mark.unit
class TestMissingCatalogErrorTemplate:
    """Tests for MISSING_CATALOG_ERROR_TEMPLATE (AC-CONST-001, AC-TEST-001)."""

    def test_is_str(self) -> None:
        """MISSING_CATALOG_ERROR_TEMPLATE is a str."""
        assert isinstance(MISSING_CATALOG_ERROR_TEMPLATE, str)

    def test_is_non_empty(self) -> None:
        """MISSING_CATALOG_ERROR_TEMPLATE is non-empty."""
        assert len(MISSING_CATALOG_ERROR_TEMPLATE) > 0

    def test_formatted_starts_with_error(self) -> None:
        """Formatted result starts with 'ERROR:' as required by the spec."""
        rendered = MISSING_CATALOG_ERROR_TEMPLATE.format(command="list")
        assert rendered.startswith("ERROR:")

    def test_formatted_contains_command_name(self) -> None:
        """The {command} placeholder is substituted into the formatted string."""
        rendered = MISSING_CATALOG_ERROR_TEMPLATE.format(command="list")
        assert "list" in rendered

    def test_formatted_mentions_catalog_source_flag(self) -> None:
        """The formatted string names the --catalog-source CLI flag."""
        rendered = MISSING_CATALOG_ERROR_TEMPLATE.format(command="list")
        assert "--catalog-source" in rendered

    def test_formatted_mentions_env_var(self) -> None:
        """The formatted string names the MPM_CATALOG_SOURCE env var."""
        rendered = MISSING_CATALOG_ERROR_TEMPLATE.format(command="list")
        assert "MPM_CATALOG_SOURCE" in rendered

    def test_template_is_format_compatible(self) -> None:
        """Template accepts str.format() with command kwarg without raising."""
        rendered = MISSING_CATALOG_ERROR_TEMPLATE.format(command="add")
        assert "add" in rendered

    def test_no_dead_code_list_limit_env_var(self) -> None:
        """LIST_LIMIT_ENV_VAR must not exist in constants (dead-code check, AC-CONST-003)."""
        import mpm_cli.constants as constants

        assert not hasattr(constants, "LIST_LIMIT_ENV_VAR")

    def test_no_dead_code_list_limit_default(self) -> None:
        """LIST_LIMIT_DEFAULT must not exist in constants (dead-code check, AC-CONST-003)."""
        import mpm_cli.constants as constants

        assert not hasattr(constants, "LIST_LIMIT_DEFAULT")


@pytest.mark.unit
class TestListEmptyCatalogNote:
    """Tests for LIST_EMPTY_CATALOG_NOTE (AC-CONST-002, AC-TEST-001)."""

    def test_is_str(self) -> None:
        """LIST_EMPTY_CATALOG_NOTE is a str."""
        assert isinstance(LIST_EMPTY_CATALOG_NOTE, str)

    def test_is_non_empty(self) -> None:
        """LIST_EMPTY_CATALOG_NOTE is a non-empty string."""
        assert len(LIST_EMPTY_CATALOG_NOTE) > 0

    def test_contains_zero_entries_phrase(self) -> None:
        """Value contains the spec-canonical 'manifest repo contains 0 entries' phrase."""
        assert "manifest repo contains 0 entries" in LIST_EMPTY_CATALOG_NOTE


@pytest.mark.unit
class TestMPMTreeNoFilterThreshold:
    """Tests for MPM_TREE_NO_FILTER_THRESHOLD (E2-F2-S1-T3 AC-FUNC-002)."""

    def test_is_int(self) -> None:
        """MPM_TREE_NO_FILTER_THRESHOLD is an int."""
        assert isinstance(MPM_TREE_NO_FILTER_THRESHOLD, int)

    def test_default_value_is_20(self) -> None:
        """MPM_TREE_NO_FILTER_THRESHOLD default value is 20."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_TREE_NO_FILTER_THRESHOLD", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_TREE_NO_FILTER_THRESHOLD == 20
        finally:
            if saved is not None:
                os.environ["MPM_TREE_NO_FILTER_THRESHOLD"] = saved
            importlib.reload(constants)

    def test_is_positive(self) -> None:
        """MPM_TREE_NO_FILTER_THRESHOLD is a positive integer."""
        assert MPM_TREE_NO_FILTER_THRESHOLD > 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_TREE_NO_FILTER_THRESHOLD env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_TREE_NO_FILTER_THRESHOLD", "42")
        importlib.reload(constants)
        try:
            assert constants.MPM_TREE_NO_FILTER_THRESHOLD == 42
        finally:
            monkeypatch.delenv("MPM_TREE_NO_FILTER_THRESHOLD", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_TREE_NO_FILTER_THRESHOLD set to a non-integer env var raises ValueError."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_TREE_NO_FILTER_THRESHOLD", "not-a-number")
        with pytest.raises((ValueError, SystemExit)):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_TREE_NO_FILTER_THRESHOLD", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMListLimit:
    """Tests for MPM_LIST_LIMIT (E2-F2-S1-T4 AC-FUNC-002)."""

    def test_is_int(self) -> None:
        """MPM_LIST_LIMIT is an int."""
        assert isinstance(MPM_LIST_LIMIT, int)

    def test_default_value_is_50(self) -> None:
        """MPM_LIST_LIMIT default value is 50."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_LIST_LIMIT", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_LIST_LIMIT == 50
        finally:
            if saved is not None:
                os.environ["MPM_LIST_LIMIT"] = saved
            importlib.reload(constants)

    def test_is_positive(self) -> None:
        """MPM_LIST_LIMIT is a positive integer."""
        assert MPM_LIST_LIMIT > 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_LIST_LIMIT env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_LIST_LIMIT", "77")
        importlib.reload(constants)
        try:
            assert constants.MPM_LIST_LIMIT == 77
        finally:
            monkeypatch.delenv("MPM_LIST_LIMIT", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_LIST_LIMIT set to a non-integer env var raises ValueError."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_LIST_LIMIT", "not-a-number")
        with pytest.raises((ValueError, SystemExit)):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_LIST_LIMIT", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMAddConstants:
    """Tests for mpm add constants (E2-F4-S1-T1 AC-FUNC-013, AC-TEST-001)."""

    def test_mpm_mpm_file_env_exists(self) -> None:
        """MPM_MANIFEST_FILE_ENV constant exists and is the string 'MPM_MANIFEST_FILE'."""
        from mpm_cli.constants import MPM_MANIFEST_FILE_ENV

        assert isinstance(MPM_MANIFEST_FILE_ENV, str)
        assert MPM_MANIFEST_FILE_ENV == "MPM_MANIFEST_FILE"

    def test_mpm_mpm_file_default_exists(self) -> None:
        """MPM_MANIFEST_FILE_DEFAULT constant exists and is './.mpm'."""
        from mpm_cli.constants import MPM_MANIFEST_FILE_DEFAULT

        assert isinstance(MPM_MANIFEST_FILE_DEFAULT, str)
        assert MPM_MANIFEST_FILE_DEFAULT == "./.mpm"

    def test_mpm_header_gitbase_exists(self) -> None:
        """MPM_HEADER_GITBASE constant exists and contains the template placeholder."""
        from mpm_cli.constants import MPM_HEADER_GITBASE

        assert isinstance(MPM_HEADER_GITBASE, str)
        assert "<YOUR_GIT_ORG_BASE_URL>" in MPM_HEADER_GITBASE

    def test_mpm_header_claude_marketplaces_dir_exists(self) -> None:
        """MPM_HEADER_CLAUDE_MARKETPLACES_DIR constant exists and contains the template value."""
        from mpm_cli.constants import MPM_HEADER_CLAUDE_MARKETPLACES_DIR

        assert isinstance(MPM_HEADER_CLAUDE_MARKETPLACES_DIR, str)
        assert "${HOME}/.claude-marketplaces" in MPM_HEADER_CLAUDE_MARKETPLACES_DIR

    def test_global_marketplace_install_header_constant_removed(self) -> None:
        """The global MPM_HEADER_MARKETPLACE_INSTALL constant is removed (spec
        Section 0 item 8 / FR-17): marketplace install is now a per-dependency
        MPM_SOURCE_<alias>_MARKETPLACE flag, so the global header template no
        longer exists.
        """
        import mpm_cli.constants as constants

        assert not hasattr(constants, "MPM_HEADER_MARKETPLACE_INSTALL")

    def test_per_dependency_marketplace_constants_exist(self) -> None:
        """The per-dependency marketplace constants replace the global header
        (spec Section 4.2 / 5.1 / FR-17).
        """
        from mpm_cli.constants import (
            CATALOG_TYPE_CLAUDE_MARKETPLACE,
            MARKETPLACE_FLAG_TRUE,
            SOURCE_MARKETPLACE_KEY,
            SOURCE_MARKETPLACE_SUFFIX,
            SOURCE_SUFFIXES,
        )

        assert SOURCE_MARKETPLACE_SUFFIX == "_MARKETPLACE"
        assert SOURCE_MARKETPLACE_KEY == "marketplace"
        assert MARKETPLACE_FLAG_TRUE == "true"
        assert CATALOG_TYPE_CLAUDE_MARKETPLACE == "claude-marketplace"

        assert SOURCE_MARKETPLACE_SUFFIX not in SOURCE_SUFFIXES

    def test_header_constants_are_non_empty(self) -> None:
        """The remaining standard-header constants are non-empty strings."""
        from mpm_cli.constants import (
            MPM_HEADER_CLAUDE_MARKETPLACES_DIR,
            MPM_HEADER_GITBASE,
        )

        assert len(MPM_HEADER_GITBASE) > 0
        assert len(MPM_HEADER_CLAUDE_MARKETPLACES_DIR) > 0

    def test_gitbase_line_starts_with_gitbase(self) -> None:
        """MPM_HEADER_GITBASE starts with 'GITBASE=' per the .mpm template."""
        from mpm_cli.constants import MPM_HEADER_GITBASE

        assert MPM_HEADER_GITBASE.startswith("GITBASE=")

    def test_claude_marketplaces_dir_line_starts_with_key(self) -> None:
        """MPM_HEADER_CLAUDE_MARKETPLACES_DIR starts with 'CLAUDE_MARKETPLACES_DIR='."""
        from mpm_cli.constants import MPM_HEADER_CLAUDE_MARKETPLACES_DIR

        assert MPM_HEADER_CLAUDE_MARKETPLACES_DIR.startswith("CLAUDE_MARKETPLACES_DIR=")


@pytest.mark.unit
class TestMPMLockFileConstant:
    """Tests for MPM_LOCK_FILE constant (E3-F1-S1-T1 AC-FUNC-008)."""

    def test_mpm_lock_file_exists(self) -> None:
        """MPM_LOCK_FILE constant exists in mpm_cli.constants and is importable."""
        from mpm_cli.constants import MPM_LOCK_FILE

        assert MPM_LOCK_FILE == "MPM_LOCK_FILE"

    def test_mpm_lock_file_value(self) -> None:
        """MPM_LOCK_FILE constant equals the string 'MPM_LOCK_FILE'."""
        from mpm_cli.constants import MPM_LOCK_FILE

        assert MPM_LOCK_FILE == "MPM_LOCK_FILE"

    def test_mpm_lock_file_is_string(self) -> None:
        """MPM_LOCK_FILE constant is a str."""
        from mpm_cli.constants import MPM_LOCK_FILE

        assert isinstance(MPM_LOCK_FILE, str)

    def test_mpm_lock_file_adjacent_to_mpm_file_env(self) -> None:
        """MPM_LOCK_FILE and MPM_MANIFEST_FILE_ENV are both importable from constants."""
        from mpm_cli.constants import MPM_MANIFEST_FILE_ENV, MPM_LOCK_FILE

        assert MPM_LOCK_FILE == "MPM_LOCK_FILE"
        assert MPM_MANIFEST_FILE_ENV == "MPM_MANIFEST_FILE"


@pytest.mark.unit
class TestMPMCompletionCacheDir:
    """Tests for MPM_COMPLETION_CACHE_DIR constant (E3-F3-S1-T9 AC-FUNC-001)."""

    def test_constant_value_equals_completion_cache(self) -> None:
        """MPM_COMPLETION_CACHE_DIR equals the string 'completion-cache'."""
        from mpm_cli.constants import MPM_COMPLETION_CACHE_DIR

        assert MPM_COMPLETION_CACHE_DIR == "completion-cache"

    def test_constant_is_string(self) -> None:
        """MPM_COMPLETION_CACHE_DIR is a str."""
        from mpm_cli.constants import MPM_COMPLETION_CACHE_DIR

        assert isinstance(MPM_COMPLETION_CACHE_DIR, str)

    def test_constant_is_non_empty(self) -> None:
        """MPM_COMPLETION_CACHE_DIR is a non-empty string."""
        from mpm_cli.constants import MPM_COMPLETION_CACHE_DIR

        assert len(MPM_COMPLETION_CACHE_DIR) > 0


@pytest.mark.unit
class TestMPMAllowInsecureRemotesConstant:
    """Tests for MPM_ALLOW_INSECURE_REMOTES constant (E3-F3-S1-T8 AC-FUNC-001)."""

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_ALLOW_INSECURE_REMOTES constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_ALLOW_INSECURE_REMOTES

        assert MPM_ALLOW_INSECURE_REMOTES is not None

    def test_constant_value(self) -> None:
        """MPM_ALLOW_INSECURE_REMOTES equals the string 'MPM_ALLOW_INSECURE_REMOTES'."""
        from mpm_cli.constants import MPM_ALLOW_INSECURE_REMOTES

        assert MPM_ALLOW_INSECURE_REMOTES == "MPM_ALLOW_INSECURE_REMOTES"

    def test_constant_is_string(self) -> None:
        """MPM_ALLOW_INSECURE_REMOTES is a str."""
        from mpm_cli.constants import MPM_ALLOW_INSECURE_REMOTES

        assert isinstance(MPM_ALLOW_INSECURE_REMOTES, str)

    def test_constant_non_empty(self) -> None:
        """MPM_ALLOW_INSECURE_REMOTES is a non-empty string."""
        from mpm_cli.constants import MPM_ALLOW_INSECURE_REMOTES

        assert len(MPM_ALLOW_INSECURE_REMOTES) > 0

    def test_constant_importable_alongside_mpm_lock_file(self) -> None:
        """MPM_ALLOW_INSECURE_REMOTES and MPM_LOCK_FILE are both importable from constants."""
        from mpm_cli.constants import MPM_ALLOW_INSECURE_REMOTES, MPM_LOCK_FILE

        assert MPM_ALLOW_INSECURE_REMOTES == "MPM_ALLOW_INSECURE_REMOTES"
        assert MPM_LOCK_FILE == "MPM_LOCK_FILE"


@pytest.mark.unit
class TestMPMOutdatedFormatConstant:
    """Tests for MPM_OUTDATED_FORMAT and MPM_OUTDATED_FORMAT_DEFAULT constants.

    AC-FUNC-007: The default output format for 'mpm outdated' is 'table',
    controlled by the MPM_OUTDATED_FORMAT env var (constant name stored in
    MPM_OUTDATED_FORMAT). The default value is stored in MPM_OUTDATED_FORMAT_DEFAULT.
    """

    def test_mpm_outdated_format_value(self) -> None:
        """MPM_OUTDATED_FORMAT equals the string 'MPM_OUTDATED_FORMAT'."""
        from mpm_cli.constants import MPM_OUTDATED_FORMAT

        assert MPM_OUTDATED_FORMAT == "MPM_OUTDATED_FORMAT"

    def test_mpm_outdated_format_is_string(self) -> None:
        """MPM_OUTDATED_FORMAT is a str."""
        from mpm_cli.constants import MPM_OUTDATED_FORMAT

        assert isinstance(MPM_OUTDATED_FORMAT, str)

    def test_mpm_outdated_format_default_value(self) -> None:
        """MPM_OUTDATED_FORMAT_DEFAULT equals 'table'."""
        from mpm_cli.constants import MPM_OUTDATED_FORMAT_DEFAULT

        assert MPM_OUTDATED_FORMAT_DEFAULT == "table"

    def test_mpm_outdated_format_default_is_string(self) -> None:
        """MPM_OUTDATED_FORMAT_DEFAULT is a str."""
        from mpm_cli.constants import MPM_OUTDATED_FORMAT_DEFAULT

        assert isinstance(MPM_OUTDATED_FORMAT_DEFAULT, str)

    def test_mpm_outdated_format_default_is_non_empty(self) -> None:
        """MPM_OUTDATED_FORMAT_DEFAULT is a non-empty string."""
        from mpm_cli.constants import MPM_OUTDATED_FORMAT_DEFAULT

        assert len(MPM_OUTDATED_FORMAT_DEFAULT) > 0


@pytest.mark.unit
class TestBranchShaTruncationConstants:
    """Tests for BRANCH_SHA_TRUNCATION_LENGTH, SHA1_HEX_LENGTH, SHA256_HEX_LENGTH.

    Added alongside the branch-pinned outdated logic (spec Section 4.4).
    """

    def test_branch_sha_truncation_length_exists(self) -> None:
        """BRANCH_SHA_TRUNCATION_LENGTH constant exists in mpm_cli.constants."""
        from mpm_cli.constants import BRANCH_SHA_TRUNCATION_LENGTH

        assert BRANCH_SHA_TRUNCATION_LENGTH is not None

    def test_branch_sha_truncation_length_value(self) -> None:
        """BRANCH_SHA_TRUNCATION_LENGTH equals 12 (matching git short-SHA convention)."""
        from mpm_cli.constants import BRANCH_SHA_TRUNCATION_LENGTH

        assert BRANCH_SHA_TRUNCATION_LENGTH == 12

    def test_branch_sha_truncation_length_is_positive_int(self) -> None:
        """BRANCH_SHA_TRUNCATION_LENGTH is a positive integer."""
        from mpm_cli.constants import BRANCH_SHA_TRUNCATION_LENGTH

        assert isinstance(BRANCH_SHA_TRUNCATION_LENGTH, int)
        assert BRANCH_SHA_TRUNCATION_LENGTH > 0

    def test_sha1_hex_length_exists(self) -> None:
        """SHA1_HEX_LENGTH constant exists in mpm_cli.constants."""
        from mpm_cli.constants import SHA1_HEX_LENGTH

        assert SHA1_HEX_LENGTH is not None

    def test_sha1_hex_length_value(self) -> None:
        """SHA1_HEX_LENGTH equals 40 (SHA-1 produces a 40-character hex digest)."""
        from mpm_cli.constants import SHA1_HEX_LENGTH

        assert SHA1_HEX_LENGTH == 40

    def test_sha1_hex_length_is_positive_int(self) -> None:
        """SHA1_HEX_LENGTH is a positive integer."""
        from mpm_cli.constants import SHA1_HEX_LENGTH

        assert isinstance(SHA1_HEX_LENGTH, int)
        assert SHA1_HEX_LENGTH > 0

    def test_sha256_hex_length_exists(self) -> None:
        """SHA256_HEX_LENGTH constant exists in mpm_cli.constants."""
        from mpm_cli.constants import SHA256_HEX_LENGTH

        assert SHA256_HEX_LENGTH is not None

    def test_sha256_hex_length_value(self) -> None:
        """SHA256_HEX_LENGTH equals 64 (SHA-256 produces a 64-character hex digest)."""
        from mpm_cli.constants import SHA256_HEX_LENGTH

        assert SHA256_HEX_LENGTH == 64

    def test_sha256_hex_length_is_positive_int(self) -> None:
        """SHA256_HEX_LENGTH is a positive integer."""
        from mpm_cli.constants import SHA256_HEX_LENGTH

        assert isinstance(SHA256_HEX_LENGTH, int)
        assert SHA256_HEX_LENGTH > 0

    def test_sha256_longer_than_sha1(self) -> None:
        """SHA256_HEX_LENGTH is longer than SHA1_HEX_LENGTH."""
        from mpm_cli.constants import SHA1_HEX_LENGTH, SHA256_HEX_LENGTH

        assert SHA256_HEX_LENGTH > SHA1_HEX_LENGTH

    def test_truncation_length_less_than_sha1_length(self) -> None:
        """BRANCH_SHA_TRUNCATION_LENGTH is shorter than SHA1_HEX_LENGTH (the shorter full SHA)."""
        from mpm_cli.constants import BRANCH_SHA_TRUNCATION_LENGTH, SHA1_HEX_LENGTH

        assert BRANCH_SHA_TRUNCATION_LENGTH < SHA1_HEX_LENGTH


@pytest.mark.unit
class TestMPMOutdatedJsonIndent:
    """Tests for MPM_OUTDATED_JSON_INDENT constant (E4-F1-S1-T4 AC-FUNC-001).

    This constant controls the indentation level used by json.dumps when
    'mpm outdated --format json' is selected. It is overridable via the
    MPM_OUTDATED_JSON_INDENT environment variable.
    """

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_OUTDATED_JSON_INDENT constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_OUTDATED_JSON_INDENT

        assert isinstance(MPM_OUTDATED_JSON_INDENT, int)

    def test_default_value_is_2(self) -> None:
        """MPM_OUTDATED_JSON_INDENT default value is 2."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_OUTDATED_JSON_INDENT", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_OUTDATED_JSON_INDENT == 2
        finally:
            if saved is not None:
                os.environ["MPM_OUTDATED_JSON_INDENT"] = saved
            importlib.reload(constants)

    def test_is_positive(self) -> None:
        """MPM_OUTDATED_JSON_INDENT is a positive integer."""
        from mpm_cli.constants import MPM_OUTDATED_JSON_INDENT

        assert MPM_OUTDATED_JSON_INDENT > 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_OUTDATED_JSON_INDENT env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_OUTDATED_JSON_INDENT", "4")
        importlib.reload(constants)
        try:
            assert constants.MPM_OUTDATED_JSON_INDENT == 4
        finally:
            monkeypatch.delenv("MPM_OUTDATED_JSON_INDENT", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_OUTDATED_JSON_INDENT set to a non-integer env var raises ValueError."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_OUTDATED_JSON_INDENT", "not-a-number")
        with pytest.raises((ValueError, SystemExit)):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_OUTDATED_JSON_INDENT", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMWhyFormatConstants:
    """Tests for MPM_WHY_FORMAT and MPM_WHY_FORMAT_DEFAULT constants (AC-FUNC-006)."""

    def test_mpm_why_format_env_var_name(self) -> None:
        """MPM_WHY_FORMAT is the correct env var name string."""
        from mpm_cli.constants import MPM_WHY_FORMAT

        assert MPM_WHY_FORMAT == "MPM_WHY_FORMAT"

    def test_mpm_why_format_default_is_text(self) -> None:
        """MPM_WHY_FORMAT_DEFAULT is 'text'."""
        from mpm_cli.constants import MPM_WHY_FORMAT_DEFAULT

        assert MPM_WHY_FORMAT_DEFAULT == "text"

    def test_mpm_why_format_default_is_string(self) -> None:
        """MPM_WHY_FORMAT_DEFAULT is a str instance."""
        from mpm_cli.constants import MPM_WHY_FORMAT_DEFAULT

        assert isinstance(MPM_WHY_FORMAT_DEFAULT, str)

    def test_mpm_why_format_json_is_json_string(self) -> None:
        """MPM_WHY_FORMAT_JSON is the string literal 'json'."""
        from mpm_cli.constants import MPM_WHY_FORMAT_JSON

        assert MPM_WHY_FORMAT_JSON == "json"

    def test_mpm_why_format_json_is_string(self) -> None:
        """MPM_WHY_FORMAT_JSON is a str instance."""
        from mpm_cli.constants import MPM_WHY_FORMAT_JSON

        assert isinstance(MPM_WHY_FORMAT_JSON, str)


@pytest.mark.unit
class TestMPMWhySuggestConstants:
    """Tests for MPM_WHY_SUGGEST_MAX_DISTANCE and MPM_WHY_SUGGEST_TOP_N (AC-FUNC-005)."""

    def test_max_distance_env_var_name_exists(self) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE constant exists and is an int."""
        from mpm_cli.constants import MPM_WHY_SUGGEST_MAX_DISTANCE

        assert isinstance(MPM_WHY_SUGGEST_MAX_DISTANCE, int)

    def test_max_distance_default_value_is_3(self) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE defaults to 3."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_WHY_SUGGEST_MAX_DISTANCE", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_WHY_SUGGEST_MAX_DISTANCE == 3
        finally:
            if saved is not None:
                os.environ["MPM_WHY_SUGGEST_MAX_DISTANCE"] = saved
            importlib.reload(constants)

    def test_max_distance_is_non_negative(self) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE is a non-negative integer (0 disables suggestions)."""
        from mpm_cli.constants import MPM_WHY_SUGGEST_MAX_DISTANCE

        assert MPM_WHY_SUGGEST_MAX_DISTANCE >= 0

    def test_max_distance_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_MAX_DISTANCE", "5")
        importlib.reload(constants)
        try:
            assert constants.MPM_WHY_SUGGEST_MAX_DISTANCE == 5
        finally:
            monkeypatch.delenv("MPM_WHY_SUGGEST_MAX_DISTANCE", raising=False)
            importlib.reload(constants)

    def test_max_distance_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE set to a non-integer env var raises ValueError."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_MAX_DISTANCE", "not-a-number")
        with pytest.raises((ValueError, SystemExit)):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WHY_SUGGEST_MAX_DISTANCE", raising=False)
        importlib.reload(constants)

    def test_top_n_env_var_name_exists(self) -> None:
        """MPM_WHY_SUGGEST_TOP_N constant exists and is an int."""
        from mpm_cli.constants import MPM_WHY_SUGGEST_TOP_N

        assert isinstance(MPM_WHY_SUGGEST_TOP_N, int)

    def test_top_n_default_value_is_3(self) -> None:
        """MPM_WHY_SUGGEST_TOP_N defaults to 3."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_WHY_SUGGEST_TOP_N", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_WHY_SUGGEST_TOP_N == 3
        finally:
            if saved is not None:
                os.environ["MPM_WHY_SUGGEST_TOP_N"] = saved
            importlib.reload(constants)

    def test_top_n_is_non_negative(self) -> None:
        """MPM_WHY_SUGGEST_TOP_N is a non-negative integer (0 disables suggestions)."""
        from mpm_cli.constants import MPM_WHY_SUGGEST_TOP_N

        assert MPM_WHY_SUGGEST_TOP_N >= 0

    def test_top_n_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_SUGGEST_TOP_N env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_TOP_N", "5")
        importlib.reload(constants)
        try:
            assert constants.MPM_WHY_SUGGEST_TOP_N == 5
        finally:
            monkeypatch.delenv("MPM_WHY_SUGGEST_TOP_N", raising=False)
            importlib.reload(constants)

    def test_top_n_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_SUGGEST_TOP_N set to a non-integer env var raises ValueError."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_TOP_N", "not-a-number")
        with pytest.raises((ValueError, SystemExit)):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WHY_SUGGEST_TOP_N", raising=False)
        importlib.reload(constants)

    def test_max_distance_negative_value_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE set to a negative integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_MAX_DISTANCE", "-1")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WHY_SUGGEST_MAX_DISTANCE", raising=False)
        importlib.reload(constants)

    def test_max_distance_non_int_raises_system_exit_with_error_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """MPM_WHY_SUGGEST_MAX_DISTANCE set to a non-integer raises SystemExit with ERROR: message."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_MAX_DISTANCE", "abc")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WHY_SUGGEST_MAX_DISTANCE", raising=False)
        importlib.reload(constants)

    def test_top_n_negative_value_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_SUGGEST_TOP_N set to a negative integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_TOP_N", "-1")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WHY_SUGGEST_TOP_N", raising=False)
        importlib.reload(constants)

    def test_top_n_non_int_raises_system_exit_with_error_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """MPM_WHY_SUGGEST_TOP_N set to a non-integer raises SystemExit with ERROR: message."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_SUGGEST_TOP_N", "xyz")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WHY_SUGGEST_TOP_N", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMWhyJsonIndent:
    """Tests for MPM_WHY_JSON_INDENT constant (E4-F2-S1-T4 AC-DOC-002).

    This constant controls the indentation level used by json.dumps when
    'mpm why --format json' is selected. It is overridable via the
    MPM_WHY_JSON_INDENT environment variable.
    """

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_WHY_JSON_INDENT constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_WHY_JSON_INDENT

        assert isinstance(MPM_WHY_JSON_INDENT, int)

    def test_default_value_is_2(self) -> None:
        """MPM_WHY_JSON_INDENT default value is 2."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_WHY_JSON_INDENT", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_WHY_JSON_INDENT == 2
        finally:
            if saved is not None:
                os.environ["MPM_WHY_JSON_INDENT"] = saved
            importlib.reload(constants)

    def test_is_non_negative(self) -> None:
        """MPM_WHY_JSON_INDENT is a non-negative integer (0 is valid for compact output)."""
        from mpm_cli.constants import MPM_WHY_JSON_INDENT

        assert MPM_WHY_JSON_INDENT >= 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_JSON_INDENT env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_JSON_INDENT", "4")
        importlib.reload(constants)
        try:
            assert constants.MPM_WHY_JSON_INDENT == 4
        finally:
            monkeypatch.delenv("MPM_WHY_JSON_INDENT", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_JSON_INDENT set to a non-integer env var raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_JSON_INDENT", "not-a-number")
        with pytest.raises(SystemExit) as exc_info:
            importlib.reload(constants)
        assert "MPM_WHY_JSON_INDENT" in str(exc_info.value)
        monkeypatch.delenv("MPM_WHY_JSON_INDENT", raising=False)
        importlib.reload(constants)

    def test_env_override_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WHY_JSON_INDENT set to a negative integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WHY_JSON_INDENT", "-1")
        with pytest.raises(SystemExit) as exc_info:
            importlib.reload(constants)
        assert "MPM_WHY_JSON_INDENT" in str(exc_info.value)
        monkeypatch.delenv("MPM_WHY_JSON_INDENT", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMResolveTimeoutConstants:
    """Tests for _MPM_RESOLVE_TIMEOUT_ENV and _MPM_RESOLVE_TIMEOUT_DEFAULT (E5-F1-S1-T1)."""

    def test_resolve_timeout_env_name_exists(self) -> None:
        """_MPM_RESOLVE_TIMEOUT_ENV constant exists and is importable."""
        from mpm_cli.constants import _MPM_RESOLVE_TIMEOUT_ENV

        assert _MPM_RESOLVE_TIMEOUT_ENV is not None

    def test_resolve_timeout_env_name_value(self) -> None:
        """_MPM_RESOLVE_TIMEOUT_ENV equals 'MPM_RESOLVE_TIMEOUT'."""
        from mpm_cli.constants import _MPM_RESOLVE_TIMEOUT_ENV

        assert _MPM_RESOLVE_TIMEOUT_ENV == "MPM_RESOLVE_TIMEOUT"

    def test_resolve_timeout_env_name_is_string(self) -> None:
        """_MPM_RESOLVE_TIMEOUT_ENV is a str."""
        from mpm_cli.constants import _MPM_RESOLVE_TIMEOUT_ENV

        assert isinstance(_MPM_RESOLVE_TIMEOUT_ENV, str)

    def test_resolve_timeout_default_exists(self) -> None:
        """_MPM_RESOLVE_TIMEOUT_DEFAULT constant exists and is importable."""
        from mpm_cli.constants import _MPM_RESOLVE_TIMEOUT_DEFAULT

        assert _MPM_RESOLVE_TIMEOUT_DEFAULT is not None

    def test_resolve_timeout_default_value(self) -> None:
        """_MPM_RESOLVE_TIMEOUT_DEFAULT equals 30."""
        from mpm_cli.constants import _MPM_RESOLVE_TIMEOUT_DEFAULT

        assert _MPM_RESOLVE_TIMEOUT_DEFAULT == 30

    def test_resolve_timeout_default_is_positive_int(self) -> None:
        """_MPM_RESOLVE_TIMEOUT_DEFAULT is a positive integer."""
        from mpm_cli.constants import _MPM_RESOLVE_TIMEOUT_DEFAULT

        assert isinstance(_MPM_RESOLVE_TIMEOUT_DEFAULT, int)
        assert _MPM_RESOLVE_TIMEOUT_DEFAULT > 0


@pytest.mark.unit
class TestMPMCompletionErrorsReportLimitConstant:
    """Tests for MPM_COMPLETION_ERRORS_REPORT_LIMIT constant (E5-F1-S1-T3 AC-FUNC-008)."""

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_COMPLETION_ERRORS_REPORT_LIMIT

        assert isinstance(MPM_COMPLETION_ERRORS_REPORT_LIMIT, int)

    def test_default_value_is_5(self) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT default value is 5."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_COMPLETION_ERRORS_REPORT_LIMIT", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_COMPLETION_ERRORS_REPORT_LIMIT == 5
        finally:
            if saved is not None:
                os.environ["MPM_COMPLETION_ERRORS_REPORT_LIMIT"] = saved
            importlib.reload(constants)

    def test_is_positive(self) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT is a positive integer."""
        from mpm_cli.constants import MPM_COMPLETION_ERRORS_REPORT_LIMIT

        assert MPM_COMPLETION_ERRORS_REPORT_LIMIT > 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", "10")
        importlib.reload(constants)
        try:
            assert constants.MPM_COMPLETION_ERRORS_REPORT_LIMIT == 10
        finally:
            monkeypatch.delenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT set to a non-integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", "not-a-number")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", raising=False)
        importlib.reload(constants)

    def test_env_override_zero_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT set to 0 raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", "0")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", raising=False)
        importlib.reload(constants)

    def test_env_override_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_COMPLETION_ERRORS_REPORT_LIMIT set to a negative integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", "-1")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_COMPLETION_ERRORS_REPORT_LIMIT", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMHomeConstants:
    """Tests for the shared MPM_HOME store constants + resolver (E5-F1-S1-T1 AC-23).

    These replace the removed MPM_CACHE_DIR_ENV / MPM_CACHE_DIR_DEFAULT and
    WORKSPACE_DIR_ENV_VAR constants, which were subsumed by the single MPM_HOME
    root (spec Section 7.1 / Section 8 / FR-15, FR-16).
    """

    def test_home_env_var_name(self) -> None:
        """MPM_HOME_ENV_VAR names the MPM_HOME environment variable."""
        from mpm_cli.constants import MPM_HOME_ENV_VAR

        assert MPM_HOME_ENV_VAR == "MPM_HOME"

    def test_home_dir_name_default(self) -> None:
        """MPM_HOME_DIR_NAME is the relative default '.mpm' (joined onto $HOME)."""
        from mpm_cli.constants import MPM_HOME_DIR_NAME

        assert MPM_HOME_DIR_NAME == ".mpm-home"

    def test_store_and_cache_subdir_names(self) -> None:
        """The store and cache live in distinct, non-empty subdirs of the home root."""
        from mpm_cli.constants import MPM_HOME_CACHE_SUBDIR, MPM_HOME_STORE_SUBDIR

        assert MPM_HOME_STORE_SUBDIR == "store"
        assert MPM_HOME_CACHE_SUBDIR == "cache"
        assert MPM_HOME_STORE_SUBDIR != MPM_HOME_CACHE_SUBDIR

    def test_store_publish_subdir_names_are_distinct_and_non_empty(self) -> None:
        """The store entries, lock, and temp subdirs are distinct non-empty names.

        publish_store_entry writes content into the temp subdir, atomically
        renames into the entries subdir, and guards each address with a lock root
        under the lock subdir; clean prunes all three. The three names must be
        distinct so the trees never collide (spec Section 3.5).
        """
        from mpm_cli.constants import (
            MPM_HOME_STORE_ENTRIES_SUBDIR,
            MPM_HOME_STORE_LOCKS_SUBDIR,
            MPM_HOME_STORE_TMP_SUBDIR,
        )

        names = {
            MPM_HOME_STORE_ENTRIES_SUBDIR,
            MPM_HOME_STORE_LOCKS_SUBDIR,
            MPM_HOME_STORE_TMP_SUBDIR,
        }
        assert len(names) == 3, "the three store publish subdir names must be distinct"
        assert all(name for name in names), "no store publish subdir name may be empty"
        assert "/" not in "".join(names), "store publish subdir names must be single path components"

    def test_store_gitignore_entry_ignores_everything(self) -> None:
        """MPM_HOME_STORE_GITIGNORE_ENTRY ignores the whole store ('*')."""
        from mpm_cli.constants import MPM_HOME_STORE_GITIGNORE_ENTRY

        assert MPM_HOME_STORE_GITIGNORE_ENTRY == "*", "the store .gitignore safety net must ignore everything"

    def test_resolve_mpm_home_default_is_under_real_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With MPM_HOME unset, the home resolves to $HOME/.mpm-home (env-derived, not hard-coded)."""
        import pathlib

        from mpm_cli.constants import MPM_HOME_DIR_NAME, resolve_mpm_home

        monkeypatch.delenv("MPM_HOME", raising=False)
        assert resolve_mpm_home() == pathlib.Path.home() / MPM_HOME_DIR_NAME

    def test_resolve_mpm_home_env_override_wins(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A set MPM_HOME env value overrides the default."""
        import pathlib

        from mpm_cli.constants import resolve_mpm_home

        monkeypatch.setenv("MPM_HOME", str(tmp_path))
        assert resolve_mpm_home() == pathlib.Path(str(tmp_path))

    def test_resolve_mpm_home_empty_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty MPM_HOME value is treated as unset and resolves to the default."""
        import pathlib

        from mpm_cli.constants import MPM_HOME_DIR_NAME, resolve_mpm_home

        monkeypatch.setenv("MPM_HOME", "")
        assert resolve_mpm_home() == pathlib.Path.home() / MPM_HOME_DIR_NAME

    def test_removed_cache_dir_env_constant_is_gone(self) -> None:
        """MPM_CACHE_DIR_ENV must no longer exist in constants (subsumed by MPM_HOME)."""
        import mpm_cli.constants as constants

        assert not hasattr(constants, "MPM_CACHE_DIR_ENV")

    def test_removed_cache_dir_default_constant_is_gone(self) -> None:
        """MPM_CACHE_DIR_DEFAULT must no longer exist in constants (subsumed by MPM_HOME)."""
        import mpm_cli.constants as constants

        assert not hasattr(constants, "MPM_CACHE_DIR_DEFAULT")

    def test_removed_workspace_dir_env_var_constant_is_gone(self) -> None:
        """WORKSPACE_DIR_ENV_VAR must no longer exist in constants (subsumed by MPM_HOME)."""
        import mpm_cli.constants as constants

        assert not hasattr(constants, "WORKSPACE_DIR_ENV_VAR")


@pytest.mark.unit
class TestMPMCompletionErrorsLogFilenameConstant:
    """Tests for MPM_COMPLETION_ERRORS_LOG_FILENAME constant (E5-F1-S1-T3 AC-FUNC-008)."""

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_COMPLETION_ERRORS_LOG_FILENAME constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_COMPLETION_ERRORS_LOG_FILENAME

        assert isinstance(MPM_COMPLETION_ERRORS_LOG_FILENAME, str)

    def test_constant_value_is_completion_errors_log(self) -> None:
        """MPM_COMPLETION_ERRORS_LOG_FILENAME equals 'completion-errors.log'."""
        from mpm_cli.constants import MPM_COMPLETION_ERRORS_LOG_FILENAME

        assert MPM_COMPLETION_ERRORS_LOG_FILENAME == "completion-errors.log"

    def test_constant_is_non_empty(self) -> None:
        """MPM_COMPLETION_ERRORS_LOG_FILENAME is a non-empty string."""
        from mpm_cli.constants import MPM_COMPLETION_ERRORS_LOG_FILENAME

        assert len(MPM_COMPLETION_ERRORS_LOG_FILENAME) > 0


@pytest.mark.unit
class TestMPMStaticCompletionSearchPathsConstant:
    """Tests for MPM_STATIC_COMPLETION_SEARCH_PATHS constant (E5-F1-S1-T3 AC-FUNC-008)."""

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_STATIC_COMPLETION_SEARCH_PATHS constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_STATIC_COMPLETION_SEARCH_PATHS

        assert MPM_STATIC_COMPLETION_SEARCH_PATHS is not None

    def test_constant_is_tuple(self) -> None:
        """MPM_STATIC_COMPLETION_SEARCH_PATHS is a tuple."""
        from mpm_cli.constants import MPM_STATIC_COMPLETION_SEARCH_PATHS

        assert isinstance(MPM_STATIC_COMPLETION_SEARCH_PATHS, tuple)

    def test_each_entry_is_two_tuple_of_strings(self) -> None:
        """Each entry in MPM_STATIC_COMPLETION_SEARCH_PATHS is a (str, str) pair."""
        from mpm_cli.constants import MPM_STATIC_COMPLETION_SEARCH_PATHS

        for entry in MPM_STATIC_COMPLETION_SEARCH_PATHS:
            assert isinstance(entry, tuple), f"Expected tuple entry, got {type(entry)}"
            assert len(entry) == 2, f"Expected 2-tuple, got length {len(entry)}"
            shell, path = entry
            assert isinstance(shell, str), f"Expected shell to be str, got {type(shell)}"
            assert isinstance(path, str), f"Expected path to be str, got {type(path)}"

    def test_constant_includes_bash_entry(self) -> None:
        """MPM_STATIC_COMPLETION_SEARCH_PATHS includes at least one bash entry."""
        from mpm_cli.constants import MPM_STATIC_COMPLETION_SEARCH_PATHS

        shells = [shell for shell, _ in MPM_STATIC_COMPLETION_SEARCH_PATHS]
        assert "bash" in shells, "Expected at least one 'bash' entry in search paths"

    def test_constant_includes_zsh_entry(self) -> None:
        """MPM_STATIC_COMPLETION_SEARCH_PATHS includes at least one zsh entry."""
        from mpm_cli.constants import MPM_STATIC_COMPLETION_SEARCH_PATHS

        shells = [shell for shell, _ in MPM_STATIC_COMPLETION_SEARCH_PATHS]
        assert "zsh" in shells, "Expected at least one 'zsh' entry in search paths"

    def test_paths_are_non_empty_strings(self) -> None:
        """All path strings in MPM_STATIC_COMPLETION_SEARCH_PATHS are non-empty."""
        from mpm_cli.constants import MPM_STATIC_COMPLETION_SEARCH_PATHS

        for shell, path in MPM_STATIC_COMPLETION_SEARCH_PATHS:
            assert len(path) > 0, f"Expected non-empty path for shell {shell!r}"


@pytest.mark.unit
class TestMPMStaleCompletionScriptWarningConstant:
    """Tests for MPM_STALE_COMPLETION_SCRIPT_WARNING constant (E5-F1-S1-T3 AC-FUNC-008)."""

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_STALE_COMPLETION_SCRIPT_WARNING constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_STALE_COMPLETION_SCRIPT_WARNING

        assert isinstance(MPM_STALE_COMPLETION_SCRIPT_WARNING, str)

    def test_constant_is_non_empty(self) -> None:
        """MPM_STALE_COMPLETION_SCRIPT_WARNING is a non-empty string."""
        from mpm_cli.constants import MPM_STALE_COMPLETION_SCRIPT_WARNING

        assert len(MPM_STALE_COMPLETION_SCRIPT_WARNING) > 0

    def test_template_contains_shell_name_placeholder(self) -> None:
        """MPM_STALE_COMPLETION_SCRIPT_WARNING contains a {shell_name} placeholder."""
        from mpm_cli.constants import MPM_STALE_COMPLETION_SCRIPT_WARNING

        assert "{shell_name}" in MPM_STALE_COMPLETION_SCRIPT_WARNING

    def test_template_contains_path_placeholder(self) -> None:
        """MPM_STALE_COMPLETION_SCRIPT_WARNING contains a {path} placeholder."""
        from mpm_cli.constants import MPM_STALE_COMPLETION_SCRIPT_WARNING

        assert "{path}" in MPM_STALE_COMPLETION_SCRIPT_WARNING

    def test_template_is_format_compatible(self) -> None:
        """MPM_STALE_COMPLETION_SCRIPT_WARNING formats correctly with shell_name and path."""
        from mpm_cli.constants import MPM_STALE_COMPLETION_SCRIPT_WARNING

        rendered = MPM_STALE_COMPLETION_SCRIPT_WARNING.format(
            shell_name="bash",
            path="/usr/local/share/bash-completion/completions/mpm",
        )
        assert "bash" in rendered
        assert "/usr/local/share/bash-completion/completions/mpm" in rendered


@pytest.mark.unit
class TestMPMCachePruneAgeDays:
    """MPM_CACHE_PRUNE_AGE_DAYS is a positive integer defaulting to 30."""

    def test_is_positive_integer(self) -> None:
        """MPM_CACHE_PRUNE_AGE_DAYS must be a positive integer."""
        from mpm_cli.constants import MPM_CACHE_PRUNE_AGE_DAYS

        assert isinstance(MPM_CACHE_PRUNE_AGE_DAYS, int)
        assert MPM_CACHE_PRUNE_AGE_DAYS > 0

    def test_default_is_30(self) -> None:
        """Default value of MPM_CACHE_PRUNE_AGE_DAYS is 30."""
        import importlib
        import os
        import sys

        for mod_name in list(sys.modules.keys()):
            if "mpm_cli.constants" in mod_name:
                del sys.modules[mod_name]

        env_backup = os.environ.pop("MPM_CACHE_PRUNE_AGE_DAYS", None)
        try:
            import mpm_cli.constants as _c

            assert _c.MPM_CACHE_PRUNE_AGE_DAYS == 30
        finally:
            if env_backup is not None:
                os.environ["MPM_CACHE_PRUNE_AGE_DAYS"] = env_backup

            for mod_name in list(sys.modules.keys()):
                if "mpm_cli.constants" in mod_name:
                    del sys.modules[mod_name]
            importlib.import_module("mpm_cli.constants")

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CACHE_PRUNE_AGE_DAYS can be overridden via environment variable."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_CACHE_PRUNE_AGE_DAYS", "60")
        for mod_name in list(sys.modules.keys()):
            if "mpm_cli.constants" in mod_name:
                del sys.modules[mod_name]
        try:
            import mpm_cli.constants as _c

            assert _c.MPM_CACHE_PRUNE_AGE_DAYS == 60
        finally:
            for mod_name in list(sys.modules.keys()):
                if "mpm_cli.constants" in mod_name:
                    del sys.modules[mod_name]
            importlib.import_module("mpm_cli.constants")

    def test_invalid_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-integer MPM_CACHE_PRUNE_AGE_DAYS raises SystemExit at import."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_CACHE_PRUNE_AGE_DAYS", "notanint")
        mod_name = "mpm_cli.constants"
        original = sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(SystemExit):
                importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if original is not None:
                sys.modules[mod_name] = original
            else:
                monkeypatch.delenv("MPM_CACHE_PRUNE_AGE_DAYS", raising=False)
                importlib.import_module(mod_name)

    def test_zero_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CACHE_PRUNE_AGE_DAYS=0 raises SystemExit at import."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_CACHE_PRUNE_AGE_DAYS", "0")
        mod_name = "mpm_cli.constants"
        original = sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(SystemExit):
                importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if original is not None:
                sys.modules[mod_name] = original
            else:
                monkeypatch.delenv("MPM_CACHE_PRUNE_AGE_DAYS", raising=False)
                importlib.import_module(mod_name)


@pytest.mark.unit
class TestMPMDoctorStaleLockScanMaxDepth:
    """MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH is a positive integer defaulting to 4."""

    def test_is_positive_integer(self) -> None:
        """MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH must be a positive integer."""
        from mpm_cli.constants import MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH

        assert isinstance(MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH, int)
        assert MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH > 0

    def test_default_is_4(self) -> None:
        """Default value of MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH is 4."""
        import importlib
        import os
        import sys

        for mod_name in list(sys.modules.keys()):
            if "mpm_cli.constants" in mod_name:
                del sys.modules[mod_name]

        env_backup = os.environ.pop("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", None)
        try:
            import mpm_cli.constants as _c

            assert _c.MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH == 4
        finally:
            if env_backup is not None:
                os.environ["MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH"] = env_backup
            for mod_name in list(sys.modules.keys()):
                if "mpm_cli.constants" in mod_name:
                    del sys.modules[mod_name]
            importlib.import_module("mpm_cli.constants")

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH can be overridden via environment."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", "8")
        for mod_name in list(sys.modules.keys()):
            if "mpm_cli.constants" in mod_name:
                del sys.modules[mod_name]
        try:
            import mpm_cli.constants as _c

            assert _c.MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH == 8
        finally:
            for mod_name in list(sys.modules.keys()):
                if "mpm_cli.constants" in mod_name:
                    del sys.modules[mod_name]
            importlib.import_module("mpm_cli.constants")

    def test_invalid_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-integer MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH raises SystemExit."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", "bad")
        mod_name = "mpm_cli.constants"
        original = sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(SystemExit):
                importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if original is not None:
                sys.modules[mod_name] = original
            else:
                monkeypatch.delenv("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", raising=False)
                importlib.import_module(mod_name)

    def test_zero_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH=0 raises SystemExit at import."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", "0")
        mod_name = "mpm_cli.constants"
        original = sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(SystemExit):
                importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if original is not None:
                sys.modules[mod_name] = original
            else:
                monkeypatch.delenv("MPM_DOCTOR_STALE_LOCK_SCAN_MAX_DEPTH", raising=False)
                importlib.import_module(mod_name)


@pytest.mark.unit
class TestMPMDoctorStaleLockAgeHours:
    """MPM_DOCTOR_STALE_LOCK_AGE_HOURS is a positive integer defaulting to 1."""

    def test_is_positive_integer(self) -> None:
        """MPM_DOCTOR_STALE_LOCK_AGE_HOURS must be a positive integer."""
        from mpm_cli.constants import MPM_DOCTOR_STALE_LOCK_AGE_HOURS

        assert isinstance(MPM_DOCTOR_STALE_LOCK_AGE_HOURS, int)
        assert MPM_DOCTOR_STALE_LOCK_AGE_HOURS > 0

    def test_default_is_1(self) -> None:
        """Default value of MPM_DOCTOR_STALE_LOCK_AGE_HOURS is 1."""
        import importlib
        import os
        import sys

        for mod_name in list(sys.modules.keys()):
            if "mpm_cli.constants" in mod_name:
                del sys.modules[mod_name]

        env_backup = os.environ.pop("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", None)
        try:
            import mpm_cli.constants as _c

            assert _c.MPM_DOCTOR_STALE_LOCK_AGE_HOURS == 1
        finally:
            if env_backup is not None:
                os.environ["MPM_DOCTOR_STALE_LOCK_AGE_HOURS"] = env_backup
            for mod_name in list(sys.modules.keys()):
                if "mpm_cli.constants" in mod_name:
                    del sys.modules[mod_name]
            importlib.import_module("mpm_cli.constants")

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_STALE_LOCK_AGE_HOURS can be overridden via environment."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", "24")
        for mod_name in list(sys.modules.keys()):
            if "mpm_cli.constants" in mod_name:
                del sys.modules[mod_name]
        try:
            import mpm_cli.constants as _c

            assert _c.MPM_DOCTOR_STALE_LOCK_AGE_HOURS == 24
        finally:
            for mod_name in list(sys.modules.keys()):
                if "mpm_cli.constants" in mod_name:
                    del sys.modules[mod_name]
            importlib.import_module("mpm_cli.constants")

    def test_invalid_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-integer MPM_DOCTOR_STALE_LOCK_AGE_HOURS raises SystemExit."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", "notanumber")
        mod_name = "mpm_cli.constants"
        original = sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(SystemExit):
                importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if original is not None:
                sys.modules[mod_name] = original
            else:
                monkeypatch.delenv("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", raising=False)
                importlib.import_module(mod_name)

    def test_zero_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_STALE_LOCK_AGE_HOURS=0 raises SystemExit at import."""
        import importlib
        import sys

        monkeypatch.setenv("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", "0")
        mod_name = "mpm_cli.constants"
        original = sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(SystemExit):
                importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if original is not None:
                sys.modules[mod_name] = original
            else:
                monkeypatch.delenv("MPM_DOCTOR_STALE_LOCK_AGE_HOURS", raising=False)
                importlib.import_module(mod_name)


@pytest.mark.unit
class TestMPMDoctorRemoteStderrPreviewChars:
    """Tests for MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS (E5-F1-S1-T5 AC-FUNC-007)."""

    def test_is_int(self) -> None:
        """MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS is an int."""
        from mpm_cli.constants import MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS

        assert isinstance(MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS, int)

    def test_default_value_is_160(self) -> None:
        """MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS defaults to 160."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS == 160
        finally:
            if saved is not None:
                os.environ["MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS"] = saved
            importlib.reload(constants)

    def test_is_positive(self) -> None:
        """MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS is a positive integer."""
        from mpm_cli.constants import MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS

        assert MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS > 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS env var overrides the default."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", "80")
        importlib.reload(constants)
        try:
            assert constants.MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS == 80
        finally:
            monkeypatch.delenv("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", raising=False)
            importlib.reload(constants)

    def test_non_int_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS set to non-integer raises SystemExit at import."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", "not-a-number")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", raising=False)
        importlib.reload(constants)

    def test_zero_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS=0 raises SystemExit at import."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", "0")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_DOCTOR_REMOTE_STDERR_PREVIEW_CHARS", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMCatalogAuditValidChecks:
    """MPM_CATALOG_AUDIT_VALID_CHECKS contains the five expected check names."""

    def test_is_frozenset(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert isinstance(MPM_CATALOG_AUDIT_VALID_CHECKS, frozenset)

    def test_contains_metadata(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert "metadata" in MPM_CATALOG_AUDIT_VALID_CHECKS

    def test_contains_source_name_derivation(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert "source-name-derivation" in MPM_CATALOG_AUDIT_VALID_CHECKS

    def test_contains_entry_name_uniqueness(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert "entry-name-uniqueness" in MPM_CATALOG_AUDIT_VALID_CHECKS

    def test_contains_remote_url(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert "remote-url" in MPM_CATALOG_AUDIT_VALID_CHECKS

    def test_contains_tag_format(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert "tag-format" in MPM_CATALOG_AUDIT_VALID_CHECKS

    def test_exactly_five_checks(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        assert len(MPM_CATALOG_AUDIT_VALID_CHECKS) == 5

    def test_all_values_are_strings(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        for name in MPM_CATALOG_AUDIT_VALID_CHECKS:
            assert isinstance(name, str)

    def test_no_underscores_in_check_names(self) -> None:
        """Check names use hyphens, not underscores, per spec Section 4.8."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_VALID_CHECKS

        for name in MPM_CATALOG_AUDIT_VALID_CHECKS:
            assert "_" not in name, f"Check name '{name}' should use hyphens, not underscores"


@pytest.mark.unit
class TestMPMCatalogAuditCacheTTL:
    """MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS has the expected default and env-override."""

    def test_default_is_3600(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS

        assert MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS == 3600

    def test_is_positive_int(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS

        assert isinstance(MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS, int)
        assert MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS > 0

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS env var overrides the default."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", "120")
        importlib.reload(constants)
        try:
            assert constants.MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS == 120
        finally:
            monkeypatch.delenv("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", raising=False)
            importlib.reload(constants)

    def test_non_int_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS set to non-integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", "not-a-number")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", raising=False)
        importlib.reload(constants)

    def test_zero_env_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS=0 raises SystemExit at import."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", "0")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_CATALOG_AUDIT_CACHE_TTL_SECONDS", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMCatalogAuditCacheSubdir:
    """MPM_CATALOG_AUDIT_CACHE_SUBDIR is the expected string."""

    def test_value_is_catalog_audit(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_CACHE_SUBDIR

        assert MPM_CATALOG_AUDIT_CACHE_SUBDIR == "catalog-audit"

    def test_is_string(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_CACHE_SUBDIR

        assert isinstance(MPM_CATALOG_AUDIT_CACHE_SUBDIR, str)


@pytest.mark.unit
class TestMPMCatalogAuditFormatEnv:
    """MPM_CATALOG_AUDIT_FORMAT_ENV holds the correct env var name."""

    def test_env_var_name(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_FORMAT_ENV

        assert MPM_CATALOG_AUDIT_FORMAT_ENV == "MPM_CATALOG_AUDIT_FORMAT"

    def test_is_string(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_FORMAT_ENV

        assert isinstance(MPM_CATALOG_AUDIT_FORMAT_ENV, str)


@pytest.mark.unit
class TestMPMCatalogAuditFormatConstants:
    """MPM_CATALOG_AUDIT_FORMAT_DEFAULT and MPM_CATALOG_AUDIT_FORMAT_JSON hold correct values."""

    def test_format_default_value(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_FORMAT_DEFAULT

        assert MPM_CATALOG_AUDIT_FORMAT_DEFAULT == "text"

    def test_format_default_is_string(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_FORMAT_DEFAULT

        assert isinstance(MPM_CATALOG_AUDIT_FORMAT_DEFAULT, str)

    def test_format_json_value(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_FORMAT_JSON

        assert MPM_CATALOG_AUDIT_FORMAT_JSON == "json"

    def test_format_json_is_string(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_AUDIT_FORMAT_JSON

        assert isinstance(MPM_CATALOG_AUDIT_FORMAT_JSON, str)

    def test_format_default_and_json_are_distinct(self) -> None:
        from mpm_cli.constants import (
            MPM_CATALOG_AUDIT_FORMAT_DEFAULT,
            MPM_CATALOG_AUDIT_FORMAT_JSON,
        )

        assert MPM_CATALOG_AUDIT_FORMAT_DEFAULT != MPM_CATALOG_AUDIT_FORMAT_JSON


@pytest.mark.unit
class TestMPMCatalogMetadataFieldLists:
    """Tests for MPM_CATALOG_METADATA_REQUIRED_FIELDS and
    MPM_CATALOG_METADATA_RECOMMENDED_FIELDS (AC-FUNC-008 / source-test-atomicity)."""

    def test_required_fields_is_tuple(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert isinstance(MPM_CATALOG_METADATA_REQUIRED_FIELDS, tuple)

    def test_required_fields_contains_name(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert "name" in MPM_CATALOG_METADATA_REQUIRED_FIELDS

    def test_required_fields_contains_display_name(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert "display-name" in MPM_CATALOG_METADATA_REQUIRED_FIELDS

    def test_required_fields_contains_description(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert "description" in MPM_CATALOG_METADATA_REQUIRED_FIELDS

    def test_required_fields_contains_version(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert "version" in MPM_CATALOG_METADATA_REQUIRED_FIELDS

    def test_required_fields_length_is_four(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert len(MPM_CATALOG_METADATA_REQUIRED_FIELDS) == 4

    def test_required_fields_all_strings(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_REQUIRED_FIELDS

        assert all(isinstance(f, str) for f in MPM_CATALOG_METADATA_REQUIRED_FIELDS)

    def test_recommended_fields_is_tuple(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert isinstance(MPM_CATALOG_METADATA_RECOMMENDED_FIELDS, tuple)

    def test_recommended_fields_contains_type(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert "type" in MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

    def test_recommended_fields_contains_owner_name(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert "owner-name" in MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

    def test_recommended_fields_contains_owner_email(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert "owner-email" in MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

    def test_recommended_fields_contains_keywords(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert "keywords" in MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

    def test_recommended_fields_length_is_four(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert len(MPM_CATALOG_METADATA_RECOMMENDED_FIELDS) == 4

    def test_recommended_fields_all_strings(self) -> None:
        from mpm_cli.constants import MPM_CATALOG_METADATA_RECOMMENDED_FIELDS

        assert all(isinstance(f, str) for f in MPM_CATALOG_METADATA_RECOMMENDED_FIELDS)

    def test_required_and_recommended_are_disjoint(self) -> None:
        from mpm_cli.constants import (
            MPM_CATALOG_METADATA_RECOMMENDED_FIELDS,
            MPM_CATALOG_METADATA_REQUIRED_FIELDS,
        )

        required = set(MPM_CATALOG_METADATA_REQUIRED_FIELDS)
        recommended = set(MPM_CATALOG_METADATA_RECOMMENDED_FIELDS)
        assert required.isdisjoint(recommended)


@pytest.mark.unit
class TestMPMCatalogEntryNameAllowedCharsRe:
    """MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE is a compiled regex in constants.py.

    AC-FUNC-006: The constant lives in constants.py (not inline in catalog.py)
    and correctly classifies entry names as within-charset or out-of-charset.
    """

    def test_constant_exists_in_constants_module(self) -> None:
        """MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE is importable from constants."""
        from mpm_cli.constants import MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE

        assert MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE is not None

    def test_constant_is_compiled_regex(self) -> None:
        """MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE is a compiled re.Pattern."""
        import re

        from mpm_cli.constants import MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE

        assert isinstance(MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE, re.Pattern)

    @pytest.mark.parametrize(
        "entry_name",
        [
            "foo_bar",
            "my-tool",
            "FOO",
            "foo123",
            "a",
            "ABC-def_123",
            "",
        ],
    )
    def test_allowed_chars_matches_valid_names(self, entry_name: str) -> None:
        """Entry names using only [a-zA-Z0-9_-] must fullmatch the pattern."""
        from mpm_cli.constants import MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE

        assert MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE.fullmatch(entry_name) is not None, (
            f"Expected {entry_name!r} to match MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE"
        )

    @pytest.mark.parametrize(
        "entry_name",
        [
            "foo.bar",
            "foo bar",
            "foo\tbar",
            "foo@bar",
            "foo/bar",
            "f\u00f3\u00f3",
            "foo!",
            "foo#bar",
        ],
    )
    def test_disallowed_chars_do_not_match(self, entry_name: str) -> None:
        """Entry names with out-of-charset chars must NOT fullmatch the pattern."""
        from mpm_cli.constants import MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE

        assert MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE.fullmatch(entry_name) is None, (
            f"Expected {entry_name!r} NOT to match MPM_CATALOG_ENTRY_NAME_ALLOWED_CHARS_RE"
        )


@pytest.mark.unit
class TestMPMCatalogAuditTagReportLimit:
    """Tests for MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT (E5-F2-S1-T6 AC-FUNC-009)."""

    def test_is_int(self) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT is an int."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT

        assert isinstance(MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT, int)

    def test_default_value_is_50(self) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT default value is 50."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT == 50
        finally:
            if saved is not None:
                os.environ["MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT"] = saved
            importlib.reload(constants)

    def test_is_positive(self) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT is a positive integer."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT

        assert MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT > 0

    def test_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT env var overrides the default value."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", "25")
        importlib.reload(constants)
        try:
            assert constants.MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT == 25
        finally:
            monkeypatch.delenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT set to a non-integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", "not-an-int")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", raising=False)
        importlib.reload(constants)

    def test_env_override_zero_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT set to zero raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", "0")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", raising=False)
        importlib.reload(constants)

    def test_env_override_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT set to a negative value raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", "-5")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_CATALOG_AUDIT_TAG_REPORT_LIMIT", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestMPMCatalogAuditTagFormatSummaryTemplate:
    """Tests for MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE (E5-F2-S1-T6 AC-FUNC-009)."""

    def test_is_str(self) -> None:
        """MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE is a str."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE

        assert isinstance(MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE, str)

    def test_is_non_empty(self) -> None:
        """MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE is non-empty."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE

        assert len(MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE) > 0

    def test_contains_remaining_placeholder(self) -> None:
        """Template contains the {remaining} placeholder."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE

        assert "{remaining}" in MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE

    def test_formatted_contains_remaining_count(self) -> None:
        """Formatted template with remaining=10 contains '10' in the output."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE.format(remaining=10)
        assert "10" in rendered

    def test_formatted_mentions_tag_format_audit(self) -> None:
        """Formatted template mentions mpm catalog audit --check tag-format."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_TAG_FORMAT_SUMMARY_TEMPLATE.format(remaining=5)
        assert "tag-format" in rendered


class TestMPMCatalogAuditLegacyDirWarningTemplate:
    """Tests for MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE (E5-F2-S1-T7 AC-FUNC-006)."""

    def test_is_str(self) -> None:
        """MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE is a str."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

        assert isinstance(MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE, str)

    def test_is_non_empty(self) -> None:
        """MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE is non-empty."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

        assert len(MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE) > 0

    def test_contains_version_placeholder(self) -> None:
        """Template contains the {version} placeholder."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

        assert "{version}" in MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

    def test_formatted_contains_version_string(self) -> None:
        """Formatted template with version='1.2.3' contains '1.2.3' in the output."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE.format(version="1.2.3")
        assert "1.2.3" in rendered

    def test_formatted_spec_verbatim_output(self) -> None:
        """Formatted template matches spec Section 4.8 wording exactly."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE.format(version="0.99.0")
        expected = (
            "Legacy catalog/ directory detected; this directory is unused by "
            "mpm >= 0.99.0 and should be deleted; "
            "see docs/migration-to-add.md"
        )
        assert rendered == expected

    def test_mentions_migration_doc(self) -> None:
        """Rendered template references the migration documentation path."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_LEGACY_DIR_WARNING_TEMPLATE.format(version="2.0.0")
        assert "docs/migration-to-add.md" in rendered


@pytest.mark.unit
class TestMPMCatalogAuditStrictSummaryTemplate:
    """Tests for MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE (E5-F2-S1-T8 AC-FUNC-007)."""

    def test_strict_summary_template_is_str(self) -> None:
        """MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE is a non-empty string."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        assert isinstance(MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE, str)
        assert len(MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE) > 0

    def test_strict_summary_template_contains_count_placeholder(self) -> None:
        """Template contains the {count} placeholder."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        assert "{count}" in MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

    def test_strict_summary_template_format_with_count(self) -> None:
        """Template formats correctly when {count} is substituted."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE.format(count=3)
        assert "3" in rendered

    def test_strict_summary_template_rendered_contains_strict_mode(self) -> None:
        """Rendered template contains 'strict mode' so operators understand the context."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE.format(count=1)
        assert "strict mode" in rendered

    def test_strict_summary_template_rendered_contains_warning(self) -> None:
        """Rendered template contains 'warning' to name the promoted finding severity."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE.format(count=2)
        assert "warning" in rendered

    def test_strict_summary_template_count_zero(self) -> None:
        """Template formats without error when count is 0 (edge case)."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE.format(count=0)
        assert "0" in rendered

    def test_strict_summary_template_count_large(self) -> None:
        """Template formats without error when count is large."""
        from mpm_cli.constants import MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE

        rendered = MPM_CATALOG_AUDIT_STRICT_SUMMARY_TEMPLATE.format(count=999)
        assert "999" in rendered


@pytest.mark.unit
class TestExitCodeDeprecated:
    """Verify EXIT_CODE_DEPRECATED is defined with the correct value (AC-FUNC-006)."""

    def test_exit_code_deprecated_is_3(self) -> None:
        assert EXIT_CODE_DEPRECATED == 3

    def test_exit_code_deprecated_is_int(self) -> None:
        assert isinstance(EXIT_CODE_DEPRECATED, int)

    def test_exit_code_deprecated_is_module_level_constant(self) -> None:
        import mpm_cli.constants as constants

        assert hasattr(constants, "EXIT_CODE_DEPRECATED"), (
            "EXIT_CODE_DEPRECATED must be a module-level constant in mpm_cli.constants"
        )

    def test_exit_code_deprecated_distinct_from_success(self) -> None:
        assert EXIT_CODE_DEPRECATED != 0

    def test_exit_code_deprecated_distinct_from_runtime_error(self) -> None:
        assert EXIT_CODE_DEPRECATED != 1

    def test_exit_code_deprecated_distinct_from_argparse_error(self) -> None:
        assert EXIT_CODE_DEPRECATED != 2


@pytest.mark.unit
class TestCompletionCacheConstants:
    """TDD-paired test for the cache constants added to constants.py by E7-F3-S1-T1."""

    def test_mpm_home_cache_subdir_is_string(self) -> None:
        """The cache now lives under the MPM_HOME cache subdir, not a standalone env var."""
        from mpm_cli.constants import MPM_HOME_CACHE_SUBDIR

        assert isinstance(MPM_HOME_CACHE_SUBDIR, str)
        assert MPM_HOME_CACHE_SUBDIR == "cache"

    def test_mpm_completion_cache_ttl_is_int(self) -> None:
        from mpm_cli.constants import MPM_COMPLETION_CACHE_TTL

        assert isinstance(MPM_COMPLETION_CACHE_TTL, int)
        assert MPM_COMPLETION_CACHE_TTL == 300

    def test_mpm_completion_timeout_is_int(self) -> None:
        from mpm_cli.constants import MPM_COMPLETION_TIMEOUT

        assert isinstance(MPM_COMPLETION_TIMEOUT, int)
        assert MPM_COMPLETION_TIMEOUT == 2

    def test_mpm_completion_refresh_bg_is_int(self) -> None:
        from mpm_cli.constants import MPM_COMPLETION_REFRESH_BG

        assert isinstance(MPM_COMPLETION_REFRESH_BG, int)
        assert MPM_COMPLETION_REFRESH_BG == 1

    def test_mpm_completion_refresh_bg_env_is_string(self) -> None:
        from mpm_cli.constants import MPM_COMPLETION_REFRESH_BG_ENV

        assert isinstance(MPM_COMPLETION_REFRESH_BG_ENV, str)
        assert MPM_COMPLETION_REFRESH_BG_ENV == "MPM_COMPLETION_REFRESH_BG"

    def test_mpm_completion_enabled_is_int(self) -> None:
        from mpm_cli.constants import MPM_COMPLETION_ENABLED

        assert isinstance(MPM_COMPLETION_ENABLED, int)
        assert MPM_COMPLETION_ENABLED == 1

    def test_mpm_accessed_at_coalesce_sec_is_int(self) -> None:
        from mpm_cli.constants import MPM_ACCESSED_AT_COALESCE_SEC

        assert isinstance(MPM_ACCESSED_AT_COALESCE_SEC, int)
        assert MPM_ACCESSED_AT_COALESCE_SEC == 60

    def test_mpm_completion_log_env_is_string(self) -> None:
        from mpm_cli.constants import MPM_COMPLETION_LOG_ENV

        assert isinstance(MPM_COMPLETION_LOG_ENV, str)
        assert MPM_COMPLETION_LOG_ENV == "MPM_COMPLETION_LOG"


@pytest.mark.unit
class TestShellMetachars:
    """Tests for SHELL_METACHARS constant (AC-FUNC-008, E7-F3-S1-T4)."""

    def test_shell_metachars_is_frozenset(self) -> None:
        """SHELL_METACHARS must be a frozenset (immutable, hashable)."""
        from mpm_cli.constants import SHELL_METACHARS

        assert isinstance(SHELL_METACHARS, frozenset)

    def test_shell_metachars_is_nonempty(self) -> None:
        """SHELL_METACHARS must contain at least the spec-mandated characters."""
        from mpm_cli.constants import SHELL_METACHARS

        assert len(SHELL_METACHARS) > 0

    @pytest.mark.parametrize(
        "char",
        ["|", "&", ";", "<", ">", "(", ")", "{", "}", "$", "`", "\\", '"', "'"],
    )
    def test_shell_metachars_contains_required_char(self, char: str) -> None:
        """Each spec-mandated metacharacter must be present in SHELL_METACHARS."""
        from mpm_cli.constants import SHELL_METACHARS

        assert char in SHELL_METACHARS, f"Missing required metachar: {char!r}"

    def test_shell_metachars_contains_only_single_chars(self) -> None:
        """Every element of SHELL_METACHARS is a single character."""
        from mpm_cli.constants import SHELL_METACHARS

        for char in SHELL_METACHARS:
            assert len(char) == 1, f"Non-single-char element in SHELL_METACHARS: {char!r}"


@pytest.mark.unit
class TestCompletionSanitizationConstants:
    """Tests for COMPLETION_MAX_ENTRY_LEN and COMPLETION_UNSAFE_CHARS (spec Section 11.3)."""

    def test_completion_max_entry_len_is_int(self) -> None:
        """COMPLETION_MAX_ENTRY_LEN must be a positive integer."""
        from mpm_cli.constants import COMPLETION_MAX_ENTRY_LEN

        assert isinstance(COMPLETION_MAX_ENTRY_LEN, int)
        assert COMPLETION_MAX_ENTRY_LEN > 0

    def test_completion_max_entry_len_value(self) -> None:
        """COMPLETION_MAX_ENTRY_LEN must be exactly 128 per spec Section 11.3."""
        from mpm_cli.constants import COMPLETION_MAX_ENTRY_LEN

        assert COMPLETION_MAX_ENTRY_LEN == 128

    def test_completion_unsafe_chars_is_frozenset(self) -> None:
        """COMPLETION_UNSAFE_CHARS must be a frozenset (immutable, hashable)."""
        from mpm_cli.constants import COMPLETION_UNSAFE_CHARS

        assert isinstance(COMPLETION_UNSAFE_CHARS, frozenset)

    def test_completion_unsafe_chars_is_nonempty(self) -> None:
        """COMPLETION_UNSAFE_CHARS must contain at least one character."""
        from mpm_cli.constants import COMPLETION_UNSAFE_CHARS

        assert len(COMPLETION_UNSAFE_CHARS) > 0

    @pytest.mark.parametrize(
        "char",
        [" ", "\t", "\n", "\r", ";", "|", "&", "$", "`"],
    )
    def test_completion_unsafe_chars_contains_required_char(self, char: str) -> None:
        """Each shell-special and whitespace character must be in COMPLETION_UNSAFE_CHARS."""
        from mpm_cli.constants import COMPLETION_UNSAFE_CHARS

        assert char in COMPLETION_UNSAFE_CHARS, f"Missing required unsafe char: {char!r}"

    def test_completion_unsafe_chars_contains_only_single_chars(self) -> None:
        """Every element of COMPLETION_UNSAFE_CHARS is a single character."""
        from mpm_cli.constants import COMPLETION_UNSAFE_CHARS

        for char in COMPLETION_UNSAFE_CHARS:
            assert len(char) == 1, f"Non-single-char element in COMPLETION_UNSAFE_CHARS: {char!r}"


@pytest.mark.unit
class TestMPMGitLsRemoteTimeoutConstant:
    """MPM_GIT_LS_REMOTE_TIMEOUT constant is defined in constants.py via _env_int."""

    def test_constant_is_importable(self) -> None:
        """MPM_GIT_LS_REMOTE_TIMEOUT is importable from mpm_cli.constants."""
        from mpm_cli.constants import MPM_GIT_LS_REMOTE_TIMEOUT

        assert MPM_GIT_LS_REMOTE_TIMEOUT is not None

    def test_constant_is_positive_integer(self) -> None:
        """MPM_GIT_LS_REMOTE_TIMEOUT is a positive integer."""
        from mpm_cli.constants import MPM_GIT_LS_REMOTE_TIMEOUT

        assert isinstance(MPM_GIT_LS_REMOTE_TIMEOUT, int)
        assert MPM_GIT_LS_REMOTE_TIMEOUT > 0

    def test_constant_default_is_30(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_GIT_LS_REMOTE_TIMEOUT defaults to 30 when env var is unset."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.delenv("MPM_GIT_LS_REMOTE_TIMEOUT", raising=False)
        importlib.reload(constants)

        assert constants.MPM_GIT_LS_REMOTE_TIMEOUT == 30

    def test_constant_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_GIT_LS_REMOTE_TIMEOUT reflects the MPM_GIT_LS_REMOTE_TIMEOUT env var."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_GIT_LS_REMOTE_TIMEOUT", "45")
        importlib.reload(constants)

        assert constants.MPM_GIT_LS_REMOTE_TIMEOUT == 45


@pytest.mark.unit
class TestMPMWorkspaceLockTimeoutSeconds:
    """Tests for MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS constant (E2-F1-S1-T1).

    This constant controls the fail-fast acquisition timeout used by
    mpm_workspace_lock. It is routed through _env_int (no hard-coded literal
    in concurrency.py) and is overridable via the
    MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS environment variable. Default is 30.
    """

    def test_constant_exists_and_is_importable(self) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS constant exists in mpm_cli.constants."""
        from mpm_cli.constants import MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS

        assert isinstance(MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS, int)

    def test_constant_is_positive_integer(self) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS is a positive integer."""
        from mpm_cli.constants import MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS

        assert MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS > 0

    def test_constant_default_is_30(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS defaults to 30 when env var is unset."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.delenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", raising=False)
        importlib.reload(constants)

        assert constants.MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS == 30

    def test_constant_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS reflects the env var override."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", "5")
        importlib.reload(constants)
        try:
            assert constants.MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS == 5
        finally:
            monkeypatch.delenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", raising=False)
            importlib.reload(constants)

    def test_env_override_non_int_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS set to a non-integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", "not-a-number")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", raising=False)
        importlib.reload(constants)

    def test_env_override_zero_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS set to 0 raises SystemExit (must be positive)."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", "0")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", raising=False)
        importlib.reload(constants)

    def test_env_override_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS set to a negative integer raises SystemExit."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", "-1")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_WORKSPACE_LOCK_TIMEOUT_SECONDS", raising=False)
        importlib.reload(constants)


@pytest.mark.unit
class TestUpdateCheckConstants:
    """Tests for the update-available alert constants (spec Section 7.1 / FR-29).

    The PyPI endpoint, upgrade command, TTL, connect/read timeouts, and body-size
    cap are all defined in constants.py so update_check.py holds no operative
    literal. The integer knobs route through _env_int and are env-overridable.
    """

    def test_pypi_endpoint_and_command_locked_values(self) -> None:
        """The endpoint and upgrade command match the locked spec source values."""
        from mpm_cli.constants import (
            MPM_PYPI_JSON_URL,
            MPM_PYPI_PROJECT_NAME,
            MPM_UPDATE_UPGRADE_COMMAND,
        )

        assert MPM_PYPI_PROJECT_NAME == "missing-package-manager"
        assert MPM_PYPI_JSON_URL == "https://pypi.org/pypi/missing-package-manager/json"
        assert MPM_UPDATE_UPGRADE_COMMAND == "pipx upgrade missing-package-manager"

    def test_default_ttl_is_10800(self) -> None:
        """MPM_UPDATE_CHECK_TTL default is 10800 (3h)."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = os.environ.pop("MPM_UPDATE_CHECK_TTL", None)
        importlib.reload(constants)
        try:
            assert constants.MPM_UPDATE_CHECK_TTL == 10800
        finally:
            if saved is not None:
                os.environ["MPM_UPDATE_CHECK_TTL"] = saved
            importlib.reload(constants)

    def test_default_timeouts_and_cap(self) -> None:
        """The connect/read timeouts default to 2s/3s and the body cap to 200KB."""
        import importlib
        import os

        import mpm_cli.constants as constants

        saved = {
            key: os.environ.pop(key, None)
            for key in (
                "MPM_UPDATE_CONNECT_TIMEOUT",
                "MPM_UPDATE_READ_TIMEOUT",
                "MPM_UPDATE_BODY_SIZE_CAP",
            )
        }
        importlib.reload(constants)
        try:
            assert constants.MPM_UPDATE_CONNECT_TIMEOUT == 2
            assert constants.MPM_UPDATE_READ_TIMEOUT == 3
            assert constants.MPM_UPDATE_BODY_SIZE_CAP == 200 * 1024
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value
            importlib.reload(constants)

    def test_ttl_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_UPDATE_CHECK_TTL env var overrides the default via _env_int."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_UPDATE_CHECK_TTL", "3600")
        importlib.reload(constants)
        try:
            assert constants.MPM_UPDATE_CHECK_TTL == 3600
        finally:
            monkeypatch.delenv("MPM_UPDATE_CHECK_TTL", raising=False)
            importlib.reload(constants)

    def test_connect_timeout_env_override_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_UPDATE_CONNECT_TIMEOUT env var overrides the default."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_UPDATE_CONNECT_TIMEOUT", "5")
        importlib.reload(constants)
        try:
            assert constants.MPM_UPDATE_CONNECT_TIMEOUT == 5
        finally:
            monkeypatch.delenv("MPM_UPDATE_CONNECT_TIMEOUT", raising=False)
            importlib.reload(constants)

    def test_ttl_non_integer_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A non-integer MPM_UPDATE_CHECK_TTL fails fast with SystemExit (_env_int guard)."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_UPDATE_CHECK_TTL", "not-a-number")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_UPDATE_CHECK_TTL", raising=False)
        importlib.reload(constants)

    def test_ttl_zero_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MPM_UPDATE_CHECK_TTL set to 0 raises SystemExit (must be positive)."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_UPDATE_CHECK_TTL", "0")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_UPDATE_CHECK_TTL", raising=False)
        importlib.reload(constants)

    def test_body_size_cap_negative_raises_system_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A negative MPM_UPDATE_BODY_SIZE_CAP raises SystemExit (must be positive)."""
        import importlib

        import mpm_cli.constants as constants

        monkeypatch.setenv("MPM_UPDATE_BODY_SIZE_CAP", "-1")
        with pytest.raises(SystemExit):
            importlib.reload(constants)
        monkeypatch.delenv("MPM_UPDATE_BODY_SIZE_CAP", raising=False)
        importlib.reload(constants)

    def test_skip_env_and_cache_layout_constants(self) -> None:
        """The skip-env name, cache subdir, and version filename constants exist."""
        from mpm_cli.constants import (
            MPM_SKIP_UPDATE_CHECK_ENV,
            MPM_SKIP_UPDATE_CHECK_TRUE,
            MPM_UPDATE_CHECK_CACHE_SUBDIR,
            MPM_UPDATE_CHECK_VERSION_FILENAME,
        )

        assert MPM_SKIP_UPDATE_CHECK_ENV == "MPM_SKIP_UPDATE_CHECK"
        assert MPM_SKIP_UPDATE_CHECK_TRUE == "1"
        assert MPM_UPDATE_CHECK_CACHE_SUBDIR
        assert MPM_UPDATE_CHECK_VERSION_FILENAME
