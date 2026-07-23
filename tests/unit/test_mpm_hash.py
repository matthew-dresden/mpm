"""Tests for the mpm_hash deterministic SHA-256 function.

Covers every property defined in AC-FUNC-002 through AC-FUNC-012 and the
end-to-end cycle required by AC-CYCLE-001.
"""

import hashlib
import pathlib

import pytest

from mpm_cli.core.mpm_hash import MPMHashError, mpm_hash


_VALID_URL = "https://example.com/repo.git"
_VALID_REVISION = "main"
_VALID_PATH = "repo-specs/my-svc/meta.xml"

_VALID_URL_B = "https://example.com/other.git"
_VALID_REVISION_B = "v1.2.3"
_VALID_PATH_B = "repo-specs/other/meta.xml"


def _write_mpm(
    tmp_path: pathlib.Path,
    sources: list[tuple[str, str, str, str]],
    *,
    prefix_lines: list[str] | None = None,
    suffix_lines: list[str] | None = None,
    filename: str = ".mpm",
) -> pathlib.Path:
    """Write a minimal .mpm file and return its path.

    Args:
        tmp_path: Base directory for the file.
        sources: List of (name, url, revision, path) tuples.
        prefix_lines: Lines to prepend before source declarations.
        suffix_lines: Lines to append after source declarations.
        filename: File name (default ``.mpm``).

    Returns:
        Path to the written .mpm file.
    """
    lines: list[str] = []
    if prefix_lines:
        lines.extend(prefix_lines)
    for name, url, revision, path in sources:
        lines.append(f"MPM_SOURCE_{name}_URL={url}")
        lines.append(f"MPM_SOURCE_{name}_REF={revision}")
        lines.append(f"MPM_SOURCE_{name}_PATH={path}")
        lines.append(f"MPM_SOURCE_{name}_NAME={name}")
        lines.append(f"MPM_SOURCE_{name}_GITBASE={url}")
    if suffix_lines:
        lines.extend(suffix_lines)
    mpm_file = tmp_path / filename
    mpm_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mpm_file


def _expected_hash(sources: list[tuple[str, str, str, str]]) -> str:
    """Compute the expected sha256 hash for a sorted list of (name,url,rev,path)."""
    sorted_sources = sorted(sources, key=lambda s: s[0])
    digest = hashlib.sha256()
    for name, url, revision, path in sorted_sources:
        digest.update(f"{name}\t{url}\t{revision}\t{path}\n".encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


@pytest.mark.unit
class TestMPMHashReturnShape:
    """mpm_hash returns a string of shape sha256:<64 lowercase hex chars>."""

    def test_shape_single_source(self, tmp_path: pathlib.Path) -> None:
        mpm_file = _write_mpm(
            tmp_path,
            [("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH)],
        )
        result = mpm_hash(mpm_file)
        assert result.startswith("sha256:")
        hex_part = result[len("sha256:") :]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_shape_multiple_sources(self, tmp_path: pathlib.Path) -> None:
        mpm_file = _write_mpm(
            tmp_path,
            [
                ("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH),
                ("beta", _VALID_URL_B, _VALID_REVISION_B, _VALID_PATH_B),
            ],
        )
        result = mpm_hash(mpm_file)
        assert result.startswith("sha256:")
        hex_part = result[len("sha256:") :]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)


@pytest.mark.unit
class TestMPMHashSourceOrdering:
    """Re-ordering source blocks in .mpm does NOT change the hash."""

    def test_reverse_order_same_hash(self, tmp_path: pathlib.Path) -> None:
        sources = [
            ("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH),
            ("beta", _VALID_URL_B, _VALID_REVISION_B, _VALID_PATH_B),
            ("gamma", "https://example.com/g.git", "develop", "repo-specs/g/meta.xml"),
        ]
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, sources, filename=".mpm")
        file_b = _write_mpm(dir_b, list(reversed(sources)), filename=".mpm")
        assert mpm_hash(file_a) == mpm_hash(file_b)

    @pytest.mark.parametrize(
        "order_a,order_b",
        [
            (["alpha", "beta"], ["beta", "alpha"]),
            (["alpha", "beta", "gamma"], ["gamma", "alpha", "beta"]),
            (["alpha", "beta", "gamma"], ["beta", "gamma", "alpha"]),
        ],
    )
    def test_various_orderings_same_hash(
        self,
        tmp_path: pathlib.Path,
        order_a: list[str],
        order_b: list[str],
    ) -> None:
        all_sources = {
            "alpha": (_VALID_URL, _VALID_REVISION, _VALID_PATH),
            "beta": (_VALID_URL_B, _VALID_REVISION_B, _VALID_PATH_B),
            "gamma": ("https://example.com/g.git", "develop", "repo-specs/g/meta.xml"),
        }
        sources_a = [(n, *all_sources[n]) for n in order_a]
        sources_b = [(n, *all_sources[n]) for n in order_b]
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, sources_a)
        file_b = _write_mpm(dir_b, sources_b)
        assert mpm_hash(file_a) == mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashComments:
    """Adding, removing, or modifying comments does NOT change the hash."""

    def test_without_comments_equals_with_comments(self, tmp_path: pathlib.Path) -> None:
        sources = [("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH)]
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, sources)
        file_b = _write_mpm(
            dir_b,
            sources,
            prefix_lines=["# This is a comment", "# Another comment"],
            suffix_lines=["# trailing comment"],
        )
        assert mpm_hash(file_a) == mpm_hash(file_b)

    def test_different_comments_same_hash(self, tmp_path: pathlib.Path) -> None:
        sources = [("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH)]
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, sources, prefix_lines=["# comment v1"])
        file_b = _write_mpm(dir_b, sources, prefix_lines=["# comment v2 -- completely different"])
        assert mpm_hash(file_a) == mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashBlankLines:
    """Adding or removing blank lines does NOT change the hash."""

    def test_with_blank_lines_same_as_without(self, tmp_path: pathlib.Path) -> None:
        sources = [("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH)]
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, sources)
        file_b = _write_mpm(
            dir_b,
            sources,
            prefix_lines=["", ""],
            suffix_lines=["", "", ""],
        )
        assert mpm_hash(file_a) == mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashRevisionChange:
    """Changing any REVISION value DOES change the hash."""

    @pytest.mark.parametrize(
        "rev_a,rev_b",
        [
            ("main", "develop"),
            ("v1.0.0", "v2.0.0"),
            ("abc1234", "def5678"),
        ],
    )
    def test_different_revision_different_hash(
        self,
        tmp_path: pathlib.Path,
        rev_a: str,
        rev_b: str,
    ) -> None:
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, [("alpha", _VALID_URL, rev_a, _VALID_PATH)])
        file_b = _write_mpm(dir_b, [("alpha", _VALID_URL, rev_b, _VALID_PATH)])
        assert mpm_hash(file_a) != mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashUrlChange:
    """Changing any URL value DOES change the hash."""

    @pytest.mark.parametrize(
        "url_a,url_b",
        [
            ("https://example.com/repo.git", "https://other.com/repo.git"),
            ("https://example.com/a.git", "https://example.com/b.git"),
        ],
    )
    def test_different_url_different_hash(
        self,
        tmp_path: pathlib.Path,
        url_a: str,
        url_b: str,
    ) -> None:
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, [("alpha", url_a, _VALID_REVISION, _VALID_PATH)])
        file_b = _write_mpm(dir_b, [("alpha", url_b, _VALID_REVISION, _VALID_PATH)])
        assert mpm_hash(file_a) != mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashPathChange:
    """Changing any PATH value DOES change the hash."""

    @pytest.mark.parametrize(
        "path_a,path_b",
        [
            ("repo-specs/a/meta.xml", "repo-specs/b/meta.xml"),
            ("specs/svc.xml", "specs/other-svc.xml"),
        ],
    )
    def test_different_path_different_hash(
        self,
        tmp_path: pathlib.Path,
        path_a: str,
        path_b: str,
    ) -> None:
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, [("alpha", _VALID_URL, _VALID_REVISION, path_a)])
        file_b = _write_mpm(dir_b, [("alpha", _VALID_URL, _VALID_REVISION, path_b)])
        assert mpm_hash(file_a) != mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashSourceNameChange:
    """Changing a source name DOES change the hash."""

    @pytest.mark.parametrize(
        "name_a,name_b",
        [
            ("foo", "bar"),
            ("alpha", "Alpha"),
            ("mysvc", "my_svc"),
        ],
    )
    def test_different_source_name_different_hash(
        self,
        tmp_path: pathlib.Path,
        name_a: str,
        name_b: str,
    ) -> None:
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, [(name_a, _VALID_URL, _VALID_REVISION, _VALID_PATH)])
        file_b = _write_mpm(dir_b, [(name_b, _VALID_URL, _VALID_REVISION, _VALID_PATH)])
        assert mpm_hash(file_a) != mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashNonSourceKeys:
    """GITBASE, CLAUDE_MARKETPLACES_DIR, MPM_MARKETPLACE_INSTALL do NOT change hash."""

    @pytest.mark.parametrize(
        "extra_lines",
        [
            ["GITBASE=https://github.com"],
            ["CLAUDE_MARKETPLACES_DIR=/opt/marketplaces"],
            ["MPM_MARKETPLACE_INSTALL=true"],
            [
                "GITBASE=https://github.com",
                "CLAUDE_MARKETPLACES_DIR=/opt/mp",
                "MPM_MARKETPLACE_INSTALL=false",
            ],
        ],
    )
    def test_non_source_keys_do_not_affect_hash(
        self,
        tmp_path: pathlib.Path,
        extra_lines: list[str],
    ) -> None:
        sources = [("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH)]
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        file_a = _write_mpm(dir_a, sources)
        file_b = _write_mpm(dir_b, sources, suffix_lines=extra_lines)
        assert mpm_hash(file_a) == mpm_hash(file_b)


@pytest.mark.unit
class TestMPMHashTabInUrl:
    """A URL containing a literal tab raises MPMHashError."""

    def test_tab_in_url_raises(self, tmp_path: pathlib.Path) -> None:
        url_with_tab = "https://example.com/re\tpo.git"
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            f"MPM_SOURCE_alpha_URL={url_with_tab}\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=repo-specs/alpha/meta.xml\n"
            "MPM_SOURCE_alpha_NAME=alpha\n"
            "MPM_SOURCE_alpha_GITBASE=https://example.com\n",
            encoding="utf-8",
        )
        with pytest.raises(MPMHashError) as exc_info:
            mpm_hash(mpm_file)
        msg = str(exc_info.value)
        assert "alpha" in msg
        assert "URL" in msg
        assert "0x09" in msg

    def test_tab_in_url_error_names_source(self, tmp_path: pathlib.Path) -> None:
        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "MPM_SOURCE_mysvc_URL=https://x.com/r\tepo.git\n"
            "MPM_SOURCE_mysvc_REF=main\n"
            "MPM_SOURCE_mysvc_PATH=specs/meta.xml\n"
            "MPM_SOURCE_mysvc_NAME=mysvc\n"
            "MPM_SOURCE_mysvc_GITBASE=https://example.com\n",
            encoding="utf-8",
        )
        with pytest.raises(MPMHashError, match="mysvc"):
            mpm_hash(mpm_file)


@pytest.mark.unit
class TestMPMHashForbiddenCharInName:
    """A source name containing a forbidden character raises MPMHashError."""

    def test_tab_in_name_via_monkeypatch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inject a tab into a source name after parsing to test name validation."""
        import mpm_cli.core.mpm_hash as mod

        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "MPM_SOURCE_alpha_URL=https://example.com/r.git\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=specs/meta.xml\n",
            encoding="utf-8",
        )

        def _fake_parse(path: pathlib.Path) -> dict:
            return {
                "MPM_SOURCES": ["al\tpha"],
                "sources": {
                    "al\tpha": {
                        "url": "https://example.com/r.git",
                        "ref": "main",
                        "path": "specs/meta.xml",
                    }
                },
                "MPM_MARKETPLACE_INSTALL": False,
                "globals": {},
            }

        monkeypatch.setattr(mod, "parse_mpmenv", _fake_parse)
        with pytest.raises(MPMHashError) as exc_info:
            mpm_hash(mpm_file)
        msg = str(exc_info.value)
        assert "ALIAS" in msg
        assert "0x09" in msg

    def test_nul_in_name_via_monkeypatch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inject a NUL byte into a source name after parsing to test name validation."""
        import mpm_cli.core.mpm_hash as mod

        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "MPM_SOURCE_alpha_URL=https://example.com/r.git\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=specs/meta.xml\n",
            encoding="utf-8",
        )

        def _fake_parse(path: pathlib.Path) -> dict:
            return {
                "MPM_SOURCES": ["al\x00pha"],
                "sources": {
                    "al\x00pha": {
                        "url": "https://example.com/r.git",
                        "ref": "main",
                        "path": "specs/meta.xml",
                    }
                },
                "MPM_MARKETPLACE_INSTALL": False,
                "globals": {},
            }

        monkeypatch.setattr(mod, "parse_mpmenv", _fake_parse)
        with pytest.raises(MPMHashError) as exc_info:
            mpm_hash(mpm_file)
        msg = str(exc_info.value)
        assert "ALIAS" in msg
        assert "0x00" in msg

    def test_newline_in_name_via_monkeypatch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inject a newline into a source name after parsing to test name validation."""
        import mpm_cli.core.mpm_hash as mod

        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "MPM_SOURCE_alpha_URL=https://example.com/r.git\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=specs/meta.xml\n",
            encoding="utf-8",
        )

        def _fake_parse(path: pathlib.Path) -> dict:
            return {
                "MPM_SOURCES": ["al\npha"],
                "sources": {
                    "al\npha": {
                        "url": "https://example.com/r.git",
                        "ref": "main",
                        "path": "specs/meta.xml",
                    }
                },
                "MPM_MARKETPLACE_INSTALL": False,
                "globals": {},
            }

        monkeypatch.setattr(mod, "parse_mpmenv", _fake_parse)
        with pytest.raises(MPMHashError) as exc_info:
            mpm_hash(mpm_file)
        msg = str(exc_info.value)
        assert "ALIAS" in msg
        assert "0x0A" in msg


@pytest.mark.unit
class TestMPMHashNewlineInPath:
    """A PATH containing a literal newline raises MPMHashError."""

    def test_newline_in_path_via_monkeypatch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inject a newline into the path value after parsing to test validation."""
        import mpm_cli.core.mpm_hash as mod

        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "MPM_SOURCE_alpha_URL=https://example.com/r.git\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=specs/meta.xml\n",
            encoding="utf-8",
        )

        def _fake_parse(path: pathlib.Path) -> dict:
            return {
                "MPM_SOURCES": ["alpha"],
                "sources": {
                    "alpha": {
                        "url": "https://example.com/r.git",
                        "ref": "main",
                        "path": "specs/meta\nxml",
                    }
                },
                "MPM_MARKETPLACE_INSTALL": False,
                "globals": {},
            }

        monkeypatch.setattr(mod, "parse_mpmenv", _fake_parse)
        with pytest.raises(MPMHashError) as exc_info:
            mpm_hash(mpm_file)
        msg = str(exc_info.value)
        assert "alpha" in msg
        assert "PATH" in msg
        assert "0x0A" in msg


@pytest.mark.unit
class TestMPMHashNulInRevision:
    """A REVISION containing a literal NUL byte raises MPMHashError."""

    def test_nul_in_revision_via_monkeypatch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inject a NUL byte into the revision value after parsing to test validation."""
        import mpm_cli.core.mpm_hash as mod

        mpm_file = tmp_path / ".mpm"
        mpm_file.write_text(
            "MPM_SOURCE_alpha_URL=https://example.com/r.git\n"
            "MPM_SOURCE_alpha_REF=main\n"
            "MPM_SOURCE_alpha_PATH=specs/meta.xml\n",
            encoding="utf-8",
        )

        def _fake_parse(path: pathlib.Path) -> dict:
            return {
                "MPM_SOURCES": ["alpha"],
                "sources": {
                    "alpha": {
                        "url": "https://example.com/r.git",
                        "ref": "ma\x00in",
                        "path": "specs/meta.xml",
                    }
                },
                "MPM_MARKETPLACE_INSTALL": False,
                "globals": {},
            }

        monkeypatch.setattr(mod, "parse_mpmenv", _fake_parse)
        with pytest.raises(MPMHashError) as exc_info:
            mpm_hash(mpm_file)
        msg = str(exc_info.value)
        assert "alpha" in msg
        assert "REF" in msg
        assert "0x00" in msg


@pytest.mark.unit
class TestMPMHashSignature:
    """mpm_hash(mpm_path: Path) -> str: no optional kwargs, stable signature."""

    def test_accepts_path_argument(self, tmp_path: pathlib.Path) -> None:
        mpm_file = _write_mpm(
            tmp_path,
            [("alpha", _VALID_URL, _VALID_REVISION, _VALID_PATH)],
        )
        result = mpm_hash(mpm_file)
        assert isinstance(result, str)

    def test_does_not_accept_extra_kwargs(self, tmp_path: pathlib.Path) -> None:
        import inspect

        sig = inspect.signature(mpm_hash)
        params = list(sig.parameters.keys())
        assert params == ["mpm_path"]


@pytest.mark.unit
class TestMPMHashEndToEndCycle:
    """End-to-end cycle: three sources, reordering plus comments, then mutation."""

    def test_cycle(self, tmp_path: pathlib.Path) -> None:
        sources_abc = [
            ("alpha", "https://example.com/alpha.git", "main", "specs/alpha/meta.xml"),
            ("beta", "https://example.com/beta.git", "develop", "specs/beta/meta.xml"),
            ("gamma", "https://example.com/gamma.git", "v1.0.0", "specs/gamma/meta.xml"),
        ]
        sources_cba = list(reversed(sources_abc))

        dir_a = tmp_path / "fixture_a"
        dir_a.mkdir()
        dir_b = tmp_path / "fixture_b"
        dir_b.mkdir()

        fixture_a = _write_mpm(dir_a, sources_abc)
        fixture_b = _write_mpm(
            dir_b,
            sources_cba,
            prefix_lines=["# Generated fixture B", "# with extra comment"],
            suffix_lines=["", "# trailing blank and comment", ""],
        )

        hash_a = mpm_hash(fixture_a)
        hash_b = mpm_hash(fixture_b)

        assert hash_a == hash_b, (
            f"Expected identical hashes for same sources in different order:\n"
            f"fixture_a hash: {hash_a}\n"
            f"fixture_b hash: {hash_b}"
        )

        sources_cba_mutated = list(sources_cba)

        sources_cba_mutated[0] = (
            sources_cba_mutated[0][0],
            sources_cba_mutated[0][1],
            "v2.0.0",
            sources_cba_mutated[0][3],
        )
        dir_b_mutated = tmp_path / "fixture_b_mutated"
        dir_b_mutated.mkdir()
        fixture_b_mutated = _write_mpm(
            dir_b_mutated,
            sources_cba_mutated,
            prefix_lines=["# Generated fixture B", "# with extra comment"],
            suffix_lines=["", "# trailing blank and comment", ""],
        )
        hash_b_mutated = mpm_hash(fixture_b_mutated)

        assert hash_a != hash_b_mutated, (
            f"Expected different hashes after REVISION change:\n"
            f"fixture_a hash: {hash_a}\n"
            f"fixture_b_mutated hash: {hash_b_mutated}"
        )

    def test_hash_matches_expected_algorithm(self, tmp_path: pathlib.Path) -> None:
        """Confirm hash matches hand-computed expected value from canonical form."""
        sources = [
            ("alpha", "https://example.com/alpha.git", "main", "specs/alpha/meta.xml"),
            ("beta", "https://example.com/beta.git", "develop", "specs/beta/meta.xml"),
        ]
        mpm_file = _write_mpm(tmp_path, sources)
        result = mpm_hash(mpm_file)
        expected = _expected_hash(sources)
        assert result == expected
