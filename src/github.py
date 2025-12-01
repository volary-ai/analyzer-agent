import datetime
import os
import shutil
import subprocess

import requests


def get_github_repo() -> str | None:
    """Extract GitHub owner and repo name from git remote."""
    remote_url = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        text=True,
    ).strip()

    if remote_url.startswith("git@github.com:"):
        repo_path = remote_url.removeprefix("git@github.com:")
    elif "github.com" in remote_url:
        _, _, repo_path = remote_url.partition("github.com/")
    else:
        return None

    # Remove .git suffix if present
    return repo_path.removesuffix(".git")


def github_auth() -> str:
    """
    Get GitHub authentication token from environment or gh CLI.

    Returns:
        GitHub authentication token

    Raises:
        RuntimeError: If no authentication method is available
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    if not shutil.which("gh"):
        raise RuntimeError(
            "No GitHub authentication found. "
            "Set GITHUB_TOKEN/GH_TOKEN environment variable or install gh CLI."
        )
    token = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=5).strip()
    if not token:
        raise RuntimeError(
            "No GitHub token returned from 'gh auth token'. "
            "Run 'gh auth login' to authenticate."
        )
    return token


class GitHubClient:
    """
    Client for interacting with the GitHub API.

    Attributes:
        token: GitHub authentication token
        owner: Repository owner
        repo: Repository name
    """

    def __init__(self, token: str, repo_path: str):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub authentication token
            repo_path: Repository path in format "owner/repo"
        """
        self.token = token
        self.owner, _, self.repo = repo_path.partition("/")

    def _default_headers(self) -> dict[str, str]:
        """Get default headers for GitHub API requests."""
        return {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.token}",
        }

    def get_issues(
            self,
            page: int | None = None,
            per_page: int = 100,
            state: str = "all",
            since: str | None = None,
    ) -> requests.Response:
        """
        Fetch issues from the repository.

        Args:
            page: Page number for pagination (1-indexed)
            per_page: Number of results per page (max 100)
            state: Filter by state ("open", "closed", "all")
            since: ISO 8601 timestamp to fetch only issues updated since then

        Returns:
            Response object containing the list of issues
        """
        params = {
            "state": state,
            "per_page": per_page,
            "page": page,
        }
        if since:
            params["since"] = since

        return requests.get(
            f"https://api.github.com/repos/{self.owner}/{self.repo}/issues",
            headers=self._default_headers(),
            params=params,
            timeout=30,
        )
