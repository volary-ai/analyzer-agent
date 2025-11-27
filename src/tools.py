import glob as glob_module
import subprocess
from pathlib import Path

import pathspec

# Cache the gitignore spec to avoid reading it multiple times
_gitignore_spec = None


def _get_gitignore_spec():
    """Load and cache the .gitignore patterns."""
    global _gitignore_spec
    if _gitignore_spec is None:
        gitignore_path = Path(".gitignore")
        if gitignore_path.exists():
            with open(gitignore_path) as f:
                _gitignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
        else:
            _gitignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", [])
    return _gitignore_spec


def _should_ignore(path: str) -> bool:
    """Check if a path should be ignored based on .gitignore patterns."""
    spec = _get_gitignore_spec()
    # Also add common patterns that should always be ignored
    common_ignores = [
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        "*.pyc",
        ".DS_Store",
    ]

    path_obj = Path(path)

    # Check if any parent directory matches common ignores
    for part in path_obj.parts:
        if part in common_ignores or any(Path(part).match(pattern) for pattern in common_ignores):
            return True

    # Check against .gitignore patterns
    return spec.match_file(path)


def ls(glob: str) -> list[str]:
    """
    Lists files under a directory.

    Examples:
    ls(glob="*") -> List top level files and folders in the working directory
    ls(glob=".*") -> List hidden files and folders in the working directory
    ls(glob="**/*") -> List files and folders recursively in the working directory
    ls(glob="*.py") -> Returns any .py files in the working directory

    :param glob: The glob pattern to match files with. Supports the ** extension for recursive search.
    :return: a list of matching paths
    """
    # Use glob with recursive=True to support ** patterns
    matches = glob_module.glob(glob, recursive=True)
    # Filter out ignored paths
    filtered = [m for m in matches if not _should_ignore(m)]
    # Sort for consistent ordering
    return sorted(filtered)


def read_file(path: str, from_line: str = None, to_line: str = None) -> str:
    """
    Reads the contents of the file at the provider path (relative to the working directory).
    Includes git blame annotations showing line numbers and dates when each line was changed.
    :param path: the path of the file to read
    :param from_line: optional starting line number (1-indexed, inclusive)
    :param to_line: optional ending line number (1-indexed, inclusive)
    :return: The files content with annotations
    """
    file_path = Path(path)

    try:
        # Run git blame to get annotation info
        output = subprocess.run(
            ["git", "blame", "--date=short", path], capture_output=True, text=True, check=True
        ).stdout

        # Filter lines if range is specified
        if from_line is not None or to_line is not None:
            lines = output.split("\n")
            start = (int(from_line) - 1) if from_line is not None else 0
            end = int(to_line) if to_line is not None else len(lines)
            return "\n".join(lines[start:end])

        return output

    except subprocess.CalledProcessError:
        # If git blame fails (e.g., file not tracked), fall back to plain file reading
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

            # Apply line range filtering
            if from_line is not None or to_line is not None:
                start = (int(from_line) - 1) if from_line is not None else 0
                end = int(to_line) if to_line is not None else len(lines)
                lines = lines[start:end]
                # Adjust line numbers to match the actual line numbers in the file
                start_num = int(from_line) if from_line is not None else 1
                return "\n".join(f"{i:4d}→{line.rstrip()}" for i, line in enumerate(lines, start=start_num))

            return "\n".join(f"{i:4d}→{line.rstrip()}" for i, line in enumerate(lines, start=1))
