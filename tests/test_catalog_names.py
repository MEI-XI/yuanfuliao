import pytest
from concurrent.futures import ThreadPoolExecutor
from conftest import bootstrap


@pytest.mark.parametrize('path,extra', [('materials', {}), ('schemes', {}), ('partners', {'kind': 'supplier'})])
def test_catalog_names_cannot_be_duplicated_on_create_or_edit(client, path, extra):
    bootstrap(client)
    first = client.post(f'/api/{path}', json={'name': '测试名称', **extra}).json()
    duplicate = client.post(f'/api/{path}', json={'name': ' 测试名称 ', **extra})
    assert duplicate.status_code == 409
    assert '重名' in duplicate.json()['detail']
    second = client.post(f'/api/{path}', json={'name': '其他名称', **extra}).json()
    assert client.put(f'/api/{path}/{second["id"]}', json={'name': '测试名称', **extra}).status_code == 409
    assert client.put(f'/api/{path}/{first["id"]}', json={'name': '测试名称', **extra}).status_code == 200


def test_simultaneous_same_name_saves_only_create_one_material(client):
    bootstrap(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/api/materials', json={'name': '并发物料'}).status_code, range(2)))
    assert sorted(results) == [201, 409]
    assert len(client.get('/api/materials').json()) == 1
