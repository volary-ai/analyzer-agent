#!/usr/bin/env python3
"""
Entrypoint script for the Volary Analyzer Agent GitHub Action.
"""
import os
import sys

from src.analyze import analyze


def main() -> int:
    workspace = os.environ.get("GITHUB_WORKSPACE", "/github/workspace")

    print(f"Analysing repository at: {workspace}")

    result = analyze(workspace)

    print("Analysis complete!")
    return result


if __name__ == "__main__":
    sys.exit(main())
