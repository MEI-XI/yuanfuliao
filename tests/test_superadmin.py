from conftest import bootstrap


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
