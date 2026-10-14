from io import BytesIO

from openpyxl import load_workbook
from docx import Document
from zipfile import ZipFile

from conftest import bootstrap
from test_records import new_ledger


def test_excel_preserves_13_columns_company_sheets_blanks_and_manufacturer_source(client):
    bootstrap(client)
    first_ledger = new_ledger(client)
    second_ledger = new_ledger(client, "味源食品")
    first = client.post(f"/api/ledgers/{first_ledger}/records", json={"fields": {
        "arrival_date": None, "material_name": "甘氨酸", "company_name": "甲商行",
        "address": "乙工厂地址", "address_source": "manufacturer", "contact": "0311-12345678",
        "contact_source": "manufacturer", "production_dates": ["2026-01-14", "2026-01-15"]
    }})
    assert first.status_code == 201
    second = client.post(f"/api/ledgers/{second_ledger}/records", json={}).json()
    ids = [first.json()["id"], second["id"]]
    assert client.post("/api/exports/xlsx", json={"record_ids": ids}).status_code == 409
    response = client.post("/api/exports/xlsx", json={"record_ids": ids, "include_pending": True})
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["青山科技", "味源食品"]
    sheet = workbook["青山科技"]
    assert sheet.max_column == 13
    assert [sheet.cell(3, col).value for col in range(1, 10)] == [
        None, "甘氨酸", "2026.01.14\n2026.01.15", None, "甲商行", "生产商：乙工厂地址", "生产商：0311-12345678", None, None
    ]
    client.post(f'/api/records/{ids[0]}/void', json={"version": 1})
    assert client.post("/api/exports/xlsx", json={"record_ids": ids, "include_pending": True}).status_code == 409


def test_word_uses_dotted_production_date_one_report_per_record_and_current_template_signatures(client):
    bootstrap(client)
    ledger = new_ledger(client)
    saved = client.post(f"/api/ledgers/{ledger}/records", json={"fields": {
        "material_name": "甘氨酸", "production_dates": ["2026-01-14"]},
        "items": [{"name": "水分", "standard": "≤0.2%", "result": "0.1%", "conclusion": "符合"}]
    }).json()
    response = client.post("/api/exports/docx", json={"record_ids": [saved["id"]], "include_pending": True})
    assert response.status_code == 200
    document = Document(BytesIO(response.content))
    content = document.element.xml
    assert "2026.01.14" in content and "甘氨酸" in content
    assert "0.1%" in content and "≤0.2%" in content
    assert "{{" not in content
    from app.exporting import template_dir
    with ZipFile(template_dir() / "检验报告.docx") as template_zip, ZipFile(BytesIO(response.content)) as output_zip:
        pictures = [name for name in template_zip.namelist() if name.startswith("word/media/")]
        assert pictures
        assert {name: template_zip.read(name) for name in pictures} == {name: output_zip.read(name) for name in pictures}
    second = client.post(f"/api/ledgers/{ledger}/records", json={}).json()
    batch = client.post("/api/exports/docx", json={"record_ids": [saved["id"], second["id"]], "include_pending": True})
    with ZipFile(BytesIO(batch.content)) as archive:
        assert len(archive.namelist()) == 2
        assert all(name.endswith(".docx") for name in archive.namelist())


def test_company_named_like_template_exports_exact_sheet_name(client):
    bootstrap(client)
    ledger = new_ledger(client, 'Sheet')
    record = client.post(f'/api/ledgers/{ledger}/records', json={}).json()
    response = client.post('/api/exports/xlsx', json={'record_ids': [record['id']], 'include_pending': True})
    assert load_workbook(BytesIO(response.content)).sheetnames == ['Sheet']


def test_word_preserves_inspection_unit_in_existing_project_column(client):
    bootstrap(client)
    ledger = new_ledger(client)
    record = client.post(f'/api/ledgers/{ledger}/records', json={'items': [{'name': '水分', 'standard': '≤0.2', 'unit': 'mg/kg', 'result': '0.1'}]}).json()
    response = client.post('/api/exports/docx', json={'record_ids': [record['id']], 'include_pending': True})
    assert '水分（mg/kg）' in Document(BytesIO(response.content)).element.xml
