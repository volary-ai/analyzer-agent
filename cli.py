#!/usr/bin/env python3
import argparse
import os
import sys

from src.analyze import analyze
from src.completion_api import CompletionApi
from src.eval import evaluate
from src.output_schemas import TechDebtAnalysis
from src.print_issues import print_issues

# TODO(jon): proper logging to file and error handling here. We should catch exception here at the top level but right
#  now that eats the stack trace.


def analyse_cmd(api: CompletionApi, args) -> int:
    issues = analyze(
        api=api,
        coordinator_model=args.coordinator_model,
        delegate_model=args.delegate_model,
    )
    if args.json:
        print(issues.model_dump_json(indent=2))
    else:
        print_issues(issues)
    return 0


def eval_cmd(api: CompletionApi, args) -> int:
    input_analysis = TechDebtAnalysis.model_validate_json(sys.stdin.read())
    issues = evaluate(
        analysis=input_analysis,
        api=api,
        coordinator_model=args.coordinator_model,
    )
    if args.json:
        print(issues.model_dump_json(indent=2))
    else:
        print_issues(issues)
    return 0


def add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--coordinator_model",
        default=os.getenv("OPENROUTER_MODEL", "openai/gpt-5.1"),
        help="Main model to use for the top level task (default: env OPENROUTER_MODEL or openai/gpt-5.1)",
    )
    parser.add_argument(
        "--openrouter_api_key",
        default=os.getenv("OPENROUTER_API_KEY"),
        help="OpenRouter API key (default: env OPENROUTER_API_KEY)",
    )
    parser.add_argument(
        "--completions_endpoint",
        default=os.getenv("COMPLETIONS_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"),
        help="Completions endpoint (default: env COMPLETIONS_ENDPOINT or OpenRouter)",
    )
    parser.add_argument("-C", "--change_dir", help="Directory to change into before running")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (default for piping)")


def init():
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_args = subparsers.add_parser("analyze")
    analyze_args.add_argument(
        "--delegate_model",
        default=os.getenv("OPENROUTER_SMALL_MODEL", "openai/gpt-5.1-codex-mini"),
        help="Small model to use for delegated tasks (default: env OPENROUTER_SMALL_MODEL or openai/gpt-5.1-codex-mini)",
    )
    analyze_args.set_defaults(func=analyse_cmd)
    add_common_args(analyze_args)

    eval_args = subparsers.add_parser("eval")
    eval_args.set_defaults(func=eval_cmd)
    add_common_args(eval_args)

    args = parser.parse_args()

    api = CompletionApi(
        api_key=args.openrouter_api_key,
        endpoint=args.completions_endpoint,
    )

    if args.change_dir:
        os.chdir(args.change_dir)

    args.func(api, args)


def main():
    exit(init())


if __name__ == "__main__":
    main()
