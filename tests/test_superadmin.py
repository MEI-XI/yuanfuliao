from conftest import bootstrap
import pytest


@pytest.mark.parametrize('timing', ['startup', 'background'])
def test_audit_retention_removes_only_logs_older_than_thirty_days(client, monkeypatch, timing):
    from datetime import datetime, timedelta, timezone
    import time
    from fastapi.testclient import TestClient
    from sqlalchemy import update
    from sqlalchemy.orm import Session
    from app.models import AuditLog
    from app.main import create_app
    bootstrap(client)
    client.post('/api/ledgers', json={'name': '保留台账'})
    logs = client.get('/api/audit-logs').json()['items']
    expired, boundary = logs[0]['id'], logs[1]['id']
    now = datetime.now(timezone.utc)
    monkeypatch.setattr('app.models.utcnow', lambda: now)
    monkeypatch.setattr('app.recycle.CLEANUP_INTERVAL_SECONDS', 0.05)
    def age_logs():
        with Session(client.app.state.engine) as session:
            session.execute(update(AuditLog).where(AuditLog.id == expired).values(at=now - timedelta(days=30, microseconds=1)))
            session.execute(update(AuditLog).where(AuditLog.id == boundary).values(at=now - timedelta(days=30)))
            session.commit()
    if timing == 'startup':
        age_logs()
    with TestClient(create_app(client.app.state.engine.url)) as other:
        other.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
        if timing == 'background':
            age_logs()
        deadline = time.monotonic() + 3
        while True:
            ids = {row['id'] for row in other.get('/api/audit-logs').json()['items']}
            if expired not in ids or time.monotonic() >= deadline:
                break
            time.sleep(0.025)
        assert expired not in ids
        assert boundary in ids
        assert other.get('/api/ledgers').json()[0]['name'] == '保留台账'


def test_audit_batch_delete_requires_superadmin_and_preserves_unselected_logs(client):
    bootstrap(client)
    client.post('/api/users', json={'username': 'reader', 'password': 'reader-password'})
    client.post('/api/users', json={'username': 'manager', 'password': 'manager-password', 'role': 'admin'})
    before = client.get('/api/audit-logs').json()['items']
    ids = [row['id'] for row in before[:2]]
    for username, password in [('reader', 'reader-password'), ('manager', 'manager-password')]:
        client.post('/api/login', json={'username': username, 'password': password})
        assert client.post('/api/audit-logs/batch-delete', json={'ids': ids}).status_code == 403
    client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
    for invalid in [[], [ids[0], ids[0]], [-1], list(range(1, 202))]:
        assert client.post('/api/audit-logs/batch-delete', json={'ids': invalid}).status_code == 422
    assert client.post('/api/audit-logs/batch-delete', json={'ids': [ids[0], 999999]}).status_code == 409
    assert set(ids).issubset({row['id'] for row in client.get('/api/audit-logs').json()['items']})
    response = client.post('/api/audit-logs/batch-delete', json={'ids': ids})
    assert response.status_code == 204, response.text
    after = client.get('/api/audit-logs').json()['items']
    remaining = {row['id'] for row in after}
    assert not set(ids).intersection(remaining)
    assert {row['id'] for row in before[2:]}.issubset(remaining)
    deletion = next(row for row in after if row['action'] == '批量删除操作日志')
    assert deletion['details']['log_ids'] == ids
    assert deletion['details']['count'] == 2
    client.post('/api/logout')
    assert client.post('/api/audit-logs/batch-delete', json={'ids': ids}).status_code == 401


def test_audit_filters_apply_before_pagination_and_use_beijing_dates(client, monkeypatch):
    from datetime import datetime, timezone
    from app.models import AuditLog
    bootstrap(client)
    client.post('/api/users', json={'username': 'night-worker', 'password': 'worker-password'})
    client.post('/api/login', json={'username': 'night-worker', 'password': 'worker-password'})
    # Exactly the start and end of Oct 15 in Beijing, plus neighbouring days.
    stamps = iter([datetime(2026, 10, 14, 15, 59, 59, tzinfo=timezone.utc),
                   datetime(2026, 10, 14, 16, 0, 0, tzinfo=timezone.utc),
                   datetime(2026, 10, 15, 15, 59, 59, tzinfo=timezone.utc),
                   datetime(2026, 10, 15, 16, 0, 0, tzinfo=timezone.utc)])
    real_init = AuditLog.__init__
    def stamped_init(self, **kwargs):
        return real_init(self, **kwargs, at=next(stamps))
    with monkeypatch.context() as context:
        context.setattr(AuditLog, '__init__', stamped_init)
        for _ in range(4):
            client.post('/api/logout')
            # Reuse the existing authenticated cookie through a login that is
            # deliberately outside the timestamp stub in the next iteration.
            if _ < 3:
                context.setattr(AuditLog, '__init__', real_init)
                client.post('/api/login', json={'username': 'night-worker', 'password': 'worker-password'})
                context.setattr(AuditLog, '__init__', stamped_init)
    client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
    filters = {'actor': 'night-worker', 'action': '退出登录', 'target': 'logout',
               'from_date': '2026-10-15', 'to_date': '2026-10-15', 'page_size': 1}
    first = client.get('/api/audit-logs', params=filters).json()
    second = client.get('/api/audit-logs', params=filters | {'page': 2}).json()
    assert first['total'] == second['total'] == 2
    assert len(first['items']) == len(second['items']) == 1
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert all(row['actor_username'] == 'night-worker' and row['action'] == '退出登录' for row in first['items'] + second['items'])
    assert client.get('/api/audit-logs', params=filters | {'target': 'missing'}).json()['total'] == 0
    assert client.get('/api/audit-logs', params={'from_date': '2026-10-16', 'to_date': '2026-10-15'}).status_code == 422


def test_superadmin_manages_credentials_and_admin_cannot_escalate(client):
    root = bootstrap(client)
    admin = client.post('/api/users', json={'username': 'manager', 'password': 'manager-password', 'role': 'admin'}).json()
    worker = client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'}).json()
    assert client.patch(f'/api/users/{worker["id"]}', json={'username': 'renamed', 'password': 'reset-password'}).status_code == 200
    revealed = client.get(f'/api/users/{worker["id"]}/password')
    assert revealed.json() == {'password': 'reset-password'}
    assert revealed.headers['cache-control'] == 'no-store'
    assert 'password' not in client.get('/api/users').text
    assert client.post('/api/login', json={'username': 'renamed', 'password': 'reset-password'}).status_code == 200
    assert client.get(f'/api/users/{worker["id"]}/password').status_code == 403
    client.post('/api/login', json={'username': 'manager', 'password': 'manager-password'})
    assert client.patch(f'/api/users/{root["id"]}', json={'password': 'another-password'}).status_code == 403
    assert client.delete(f'/api/users/{root["id"]}').status_code == 403
    assert client.patch(f'/api/users/{worker["id"]}', json={'role': 'admin'}).status_code == 403
    assert client.post('/api/users', json={'username': 'other-admin', 'password': 'another-password', 'role': 'admin'}).status_code == 403
    assert client.get(f'/api/users/{worker["id"]}/password').status_code == 403
    assert client.post('/api/ledgers', json={'name': '管理员维护'}).status_code == 201


def test_audit_retains_actor_metadata_and_excludes_credentials(client):
    root = bootstrap(client)
    worker = client.post('/api/users', json={'username': 'worker', 'password': 'private-password'}).json()
    client.get(f'/api/users/{worker["id"]}/password')
    client.put('/api/settings/cloud', json={'api_key': 'private-api-key'})
    client.post('/api/logout')
    client.post('/api/login', json={'username': 'worker', 'password': 'private-password'})
    assert client.get('/api/audit-logs').status_code == 403
    client.post('/api/logout')
    client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
    assert client.delete(f'/api/users/{worker["id"]}').status_code == 204
    result = client.get('/api/audit-logs?page_size=100')
    assert result.status_code == 200
    entries = result.json()['items']
    assert {'登录', '退出登录', '查看密码', '创建账号', '删除账号', '更新云端设置'} <= {row['action'] for row in entries}
    assert any(row['actor_username'] == 'worker' and row['actor_id'] == worker['id'] for row in entries)
    assert all(row['at'] and row['target'] and 200 <= row['status_code'] < 300 for row in entries)
    assert 'private-password' not in result.text
    assert 'private-api-key' not in result.text
    assert 'test-password-123' not in result.text
    first = client.get('/api/audit-logs?page_size=2').json()
    second = client.get('/api/audit-logs?page=2&page_size=2').json()
    assert first['total'] == len(entries)
    assert len(first['items']) == 2
    assert {row['id'] for row in first['items']}.isdisjoint(row['id'] for row in second['items'])


def test_batch_void_validates_every_record_and_rolls_back_on_conflict(client):
    bootstrap(client)
    ledger = client.post('/api/ledgers', json={'name': '批量台账'}).json()['id']
    records = [client.post(f'/api/ledgers/{ledger}/records', json={'fields': {'material_name': name}}).json() for name in ['甲', '乙']]
    payload = {'records': [{'id': record['id'], 'version': record['version']} for record in records]}
    payload['records'][1]['version'] += 1
    assert client.post('/api/records/batch-void', json=payload).status_code == 409
    for record in records:
        assert client.get(f'/api/records/{record["id"]}').json() == record
    payload['records'][1]['version'] -= 1
    result = client.post('/api/records/batch-void', json=payload)
    assert result.status_code == 200
    assert [record['status'] for record in result.json()] == ['void', 'void']
    assert client.get(f'/api/ledgers/{ledger}/records').json() == []
    assert client.post('/api/records/batch-void', json=payload).status_code == 409
    logs = client.get('/api/audit-logs').json()['items']
    assert len([row for row in logs if row['action'] == '批量作废记录']) == 1
    client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'})
    client.post('/api/login', json={'username': 'worker', 'password': 'worker-password'})
    assert client.post('/api/records/batch-void', json=payload).status_code == 403


def test_exports_audit_selected_records_without_record_contents(client):
    bootstrap(client)
    ledger = client.post('/api/ledgers', json={'name': '导出台账'}).json()['id']
    record = client.post(f'/api/ledgers/{ledger}/records', json={'fields': {'notes': 'private-record-notes'}}).json()
    assert client.post('/api/exports/xlsx', json={'record_ids': [record['id']], 'include_pending': True}).status_code == 200
    result = client.get('/api/audit-logs')
    export = next(row for row in result.json()['items'] if row['action'] == '导出台账')
    assert export['details']['record_ids'] == [record['id']]
    assert 'private-record-notes' not in result.text


def test_root_can_rename_and_reset_own_password_and_old_session_is_revoked(client):
    root = bootstrap(client)
    response = client.patch(f'/api/users/{root["id"]}', json={'username': 'owner', 'password': 'new-root-password'})
    assert response.status_code == 200
    assert response.json()['role'] == 'superadmin'
    assert client.get('/api/me').status_code == 401
    assert client.post('/api/login', json={'username': 'owner', 'password': 'new-root-password'}).status_code == 200
    assert client.get(f'/api/users/{root["id"]}/password').json() == {'password': 'new-root-password'}
    assert client.delete(f'/api/users/{root["id"]}').status_code == 409


def test_batch_void_missing_and_duplicate_selection_does_not_change_records(client):
    bootstrap(client)
    ledger = client.post('/api/ledgers', json={'name': '异常选择台账'}).json()['id']
    record = client.post(f'/api/ledgers/{ledger}/records', json={}).json()
    entry = {'id': record['id'], 'version': record['version']}
    assert client.post('/api/records/batch-void', json={'records': [entry, {'id': 999999, 'version': 1}]}).status_code == 404
    assert client.post('/api/records/batch-void', json={'records': [entry, entry]}).status_code == 422
    assert client.get(f'/api/records/{record["id"]}').json() == record


def test_missing_reveal_key_does_not_replace_key_or_break_hash_login(client):
    import os
    from pathlib import Path

    root = bootstrap(client)
    key = Path(os.environ['DATA_DIR']) / 'credential.key'
    backup = key.with_suffix('.backup')
    key.rename(backup)
    assert client.get(f'/api/users/{root["id"]}/password').status_code == 503
    assert not key.exists()
    client.post('/api/logout')
    assert client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'}).status_code == 200
    backup.rename(key)
    assert client.get(f'/api/users/{root["id"]}/password').json() == {'password': 'test-password-123'}
