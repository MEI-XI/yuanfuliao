import json
import time

import httpx

from conftest import bootstrap
from test_records import new_ledger
from test_recognition import run_label


def test_all_supplier_manufacturer_names_and_addresses_are_selectable(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), [
        '品名：甘氨酸', '供应商：甲贸易有限公司', '供应商：乙贸易有限公司',
        '生产商：丙食品有限公司', '生产厂家：丁食品有限公司',
        '供应商地址：上海市甲路1号', '供应商地址：上海市乙路2号',
        '生产商地址：河北省丙路3号', '生产地址：河北省丁路4号',
    ])
    assert job['conflicts']['company_name'] == ['甲贸易有限公司', '乙贸易有限公司', '丙食品有限公司', '丁食品有限公司']
    assert job['conflicts']['address'] == ['上海市甲路1号', '上海市乙路2号', '河北省丙路3号', '河北省丁路4号']
    assert job['party_options']['company_name'][0] == {'value': '甲贸易有限公司', 'source': 'supplier'}
    assert job['party_options']['address'][-1] == {'value': '河北省丁路4号', 'source': 'manufacturer'}


def test_split_and_inline_labels_keep_all_parties_and_exclude_phone_suffix(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), [
        '供应商：甲贸易有限公司 供应商地址：上海市甲路1号 电话：021-12345678',
        '生产商：', '乙食品有限公司', '生产商地址：', '河北省乙路2号',
        '生产地址：河北省乙路2号',
    ])
    assert job['conflicts']['company_name'] == ['甲贸易有限公司', '乙食品有限公司']
    assert job['conflicts']['address'] == ['上海市甲路1号', '河北省乙路2号']
    assert len(job['party_options']['address']) == 2


def test_multiple_photos_and_crop_english_parties_are_not_lost(client):
    bootstrap(client)
    ledger = new_ledger(client)
    first = run_label(client, ledger, ['Supplier: Alpha Trading', 'Supplier Address: 1 London Road'])
    second = run_label(client, ledger, ['Manufacturer: Beta Foods', 'Manufacturer Address: 2 Paris Road'])
    readings = iter([
        {'texts': ['Supplier: Alpha Trading', 'Supplier Address: 1 London Road'], 'boxes': [], 'supplements': [
            {'texts': ['Manufacturer: Gamma Foods', 'Manufacturer Address: 3 Rome Road'], 'boxes': [], 'kind': 'crop'}]},
        {'texts': ['Manufacturer: Beta Foods', 'Manufacturer Address: 2 Paris Road'], 'boxes': []},
    ])
    client.app.state.scan_image = lambda path: next(readings)
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': first['image_ids'] + second['image_ids'], 'cloud_enabled': False}).json()
    for _ in range(100):
        job = client.get(f'/api/recognition/{job["id"]}').json()
        if job['local_status'] == 'done':
            break
        time.sleep(.02)
    assert set(job['conflicts']['company_name']) == {'Alpha Trading', 'Beta Foods', 'Gamma Foods'}
    assert set(job['conflicts']['address']) == {'1 London Road', '2 Paris Road', '3 Rome Road'}
    assert len(job['party_options']['address']) == 3


def test_cloud_keeps_all_role_candidates_and_normal_field_alternatives(client, monkeypatch):
    bootstrap(client)
    client.put('/api/settings/cloud', json={'api_key': 'test-only-key'})
    real_client = httpx.Client
    payload = {
        'company_name': '甲贸易公司', 'address': '上海市甲路1号',
        'candidates': {'company_name': ['乙食品公司'], 'address': ['河北省乙路2号']},
        'party_options': {'company_name': [{'value': '丙食品公司', 'source': 'manufacturer'}],
                          'address': [{'value': '河北省丙路3号', 'source': 'manufacturer'}, {'value': {}, 'source': 'supplier'}]},
    }
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(payload, ensure_ascii=False)}}]}))))
    job = run_label(client, new_ledger(client), ['品名：甘氨酸'], cloud_enabled=True)
    assert job['cloud_status'] == 'done', job['cloud_error']
    assert set(job['conflicts']['company_name']) == {'甲贸易公司', '乙食品公司', '丙食品公司'}
    assert set(job['conflicts']['address']) == {'上海市甲路1号', '河北省乙路2号', '河北省丙路3号'}
    assert {'value': '河北省丙路3号', 'source': 'manufacturer'} in job['party_options']['address']


def test_cloud_array_fields_are_kept_as_choices_instead_of_discarded(client, monkeypatch):
    bootstrap(client)
    client.put('/api/settings/cloud', json={'api_key': 'test-only-key'})
    real_client = httpx.Client
    payload = {'company_name': ['甲公司', '乙公司'], 'address': ['甲路1号', '乙路2号']}
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(payload)}}]}))))
    job = run_label(client, new_ledger(client), ['品名：甘氨酸'], cloud_enabled=True)
    assert job['conflicts']['company_name'] == ['甲公司', '乙公司']
    assert job['conflicts']['address'] == ['甲路1号', '乙路2号']
