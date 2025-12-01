#!/usr/bin/env python3
import json
import sys

from rich.console import Console
from rich.table import Table

from .output_schemas import TechDebtAnalysis

console = Console(stderr=True)


def print_issues(analysis: TechDebtAnalysis) -> int:
    """Print tech debt issues in a formatted table.

    Args:
        analysis: A TechDebtAnalysis

    Returns:
        Exit code (0 for success)
    """
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan bold", width=30)
    table.add_column("Description", style="white", width=40)
    table.add_column("Action", style="green", width=35)

    table.add_column("Files", style="dim", width=25)

    for issue in analysis.issues:
        # Format files list
        files_display = "\n".join(issue.files) if issue.files else "[dim]-[/dim]"

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

        analysis = TechDebtAnalysis.model_validate_json(stdin_content)

        sys.exit(print_issues(analysis))
    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing JSON: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
