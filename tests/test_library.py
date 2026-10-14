from conftest import bootstrap
from test_records import new_ledger


def test_schemes_can_be_shared_without_material_and_selected_for_any_material(client):
    bootstrap(client)
    ledger = new_ledger(client)
    shared = client.post('/api/schemes', json={'name': '通用外观标准', 'items': [{'name': '外观', 'standard': '无异物'}]})
    assert shared.status_code == 201
    assert shared.json()['material_id'] is None
    first = client.post('/api/materials', json={'name': '甘氨酸'}).json()
    second = client.post('/api/materials', json={'name': '精氨酸'}).json()
    linked = client.post('/api/schemes', json={'material_id': first['id'], 'name': '可复用标准', 'items': [{'name': '水分', 'standard': '≤0.2%'}]}).json()
    for material in [None, first['id'], second['id']]:
        record = client.post(f'/api/ledgers/{ledger}/records', json={'material_id': material, 'scheme_id': shared.json()['id']})
        assert record.status_code == 201
        assert record.json()['items'][0]['name'] == '外观'
        changed = client.patch(f'/api/records/{record.json()["id"]}', json={'version': 1, 'scheme_id': linked['id']})
        assert changed.status_code == 200
        assert changed.json()['items'][0]['name'] == '水分'
    assert client.put(f'/api/schemes/{linked["id"]}', json={'name': '取消绑定', 'items': []}).json()['material_id'] is None


def test_changing_material_keeps_chosen_scheme_and_inspection_snapshot(client):
    bootstrap(client)
    ledger = new_ledger(client)
    first = client.post('/api/materials', json={'name': '甘氨酸'}).json()
    second = client.post('/api/materials', json={'name': '精氨酸'}).json()
    scheme = client.post('/api/schemes', json={'name': '通用', 'items': [{'name': '外观', 'standard': '无异物'}]}).json()
    record = client.post(f'/api/ledgers/{ledger}/records', json={'material_id': first['id'], 'scheme_id': scheme['id'], 'items': [{'name': '外观', 'standard': '无异物', 'result': '符合', 'conclusion': '合格'}]}).json()
    changed = client.patch(f'/api/records/{record["id"]}', json={'version': 1, 'material_id': second['id']}).json()
    assert changed['scheme_name'] == '通用'
    assert changed['items'] == record['items']


def test_explicit_no_scheme_does_not_label_individual_items_with_material_default(client):
    bootstrap(client)
    ledger = new_ledger(client)
    material = client.post('/api/materials', json={'name': '甘氨酸'}).json()
    client.post('/api/schemes', json={'material_id': material['id'], 'name': '默认水分标准', 'items': [{'name': '水分'}]})
    record = client.post(f'/api/ledgers/{ledger}/records', json={'material_id': material['id'], 'scheme_id': None, 'items': [{'name': '外观', 'standard': '无异物'}]}).json()
    assert record['scheme_name'] == ''
    assert record['items'][0]['name'] == '外观'


def test_material_schemes_autofill_only_when_unique_and_records_keep_snapshots(client):
    bootstrap(client)
    ledger = new_ledger(client)
    material_response = client.post("/api/materials", json={"name": "甘氨酸", "model": "食品级", "aliases": "氨基乙酸"})
    assert material_response.status_code == 201
    material = material_response.json()["id"]
    scheme_body = {"material_id": material, "name": "常规标准", "items": [{"name": "水分", "standard": "≤0.2%", "unit": "%"}]}
    first = client.post("/api/schemes", json=scheme_body).json()
    record = client.post(f"/api/ledgers/{ledger}/records", json={"material_id": material}).json()
    assert record["items"] == [{"name": "水分", "standard": "≤0.2%", "unit": "%", "result": "", "conclusion": ""}]
    assert record["fields"]["sampling_items"] == "水分"
    changed = scheme_body | {"items": [{"name": "水分", "standard": "≤0.3%", "unit": "%"}]}
    assert client.put(f'/api/schemes/{first["id"]}', json=changed).status_code == 200
    assert client.get(f'/api/records/{record["id"]}').json()["items"][0]["standard"] == "≤0.2%"
    second = client.post("/api/schemes", json=scheme_body | {"name": "另一标准"}).json()
    unselected = client.post(f"/api/ledgers/{ledger}/records", json={"material_id": material}).json()
    assert unselected["items"] == []
    selected = client.post(f"/api/ledgers/{ledger}/records", json={"material_id": material, "scheme_id": second["id"]}).json()
    assert selected["scheme_name"] == "另一标准"


def test_shared_partner_details_are_admin_maintained_and_readable_by_workers(client):
    bootstrap(client)
    response = client.post("/api/partners", json={"name": "乙工厂", "kind": "manufacturer", "address": "河北", "contact": "0311-12345678"})
    assert response.status_code == 201
    partner = response.json()
    assert client.put(f'/api/partners/{partner["id"]}', json={"name": "乙工厂", "kind": "manufacturer", "address": "河北石家庄", "contact": ""}).status_code == 200
    client.post("/api/users", json={"username": "worker", "password": "worker-password"})
    client.post("/api/login", json={"username": "worker", "password": "worker-password"})
    assert client.get("/api/partners").json()[0]["address"] == "河北石家庄"
    assert client.post("/api/partners", json={"name": "篡改", "kind": "supplier"}).status_code == 403
