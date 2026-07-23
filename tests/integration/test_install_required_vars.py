"""Integration tests for mpm install required variable validation.

Verifies that the install command fails fast with exit code 1 and a
clear error message naming the missing variable when any of the three
required MPM_SOURCE_* variables is absent from the .mpm file.

AC-TEST-001: install fails fast with clear message when MPM_SOURCE_*_URL is missing
AC-TEST-002: install fails fast when MPM_SOURCE_*_REF is missing
AC-TEST-003: install fails fast when MPM_SOURCE_*_PATH is missing
AC-TEST-004: install succeeds with all required variables supplied
AC-FUNC-001: Every required variable must be present or install exits 1 naming the missing variable
AC-CHANNEL-001: Error output goes to stderr only; stdout is clean on failure
"""

import pathlib
from unittest.mock import patch

import pytest

from mpm_cli.cli import main


_SOURCE_NAME = "testsource"
_VALID_URL = "https://example.com/repo.git"
_VALID_REVISION = "main"
_VALID_PATH = "repo-specs/manifest.xml"
_VALID_GITBASE = "https://example.com"

_ALL_REQUIRED_VARS = (
    f"MPM_SOURCE_{_SOURCE_NAME}_URL={_VALID_URL}\n"
    f"MPM_SOURCE_{_SOURCE_NAME}_REF={_VALID_REVISION}\n"
    f"MPM_SOURCE_{_SOURCE_NAME}_PATH={_VALID_PATH}\n"
    f"MPM_SOURCE_{_SOURCE_NAME}_NAME={_SOURCE_NAME}\n"
    f"MPM_SOURCE_{_SOURCE_NAME}_GITBASE={_VALID_GITBASE}\n"
)

_MISSING_URL = f"MPM_SOURCE_{_SOURCE_NAME}_REF={_VALID_REVISION}\nMPM_SOURCE_{_SOURCE_NAME}_PATH={_VALID_PATH}\n"

_MISSING_REVISION = f"MPM_SOURCE_{_SOURCE_NAME}_URL={_VALID_URL}\nMPM_SOURCE_{_SOURCE_NAME}_PATH={_VALID_PATH}\n"

_MISSING_PATH = f"MPM_SOURCE_{_SOURCE_NAME}_URL={_VALID_URL}\nMPM_SOURCE_{_SOURCE_NAME}_REF={_VALID_REVISION}\n"


def _write_mpmenv(directory: pathlib.Path, content: str) -> pathlib.Path:
    """Write a .mpm file in directory with the given content and return its path.

    Args:
        directory: Directory in which to create the .mpm file.
        content: File content to write.

    Returns:
        Absolute path to the written .mpm file.
    """
    mpmenv = directory / ".mpm"
    mpmenv.write_text(content)
    return mpmenv.resolve()


@pytest.mark.integration
class TestInstallMissingRequiredVars:
    """AC-TEST-001/002/003 and AC-FUNC-001: install exits 1 naming the missing variable."""

    @pytest.mark.parametrize(
        "content,missing_var_suffix",
        [
            (_MISSING_URL, f"MPM_SOURCE_{_SOURCE_NAME}_URL"),
            (_MISSING_REVISION, f"MPM_SOURCE_{_SOURCE_NAME}_REF"),
            (_MISSING_PATH, f"MPM_SOURCE_{_SOURCE_NAME}_PATH"),
        ],
        ids=["missing_URL", "missing_REF", "missing_PATH"],
    )
    def test_install_exits_1_when_required_var_missing(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture,
        content: str,
        missing_var_suffix: str,
    ) -> None:
        """AC-TEST-001/002/003/AC-FUNC-001: exits 1 with error naming the missing variable."""
        mpmenv = _write_mpmenv(tmp_path, content)

        with pytest.raises(SystemExit) as exc_info:
            main(["install", str(mpmenv)])

        assert exc_info.value.code == 1, (
            f"Expected exit code 1 when {missing_var_suffix!r} is missing, got {exc_info.value.code}"
        )

        captured = capsys.readouterr()
        assert missing_var_suffix in captured.err, (
            f"Expected error message naming {missing_var_suffix!r} in stderr, got stderr={captured.err!r}"
        )

    @pytest.mark.parametrize(
        "content,missing_var_suffix",
        [
            (_MISSING_URL, f"MPM_SOURCE_{_SOURCE_NAME}_URL"),
            (_MISSING_REVISION, f"MPM_SOURCE_{_SOURCE_NAME}_REF"),
            (_MISSING_PATH, f"MPM_SOURCE_{_SOURCE_NAME}_PATH"),
        ],
        ids=["missing_URL_no_stdout", "missing_REF_no_stdout", "missing_PATH_no_stdout"],
    )
    def test_install_error_on_stderr_not_stdout(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture,
        content: str,
        missing_var_suffix: str,
    ) -> None:
        """AC-CHANNEL-001: error output goes to stderr only; stdout is clean on failure."""
        mpmenv = _write_mpmenv(tmp_path, content)

        with pytest.raises(SystemExit):
            main(["install", str(mpmenv)])

        captured = capsys.readouterr()
        assert missing_var_suffix not in captured.out, (
            f"Error for missing {missing_var_suffix!r} must not appear on stdout, got stdout={captured.out!r}"
        )
        assert "Error" in captured.err, (
            f"Expected 'Error' prefix in stderr when {missing_var_suffix!r} is missing, got stderr={captured.err!r}"
        )


@pytest.mark.integration
class TestInstallAllVarsPresent:
    """AC-TEST-004: install does not exit 1 when all required variables are supplied."""

    def test_install_proceeds_when_all_required_vars_supplied(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """AC-TEST-004: install does not raise SystemExit when all required vars are present."""
        mpmenv = _write_mpmenv(tmp_path, _ALL_REQUIRED_VARS)

        with patch("mpm_cli.commands.install.install") as mock_install:
            main(["install", str(mpmenv)])

        mock_install.assert_called_once()
        called_path: pathlib.Path = mock_install.call_args[0][0]
        assert called_path.is_absolute()
        assert called_path == mpmenv
