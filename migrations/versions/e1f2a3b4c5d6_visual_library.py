"""visual library: generalise build_visualizations into visuals, add events

Revision ID: e1f2a3b4c5d6
Revises: c4e8a1b7d902
Create Date: 2026-08-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1b7d902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('build_visualizations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_build_visualizations_build_id'))
        batch_op.drop_index(batch_op.f('ix_build_visualizations_fingerprint'))
        batch_op.drop_index(batch_op.f('ix_build_visualizations_ready_build_id'))
        batch_op.drop_index(batch_op.f('ix_build_visualizations_status'))

    op.rename_table('build_visualizations', 'visuals')

    with op.batch_alter_table('visuals', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('entity_type', sa.String(length=16), nullable=False, server_default='build')
        )
        batch_op.add_column(
            sa.Column('entity_id', sa.String(length=96), nullable=False, server_default='')
        )
        batch_op.add_column(sa.Column('entity_slug', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('category', sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column('identity_key', sa.String(length=64), nullable=False, server_default='')
        )
        batch_op.add_column(
            sa.Column(
                'source', sa.String(length=32), nullable=False, server_default='openai-images'
            )
        )
        batch_op.add_column(
            sa.Column('is_valid', sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column('history', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('cost_usd', sa.Numeric(precision=8, scale=4), nullable=True))
        batch_op.create_index(batch_op.f('ix_visuals_build_id'), ['build_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_visuals_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_visuals_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_visuals_fingerprint'), ['fingerprint'], unique=True)
        batch_op.create_index(batch_op.f('ix_visuals_identity_key'), ['identity_key'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_visuals_ready_build_id'), ['ready_build_id'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_visuals_status'), ['status'], unique=False)

    # Rows rendered by the first visualiser: classify them and give them an
    # identity so the library can find them. scripts/generate_visual_library
    # --rekey recomputes identity keys with the current formula.
    op.execute(
        "UPDATE visuals SET "
        "entity_type = CASE WHEN ready_build_id IS NOT NULL THEN 'ready_build' ELSE 'build' END, "
        "entity_id = COALESCE(CAST(ready_build_id AS TEXT), CAST(build_id AS TEXT), ''), "
        "identity_key = fingerprint, "
        "category = 'build'"
    )

    op.create_table(
        'visual_events',
        sa.Column('id', ID, autoincrement=True, nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('entity_type', sa.String(length=16), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('visual_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_visual_events_kind'), ['kind'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('visual_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_visual_events_kind'))
    op.drop_table('visual_events')

    with op.batch_alter_table('visuals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_visuals_status'))
        batch_op.drop_index(batch_op.f('ix_visuals_ready_build_id'))
        batch_op.drop_index(batch_op.f('ix_visuals_identity_key'))
        batch_op.drop_index(batch_op.f('ix_visuals_fingerprint'))
        batch_op.drop_index(batch_op.f('ix_visuals_entity_type'))
        batch_op.drop_index(batch_op.f('ix_visuals_entity_id'))
        batch_op.drop_index(batch_op.f('ix_visuals_build_id'))
        batch_op.drop_column('cost_usd')
        batch_op.drop_column('history')
        batch_op.drop_column('is_valid')
        batch_op.drop_column('source')
        batch_op.drop_column('identity_key')
        batch_op.drop_column('category')
        batch_op.drop_column('entity_slug')
        batch_op.drop_column('entity_id')
        batch_op.drop_column('entity_type')

    op.rename_table('visuals', 'build_visualizations')

    with op.batch_alter_table('build_visualizations', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_build_visualizations_build_id'), ['build_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_build_visualizations_fingerprint'), ['fingerprint'], unique=True
        )
        batch_op.create_index(
            batch_op.f('ix_build_visualizations_ready_build_id'), ['ready_build_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_build_visualizations_status'), ['status'], unique=False
        )
