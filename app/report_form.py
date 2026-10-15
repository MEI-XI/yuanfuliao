"""Fill the supplied plain inspection form without rebuilding its table or signatures."""
from copy import deepcopy
from io import BytesIO

from docx import Document
from docx.shared import Pt


def fill_plain_report(source, context):
    document = Document(BytesIO(source))
    xml = document.element.xml
    if '{{' in xml or '{%' in xml or not document.tables:
        return None
    table = document.tables[0]
    if (len(table.rows) != 7 or len(table.columns) != 4
            or '检品名称' not in table.cell(0, 0).text
            or '检验项目' not in table.cell(6, 0).text):
        return None
    fields = {(0, 1): 'material_name', (0, 3): 'company_name', (1, 1): 'batch_blank',
              (1, 3): 'specification', (2, 1): 'packaging', (2, 3): 'received_quantity',
              (3, 1): 'basis', (3, 3): 'production_dates', (4, 1): 'shelf_life', (4, 3): 'inspection_date'}
    for (row, col), key in fields.items():
        paragraph = table.cell(row, col).paragraphs[0]
        paragraph.clear().add_run(context.get(key) or '')
    table.cell(5, 0).paragraphs[0].clear().add_run('该公司是否提供内检报告：' + (context.get('internal_report') or ''))
    table.cell(5, 2).paragraphs[0].clear().add_run(context.get('report_reference') or '')
    cell = table.cell(6, 0)
    paragraphs = cell.paragraphs
    if len(paragraphs) < 7:
        return None
    rows = paragraphs[1:5]
    conclusion = paragraphs[5]
    # Reuse the existing paragraph metrics. Extra items are inserted before the
    # conclusion; the signature paragraph and its floating images stay intact.
    for _ in range(max(0, len(context['items']) - len(rows))):
        clone = deepcopy(rows[-1]._p)
        conclusion._p.addprevious(clone)
        from docx.text.paragraph import Paragraph
        rows.append(Paragraph(clone, cell))
    for index, paragraph in enumerate(rows):
        item = context['items'][index] if index < len(context['items']) else {}
        paragraph.clear()
        for position in (120, 283, 432):
            paragraph.paragraph_format.tab_stops.add_tab_stop(Pt(position))
        paragraph.add_run('\t'.join(item.get(key, '') for key in ('name', 'standard', 'result', 'conclusion')))
    # Clearing just text preserves any anchored objects in the conclusion too.
    for node in conclusion._p.xpath('.//w:t'):
        node.text = ''
    conclusion.add_run('结  论：' + (context.get('conclusion') or ''))
    output = BytesIO()
    document.save(output)
    return output.getvalue()
