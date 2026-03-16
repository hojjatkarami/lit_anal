"""Pydantic schemas for LLM synthesis output — matches PRD §9.2."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    quote: str = Field(description="Verbatim text excerpt from the paper supporting the answer.")
    page: int | None = Field(default=None, description="Page number where the quote appears.")
    section: str | None = Field(default=None, description="Section heading (e.g. 'Methods').")
    figure_id: str | None = Field(default=None, description="Figure identifier if relevant.")


class Reference(BaseModel):
    title: str | None = None
    year: int | None = None
    doi: str | None = None


class QuestionAnswer(BaseModel):
    question: str
    answer: str = Field(
        description=(
            "Answer to the question based strictly on the paper content. "
            "If evidence is insufficient, write 'Insufficient evidence.'"
        )
    )
    evidence: list[Evidence] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    status: Literal["answered", "insufficient_evidence", "failed"] = "answered"


class PaperAnswerOutput(BaseModel):
    paper_id: str
    paper_title: str | None
    answers: list[QuestionAnswer]


def parse_questions(prompt: str) -> list[str]:
    """
    Extract a list of distinct questions from a free-form prompt.

    Splits on numbered lists (1. 2. 3.) or explicit question marks; falls back
    to treating the whole prompt as a single question.
    """
    import re

    # Try numbered list: lines starting with "1.", "2.", etc.
    numbered_lines = re.findall(r"^\s*\d+[\.)]\s+(.*)$", prompt.strip(), flags=re.MULTILINE)
    if numbered_lines:
        return [q.strip() for q in numbered_lines if q.strip()]

    # Try splitting on lines that end with a "?" (each line = one question)
    lines = [l.strip() for l in prompt.strip().splitlines() if l.strip().endswith("?")]
    if lines:
        return lines

    # Fall back: the whole prompt as one question
    return [prompt.strip()]
