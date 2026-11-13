"""tambah_maintenance_schedules

Revision ID: c7e2b19f03d2
Revises: b8f41e0a29c1
Create Date: 2026-11-13 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7e2b19f03d2'
down_revision = 'b8f41e0a29c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maintenance_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('judul', sa.String(length=150), nullable=False),
        sa.Column('deskripsi', sa.Text(), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('pelanggan', sa.String(length=150), nullable=True),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('perangkat', sa.String(length=150), nullable=True),
        sa.Column('lokasi', sa.String(length=200), nullable=True),
        sa.Column('prioritas', sa.String(length=20), nullable=False, server_default='sedang'),
        sa.Column('tanggal_rencana', sa.DateTime(), nullable=False),
        sa.Column('pengulangan', sa.String(length=20), nullable=False, server_default='tidak_ada'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='terjadwal'),
        sa.Column('last_ticket_id', sa.Integer(), nullable=True),
        sa.Column('dibuat_oleh', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['last_ticket_id'], ['tickets.id']),
        sa.ForeignKeyConstraint(['dibuat_oleh'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('maintenance_schedules', schema=None) as batch_op:
        batch_op.create_index('ix_maintenance_schedules_customer_id', ['customer_id'], unique=False)
        batch_op.create_index('ix_maintenance_schedules_device_id', ['device_id'], unique=False)
        batch_op.create_index('ix_maintenance_schedules_status', ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('maintenance_schedules', schema=None) as batch_op:
        batch_op.drop_index('ix_maintenance_schedules_status')
        batch_op.drop_index('ix_maintenance_schedules_device_id')
        batch_op.drop_index('ix_maintenance_schedules_customer_id')
    op.drop_table('maintenance_schedules')

