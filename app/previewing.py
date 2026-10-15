"""Render the actual Office exports as PDFs for browser preview."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from jinja2 import TemplateError
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app import template_conversion
from app.exporting import excel_bytes, word_bytes
from app.models import Ledger, User
from app.personal_templates import decode_template
from app.schemas import ExportInput


def office_pdf(data: bytes, extension: str) -> bytes:
    if extension in {'doc', 'docx', 'rtf'}:
        kind = 'docx'
    elif extension in {'xls', 'xlsx', 'csv'}:
        kind = 'xlsx'
    else:
        raise HTTPException(422, '该文档类型不支持PDF预览')
    with TemporaryDirectory(prefix='office-preview-') as temporary:
        directory = Path(temporary)
        source = directory / ('source.' + extension)
        destination = directory / 'source.pdf'
        source.write_bytes(data)
        executable = template_conversion._libreoffice()
        timeout_message = '文档预览转换超时，请稍后重试或下载原文件查看'
        if executable:
            filter_name = 'pdf:writer_pdf_Export' if kind == 'docx' else 'pdf:calc_pdf_Export'
            template_conversion._run_converter(
                [executable, '-env:UserInstallation=' + (directory / 'profile').as_uri(), '--headless',
                 '--convert-to', filter_name, '--outdir', str(directory), str(source)], directory,
                timeout_message=timeout_message)
        office_available = template_conversion._office_available(kind)
        if not destination.exists() and office_available:
            command, environment = template_conversion._office_command(source, destination, kind, directory, pdf=True)
            template_conversion._run_converter(command, directory, environment=environment, timeout_message=timeout_message)
        if not destination.exists():
            if not executable and not office_available:
                raise HTTPException(503, '服务器未安装PDF转换工具，请配置LibreOffice或Microsoft Office后重试')
            raise HTTPException(422, '文档无法生成预览，请确认文件未加密且可在Office中正常打开')
        return destination.read_bytes()


def register_preview_routes(app, db, current_user, export_records):
    @app.post('/api/previews/{kind}')
    def preview_export(kind: str, body: ExportInput, request: Request,
                       user: User = Depends(current_user), session: Session = Depends(db)):
        if kind not in {'docx', 'xlsx'}:
            raise HTTPException(404, '预览类型不存在')
        rows = export_records(body, session)
        if kind == 'docx' and any(not row.inspection_enabled for row in rows):
            raise HTTPException(409, '所选记录中有未检验记录，请取消勾选未检验记录后预览 Word')
        template = decode_template(body.template_base64, kind)
        try:
            if kind == 'xlsx':
                names = {row.ledger_id: session.get(Ledger, row.ledger_id).name for row in rows}
                content = office_pdf(excel_bytes(rows, names, template), 'xlsx')
            elif len(rows) == 1:
                content = office_pdf(word_bytes(rows[0], template), 'docx')
            else:
                with PdfWriter() as writer:
                    for row in rows:
                        writer.append(BytesIO(office_pdf(word_bytes(row, template), 'docx')))
                    output = BytesIO()
                    writer.write(output)
                    content = output.getvalue()
        except TemplateError:
            raise HTTPException(422, 'Word模板占位符或语法不正确，请检查模板后重新预览') from None
        except (FileNotFoundError, OSError):
            raise HTTPException(503, '无法读取导出模板，请检查模板文件是否存在且已保存') from None
        request.state.audit_details = {'record_ids': [row.id for row in rows], 'kind': kind}
        return Response(content, media_type='application/pdf', headers={
            'Content-Disposition': f'inline; filename="preview-{kind}.pdf"',
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
        })
