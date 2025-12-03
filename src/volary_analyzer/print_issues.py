#!/usr/bin/env python3
import json
import re
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from .output_schemas import EvaluatedTechDebtAnalysis, FileReference, TechDebtAnalysis

console = Console(stderr=True)

# Recognises a file with optional lines on the end
# e.g. src/core/logging.go:53-65
# or   go.mod:59
_file_search_re = re.compile(
    r"(?:([^\s`,:;]+/[^\s`,:;]+)(?::([0-9]+))?(?:-([0-9]+))?|([^\s`,:;]+):([0-9]+)(?:-([0-9]+))?)"
)


def _format_eval_key(key: str) -> str:
    # "impact_score" -> "Impact Score"
    return key.replace("_", " ").title()


_COLOUR_BY_SCORE = {
    "low": "red",
    "medium": "cyan",
    "high": "green",
}

_COLOUR_BY_EFFORT = {
    "low": "green",
    "medium": "cyan",
    "high": "red",
}


def _format_eval_value(key: str, value: Any) -> str:
    # Booleans: Yes/No with colours
    if isinstance(value, bool):
        return "[green]Yes[/green]" if value else "[red]No[/red]"

    if key == "impact_score" or key == "effort":
        score = str(value).lower()
        colours = _COLOUR_BY_SCORE if key == "impact_score" else _COLOUR_BY_EFFORT
        colour = colours.get(score, "white")
        label = score.title()
        return f"[{colour}]{label}[/{colour}]"
    # Fallback for anything else
    return str(value)


def print_issues(analysis: TechDebtAnalysis | EvaluatedTechDebtAnalysis, *, width: int | None = None):
    """Print tech debt issues in a formatted table.

    Args:
        analysis: Either TechDebtAnalysis or EvaluatedTechDebtAnalysis

    Returns:
        Exit code (0 for success)
    """
    table = Table(show_header=True, header_style="bold magenta", width=width)
    table.add_column("Title", style="cyan bold", width=30, no_wrap=False)
    table.add_column("Description", style="white", width=40, no_wrap=False)
    table.add_column("Action", style="green", width=35, no_wrap=False)

    # Check if this is evaluated analysis by checking if first issue has evaluation
    has_evaluation = isinstance(analysis, EvaluatedTechDebtAnalysis)
    if has_evaluation:
        table.add_column("Evaluation", style="yellow", width=25, no_wrap=False)

    table.add_column("Files", style="dim", width=50, no_wrap=False, overflow="fold")

    for issue in analysis.issues:
        # Format files list
        files_display = "\n".join([str(file) for file in issue.files]) if issue.files else "[dim]-[/dim]"

        if has_evaluation:
            # Format evaluation criteria
            eval_data = issue.evaluation.model_dump()
            eval_display = "\n".join(f"{_format_eval_key(k)}: {_format_eval_value(k, v)}" for k, v in eval_data.items())
            table.add_row(
                issue.title,
                _highlight_files(issue.short_description) + "\n",
                _highlight_files(issue.recommended_action) + "\n",
                eval_display,
                files_display,
            )
        else:
            table.add_row(
                issue.title,
                _highlight_files(issue.short_description) + "\n",
                _highlight_files(issue.recommended_action) + "\n",
                files_display,
            )

    console.print(table)
    console.print(f"\n[bold]Total issues found: {len(analysis.issues)}[/bold]")


def _highlight_files(text: str) -> str:
    """Highlights any files in the given text in cyan."""
    return _file_search_re.sub(lambda m: "[cyan]" + m.group(0) + "[/cyan]", text)


def render_summary_markdown(
    analysis: TechDebtAnalysis | EvaluatedTechDebtAnalysis, repo: str = "", revision: str = ""
) -> str:
    """Renders a Markdown table (GitHub flavour) containing the given analysis issues.

    If repo and revision are provided, it will render GitHub source links for files.
    """

    # Header rows
    if isinstance(analysis, EvaluatedTechDebtAnalysis):
        rows = [
            "| Title       | Description    | Action         | Evaluation        | Files              |",
            "| ----------- | -------------- | -------------- | ----------------- | ------------------ |",
        ]
    else:
        rows = [
            "| Title       | Description    | Action         | Files              |",
            "| ----------- | -------------- | -------------- | ------------------ |",
        ]

    rows += ["| " + " | ".join(_render_summary_markdown_row(issue, repo, revision)) + " |" for issue in analysis.issues]
    return "\n".join(rows)


def _render_summary_markdown_row(issue, repo: str = "", revision: str = ""):
    yield _escape_newlines(issue.title)
    yield _escape_newlines(_add_source_links(issue.short_description, repo, revision))
    yield _escape_newlines(_add_source_links(issue.recommended_action, repo, revision))

    if evaluation := getattr(issue, "evaluation", None):
        # Format evaluation criteria
        eval_data = evaluation.model_dump()
        eval_display = "\n".join(f"{_format_eval_key(k)}: {_format_eval_value(k, v)}" for k, v in eval_data.items())
        yield _escape_newlines(eval_display)

    files_display = "\n".join([_file_source_link(file, repo, revision) for file in issue.files]) if issue.files else "-"
    yield _escape_newlines(files_display)


def _escape_newlines(str: str) -> str:
    return str.replace("\n", "<br>")


def _add_source_links(text: str, repo: str = "", revision: str = ""):
    """Add Markdown links to source files found in the given text."""
    return _file_search_re.sub(
        lambda m: _markdown_link(
            # The sub-groups occur in two places in the regex so we have to deal with both
            filename=m.group(1) or m.group(4),
            start=m.group(2) or m.group(5),
            end=m.group(3) or m.group(6),
            repo=repo,
            revision=revision,
        )
        if repo and revision
        else m.group(0),
        text,
    )


def _file_source_link(ref: FileReference, repo: str = "", revision: str = ""):
    """Render a Markdown link from one of our file objects."""
    return (
        _markdown_link(
            filename=ref.path,
            start=ref.line_start,
            end=ref.line_end,
            repo=repo,
            revision=revision,
        )
        if repo and revision
        else str(ref)
    )


def _markdown_link(filename: str, start: str | None, end: str | None, repo: str, revision: str):
    """Render a Markdown link from a set of components."""
    query = f"#L{start}-L{end}" if end else f"#L{start}" if start else ""
    text = f"{filename}:{start}-{end}" if end else f"{filename}:{start}" if start else filename
    return f"[{text}](https://github.com/{repo}/blob/{revision}/{filename}{query})"


def _format_eval_key(key: str) -> str:
    # "impact_score" -> "Impact Score"
    return key.replace("_", " ").title()


def _format_eval_value(key: str, value) -> str:
    # Booleans: Yes/No
    if isinstance(value, bool):
        return "Yes" if value else "No"

    if key == "impact_score" or key == "effort":
        score = str(value).lower()
        return score.title()

    # Fallback for anything else
    return str(value)


if __name__ == "__main__":
    try:
        stdin_content = sys.stdin.read()

        # Try to parse as EvaluatedTechDebtAnalysis first
        try:
            analysis = EvaluatedTechDebtAnalysis.model_validate_json(stdin_content)
        except Exception:
            # Fall back to TechDebtAnalysis
            analysis = TechDebtAnalysis.model_validate_json(stdin_content)

        print_issues(analysis)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing JSON: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
