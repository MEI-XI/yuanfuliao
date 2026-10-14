import pytest
from sqlalchemy.orm import Session

from app.models import History, Photo, RecognitionJob, Record
from conftest import bootstrap
from test_records import new_ledger


@pytest.mark.parametrize('resource', ['materials', 'schemes', 'partners', 'users', 'ledgers'])
def test_delete_requires_administrator_and_reports_missing_entries(client, resource):
    assert client.delete(f'/api/{resource}/999999').status_code == 401
    bootstrap(client)
    assert client.delete(f'/api/{resource}/999999').status_code == 404
    client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'})
    client.post('/api/login', json={'username': 'worker', 'password': 'worker-password'})
    assert client.delete(f'/api/{resource}/999999').status_code == 403


def test_deleting_shared_material_scheme_and_partner_preserves_record_snapshots(client):
    bootstrap(client)
    ledger = new_ledger(client)
    material = client.post('/api/materials', json={'name': '甘氨酸', 'model': '食品级'}).json()
    scheme = client.post('/api/schemes', json={'material_id': material['id'], 'name': '水分标准', 'items': [{'name': '水分', 'standard': '≤0.2%', 'unit': '%'}]}).json()
    partner = client.post('/api/partners', json={'name': '乙工厂', 'kind': 'manufacturer', 'address': '河北'}).json()
    record = client.post(f'/api/ledgers/{ledger}/records', json={
        'material_id': material['id'], 'scheme_id': scheme['id'],
        'fields': {'company_name': '乙工厂', 'address': '河北'},
        'report': {'basis': '食品检验规范', 'inspector': '检查员'},
    }).json()
    history = client.get(f'/api/records/{record["id"]}/history').json()
    assert client.delete(f'/api/materials/{material["id"]}').status_code == 204
    assert client.get('/api/materials').json() == []
    assert client.get('/api/schemes').json()[0]['material_id'] is None
    assert client.delete(f'/api/schemes/{scheme["id"]}').status_code == 204
    assert client.delete(f'/api/partners/{partner["id"]}').status_code == 204
    assert client.get('/api/schemes').json() == []
    assert client.get('/api/partners').json() == []
    current = client.get(f'/api/records/{record["id"]}').json()
    assert current == record | {'material_id': None}
    assert client.get(f'/api/records/{record["id"]}/history').json() == history


def test_delete_unused_account_removes_sessions_and_self_delete_is_rejected(client):
    admin = bootstrap(client)
    own = client.delete(f'/api/users/{admin["id"]}')
    assert own.status_code == 409
    assert '当前' in own.json()['detail']
    worker = client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'}).json()
    client.post('/api/login', json={'username': 'worker', 'password': 'worker-password'})
    worker_cookie = client.cookies.get('session')
    client.post('/api/login', json={'username': 'admin', 'password': 'test-password-123'})
    assert client.delete(f'/api/users/{worker["id"]}').status_code == 204
    assert [entry['username'] for entry in client.get('/api/users').json()] == ['admin']
    client.cookies.set('session', worker_cookie)
    assert client.get('/api/me').status_code == 401


@pytest.mark.parametrize('reference', ['creator', 'checker', 'history', 'photo', 'job'])
def test_delete_account_with_business_history_recommends_disabling(client, reference):
    admin = bootstrap(client)
    worker = client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'}).json()
    ledger = new_ledger(client)
    with Session(client.app.state.engine) as session:
        if reference in ['creator', 'checker', 'history']:
            record = Record(ledger_id=ledger, creator_id=worker['id'] if reference == 'creator' else admin['id'],
                            checker_id=worker['id'] if reference == 'checker' else None, fields={})
            session.add(record)
            session.flush()
            if reference == 'history':
                session.add(History(record_id=record.id, actor_id=worker['id'], action='edit', snapshot={}))
        elif reference == 'photo':
            session.add(Photo(ledger_id=ledger, owner_id=worker['id'], path='isolated.png', filename='label.png', media_type='image/png'))
        else:
            session.add(RecognitionJob(ledger_id=ledger, owner_id=worker['id'], image_ids=[], cloud_enabled=False))
        session.commit()
    response = client.delete(f'/api/users/{worker["id"]}')
    assert response.status_code == 409
    assert '停用' in response.json()['detail']
    assert worker in client.get('/api/users').json()


@pytest.mark.parametrize('reference', ['record', 'photo', 'job'])
def test_delete_nonempty_ledger_explains_why_and_preserves_data(client, reference):
    admin = bootstrap(client)
    ledger = new_ledger(client)
    with Session(client.app.state.engine) as session:
        if reference == 'record':
            session.add(Record(ledger_id=ledger, creator_id=admin['id'], fields={}, status='void'))
        elif reference == 'photo':
            session.add(Photo(ledger_id=ledger, owner_id=admin['id'], path='isolated.png', filename='label.png', media_type='image/png'))
        else:
            session.add(RecognitionJob(ledger_id=ledger, owner_id=admin['id'], image_ids=[], cloud_enabled=False))
        session.commit()
    response = client.delete(f'/api/ledgers/{ledger}')
    assert response.status_code == 409
    assert {'record': '记录', 'photo': '照片', 'job': '识别任务'}[reference] in response.json()['detail']
    assert client.get('/api/ledgers').json() == [{'id': ledger, 'name': '青山科技'}]


def test_delete_empty_ledger(client):
    bootstrap(client)
    ledger = new_ledger(client)
    assert client.delete(f'/api/ledgers/{ledger}').status_code == 204
    assert client.get('/api/ledgers').json() == []
