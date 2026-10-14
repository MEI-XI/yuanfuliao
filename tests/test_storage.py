import os
from io import BytesIO
from pathlib import Path
from PIL import Image
from conftest import bootstrap
from test_records import new_ledger


def test_uploaded_photos_remain_readable_after_moving_data_directory(client, tmp_path, monkeypatch):
    bootstrap(client)
    ledger = new_ledger(client)
    photo = BytesIO()
    Image.new('RGB', (80, 100), 'white').save(photo, format='JPEG')
    image_id = client.post(f'/api/ledgers/{ledger}/images', files={'file': ('label.jpg', photo.getvalue(), 'image/jpeg')}).json()['id']
    original = Path(os.environ['DATA_DIR'])
    relocated = tmp_path / 'relocated-data'
    original.rename(relocated)
    monkeypatch.setenv('DATA_DIR', str(relocated))
    response = client.get(f'/api/images/{image_id}')
    assert response.status_code == 200
    assert response.content == photo.getvalue()
