"""SQLAlchemy ORM models matching PRD §8.1."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ── papers ────────────────────────────────────────────────────────────────────

class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    zotero_key: Mapped[str | None] = mapped_column(String(64))
    zotero_collection_key: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    short_title: Mapped[str | None] = mapped_column(Text)
    citation_key: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[Any | None] = mapped_column(JSON)   # list of strings
    year: Mapped[int | None]
    doi: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    extractions: Mapped[list["PaperExtraction"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    answers: Mapped[list["PaperAnswer"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


# ── paper_extractions ─────────────────────────────────────────────────────────

ExtractionStatus = Enum(
    "pending", "completed", "failed", name="extraction_status"
)


class PaperExtraction(Base):
    __tablename__ = "paper_extractions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    text_content: Mapped[str | None] = mapped_column(Text)
    markdown_path: Mapped[str | None] = mapped_column(Text)
    html_path: Mapped[str | None] = mapped_column(Text)
    json_path: Mapped[str | None] = mapped_column(Text)
    doctags_path: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    paper: Mapped["Paper"] = relationship(back_populates="extractions")


# ── analysis_runs ─────────────────────────────────────────────────────────────

RunStatus = Enum("pending", "running", "completed", "failed", name="run_status")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    run_name: Mapped[str | None] = mapped_column(Text)
    prompt_raw: Mapped[str | None] = mapped_column(Text)
    questions: Mapped[Any | None] = mapped_column(JSON)   # list of strings
    llm_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    langfuse_trace_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    answers: Mapped[list["PaperAnswer"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


# ── paper_answers ─────────────────────────────────────────────────────────────

class PaperAnswer(Base):
    __tablename__ = "paper_answers"
    __table_args__ = (
        UniqueConstraint("run_id", "paper_id", name="uq_run_paper"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    answers: Mapped[Any | None] = mapped_column(JSON)      # list of QuestionAnswer dicts
    references: Mapped[Any | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped["AnalysisRun"] = relationship(back_populates="answers")
    paper: Mapped["Paper"] = relationship(back_populates="answers")
