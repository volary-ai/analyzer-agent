import os
from pathlib import Path

from src.tools import ls, read_file

DEFAULT_COMPLETION_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def analyze(
    *,
    workspace: str | None,
    completions_endpoint: str | None,
    completions_api_key: str | None,
) -> None:
    if completions_endpoint is None:
        completions_endpoint = DEFAULT_COMPLETION_ENDPOINT

    if completions_api_key is None:
        raise ValueError("API key is required")

    if workspace is None:
        raise ValueError("Workspace is required")

    os.chdir(workspace)

    print(get_repo_context())


def get_repo_context() -> str:
    """
    Gather context about the repository structure and documentation.
    Returns a formatted string with repo overview information.
    """
    context_parts = []

    # Get top-level directory listing
    try:
        top_level = ls("*")
        if top_level:
            context_parts.append("## Repository Structure (top-level)")
            context_parts.append("```")
            context_parts.append("\n".join(top_level))
            context_parts.append("```")
    except Exception:
        pass

    # Try to read README.md
    readme_path = Path("README.md")
    if readme_path.exists():
        try:
            readme_content = read_file("README.md")
            context_parts.append("\n## README.md")
            context_parts.append("```markdown")
            context_parts.append(readme_content)
            context_parts.append("```")
        except Exception:
            pass

    # Try to read CLAUDE.md
    claude_md_path = Path("CLAUDE.md")
    if claude_md_path.exists():
        try:
            claude_content = read_file("CLAUDE.md")
            context_parts.append("\n## CLAUDE.md (Project Instructions)")
            context_parts.append("```markdown")
            context_parts.append(claude_content)
            context_parts.append("```")
        except Exception:
            pass

    if context_parts:
        return "\n".join(context_parts)
    else:
        return "No additional repository context available."
