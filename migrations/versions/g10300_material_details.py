"""Store reusable material details and address/contact attribution."""
from alembic import op
import sqlalchemy as sa

revision = 'g10300'
down_revision = 'f10200'
branch_labels = None
depends_on = None


def upgrade():
    for name, length in [('specification', 500), ('company_name', 200),
                         ('address', 1000), ('contact', 500), ('shelf_life', 200),
                         ('address_source', 24), ('contact_source', 24)]:
        op.add_column('materials', sa.Column(name, sa.String(length), nullable=False, server_default=''))


def downgrade():
    for name in ['contact_source', 'address_source', 'shelf_life', 'contact',
                 'address', 'company_name', 'specification']:
        op.drop_column('materials', name)
