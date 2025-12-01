from pathlib import Path

from .agent import Agent, CompletionApi, console
from .output_schemas import TechDebtAnalysis
from .prompts import ANALYZER_PROMPT, START_ANALYSIS_PROMPT
from .tools import delegate_task_to_agent, grep, ls, read_file


def analyze(
    *,
    api: CompletionApi,
    coordinator_model: str,
    delegate_model: str,
) -> TechDebtAnalysis:
    # Gather repository context
    repo_context = get_repo_context()

    tools = [ls, read_file, grep]

    delegate_agent = Agent(
        instruction=ANALYZER_PROMPT,
        tools=tools,
        model=delegate_model,
        api=api,
        agent_name="Analysis Task Runner",
    )

    coordinator_agent = Agent(
        instruction=ANALYZER_PROMPT,
        tools=tools + [delegate_task_to_agent(delegate_agent, repo_context)],
        model=coordinator_model,
        api=api,
        agent_name="Analyzer",
    )

    start_analysis_prompt = START_ANALYSIS_PROMPT.format(status=repo_context)
    analysis = coordinator_agent.run(
        prompt=start_analysis_prompt,
        output_class=TechDebtAnalysis,
    )

    if not analysis.issues:
        console.print("\n[green]No technical debt issues found![/green]")

    return analysis


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
