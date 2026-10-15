"""Promote the existing admin account and add recoverable new credentials."""
from alembic import op
import sqlalchemy as sa

revision = 'e10100'
down_revision = 'd9100'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('password_encrypted', sa.String(1024), nullable=True))
    op.execute("UPDATE users SET role = 'superadmin' WHERE username = 'admin'")


def downgrade():
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'superadmin'")
    op.drop_column('users', 'password_encrypted')
