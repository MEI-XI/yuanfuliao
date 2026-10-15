"""Saved report files attached to a record, with the record's edit permissions."""
import os
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

from fastapi import Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.models import Base, Record, User, utcnow
from app.recycle import record_expired


MAX_REPORT_SIZE = 20 * 1024 * 1024
MEDIA_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
    '.pdf': 'application/pdf', '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.txt': 'text/plain', '.csv': 'text/csv', '.rtf': 'application/rtf',
}
OFFICE_EXTENSIONS = {'.doc', '.docx', '.xls', '.xlsx', '.rtf', '.csv'}


class ReportAttachment(Base):
    __tablename__ = 'report_attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey('records.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    filename: Mapped[str] = mapped_column(String(250))
    storage_key: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def report_attachment_path(storage_key):
    return Path(os.getenv('DATA_DIR', 'data')) / 'report-attachments' / storage_key


def attachment_view(item):
    return {key: getattr(item, key) for key in ('id', 'record_id', 'owner_id', 'filename', 'media_type', 'size', 'created_at')}


def _filename(value):
    name = (value or '').replace('\\', '/').rsplit('/', 1)[-1]
    name = ''.join(character for character in name if ord(character) >= 32 and ord(character) != 127).strip()
    suffix = Path(name).suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise HTTPException(422, '请选择图片、PDF、Word、Excel或文本报告文件')
    return name[:250 - len(suffix)] + suffix if len(name) > 250 else name


def _text(data):
    if b'\x00' in data:
        raise ValueError('binary text')
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('gb18030')


def _validate(data, extension):
    if not data:
        raise HTTPException(422, '报告文件为空')
    try:
        if extension in {'.jpg', '.jpeg', '.png', '.webp'}:
            with Image.open(BytesIO(data)) as image:
                expected = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}[extension]
                if image.format != expected:
                    raise ValueError('image format')
                image.verify()
        elif extension == '.pdf':
            if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:
                raise ValueError('pdf signature')
        elif extension in {'.docx', '.xlsx'}:
            with ZipFile(BytesIO(data)) as package:
                entries = package.infolist()
                expected = 'word/document.xml' if extension == '.docx' else 'xl/workbook.xml'
                if len(entries) > 3000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
                    raise ValueError('expanded size')
                if expected not in package.namelist() or '[Content_Types].xml' not in package.namelist():
                    raise ValueError('office package')
        elif extension in {'.doc', '.xls'}:
            if not data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
                raise ValueError('office signature')
        elif extension == '.rtf':
            if not data.lstrip().startswith(b'{\\rtf'):
                raise ValueError('rtf signature')
        else:
            _text(data)
    except (ValueError, UnicodeError, BadZipFile, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, '报告文件损坏或内容与扩展名不符，请检查后重新上传') from exc


def register_report_attachment_routes(app, db, current_user, get_record, record_view, append_history):
    def editable(record_id, version, user, session):
        record = session.scalar(select(Record).where(Record.id == record_id).with_for_update())
        if record is None or record_expired(record):
            raise HTTPException(404, '记录不存在')
        if user.role not in ('admin', 'superadmin') and record.creator_id != user.id:
            raise HTTPException(403, '只能修改自己创建的记录的报告附件')
        if record.status == 'void':
            raise HTTPException(409, '作废记录不能修改')
        if record.version != version:
            raise HTTPException(409, '记录已被修改，请重新打开后核对')
        return record

    def change_record(record, user, action, session):
        record.version += 1
        record.updated_at = utcnow()
        record.status, record.checker_id, record.checked_at = 'pending', None, None
        append_history(record, user, action, session)

    def metadata(record):
        return {'record_version': record.version, **{key: getattr(record, key) for key in ('status', 'checker_id', 'checked_at', 'updated_at')}}

    def get_attachment(attachment_id, session):
        attachment = session.get(ReportAttachment, attachment_id)
        if attachment is None:
            raise HTTPException(404, '报告附件不存在')
        get_record(attachment.record_id, session)
        return attachment

    def existing_file(attachment):
        path = report_attachment_path(attachment.storage_key)
        if not path.is_file():
            raise HTTPException(404, '报告文件不存在')
        return path

    @app.get('/api/records/{record_id}/reports')
    def reports(record_id: int, user: User = Depends(current_user), session: Session = Depends(db)):
        get_record(record_id, session)
        return [attachment_view(item) for item in session.scalars(
            select(ReportAttachment).where(ReportAttachment.record_id == record_id).order_by(ReportAttachment.id))]

    @app.post('/api/records/{record_id}/reports', status_code=201)
    def upload_report(record_id: int, file: UploadFile, request: Request, version: int = Form(..., ge=1),
                      user: User = Depends(current_user), session: Session = Depends(db)):
        filename = _filename(file.filename)
        data = file.file.read(MAX_REPORT_SIZE + 1)
        if len(data) > MAX_REPORT_SIZE:
            raise HTTPException(413, '单个报告文件不能超过20 MiB')
        extension = Path(filename).suffix.lower()
        _validate(data, extension)
        record = editable(record_id, version, user, session)
        attachment = ReportAttachment(record_id=record.id, owner_id=user.id, filename=filename,
            storage_key=uuid.uuid4().hex + extension, media_type=MEDIA_TYPES[extension], size=len(data))
        path = report_attachment_path(attachment.storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(data)
            session.add(attachment)
            change_record(record, user, 'report_uploaded', session)
            session.commit()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        request.state.audit_details = {'record_id': record.id, 'filename': filename}
        return {'attachment': attachment_view(attachment), **metadata(record)}

    @app.get('/api/reports/{attachment_id}/file')
    def report_file(attachment_id: int, download: bool = False, user: User = Depends(current_user), session: Session = Depends(db)):
        attachment = get_attachment(attachment_id, session)
        inline = not download and (attachment.media_type.startswith('image/') or attachment.media_type == 'application/pdf')
        return FileResponse(existing_file(attachment), media_type=attachment.media_type, filename=attachment.filename,
            content_disposition_type='inline' if inline else 'attachment',
            headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})

    @app.get('/api/reports/{attachment_id}/preview')
    def preview_report(attachment_id: int, user: User = Depends(current_user), session: Session = Depends(db)):
        attachment = get_attachment(attachment_id, session)
        path = existing_file(attachment)
        extension = Path(attachment.filename).suffix.lower()
        headers = {'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'}
        if extension in OFFICE_EXTENSIONS:
            from app.previewing import office_pdf
            data = office_pdf(path.read_bytes(), extension.lstrip('.'))
            headers['Content-Disposition'] = "inline; filename*=utf-8''" + quote(Path(attachment.filename).stem + '.pdf')
            return Response(data, media_type='application/pdf', headers=headers)
        if extension == '.txt':
            return PlainTextResponse(_text(path.read_bytes()), headers=headers)
        return FileResponse(path, media_type=attachment.media_type, filename=attachment.filename,
                            content_disposition_type='inline', headers=headers)

    @app.delete('/api/reports/{attachment_id}')
    def delete_report(attachment_id: int, request: Request, version: int = Query(..., ge=1),
                      user: User = Depends(current_user), session: Session = Depends(db)):
        attachment = get_attachment(attachment_id, session)
        record = editable(attachment.record_id, version, user, session)
        path = report_attachment_path(attachment.storage_key)
        filename = attachment.filename
        session.delete(attachment)
        change_record(record, user, 'report_deleted', session)
        session.commit()
        path.unlink(missing_ok=True)
        request.state.audit_details = {'record_id': record.id, 'filename': filename}
        return metadata(record)
