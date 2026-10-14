"""Recycle-bin retention, restoration, and server-owned cleanup."""
import logging
from datetime import timedelta
from threading import Event, Thread

from fastapi import Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.models import History, Record, User
from app.schemas import VersionInput


logger = logging.getLogger(__name__)
RETENTION = timedelta(days=30)
CLEANUP_INTERVAL_SECONDS = 3600


def record_expired(item, now=None):
    return (item.status == 'void' and item.voided_at is not None
            and item.voided_at < (now or models.utcnow()) - RETENTION)


def delete_records(session, record_ids):
    session.execute(delete(History).where(History.record_id.in_(record_ids)))
    session.execute(delete(Record).where(Record.id.in_(record_ids)))


def purge_expired_records(session, now=None):
    """Delete expired records within the caller's transaction, with row locks."""
    cutoff = (now or models.utcnow()) - RETENTION
    record_ids = list(session.scalars(
        select(Record.id).where(Record.status == 'void', Record.voided_at < cutoff)
        .order_by(Record.id).with_for_update()
    ))
    if record_ids:
        delete_records(session, record_ids)
    return len(record_ids)


class RecycleCleaner:
    def __init__(self, engine):
        self.engine = engine
        self.stop_event = Event()
        self.thread = Thread(target=self.run, name='recycle-cleanup', daemon=True)

    def clean(self):
        with Session(self.engine) as session:
            purge_expired_records(session)
            session.commit()

    def start(self):
        self.clean()
        self.thread.start()

    def run(self):
        while not self.stop_event.wait(CLEANUP_INTERVAL_SECONDS):
            try:
                self.clean()
            except Exception:
                logger.exception('Recycle-bin cleanup failed; retrying next cycle')

    def stop(self):
        self.stop_event.set()
        self.thread.join()


def register_recycle_routes(app, db, current_user, administrator, record_view, append_history):
    @app.get('/api/recycle-bin')
    def recycle_bin(ledger_id: int | None = None, user: User = Depends(current_user), session: Session = Depends(db)):
        purge_expired_records(session)
        session.commit()
        query = select(Record).where(Record.status == 'void')
        if ledger_id is not None:
            query = query.where(Record.ledger_id == ledger_id)
        return [record_view(item) for item in session.scalars(query.order_by(Record.voided_at.desc(), Record.id.desc()))]

    @app.post('/api/records/{record_id}/restore')
    def restore_record(record_id: int, body: VersionInput, user: User = Depends(administrator), session: Session = Depends(db)):
        item = session.scalar(select(Record).where(Record.id == record_id).with_for_update())
        if item is None:
            raise HTTPException(404, '记录不存在')
        now = models.utcnow()
        if record_expired(item, now):
            delete_records(session, [item.id])
            session.commit()
            raise HTTPException(404, '记录不存在')
        if item.status != 'void':
            raise HTTPException(409, '只有回收站中的记录可以恢复')
        if item.version != body.version:
            raise HTTPException(409, '记录已被修改，请重新打开后核对')
        item.status, item.checker_id, item.checked_at, item.voided_at = 'pending', None, None, None
        item.version += 1
        item.updated_at = now
        append_history(item, user, 'restored', session)
        session.commit()
        return record_view(item)
