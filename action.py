#!/usr/bin/env python3
"""
Entrypoint script for the Volary Analyzer Agent GitHub Action.
"""

import os
import sys
from typing import Any

from src.analyze import analyze
from src.completion_api import CompletionApi
from src.eval import eval
from src.output_schemas import EvaluatedTechDebtAnalysis
from src.print_issues import print_issues

DEFAULT_COMPLETION_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_COORDINATOR_MODEL = "openai/gpt-5.1"
DEFAULT_DELEGATE_MODEL = "openai/gpt-5.1-codex-mini"


def main() -> int:
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if not workspace:
        raise ValueError("Workspace is required")

    summary_output = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_output:
        raise ValueError("Summary output is required")

    print(f"Analysing repository at: {workspace}")
    os.chdir(workspace)

    completions_api_key = os.environ.get("INPUT_COMPLETIONS-API-KEY")
    if not completions_api_key:
        raise ValueError("API key is required")

    coordinator_model = os.environ.get("INPUT_COORDINATOR-MODEL") or None
    if not coordinator_model:
        coordinator_model = DEFAULT_COORDINATOR_MODEL

    delegate_model = os.environ.get("INPUT_DELEGATE-MODEL") or None
    if not delegate_model:
        delegate_model = DEFAULT_DELEGATE_MODEL

    completions_endpoint = os.environ.get("INPUT_COMPLETIONS-ENDPOINT")
    # Create shared CompletionApi instance for usage tracking across all agents
    api = CompletionApi(
        api_key=completions_api_key,
        endpoint=completions_endpoint or DEFAULT_COMPLETION_ENDPOINT,
    )

    try:
        analysis = analyze(
            api=api,
            coordinator_model=coordinator_model,
            delegate_model=delegate_model,
        )
        evaluated_analysis = eval(
            api=api,
            analysis=analysis,
            coordinator_model=coordinator_model,
        )
        print_issues(evaluated_analysis, width=180)
        write_summary_markdown(summary_output, evaluated_analysis)
        api.print_usage_summary()
        print("Analysis complete!")

        return 0
    except Exception as e:
        api.print_usage_summary()
        print(f"Error: {e}")
        return 1


def write_summary_markdown(summary_output: str, analysis: EvaluatedTechDebtAnalysis):
    with open(summary_output, "a") as file:
        heading = "| Title | Description | Action |"
        border = "| --- | --- | --- |"

        # Check if this is evaluated analysis by checking if first issue has evaluation
        has_evaluation = isinstance(analysis, EvaluatedTechDebtAnalysis)
        if has_evaluation:
            heading += " Evaluation |"
            border += " --- |"

        heading += " Files |"
        border += " --- |"

        file.write(heading)

        for issue in analysis.issues:
            # Format files list
            files_display = "\n".join(issue.files) if issue.files else "-"

            line = f"| {issue.title} | {issue.short_description} | {issue.recommended_action} |"

            if has_evaluation:
                # Format evaluation criteria
                eval_data = issue.evaluation.model_dump()
                eval_display = "\n".join(
                    f"{_format_eval_key(k)}: {_format_eval_value(k, v)}" for k, v in eval_data.items()
                )
                line += f" {eval_display} |"

            line += f" {files_display} |"


def _format_eval_key(key: str) -> str:
    # "impact_score" -> "Impact Score"
    return key.replace("_", " ").title()


def _format_eval_value(key: str, value: Any) -> str:
    # Booleans: Yes/No
    if isinstance(value, bool):
        return "Yes" if value else "No"

    if key == "impact_score" or key == "effort":
        score = str(value).lower()
        return score.title()

    # Fallback for anything else
    return str(value)


if __name__ == "__main__":
    sys.exit(main())
