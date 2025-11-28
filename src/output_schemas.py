"""Pydantic models for structured data."""

from pydantic import BaseModel, Field


class TechDebtIssue(BaseModel):
    """Represents a single technical debt issue."""

    title: str = Field(description="The title of the issue")
    short_description: str = Field(description="A brief description of the technical debt issue (1-2 sentences)")
    recommended_action: str = Field(description="The specific action to take to resolve this issue")
    kind: str | None = Field(
        default=None,
        description="Optional: The kind of the issue. Should match one of the kinds of technical debt issues identified in the system prompt or be left empty otherwise.",
    )
    files: list[str] | None = Field(
        default=None,
        description="Optional: a list of files related to the issue. This can refer to the whole file i.e. just main.go or a specific line i.e. main.go:12",
    )


class TechDebtAnalysis(BaseModel):
    """Container for tech debt analysis results."""

    issues: list[TechDebtIssue]
