import datetime
import sys

import chromadb
from github import Github
from github.GithubObject import NotSet
from .analysis_history import load_analysis_history


def _get_github_issues(gh_client: Github, repo_path: str, since: str | None) -> list[dict]:
    """
    Fetch all issues from GitHub, handling pagination.

    Args:
        gh_client: Authenticated PyGithub client
        repo_path: Repository path in format "owner/repo"
        since: ISO 8601 timestamp to fetch only issues updated since then

    Returns:
        List of issue dictionaries from GitHub API

    Note:
        PyGithub automatically handles rate limiting with retries and backoff.
    """
    repo = gh_client.get_repo(repo_path)

    since_dt = datetime.datetime.fromisoformat(since.replace("Z", "+00:00")) if since else NotSet
    issues = repo.get_issues(state="all", since=since_dt)

    ret = []
    for issue in issues:
        # Convert PyGithub Issue object to dict format matching API
        issue_dict = {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "html_url": issue.html_url,
            "pull_request": {"url": issue.pull_request.url} if issue.pull_request else None,
        }
        ret.append(issue_dict)

    return ret


def _index_github_issues(collection: chromadb.Collection, issues: list[dict]) -> None:
    """
    Index GitHub issues into ChromaDB collection.

    Args:
        collection: ChromaDB collection to upsert documents into
        issues: List of issue dictionaries from GitHub API
    """
    if not issues:
        return

    documents = []
    ids = []
    metadata = []
    for issue in issues:
        # Combine title and body for better search
        title = issue["title"]
        body = issue.get("body") or ""
        doc_text = f"{title}\n\n{body}"

        documents.append(doc_text)
        issue_id = f"github_{issue['number']}"
        ids.append(issue_id)
        metadata.append(
            {
                "issue_id": issue_id,
                "source": "github",
                "state": issue["state"],
                "url": issue["html_url"],
                "title": title,
            }
        )

    # Upsert documents (update existing, add new)
    collection.upsert(
        ids=ids,
        metadatas=metadata,
        documents=documents,
    )

    # Update sync timestamp in collection metadata
    current_time = datetime.datetime.now(datetime.UTC).isoformat()
    collection.modify(
        metadata={"description": f"GitHub issues and PRs for {collection.name}", "last_sync": current_time}
    )


def _index_analysis_history(collection: chromadb.Collection, history_issues: list) -> None:
    """
    Index analysis history (previous tech debt issues) into ChromaDB collection.

    Args:
        collection: ChromaDB collection to upsert documents into
        history_issues: List of SavedTechDebtIssue objects from previous analyses
    """
    if not history_issues:
        return

    documents = []
    ids = []
    metadata = []

    for issue in history_issues:
        # Combine title, description, and recommended action for better search
        doc_text = f"{issue.title}\n\n{issue.short_description}\n\nRecommended action: {issue.recommended_action}"
        if issue.impact:
            doc_text += f"\n\nImpact: {issue.impact}"

        documents.append(doc_text)
        ids.append(issue.id)
        metadata.append(
            {
                "issue_id": issue.id,
                "title": issue.title,
                "source": "analysis_history",
                "files": ", ".join(f.path for f in issue.files) if issue.files else "",
            }
        )

    # Upsert documents (update existing, add new)
    collection.upsert(
        ids=ids,
        metadatas=metadata,
        documents=documents,
    )


def issue_vector_db(
    chroma_client: chromadb.ClientAPI,
    cache_dir: str,
    gh_client: Github | None = None,
    repo_path: str | None = None,
) -> chromadb.Collection:
    """
    Create a vector DB with both GitHub issues and analysis history.

    Args:
        chroma_client: The ChromaDB client
        cache_dir: Cache directory path for analysis history
        gh_client: Optional authenticated PyGithub client
        repo_path: Optional repository path in format "owner/repo"

    Returns:
        The ChromaDB collection with indexed issues and history
    """

    # Determine collection name based on repo
    if repo_path:
        collection_name = f"issues_{repo_path.replace('/', '_')}"
    else:
        # Use a generic name if no repo info
        from .analysis_history import _get_repo_id

        collection_name = f"issues_{_get_repo_id()}"

    collection = chroma_client.get_or_create_collection(collection_name)
    collection_meta = collection.metadata or {}
    last_sync = collection_meta.get("last_sync")

    # Index GitHub issues if available
    if gh_client and repo_path:
        print(f"Indexing GitHub issues for {repo_path}...", file=sys.stderr)
        github_issues = _get_github_issues(gh_client=gh_client, repo_path=repo_path, since=last_sync)
        _index_github_issues(collection=collection, issues=github_issues)
        print(f"Indexed {len(github_issues)} GitHub issues...", file=sys.stderr)

    # Index analysis history
    history_issues = load_analysis_history(cache_dir, since=last_sync)
    if history_issues:
        print(f"Indexing {len(history_issues)} issues from analysis history...", file=sys.stderr)
        _index_analysis_history(collection=collection, history_issues=history_issues)

    return collection
