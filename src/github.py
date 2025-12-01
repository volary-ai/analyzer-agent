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
    Attempts to find or create (through the gh cli) a gh auth token
    :return: The token
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    if not shutil.which("gh"):
        raise Exception("Error: No GitHub authentication found (GITHUB_TOKEN / GH_TOKEN not set, `gh` binary not found")
    token = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=5).strip()
    if not token:
        raise Exception("Error: No GitHub authentication returned from `gh auth token`.")
    return token


class GitHubClient:
    def __init__(self, token: str, repo_path: str):
        self.token = token
        self.owner, _, self.repo = repo_path.partition("/")

    def _default_headers(self) -> dict:
        return {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.token}",
        }

    def get_issues(
            self,
            page: int = None,
            per_page:int = 100,
            state:str="all",
            since: str = None,
    ):
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
