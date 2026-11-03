import time
import pytest

from conftest import bootstrap
from test_records import new_ledger
from test_recognition import run_label


def test_recognition_keeps_complete_title_and_offers_uncertain_name_for_review(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), ['鸡蛋黄粉 制品', '规格：20kg/袋', '保质期：12个月'])
    assert job['fields']['material_name'] == '鸡蛋黄粉制品'
    assert job['conflicts']['material_name'] == ['鸡蛋黄粉制品']


def test_gateway_heading_identifies_a_name_without_a_known_product_ending(client):
    bootstrap(client)
    ledger = new_ledger(client)
    previous = run_label(client, ledger, ['合格'])
    client.app.state.scan_image = lambda _: {
        'texts': ['增稠复合剂', '规格：1kg', '保质期：12个月'], 'boxes': [],
        'raw_text': '# 增稠复合剂\n\n规格：1kg\n\n保质期：12个月',
    }
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': previous['image_ids'], 'cloud_enabled': False}).json()
    for _ in range(100):
        job = client.get(f'/api/recognition/{job["id"]}').json()
        if job['local_status'] in {'done', 'failed'}:
            break
        time.sleep(.02)
    assert job['local_status'] == 'done'
    assert job['fields']['material_name'] == '增稠复合剂'
    assert job['conflicts']['material_name'] == ['增稠复合剂']


@pytest.mark.parametrize('texts,expected', [
    (['红日', '食品添加剂', '组织蛋白', '生产商：示例食品有限公司', '配料表：大豆蛋白、食用油'], '组织蛋白'),
    (['营养成分表', '蛋白质', '脂肪', '碳水化合物', '每100g', '生产用植物油', '请置于阴凉干燥处'], '生产用植物油'),
    (['# 红日', '鸡蛋黄粉制品', '生产地址：安徽省亳州市工业园'], '鸡蛋黄粉制品'),
])
def test_name_evidence_does_not_confuse_brand_instructions_or_nutrition_with_product(client, texts, expected):
    bootstrap(client)
    job = run_label(client, new_ledger(client), texts)
    assert job['fields']['material_name'] == expected
    assert job['conflicts']['material_name'] == [expected]


def test_explicit_name_preserves_unknown_ending_and_all_conflicting_labels(client):
    bootstrap(client)
    ledger = new_ledger(client)
    single = run_label(client, ledger, ['品名：蛋白质', '# 广美科', '保质期：12个月'])
    assert single['fields']['material_name'] == '蛋白质'
    assert not single['conflicts'].get('material_name')
    multiple = run_label(client, ledger, ['品名：复合稳定剂', '产品名称：复合增稠剂', '品名：复合稳定剂'])
    assert multiple['fields']['material_name'] == '复合稳定剂'
    assert multiple['conflicts']['material_name'] == ['复合稳定剂', '复合增稠剂']


def test_company_brand_heading_is_not_used_when_product_title_was_not_read(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), [
        '## Angel安琪', '保质期：24个月', '安琪酵母股份有限公司',
        '生产商：安琪酵母（宜昌）有限公司',
    ])
    assert not job['fields'].get('material_name')
    assert not job['conflicts'].get('material_name')


def test_name_with_model_has_one_candidate_and_matches_checked_history(client):
    bootstrap(client)
    ledger = new_ledger(client)
    saved = client.post(f'/api/ledgers/{ledger}/records', json={
        'fields': {'material_name': '鸡蛋黄粉制品 A型', 'company_name': '确认食品有限公司'},
        'inspection_enabled': True,
        'items': [{'name': '水分', 'standard': '≤0.5%', 'result': '0.2%', 'conclusion': '合格'}],
    })
    assert saved.status_code == 201, saved.text
    record = saved.json()
    checked = client.post(f'/api/records/{record["id"]}/check', json={'version': record['version']})
    assert checked.status_code == 200, checked.text
    job = run_label(client, ledger, ['鸡蛋黄粉制品', '型号：A型', '规格：20kg/袋'])
    assert job['fields']['material_name'] == '鸡蛋黄粉制品 A型'
    assert job['conflicts']['material_name'] == ['鸡蛋黄粉制品 A型']
    assert job['review_suggestions']['fields']['material_name'] == '鸡蛋黄粉制品 A型'
    assert job['review_suggestions']['sources'][0]['record_id'] == record['id']
    assert job['review_suggestions']['inspection']['items'][0]['result'] == '0.2%'


def test_reference_section_heading_is_not_a_competing_material_name(client):
    bootstrap(client)
    job = run_label(client, new_ledger(client), ['## L-精氨酸', '## 以下资料仅供参考', '保质期：2年'])
    assert job['fields']['material_name'] == 'L-精氨酸'
    assert job['conflicts']['material_name'] == ['L-精氨酸']
