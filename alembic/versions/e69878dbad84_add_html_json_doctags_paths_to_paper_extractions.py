"""add html json doctags paths to paper extractions

Revision ID: e69878dbad84
Revises: d3e7f2b1a5c9
Create Date: 2026-03-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e69878dbad84"
down_revision: Union[str, None] = "d3e7f2b1a5c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paper_extractions", sa.Column("html_path", sa.Text(), nullable=True)
    )
    op.add_column(
        "paper_extractions", sa.Column("json_path", sa.Text(), nullable=True)
    )
    op.add_column(
        "paper_extractions", sa.Column("doctags_path", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("paper_extractions", "doctags_path")
    op.drop_column("paper_extractions", "json_path")
    op.drop_column("paper_extractions", "html_path")
