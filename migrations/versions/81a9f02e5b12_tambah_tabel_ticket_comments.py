"""tambah_tabel_ticket_comments

Revision ID: 81a9f02e5b12
Revises: 7685699d2ed9
Create Date: 2026-11-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '81a9f02e5b12'
down_revision = '7685699d2ed9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ticket_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('dibuat_oleh', sa.Integer(), nullable=False),
        sa.Column('pesan', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dibuat_oleh'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ticket_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_comments_ticket_id'), ['ticket_id'], unique=False)


def downgrade():
    with op.batch_alter_table('ticket_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ticket_comments_ticket_id'))
    op.drop_table('ticket_comments')

