from datetime import timedelta
from pathlib import Path
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Photo, RecognitionJob, LoginSession, utcnow
from conftest import bootstrap
from test_records import new_ledger


def test_cleanup_retains_record_history_and_active_jobs_and_only_removes_old_abandoned_resources(client):
    user = bootstrap(client)
    ledger = new_ledger(client)
    root = Path(os.environ['DATA_DIR']) / 'images'
    root.mkdir(parents=True)
    now = utcnow()
    with Session(client.app.state.engine) as session:
        photos = []
        for name in ['abandoned', 'record', 'history', 'running', 'recent']:
            path = root / (name + '.png')
            path.write_bytes(b'fixture')
            photo = Photo(ledger_id=ledger, owner_id=user['id'], path='images/' + path.name,
                          filename=path.name, media_type='image/png', created_at=now - timedelta(days=31) if name != 'recent' else now)
            session.add(photo); session.flush(); photos.append(photo.id)
        job = RecognitionJob(ledger_id=ledger, owner_id=user['id'], image_ids=[photos[0]], cloud_enabled=False,
                             local_status='failed', cloud_status='disabled', created_at=now - timedelta(days=31))
        running = RecognitionJob(ledger_id=ledger, owner_id=user['id'], image_ids=[photos[3]], cloud_enabled=False,
                                 local_status='running', cloud_status='disabled', created_at=now - timedelta(days=31))
        session.add_all([job, running, LoginSession(token_hash='expired', user_id=user['id'], expires_at=now - timedelta(days=1))])
        session.commit(); job_id = job.id; running_id = running.id
    current = client.post(f'/api/ledgers/{ledger}/records', json={'image_ids': [photos[1]]}).json()
    historic = client.post(f'/api/ledgers/{ledger}/records', json={'image_ids': [photos[2]]}).json()
    response = client.patch(f'/api/records/{historic["id"]}', json={'version': historic['version'], 'image_ids': []})
    assert response.status_code == 200, response.text
    from app.resource_cleanup import clean_resources
    with Session(client.app.state.engine) as session:
        result = clean_resources(session, now=now)
        assert (root / 'abandoned.png').exists(), 'files must survive until commit'
        session.commit()
    assert result == {'sessions': 1, 'jobs': 1, 'photos': 1, 'orphan_files': 0, 'batch_receipts': 0}
    assert not (root / 'abandoned.png').exists()
    for name in ['record', 'history', 'running', 'recent']:
        assert (root / (name + '.png')).exists()
    with Session(client.app.state.engine) as session:
        assert session.get(RecognitionJob, job_id) is None
        assert session.get(RecognitionJob, running_id) is not None
        assert session.get(LoginSession, 'expired') is None
    assert client.get(f'/api/records/{current["id"]}').status_code == 200


def test_cleanup_rollback_retains_files_and_rejects_outside_path(client, tmp_path):
    user = bootstrap(client); ledger = new_ledger(client); now = utcnow()
    root = Path(os.environ['DATA_DIR']) / 'images'; root.mkdir(parents=True)
    inside = root / 'rollback.png'; inside.write_bytes(b'keep')
    outside = tmp_path / 'outside.png'; outside.write_bytes(b'outside')
    with Session(client.app.state.engine) as session:
        for path in [inside, outside]:
            session.add(Photo(ledger_id=ledger, owner_id=user['id'], path=str(path), filename=path.name,
                              media_type='image/png', created_at=now - timedelta(days=31)))
        session.commit()
    from app.resource_cleanup import clean_resources
    with Session(client.app.state.engine) as session:
        clean_resources(session, now=now)
        session.rollback()
    assert inside.read_bytes() == b'keep'
    with Session(client.app.state.engine) as session:
        clean_resources(session, now=now); session.commit()
    assert not inside.exists()
    assert outside.read_bytes() == b'outside'


def test_cleanup_preserves_history_job_and_recycled_photos_and_expires_only_old_orphan_files(client):
    from app.models import BatchSubmission, History, Record
    from app.resource_cleanup import clean_resources
    user = bootstrap(client); ledger = new_ledger(client); now = utcnow()
    data = Path(os.environ['DATA_DIR']); images = data / 'images'; reports = data / 'report-attachments'
    images.mkdir(parents=True); reports.mkdir(parents=True)
    for directory in [images, reports]:
        for name in ['old-orphan', 'recent-orphan']:
            path = directory / name; path.write_bytes(b'content')
            if name.startswith('old'):
                os.utime(path, (now.timestamp() - 31 * 86400, now.timestamp() - 31 * 86400))
    retained = images / 'history.png'; retained.write_bytes(b'history')
    with Session(client.app.state.engine) as session:
        photo = Photo(ledger_id=ledger, owner_id=user['id'], path='images/history.png', filename='history.png',
                      media_type='image/png', created_at=now - timedelta(days=40))
        session.add(photo); session.flush()
        job = RecognitionJob(ledger_id=ledger, owner_id=user['id'], image_ids=[photo.id], cloud_enabled=False,
                             local_status='done', cloud_status='disabled', created_at=now - timedelta(days=40))
        session.add(job); session.commit(); photo_id, job_id = photo.id, job.id
    record = client.post(f'/api/ledgers/{ledger}/records', json={'image_ids': [photo_id], 'recognition_job_id': job_id}).json()
    changed = client.patch(f'/api/records/{record["id"]}', json={'version': record['version'], 'image_ids': [], 'recognition_job_id': None}).json()
    response = client.post(f'/api/records/{record["id"]}/void', json={'version': changed['version']})
    assert response.status_code == 200
    with Session(client.app.state.engine) as session:
        session.add_all([
            BatchSubmission(id='removed', owner_id=user['id'], ledger_id=ledger, payload_hash='x', record_ids=[99999]),
            BatchSubmission(id='retained', owner_id=user['id'], ledger_id=ledger, payload_hash='x', record_ids=[record['id']]),
        ])
        session.commit()
        result = clean_resources(session, now=now); session.commit()
        assert result['jobs'] == result['photos'] == 0
        assert result['orphan_files'] == 2
        assert result['batch_receipts'] == 1
        assert session.get(RecognitionJob, job_id) is not None
        assert session.get(Photo, photo_id) is not None
        assert session.get(BatchSubmission, 'retained') is not None
    assert retained.exists()
    for directory in [images, reports]:
        assert not (directory / 'old-orphan').exists()
        assert (directory / 'recent-orphan').exists()
