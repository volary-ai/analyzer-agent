import datetime
import glob as glob_module
import subprocess
from collections.abc import Callable
from pathlib import Path

import chromadb
import pathspec

from .agent import Agent
from .completion_api import CompletionApi
from .output_schemas import IssueWithContext, TechDebtIssue, TechDebtAnalysis, EvaluationInput, Evaluation
from .prompts import ANALYSIS_DELEGATE_PROMPT, ANALYZER_PROMPT, SEARCH_PROMPT, EVAL_PROMPT
from .search import fetch_page_content, web_search

_LS_LIMIT = 100
_GLOB_LIMIT = 100


def ls(glob: str) -> str:
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
    ret = ls_all(glob)
    if len(ret) > _LS_LIMIT:
        ret_str = "\n".join(ret[:_LS_LIMIT])
        # limit results to avoid filling the context window
        return f"found {len(ret)} results. Showing first {_LS_LIMIT}: \n{ret_str}"
    # Sort for consistent ordering
    return "\n".join(ret)


def ls_all(glob: str) -> list[str]:
    """Lists all files under a directory.

    Lower-level than ls and not designed for an LLM to wield directly.
    """
    # Use glob with recursive=True to support ** patterns
    matches = glob_module.glob(glob, recursive=True)
    # Filter out ignored paths
    return sorted(m for m in matches if not _should_ignore(m))


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


def read_file(path: str, from_line: int | None = None, to_line: int | None = None) -> str:
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
        output = subprocess.check_output(
            ["git", "blame", "--date=short", path], text=True, stderr=subprocess.STDOUT, timeout=30
        )

        # Filter lines if range is specified
        if from_line is not None or to_line is not None:
            lines = output.split("\n")
            start = (from_line - 1) if from_line is not None else 0
            end = to_line if to_line is not None else len(lines)
            return "\n".join(lines[start:end])

        return output

    except subprocess.CalledProcessError:
        # If git blame fails (e.g., file not tracked), fall back to plain file reading
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

            # Apply line range filtering
            if from_line is not None or to_line is not None:
                start = (from_line - 1) if from_line is not None else 0
                end = to_line if to_line is not None else len(lines)
                lines = lines[start:end]
                # Adjust line numbers to match the actual line numbers in the file
                start_num = from_line if from_line is not None else 1
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

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            # Limit output to avoid overwhelming the LLM
            lines = result.stdout.strip().split("\n")
            if len(lines) > _GLOB_LIMIT:
                return f"Found {len(lines)} matches (showing first 100):\n" + "\n".join(lines[:_GLOB_LIMIT])
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


def contextualise_issue(issue: TechDebtIssue) -> IssueWithContext:
    """
    Add file content context to a technical debt issue.

    Reads the file contents referenced in the issue (with +/- 5 lines of context)
    and returns an IssueWithContext with the file contents included.

    Args:
        issue: The technical debt issue to contextualize

    Returns:
        IssueWithContext with file contents populated
    """
    file_contents = {}
    if issue.files:
        for file_ref in issue.files:
            try:
                from_line = None
                to_line = None
                if file_ref.line_start is not None:
                    from_line = max(1, file_ref.line_start - 5)
                if file_ref.line_end is not None:
                    to_line = file_ref.line_end + 5

                content = read_file(
                    file_ref.path,
                    from_line=from_line,
                    to_line=to_line,
                )
                file_contents[file_ref.path] = content
            except Exception as e:
                file_contents[file_ref.path] = f"Error reading file: {e}"

    return IssueWithContext(issue=issue, file_contents=file_contents)


def query_issues_factory(collection: chromadb.Collection) -> Callable[[list[str]], str]:
    """
    Creates a query issues tool for semantic search over GitHub issues and PRs.

    Args:
        collection: ChromaDB collection containing indexed issues

    Returns:
        Function that performs semantic search over the issue collection
    """

    def query_issues(queries: list[str]) -> str:
        """
        Search GitHub issues and PRs using semantic vector search.

        This performs semantic search over issue titles, descriptions, and PR diffs
        using ChromaDB's vector embeddings. It finds issues based on meaning rather
        than exact keyword matches.

        Usage notes:
        - Run multiple queries with different phrasings to find related issues
        - DO NOT run multiple queries for different issues simultaneously. This will only muddy the embedding. Use
          multiple tool calls for each issue instead.
        - Queries are semantic, so "authentication failure" will match "login broken"
        - Returns top 5 most relevant results per query
        - Use this to check if issues have already been reported

        Examples:
            query_issues(["memory leak in parser"])
            query_issues(["rate limiting", "API throttling"])

        Args:
            queries: List of natural language search queries

        Returns:
            Formatted string containing top matching issues with titles, URLs, and content
        """
        results = collection.query(query_texts=queries, n_results=5)
        ret: list[str] = []

        # Process results for each query
        for query_idx, query_text in enumerate(queries):
            if query_idx > 0:
                ret.append("\n" + "=" * 80)
            ret.append(f"\nResults for query: {query_text}\n")

            for i, (doc, distance, doc_id, meta) in enumerate(
                zip(
                    results["documents"][query_idx],
                    results["distances"][query_idx],
                    results["ids"][query_idx],
                    results["metadatas"][query_idx],
                    strict=False,
                ),
                1,
            ):
                ret.append(
                    f"===== {i}. [ID: {doc_id}] (distance: {distance:.4f}) ======"
                    f"   Issue #{meta['number']} ({meta['state'].upper()}): {meta['title']}"
                    f"   URL: {meta['url']}"
                    f"   Body:\n{doc}"
                )

        return "\n".join(ret)

    return query_issues


def delegate_tool_factory(api: CompletionApi, model: str, tools: list[Callable], repo_context: str) -> Callable:
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
        delegate_agent = Agent(
            instruction=ANALYZER_PROMPT,
            tools=tools,
            model=model,
            api=api,
            agent_name="Analysis Task Runner",
        )

        prompt = ANALYSIS_DELEGATE_PROMPT.format(task=description, status=repo_context)
        return delegate_agent.run(task=task, prompt=prompt)

    return delegate_task


def web_answers_tool_factory(api: CompletionApi, model: str) -> Callable[[str], str]:
    def web_answers(question: str) -> str:
        """
        Searches the web for the answer to a question using an autonomous sub-agent.

        The sub-agent can run multiple searches and selectively fetch web pages to find the answer.
        This tool is ideal for looking up factual information, current versions, or online data.

        Examples:
            web_answers("What is the latest Go version?")
            web_answers("What are the key migration points for psycopg3?")

        It is highly recommended to use this tool to verify that a library, framework, or language is actually out of
        date.

        You should use this tool to answer well scoped questions, that can be answered in a few searches.

        :param question: The question to answer using web search
        :return: The answer to the question with sources
        """
        search_agent = Agent(
            instruction=SEARCH_PROMPT.format(question=question, date=datetime.datetime.now().isoformat()),
            tools=[web_search, fetch_page_content],
            model=model,
            api=api,
            agent_name="Web Search",
        )
        return search_agent.run()

    return web_answers


def report_issue_tool_factory(
    api: CompletionApi, model: str, agent_instruction: str, tools: list
) -> Callable:
    """
    Creates a report_issue tool that evaluates a single issue for quality and relevance.

    Args:
        api: CompletionApi instance
        model: Model to use for evaluation
        agent_instruction: Instruction for the system prompt for the agent
        tools: Tools available to the eval agent (query_issues, web_answers)

    Returns:
        Function that evaluates a single issue and returns critique
    """

    def report_issue(analysis: TechDebtAnalysis) -> str:
        """
        Report a potential technical debt issues for early feedback and critique.

        Use this tool to validate issues as you discover them. This can be used once you have done a thorough
        investigation to get feedback on your work so far. Use this to decide if you have 10-15 good issues before
        finally reporting your results to the user.

        This helps you:
        - Avoid wasting time on subjective or opinion-based suggestions
        - Ensure issues are actionable with clear next steps
        - Avoid reporting duplicate issues
        - Get feedback on impact and effort estimates

        Usage notes:
        - Call this as soon as you identify a potential issue
        - Use the feedback to refine your analysis or move on
        - Don't report issues that receive negative critique
        - Focus your exploration based on what kinds of issues are valued

        Args:
            analysis: The technical debt issue to evaluate (with title, short_description, impact, recommended_action, files)

        Returns:
            Critique of the issue with feedback on quality, relevance, and whether to include it
        """
        issues_with_context = [contextualise_issue(issue) for issue in analysis.issues]

        # Create eval agent
        eval_agent = Agent(
            instruction=agent_instruction,
            model=model,
            api=api,
            agent_name="Issue Evaluator",
            tools=tools,
        )

        eval_input = EvaluationInput(issues=issues_with_context)
        try:
            critique = eval_agent.run(prompt=EVAL_PROMPT % eval_input.model_dump_json(indent=2), output_class=Evaluation)
            return critique.model_dump_json(indent=2)
        except Exception as e:
            return f"Error evaluating issue: {e}"

    return report_issue
