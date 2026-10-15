import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine

from app.models import Base
from app.report_attachments import ReportAttachment  # Register attachment metadata.

config = context.config
load_dotenv()


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=os.environ['DATABASE_URL'], target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get('connection') is not None:
    run(config.attributes['connection'])
else:
    with create_engine(os.environ['DATABASE_URL']).connect() as connection:
        run(connection)
