import json

import httpx
from conftest import bootstrap
from test_recognition import run_label
from test_records import new_ledger


TEXTS = ['Product Name: Glycine', 'Manufacturer: Example Food Co., Ltd.', 'Net Weight: 25 kg/bag',
         'MFG: 2026.01.14', 'EXP: 2028.01.13', 'Shelf Life: 24 months', 'Packaging: Paper bag',
         'Address: 10 Food Road, London', 'Tel: +44 20 1234 5678', 'Batch No: EN260114']


def test_english_labels_keep_original_fields_when_cloud_disabled(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), TEXTS)
    assert job['fields']['material_name'] == 'Glycine'
    assert job['fields']['company_name'] == 'Example Food Co., Ltd.'
    assert job['fields']['specification'] == '25 kg/bag'
    assert job['fields']['shelf_life'] == '24个月'
    assert job['fields']['production_dates'] == ['2026-01-14']
    assert job['fields']['expiry_date'] == '2028-01-13'
    assert job['fields']['contact'] == '+44 20 1234 5678'
    assert job['english_detected'] is True
    assert job['evidence'][0]['texts'] == TEXTS


def test_english_cloud_translation_is_returned_for_review_and_failure_keeps_local(client, monkeypatch):
    bootstrap(client)
    ledger = new_ledger(client)
    client.put('/api/settings/cloud', json={'api_key': 'test-only-key'})
    real_client = httpx.Client
    requests = []

    def translated(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'material_name': '甘氨酸', 'specification': '25公斤/袋',
            'company_name': '示例食品公司（Example Food Co., Ltd.）', 'packaging': '纸袋',
        }, ensure_ascii=False)}}]})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(translated)))
    job = run_label(client, ledger, TEXTS, cloud_enabled=True)
    assert job['cloud_status'] == 'done', job['cloud_error']
    assert job['cloud_fields']['material_name'] == '甘氨酸'
    assert job['fields']['material_name'] == 'Glycine'
    assert '翻译成中文' in requests[0]['messages'][0]['content'][0]['text']
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(503))))
    failed = run_label(client, ledger, TEXTS, cloud_enabled=True)
    assert failed['cloud_status'] == 'failed'
    assert failed['fields']['material_name'] == 'Glycine'


def test_english_expiry_only_and_ambiguous_dates_do_not_become_production(client):
    bootstrap(client)
    ledger = new_ledger(client)
    expiry = run_label(client, ledger, ['Product Name: Glycine', 'EXP: 20280113'])
    assert expiry['fields']['expiry_date'] == '2028-01-13'
    assert not expiry['fields'].get('production_dates')
    ambiguous = run_label(client, ledger, ['MFG: 01/02/2026', 'EXP: 13 JAN 2028'])
    assert ambiguous['conflicts']['production_dates'] == ['2026-02-01', '2026-01-02']
    assert not ambiguous['fields'].get('production_dates')
    assert ambiguous['fields']['expiry_date'] == '2028-01-13'


def test_chinese_packaging_with_tel_is_not_reported_as_english(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), ['品名：甘氨酸', '生产商：测试食品有限公司', 'TEL: 0311-12345678'])
    assert job['english_detected'] is False
