#!/usr/bin/env python3
"""
Entrypoint script for the Volary Analyzer Agent GitHub Action.
"""

import os
import sys

from src.volary_analyzer.analyze import analyze
from src.volary_analyzer.completion_api import CompletionApi
from src.volary_analyzer.eval import eval
from src.volary_analyzer.print_issues import print_issues, render_summary_markdown

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
            search_model=delegate_model,
        )
        print_issues(evaluated_analysis)
        with open(summary_output, "a") as f:
            f.write(render_summary_markdown(evaluated_analysis))
        api.print_usage_summary()
        print("Analysis complete!")

        return 0
    except Exception as e:
        api.print_usage_summary()
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
