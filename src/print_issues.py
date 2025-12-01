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


def print_issues(analysis: TechDebtAnalysis | EvaluatedTechDebtAnalysis) -> int:
    """Print tech debt issues in a formatted table.

    Args:
        analysis: Either TechDebtAnalysis or EvaluatedTechDebtAnalysis

    Returns:
        Exit code (0 for success)
    """
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan bold", width=30)
    table.add_column("Description", style="white", width=40)
    table.add_column("Action", style="green", width=35)

    # Check if this is evaluated analysis by checking if first issue has evaluation
    has_evaluation = isinstance(analysis, EvaluatedTechDebtAnalysis)
    if has_evaluation:
        table.add_column("Evaluation", style="yellow", width=25)

    table.add_column("Files", style="dim", width=25)

    for issue in analysis.issues:
        # Format files list
        files_display = "\n".join(issue.files) if issue.files else "[dim]-[/dim]"

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
    return 0


if __name__ == "__main__":
    try:
        stdin_content = sys.stdin.read()

        # Try to parse as EvaluatedTechDebtAnalysis first
        try:
            analysis = EvaluatedTechDebtAnalysis.model_validate_json(stdin_content)
        except Exception:
            # Fall back to TechDebtAnalysis
            analysis = TechDebtAnalysis.model_validate_json(stdin_content)

        sys.exit(print_issues(analysis))
    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing JSON: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
