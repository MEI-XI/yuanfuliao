import pytest
from conftest import bootstrap


@pytest.mark.parametrize('resource', ['materials', 'schemes'])
def test_catalog_times_are_server_managed(client, resource):
    bootstrap(client)
    created = client.post('/api/' + resource, json={'name': '时间测试'}).json()
    assert created['created_at']
    assert created['updated_at']
    changed = client.put(f'/api/{resource}/{created["id"]}', json={'name': '修改后的名称'}).json()
    assert changed['created_at'] == created['created_at']
    assert changed['updated_at'] > created['updated_at']
    listed = client.get('/api/' + resource).json()[0]
    assert listed['updated_at'] == changed['updated_at']
    assert client.put(f'/api/{resource}/{created["id"]}', json={'name': '伪造', 'created_at': '2000-01-01'}).status_code == 422
