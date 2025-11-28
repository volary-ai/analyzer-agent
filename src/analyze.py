import os
from pathlib import Path

from rich.table import Table

from .agent import Agent, APIKeyMissingError, console, print_combined_usage
from .prompts import COORDINATOR_PROMPT, START_ANALYSIS_PROMPT
from .output_schemas import TechDebtAnalysis
from .tools import delegate_task_to_agent, grep, ls, read_file

DEFAULT_COMPLETION_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_COORDINATOR_MODEL = "openai/gpt-5.1"
DEFAULT_DELEGATE_MODEL = "openai/gpt-5.1-codex-mini"


def analyze(
    *,
    workspace: str | None,
    completions_endpoint: str | None,
    completions_api_key: str | None,
    coordinator_model: str | None,
    delegate_model: str | None,
) -> None:
    if completions_api_key is None:
        raise APIKeyMissingError("API key is required")

    if workspace is None:
        raise ValueError("Workspace is required")

    if completions_endpoint is None:
        completions_endpoint = DEFAULT_COMPLETION_ENDPOINT

    if coordinator_model is None:
        coordinator_model = DEFAULT_COORDINATOR_MODEL

    if delegate_model is None:
        delegate_model = DEFAULT_DELEGATE_MODEL

    os.chdir(workspace)

    # Gather repository context
    repo_context = get_repo_context()

    tools = [ls, read_file, grep]

    delegate_agent = Agent(
        instruction=COORDINATOR_PROMPT,
        tools=tools,
        model=delegate_model,
        endpoint=completions_endpoint,
        api_key=completions_api_key,
        agent_name="Task Runner",
    )

    coordinator_agent = Agent(
        instruction=COORDINATOR_PROMPT,
        tools=tools + [delegate_task_to_agent(delegate_agent, repo_context)],
        model=coordinator_model,
        endpoint=completions_endpoint,
        api_key=completions_api_key,
        agent_name="Tech Debt Agent",
    )

    try:
        analysis_prompt = START_ANALYSIS_PROMPT.format(status=repo_context)
        analysis = coordinator_agent.run(
            prompt=analysis_prompt,
            output_class=TechDebtAnalysis,
        )

        if not analysis.issues:
            console.print("\n[green]No technical debt issues found![/green]")
            # Print usage stats
            print_combined_usage([coordinator_agent, delegate_agent])
            return 0

        result = print_issues(analysis)

        # Print usage stats at the end
        print_combined_usage([coordinator_agent, delegate_agent])
        return result

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        # Still print usage even on error
        print_combined_usage([coordinator_agent, delegate_agent])
        return 1


def get_repo_context() -> str:
    """
    Gather context about the repository structure and documentation.
    Returns a formatted string with repo overview information.
    """
    context_parts = []

    # Get top-level directory listing
    try:
        top_level = ls("*")
        if top_level:
            context_parts.append("## Repository Structure (top-level)")
            context_parts.append("```")
            context_parts.append("\n".join(top_level))
            context_parts.append("```")
    except Exception:
        pass

    # Try to read README.md
    readme_path = Path("README.md")
    if readme_path.exists():
        try:
            readme_content = read_file("README.md")
            context_parts.append("\n## README.md")
            context_parts.append("```markdown")
            context_parts.append(readme_content)
            context_parts.append("```")
        except Exception:
            pass

    # Try to read CLAUDE.md
    claude_md_path = Path("CLAUDE.md")
    if claude_md_path.exists():
        try:
            claude_content = read_file("CLAUDE.md")
            context_parts.append("\n## CLAUDE.md (Project Instructions)")
            context_parts.append("```markdown")
            context_parts.append(claude_content)
            context_parts.append("```")
        except Exception:
            pass

    if context_parts:
        return "\n".join(context_parts)
    else:
        return "No additional repository context available."


def print_issues(data: dict, eval_scores: dict | None = None) -> int:
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan bold", width=30)
    table.add_column("Description", style="white", width=50)
    table.add_column("Kind", style="yellow", width=15)

    if eval_scores is not None:
        table.add_column("Score", style="yellow", width=15)

    table.add_column("Files", style="dim", width=25)

    for issue in data["issues"]:
        # Format files list
        files = issue.get("files", [])
        files_display = "\n".join(files) if files else "[dim]-[/dim]"

        # Get kind or show '-'
        kind = issue.get("kind", "")
        kind_display = kind if kind else "[dim]-[/dim]"

        if eval_scores is not None:
            table.add_row(
                issue["title"],
                issue["description"] + "\n",
                kind_display,
                str(eval_scores.get(issue["title"], 0.0)),
                files_display,
            )
        else:
            table.add_row(
                issue["title"],
                issue["description"] + "\n",
                kind_display,
                files_display,
            )

    console.print(table)
    console.print(f"\n[bold]Total issues found: {len(data['issues'])}[/bold]")
    return 0
