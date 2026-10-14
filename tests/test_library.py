from conftest import bootstrap
from test_records import new_ledger


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
