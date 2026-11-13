"""tambah ticket_attachments

Revision ID: d4f9a823e01b
Revises: c7e2b19f03d2
Create Date: 2026-11-13 12:31:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4f9a823e01b'
down_revision = 'c7e2b19f03d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ticket_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('nama_file', sa.String(200), nullable=False),
        sa.Column('mime_type', sa.String(50), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('jenis', sa.String(20), nullable=False, server_default='umum'),
        sa.Column('diunggah_oleh', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id']),
        sa.ForeignKeyConstraint(['diunggah_oleh'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ticket_attachments_ticket_id', 'ticket_attachments', ['ticket_id'])


def downgrade():
    op.drop_index('ix_ticket_attachments_ticket_id', table_name='ticket_attachments')
    op.drop_table('ticket_attachments')

