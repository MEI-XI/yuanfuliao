"""Allow removal of history choices without changing saved records."""
from alembic import op
import sqlalchemy as sa

revision = 'j10600'
down_revision = 'i10500'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('certificate_options', sa.Column('hidden', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('certificate_options', 'hidden')
