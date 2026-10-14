"""Keep existing report capability; new records default to no inspection."""
from alembic import op
import sqlalchemy as sa

revision = 'c8100'
down_revision = 'b7100'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('records', sa.Column('inspection_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('records', 'inspection_enabled', server_default=sa.false())


def downgrade():
    op.drop_column('records', 'inspection_enabled')
