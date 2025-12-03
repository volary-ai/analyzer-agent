#!/usr/bin/env python3

import argparse
import os
import sys

from platformdirs import user_config_dir
from pydantic import ValidationError
from rich.console import Console

from .analyze import analyze
from .completion_api import CompletionApi
from .eval import eval
from .output_schemas import EvaluatedTechDebtAnalysis, TechDebtAnalysis
from .print_issues import print_issues
from .tools import web_search_tool_factory

console = Console(stderr=True)


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
        default=os.getenv("COMPLETIONS_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"),
        help="Completions endpoint (default: env COMPLETIONS_ENDPOINT or OpenRouter)",
    )
    parser.add_argument(
        "--cache_dir",
        default=user_config_dir("volary-analyzer", "volary.ai"),
        help="Directory for caching vector database (default: user config directory)",
    )
    parser.add_argument("-C", "--change_dir", help="Directory to change into before running")
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=[
            # An enum would be nice for this but it looks bad in the CLI
            "run",
            "analyze",
            "eval",
            "print",
            "search",
        ],
    )
    args = parser.parse_args()
    if not args.completions_api_key:
        sys.stderr.write("The flag --completions_api_key is required (or set the $COMPLETIONS_API_KEY env var)\n")
        return 1

    if args.change_dir:
        os.chdir(args.change_dir)

    api = CompletionApi(
        api_key=args.completions_api_key,
        endpoint=args.completions_endpoint,
    )

    match args.action:
        case "run":
            console.print("[bold green]Running analysis...[/bold green]")
            analysis = analyze(
                api=api,
                coordinator_model=args.coordinator_model,
                delegate_model=args.delegate_model,
            )
            evaluated_analysis = eval(
                api=api,
                analysis=analysis,
                coordinator_model=args.coordinator_model,
                search_model=args.delegate_model,
                cache_dir=args.cache_dir,
            )
            print_issues(evaluated_analysis)
            api.print_usage_summary()
        case "analyze":
            console.print("[bold green]Running analysis...[/bold green]")
            analysis = analyze(
                api=api,
                coordinator_model=args.coordinator_model,
                delegate_model=args.delegate_model,
            )
            print(analysis.model_dump_json(indent=2))
            api.print_usage_summary()
        case "eval":
            console.print("[bold green]Evaluating issues...[/bold green]")
            analysis = TechDebtAnalysis.model_validate_json(sys.stdin.read())
            evaluated_analysis = eval(
                api=api,
                analysis=analysis,
                coordinator_model=args.coordinator_model,
                cache_dir=args.cache_dir,
                search_model=args.delegate_model,
            )
            print(evaluated_analysis.model_dump_json(indent=2))
            api.print_usage_summary()
        case "print":
            raw = sys.stdin.read()
            try:
                analysis = EvaluatedTechDebtAnalysis.model_validate_json(raw)
            except ValidationError:
                analysis = TechDebtAnalysis.model_validate_json(raw)
            print_issues(analysis)
        case "search":
            console.print("[bold green]Searching results...[/bold green]")
            tool = web_search_tool_factory(api=api, model=args.delegate_model)
            question = sys.stdin.read().strip()
            print(tool(question))
    return 0


if __name__ == "__main__":
    sys.exit(main())
