#!/usr/bin/env python3
"""
Entrypoint script for the Volary Analyzer Agent GitHub Action.
"""

import os
import sys

import chromadb

from src.volary_analyzer.analyze import analyze
from src.volary_analyzer.completion_api import CompletionApi
from src.volary_analyzer.eval import eval
from src.volary_analyzer.print_issues import print_issues, render_summary_markdown
from src.volary_analyzer.tools import ls_all
from volary_analyzer.github_helper import get_github_client
from volary_analyzer.vectorised_issue_search import github_vector_db

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

    cache_dir = os.environ.get("INPUT_CACHE-DIR")
    if not cache_dir:
        # Default to workspace cache directory for GitHub Actions
        cache_dir = os.path.join(workspace, ".cache", "volary-analyzer")

    # Create shared CompletionApi instance for usage tracking across all agents
    api = CompletionApi(
        api_key=completions_api_key,
        endpoint=completions_endpoint or DEFAULT_COMPLETION_ENDPOINT,
    )

    # Github meta-info
    revision = os.environ.get("GITHUB_SHA")
    repo = os.environ.get("GITHUB_REPOSITORY")

    chroma_client = chromadb.PersistentClient(path=cache_dir)
    gh_client = get_github_client()
    collection = github_vector_db(chroma_client, gh_client, repo)

    try:
        analysis = analyze(
            api=api,
            coordinator_model=coordinator_model,
            delegate_model=delegate_model,
            issues_collection=collection,
        )
        evaluated_analysis = eval(
            api=api,
            analysis=analysis,
            coordinator_model=coordinator_model,
            issues_collection=collection,
            search_model=delegate_model,
        )
        print_issues(evaluated_analysis)
        files = set(ls_all("**/*"))
        with open(summary_output, "a") as f:
            f.write(render_summary_markdown(evaluated_analysis, repo=repo, revision=revision, files=files))
        api.print_usage_summary()
        print("Analysis complete!")

        return 0
    except Exception as e:
        api.print_usage_summary()
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
