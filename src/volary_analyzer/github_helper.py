import os
import shutil
import subprocess

from github import Auth, Github


def get_github_repo() -> str | None:
    """Extract GitHub owner and repo name from git remote."""
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        return None

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
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    if not shutil.which("gh"):
        raise RuntimeError(
            "No GitHub authentication found. " "Set GITHUB_TOKEN/GH_TOKEN environment variable or install gh CLI."
        )
    token = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=5).strip()
    if not token:
        raise RuntimeError("No GitHub token returned from 'gh auth token'. " "Run 'gh auth login' to authenticate.")
    return token


def get_github_client() -> Github:
    """
    Create an authenticated PyGithub client.
    """
    return Github(auth=Auth.Token(github_auth()), per_page=100, retry=3)
