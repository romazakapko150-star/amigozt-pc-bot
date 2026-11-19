"""compatibility snapshot on leads

Revision ID: 9b2f4c7d1a63
Revises: 573e9006db8e
Create Date: 2026-08-22 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b2f4c7d1a63'
down_revision: Union[str, Sequence[str], None] = '573e9006db8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('compatibility_snapshot', sa.JSON(), nullable=False, server_default='{}')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('compatibility_snapshot')
