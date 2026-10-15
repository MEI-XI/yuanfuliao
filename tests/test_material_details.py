from conftest import bootstrap


def test_material_details_persist_and_remain_admin_maintained(client):
    bootstrap(client)
    body = {
        'name': '甘氨酸', 'model': '食品级', 'aliases': '氨基乙酸',
        'specification': '25kg/袋', 'company_name': '甲供应商',
        'address': '河北石家庄', 'contact': '0311-12345678',
        'shelf_life': '24个月', 'address_source': 'manufacturer',
        'contact_source': 'supplier', 'packaging': '纸塑复合袋',
    }
    response = client.post('/api/materials', json=body)
    assert response.status_code == 201, response.text
    material_id = response.json()['id']
    assert response.json() == {'id': material_id, **body}
    assert client.get('/api/materials').json() == [{'id': material_id, **body}]
    client.post('/api/users', json={'username': 'manager', 'password': 'manager-password', 'role': 'admin'})
    client.post('/api/users', json={'username': 'worker', 'password': 'worker-password'})
    client.post('/api/login', json={'username': 'manager', 'password': 'manager-password'})
    changed = body | {'specification': '20kg/袋', 'company_name': '乙供应商', 'address': '山东', 'contact': '', 'shelf_life': '12个月', 'address_source': 'supplier', 'contact_source': ''}
    assert client.put(f'/api/materials/{material_id}', json=changed).json() == {'id': material_id, **changed}
    client.post('/api/login', json={'username': 'worker', 'password': 'worker-password'})
    assert client.get('/api/materials').json() == [{'id': material_id, **changed}]
    assert client.post('/api/materials', json=body).status_code == 403
    assert client.put(f'/api/materials/{material_id}', json=body).status_code == 403


def test_material_details_default_empty_and_validate_attribution(client):
    bootstrap(client)
    response = client.post('/api/materials', json={'name': '旧式物料'})
    assert response.status_code == 201
    for field in ['specification', 'company_name', 'address', 'contact', 'shelf_life', 'packaging', 'address_source', 'contact_source']:
        assert response.json()[field] == ''
    for field in ['address_source', 'contact_source']:
        assert client.post('/api/materials', json={'name': '错误来源', field: 'other'}).status_code == 422


def test_material_migration_keeps_existing_catalog_entries(client):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from sqlalchemy import text

    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with client.app.state.engine.begin() as connection:
        config.attributes['connection'] = connection
        command.downgrade(config, 'f10200')
        connection.execute(text("INSERT INTO materials (name, model, aliases) VALUES ('已有物料', '食品级', '旧别名')"))
        command.upgrade(config, 'head')
    bootstrap(client)
    material = client.get('/api/materials').json()[0]
    assert material['name'] == '已有物料'
    assert material['model'] == '食品级'
    assert material['aliases'] == '旧别名'
    for field in ['specification', 'company_name', 'address', 'contact', 'shelf_life', 'packaging', 'address_source', 'contact_source']:
        assert material[field] == ''
