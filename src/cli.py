#!/usr/bin/env python3

import argparse
import os
import sys
from enum import Enum


def main() -> int:
    """Entry point for the analyzer CLI."""
    parser = argparse.ArgumentParser(description="Volary analysis agent - finds code & tech debt issues")
    parser.add_argument(
        "--model",
        default=os.getenv("COMPLETIONS_MODEL", "openai/gpt-5.1"),
        help="Model to use (default: env COMPLETIONS_MODEL or openai/gpt-5.1)",
    )
    parser.add_argument(
        "--small_model",
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
            "run", "analyse", "eval", "print",
        ],
    )
    args = parser.parse_args()
    print(action)


if __name__ == "__main__":
    sys.exit(main())
