"""drop_piece_name_unique

Revision ID: e8f2a1b3c4d5
Revises: 195cda7d3a7b
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e8f2a1b3c4d5'
down_revision = '195cda7d3a7b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pieces', schema=None) as batch_op:
        batch_op.drop_constraint('pieces_name_key', type_='unique')


def downgrade():
    with op.batch_alter_table('pieces', schema=None) as batch_op:
        batch_op.create_unique_constraint('pieces_name_key', ['name'])
