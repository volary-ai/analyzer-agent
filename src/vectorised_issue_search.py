import datetime

import chromadb

from src.github import GitHubClient


def _get_github_issues(gh_client:GitHubClient, since: str|None) -> list[dict]:
    ret = []
    page = 1
    while True:
        response = gh_client.get_issues(page=page, since=since)

        if response.status_code != 200:
            # TODO(jon): better exception type
            raise Exception(f"Unexpected status code from github ({response.status_code}): \n{response.json()}")

        issues = response.json()
        if not issues:
            break

        page += 1

        for issue in issues:
            ret.append(issue)

        # Break if we got fewer than 100 results (last page)
        if len(issues) < 100:
            break

    return ret

def _index_issues(collection: chromadb.Collection, issues: list[dict]) -> None:
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
        metadata.append({
            "number": issue["number"],
            "state": issue["state"],
            "url": issue["html_url"],
            "title": title,
            "pull_request": issue["pull_request"]["url"] if "pull_request" in issue else "",
        })

    collection.upsert(
        ids=ids,
        metadatas=metadata,
        documents=documents,
    )
    current_time = datetime.datetime.now(datetime.UTC).isoformat()
    collection.modify(metadata={"description": "Issues and pull reqs", "last_sync": current_time})

def github_vector_db(chroma_client: chromadb.ClientAPI, gh_client: GitHubClient) -> chromadb.Collection:
    """
    Indexes a GitHub repo into a vector db.

    :param chroma_client: The ChromaDB client
    :param gh_client: Authed client to talk to GitHub with
    :return: The ChromaDB collection
    """
    collection = chroma_client.get_or_create_collection(f"github.com_{gh_client.owner}_{gh_client.repo}")
    collection_meta = collection.metadata or {}
    last_sync = collection_meta.get("last_sync")
    issues = _get_github_issues(gh_client=gh_client, since=last_sync)
    _index_issues(collection=collection, issues=issues)

    return collection
