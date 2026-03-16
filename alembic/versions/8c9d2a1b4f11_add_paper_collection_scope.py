"""add paper collection scope

Revision ID: 8c9d2a1b4f11
Revises: c53ae0f456d9
Create Date: 2026-03-13 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c9d2a1b4f11"
down_revision: Union[str, Sequence[str], None] = "c53ae0f456d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("papers", sa.Column("zotero_collection_key", sa.String(64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("papers", "zotero_collection_key")
