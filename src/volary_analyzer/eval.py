"""
Evaluation agent - scores technical debt issues for relevance and actionability.
"""

from collections.abc import Callable

import chromadb
from rich.console import Console

from .agent import Agent
from .completion_api import CompletionApi
from .github_helper import get_github_client, get_github_repo
from .output_schemas import (
    EvaluatedTechDebtAnalysis,
    EvaluatedTechDebtIssue,
    Evaluation,
    EvaluationCriteria,
    EvaluationInput,
    IssueWithContext,
    TechDebtAnalysis,
    TechDebtIssue,
)
from .prompts import EVAL_PROMPT, EVAL_SYSTEM_PROMPT
from .tools import query_issues_factory, read_file, web_answers_tool_factory
from .vectorised_issue_search import github_vector_db

console = Console(stderr=True)  # Output to stderr so stdout is clean for piping


def contextualise_issue(issue: TechDebtIssue) -> IssueWithContext:
    file_contents = {}
    if issue.files:
        for file_ref in issue.files:
            try:
                from_line = None
                to_line = None
                if file_ref.line_start is not None:
                    from_line = str(max(1, file_ref.line_start - 5))
                if file_ref.line_end is not None:
                    to_line = str(file_ref.line_end + 5)

                content = read_file(
                    file_ref.path,
                    from_line=from_line,
                    to_line=to_line,
                )
                file_contents[file_ref.path] = content
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {file_ref.path}: {e}[/yellow]")
                file_contents[file_ref.path] = f"Error reading file: {e}"

    return IssueWithContext(issue=issue, file_contents=file_contents)


def eval(
    *,
    analysis: TechDebtAnalysis,
    api: CompletionApi,
    coordinator_model: str,
    search_model: str,
    cache_dir: str,
) -> EvaluatedTechDebtAnalysis:
    if not analysis.issues:
        console.print("[yellow]No issues to evaluate[/yellow]")
        return EvaluatedTechDebtAnalysis(issues=[])

    console.print(
        f"[bold]Received {len(analysis.issues)} issues to evaluate[/bold]",
        style="cyan",
    )

    tools: list[Callable] = [
        web_answers_tool_factory(
            api=api,
            model=search_model,
        )
    ]
    github_issue_instruction = ""
    if repo_path := get_github_repo():
        chroma_client = chromadb.PersistentClient(path=cache_dir)
        gh_client = get_github_client()
        collection = github_vector_db(chroma_client, gh_client, repo_path)
        tools.append(query_issues_factory(collection))
        github_issue_instruction = "You MUST search for related issues with query_issues() to make sure you're not reporting issues that have already been considered."
    else:
        console.print("I notice this isn't a GitHub repo. We have no access to your issues so may report duplicates.")

    issues_with_context = []
    for issue in analysis.issues:
        issues_with_context.append(contextualise_issue(issue))

    evaluation_input = EvaluationInput(issues=issues_with_context)

    eval_agent = Agent(
        instruction=EVAL_SYSTEM_PROMPT.format(github_issue_instruction=github_issue_instruction),
        model=coordinator_model,
        api=api,
        agent_name="Evaluator",
        tools=tools,
    )

    console.print("[bold]Running evaluation...[/bold]", style="cyan")
    evaluations = eval_agent.run(
        prompt=EVAL_PROMPT % evaluation_input.model_dump_json(indent=2),
        output_class=Evaluation,
    )

    # Merge evaluation results back into original issues
    evaluations_map = {issue.title: issue for issue in evaluations.issues}

    # Create evaluated issues with evaluation criteria
    evaluated_issues = []
    for issue in analysis.issues:
        evaluation = evaluations_map.get(issue.title)
        if evaluation:
            evaluated_issue = EvaluatedTechDebtIssue(
                title=issue.title,
                short_description=issue.short_description,
                impact=issue.impact,
                recommended_action=issue.recommended_action,
                files=issue.files,
                evaluation=EvaluationCriteria(
                    objective=evaluation.objective,
                    actionable=evaluation.actionable,
                    production=evaluation.production,
                    local=evaluation.local,
                    impact_score=evaluation.impact_score,
                    effort=evaluation.effort,
                ),
                duplicated_by=evaluation.duplicated_by,
            )
            evaluated_issues.append(evaluated_issue)

    evaluated_issues.sort(key=_order_issues)
    return EvaluatedTechDebtAnalysis(issues=evaluated_issues)


def _calculate_priority_score(issue: EvaluatedTechDebtIssue) -> float:
    """
    Calculate a priority score for an issue based on impact and effort.

    Higher scores = higher priority (low effort + high impact is best).

    Score calculation:
    - Impact: high=3, medium=2, low=1
    - Effort: low=3, medium=2, high=1 (inverted - lower effort is better)
    - Priority = impact_weight * effort_weight

    This gives us:
    - High impact + Low effort = 3 * 3 = 9 (highest priority)
    - High impact + Medium effort = 3 * 2 = 6
    - Medium impact + Low effort = 2 * 3 = 6
    - Low impact + Low effort = 1 * 3 = 3
    - High impact + High effort = 3 * 1 = 3
    - Low impact + High effort = 1 * 1 = 1 (lowest priority)
    """
    impact_scores = {"high": 3, "medium": 2, "low": 1}
    effort_scores = {"low": 3, "medium": 2, "high": 1}  # Inverted

    impact = impact_scores.get(issue.evaluation.impact_score, 1)
    effort = effort_scores.get(issue.evaluation.effort, 1)

    return impact * effort


def _order_issues(issue: EvaluatedTechDebtIssue):
    """Sort key function to order issues once they are evaluated."""
    # Primary: priority score (negative for descending)
    # Secondary: bool counts (objective, actionable, production)
    eval_data = issue.evaluation.model_dump()
    bool_score = sum(1 for k, v in eval_data.items() if isinstance(v, bool) and v)

    return (-_calculate_priority_score(issue), -bool_score)
