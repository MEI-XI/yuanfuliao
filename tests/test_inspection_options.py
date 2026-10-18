from conftest import bootstrap
from test_records import new_ledger


def test_inspection_choices_are_separate_persistent_and_can_be_removed_and_retyped(client):
    bootstrap(client)
    assert client.get('/api/inspection-options/result').json() == ['符合', '不符合']
    assert client.get('/api/inspection-options/conclusion').json() == ['合格', '不合格']
    ledger = new_ledger(client)
    record = client.post(f'/api/ledgers/{ledger}/records', json={
        'inspection_enabled': True,
        'items': [{'name': '水分', 'result': '0.2%', 'conclusion': '复检合格'}],
    }).json()
    assert '0.2%' in client.get('/api/inspection-options/result').json()
    assert '0.2%' not in client.get('/api/inspection-options/conclusion').json()
    assert '复检合格' in client.get('/api/inspection-options/conclusion').json()
    deleted = client.delete('/api/inspection-options/result', params={'name': '0.2%'})
    assert deleted.status_code == 200
    assert '0.2%' not in deleted.json()
    saved = client.get(f'/api/records/{record["id"]}').json()
    assert saved['items'][0]['result'] == '0.2%'
    client.patch(f'/api/records/{record["id"]}', json={'version': saved['version'], 'items': saved['items']})
    assert '0.2%' not in client.get('/api/inspection-options/result').json()
    restored = client.post('/api/inspection-options/result', params={'name': '0.2%'})
    assert restored.json().count('0.2%') == 1
    assert client.delete('/api/inspection-options/result', params={'name': '符合'}).status_code == 422
