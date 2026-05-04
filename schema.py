"""Pydantic output models for the code-review-agent.

The reviewer agent is constrained to emit a `ReviewReport`. PydanticAI uses these
models to (a) generate a JSON schema for the LLM's structured-output call, and
(b) validate the response, retrying on failure.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Severity = Literal["low", "medium", "high", "critical"]
Category = Literal["bug", "security", "complexity", "style"]


class Issue(BaseModel):
    """A single review finding tied to a file (and ideally a line)."""

    file: str = Field(description="Project-relative path to the file containing the issue.")
    line: Optional[int] = Field(
        default=None,
        description="1-indexed line number where the issue is located, if applicable.",
    )
    severity: Severity = Field(description="How urgently this should be fixed.")
    category: Category = Field(description="Type of issue: bug, security, complexity, or style.")
    explanation: str = Field(description="What the issue is and why it matters, in plain language.")
    fix: str = Field(description="Concrete, actionable suggested fix.")
    root_cause: Optional[str] = Field(
        default=None,
        description="If the agent traced this issue back to its origin, where it actually starts.",
    )
    related_files: Optional[List[str]] = Field(
        default=None,
        description="Other files involved in the issue (callers, dependencies, shared state).",
    )


class ReviewReport(BaseModel):
    """The final structured output of the agentic review loop."""

    summary: str = Field(description="High-level summary of the review (2-4 sentences).")
    issues: List[Issue] = Field(
        default_factory=list,
        description="All findings from the investigation, deduplicated and prioritized.",
    )
    total_files_reviewed: int = Field(description="Number of .py files included in the review.")
    critical_count: int = Field(description="Count of issues with severity='critical'.")
    high_count: int = Field(description="Count of issues with severity='high'.")
    investigation_steps: int = Field(
        description="Number of tool calls the agent made during investigation.",
    )
