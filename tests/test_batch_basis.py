from uuid import uuid4

from conftest import bootstrap
from test_records import new_ledger


def test_basis_defaults_to_scheme_name_and_keeps_manual_or_explicit_blank(client):
    bootstrap(client)
    ledger = new_ledger(client)
    first = client.post('/api/schemes', json={'name': '外观标准'}).json()
    second = client.post('/api/schemes', json={'name': '水分标准'}).json()
    record = client.post(f'/api/ledgers/{ledger}/records', json={
        'inspection_enabled': True, 'scheme_id': first['id'],
    }).json()
    assert record['report']['basis'] == '外观标准'
    changed = client.patch(f'/api/records/{record["id"]}', json={
        'version': record['version'], 'scheme_id': second['id'],
    }).json()
    assert changed['report']['basis'] == '水分标准'
    custom = client.patch(f'/api/records/{record["id"]}', json={
        'version': changed['version'], 'report': {'basis': '人工依据'},
    }).json()
    changed = client.patch(f'/api/records/{record["id"]}', json={
        'version': custom['version'], 'scheme_id': first['id'],
    }).json()
    assert changed['report']['basis'] == '人工依据'
    blank = client.post(f'/api/ledgers/{ledger}/records', json={
        'inspection_enabled': True, 'scheme_id': first['id'], 'report': {'basis': ''},
    }).json()
    assert blank['report']['basis'] == ''


def test_batch_save_is_atomic_and_retry_does_not_duplicate_checked_records(client):
    admin = bootstrap(client)
    ledger = new_ledger(client)
    body = {'request_id': str(uuid4()), 'mark_checked': True, 'records': [
        {'fields': {'material_name': '第一组'}},
        {'inspection_enabled': True, 'fields': {'material_name': '第二组'}},
    ]}
    failed = body | {'records': [body['records'][0], {'material_id': 999999}]}
    assert client.post(f'/api/ledgers/{ledger}/records/batch', json=failed).status_code == 422
    assert client.get(f'/api/ledgers/{ledger}/records').json() == []
    saved = client.post(f'/api/ledgers/{ledger}/records/batch', json=body)
    assert saved.status_code == 201
    records = saved.json()
    assert [r['fields']['material_name'] for r in records] == ['第一组', '第二组']
    assert all(r['status'] == 'checked' and r['checker_id'] == admin['id'] for r in records)
    retry = client.post(f'/api/ledgers/{ledger}/records/batch', json=body)
    assert [r['id'] for r in retry.json()] == [r['id'] for r in records]
    assert len(client.get(f'/api/ledgers/{ledger}/records').json()) == 2
    mismatch = client.post(f'/api/ledgers/{ledger}/records/batch', json=body | {'mark_checked': False})
    assert mismatch.status_code == 409
    pending = client.post(f'/api/ledgers/{ledger}/records/batch', json={
        'request_id': str(uuid4()), 'records': [{'fields': {'material_name': '未核对组'}}],
    }).json()
    assert pending[0]['status'] == 'pending' and pending[0]['checker_id'] is None
