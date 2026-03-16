"""add llm_name to analysis_runs

Revision ID: d3e7f2b1a5c9
Revises: b6e2f1a9c4d7
Create Date: 2026-03-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3e7f2b1a5c9"
down_revision: Union[str, Sequence[str], None] = "b6e2f1a9c4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("analysis_runs", sa.Column("llm_name", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("analysis_runs", "llm_name")
