import json
import httpx

from conftest import bootstrap
from test_records import new_ledger
from test_recognition import run_label


def test_incomplete_specification_does_not_block_complete_net_weight(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), ['产品名称：鸡蛋黄粉制品', '规格：20kg/', '净含量：20kg'])
    assert job['fields']['specification'] == '20kg'
    assert '20kg/' in job['conflicts']['specification']
    assert job['candidate_defaults']['specification'] == '20kg'
    assert any(w['field'] == 'specification' for w in job['field_warnings'])


def test_incomplete_values_remain_candidates_without_invented_units(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), ['品名：鸡蛋黄粉制品', '规格：20kg/', '保质期：12'])
    assert not job['fields'].get('specification')
    assert not job['fields'].get('shelf_life')
    assert job['conflicts']['specification'] == ['20kg/']
    assert job['conflicts']['shelf_life'] == ['12']
    assert {w['field'] for w in job['field_warnings']} >= {'specification', 'shelf_life'}


def test_cloud_name_candidates_have_default_and_keep_alternatives(client, monkeypatch):
    bootstrap(client)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'candidates': {'material_name': ['鸡蛋黄粉制品', '鸡蛋黄粉']}
        })}}]})
    ), **kwargs))
    job = run_label(client, new_ledger(client), ['净含量：20kg'], cloud_enabled=True)
    assert job['cloud_status'] == 'done'
    assert job['candidate_defaults']['material_name'] == '鸡蛋黄粉制品'
    assert job['conflicts']['material_name'] == ['鸡蛋黄粉制品', '鸡蛋黄粉']


def test_cloud_incomplete_units_do_not_become_complete_defaults(client, monkeypatch):
    bootstrap(client)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'specification': '20kg/', 'shelf_life': '12'
        })}}]})
    ), **kwargs))
    job = run_label(client, new_ledger(client), [], cloud_enabled=True)
    assert not job['cloud_fields'].get('specification')
    assert not job['cloud_fields'].get('shelf_life')
    assert job['conflicts']['specification'] == ['20kg/']
    assert job['conflicts']['shelf_life'] == ['12']


def test_cloud_keeps_complete_default_alongside_incomplete_candidates(client, monkeypatch):
    bootstrap(client)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'material_name': '鸡蛋黄粉制品', 'specification': '20kg',
            'candidates': {'material_name': ['鸡蛋黄粉'], 'specification': ['20kg/']},
        })}}]})
    ), **kwargs))
    job = run_label(client, new_ledger(client), [], cloud_enabled=True)
    assert job['candidate_defaults']['material_name'] == '鸡蛋黄粉制品'
    assert job['candidate_defaults']['specification'] == '20kg'
    assert job['conflicts']['material_name'] == ['鸡蛋黄粉制品', '鸡蛋黄粉']
    assert job['conflicts']['specification'] == ['20kg', '20kg/']


def test_english_translation_can_default_name_while_retaining_original(client):
    bootstrap(client)
    client.app.state.cloud_extract = lambda paths, texts, thinking_mode='disabled': {'material_name': '甘氨酸'}
    job = run_label(client, new_ledger(client), ['Product Name: Glycine', 'Net Weight: 25 kg'], cloud_enabled=True)
    assert job['english_detected']
    assert job['candidate_defaults']['material_name'] == '甘氨酸'
    assert job['fields']['material_name'] == 'Glycine'
