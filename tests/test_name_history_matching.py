import time

from conftest import bootstrap
from test_records import new_ledger
from test_recognition import run_label


def checked_record(client, ledger, name, *, job=None):
    body = {
        'fields': {'material_name': name, 'company_name': '确认食品有限公司'},
        'inspection_enabled': True,
        'items': [{'name': '水分', 'standard': '≤0.5%', 'result': '0.2%', 'conclusion': '合格'}],
    }
    if job:
        body.update(recognition_job_id=job['id'], image_ids=job['image_ids'])
    saved = client.post(f'/api/ledgers/{ledger}/records', json=body)
    assert saved.status_code == 201, saved.text
    record = saved.json()
    checked = client.post(f'/api/records/{record["id"]}/check', json={'version': record['version']})
    assert checked.status_code == 200, checked.text
    return checked.json()


def test_single_name_candidate_exactly_matches_confirmed_spelling(client):
    bootstrap(client)
    ledger = new_ledger(client)
    checked = checked_record(client, ledger, '鸡蛋黄粉 制品')
    client.app.state.cloud_extract = lambda paths, texts, thinking_mode='disabled': {'_candidates': {'material_name': ['鸡蛋黄粉制品']}}
    job = run_label(client, ledger, ['保质期：12个月'], cloud_enabled=True)
    suggestion = job['review_suggestions']
    assert suggestion['match_status'] == 'matched'
    assert suggestion['fields']['material_name'] == '鸡蛋黄粉 制品'
    assert suggestion['sources'][0]['record_id'] == checked['id']
    assert suggestion['inspection']['items'][0]['result'] == '0.2%'


def test_multiple_unresolved_candidates_do_not_reuse_only_known_history(client):
    bootstrap(client)
    ledger = new_ledger(client)
    checked_record(client, ledger, '鸡蛋黄粉')
    client.app.state.cloud_extract = lambda paths, texts, thinking_mode='disabled': {'_candidates': {'material_name': ['鸡蛋黄粉', '鸡蛋黄粉制品']}}
    job = run_label(client, ledger, ['保质期：12个月'], cloud_enabled=True)
    assert job['review_suggestions']['fields'] == {}
    assert job['review_suggestions']['inspection'] is None


def test_differing_local_and_cloud_names_do_not_reuse_only_known_history(client):
    bootstrap(client)
    ledger = new_ledger(client)
    checked_record(client, ledger, '鸡蛋黄粉')
    client.app.state.cloud_extract = lambda paths, texts, thinking_mode='disabled': {'material_name': '鸡蛋黄粉制品'}
    job = run_label(client, ledger, ['品名：鸡蛋黄粉'], cloud_enabled=True)
    assert job['review_suggestions']['fields'] == {}
    assert job['review_suggestions']['inspection'] is None


def test_product_suffix_is_not_removed_when_matching_history(client):
    bootstrap(client)
    ledger = new_ledger(client)
    checked_record(client, ledger, '鸡蛋黄粉')
    job = run_label(client, ledger, ['品名：鸡蛋黄粉制品'])
    assert job['review_suggestions']['sources'] == []
    assert job['review_suggestions']['inspection'] is None


def test_exact_catalog_alias_offers_full_name_without_reusing_inspection(client):
    bootstrap(client)
    ledger = new_ledger(client)
    material = client.post('/api/materials', json={
        'name': '鸡蛋黄粉制品', 'model': 'A型', 'aliases': '蛋黄制品A；黄粉A',
    })
    assert material.status_code == 201, material.text
    job = run_label(client, ledger, ['品名：蛋黄制品A'])
    assert job['candidate_defaults']['material_name'] == '鸡蛋黄粉制品 A型'
    assert job['review_suggestions']['inspection'] is None
    assert job['review_suggestions']['sources'] == []


def test_checked_name_from_old_ambiguous_ocr_is_reused_but_other_candidate_is_not_alias(client):
    bootstrap(client)
    ledger = new_ledger(client)
    first = run_label(client, ledger, ['品名：鸡蛋黄粉'])
    second = run_label(client, ledger, ['品名：鸡蛋黄粉制品'])
    readings = iter([['品名：鸡蛋黄粉'], ['品名：鸡蛋黄粉制品']])
    client.app.state.scan_image = lambda path: {'texts': next(readings), 'boxes': []}
    mixed = client.post(f'/api/ledgers/{ledger}/recognition', json={
        'image_ids': first['image_ids'] + second['image_ids'], 'cloud_enabled': False,
    }).json()
    for _ in range(100):
        mixed = client.get(f'/api/recognition/{mixed["id"]}').json()
        if mixed['local_status'] == 'done':
            break
        time.sleep(.02)
    assert mixed['conflicts']['material_name'] == ['鸡蛋黄粉', '鸡蛋黄粉制品']
    checked = checked_record(client, ledger, '鸡蛋黄粉制品', job=mixed)
    confirmed = run_label(client, ledger, ['品名：鸡蛋黄粉制品'])['review_suggestions']
    assert confirmed['fields']['material_name'] == '鸡蛋黄粉制品'
    assert confirmed['sources'][0]['record_id'] == checked['id']
    other = run_label(client, ledger, ['品名：鸡蛋黄粉'])['review_suggestions']
    assert other['sources'] == []


def test_same_catalog_alias_for_different_materials_does_not_choose_one(client):
    bootstrap(client)
    ledger = new_ledger(client)
    for name in ['鸡蛋黄粉', '鸡蛋黄粉制品']:
        response = client.post('/api/materials', json={'name': name, 'aliases': '黄色物料'})
        assert response.status_code == 201, response.text
    job = run_label(client, ledger, ['品名：黄色物料'])
    assert job['candidate_defaults']['material_name'] not in ['鸡蛋黄粉', '鸡蛋黄粉制品']
    assert job['review_suggestions']['sources'] == []
