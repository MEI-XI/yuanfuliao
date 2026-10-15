"""Shared packaging details and inspection report attachments."""
from alembic import op
import sqlalchemy as sa

revision = 'h10400'
down_revision = 'g10300'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('materials', sa.Column('packaging', sa.String(500), nullable=False, server_default=''))
    op.create_table('report_attachments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('record_id', sa.Integer(), sa.ForeignKey('records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(250), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('media_type', sa.String(120), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_report_attachments_record_id', 'report_attachments', ['record_id'])


def downgrade():
    op.drop_table('report_attachments')
    op.drop_column('materials', 'packaging')
