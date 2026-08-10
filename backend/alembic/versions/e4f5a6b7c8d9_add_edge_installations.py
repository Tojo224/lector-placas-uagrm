"""add independent edge installations

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("credential_hash", sa.String(), nullable=False),
        sa.Column("credential_issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_edge_installations_is_active", "edge_installations", ["is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_edge_installations_is_active", table_name="edge_installations")
    op.drop_table("edge_installations")
