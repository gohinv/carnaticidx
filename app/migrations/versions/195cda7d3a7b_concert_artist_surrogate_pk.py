"""concert_artist_surrogate_pk

Revision ID: 195cda7d3a7b
Revises: d4c3d914c644
Create Date: 2026-06-11 18:34:08.370073

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '195cda7d3a7b'
down_revision = 'd4c3d914c644'
branch_labels = None
depends_on = None


def upgrade():
    # Drop PK on concert_id so multiple artists per concert are allowed
    op.drop_constraint('concert_artists_pkey', 'concert_artists', type_='primary')

    op.execute("CREATE SEQUENCE concert_artists_id_seq")
    op.add_column('concert_artists', sa.Column('id', sa.Integer(), nullable=True))
    op.execute("UPDATE concert_artists SET id = nextval('concert_artists_id_seq')")
    op.alter_column('concert_artists', 'id', nullable=False)
    op.execute(
        "ALTER TABLE concert_artists ALTER COLUMN id "
        "SET DEFAULT nextval('concert_artists_id_seq')"
    )
    op.execute("ALTER SEQUENCE concert_artists_id_seq OWNED BY concert_artists.id")
    op.create_primary_key('concert_artists_pkey', 'concert_artists', ['id'])

    op.alter_column('concert_artists', 'artist_id', existing_type=sa.INTEGER(), nullable=False)


def downgrade():
    op.drop_constraint('concert_artists_pkey', 'concert_artists', type_='primary')
    op.drop_column('concert_artists', 'id')
    op.execute("DROP SEQUENCE IF EXISTS concert_artists_id_seq")

    op.create_primary_key('concert_artists_pkey', 'concert_artists', ['concert_id'])
    op.alter_column('concert_artists', 'artist_id', existing_type=sa.INTEGER(), nullable=True)
