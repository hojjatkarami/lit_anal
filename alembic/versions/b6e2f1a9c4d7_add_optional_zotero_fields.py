"""add optional zotero fields

Revision ID: b6e2f1a9c4d7
Revises: a1f4d2c8b7e3
Create Date: 2026-03-13 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6e2f1a9c4d7"
down_revision: Union[str, Sequence[str], None] = "a1f4d2c8b7e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("papers", sa.Column("short_title", sa.Text(), nullable=True))
    op.add_column("papers", sa.Column("citation_key", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("papers", "citation_key")
    op.drop_column("papers", "short_title")