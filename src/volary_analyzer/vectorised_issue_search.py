import datetime
import sys

import chromadb
from github import Github
from github.GithubObject import NotSet


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


def _index_issues(collection: chromadb.Collection, issues: list[dict]) -> None:
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
        ids.append(f"issue_{issue['number']}")
        metadata.append(
            {
                "number": issue["number"],
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


def github_vector_db(chroma_client: chromadb.ClientAPI, gh_client: Github, repo_path: str) -> chromadb.Collection:
    """
    Indexes a GitHub repo into a vector db.

    Args:
        chroma_client: The ChromaDB client
        gh_client: Authenticated PyGithub client
        repo_path: Repository path in format "owner/repo"

    Returns:
        The ChromaDB collection with indexed issues
    """
    print(f"Indexing GitHub issues for {repo_path}...", file=sys.stderr)
    collection_name = f"github.com_{repo_path.replace('/', '_')}"
    collection = chroma_client.get_or_create_collection(collection_name)
    collection_meta = collection.metadata or {}
    last_sync = collection_meta.get("last_sync")
    issues = _get_github_issues(gh_client=gh_client, repo_path=repo_path, since=last_sync)
    _index_issues(collection=collection, issues=issues)
    print(f"Indexed {len(issues)} new issues...", file=sys.stderr)

    return collection
