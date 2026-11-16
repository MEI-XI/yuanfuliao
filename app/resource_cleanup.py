"""Bounded, reference-aware retention for abandoned uploads and recognition work."""
import logging
import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, event, select, text
from sqlalchemy.orm import Session

from app.models import BatchSubmission, History, LoginSession, Photo, RecognitionJob, Record, utcnow
from app.report_attachments import ReportAttachment

logger = logging.getLogger(__name__)
RESOURCE_RETENTION = timedelta(days=30)
RESOURCE_LOCK = 814017
MAX_REMOVALS = 1000


def protect_resource_references(session):
    """Hold through commit when validating photos/jobs for a new reference."""
    session.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'), {'key': RESOURCE_LOCK})


def safe_file(path, root):
    """Only direct files of our managed folder; never follow links/junctions."""
    path, root = Path(path).absolute(), Path(root).absolute()
    if path.parent != root or root.is_symlink() or path.is_symlink():
        return None
    if any(part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()) for part in (root, *root.parents, path)):
        return None
    if path.resolve().parent != root.resolve():
        return None
    return path


def schedule_file(session, path, root):
    candidate = safe_file(path, root)
    if candidate is not None:
        session.info.setdefault('deleted_resource_files', set()).add((candidate, Path(root).absolute()))


@event.listens_for(Session, 'after_commit')
def remove_resource_files(session):
    for path, root in session.info.pop('deleted_resource_files', ()):
        candidate = safe_file(path, root)
        if candidate is not None:
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                logger.exception('Could not remove abandoned resource %s', path.name)


@event.listens_for(Session, 'after_rollback')
def retain_resource_files(session):
    session.info.pop('deleted_resource_files', None)


def clean_resources(session, now=None):
    """Caller owns commit. Referenced data and active jobs are always retained."""
    now = now or utcnow()
    cutoff = now - RESOURCE_RETENTION
    session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': RESOURCE_LOCK})
    result = {'sessions': 0, 'jobs': 0, 'photos': 0, 'orphan_files': 0, 'batch_receipts': 0}
    result['sessions'] = session.execute(delete(LoginSession).where(LoginSession.expires_at < now)).rowcount
    protected_jobs, protected_photos, record_ids = set(), set(), set()
    for record in session.execute(select(Record.id, Record.image_ids, Record.recognition_job_id).execution_options(yield_per=500)):
        record_ids.add(record.id)
        protected_photos.update(record.image_ids or [])
        if record.recognition_job_id is not None:
            protected_jobs.add(record.recognition_job_id)
    for snapshot in session.scalars(select(History.snapshot).execution_options(yield_per=500)):
        protected_photos.update(snapshot.get('image_ids') or [])
        if snapshot.get('recognition_job_id') is not None:
            protected_jobs.add(snapshot['recognition_job_id'])
    candidates = select(RecognitionJob).where(RecognitionJob.created_at < cutoff,
        RecognitionJob.local_status.in_(['done', 'failed']), RecognitionJob.cloud_status.in_(['done', 'failed', 'disabled'])).order_by(RecognitionJob.id)
    for job in session.scalars(candidates.execution_options(yield_per=500)):
        if job.id not in protected_jobs:
            session.delete(job)
            result['jobs'] += 1
            if result['jobs'] >= MAX_REMOVALS:
                break
    session.flush()
    for image_ids in session.scalars(select(RecognitionJob.image_ids).execution_options(yield_per=500)):
        protected_photos.update(image_ids or [])
    data = Path(os.getenv('DATA_DIR', 'data')).absolute()
    root = data / 'images'
    for photo in session.scalars(select(Photo).where(Photo.created_at < cutoff).order_by(Photo.id).execution_options(yield_per=500)):
        if photo.id not in protected_photos:
            path = Path(photo.path)
            if not path.is_absolute():
                path = data / path
            session.delete(photo)
            session.flush()
            if session.scalar(select(Photo.id).where(Photo.path == photo.path).limit(1)) is None:
                schedule_file(session, path, root)
            result['photos'] += 1
            if result['photos'] >= MAX_REMOVALS:
                break
    session.flush()
    # Old failed writes and failed post-commit unlinks can leave files without rows.
    photo_paths = set()
    for stored in session.scalars(select(Photo.path)):
        path = Path(stored)
        photo_paths.add((path if path.is_absolute() else data / path).absolute())
    report_paths = {data / 'report-attachments' / key for key in session.scalars(select(ReportAttachment.storage_key))}
    queued = {path for path, _ in session.info.get('deleted_resource_files', ())}
    for directory, referenced in [(root, photo_paths), (data / 'report-attachments', report_paths)]:
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.iterdir():
            if result['orphan_files'] >= MAX_REMOVALS:
                break
            if path in referenced or path in queued or safe_file(path, directory) is None:
                continue
            try:
                if path.is_file() and path.stat().st_mtime < cutoff.timestamp():
                    schedule_file(session, path, directory)
                    result['orphan_files'] += 1
            except OSError:
                logger.warning('Could not inspect orphan candidate %s', path.name)
    for receipt in session.scalars(select(BatchSubmission).execution_options(yield_per=500)):
        if receipt.record_ids and not any(record_id in record_ids for record_id in receipt.record_ids):
            session.delete(receipt)
            result['batch_receipts'] += 1
            if result['batch_receipts'] >= MAX_REMOVALS:
                break
    return result
