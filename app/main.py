import hashlib
import json
import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from jinja2 import TemplateError

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import create_engine, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, BatchSubmission, History, Ledger, LoginSession, Material, Partner, Photo, RecognitionJob, Record, Scheme, Setting, User, utcnow
from app.schemas import BatchRecordCreate, BatchVoidInput, CloudSettingInput, Credentials, ExportInput, LedgerInput, MaterialInput, PartnerInput, RecognitionInput, RecordChange, RecordCreate, SchemeInput, ShelfLifeInput, UserChange, UserCreate, VersionInput
from app.recycle import RecycleCleaner, record_expired, register_recycle_routes
from app.storage import photo_path
from app.credentials import encrypt_password, decrypt_password

passwords = PasswordHasher()


def user_view(user):
    return {"id": user.id, "username": user.username, "role": user.role, "active": user.active}


def record_view(item):
    from app.expiry import normalize_shelf_life
    result = {key: getattr(item, key) for key in ("id", "ledger_id", "creator_id", "fields", "status", "voided_at", "inspection_enabled", "version",
                                               "created_at", "updated_at", "checker_id", "checked_at", "material_id", "scheme_name", "items", "report", "image_ids", "recognition_job_id")}
    result['fields'] = item.fields | {'shelf_life': normalize_shelf_life(item.fields.get('shelf_life', ''))}
    return result


def create_app(database_url: str | None = None) -> FastAPI:
    load_dotenv()
    engine = create_engine(database_url or os.environ["DATABASE_URL"], pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(app):
        from alembic import command
        from alembic.config import Config
        migration = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
        with engine.begin() as connection:
            migration.attributes['connection'] = connection
            command.upgrade(migration, 'head')
        from app.recognition import LocalScanner, cloud_extract
        app.state.scan_image = LocalScanner()
        def configured_cloud(paths, texts):
            with Session(engine) as session:
                setting = session.get(Setting, "zhipu_key")
                api_key = setting.value if setting else os.getenv("ZHIPU_API_KEY", "")
            return cloud_extract(paths, texts, api_key)
        app.state.cloud_extract = configured_cloud
        app.state.local_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-ocr")
        app.state.cloud_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cloud-vision")
        with Session(engine) as session:
            for job in session.scalars(select(RecognitionJob).where(RecognitionJob.local_status.in_(["queued", "running"]))):
                job.local_status, job.error = "failed", "服务重启中断了识别，请重试"
            for job in session.scalars(select(RecognitionJob).where(RecognitionJob.cloud_status.in_(["queued", "running"]))):
                job.cloud_status, job.cloud_error = "failed", "服务重启中断了云端辅助，本地结果不受影响"
            session.commit()
        cleaner = RecycleCleaner(engine)
        cleaner.start()
        try:
            yield
        finally:
            cleaner.stop()
            app.state.local_pool.shutdown(wait=True)
            app.state.cloud_pool.shutdown(wait=True)
            engine.dispose()

    app = FastAPI(title="原辅料查验", lifespan=lifespan)
    app.state.engine = engine

    def db():
        with Session(engine) as session:
            yield session

    def current_user(request: Request, session: Session = Depends(db)):
        token = request.cookies.get("session", "")
        login = session.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
        user = session.get(User, login.user_id) if login and login.expires_at > utcnow() else None
        if not user or not user.active:
            raise HTTPException(401, "请先登录")
        request.state.audit_actor = (user.id, user.username)
        return user

    def administrator(user: User = Depends(current_user)):
        if user.role not in ("admin", "superadmin"):
            raise HTTPException(403, "此操作需要管理员权限")
        return user

    from app.audit import register_audit
    register_audit(app, engine, db, current_user)

    from app.maintenance import register_maintenance_routes
    register_maintenance_routes(app, db, administrator)

    @app.exception_handler(IntegrityError)
    async def duplicate(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": "名称已存在或关联数据有冲突"})

    @app.get("/api/setup")
    def setup_status(session: Session = Depends(db)):
        return {"required": session.scalar(select(User.id).limit(1)) is None}

    @app.post("/api/setup", status_code=201)
    def setup(body: Credentials, session: Session = Depends(db)):
        session.execute(text("SELECT pg_advisory_xact_lock(814014)"))
        if session.scalar(select(User.id).limit(1)) is not None:
            raise HTTPException(409, "已完成初始化")
        user = User(username=body.username, password_hash=passwords.hash(body.password), password_encrypted=encrypt_password(body.password), role="superadmin")
        session.add(user)
        session.commit()
        return user_view(user)

    @app.post("/api/login")
    def login(body: Credentials, response: Response, request: Request, session: Session = Depends(db)):
        user = session.scalar(select(User).where(User.username == body.username))
        try:
            valid = user and user.active and passwords.verify(user.password_hash, body.password)
        except VerificationError:
            valid = False
        if not valid:
            raise HTTPException(401, "账号或密码不正确")
        request.state.audit_actor = (user.id, user.username)
        token = secrets.token_urlsafe(32)
        session.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                                 expires_at=utcnow() + timedelta(hours=12)))
        session.commit()
        response.set_cookie("session", token, httponly=True, samesite="strict", max_age=43200,
                            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true")
        return user_view(user)

    @app.get("/api/me")
    def me(user: User = Depends(current_user)):
        return user_view(user)

    @app.post("/api/logout", status_code=204)
    def logout(request: Request, response: Response, session: Session = Depends(db)):
        token = request.cookies.get("session", "")
        login_session = session.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
        actor = session.get(User, login_session.user_id) if login_session and login_session.expires_at > utcnow() else None
        if actor and actor.active:
            request.state.audit_actor = (actor.id, actor.username)
        session.execute(delete(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        session.commit()
        response.delete_cookie("session")

    @app.get("/api/users")
    def users(user: User = Depends(administrator), session: Session = Depends(db)):
        return [user_view(item) for item in session.scalars(select(User).order_by(User.id))]

    @app.get("/api/people")
    def people(user: User = Depends(current_user), session: Session = Depends(db)):
        return [{"id": item.id, "username": item.username} for item in session.scalars(select(User).order_by(User.id))]

    @app.post("/api/users", status_code=201)
    def add_user(body: UserCreate, user: User = Depends(administrator), session: Session = Depends(db)):
        if body.role == "superadmin" or (user.role != "superadmin" and body.role != "user"):
            raise HTTPException(403, "只有超级管理员可以设置管理员权限，不能新增超级管理员")
        item = User(username=body.username, password_hash=passwords.hash(body.password), password_encrypted=encrypt_password(body.password), role=body.role)
        session.add(item)
        session.commit()
        return user_view(item)

    @app.patch("/api/users/{user_id}")
    def change_user(user_id: int, body: UserChange, user: User = Depends(administrator), session: Session = Depends(db)):
        session.execute(text("SELECT pg_advisory_xact_lock(814015)"))
        item = session.get(User, user_id)
        if not item:
            raise HTTPException(404, "账号不存在")
        if user.role != "superadmin" and (item.role == "superadmin" or (body.role is not None and body.role != item.role) or body.username is not None):
            raise HTTPException(403, "只有超级管理员可以修改该账号或权限")
        if body.role == "superadmin" and item.role != "superadmin":
            raise HTTPException(403, "不能新增超级管理员")
        if item.role == "superadmin" and (body.role not in (None, "superadmin") or body.active is False):
            raise HTTPException(409, "超级管理员不能降级或停用")
        if item.role == "admin" and item.active and (body.role == "user" or body.active is False):
            other_admin = session.scalar(select(User.id).where(User.id != item.id, User.role.in_(("admin", "superadmin")), User.active.is_(True)).limit(1))
            if other_admin is None:
                raise HTTPException(409, "至少需要保留一个启用的管理员账号")
        if body.username is not None:
            item.username = body.username
        if body.role is not None:
            item.role = body.role
        if body.active is not None:
            item.active = body.active
        if body.password:
            item.password_hash = passwords.hash(body.password)
            item.password_encrypted = encrypt_password(body.password)
            session.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
        session.commit()
        return user_view(item)

    @app.get("/api/users/{user_id}/password")
    def reveal_password(user_id: int, response: Response, user: User = Depends(administrator), session: Session = Depends(db)):
        if user.role != "superadmin":
            raise HTTPException(403, "只有超级管理员可以查看密码")
        item = session.get(User, user_id)
        if not item:
            raise HTTPException(404, "账号不存在")
        response.headers["Cache-Control"] = "no-store"
        return {"password": decrypt_password(item.password_encrypted)}

    @app.get("/api/ledgers")
    def ledgers(user: User = Depends(current_user), session: Session = Depends(db)):
        return [{"id": row.id, "name": row.name} for row in session.scalars(select(Ledger).order_by(Ledger.id))]

    @app.post("/api/ledgers", status_code=201)
    def add_ledger(body: LedgerInput, user: User = Depends(administrator), session: Session = Depends(db)):
        item = Ledger(name=body.name, name_key=body.name.casefold())
        session.add(item)
        session.commit()
        return {"id": item.id, "name": item.name}

    @app.patch("/api/ledgers/{ledger_id}")
    def rename_ledger(ledger_id: int, body: LedgerInput, user: User = Depends(administrator), session: Session = Depends(db)):
        item = session.get(Ledger, ledger_id)
        if not item:
            raise HTTPException(404, "台账不存在")
        item.name, item.name_key = body.name, body.name.casefold()
        session.commit()
        return {"id": item.id, "name": item.name}

    def get_record(record_id, session):
        item = session.get(Record, record_id)
        if not item or record_expired(item):
            raise HTTPException(404, "记录不存在")
        return item

    def append_history(item, actor, action, session):
        session.flush()
        session.add(History(record_id=item.id, actor_id=actor.id, action=action, snapshot=jsonable_encoder(record_view(item))))

    def editable_record(record_id, version, user, session):
        item = session.scalar(select(Record).where(Record.id == record_id).with_for_update())
        if not item or record_expired(item):
            raise HTTPException(404, "记录不存在")
        if user.role not in ("admin", "superadmin") and item.creator_id != user.id:
            raise HTTPException(403, "只能修改或核对自己创建的记录")
        if item.status == "void":
            raise HTTPException(409, "作废记录不能修改")
        if item.version != version:
            raise HTTPException(409, "记录已被修改，请重新打开后核对")
        item.version += 1
        item.updated_at = utcnow()
        return item

    register_recycle_routes(app, db, current_user, administrator, record_view, append_history)
    from app.report_attachments import register_report_attachment_routes
    register_report_attachment_routes(app, db, current_user, get_record, record_view, append_history)

    @app.post('/api/shelf-life/derive')
    def derive_expiry(body: ShelfLifeInput, user: User = Depends(current_user)):
        from app.expiry import derive_shelf_life
        return derive_shelf_life(**body.model_dump(mode='json'))

    def create_record(ledger_id, body, user, session):
        if not session.get(Ledger, ledger_id):
            raise HTTPException(404, "台账不存在")
        validate_images(body.image_ids, ledger_id, user, session)
        validate_job(body.recognition_job_id, body.image_ids, ledger_id, session)
        material = session.get(Material, body.material_id) if body.material_id else None
        if body.material_id and not material:
            raise HTTPException(422, "物料不存在")
        scheme = session.get(Scheme, body.scheme_id) if body.scheme_id else None
        if body.scheme_id and not scheme:
            raise HTTPException(422, "检验方案不存在")
        if body.inspection_enabled and "scheme_id" not in body.model_fields_set and material:
            choices = list(session.scalars(select(Scheme).where(Scheme.material_id == material.id)))
            if len(choices) == 1:
                scheme = choices[0]
        fields = body.fields.model_dump(mode="json")
        if material and not fields["material_name"]:
            fields["material_name"] = " ".join(filter(None, [material.name, material.model]))
        items = [i.model_dump() for i in body.items] if body.items is not None else [i | {"result": "", "conclusion": ""} for i in scheme.items] if scheme else []
        report = body.report.model_dump(mode="json")
        if material and 'packaging' not in body.report.model_fields_set:
            report['packaging'] = material.packaging
        if scheme and 'basis' not in body.report.model_fields_set:
            report['basis'] = scheme.name
        item = Record(ledger_id=ledger_id, creator_id=user.id, fields=fields, material_id=body.material_id,
                      inspection_enabled=body.inspection_enabled,
                      scheme_name=scheme.name if scheme else "", items=items, report=report, image_ids=list(dict.fromkeys(body.image_ids)), recognition_job_id=body.recognition_job_id)
        session.add(item)
        append_history(item, user, "created", session)
        return item

    @app.post("/api/ledgers/{ledger_id}/records", status_code=201)
    def add_record(ledger_id: int, body: RecordCreate, user: User = Depends(current_user), session: Session = Depends(db)):
        item = create_record(ledger_id, body, user, session)
        session.commit()
        return record_view(item)

    @app.post('/api/ledgers/{ledger_id}/records/batch', status_code=201)
    def add_batch(ledger_id: int, body: BatchRecordCreate, user: User = Depends(current_user), session: Session = Depends(db)):
        request_id = str(body.request_id)
        payload_hash = hashlib.sha256(json.dumps(body.model_dump(mode='json', exclude_unset=True), sort_keys=True).encode()).hexdigest()
        session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'record-batch:' + request_id})
        receipt = session.get(BatchSubmission, request_id)
        if receipt:
            if receipt.owner_id != user.id or receipt.ledger_id != ledger_id or receipt.payload_hash != payload_hash:
                raise HTTPException(409, '本批次已提交，请返回台账查看已保存记录')
            saved = [session.get(Record, record_id) for record_id in receipt.record_ids]
            if any(item is None or record_expired(item) for item in saved):
                raise HTTPException(409, '本批次已保存，部分记录已清理，请返回台账查看')
            return [record_view(item) for item in saved]
        saved = [create_record(ledger_id, draft, user, session) for draft in body.records]
        if body.mark_checked:
            for item in saved:
                item.status, item.checker_id, item.checked_at = 'checked', user.id, utcnow()
                item.version += 1
                item.updated_at = item.checked_at
                append_history(item, user, 'checked', session)
        session.add(BatchSubmission(id=request_id, owner_id=user.id, ledger_id=ledger_id,
                                    payload_hash=payload_hash, record_ids=[item.id for item in saved]))
        session.commit()
        return [record_view(item) for item in saved]

    @app.post('/api/records/batch-void')
    def batch_void_records(body: BatchVoidInput, request: Request, user: User = Depends(administrator), session: Session = Depends(db)):
        versions = {entry.id: entry.version for entry in body.records}
        rows = list(session.scalars(select(Record).where(Record.id.in_(versions)).order_by(Record.id).with_for_update()))
        if len(rows) != len(versions) or any(record_expired(row) for row in rows):
            raise HTTPException(404, '记录不存在')
        for row in rows:
            if row.status == 'void':
                raise HTTPException(409, '所选记录包含已作废记录，请刷新列表')
            if row.version != versions[row.id]:
                raise HTTPException(409, '所选记录已被修改，请刷新列表后重试')
        now = utcnow()
        for row in rows:
            row.status, row.voided_at, row.updated_at = 'void', now, now
            row.version += 1
            append_history(row, user, 'voided', session)
        session.commit()
        request.state.audit_details = {'record_ids': [row.id for row in rows]}
        by_id = {row.id: row for row in rows}
        return [record_view(by_id[entry.id]) for entry in body.records]

    @app.get("/api/records/{record_id}")
    def record(record_id: int, user: User = Depends(current_user), session: Session = Depends(db)):
        return record_view(get_record(record_id, session))

    @app.get("/api/records")
    def all_records(user: User = Depends(current_user), session: Session = Depends(db)):
        return [record_view(item) for item in session.scalars(select(Record).where(Record.status != 'void').order_by(Record.id.desc()))]

    @app.get("/api/ledgers/{ledger_id}/records")
    def records(ledger_id: int, user: User = Depends(current_user), session: Session = Depends(db)):
        return [record_view(row) for row in session.scalars(select(Record).where(Record.ledger_id == ledger_id, Record.status != 'void').order_by(Record.id.desc()))]

    @app.patch("/api/records/{record_id}")
    def edit_record(record_id: int, body: RecordChange, user: User = Depends(current_user), session: Session = Depends(db)):
        item = editable_record(record_id, body.version, user, session)
        enabled = body.inspection_enabled if body.inspection_enabled is not None else item.inspection_enabled
        # A full editor draft can contain work entered while inspection was on,
        # then switched off before saving. Keep it dormant, never exportable.
        if not item.inspection_enabled and not enabled and body.inspection_enabled is None:
            changed_items = body.items is not None and [i.model_dump() for i in body.items] != item.items
            changed_report = body.report is not None and item.report | body.report.model_dump(mode="json", exclude_unset=True) != item.report
            if changed_items or changed_report or 'scheme_id' in body.model_fields_set:
                raise HTTPException(409, '未检验记录的检验项目和报告信息已锁定，请先选择检验')
        item.inspection_enabled = enabled
        if "material_id" in body.model_fields_set:
            if body.material_id and not session.get(Material, body.material_id):
                raise HTTPException(422, "物料不存在")
            item.material_id = body.material_id
        if "scheme_id" in body.model_fields_set:
            scheme = session.get(Scheme, body.scheme_id) if body.scheme_id else None
            if body.scheme_id and not scheme:
                raise HTTPException(422, "检验方案不存在")
            if (scheme or item.report.get('basis', '') == item.scheme_name) and (body.report is None or 'basis' not in body.report.model_fields_set):
                item.report = item.report | {'basis': scheme.name if scheme else ''}
            item.scheme_name = scheme.name if scheme else ""
            item.items = [i | {"result": "", "conclusion": ""} for i in scheme.items] if scheme else []
        if body.fields is not None:
            item.fields = item.fields | body.fields.model_dump(mode="json", exclude_unset=True)
        if body.items is not None:
            item.items = [i.model_dump() for i in body.items]
        if body.report is not None:
            item.report = item.report | body.report.model_dump(mode="json", exclude_unset=True)
        if body.image_ids is not None:
            validate_images([i for i in body.image_ids if i not in item.image_ids], item.ledger_id, user, session)
            item.image_ids = list(dict.fromkeys(body.image_ids))
        if 'recognition_job_id' in body.model_fields_set:
            validate_job(body.recognition_job_id, item.image_ids, item.ledger_id, session)
            item.recognition_job_id = body.recognition_job_id
        elif body.image_ids is not None and item.recognition_job_id:
            job = session.get(RecognitionJob, item.recognition_job_id)
            if set(job.image_ids) != set(item.image_ids):
                item.recognition_job_id = None
        item.status, item.checker_id, item.checked_at = "pending", None, None
        append_history(item, user, "edited", session)
        session.commit()
        return record_view(item)

    @app.post("/api/records/{record_id}/check")
    def check_record(record_id: int, body: VersionInput, user: User = Depends(current_user), session: Session = Depends(db)):
        item = editable_record(record_id, body.version, user, session)
        item.status, item.checker_id, item.checked_at = "checked", user.id, utcnow()
        append_history(item, user, "checked", session)
        session.commit()
        return record_view(item)

    @app.get("/api/records/{record_id}/history")
    def history(record_id: int, user: User = Depends(current_user), session: Session = Depends(db)):
        get_record(record_id, session)
        return [{"actor_id": h.actor_id, "action": h.action, "at": h.at, "snapshot": h.snapshot}
                for h in session.scalars(select(History).where(History.record_id == record_id).order_by(History.id))]

    @app.post("/api/records/{record_id}/void")
    def void_record(record_id: int, body: VersionInput, user: User = Depends(administrator), session: Session = Depends(db)):
        item = editable_record(record_id, body.version, user, session)
        item.status = "void"
        item.voided_at = utcnow()
        append_history(item, user, "voided", session)
        session.commit()
        return record_view(item)

    @app.get("/api/materials")
    def materials(user: User = Depends(current_user), session: Session = Depends(db)):
        from app.expiry import normalize_shelf_life
        return [{"id": m.id, **{field: getattr(m, field) for field in MaterialInput.model_fields},
                 'shelf_life': normalize_shelf_life(m.shelf_life)}
                for m in session.scalars(select(Material).order_by(Material.id))]

    @app.post("/api/materials", status_code=201)
    def add_material(body: MaterialInput, user: User = Depends(administrator), session: Session = Depends(db)):
        material = Material(**body.model_dump())
        session.add(material)
        session.commit()
        return {"id": material.id, **body.model_dump()}

    @app.put("/api/materials/{material_id}")
    def edit_material(material_id: int, body: MaterialInput, user: User = Depends(administrator), session: Session = Depends(db)):
        material = session.get(Material, material_id)
        if not material:
            raise HTTPException(404, "物料不存在")
        for key, value in body.model_dump().items():
            setattr(material, key, value)
        session.commit()
        return {"id": material.id, **body.model_dump()}

    @app.get("/api/schemes")
    def schemes(material_id: int | None = None, user: User = Depends(current_user), session: Session = Depends(db)):
        query = select(Scheme).order_by(Scheme.id)
        if material_id:
            query = query.where(Scheme.material_id == material_id)
        return [{"id": s.id, "material_id": s.material_id, "name": s.name, "items": s.items} for s in session.scalars(query)]

    def save_scheme(body, session, scheme_id=None):
        if body.material_id is not None and not session.get(Material, body.material_id):
            raise HTTPException(422, "物料不存在")
        item = session.get(Scheme, scheme_id) if scheme_id else Scheme()
        if not item:
            raise HTTPException(404, "方案不存在")
        item.material_id, item.name, item.items = body.material_id, body.name, [i.model_dump() for i in body.items]
        session.add(item)
        session.commit()
        return {"id": item.id, **body.model_dump()}

    @app.post("/api/schemes", status_code=201)
    def add_scheme(body: SchemeInput, user: User = Depends(administrator), session: Session = Depends(db)):
        return save_scheme(body, session)

    @app.put("/api/schemes/{scheme_id}")
    def edit_scheme(scheme_id: int, body: SchemeInput, user: User = Depends(administrator), session: Session = Depends(db)):
        return save_scheme(body, session, scheme_id)

    @app.get("/api/partners")
    def partners(user: User = Depends(current_user), session: Session = Depends(db)):
        return [{"id": p.id, "name": p.name, "kind": p.kind, "address": p.address, "contact": p.contact}
                for p in session.scalars(select(Partner).order_by(Partner.id))]

    def save_partner(body, session, partner_id=None):
        item = session.get(Partner, partner_id) if partner_id else Partner()
        if not item:
            raise HTTPException(404, "单位不存在")
        for key, value in body.model_dump().items():
            setattr(item, key, value)
        session.add(item)
        session.commit()
        return {"id": item.id, **body.model_dump()}

    @app.post("/api/partners", status_code=201)
    def add_partner(body: PartnerInput, user: User = Depends(administrator), session: Session = Depends(db)):
        return save_partner(body, session)

    @app.put("/api/partners/{partner_id}")
    def edit_partner(partner_id: int, body: PartnerInput, user: User = Depends(administrator), session: Session = Depends(db)):
        return save_partner(body, session, partner_id)

    def export_records(body, session):
        ids = list(dict.fromkeys(body.record_ids))
        rows = [get_record(record_id, session) for record_id in ids]
        if any(r.status == "void" for r in rows):
            raise HTTPException(409, "所选记录中有作废记录，请取消选择")
        if not body.include_pending and any(r.status == "pending" for r in rows):
            raise HTTPException(409, "所选记录尚未核对，确认后才能导出")
        return rows

    from app.previewing import register_preview_routes
    register_preview_routes(app, db, current_user, export_records)

    @app.post('/api/templates/convert/{kind}')
    def convert_uploaded_template(kind: str, file: UploadFile, user: User = Depends(current_user)):
        from app.template_conversion import convert_template
        if kind not in {'docx', 'xlsx'}:
            raise HTTPException(404, '模板类型不存在')
        content = file.file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, '个人模板不能超过10MB')
        content = convert_template(content, file.filename or '', kind)
        media = 'application/vnd.openxmlformats-officedocument.' + ('wordprocessingml.document' if kind == 'docx' else 'spreadsheetml.sheet')
        return Response(content, media_type=media, headers={'Cache-Control': 'no-store'})

    @app.get('/api/templates/{kind}')
    def default_template(kind: str, user: User = Depends(current_user)):
        from app.exporting import template_dir
        from app.personal_templates import FILENAMES
        if kind not in FILENAMES:
            raise HTTPException(404, '模板类型不存在')
        path = template_dir() / FILENAMES[kind]
        if not path.is_file():
            raise HTTPException(503, '服务器默认模板尚未配置')
        return FileResponse(path, filename=FILENAMES[kind], headers={'Cache-Control': 'no-store'})

    @app.post("/api/exports/xlsx")
    def export_excel(body: ExportInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
        from app.exporting import excel_bytes
        from app.personal_templates import decode_template
        rows = export_records(body, session)
        request.state.audit_details = {'record_ids': [row.id for row in rows]}
        template = decode_template(body.template_base64, 'xlsx')
        names = {row.ledger_id: session.get(Ledger, row.ledger_id).name for row in rows}
        try:
            content = excel_bytes(rows, names, template)
        except FileNotFoundError:
            raise HTTPException(503, "模板文件夹缺少查验台账.xlsx")
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="ledger.xlsx"'})

    @app.post("/api/exports/docx")
    def export_word(body: ExportInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
        from app.exporting import report_filename, word_archive, word_bytes
        from app.personal_templates import decode_template
        rows = export_records(body, session)
        request.state.audit_details = {'record_ids': [row.id for row in rows]}
        if any(not row.inspection_enabled for row in rows):
            raise HTTPException(409, '所选记录中有未检验记录，请取消勾选未检验记录后导出 Word')
        template = decode_template(body.template_base64, 'docx')
        try:
            content = word_bytes(rows[0], template) if len(rows) == 1 else word_archive(rows, template)
        except TemplateError:
            raise HTTPException(422, 'Word模板占位符或语法不正确，请检查模板后重新导出') from None
        except (FileNotFoundError, OSError):
            raise HTTPException(503, "无法读取模板文件夹的检验报告.docx，请检查文件是否存在且已保存")
        suffix = "docx" if len(rows) == 1 else "zip"
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if suffix == "docx" else "application/zip"
        filename = report_filename(rows[0]) if len(rows) == 1 else '原辅料检验报告.zip'
        return Response(content, media_type=media, headers={"Content-Disposition": f"attachment; filename=\"reports.{suffix}\"; filename*=UTF-8''{quote(filename)}"})

    def validate_images(image_ids, ledger_id, user, session):
        for image_id in image_ids:
            image = session.get(Photo, image_id)
            if not image or image.ledger_id != ledger_id:
                raise HTTPException(422, "图片不属于当前台账")
            if image.owner_id != user.id and user.role not in ("admin", "superadmin"):
                raise HTTPException(403, "只能使用自己上传的图片")

    @app.post("/api/ledgers/{ledger_id}/images", status_code=201)
    def upload_image(ledger_id: int, file: UploadFile, user: User = Depends(current_user), session: Session = Depends(db)):
        if not session.get(Ledger, ledger_id):
            raise HTTPException(404, "台账不存在")
        content = file.file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "单张照片不能超过20MB")
        try:
            with Image.open(BytesIO(content)) as picture:
                if picture.format not in {"JPEG", "PNG", "WEBP"} or picture.width * picture.height > 40_000_000:
                    raise ValueError()
                kind = picture.format
                picture.verify()
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
            raise HTTPException(422, "请上传有效的 JPG、PNG 或 WebP 图片，最多4000万像素")
        directory = Path(os.getenv("DATA_DIR", "data")) / "images"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid.uuid4().hex + {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[kind])
        path.write_bytes(content)
        photo = Photo(ledger_id=ledger_id, owner_id=user.id, path='images/' + path.name, filename=(file.filename or "图片")[:250], media_type=Image.MIME[kind])
        session.add(photo)
        session.commit()
        return {"id": photo.id, "filename": photo.filename, "url": f"/api/images/{photo.id}"}

    @app.get("/api/images/{image_id}")
    def get_image(image_id: int, user: User = Depends(current_user), session: Session = Depends(db)):
        photo = session.get(Photo, image_id)
        if not photo:
            raise HTTPException(404, "图片不存在")
        if photo.owner_id != user.id and user.role not in ("admin", "superadmin"):
            attached = any(image_id in record.image_ids for record in session.scalars(select(Record).where(Record.ledger_id == photo.ledger_id)))
            if not attached:
                raise HTTPException(403, "图片尚未关联可查看记录")
        return FileResponse(photo_path(photo.path), media_type=photo.media_type, headers={"Cache-Control": "private, no-store"})

    def job_view(job, session):
        from app.review_feedback import checked_suggestions
        result = {key: getattr(job, key) for key in ("id", "image_ids", "local_status", "cloud_status", "fields", "cloud_fields", "evidence", "conflicts", "error", "cloud_error")}
        result['cloud_warnings'] = result['cloud_fields'].get('_warnings', [])
        result['conflicts'] = {key: list(values) for key, values in result['conflicts'].items()}
        for key, values in result['cloud_fields'].get('_candidates', {}).items():
            result['conflicts'][key] = list(dict.fromkeys(result['conflicts'].get(key, []) + values))
        result['cloud_fields'] = {key: value for key, value in result['cloud_fields'].items() if not key.startswith('_')}
        result['queue_ahead'] = session.scalar(select(func.count()).select_from(RecognitionJob).where(
            RecognitionJob.id < job.id, RecognitionJob.local_status.in_(['queued', 'running']))) if job.local_status == 'queued' else 0
        result['review_suggestions'] = checked_suggestions(job, session)
        return result

    def validate_job(job_id, image_ids, ledger_id, session):
        if job_id is None:
            return
        job = session.get(RecognitionJob, job_id)
        if not job or job.ledger_id != ledger_id or set(job.image_ids) != set(image_ids):
            raise HTTPException(422, '识别任务与本条记录图片不匹配')

    @app.post("/api/ledgers/{ledger_id}/recognition", status_code=202)
    def recognize(ledger_id: int, body: RecognitionInput, user: User = Depends(current_user), session: Session = Depends(db)):
        validate_images(body.image_ids, ledger_id, user, session)
        # Serialize submissions from one user so double-clicks and concurrent
        # requests reuse the active job instead of growing the CPU queue.
        session.execute(text('SELECT pg_advisory_xact_lock(814016, :owner)'), {'owner': user.id})
        active = session.scalars(select(RecognitionJob).where(
            RecognitionJob.owner_id == user.id, RecognitionJob.ledger_id == ledger_id,
            or_(RecognitionJob.local_status.in_(['queued', 'running']), RecognitionJob.cloud_status.in_(['queued', 'running']))))
        for existing in active:
            if set(existing.image_ids) == set(body.image_ids) and existing.cloud_enabled == body.cloud_enabled:
                return job_view(existing, session)
        job = RecognitionJob(ledger_id=ledger_id, owner_id=user.id, image_ids=list(dict.fromkeys(body.image_ids)), cloud_enabled=body.cloud_enabled,
                             cloud_status="queued" if body.cloud_enabled else "disabled")
        session.add(job)
        session.commit()
        result = job_view(job, session)
        from app.jobs import run_local
        app.state.local_pool.submit(run_local, app, job.id)
        return result

    @app.get("/api/recognition/{job_id}")
    def get_job(job_id: int, response: Response, user: User = Depends(current_user), session: Session = Depends(db)):
        job = session.get(RecognitionJob, job_id)
        if not job:
            raise HTTPException(404, "识别任务不存在")
        if job.owner_id != user.id and user.role not in ("admin", "superadmin"):
            if not session.scalar(select(Record.id).where(Record.recognition_job_id == job.id).limit(1)):
                raise HTTPException(403, "只能查看自己的或已保存记录的识别任务")
        response.headers['Cache-Control'] = 'no-store'
        return job_view(job, session)

    @app.get("/api/settings/cloud")
    def cloud_settings(user: User = Depends(administrator), session: Session = Depends(db)):
        setting = session.get(Setting, "zhipu_key")
        return {"configured": bool(setting.value if setting else os.getenv("ZHIPU_API_KEY", "")), "model": "glm-4.1v-thinking-flash"}

    @app.put("/api/settings/cloud")
    def set_cloud(body: CloudSettingInput, user: User = Depends(administrator), session: Session = Depends(db)):
        session.merge(Setting(key="zhipu_key", value=body.api_key))
        session.commit()
        return {"configured": bool(body.api_key), "model": "glm-4.1v-thinking-flash"}

    @app.post("/api/settings/cloud/test")
    def test_cloud(user: User = Depends(administrator)):
        from app.recognition import CloudRecognitionError
        try:
            app.state.cloud_extract([], [["品名：连接测试物料"]])
            return {"ok": True, "message": "连接成功：已验证密钥和模型调用。图片识别效果请上传包装照片验证。"}
        except CloudRecognitionError as exc:
            return {"ok": False, "message": str(exc)}
        except Exception:
            return {"ok": False, "message": "云端连接测试失败，请稍后重试；本地识别仍可使用"}

    from fastapi.staticfiles import StaticFiles
    frontend = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
    if frontend.is_dir():
        app.mount('/', StaticFiles(directory=str(frontend), html=True), name='frontend')
    return app
