"""Auto-discover the .mpm configuration file by walking up the directory tree.

Searches from a starting directory (default: current working directory) upward
through parent directories until a .mpm file is found or the filesystem root
is reached.
"""

from pathlib import Path

from mpm_cli.constants import MPMENV_FILENAME


def find_mpmenv(start_dir: Path | None = None) -> Path:
    """Walk up from start_dir looking for a .mpm file.

    Args:
        start_dir: Directory to start searching from. Defaults to the
            current working directory.

    Returns:
        Absolute path to the nearest .mpm file.

    Raises:
        FileNotFoundError: If no .mpm file is found between start_dir
            and the filesystem root.
    """
    current = (start_dir or Path.cwd()).resolve()

    while True:
        candidate = current / MPMENV_FILENAME
        if candidate.is_file():
            return candidate

        parent = current.parent
        if parent == current:
            break
        current = parent

    msg = (
        f"No {MPMENV_FILENAME} file found in {start_dir or Path.cwd()} "
        f"or any parent directory.\n"
        f"Run 'mpm add <entry> --catalog-source <source>' to create one, or pass an explicit path."
    )
    raise FileNotFoundError(msg)
