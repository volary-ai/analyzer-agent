#!/usr/bin/env python3

import argparse
import os
import sys
from enum import Enum

from analyze import analyze
from completion_api import CompletionApi
from eval import eval
from print_issues import print_issues


def main() -> int:
    """Entry point for the analyzer CLI."""
    parser = argparse.ArgumentParser(description="Volary analysis agent - finds code & tech debt issues")
    parser.add_argument(
        "--coordinator_model",
        default=os.getenv("COORDINATOR_MODEL", "openai/gpt-5.1"),
        help="Model to use (default: env COORDINATOR_MODEL or openai/gpt-5.1)",
    )
    parser.add_argument(
        "--delegate_model",
        default=os.getenv("DELEGATE_MODEL", "openai/gpt-5.1-codex-mini"),
        help="Small model for exploration (default: env DELEGATE_MODEL or openai/gpt-5.1-codex-mini)",
    )
    parser.add_argument(
        "--completions_api_key",
        default=os.getenv("COMPLETIONS_API_KEY"),
        help="API key for the completions endpoint (default: env COMPLETIONS_API_KEY)",
        required=True,
    )
    parser.add_argument(
        "--completions_endpoint",
        default=os.getenv(
            "COMPLETIONS_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"
        ),
        help="Completions endpoint (default: env COMPLETIONS_ENDPOINT or OpenRouter)",
    )
    parser.add_argument(
        "-C", "--change_dir", help="Directory to change into before running"
    )
    parser.add_argument(
        "action", nargs="?", default="run", choices=[
            # An enum would be nice for this but it looks bad in the CLI
            "run", "analyze", "eval", "print",
        ],
    )
    args = parser.parse_args()

    api = CompletionApi(
        api_key=args.completions_api_key,
        endpoints=args.completions_endpoint,
    )

    match args.action:
        case "run":
            analysis = analyze(
                api=api,
                coordinator_model=args.coordinator_model,
                delegate_model=args.delegate_model,
            )
            evaluated_analysis = eval(
                api=api,
                analysis=analysis,
                coordinator_model=args.coordinator_model,
            )
            print_issues(evaluated_analysis)
        case "analyze":
            analysis = analyze(
                api=api,
                coordinator_model=args.coordinator_model,
                delegate_model=args.delegate_model,
            )



if __name__ == "__main__":
    sys.exit(main())
