#!/usr/bin/env python3
"""
Entrypoint script for the Volary Analyzer Agent GitHub Action.
"""

import os
import sys

from src.analyze import analyze


def main() -> int:
    workspace = os.environ.get("GITHUB_WORKSPACE", "/github/workspace")
    completions_endpoint = os.environ.get("INPUT_COMPLETIONS-ENDPOINT") or None
    completions_api_key = os.environ.get("INPUT_COMPLETIONS-API-KEY") or None
    coordinator_model = os.environ.get("INPUT_COORDINATOR-MODEL") or None
    delegate_model = os.environ.get("INPUT_DELEGATE-MODEL") or None

    print(f"Analysing repository at: {workspace}")

    try:
        analyze(
            workspace=workspace,
            completions_endpoint=completions_endpoint,
            completions_api_key=completions_api_key,
            coordinator_model=coordinator_model,
            delegate_model=delegate_model,
        )
        print("Analysis complete!")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
