"""Link saved records to original recognition evidence."""
from alembic import op
import sqlalchemy as sa

revision = 'a6140'
down_revision = '5d81f3388440'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('records', sa.Column('recognition_job_id', sa.Integer(), nullable=True))
    op.create_foreign_key('records_recognition_job_fk', 'records', 'recognition_jobs', ['recognition_job_id'], ['id'])


def downgrade():
    op.drop_constraint('records_recognition_job_fk', 'records', type_='foreignkey')
    op.drop_column('records', 'recognition_job_id')
