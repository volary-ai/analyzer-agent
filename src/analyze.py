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


def get_repo_context(readme_md: str = "README.md", claude_md: str = "CLAUDE.md", agents_md: str = "AGENTS.md") -> str:
    """
    Gather context about the repository structure and documentation.
    Returns a formatted string with repo overview information.
    """
    context_parts = []

    # Get top-level directory listing
    try:
        top_level = ls("*")
        if top_level:
            context_parts += [
                "## Repository Structure (top-level)",
                "```",
                "\n".join(top_level),
                "```",
            ]
    except Exception:
        pass

    headers = {
        readme_md: "README.md",
        claude_md: "CLAUDE.md (Project Instructions)",
        agents_md: "AGENTS.md (Project Instructions)",
    }

    # Try to read all these files
    for filename in [readme_md, claude_md, agents_md]:
        if Path(filename).exists():
            try:
                content = read_file(filename)
                context_parts += [
                    "\n## " + headers[filename],
                    "```markdown",
                    content,
                    "```",
                ]
            except Exception:
                pass

    if context_parts:
        return "\n".join(context_parts)
    else:
        return "No additional repository context available."
