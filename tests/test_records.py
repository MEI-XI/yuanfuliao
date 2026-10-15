from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import bootstrap


def new_ledger(client, name="青山科技"):
    response = client.post("/api/ledgers", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_ledger_names_are_valid_sheet_names_and_only_admin_can_create(client):
    bootstrap(client)
    ledger_id = new_ledger(client)
    assert client.get("/api/ledgers").json() == [{"id": ledger_id, "name": "青山科技"}]
    assert client.post("/api/ledgers", json={"name": "公司/部门"}).status_code == 422
    assert client.post("/api/ledgers", json={"name": "青山科技"}).status_code == 409
    client.post("/api/users", json={"username": "worker", "password": "worker-password"})
    client.post("/api/login", json={"username": "worker", "password": "worker-password"})
    assert client.get("/api/ledgers").status_code == 200
    assert client.post("/api/ledgers", json={"name": "味源食品"}).status_code == 403


def test_empty_record_defaults_arrival_but_explicit_blank_stays_blank(client):
    admin = bootstrap(client)
    ledger = new_ledger(client)
    response = client.post(f"/api/ledgers/{ledger}/records", json={})
    assert response.status_code == 201
    record = response.json()
    assert record["fields"]["arrival_date"] == datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    assert record["fields"]["received_quantity"] == ""
    assert record["creator_id"] == admin["id"]
    assert record["status"] == "pending"
    blank = client.post(f"/api/ledgers/{ledger}/records", json={"fields": {"arrival_date": None}}).json()
    assert client.get(f'/api/records/{blank["id"]}').json()["fields"]["arrival_date"] is None
    assert len(client.get(f"/api/ledgers/{ledger}/records").json()) == 2


def test_record_editing_is_owner_only_and_changes_reset_check_with_history(client):
    admin = bootstrap(client)
    ledger = new_ledger(client)
    client.post("/api/users", json={"username": "worker", "password": "worker-password"})
    saved = client.post(f"/api/ledgers/{ledger}/records", json={}).json()
    path = f'/api/records/{saved["id"]}'
    client.post("/api/login", json={"username": "worker", "password": "worker-password"})
    assert client.get(path).status_code == 200
    assert client.patch(path, json={"version": 1, "fields": {"notes": "不能修改"}}).status_code == 403
    assert client.post(path + "/check", json={"version": 1}).status_code == 403
    client.post("/api/login", json={"username": "admin", "password": "test-password-123"})
    checked = client.post(path + "/check", json={"version": 1}).json()
    assert checked["status"] == "checked"
    assert checked["checker_id"] == admin["id"]
    edited = client.patch(path, json={"version": checked["version"], "fields": {"arrival_date": None, "notes": "人工修改"}}).json()
    assert edited["status"] == "pending"
    assert edited["checker_id"] is None
    assert edited["creator_id"] == admin["id"]
    assert edited["fields"]["arrival_date"] is None
    history = client.get(path + "/history").json()
    assert [h["action"] for h in history] == ["created", "checked", "edited"]
    assert history[-1]["snapshot"]["fields"]["notes"] == "人工修改"


def test_stale_updates_cannot_overwrite_and_void_records_are_read_only(client):
    bootstrap(client)
    ledger = new_ledger(client)
    client.post("/api/users", json={"username": "worker", "password": "worker-password"})
    client.post("/api/login", json={"username": "worker", "password": "worker-password"})
    saved = client.post(f"/api/ledgers/{ledger}/records", json={}).json()
    path = f'/api/records/{saved["id"]}'
    assert client.patch(path, json={"version": 1, "fields": {"notes": "新内容"}}).status_code == 200
    assert client.patch(path, json={"version": 1, "fields": {"notes": "过期内容"}}).status_code == 409
    assert client.post(path + "/void", json={"version": 2}).status_code == 403
    client.post("/api/login", json={"username": "admin", "password": "test-password-123"})
    assert client.post(path + "/void", json={"version": 2}).status_code == 200
    assert client.get(path).json()["fields"]["notes"] == "新内容"
    assert client.get(path).json()["status"] == "void"
    assert client.patch(path, json={"version": 3, "fields": {"notes": "改作废"}}).status_code == 409


def test_changing_a_saved_scheme_replaces_snapshot_instead_of_reusing_results(client):
    bootstrap(client)
    ledger = new_ledger(client)
    material = client.post('/api/materials', json={'name': '甘氨酸'}).json()['id']
    first = client.post('/api/schemes', json={'material_id': material, 'name': '原标准', 'items': [{'name': '水分', 'standard': '≤0.2%'}]}).json()
    second = client.post('/api/schemes', json={'material_id': material, 'name': '新标准', 'items': [{'name': '含量', 'standard': '≥98.5%'}]}).json()
    record = client.post(f'/api/ledgers/{ledger}/records', json={'inspection_enabled': True, 'material_id': material, 'scheme_id': first['id'], 'items': [{'name': '水分', 'standard': '≤0.2%', 'result': '0.1%', 'conclusion': '符合'}]}).json()
    changed = client.patch(f'/api/records/{record["id"]}', json={'version': 1, 'material_id': material, 'scheme_id': second['id']})
    assert changed.status_code == 200
    assert changed.json()['scheme_name'] == '新标准'
    assert changed.json()['items'] == [{'name': '含量', 'standard': '≥98.5%', 'unit': '', 'result': '', 'conclusion': ''}]


def test_worker_can_list_records_across_companies_and_filter_by_creator(client):
    administrator = bootstrap(client)
    for name in ['青山科技', '味源食品']:
        ledger = new_ledger(client, name)
        client.post(f'/api/ledgers/{ledger}/records', json={})
    client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'})
    client.post('/api/login', json={'username': 'worker', 'password': 'worker-password'})
    response = client.get('/api/records')
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert len({record['ledger_id'] for record in response.json()}) == 2
    assert {'id': administrator['id'], 'username': 'admin'} in client.get('/api/people').json()
    assert client.get('/api/users').status_code == 403
def test_sampling_items_stay_manual_when_selecting_and_changing_scheme(client):
    bootstrap(client)
    ledger = new_ledger(client)
    scheme = client.post('/api/schemes', json={'name': '人工抽检方案', 'items': [{'name': '含量', 'standard': '≥98%'}]}).json()
    record = client.post(f'/api/ledgers/{ledger}/records', json={'inspection_enabled': True, 'scheme_id': scheme['id']}).json()
    assert record['fields']['sampling_items'] == ''
    changed = client.patch(f'/api/records/{record["id"]}', json={'version': record['version'], 'fields': {'sampling_items': '人工指定'}}).json()
    changed = client.patch(f'/api/records/{record["id"]}', json={'version': changed['version'], 'scheme_id': scheme['id']}).json()
    assert changed['fields']['sampling_items'] == '人工指定'
