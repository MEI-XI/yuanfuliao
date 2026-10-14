"""Allow inspection schemes without a material binding."""
from alembic import op
import sqlalchemy as sa

revision = 'b7100'
down_revision = 'a6140'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('schemes', 'material_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Unbound schemes cannot be represented by the old schema. Fail rather than delete them.
    op.alter_column('schemes', 'material_id', existing_type=sa.Integer(), nullable=False)
