"""Remember the auxiliary thinking mode selected for each recognition job."""
from alembic import op
import sqlalchemy as sa

revision = 'm10900'
down_revision = 'l10800'
branch_labels = None
depends_on = None


def upgrade():
    # Existing jobs used the former provider; NULL preserves that history.
    # Newly submitted jobs explicitly store the selected mode (default disabled).
    op.add_column('recognition_jobs', sa.Column('cloud_thinking', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('recognition_jobs', 'cloud_thinking')
