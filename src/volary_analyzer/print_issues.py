#!/usr/bin/env python3
import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from .output_schemas import EvaluatedTechDebtAnalysis, TechDebtAnalysis

console = Console(stderr=True)


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
        files_display = "\n".join([file.format() for file in issue.files]) if issue.files else "[dim]-[/dim]"

        if has_evaluation:
            # Format evaluation criteria
            eval_data = issue.evaluation.model_dump()
            eval_display = "\n".join(f"{_format_eval_key(k)}: {_format_eval_value(k, v)}" for k, v in eval_data.items())
            table.add_row(
                issue.title,
                issue.short_description + "\n",
                issue.recommended_action + "\n",
                eval_display,
                files_display,
            )
        else:
            table.add_row(
                issue.title,
                issue.short_description + "\n",
                issue.recommended_action + "\n",
                files_display,
            )

    console.print(table)
    console.print(f"\n[bold]Total issues found: {len(analysis.issues)}[/bold]")


def render_summary_markdown(analysis: TechDebtAnalysis | EvaluatedTechDebtAnalysis) -> str:
    """Renders a Markdown table (GitHub flavour) containing the given analysis issues."""

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

    rows += ["| " + " | ".join(_render_summary_markdown_row(issue)) + " |" for issue in analysis.issues]
    return "\n".join(rows)


def _render_summary_markdown_row(issue):
    yield _escape_newlines(issue.title)
    yield _escape_newlines(issue.short_description)
    yield _escape_newlines(issue.recommended_action)

    if evaluation := getattr(issue, "evaluation", None):
        # Format evaluation criteria
        eval_data = evaluation.model_dump()
        eval_display = "\n".join(f"{_format_eval_key(k)}: {_format_eval_value(k, v)}" for k, v in eval_data.items())
        yield _escape_newlines(eval_display)

    files_display = "\n".join([file.format() for file in issue.files]) if issue.files else "-"
    yield _escape_newlines(files_display)


def _escape_newlines(str: str) -> str:
    return str.replace("\n", "<br>")


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
