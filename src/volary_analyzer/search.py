"""Web search functionality using DuckDuckGo."""

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

# Cache for fetched page content to avoid re-downloading
_page_cache: dict[str, str] = {}


def web_search(query: str, max_results: int = 10) -> str:
    """
    Search DuckDuckGo and return a list of results with titles and URLs.

    This does NOT fetch the page content - use fetch_page() for that.
    Use this to explore what's available, then selectively fetch pages that look relevant.

    Args:
        query: The search query to run
        max_results: Maximum number of results to return. Searching is cheap, so this can be set relatively high.

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
            if result.get("body"):
                # Include snippet if available
                snippet = result["body"][:200] + "..." if len(result["body"]) > 200 else result["body"]
                output.append(f"    Snippet: {snippet}")
            output.append("")  # Empty line between results

        return "\n".join(output)
    except Exception as e:
        return f"[Error performing search: {e}]"


_DEFAULT_CHUNK_SIZE = 5000


def fetch_page_content(url: str, from_char: int = 0, to_char: int = _DEFAULT_CHUNK_SIZE) -> str:
    """
    Fetch and extract text content from a URL with caching and range support.

    This function caches fetched pages to avoid re-downloading. You can fetch specific
    character ranges from the cached content without re-fetching the entire page.

    Use this to read the content of pages that look relevant from search results.
    Only fetch pages that are likely to contain the answer to your question.

    Usage patterns:
    - fetch_page_content(url) -> Returns first 5000 chars (default)
    - fetch_page_content(url, to_char=10000) -> Returns first 10000 chars
    - fetch_page_content(url, from_char=5000, to_char=10000) -> Returns chars 5000-10000
    - fetch_page_content(url, from_char=10000) -> Returns chars 10000-15000

    Args:
        url: The URL to fetch
        from_char: Starting character position (0-indexed, inclusive). Default 0.
        to_char: Ending character position (exclusive). Default 5000.

    Returns:
        Extracted text content from the requested range, with continuation guidance if truncated
    """
    try:
        # Check if page is already cached
        if url not in _page_cache:
            # Fetch and cache the full page
            response = httpx.get(
                url,
                timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                follow_redirects=True,
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

            # Cache the full content
            _page_cache[url] = text

        # Get cached content
        full_text = _page_cache[url]
        result = full_text[from_char:to_char]

        # Add helpful continuation message if there's more content
        if to_char < len(full_text):
            result += f"\n\n[Showing chars {from_char}-{to_char} of {len(full_text)}. Use from_char={to_char}, to_char={to_char + _DEFAULT_CHUNK_SIZE} to continue.]"
        elif from_char > 0:
            result += f"\n\n[Showing chars {from_char}-{len(full_text)} of {len(full_text)}. End of page.]"

        return result

    except Exception as e:
        return f"[Error fetching content: {e}]"
