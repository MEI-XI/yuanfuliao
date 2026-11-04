from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest

from conftest import bootstrap
from test_records import new_ledger


def start_blocked_recognition(client, ledger, stage, release, *, fail=False):
    started = Event()

    def blocked_result(*args):
        started.set()
        if not release.wait(15):
            raise RuntimeError('Test recognition was not released')
        if fail:
            raise RuntimeError('Model unavailable')
        return {'texts': ['品名：甘氨酸'], 'boxes': []} if stage == 'local' else {'material_name': '甘氨酸'}

    client.app.state.scan_image = blocked_result if stage == 'local' else lambda path: {'texts': ['品名：甘氨酸'], 'boxes': []}
    client.app.state.cloud_extract = blocked_result if stage == 'cloud' else lambda paths, texts, thinking_mode='disabled': {'material_name': '甘氨酸'}
    image = client.post(f'/api/ledgers/{ledger}/images', files={
        'file': ('label.png', (Path(__file__).parent / 'fixtures/label.png').read_bytes(), 'image/png'),
    }).json()
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={
        'image_ids': [image['id']], 'cloud_enabled': stage == 'cloud',
    }).json()
    assert started.wait(5)
    current = client.get(f'/api/recognition/{job["id"]}').json()
    assert current[f'{stage}_status'] == 'running'
    return {'image_ids': [image['id']], 'recognition_job_id': job['id'], 'fields': {'material_name': '人工暂存名称'}}


def wait_finished(client, job_id):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        job = client.get(f'/api/recognition/{job_id}').json()
        if job['local_status'] not in {'queued', 'running'} and job['cloud_status'] not in {'queued', 'running'}:
            return job
        sleep(.02)
    pytest.fail('Recognition did not finish')


@pytest.mark.parametrize('stage', ['local', 'cloud'])
@pytest.mark.parametrize('fail', [False, True])
def test_running_recognition_allows_pending_batch_and_only_checks_after_completion(client, stage, fail):
    bootstrap(client)
    ledger = new_ledger(client)
    release = Event()
    try:
        draft = start_blocked_recognition(client, ledger, stage, release, fail=fail)
        body = {'request_id': str(uuid4()), 'records': [{'fields': {'material_name': '手动记录'}}, draft]}
        rejected = client.post(f'/api/ledgers/{ledger}/records/batch', json=body | {'mark_checked': True})
        assert rejected.status_code == 409
        assert '识别尚未完成' in rejected.json()['detail']
        assert '待核对' in rejected.json()['detail']
        assert client.get(f'/api/ledgers/{ledger}/records').json() == []

        saved = client.post(f'/api/ledgers/{ledger}/records/batch', json=body)
        assert saved.status_code == 201, saved.text
        records = saved.json()
        assert all(record['status'] == 'pending' and record['checker_id'] is None for record in records)
        retry = client.post(f'/api/ledgers/{ledger}/records/batch', json=body)
        assert [record['id'] for record in retry.json()] == [record['id'] for record in records]
        record = records[1]
        rejected = client.post(f'/api/records/{record["id"]}/check', json={'version': record['version']})
        assert rejected.status_code == 409
        assert client.get(f'/api/records/{record["id"]}').json()['status'] == 'pending'
    finally:
        release.set()
    job = wait_finished(client, draft['recognition_job_id'])
    assert job[f'{stage}_status'] == ('failed' if fail else 'done')
    current = client.get(f'/api/records/{record["id"]}').json()
    assert current['fields']['material_name'] == '人工暂存名称'
    assert current['version'] == record['version']
    assert current['status'] == 'pending'
    checked = client.post(f'/api/records/{record["id"]}/check', json={'version': current['version']})
    assert checked.status_code == 200
    assert checked.json()['status'] == 'checked'


def test_queued_recognition_saves_pending_and_rejects_checking(client):
    bootstrap(client)
    ledger = new_ledger(client)
    release = Event()
    try:
        running = start_blocked_recognition(client, ledger, 'local', release)
        image = client.post(f'/api/ledgers/{ledger}/images', files={
            'file': ('queued.png', (Path(__file__).parent / 'fixtures/label.png').read_bytes(), 'image/png'),
        }).json()
        job = client.post(f'/api/ledgers/{ledger}/recognition', json={
            'image_ids': [image['id']], 'cloud_enabled': True,
        }).json()
        assert job['local_status'] == job['cloud_status'] == 'queued'
        draft = {'image_ids': [image['id']], 'recognition_job_id': job['id']}
        saved = client.post(f'/api/ledgers/{ledger}/records/batch', json={
            'request_id': str(uuid4()), 'records': [draft],
        })
        assert saved.status_code == 201, saved.text
        record = saved.json()[0]
        assert record['status'] == 'pending'
        assert client.post(f'/api/records/{record["id"]}/check', json={'version': record['version']}).status_code == 409
        assert client.post(f'/api/ledgers/{ledger}/records/batch', json={
            'request_id': str(uuid4()), 'mark_checked': True, 'records': [draft],
        }).status_code == 409
        assert len(client.get(f'/api/ledgers/{ledger}/records').json()) == 1
    finally:
        release.set()
    wait_finished(client, running['recognition_job_id'])
    wait_finished(client, job['id'])
