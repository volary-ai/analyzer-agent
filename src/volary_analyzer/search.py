"""Web search functionality using DuckDuckGo."""


import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


def ddg_search(query: str, max_results: int = 10) -> str:
    """
    Search DuckDuckGo and return a list of results with titles and URLs.

    This does NOT fetch the page content - use fetch_page() for that.
    Use this to explore what's available, then selectively fetch pages that look relevant.

    Args:
        query: The search query to run
        max_results: Maximum number of results to return (default 10)

    Returns:
        Formatted string with numbered search results showing title and URL
    """
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max_results, region="wt-wt")

        if not results:
            return f"No results found for query: {query}"

        output = [f"Search results for: {query}\n"]
        for i, result in enumerate(results, 1):
            output.append(f"[{i}] {result['title']}")
            output.append(f"    URL: {result['href']}")
            if result.get('body'):
                # Include snippet if available
                snippet = result['body'][:200] + "..." if len(result['body']) > 200 else result['body']
                output.append(f"    Snippet: {snippet}")
            output.append("")  # Empty line between results

        return "\n".join(output)
    except Exception as e:
        return f"[Error performing search: {e}]"


def fetch_page_content(url: str, max_length: int = 10000) -> str:
    """
    Fetch and extract text content from a URL.

    Use this to read the content of pages that look relevant from search results.
    Only fetch pages that are likely to contain the answer to your question.

    Args:
        url: The URL to fetch
        max_length: Maximum length of content to return (default 10000 chars)

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

