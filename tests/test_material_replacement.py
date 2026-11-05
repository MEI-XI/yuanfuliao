import pytest
from conftest import bootstrap


def test_same_name_material_replaces_details_preserving_id_links_and_saved_record(client):
    bootstrap(client)
    first = client.post('/api/materials', json={'name': '测试原料', 'specification': '25kg', 'packaging': '纸袋'}).json()
    scheme = client.post('/api/schemes', json={'name': '原料标准', 'material_id': first['id']}).json()
    ledger = client.post('/api/ledgers', json={'name': '物料替换测试'}).json()['id']
    record = client.post(f'/api/ledgers/{ledger}/records', json={'material_id': first['id'], 'fields': {'material_name': '测试原料', 'specification': '25kg'}}).json()
    changed = client.post('/api/materials', json={'name': '测试原料', 'specification': '20kg', 'packaging': '塑料袋'})
    assert changed.status_code == 200, changed.text
    saved = changed.json()
    assert saved['id'] == first['id'] and saved['created_at'] == first['created_at']
    assert saved['updated_at'] > first['updated_at']
    assert saved['save_action'] == 'replaced'
    assert len(client.get('/api/materials').json()) == 1
    assert client.get('/api/schemes').json()[0]['material_id'] == scheme['material_id']
    assert client.get(f'/api/records/{record["id"]}').json()['fields']['specification'] == '25kg'
    assert client.get('/api/audit-logs').json()['items'][0]['action'] == '修改物料'


@pytest.mark.parametrize('method', ['POST', 'PUT'])
def test_identical_material_reports_existing_without_modifying_timestamp(client, method):
    bootstrap(client)
    body = {'name': '原料A', 'model': '甲型', 'shelf_life': '1年', 'contact': '123'}
    first = client.post('/api/materials', json=body).json()
    route = '/api/materials' if method == 'POST' else f'/api/materials/{first["id"]}'
    response = client.request(method, route, json=body | {'name': ' 原料a ', 'shelf_life': '12个月'})
    assert response.status_code == 409
    assert '已经有同样的物料' in response.json()['detail']
    assert client.get('/api/materials').json()[0]['updated_at'] == first['updated_at']
