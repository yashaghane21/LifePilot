"""enable pgvector extension

Revision ID: f3019490e023
Revises: 
Create Date: 2026-11-14 11:37:06.519818

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3019490e023'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector so later migrations can create `vector` columns for semantic memory."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Fails if any table still has a vector column, which is the safe behaviour."""
    op.execute("DROP EXTENSION IF EXISTS vector")
