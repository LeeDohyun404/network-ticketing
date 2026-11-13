"""perangkat_customer_id_nullable

Revision ID: b8f41e0a29c1
Revises: 81a9f02e5b12
Create Date: 2026-11-13 18:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8f41e0a29c1'
down_revision = '81a9f02e5b12'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.alter_column('customer_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.alter_column('customer_id', existing_type=sa.Integer(), nullable=False)
