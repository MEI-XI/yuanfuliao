"""Recycle-bin retention, restoration, and server-owned cleanup."""
import logging
from datetime import timedelta
from threading import Event, Thread

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app import models
from app.models import History, Record, User
from app.schemas import BatchRecordSelection, VersionInput


logger = logging.getLogger(__name__)
RETENTION = timedelta(days=30)
CLEANUP_INTERVAL_SECONDS = 3600


def record_expired(item, now=None):
    return (item.status == 'void' and item.voided_at is not None
            and item.voided_at < (now or models.utcnow()) - RETENTION)


def delete_records(session, record_ids):
    from app.report_attachments import ReportAttachment, report_attachment_path
    keys = session.scalars(select(ReportAttachment.storage_key).where(ReportAttachment.record_id.in_(record_ids)))
    session.info.setdefault('deleted_report_files', set()).update(report_attachment_path(key) for key in keys)
    session.execute(delete(History).where(History.record_id.in_(record_ids)))
    session.execute(delete(Record).where(Record.id.in_(record_ids)))


@event.listens_for(Session, 'after_commit')
def remove_deleted_report_files(session):
    for path in session.info.pop('deleted_report_files', ()):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception('Could not remove expired report file %s', path.name)


@event.listens_for(Session, 'after_rollback')
def retain_rolled_back_report_files(session):
    session.info.pop('deleted_report_files', None)


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
        from app.audit import purge_expired_audit_logs
        with Session(self.engine) as session:
            purge_expired_records(session)
            purge_expired_audit_logs(session)
            session.commit()

    def start(self):
        self.clean()
        self.thread.start()

    def run(self):
        while not self.stop_event.wait(CLEANUP_INTERVAL_SECONDS):
            try:
                self.clean()
            except Exception:
                logger.exception('Record and audit retention cleanup failed; retrying next cycle')

    def stop(self):
        self.stop_event.set()
        self.thread.join()


def register_recycle_routes(app, db, current_user, administrator, record_view, append_history):
    def selected_recycled_records(body, session):
        versions = {entry.id: entry.version for entry in body.records}
        rows = list(session.scalars(select(Record).where(Record.id.in_(versions)).order_by(Record.id).with_for_update()))
        if len(rows) != len(versions) or any(record_expired(row) for row in rows):
            raise HTTPException(404, '所选记录已被删除或超过保留期限，请刷新列表后重新选择')
        for row in rows:
            if row.status != 'void' or row.version != versions[row.id]:
                raise HTTPException(409, f'记录 #{row.id} 已被修改或还原，本次未处理任何记录，请刷新列表后重新选择')
        return rows

    @app.post('/api/recycle-bin/batch-restore')
    def batch_restore_records(body: BatchRecordSelection, request: Request,
                              user: User = Depends(administrator), session: Session = Depends(db)):
        rows = selected_recycled_records(body, session)
        now = models.utcnow()
        for item in rows:
            item.status, item.checker_id, item.checked_at, item.voided_at = 'pending', None, None, None
            item.version += 1
            item.updated_at = now
            append_history(item, user, 'restored', session)
        session.commit()
        request.state.audit_details = {'record_ids': [row.id for row in rows]}
        by_id = {row.id: row for row in rows}
        return [record_view(by_id[entry.id]) for entry in body.records]

    @app.post('/api/recycle-bin/batch-delete', status_code=204)
    def batch_delete_recycled_records(body: BatchRecordSelection, request: Request,
                                      user: User = Depends(administrator), session: Session = Depends(db)):
        rows = selected_recycled_records(body, session)
        ids = [row.id for row in rows]
        delete_records(session, ids)
        session.commit()
        request.state.audit_details = {'record_ids': ids, 'count': len(ids)}

    @app.delete('/api/recycle-bin/{record_id}', status_code=204)
    def delete_recycled_record(record_id: int, request: Request, version: int = Query(..., ge=1),
                               user: User = Depends(administrator), session: Session = Depends(db)):
        item = session.scalar(select(Record).where(Record.id == record_id).with_for_update())
        if item is None:
            raise HTTPException(404, '记录不存在')
        if item.status != 'void':
            raise HTTPException(409, '只有回收站中的记录可以永久删除')
        if item.version != version:
            raise HTTPException(409, '记录已被修改，请刷新后重试')
        request.state.audit_details = {'record_id': item.id, 'ledger_id': item.ledger_id,
                                       'material_name': item.fields.get('material_name', '')}
        delete_records(session, [item.id])
        session.commit()

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
