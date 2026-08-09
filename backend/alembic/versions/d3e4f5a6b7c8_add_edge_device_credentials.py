"""add edge device credentials

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dispositivos", sa.Column("edge_credential_hash", sa.String(), nullable=True))
    op.add_column(
        "dispositivos",
        sa.Column("edge_credential_issued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dispositivos", "edge_credential_issued_at")
    op.drop_column("dispositivos", "edge_credential_hash")
