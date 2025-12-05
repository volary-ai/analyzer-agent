"""Utilities for managing analysis history (previous issues) in a JSONL file."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from .output_schemas import TechDebtIssue


class SavedTechDebtIssue(TechDebtIssue):
    created: datetime = Field()
    id: str = Field()


def _get_repo_id() -> str:
    """
    Generate a unique identifier for the current repository.

    Uses git remote URL if available, otherwise falls back to absolute path.

    Returns:
        A sanitized string identifier for the repo
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            remote_url = result.stdout.strip()
            # Hash the URL to create a stable identifier
            return hashlib.sha256(remote_url.encode()).hexdigest()[:16]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # Fallback to current directory path
    cwd = Path.cwd().resolve()
    return hashlib.sha256(str(cwd).encode()).hexdigest()[:16]


def get_history_file_path(cache_dir: str) -> Path:
    """
    Get the path to the analysis history JSONL file for the current repo.

    Args:
        cache_dir: Base cache directory path

    Returns:
        Path to the JSONL file in the cache directory
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    repo_id = _get_repo_id()
    return cache_path / f"analysis-history-{repo_id}.jsonl"


def load_analysis_history(cache_dir: str, since: str | None = None) -> list[SavedTechDebtIssue]:
    """
    Load previously identified issues from the history file.

    Args:
        cache_dir: Base cache directory path
        since: Optional ISO 8601 timestamp to load only issues created since then

    Returns:
        List of SavedTechDebtIssue objects from previous analyses
    """
    history_file = get_history_file_path(cache_dir)

    if not history_file.exists():
        return []

    since_dt = datetime.fromisoformat(since) if since else None
    issues = []

    with open(history_file, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                try:
                    issue_data = json.loads(line)
                    # Add line number for ID generation
                    issue_data["id"] = f"issue_{line_num}"
                    saved_issue = SavedTechDebtIssue.model_validate(issue_data)

                    # Filter by timestamp if requested
                    if since_dt and saved_issue.created <= since_dt:
                        continue

                    issues.append(saved_issue)
                except (json.JSONDecodeError, ValueError) as e:
                    # Skip malformed lines
                    print(f"Warning: Skipping malformed line in history: {e}")
                    continue

    return issues


def save_analysis_history(cache_dir: str, new_issues: list[TechDebtIssue]) -> None:
    """
    Append new issues to the analysis history file.

    Args:
        cache_dir: Base cache directory path
        new_issues: List of new TechDebtIssue objects to append
    """
    if not new_issues:
        return

    history_file = get_history_file_path(cache_dir)
    timestamp = datetime.now(UTC).isoformat()

    with open(history_file, "a", encoding="utf-8") as f:
        for issue in new_issues:
            issue_data = issue.model_dump()
            issue_data["created"] = timestamp
            # Note: line_number will be assigned when loaded
            f.write(json.dumps(issue_data) + "\n")
