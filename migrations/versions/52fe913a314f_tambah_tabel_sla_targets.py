"""tambah_tabel_sla_targets

Revision ID: 52fe913a314f
Revises: 
Create Date: 2026-11-13 16:44:33.727123

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '52fe913a314f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sla_targets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prioritas', sa.String(length=20), nullable=False),
        sa.Column('target_respons_menit', sa.Integer(), nullable=False),
        sa.Column('target_penyelesaian_menit', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('prioritas'),
    )


def downgrade():
    op.drop_table('sla_targets')
