"""add images_dir to paper extractions

Revision ID: f2c1b9a7d4e8
Revises: e69878dbad84
Create Date: 2026-03-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2c1b9a7d4e8"
down_revision: Union[str, None] = "e69878dbad84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paper_extractions", sa.Column("images_dir", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("paper_extractions", "images_dir")
