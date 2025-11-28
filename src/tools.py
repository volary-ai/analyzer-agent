import glob as glob_module
import subprocess
from collections.abc import Callable
from pathlib import Path

import pathspec

from .agent import Agent
from .prompts import TECH_DEBT_DELEGATED_TASK_PROMPT


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


def grep(pattern: str, path: str = ".", file_pattern: str = "*") -> str:
    """
    Searches for a pattern in files using git grep (respects .gitignore).

    Examples:
    grep(pattern="TODO", path=".", file_pattern="*.py") -> Searches for TODO in all Python files
    grep(pattern="import.*requests", path="src") -> Searches for import statements with requests in src/
    grep(pattern="class.*Error", file_pattern="*.java") -> Searches for Error classes in Java files

    :param pattern: The regex pattern to search for
    :param path: The directory to search in (default: current directory)
    :param file_pattern: Glob pattern to filter files (default: all files)
    :return: Matching lines with file names and line numbers, or a message if no matches found
    """
    try:
        # Use git grep which automatically respects .gitignore
        cmd = ["git", "grep", "-n", "-E", pattern]

        # Add path restriction if not current directory
        if path != ".":
            cmd.append("--")
            if file_pattern != "*":
                cmd.append(f"{path}/{file_pattern}")
            else:
                cmd.append(path)
        elif file_pattern != "*":
            cmd.extend(["--", file_pattern])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            # Limit output to avoid overwhelming the LLM
            lines = result.stdout.strip().split("\n")
            if len(lines) > 100:
                return f"Found {len(lines)} matches (showing first 100):\n" + "\n".join(lines[:100])
            return result.stdout.strip()
        elif result.returncode == 1:
            # No matches found (this is normal, not an error)
            return f"No matches found for pattern '{pattern}'"
        else:
            # Actual error
            return f"Error searching: {result.stderr.strip()}"

    except subprocess.TimeoutExpired:
        return "Search timed out after 30 seconds. Try narrowing the search with a more specific path or file_pattern."
    except Exception as e:
        return f"Error executing grep: {str(e)}"


def delegate_task_to_agent(delegee: Agent, repo_context: str) -> Callable:
    def delegate_task(task: str, description: str):
        """
        Delegates a task to a sub-agent to perform a complex step in analysing the repo.

        Usage notes:
        - Use this to delegate complex tasks so you can stay focused on the overall picture
        - Try to delegate tasks on a focused part of the repo, providing a description of the relevant files to the task
        - Delegate multiple tasks as once so they can be done in parallel to speed things up
        - Do NOT use this to perform simple, one-step tasks like reading a single file
        - Do NOT mention the sub-agents to the user. They are not aware of your internal architecture.

        <example-usage>
        user - Find tech debt in my repo
        agent - Glob(*) -> Makefile go.mod go.sum ...
                reasoning: I can see this is a Go repo. I should have a look at the Go source files.
        agent - Glob(**.go) -> gateway/api.go ...
                reasoning: I can see there's a gateway folder with some Go code in it however I don't see any test files.
        agent - Delegate(agent: explore, description: Check the test coverage for the API gateway under `gateway/**.go`)
        sub-agent - I can see the gateway has good integration test coverage through the Python integration tests under
                    testing/api however I can't find any unit testing.
        agent - Read(Makefile)
                reasoning: I can see that the integration tests are ran as part of `make test` which means we have good
                           test coverage of the API gateway that can be run locally before merging changes. This is a
                           low priority issue.
        </example-usage>

        :param task: A short 3-5 word description of the task to report back to the user
        :param description: A description of the task including any context that might be useful. The subagent will not
                            have access to the same information you have (e.g. code snippets) unless made available here.
        :return: The result of the complex step in analysing the repo.
        """

        prompt = TECH_DEBT_DELEGATED_TASK_PROMPT.format(task=description, status=repo_context)
        return delegee.run(task=task, prompt=prompt)

    return delegate_task
