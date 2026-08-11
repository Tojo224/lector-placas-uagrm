"""Merge Edge installation identity and vehicle color branches.

Revision ID: f60718293a4b
Revises: e4f5a6b7c8d9, e50eae02c7d8
"""

from collections.abc import Sequence


revision: str = "f60718293a4b"
down_revision: str | Sequence[str] | None = ("e4f5a6b7c8d9", "e50eae02c7d8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
