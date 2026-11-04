from pathlib import Path
from threading import Event
import httpx
import pytest

from conftest import bootstrap
from test_pending_recognition import wait_finished
from test_records import new_ledger


def upload_label(client, ledger):
    response = client.post(f'/api/ledgers/{ledger}/images', files={
        'file': ('label.png', (Path(__file__).parent / 'fixtures/label.png').read_bytes(), 'image/png'),
    })
    assert response.status_code == 201
    return response.json()['id']


def test_auxiliary_defaults_to_disabled_thinking_and_reports_mode(client):
    bootstrap(client)
    ledger = new_ledger(client)
    image = upload_label(client, ledger)
    client.app.state.scan_image = lambda path: {'texts': ['品名：甘氨酸'], 'boxes': []}
    modes = []

    def auxiliary(paths, texts, thinking_mode):
        modes.append(thinking_mode)
        return {'packaging': '纸袋'}

    client.app.state.cloud_extract = auxiliary
    response = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image]})
    assert response.status_code == 202
    assert response.json()['cloud_thinking'] == 'disabled'
    job = wait_finished(client, response.json()['id'])
    assert job['cloud_status'] == 'done'
    assert job['cloud_fields']['packaging'] == '纸袋'
    assert job['fields']['material_name'] == '甘氨酸'
    assert modes == ['disabled']


def test_selected_low_thinking_is_not_reused_from_a_fast_job(client):
    bootstrap(client)
    ledger = new_ledger(client)
    image = upload_label(client, ledger)
    release = Event()
    modes = []

    def scan(path):
        assert release.wait(10)
        return {'texts': ['品名：甘氨酸'], 'boxes': []}

    def auxiliary(paths, texts, thinking_mode):
        modes.append(thinking_mode)
        return {'packaging': '纸袋'}

    client.app.state.scan_image = scan
    client.app.state.cloud_extract = auxiliary
    try:
        fast = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image]}).json()
        low_response = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image], 'cloud_thinking': 'low'})
        assert low_response.status_code == 202
        low = low_response.json()
        assert low['id'] != fast['id']
        assert low['cloud_thinking'] == 'low'
        retry = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image], 'cloud_thinking': 'low'}).json()
        assert retry['id'] == low['id']
    finally:
        release.set()
    assert wait_finished(client, fast['id'])['cloud_status'] == 'done'
    assert wait_finished(client, low['id'])['cloud_status'] == 'done'
    assert sorted(modes) == ['disabled', 'low']


@pytest.mark.parametrize('mode', ['disabled', 'low'])
def test_gateway_timeout_preserves_base_recognition_and_record_saving(client, monkeypatch, mode):
    bootstrap(client)
    ledger = new_ledger(client)
    image = upload_label(client, ledger)
    client.app.state.scan_image = lambda path: {'texts': ['品名：甘氨酸', '规格：25kg/袋'], 'boxes': []}
    requests = []

    def timeout(request):
        requests.append(request)
        raise httpx.ReadTimeout('private upstream detail', request=request)

    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(timeout), **kwargs))
    response = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image], 'cloud_thinking': mode})
    assert response.status_code == 202
    job = wait_finished(client, response.json()['id'])
    assert job['cloud_status'] == 'failed'
    assert job['local_status'] == 'done'
    assert job['fields']['material_name'] == '甘氨酸'
    assert 'DeepSeek' in job['cloud_error'] and '超时' in job['cloud_error']
    assert 'private upstream detail' not in job['cloud_error']
    assert len(requests) == 1
    saved = client.post(f'/api/ledgers/{ledger}/records', json={
        'fields': job['fields'] | {'address': '人员填写地址'},
        'image_ids': [image], 'recognition_job_id': job['id'],
    })
    assert saved.status_code == 201
    assert saved.json()['fields']['material_name'] == '甘氨酸'
    assert saved.json()['fields']['address'] == '人员填写地址'
