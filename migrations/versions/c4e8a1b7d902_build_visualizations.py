"""build visualizations

Revision ID: c4e8a1b7d902
Revises: 9b2f4c7d1a63
Create Date: 2026-08-22 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1b7d902'
down_revision: Union[str, Sequence[str], None] = '9b2f4c7d1a63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'build_visualizations',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('build_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
        sa.Column('ready_build_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
        sa.Column('components', sa.JSON(), nullable=False),
        sa.Column('preset_key', sa.String(length=40), nullable=False),
        sa.Column('image_path', sa.String(length=512), nullable=True),
        sa.Column('telegram_file_id', sa.String(length=256), nullable=True),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('prompt_version', sa.String(length=8), nullable=False),
        sa.Column('prompt_hash', sa.String(length=40), nullable=False),
        sa.Column('prompt_text', sa.Text(), nullable=True),
        sa.Column('references_used', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('generation_seconds', sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['build_id'], ['builds.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['ready_build_id'], ['ready_builds.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('build_visualizations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_build_visualizations_build_id'), ['build_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_build_visualizations_fingerprint'), ['fingerprint'], unique=True)
        batch_op.create_index(batch_op.f('ix_build_visualizations_ready_build_id'), ['ready_build_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_build_visualizations_status'), ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('build_visualizations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_build_visualizations_status'))
        batch_op.drop_index(batch_op.f('ix_build_visualizations_ready_build_id'))
        batch_op.drop_index(batch_op.f('ix_build_visualizations_fingerprint'))
        batch_op.drop_index(batch_op.f('ix_build_visualizations_build_id'))
    op.drop_table('build_visualizations')
