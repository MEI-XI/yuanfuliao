"""Give uploaded photos and recognition jobs a safe retention clock."""
from alembic import op
import sqlalchemy as sa

revision = 'n11000'
down_revision = 'm10900'
branch_labels = None
depends_on = None


def upgrade():
    # Historical creation times are unknown. Begin their grace period now,
    # never infer age from a filename or remove existing resources immediately.
    for table in ('photos', 'recognition_jobs'):
        op.add_column(table, sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
        op.create_index(f'ix_{table}_created_at', table, ['created_at'])
        op.alter_column(table, 'created_at', server_default=None)


def downgrade():
    for table in ('photos', 'recognition_jobs'):
        op.drop_index(f'ix_{table}_created_at', table_name=table)
        op.drop_column(table, 'created_at')
