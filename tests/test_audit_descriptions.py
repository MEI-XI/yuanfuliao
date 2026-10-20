from conftest import bootstrap


def test_audit_describes_named_objects_and_keeps_names_after_deletion(client):
    bootstrap(client)
    ledger = client.post('/api/ledgers', json={'name': '青山科技'}).json()
    material = client.post('/api/materials', json={'name': '甘氨酸'}).json()
    scheme = client.post('/api/schemes', json={'name': '添加剂标准', 'items': []}).json()
    record = client.post(f'/api/ledgers/{ledger["id"]}/records', json={'fields': {'material_name': '甘氨酸'}}).json()
    edited = client.patch(f'/api/records/{record["id"]}', json={'version': record['version'], 'fields': {'material_name': '甘氨酸', 'notes': 'private-notes'}})
    assert edited.status_code == 200
    assert client.delete(f'/api/materials/{material["id"]}').status_code == 204
    rows = client.get('/api/audit-logs').json()['items']
    descriptions = {row['action']: row['description'] for row in rows}
    assert '甘氨酸' in descriptions['创建物料']
    assert '甘氨酸' in descriptions['删除物料']
    assert '添加剂标准' in descriptions['创建检验方案']
    assert '青山科技' in descriptions['修改记录']
    assert '甘氨酸' in descriptions['修改记录']
    assert str(record['id']) in descriptions['修改记录']
    assert 'private-notes' not in str(rows)
    found = client.get('/api/audit-logs', params={'target': '添加剂标准'}).json()
    assert found['total'] == 1
    assert found['items'][0]['action'] == '创建检验方案'
