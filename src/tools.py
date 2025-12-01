import glob as glob_module
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pathspec
import requests

from .agent import Agent
from .prompts import ANALYSIS_DELEGATE_PROMPT


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
        output = subprocess.check_output(["git", "blame", "--date=short", path], text=True)

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


def query_issues_factory() -> Callable | None:
    """
    Creates a query issues tool.

    :return: The tool to be passed to the agent, if we're in a GitHub repo and have auth set up.
    """
    # TODO(jon): Make this tool use an abstraction over the issues. We don't want to be tied to just github, but also we
    #  want to include issues that have previously been raised by this tool but rejected by the user that may have never
    #  made it to the actual issue tracker. This is fine for the proof-of-concept though.
    repo = _get_github_repo()
    if not repo:
        return None
    token = _gh_auth()

    def query_issues(queries: list[str]) -> list[str]:
        """
        Queries issues and PRs from GitHub's search/issues API associated with this codebase. This can be used to find
        existing issues related to a topic.

        This tool is only available when working in a GitHub repository. If you see this prompt that means you're in a
        GitHub codebase.

        The query syntax uses GitHub's format i.e. SEARCH_KEYWORD_1 SEARCH_KEYWORD_N QUALIFIER_1 QUALIFIER_N e.g.
        `"use after free" SomeType in:title state:open`.

        Usage notes:
        - DO run multiple queries at once including synonyms and rephrasing of the potential issue
        - DO use this tool to verify the issue hasn't already been reported.
        - DO use the delegate_task tool for this as it's far more cost-effective

        :param queries: List of search queries to run against the issue tracker
        :return: a list of issues from the ticketing system
        """
        results = []
        for query in queries:
            try:
                # Search issues in the specific repository
                search_query = f"{query} repo:{repo}"
                response = requests.get(
                    "https://api.github.com/search/issues",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={"q": search_query, "per_page": 10},
                    timeout=10,
                )

                if response.status_code == 401:
                    return ["Error: GitHub authentication failed. Please check your GITHUB_TOKEN or GH_TOKEN."]
                elif response.status_code == 403:
                    return ["Error: GitHub API rate limit exceeded or access forbidden."]
                elif response.status_code != 200:
                    results.append(f"Error searching for '{query}': HTTP {response.status_code}")
                    continue

                data = response.json()
                total_count = data.get("total_count", 0)

                if total_count == 0:
                    results.append(f"Query: '{query}' - No issues found")
                else:
                    results.append(f"\nQuery: '{query}' - Found {total_count} issue(s) (showing top 10):\n")
                    for issue in data.get("items", []):
                        state = issue["state"].upper()
                        number = issue["number"]
                        title = issue["title"]
                        url = issue["html_url"]
                        labels = ", ".join([label["name"] for label in issue.get("labels", [])])
                        labels_str = f" [{labels}]" if labels else ""

                        results.append(f"  #{number} ({state}): {title}{labels_str}")
                        results.append(f"    URL: {url}")

            except requests.exceptions.Timeout:
                results.append(f"Error: Request timed out while searching for '{query}'")
            except Exception as e:
                results.append(f"Error searching for '{query}': {str(e)}")

        return results

    return query_issues


def _get_github_repo() -> str | None:
    """Extract GitHub owner and repo name from git remote."""
    remote_url = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        text=True,
    ).strip()

    # Handle both SSH and HTTPS URLs
    # SSH: git@github.com:owner/repo.git
    # HTTPS: https://github.com/owner/repo.git
    if remote_url.startswith("git@github.com:"):
        repo_path = remote_url.removeprefix("git@github.com:")
    elif "github.com" in remote_url:
        _, _, repo_path = remote_url.partition("github.com/")
    else:
        return None

    # Remove .git suffix if present
    return repo_path.removesuffix(".git")


def _gh_auth() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    if not shutil.which("gh"):
        raise Exception("Error: No GitHub authentication found (GITHUB_TOKEN / GH_TOKEN not set, `gh` binary not found")
    token = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=5).strip()
    if not token:
        raise Exception("Error: No GitHub authentication returned from `gh auth token`.")
    return token


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

        prompt = ANALYSIS_DELEGATE_PROMPT.format(task=description, status=repo_context)
        return delegee.run(task=task, prompt=prompt)

    return delegate_task
