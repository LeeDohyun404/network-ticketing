"""tambah_customers_dan_devices

Revision ID: 244f4c03e380
Revises: 52fe913a314f
Create Date: 2026-11-13 17:10:29.851547

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '244f4c03e380'
down_revision = '52fe913a314f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nama', sa.String(length=150), nullable=False),
        sa.Column('alamat', sa.Text(), nullable=True),
        sa.Column('kontak', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nama', sa.String(length=150), nullable=False),
        sa.Column('jenis', sa.String(length=50), nullable=False),
        sa.Column('lokasi', sa.String(length=200), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('device_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_tickets_customer_id', 'customers', ['customer_id'], ['id'])
        batch_op.create_foreign_key('fk_tickets_device_id', 'devices', ['device_id'], ['id'])


def downgrade():
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tickets_device_id', type_='foreignkey')
        batch_op.drop_constraint('fk_tickets_customer_id', type_='foreignkey')
        batch_op.drop_column('device_id')
        batch_op.drop_column('customer_id')

    op.drop_table('devices')
    op.drop_table('customers')
