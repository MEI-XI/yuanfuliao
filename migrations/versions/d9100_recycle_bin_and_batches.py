"""Track recycle retention and completed batch submissions."""
from alembic import op
import sqlalchemy as sa

revision = 'd9100'
down_revision = 'c8100'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('records', sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True))
    # Before restoration existed, void was terminal and updated_at was its time.
    op.execute("UPDATE records SET voided_at = updated_at WHERE status = 'void'")
    op.create_table(
        'batch_submissions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ledger_id', sa.Integer(), sa.ForeignKey('ledgers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('record_ids', sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table('batch_submissions')
    op.drop_column('records', 'voided_at')
