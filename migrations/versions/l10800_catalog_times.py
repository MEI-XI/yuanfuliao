"""Record catalog creation and last modification times without inventing history."""
from alembic import op
import sqlalchemy as sa

revision = 'l10800'
down_revision = 'k10700'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('materials', 'schemes'):
        op.add_column(table, sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for table in ('materials', 'schemes'):
        op.drop_column(table, 'updated_at')
        op.drop_column(table, 'created_at')
