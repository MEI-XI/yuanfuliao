"""Remember custom accompanying certificates independently of records."""
from alembic import op
import sqlalchemy as sa

revision = 'i10500'
down_revision = 'h10400'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('certificate_options',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False))


def downgrade():
    op.drop_table('certificate_options')
