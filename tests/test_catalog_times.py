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


def test_scheme_names_remove_report_boilerplate_before_duplicate_check(client):
    bootstrap(client)
    created = client.post('/api/schemes', json={'name': '依据该公司提供的内检报告为准. GB/T 6543'})
    assert created.status_code == 201
    assert created.json()['name'] == 'GB/T 6543'
    assert client.post('/api/schemes', json={'name': '依据该公司提供的内检报告为准。GB/T 6543'}).status_code == 409
    changed = client.put(f'/api/schemes/{created.json()["id"]}', json={'name': '依据该公司提供的内检报告为准.QB/T1871'})
    assert changed.json()['name'] == 'QB/T1871'
    assert client.post('/api/schemes', json={'name': '依据该公司提供的内检报告为准.'}).status_code == 422
