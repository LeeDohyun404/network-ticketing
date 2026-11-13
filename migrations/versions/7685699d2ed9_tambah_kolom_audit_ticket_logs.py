"""tambah_kolom_audit_ticket_logs

Revision ID: 7685699d2ed9
Revises: 244f4c03e380
Create Date: 2026-11-13 17:19:09.798497

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7685699d2ed9'
down_revision = '244f4c03e380'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ticket_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aksi', sa.String(length=50), nullable=False, server_default='status'))
        batch_op.add_column(sa.Column('field_diubah', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('nilai_lama', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('nilai_baru', sa.Text(), nullable=True))
        batch_op.alter_column('status_lama', existing_type=sa.String(length=20), nullable=True)
        batch_op.alter_column('status_baru', existing_type=sa.String(length=20), nullable=True)


def downgrade():
    with op.batch_alter_table('ticket_logs', schema=None) as batch_op:
        batch_op.alter_column('status_baru', existing_type=sa.String(length=20), nullable=False)
        batch_op.alter_column('status_lama', existing_type=sa.String(length=20), nullable=False)
        batch_op.drop_column('nilai_baru')
        batch_op.drop_column('nilai_lama')
        batch_op.drop_column('field_diubah')
        batch_op.drop_column('aksi')
