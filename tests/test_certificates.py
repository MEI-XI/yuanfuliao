from conftest import bootstrap
from test_records import new_ledger


def test_certificate_choices_remember_saved_text_after_record_is_edited(client):
    bootstrap(client)
    defaults = client.get('/api/certificate-options')
    assert defaults.status_code == 200
    assert defaults.json() == ['出厂检验报告', '检疫证', '肉品品质合格证', '进关检疫证', '报关单']
    ledger = new_ledger(client)
    record = client.post(f'/api/ledgers/{ledger}/records', json={'fields': {'certificates': '检疫证、原产地证；自定义合格单'}}).json()
    assert record['fields']['certificates'] == '检疫证、原产地证；自定义合格单'
    client.patch(f'/api/records/{record["id"]}', json={'version': record['version'], 'fields': {'certificates': ''}})
    options = client.get('/api/certificate-options').json()
    assert '原产地证' in options
    assert '自定义合格单' in options
    assert options.count('检疫证') == 1


def test_delete_certificate_history_keeps_records_and_does_not_return_on_save(client):
    bootstrap(client)
    ledger = new_ledger(client)
    record = client.post(f'/api/ledgers/{ledger}/records', json={'fields': {'certificates': '原产地证'}}).json()
    deleted = client.delete('/api/certificate-options', params={'name': '原产地证'})
    assert deleted.status_code == 200
    assert '原产地证' not in deleted.json()
    assert client.get(f'/api/records/{record["id"]}').json()['fields']['certificates'] == '原产地证'
    client.patch(f'/api/records/{record["id"]}', json={'version': record['version'], 'fields': record['fields']})
    assert '原产地证' not in client.get('/api/certificate-options').json()
    assert client.delete('/api/certificate-options', params={'name': '检疫证'}).status_code == 422
    restored = client.post('/api/certificate-options', params={'name': '原产地证'})
    assert restored.status_code == 200
    assert restored.json().count('原产地证') == 1
    assert client.post('/api/certificate-options', params={'name': '原产地证'}).json().count('原产地证') == 1
