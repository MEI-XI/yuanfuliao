from conftest import bootstrap
import pytest
from concurrent.futures import ThreadPoolExecutor


def test_same_name_replaces_scheme_in_place_and_preserves_record_snapshot(client):
    bootstrap(client)
    original = {'name': '含量标准', 'items': [{'name': '含量', 'standard': '≥98%'}]}
    first = client.post('/api/schemes', json=original).json()
    ledger = client.post('/api/ledgers', json={'name': '方案替换测试'}).json()['id']
    record = client.post(f'/api/ledgers/{ledger}/records', json={
        'scheme_id': first['id'], 'inspection_enabled': True,
    }).json()
    response = client.post('/api/schemes', json=original | {'items': [{'name': '含量', 'standard': '≥99%'}]})
    assert response.status_code == 200, response.text
    replaced = response.json()
    assert replaced['id'] == first['id']
    assert replaced['created_at'] == first['created_at']
    assert replaced['updated_at'] > first['updated_at']
    assert replaced['save_action'] == 'replaced'
    schemes = client.get('/api/schemes').json()
    assert len(schemes) == 1 and schemes[0]['items'][0]['standard'] == '≥99%'
    assert client.get(f'/api/records/{record["id"]}').json()['items'][0]['standard'] == '≥98%'
    logs = client.get('/api/audit-logs').json()['items']
    assert logs[0]['action'] == '修改检验方案'
    assert '含量标准' in logs[0]['description']


@pytest.mark.parametrize('method', ['POST', 'PUT'])
def test_identical_scheme_is_reported_without_changing_saved_content(client, method):
    bootstrap(client)
    body = {'name': '检测方案A', 'items': [{'name': ' 水分 ', 'standard': ' ≤1% '}]}
    original = client.post('/api/schemes', json=body).json()
    route = '/api/schemes' if method == 'POST' else f'/api/schemes/{original["id"]}'
    response = client.request(method, route, json=body | {'name': ' 检测方案a '})
    assert response.status_code == 409
    assert '已经有同样' in response.json()['detail']
    saved = client.get('/api/schemes').json()
    assert len(saved) == 1
    assert saved[0]['updated_at'] == original['updated_at']
    assert saved[0]['name'] == original['name']


def test_editing_into_existing_name_replaces_target_without_deleting_source(client):
    bootstrap(client)
    target = client.post('/api/schemes', json={'name': '目标方案', 'items': [{'name': '水分', 'standard': '≤1%'}]}).json()
    source = client.post('/api/schemes', json={'name': '原方案'}).json()
    body = {'name': '目标方案', 'items': [{'name': '水分', 'standard': '≤2%'}]}
    changed = client.put(f'/api/schemes/{source["id"]}', json=body)
    assert changed.status_code == 200
    assert changed.json()['id'] == target['id']
    assert changed.json()['save_action'] == 'replaced'
    rows = {row['id']: row for row in client.get('/api/schemes').json()}
    assert rows[source['id']]['name'] == '原方案'
    assert rows[target['id']]['items'][0]['standard'] == '≤2%'
    assert client.put('/api/schemes/999999', json=body).status_code == 404


def test_simultaneous_identical_scheme_saves_only_keep_one(client):
    bootstrap(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post('/api/schemes', json={
            'name': '并发方案', 'items': [{'name': '外观', 'standard': '无异物'}],
        }).status_code, range(2)))
    assert sorted(responses) == [201, 409]
    assert len(client.get('/api/schemes').json()) == 1
