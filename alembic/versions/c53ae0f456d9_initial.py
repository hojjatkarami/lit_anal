"""initial

Revision ID: c53ae0f456d9
Revises: 
Create Date: 2026-03-13 14:30:46.257701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c53ae0f456d9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "papers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("file_path", sa.Text),
        sa.Column("zotero_key", sa.String(64)),
        sa.Column("title", sa.Text),
        sa.Column("authors", sa.JSON),
        sa.Column("year", sa.Integer),
        sa.Column("doi", sa.Text),
        sa.Column("venue", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "paper_extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text_content", sa.Text),
        sa.Column("extraction_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_name", sa.Text),
        sa.Column("prompt_raw", sa.Text),
        sa.Column("questions", sa.JSON),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("langfuse_trace_id", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "paper_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answers", sa.JSON),
        sa.Column("references", sa.JSON),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "paper_id", name="uq_run_paper"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("paper_answers")
    op.drop_table("analysis_runs")
    op.drop_table("paper_extractions")
    op.drop_table("papers")
