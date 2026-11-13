"""tambah eskalasi dan notifikasi

Revision ID: e5a1b34c7890
Revises: d4f9a823e01b
Create Date: 2026-11-13 13:18:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5a1b34c7890'
down_revision = 'd4f9a823e01b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_escalated', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('escalation_level', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('escalated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('escalation_reason', sa.Text(), nullable=True))

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=True),
        sa.Column('judul', sa.String(150), nullable=False),
        sa.Column('pesan', sa.Text(), nullable=False),
        sa.Column('tipe', sa.String(30), nullable=False, server_default='eskalasi'),
        sa.Column('dibaca', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_ticket_id', 'notifications', ['ticket_id'])


def downgrade():
    op.drop_index('ix_notifications_ticket_id', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_column('escalation_reason')
        batch_op.drop_column('escalated_at')
        batch_op.drop_column('escalation_level')
        batch_op.drop_column('is_escalated')

