import time
from io import BytesIO

from PIL import Image

from conftest import bootstrap
from test_records import new_ledger


def run_label(client, ledger, texts):
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': texts, 'boxes': []}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        job = client.get(f'/api/recognition/{job["id"]}').json()
        if job['local_status'] in {'done', 'failed'}:
            break
        time.sleep(.02)
    assert job['local_status'] == 'done'
    return job


def test_checked_corrections_suggest_stable_fields_only_and_with_source(client):
    bootstrap(client)
    ledger = new_ledger(client)
    texts = ['品名：甘氮酸', '生产商：测试食品有限公司', '规格：25kg/袋', '生产日期：20261001']
    first = run_label(client, ledger, texts)
    saved = client.post(f'/api/ledgers/{ledger}/records', json={
        'recognition_job_id': first['id'], 'image_ids': first['image_ids'],
        'fields': first['fields'] | {'material_name': '甘氨酸', 'address': '测试路1号', 'address_source': 'manufacturer', 'received_quantity': '100kg'},
        'items': [{'name': '水分', 'result': '合格'}],
    }).json()
    next_job = run_label(client, ledger, texts)
    assert next_job['review_suggestions']['fields'] == {}
    checked = client.post(f'/api/records/{saved["id"]}/check', json={'version': saved['version']}).json()
    suggestion = client.get(f'/api/recognition/{next_job["id"]}').json()['review_suggestions']
    assert suggestion['fields']['material_name'] == '甘氨酸'
    assert suggestion['fields']['address'] == '测试路1号'
    assert suggestion['fields']['address_source'] == 'manufacturer'
    assert suggestion['sources'][0]['record_id'] == saved['id']
    assert suggestion['sources'][0]['version'] == checked['version']
    assert not {'production_dates', 'arrival_date', 'received_quantity', 'result', 'sensory'} & suggestion['fields'].keys()
    client.patch(f'/api/records/{saved["id"]}', json={'version': checked['version'], 'fields': {'address': '待重新核对'}})
    assert client.get(f'/api/recognition/{next_job["id"]}').json()['review_suggestions']['fields'] == {}


def test_feedback_rejects_ambiguous_contacts_different_specs_and_voided_records(client):
    bootstrap(client)
    ledger = new_ledger(client)
    texts = ['品名：甘氨酸', '生产商：测试食品有限公司', '规格：25kg/袋']
    records = []
    for phone in ['0311-11111111', '0311-22222222']:
        job = run_label(client, ledger, texts)
        saved = client.post(f'/api/ledgers/{ledger}/records', json={
            'recognition_job_id': job['id'], 'image_ids': job['image_ids'],
            'fields': job['fields'] | {'contact': phone, 'contact_source': 'manufacturer'},
        }).json()
        records.append(client.post(f'/api/records/{saved["id"]}/check', json={'version': saved['version']}).json())
    matched = run_label(client, ledger, texts)
    assert 'contact' not in matched['review_suggestions']['fields']
    assert 'contact_source' not in matched['review_suggestions']['fields']
    assert len(matched['review_suggestions']['conflicts']['contact']) == 2
    different = run_label(client, ledger, texts[:2] + ['规格：20kg/袋'])
    assert different['review_suggestions']['fields'] == {}
    client.post(f'/api/records/{records[0]["id"]}/void', json={'version': records[0]['version']})
    remaining = client.get(f'/api/recognition/{matched["id"]}').json()['review_suggestions']
    assert remaining['fields']['contact'] == '0311-22222222'
    assert len(remaining['sources']) == 1


def test_conflicting_photo_identities_do_not_activate_history_autofill(client):
    bootstrap(client)
    ledger = new_ledger(client)
    texts = ['品名：甘氨酸', '生产商：测试食品有限公司', '规格：25kg/袋']
    first = run_label(client, ledger, texts)
    saved = client.post(f'/api/ledgers/{ledger}/records', json={
        'recognition_job_id': first['id'], 'image_ids': first['image_ids'],
        'fields': first['fields'] | {'address': '仅甘氨酸的地址'},
    }).json()
    client.post(f'/api/records/{saved["id"]}/check', json={'version': saved['version']})
    other = run_label(client, ledger, ['品名：精氨酸', *texts[1:]])
    images = first['image_ids'] + other['image_ids']
    readings = iter([texts, ['品名：精氨酸', *texts[1:]]])
    client.app.state.scan_image = lambda path: {'texts': next(readings), 'boxes': []}
    mixed = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': images, 'cloud_enabled': False}).json()
    for _ in range(100):
        mixed = client.get(f'/api/recognition/{mixed["id"]}').json()
        if mixed['local_status'] == 'done':
            break
        time.sleep(.02)
    assert mixed['conflicts']['material_name'] == ['甘氨酸', '精氨酸']
    assert mixed['review_suggestions']['fields'] == {}
    mixed_record = client.post(f'/api/ledgers/{ledger}/records', json={
        'recognition_job_id': mixed['id'], 'image_ids': mixed['image_ids'],
        'fields': mixed['fields'] | {'material_name': '精氨酸', 'address': '精氨酸的另一地址'},
    }).json()
    client.post(f'/api/records/{mixed_record["id"]}/check', json={'version': mixed_record['version']})
    clean = run_label(client, ledger, texts)['review_suggestions']
    assert [source['record_id'] for source in clean['sources']] == [saved['id']]
    assert clean['fields']['material_name'] == '甘氨酸'


def test_duplicate_inflight_recognition_reuses_job_and_queue_clears(client):
    from threading import Event
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    ids = [client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id'] for _ in range(2)]
    started, release = Event(), Event()
    def scan(path):
        started.set()
        assert release.wait(5)
        return {'texts': ['品名：甘氨酸'], 'boxes': []}
    client.app.state.scan_image = scan
    try:
        first = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [ids[0]], 'cloud_enabled': False}).json()
        assert started.wait(2)
        duplicate = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [ids[0]], 'cloud_enabled': False}).json()
        assert duplicate['id'] == first['id']
        second = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [ids[1]], 'cloud_enabled': False}).json()
        queued = client.get(f'/api/recognition/{second["id"]}').json()
        assert queued['local_status'] == 'queued'
        assert queued['queue_ahead'] == 1
    finally:
        release.set()
    for _ in range(100):
        response = client.get(f'/api/recognition/{second["id"]}')
        result = response.json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    assert result['local_status'] == 'done'
    assert result['queue_ahead'] == 0
    assert response.headers['cache-control'] == 'no-store'


def test_cloud_failure_keeps_local_result_and_does_not_prevent_saving(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new("RGB", (80, 100), "white").save(photo, format="JPEG")
    upload = client.post(f"/api/ledgers/{ledger}/images", files={"file": ("photo.jpg", photo.getvalue(), "image/jpeg")})
    assert upload.status_code == 201
    image_id = upload.json()["id"]
    # Replace only model inference / the external cloud boundary; parsing, tasks,
    # persistence, permissions and record saving all use their real implementations.
    client.app.state.scan_image = lambda path: {"texts": ["产品名称：甘氨酸", "生产日期：2026年01月14日", "规格：25kg/袋", "合格"], "boxes": []}
    def unavailable(paths, texts):
        raise TimeoutError("provider unavailable")
    client.app.state.cloud_extract = unavailable
    job = client.post(f"/api/ledgers/{ledger}/recognition", json={"image_ids": [image_id], "cloud_enabled": True}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result["local_status"] == "done" and result["cloud_status"] == "failed":
            break
        time.sleep(0.02)
    assert result["fields"]["material_name"] == "甘氨酸"
    assert result["fields"]["production_dates"] == ["2026-01-14"]
    assert "received_quantity" not in result["fields"]
    assert "sensory" not in result["fields"]
    assert result["cloud_status"] == "failed"
    saved = client.post(f"/api/ledgers/{ledger}/records", json={"fields": result["fields"], "image_ids": [image_id]})
    assert saved.status_code == 201
    assert client.get(f'/api/records/{saved.json()["id"]}').json()["image_ids"] == [image_id]
    client.post("/api/logout")
    assert client.get(f"/api/images/{image_id}").status_code == 401


def test_local_ocr_does_not_mistake_manufacturer_for_material_or_watermark_for_date(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['河北华阳生物科技有限公司', '合格', '规', '格：25kg/袋（桶）', '生产日期：', '2026/10/07 09:40'], 'boxes': []}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    assert result['fields'].get('material_name', '') == ''
    assert result['fields'].get('production_dates', []) == []
    assert result['fields']['specification'] == '25kg/袋（桶）'


def test_supplier_preferred_and_compact_production_date_extracted_without_business_guesses(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['生产商：乙工厂', '供应商：甲商行', '供应商地址：郑州市测试路1号', '供应商电话：0371-12345678', '产品名称：L-半胱氨酸', '净含量：25kg', '生产日期、批号：20261001-1', '2026/10/08 16:06'], 'boxes': []}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    assert result['fields']['company_name'] == '甲商行'
    assert result['fields']['address_source'] == 'supplier'
    assert result['fields']['contact_source'] == 'supplier'
    assert result['fields']['production_dates'] == ['2026-10-01']
    assert result['fields']['specification'] == '25kg'
    assert 'received_quantity' not in result['fields']


def test_saved_record_retains_recognition_evidence_for_all_viewers(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['品名：甘氨酸'], 'boxes': []}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    response = client.post(f'/api/ledgers/{ledger}/records', json={'image_ids': [image_id], 'recognition_job_id': job['id']})
    assert response.status_code == 201
    assert client.get(f'/api/records/{response.json()["id"]}').json()['recognition_job_id'] == job['id']
    client.post('/api/users', json={'username': 'reader', 'password': 'reader-password', 'role': 'user'})
    client.post('/api/login', json={'username': 'reader', 'password': 'reader-password'})
    evidence = client.get(f'/api/recognition/{job["id"]}')
    assert evidence.status_code == 200
    assert evidence.json()['evidence'][0]['texts'] == ['品名：甘氨酸']


def test_label_title_and_split_date_are_extracted_instead_of_brand(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['合格', 'L-精氨酸', '佳斯特', '净', '含量：25kg', '生产日期：', '2026年09月19日', '保质期：', '2年'], 'boxes': []}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    assert result['fields']['material_name'] == 'L-精氨酸'
    assert result['fields']['specification'] == '25kg'
    assert result['fields']['shelf_life'] == '2年'
    assert result['fields']['production_dates'] == ['2026-09-19']


def test_split_product_name_follows_label_row_not_nearer_material_row(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['产品名称：', '透明卷膜150mm', '同步NY/PE'], 'boxes': [
        [[0,0],[80,0],[80,20],[0,20]], [[100,0],[500,0],[500,20],[100,20]], [[100,40],[220,40],[220,60],[100,60]]
    ]}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    assert result['fields']['material_name'] == '透明卷膜150mm'


def test_crop_phone_keeps_manufacturer_source_with_supplier_name(client):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    client.app.state.scan_image = lambda path: {'texts': ['供应商：甲商行'], 'boxes': [], 'supplements': [{'texts': ['生产商电话：0311-12345678'], 'boxes': [], 'kind': 'crop'}]}
    job = client.post(f'/api/ledgers/{ledger}/recognition', json={'image_ids': [image_id], 'cloud_enabled': False}).json()
    for _ in range(100):
        result = client.get(f'/api/recognition/{job["id"]}').json()
        if result['local_status'] == 'done':
            break
        time.sleep(.02)
    assert result['fields']['company_name'] == '甲商行'
    assert result['fields']['contact'] == '0311-12345678'
    assert result['fields']['contact_source'] == 'manufacturer'
