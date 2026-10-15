"""Retain successful authenticated operation metadata without payloads."""
from alembic import op
import sqlalchemy as sa

revision = 'f10200'
down_revision = 'e10100'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('actor_username', sa.String(80), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(80), nullable=False),
        sa.Column('target', sa.String(300), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False))
    op.create_index('ix_audit_logs_at', 'audit_logs', ['at'])


def downgrade():
    op.drop_table('audit_logs')
