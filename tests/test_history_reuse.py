from conftest import bootstrap
from test_records import new_ledger
from test_recognition import run_label


def test_repeated_recognition_matches_material_despite_missing_company_and_changed_spec_format(client):
    bootstrap(client)
    ledger = new_ledger(client)
    texts = ['品名：甘氨酸', '规格：25kg']
    original = run_label(client, ledger, texts)
    saved = client.post(f'/api/ledgers/{ledger}/records', json={
        'recognition_job_id': original['id'], 'image_ids': original['image_ids'],
        'inspection_enabled': True,
        'fields': {'material_name': '甘氨酸', 'company_name': '人工维护厂家', 'specification': '25公斤/袋',
                   'sensory': '白色粉末', 'sampling_items': '含量'},
        'items': [{'name': '含量', 'standard': '≥98.5%', 'result': '符合', 'conclusion': '合格'}],
    }).json()
    checked = client.post(f'/api/records/{saved["id"]}/check', json={'version': saved['version']}).json()
    repeated = run_label(client, ledger, texts + ['生产日期：2026.10.18', '保质期：24个月'])
    history = repeated['review_suggestions']
    assert history['sources'][0]['record_id'] == checked['id']
    assert history['fields']['company_name'] == '人工维护厂家'
    assert history['inspection']['items'][0]['result'] == '符合'
    # The same image bytes do not establish the material: OCR must identify it.
    different = run_label(client, ledger, ['品名：柠檬酸', '规格：25kg'])
    assert different['review_suggestions']['sources'] == []


def test_checked_history_includes_inspection_snapshot_but_never_old_batch_values(client):
    bootstrap(client)
    ledger = new_ledger(client)
    texts = ['品名：甘氨酸', '生产商：测试食品有限公司', '规格：25kg/袋']
    original = run_label(client, ledger, texts)
    record = client.post(f'/api/ledgers/{ledger}/records', json={
        'recognition_job_id': original['id'], 'image_ids': original['image_ids'], 'inspection_enabled': True,
        'fields': original['fields'] | {'arrival_date': '2025-01-01', 'production_dates': ['2024-12-01'],
            'shelf_life': '12个月', 'expiry_date': '2025-11-30', 'received_quantity': '100袋',
            'sensory': '白色粉末', 'certificates': '出厂检验报告', 'notes': '保存于阴凉处'},
        'items': [{'name': '含量', 'standard': '≥98.5%', 'result': '99.2%', 'conclusion': '合格'}],
        'report': {'basis': '甘氨酸标准', 'packaging': '纸塑袋', 'conclusion': '合格',
                   'batch_number': 'OLD-BATCH', 'inspection_date': '2025-01-01', 'internal_report': '是'},
    }).json()
    before = run_label(client, ledger, texts)
    assert before['review_suggestions'].get('inspection') is None
    client.post(f'/api/records/{record["id"]}/check', json={'version': record['version']})
    job = run_label(client, ledger, texts + ['生产日期：2026.10.01', '保质期：24个月', '到货数量：6袋'])
    history = job['review_suggestions']
    assert history['fields']['sensory'] == '白色粉末'
    assert history['fields']['certificates'] == '出厂检验报告'
    assert history['fields']['notes'] == '保存于阴凉处'
    assert not {'arrival_date', 'production_dates', 'shelf_life', 'expiry_date', 'received_quantity'} & history['fields'].keys()
    assert history['inspection']['items'][0]['result'] == '99.2%'
    assert history['inspection']['report'] == {'basis': '甘氨酸标准', 'packaging': '纸塑袋', 'conclusion': '合格', 'internal_report': '是'}
    assert history['inspection']['source_record_id'] == record['id']
    assert job['fields']['production_dates'] == ['2026-10-01']
    assert job['fields']['shelf_life'] == '24个月'
    assert job['fields']['received_quantity'] == '6袋'
    assert job['fields']['expiry_date'] == '2028-09-30'


def test_latest_checked_record_is_applied_as_a_whole_and_voided_history_is_excluded(client):
    bootstrap(client)
    ledger = new_ledger(client)
    texts = ['品名：甘氨酸', '生产商：测试食品有限公司', '规格：25kg/袋']
    records = []
    for result in ['符合', '不符合']:
        original = run_label(client, ledger, texts)
        saved = client.post(f'/api/ledgers/{ledger}/records', json={
            'recognition_job_id': original['id'], 'image_ids': original['image_ids'],
            'inspection_enabled': True, 'fields': original['fields'],
            'items': [{'name': '含量', 'standard': '≥98.5%', 'result': result}],
        }).json()
        records.append(client.post(f'/api/records/{saved["id"]}/check', json={'version': saved['version']}).json())
    job = run_label(client, ledger, texts)
    assert job['review_suggestions']['inspection']['items'][0]['result'] == '不符合'
    assert job['review_suggestions']['sources'][0]['record_id'] == records[1]['id']
    assert job['review_suggestions']['inspection_choices'] == []
    client.post(f'/api/records/{records[1]["id"]}/void', json={'version': records[1]['version']})
    updated = client.get(f'/api/recognition/{job["id"]}').json()
    assert updated['review_suggestions']['inspection']['items'][0]['result'] == '符合'
    assert len(updated['review_suggestions']['sources']) == 1


def test_shared_ocr_title_for_different_models_does_not_establish_same_material(client):
    bootstrap(client)
    ledger = new_ledger(client)
    for name in ['调味粉 A1', '调味粉 B2']:
        original = run_label(client, ledger, ['品名：调味粉'])
        saved = client.post(f'/api/ledgers/{ledger}/records', json={
            'fields': {'material_name': name, 'specification': '25kg'},
            'recognition_job_id': original['id'], 'image_ids': original['image_ids'],
        }).json()
        client.post(f'/api/records/{saved["id"]}/check', json={'version': saved['version']})
    unknown_model = run_label(client, ledger, ['品名：调味粉'])['review_suggestions']
    assert unknown_model['match_status'] == 'ambiguous'
    assert unknown_model['sources'] == []
    assert unknown_model['inspection'] is None
    known_model = run_label(client, ledger, ['品名：调味粉', '型号：A1'])['review_suggestions']
    assert known_model['fields']['material_name'] == '调味粉 A1'
    client.app.state.cloud_extract = lambda paths, texts: {'material_name': '调味粉'}
    model_with_generic_translation = run_label(client, ledger, ['品名：调味粉', '型号：A1'], cloud_enabled=True)['review_suggestions']
    assert model_with_generic_translation['fields']['material_name'] == '调味粉 A1'
