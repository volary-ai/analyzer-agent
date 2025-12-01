#!/usr/bin/env python3

import argparse
import os
import sys
from enum import Enum

from src.analyze import analyze
from src.completion_api import CompletionApi
from src.eval import eval
from src.output_schemas import TechDebtAnalysis, EvaluatedTechDebtAnalysis
from src.print_issues import print_issues


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
    if not args.completions_api_key:
        sys.stderr.write(f"The flag --completions_api_key is required (or set the $COMPLETIONS_API_KEY env var)\n")
        return 1

    if args.change_dir:
        os.chdir(args.change_dir)

    api = CompletionApi(
        api_key=args.completions_api_key,
        endpoint=args.completions_endpoint,
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
            api.print_usage_summary()
        case "analyze":
            analysis = analyze(
                api=api,
                coordinator_model=args.coordinator_model,
                delegate_model=args.delegate_model,
            )
            print(analysis.model_dump_json(indent=2))
            api.print_usage_summary()
        case "eval":
            analysis = TechDebtAnalysis.model_validate_json(sys.stdin.read())
            evaluated_analysis = eval(
                api=api,
                analysis=analysis,
                coordinator_model=args.coordinator_model,
            )
            print(evaluated_analysis.model_dump_json(indent=2))
            api.print_usage_summary()
        case "print":
            analysis = EvaluatedTechDebtAnalysis.model_validate_json(sys.stdin.read())
            print_issues(evaluated_analysis)
    return 0


if __name__ == "__main__":
    sys.exit(main())
