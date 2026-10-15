from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
import pytest
import time

from app.main import create_app
from app.models import Record
from conftest import bootstrap
from test_records import new_ledger
from test_recognition import run_label


def create_record(client, ledger, **body):
    response = client.post(f'/api/ledgers/{ledger}/records', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def void_record(client, record):
    response = client.post(f'/api/records/{record["id"]}/void', json={'version': record['version']})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('role', ['admin', 'superadmin'])
def test_permanent_delete_requires_admin_current_version_and_void_record(client, role):
    bootstrap(client)
    ledger = new_ledger(client)
    active = create_record(client, ledger)
    recycled = void_record(client, create_record(client, ledger))
    path = f'/api/recycle-bin/{recycled["id"]}'
    client.post('/api/users', json={'username': 'reader', 'password': 'reader-password'})
    client.post('/api/users', json={'username': 'manager', 'password': 'manager-password', 'role': 'admin'})
    client.post('/api/login', json={'username': 'reader', 'password': 'reader-password'})
    assert client.delete(path, params={'version': recycled['version']}).status_code == 403
    username, password = ('manager', 'manager-password') if role == 'admin' else ('admin', 'test-password-123')
    client.post('/api/login', json={'username': username, 'password': password})
    assert client.delete(f'/api/recycle-bin/{active["id"]}', params={'version': active['version']}).status_code == 409
    assert client.delete(path, params={'version': recycled['version'] - 1}).status_code == 409
    assert client.delete(path, params={'version': recycled['version']}).status_code == 204
    assert client.get(f'/api/records/{recycled["id"]}').status_code == 404
    assert client.get(f'/api/records/{active["id"]}').status_code == 200
    client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
    audit = client.get('/api/audit-logs').json()['items']
    assert any(row['action'] == '永久删除记录' and row['details']['record_id'] == recycled['id'] for row in audit)


def test_void_records_only_appear_in_recycle_bin_with_company_filter(client):
    bootstrap(client)
    first = new_ledger(client)
    second = new_ledger(client, '第二公司')
    active = create_record(client, first)
    first_void = void_record(client, create_record(client, first))
    second_void = void_record(client, create_record(client, second))
    response = client.get('/api/recycle-bin')
    assert response.status_code == 200, response.text
    assert {row['id'] for row in response.json()} == {first_void['id'], second_void['id']}
    assert [row['id'] for row in client.get('/api/recycle-bin', params={'ledger_id': first}).json()] == [first_void['id']]
    assert [row['id'] for row in client.get('/api/records').json()] == [active['id']]
    assert [row['id'] for row in client.get(f'/api/ledgers/{first}/records').json()] == [active['id']]
    assert first_void['voided_at'] is not None


def test_restoration_requires_admin_and_current_version_and_preserves_content(client):
    admin = bootstrap(client)
    ledger = new_ledger(client)
    job = run_label(client, ledger, ['品名：甘氨酸'])
    original = create_record(client, ledger, inspection_enabled=True,
                             recognition_job_id=job['id'], image_ids=job['image_ids'],
                             fields={'material_name': '甘氨酸', 'notes': '保留内容'},
                             items=[{'name': '含量', 'result': '99.8', 'conclusion': '合格'}],
                             report={'conclusion': '合格'})
    path = f'/api/records/{original["id"]}'
    checked = client.post(path + '/check', json={'version': original['version']}).json()
    voided = void_record(client, checked)
    client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'})
    client.post('/api/login', json={'username': 'worker', 'password': 'worker-password'})
    assert client.get('/api/recycle-bin').status_code == 200
    assert client.post(path + '/restore', json={'version': voided['version']}).status_code == 403
    client.post('/api/logout')
    assert client.get('/api/recycle-bin').status_code == 401
    assert client.post(path + '/restore', json={'version': voided['version']}).status_code == 401
    client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
    assert client.post(path + '/restore', json={'version': original['version']}).status_code == 409
    response = client.post(path + '/restore', json={'version': voided['version']})
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored['status'] == 'pending'
    assert restored['version'] == voided['version'] + 1
    assert restored['voided_at'] is None
    assert restored['checker_id'] is None
    assert restored['checked_at'] is None
    for key in ('fields', 'items', 'report', 'inspection_enabled', 'creator_id', 'created_at', 'image_ids', 'recognition_job_id'):
        assert restored[key] == original[key]
    assert client.get('/api/recycle-bin').json() == []
    assert client.get('/api/records').json() == [restored]
    history = client.get(path + '/history').json()
    assert [row['action'] for row in history] == ['created', 'checked', 'voided', 'restored']
    assert history[-1]['actor_id'] == admin['id']
    assert history[-1]['snapshot']['status'] == 'pending'
    assert client.post(path + '/restore', json={'version': restored['version']}).status_code == 409


def test_purge_keeps_shared_images_and_recognition_jobs(client):
    bootstrap(client)
    ledger = new_ledger(client)
    job = run_label(client, ledger, ['品名：甘氨酸'])
    links = {'recognition_job_id': job['id'], 'image_ids': job['image_ids']}
    active = create_record(client, ledger, **links)
    expired = void_record(client, create_record(client, ledger, **links))
    set_void_time(client, expired, datetime.now(timezone.utc) - timedelta(days=31))
    response = client.get('/api/recycle-bin')
    assert response.status_code == 200, response.text
    assert response.json() == []
    assert client.get(f'/api/records/{expired["id"]}').status_code == 404
    assert client.get(f'/api/records/{active["id"]}').json()['image_ids'] == job['image_ids']
    assert client.get(f'/api/recognition/{job["id"]}').status_code == 200
    assert client.get(f'/api/images/{job["image_ids"][0]}').status_code == 200


def set_void_time(client, record, when):
    with Session(client.app.state.engine) as session:
        session.execute(update(Record).where(Record.id == record['id']).values(voided_at=when))
        session.commit()


def test_retention_uses_void_time_and_keeps_exact_thirty_day_boundary(client, monkeypatch):
    bootstrap(client)
    ledger = new_ledger(client)
    active = create_record(client, ledger)
    boundary = void_record(client, create_record(client, ledger))
    expired = void_record(client, create_record(client, ledger))
    now = datetime.now(timezone.utc)
    monkeypatch.setattr('app.models.utcnow', lambda: now)
    set_void_time(client, boundary, now - timedelta(days=30))
    set_void_time(client, expired, now - timedelta(days=30, microseconds=1))
    # Even old active data must survive retention.
    with Session(client.app.state.engine) as session:
        session.execute(update(Record).where(Record.id == active['id']).values(updated_at=now - timedelta(days=100)))
        session.commit()
    response = client.get('/api/recycle-bin')
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == [boundary['id']]
    assert client.get(f'/api/records/{active["id"]}').status_code == 200
    assert client.get(f'/api/records/{expired["id"]}').status_code == 404
    assert client.get(f'/api/records/{expired["id"]}/history').status_code == 404
    assert client.post(f'/api/records/{boundary["id"]}/restore', json={'version': boundary['version']}).status_code == 200


@pytest.mark.parametrize('operation', ['read', 'history', 'restore', 'edit', 'check'])
def test_expired_record_is_unavailable_before_next_cleanup_cycle(client, operation):
    bootstrap(client)
    ledger = new_ledger(client)
    record = void_record(client, create_record(client, ledger))
    set_void_time(client, record, datetime.now(timezone.utc) - timedelta(days=31))
    path = f'/api/records/{record["id"]}'
    if operation == 'read':
        response = client.get(path)
    elif operation == 'history':
        response = client.get(path + '/history')
    elif operation == 'edit':
        response = client.patch(path, json={'version': record['version'], 'fields': {'notes': '过期'}})
    else:
        response = client.post(path + '/' + operation, json={'version': record['version']})
    assert response.status_code == 404, response.text


def test_startup_purges_expired_records_and_their_history_without_browser_visit(client):
    bootstrap(client)
    ledger = new_ledger(client)
    record = void_record(client, create_record(client, ledger))
    set_void_time(client, record, datetime.now(timezone.utc) - timedelta(days=31))
    restarted = create_app(client.app.state.engine.url)
    with TestClient(restarted) as other:
        other.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
        # Deleting the now-empty ledger proves actual record deletion, not a filtered GET.
        assert other.delete(f'/api/ledgers/{ledger}').status_code == 204


def test_background_cleanup_removes_expired_records_without_recycle_request(client, monkeypatch):
    bootstrap(client)
    ledger = new_ledger(client)
    record = void_record(client, create_record(client, ledger))
    monkeypatch.setattr('app.recycle.CLEANUP_INTERVAL_SECONDS', 0.05)
    restarted = create_app(client.app.state.engine.url)
    with TestClient(restarted) as other:
        other.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
        set_void_time(client, record, datetime.now(timezone.utc) - timedelta(days=31))
        deadline = time.monotonic() + 3
        response = other.delete(f'/api/ledgers/{ledger}')
        while response.status_code == 409 and time.monotonic() < deadline:
            time.sleep(0.025)
            response = other.delete(f'/api/ledgers/{ledger}')
        assert response.status_code == 204, response.text
