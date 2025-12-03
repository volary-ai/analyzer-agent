"""Pydantic models for structured data."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileReference(BaseModel):
    """Reference to a file or specific lines within a file."""

    path: str = Field(description="Path to the file relative to repository root")
    line_start: int | None = Field(
        default=None,
        description="Optional starting line number (1-indexed). If specified, line_end should also be specified.",
    )
    line_end: int | None = Field(
        default=None,
        description="Optional ending line number (1-indexed, inclusive). If specified, line_start should also be specified.",
    )

    def __str__(self) -> str:
        """String representation of the file reference."""
        if self.line_start is not None and self.line_end is not None:
            return f"{self.path}:{self.line_start}-{self.line_end}"
        elif self.line_start is not None:
            return f"{self.path}:{self.line_start}"
        else:
            return self.path


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
    files: list[FileReference] | None = Field(
        default=None,
        description="Optional: list of files related to this issue. Include specific line ranges when the issue is localized to particular code sections.",
    )


class TechDebtAnalysis(BaseModel):
    """Container for tech debt analysis results."""

    issues: list[TechDebtIssue]


class EvaluatedIssue(BaseModel):
    """A tech debt issue with evaluation criteria."""

    title: str = Field(description="The title of the issue")
    objective: bool = Field(
        description="true if we consider this issue is objective, false if it is a subjective concern"
    )
    actionable: bool = Field(
        description="true if the issue is actionable now, false if it needs to wait for a condition that isn't yet met"
    )
    production: bool = Field(
        description="true if the issue relates to a production usage of the software, false if it is related to development usage"
    )
    local: bool = Field(
        description="true if the proposed fix is locally scoped within the repo, false if it touches files in widely spread locations"
    )
    impact_score: Literal["low", "medium", "high"] = Field(
        description="Severity of the impact (or lost opportunity cost) if this issue is not addressed: low, medium, or high"
    )
    effort: Literal["low", "medium", "high"] = Field(
        description="Amount of engineering time required to implement: low, medium, or high"
    )


class Evaluation(BaseModel):
    """Container for issue evaluations."""

    issues: list[EvaluatedIssue]


class EvaluationCriteria(BaseModel):
    """Evaluation criteria for a tech debt issue."""

    objective: bool = Field(description="true if the issue is objective, false if it is subjective")
    actionable: bool = Field(description="true if the issue is actionable now, false if it needs to wait")
    production: bool = Field(description="true if the issue relates to production usage, false if development only")
    local: bool = Field(description="true if the fix is locally scoped, false if widely spread")
    impact_score: Literal["low", "medium", "high"] = Field(
        description="Severity of the impact (or lost opportunity cost) if this issue is not addressed: low, medium, or high"
    )
    effort: Literal["low", "medium", "high"] = Field(
        description="Amount of engineering time required to implement: low, medium, or high"
    )


class EvaluatedTechDebtIssue(TechDebtIssue):
    """A tech debt issue with evaluation criteria attached."""

    evaluation: EvaluationCriteria = Field(description="Evaluation criteria for this issue")


class EvaluatedTechDebtAnalysis(BaseModel):
    """Container for tech debt analysis results with evaluations."""

    issues: list[EvaluatedTechDebtIssue]


class IssueWithContext(BaseModel):
    """Tech debt issue with file contents for evaluation."""

    issue: TechDebtIssue
    file_contents: dict[str, str] = Field(
        description="Map of file paths to their contents. Only includes files referenced in the issue."
    )


class EvaluationInput(BaseModel):
    """Input structure for evaluation agent with file context."""

    issues: list[IssueWithContext]
