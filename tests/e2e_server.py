"""Disposable PostgreSQL schema for browser tests. No production data changes."""
import os
import sys
import uuid
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
import uvicorn

root = Path(__file__).resolve().parents[1]
os.chdir(root)
os.environ['DATA_DIR'] = str(root / 'tmp' / 'e2e-uploads')
sys.path.insert(0, str(root))
from app.main import create_app

url = os.getenv("TEST_DATABASE_URL") or (root / "tmp/test-database-url.txt").read_text().strip()
schema = "e2e_" + uuid.uuid4().hex
with psycopg.connect(url, autocommit=True) as connection:
    connection.execute(f'CREATE SCHEMA "{schema}"')
scoped_url = url.replace("postgresql://", "postgresql+psycopg://", 1) + f"?options=-csearch_path%3D{schema}"
try:
    app = create_app(scoped_url)
    original_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def test_lifespan(application):
        async with original_lifespan(application):
            def scan(path):
                return {"texts": ["产品名称：甘氨酸", "生产日期：2026年01月14日"], "boxes": []}
            def cloud(paths, texts):
                time.sleep(1)
                return {"material_name": "云端建议名称"}
            application.state.scan_image = scan
            application.state.cloud_extract = cloud
            yield
    app.router.lifespan_context = test_lifespan
    uvicorn.run(app, host="127.0.0.1", port=8001)
finally:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
