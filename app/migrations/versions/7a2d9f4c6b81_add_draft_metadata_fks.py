"""add draft metadata foreign keys

Revision ID: 7a2d9f4c6b81
Revises: 593587be480a
Create Date: 2026-07-12 13:14:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a2d9f4c6b81'
down_revision = '593587be480a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('setlist_item_drafts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('raga_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('talam_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('composer_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_setlist_item_drafts_raga_id'), ['raga_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_setlist_item_drafts_talam_id'), ['talam_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_setlist_item_drafts_composer_id'), ['composer_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_setlist_item_drafts_raga_id_ragas',
            'ragas',
            ['raga_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_setlist_item_drafts_talam_id_talams',
            'talams',
            ['talam_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_setlist_item_drafts_composer_id_composers',
            'composers',
            ['composer_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('setlist_item_drafts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_setlist_item_drafts_composer_id_composers', type_='foreignkey')
        batch_op.drop_constraint('fk_setlist_item_drafts_talam_id_talams', type_='foreignkey')
        batch_op.drop_constraint('fk_setlist_item_drafts_raga_id_ragas', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_setlist_item_drafts_composer_id'))
        batch_op.drop_index(batch_op.f('ix_setlist_item_drafts_talam_id'))
        batch_op.drop_index(batch_op.f('ix_setlist_item_drafts_raga_id'))
        batch_op.drop_column('composer_id')
        batch_op.drop_column('talam_id')
        batch_op.drop_column('raga_id')
