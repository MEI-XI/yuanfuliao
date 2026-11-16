from pathlib import Path
from conftest import bootstrap


def test_storage_requires_admin_and_counts_files(client, monkeypatch, tmp_path):
    assert client.get('/api/storage-usage').status_code == 401
    bootstrap(client)
    root = tmp_path / 'data'
    (root / 'images').mkdir(parents=True, exist_ok=True)
    (root / 'images' / 'sample.jpg').write_bytes(b'x' * 123)
    (root / 'report-attachments').mkdir(exist_ok=True)
    (root / 'report-attachments' / 'report.pdf').write_bytes(b'y' * 456)
    response = client.get('/api/storage-usage')
    assert response.status_code == 200
    result = response.json()
    categories = {row['key']: row for row in result['categories']}
    assert not {'development_temp', 'python_runtime', 'frontend_dependencies', 'research', 'backups'} & categories.keys()
    assert categories['application']['bytes'] > 0
    assert 'configuration' in categories
    assert categories['images']['bytes'] == 123
    assert categories['reports']['bytes'] == 456
    assert result['database_bytes'] > 0
    assert result['disk']['total'] >= result['disk']['free'] > 0
    client.post('/api/users', json={'username': 'viewer', 'password': 'test-password-123', 'role': 'user'})
    client.post('/api/login', json={'username': 'viewer', 'password': 'test-password-123'})
    assert client.get('/api/storage-usage').status_code == 403


def test_only_old_owned_conversion_directories_are_cleaned(tmp_path, monkeypatch):
    import os, time
    from app.storage_usage import temporary_root, purge_stale_temporary_files
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'data'))
    root = temporary_root()
    old = root / 'office-preview-old'; old.mkdir(); (old / 'source.docx').write_bytes(b'regenerate')
    fresh = root / 'office-preview-active'; fresh.mkdir()
    unknown = root / 'research'; unknown.mkdir(); (unknown / 'keep.txt').write_bytes(b'keep')
    stamp = time.time() - 8 * 86400
    os.utime(old, (stamp, stamp)); os.utime(unknown, (stamp, stamp))
    assert purge_stale_temporary_files() == 1
    assert not old.exists()
    assert fresh.exists() and unknown.exists()
