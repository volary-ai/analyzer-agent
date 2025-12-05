from collections.abc import Callable

import chromadb

from .agent import Agent, CompletionApi, console
from .output_schemas import TechDebtAnalysis
from .prompts import ANALYZER_PROMPT, EVAL_SYSTEM_PROMPT, START_ANALYSIS_PROMPT
from .tools import (
    delegate_tool_factory,
    grep,
    ls,
    query_issues_factory,
    read_file,
    report_issue_tool_factory,
    web_answers_tool_factory,
)


def analyze(
    *,
    api: CompletionApi,
    coordinator_model: str,
    delegate_model: str,
    issues_collection: chromadb.Collection | None = None,
) -> TechDebtAnalysis:
    repo_context = get_repo_context()

    web_answers_tool = web_answers_tool_factory(api, delegate_model)

    eval_tools: list[Callable] = [web_answers_tool]

    github_issue_instruction = ""
    if issues_collection:
        query_issues_tool = query_issues_factory(issues_collection)
        eval_tools.append(query_issues_tool)
        github_issue_instruction = (
            "You MUST search for related issues with query_issues() to make sure you're not "
            "reporting issues that have already been considered."
        )

    # Add report_issue tool for early feedback
    report_issue_tool = report_issue_tool_factory(
        api=api,
        model=coordinator_model,
        agent_instruction=EVAL_SYSTEM_PROMPT.format(github_issue_instruction=github_issue_instruction),
        tools=eval_tools,
    )
    base_tools = [
        ls,
        read_file,
        grep,
        web_answers_tool,
    ]
    delegate_tool = delegate_tool_factory(
        api=api,
        model=delegate_model,
        tools=base_tools,
        repo_context=repo_context,
    )

    coordinator_agent = Agent(
        instruction=ANALYZER_PROMPT,
        tools=base_tools + [delegate_tool, report_issue_tool],
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
        try:
            with open(filename) as f:
                content = f.read()
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
