import httpx
import pytest
import time
from io import BytesIO
from PIL import Image

from conftest import bootstrap
from test_records import new_ledger


def test_cloud_connection_reports_rejected_credentials_without_echoing_key(client, monkeypatch):
    bootstrap(client)
    key = 'test-key-never-echo'
    client.put('/api/settings/cloud', json={'api_key': key})
    real_client = httpx.Client
    def reject(request):
        assert request.headers['authorization'] == 'Bearer ' + key
        return httpx.Response(401, json={'error': {'code': '401', 'message': 'Invalid token ' + key}})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(reject), **kwargs))
    response = client.post('/api/settings/cloud/test')
    assert response.status_code == 200
    assert response.json()['ok'] is False
    assert '401' in response.json()['message']
    assert '完整' in response.json()['message']
    assert key not in response.text
    client.post('/api/users', json={'username': 'ordinary', 'password': 'ordinary-password', 'role': 'user'})
    client.post('/api/login', json={'username': 'ordinary', 'password': 'ordinary-password'})
    assert client.post('/api/settings/cloud/test').status_code == 403


def test_cloud_auth_failure_keeps_local_results_and_explains_how_to_fix(client, monkeypatch):
    bootstrap(client)
    ledger = new_ledger(client)
    client.put('/api/settings/cloud', json={'api_key': 'rejected-key'})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401)), **kwargs))
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['品名：甘氨酸'], 'boxes': []}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': True}).json()
    for _ in range(100):
        job = client.get(f'/api/recognition/{job["id"]}').json()
        if job['cloud_status'] == 'failed':
            break
        time.sleep(.02)
    assert job['local_status'] == 'done'
    assert job['fields']['material_name'] == '甘氨酸'
    assert job['cloud_status'] == 'failed'
    assert '401' in job['cloud_error']
    assert '本地结果已保留' in job['cloud_error']


@pytest.mark.parametrize('failure, expected', [('timeout', '超时'), (429, '429'), (403, '403'), (500, '500')])
def test_cloud_test_reports_provider_and_network_failures(client, monkeypatch, failure, expected):
    bootstrap(client)
    client.put('/api/settings/cloud', json={'api_key': 'test-key'})
    real_client = httpx.Client
    def fail(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('network timed out', request=request)
        return httpx.Response(failure, json={'error': {'message': 'private provider details'}})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(fail), **kwargs))
    result = client.post('/api/settings/cloud/test').json()
    assert result['ok'] is False
    assert expected in result['message']
    assert 'private provider details' not in result['message']


def test_cloud_test_validates_saved_key_and_model_response(client, monkeypatch):
    bootstrap(client)
    client.put('/api/settings/cloud', json={'api_key': ''})
    assert '尚未配置' in client.post('/api/settings/cloud/test').json()['message']
    client.put('/api/settings/cloud', json={'api_key': 'working-test-key'})
    real_client = httpx.Client
    def respond(request):
        assert request.headers['authorization'] == 'Bearer working-test-key'
        assert b'glm-4.1v-thinking-flash' in request.content
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"material_name":"测试物料"}'}}]})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    assert client.post('/api/settings/cloud/test').json()['ok'] is True


def test_cloud_test_distinguishes_unusable_model_output_from_auth_failure(client, monkeypatch):
    bootstrap(client)
    client.put('/api/settings/cloud', json={'api_key': 'test-key'})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': '不是 JSON'}}]})), **kwargs))
    result = client.post('/api/settings/cloud/test').json()
    assert result['ok'] is False
    assert '格式' in result['message']
