"""Keep reusable inspection results and conclusions."""
from alembic import op
import sqlalchemy as sa

revision = 'k10700'
down_revision = 'j10600'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('inspection_options',
                    sa.Column('kind', sa.String(20), primary_key=True),
                    sa.Column('key', sa.String(64), primary_key=True),
                    sa.Column('name', sa.Text(), nullable=False),
                    sa.Column('hidden', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_table('inspection_options')
