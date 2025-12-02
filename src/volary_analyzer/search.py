"""Web search functionality using DuckDuckGo."""

from collections.abc import Callable

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


def fetch_page_content(url: str, max_length: int = 10000) -> str:
    """
    Fetch and extract text content from a URL.

    Args:
        url: The URL to fetch
        max_length: Maximum length of content to return (default 5000)

    Returns:
        Extracted text content from the page
    """
    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return text
    except Exception as e:
        return f"[Error fetching content: {e}]"


def text(query:str) -> str:
    """
    Search the web using DuckDuckGo and return formatted results with page content.

    This tool searches the internet for information and fetches the actual content
    of the top results. Use this when you need up-to-date information from the web
    that isn't available in the codebase.

    Usage notes:
    - Good for: latest API versions, current best practices, documentation lookups
    - Returns up to 5 search results with full page content
    - Each result includes the page title, URL, and extracted text content

    Examples:
        web_search("What is the latest Go version?")
        web_search("Python asyncio best practices 2024")
        web_search("KEDA ScaledObject API version")

    Args:
        query: The search query

    Returns:
        Formatted string with search results and page content
    """
    ddgs = DDGS()
    results = ddgs.text(query, max_results=10, region="wt-wt")

    context_parts = []
    for i, result in enumerate(results, 1):
        context_parts.append(f"\n[{i}] {result['title']}")
        context_parts.append(f"URL: {result['href']}")

        # Fetch actual page content
        content = fetch_page_content(result["href"])
        context_parts.append(f"Content: {content}\n")

    return "\n".join(context_parts)

