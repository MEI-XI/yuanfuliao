from conftest import bootstrap
from test_records import new_ledger
from uuid import uuid4


def test_invalid_record_dates_explain_field_and_correction_and_allow_resave(client):
    bootstrap(client)
    ledger = new_ledger(client)
    body = {'fields': {'material_name': '日期核对样本', 'production_dates': ['2026-02-30']}}
    response = client.post(f'/api/ledgers/{ledger}/records', json=body)
    assert response.status_code == 422
    detail = response.json()['detail']
    assert isinstance(detail, str)
    assert '生产日期第1项' in detail
    assert '有效日期' in detail
    assert '修改后重新保存' in detail
    body['fields']['production_dates'] = ['2026-02-28']
    assert client.post(f'/api/ledgers/{ledger}/records', json=body).status_code == 201


def test_validation_identifies_batch_position_and_material_length(client):
    bootstrap(client)
    response = client.post('/api/materials', json={'name': '长' * 201})
    assert response.status_code == 422
    assert '物料名称' in response.json()['detail']
    assert '200' in response.json()['detail']
    ledger = new_ledger(client)
    response = client.post(f'/api/ledgers/{ledger}/records/batch', json={
        'request_id': str(uuid4()), 'records': [{}, {'fields': {'production_dates': ['错误日期']}}]})
    assert response.status_code == 422
    assert '本次提交第2条记录' in response.json()['detail']
    assert '生产日期第1项' in response.json()['detail']
