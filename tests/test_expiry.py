import pytest

from conftest import bootstrap


@pytest.mark.parametrize('production_dates, shelf_life, expected_shelf_life, expected', [
    (['2026-01-14'], '12个月', '12个月', '2027-01-13'),
    (['2026-01-31'], '1个月', '1个月', '2026-02-27'),
    (['2024-02-29'], '1年', '12个月', '2025-02-27'),
    (['2024-02-01'], '29天', '29天', '2024-02-29'),
    (['2026-02-01'], '1天', '1天', '2026-02-01'),
    (['2026-02-14', '2026-01-14'], '12个月', '12个月', '2027-01-13'),
])
def test_expiry_uses_calendar_duration_inclusive_of_production_day(client, production_dates, shelf_life, expected_shelf_life, expected):
    bootstrap(client)
    response = client.post('/api/shelf-life/derive', json={
        'production_dates': production_dates, 'shelf_life': shelf_life,
    })
    assert response.status_code == 200, response.text
    assert response.json()['expiry_date'] == expected
    assert response.json()['shelf_life'] == expected_shelf_life


@pytest.mark.parametrize('production_dates, expiry_date, expected', [
    (['2026-01-14'], '2027-01-13', '12个月'),
    (['2026-01-14'], '2026-02-12', '30天'),
    (['2026-01-31'], '2026-02-27', '1个月'),
    (['2026-02-14', '2026-01-14'], '2027-01-13', '12个月'),
])
def test_printed_expiry_fills_only_missing_shelf_life(client, production_dates, expiry_date, expected):
    bootstrap(client)
    response = client.post('/api/shelf-life/derive', json={
        'production_dates': production_dates, 'expiry_date': expiry_date,
    })
    assert response.status_code == 200, response.text
    assert response.json()['expiry_date'] == expiry_date
    assert response.json()['shelf_life'] == expected


def test_expiry_derivation_preserves_manual_values_and_warns_on_conflicting_dates(client):
    bootstrap(client)
    response = client.post('/api/shelf-life/derive', json={
        'production_dates': ['2026-01-14'], 'shelf_life': '12个月', 'expiry_date': '2027-01-14',
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['expiry_date'] == '2027-01-14'
    assert result['shelf_life'] == '12个月'
    assert result['warnings']


@pytest.mark.parametrize('values', [
    {'shelf_life': '12个月'},
    {'production_dates': ['2026-01-14'], 'shelf_life': '常温12个月，冷藏18个月'},
    {'production_dates': ['2026-01-14'], 'shelf_life': '0个月'},
    {'production_dates': ['2026-01-14'], 'expiry_date': '2026-01-13'},
])
def test_missing_or_ambiguous_expiry_inputs_require_review(client, values):
    bootstrap(client)
    response = client.post('/api/shelf-life/derive', json=values)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['shelf_life'] == values.get('shelf_life', '')
    assert result['expiry_date'] == values.get('expiry_date')
    assert result['warnings']
