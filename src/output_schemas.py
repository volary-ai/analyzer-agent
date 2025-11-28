"""Pydantic models for structured data."""

from pydantic import BaseModel, ConfigDict, Field


class TechDebtIssue(BaseModel):
    """Represents a single technical debt issue."""

    # Allow extra fields (like 'kind' from old schema) to be ignored
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    title: str = Field(description="The title of the issue")
    short_description: str = Field(
        validation_alias="description",
        description="A brief description of the technical debt issue (1-2 sentences)",
    )
    impact: str = Field(
        default="Not specified",
        description="The impact of the technical debt issue (1-2 sentences). This should focus on the reasons why this "
        "change is important.",
    )
    recommended_action: str = Field(
        default="See description for details",
        description="The specific action to take to resolve this issue. Try to keep this terse and to the point. "
        "DO mention key affected files, functions and line numbers. DON'T mention every usage that needs to "
        "be updated. A good response might be 'Remove unsued foo parameter from bar() in baz.py:123'. A bad "
        "response might be '1) Remove foo parameter from bar() in baz.py:123, 2) update usage in x.py, "
        "3) update usage in y.py'",
    )
    files: list[str] | None = Field(
        default=None,
        description="Optional: a list of files related to the issue. This can refer to the whole file i.e. just main.go or a specific line i.e. main.go:12",
    )


class TechDebtAnalysis(BaseModel):
    """Container for tech debt analysis results."""

    issues: list[TechDebtIssue]
