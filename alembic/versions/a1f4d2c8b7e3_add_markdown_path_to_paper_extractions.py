"""add markdown path to paper extractions

Revision ID: a1f4d2c8b7e3
Revises: 8c9d2a1b4f11
Create Date: 2026-03-13 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f4d2c8b7e3"
down_revision: Union[str, Sequence[str], None] = "8c9d2a1b4f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("paper_extractions", sa.Column("markdown_path", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("paper_extractions", "markdown_path")
