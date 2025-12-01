#!/usr/bin/env python3
"""
Simple ChromaDB search experiment.

Usage:
  # Search sample documents:
  echo "search query" | python3 chromadb_search.py

  # Search GitHub issues:
  echo "search query" | python3 chromadb_search.py owner/repo
"""

import sys

import chromadb

from src.github import GitHubClient, github_auth
from src.tools import query_issues_factory
from src.vectorised_issue_search import github_vector_db


def main():
    # Parse command line arguments
    if len(sys.argv) > 1:
        # GitHub mode: owner/repo
        repo_arg = sys.argv[1]
        if "/" not in repo_arg:
            print(f"Error: Repository should be in format 'owner/repo', got '{repo_arg}'", file=sys.stderr)
            sys.exit(1)

        owner, repo = repo_arg.split("/", 1)
    else:
        exit(1) # TODO proper flag parsing

    # Create a persistent ChromaDB client (data saved to ./chroma_db)
    client = chromadb.PersistentClient(path="./chroma_db")

    # Read search query from stdin
    query = sys.stdin.read().strip()

    if not query:
        print("Error: No search query provided", file=sys.stderr)
        print(f"Usage: echo 'your query' | python3 {sys.argv[0]}", file=sys.stderr)
        sys.exit(1)

    print(f"\nSearching for: '{query}'", file=sys.stderr)
    print("-" * 60, file=sys.stderr)
    token = github_auth()

    gh_client = GitHubClient(token=token, repo_path=repo_arg)
    collection = github_vector_db(client, gh_client)

    tool = query_issues_factory(collection)
    print(tool([query]))


if __name__ == "__main__":
    main()
