from fastapi import Depends, HTTPException
from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.orm import Session

from app.models import History, Ledger, LoginSession, Material, Partner, Photo, RecognitionJob, Record, Scheme, User


def register_maintenance_routes(app, db, administrator):
    def entry(session, model, entry_id, label):
        item = session.scalar(select(model).where(model.id == entry_id).with_for_update())
        if item is None:
            raise HTTPException(404, f'{label}不存在')
        return item

    @app.delete('/api/materials/{material_id}', status_code=204)
    def delete_material(material_id: int, user: User = Depends(administrator), session: Session = Depends(db)):
        item = entry(session, Material, material_id, '物料')
        session.execute(update(Record).where(Record.material_id == material_id).values(material_id=None))
        session.execute(update(Scheme).where(Scheme.material_id == material_id).values(material_id=None))
        session.delete(item)
        session.commit()

    @app.delete('/api/schemes/{scheme_id}', status_code=204)
    def delete_scheme(scheme_id: int, user: User = Depends(administrator), session: Session = Depends(db)):
        session.delete(entry(session, Scheme, scheme_id, '检验方案'))
        session.commit()

    @app.delete('/api/partners/{partner_id}', status_code=204)
    def delete_partner(partner_id: int, user: User = Depends(administrator), session: Session = Depends(db)):
        session.delete(entry(session, Partner, partner_id, '单位资料'))
        session.commit()

    @app.delete('/api/users/{user_id}', status_code=204)
    def delete_user(user_id: int, user: User = Depends(administrator), session: Session = Depends(db)):
        session.execute(text('SELECT pg_advisory_xact_lock(814015)'))
        item = entry(session, User, user_id, '账号')
        if item.role == 'superadmin' and user.role != 'superadmin':
            raise HTTPException(403, '只有超级管理员可以管理该账号')
        if item.id == user.id:
            raise HTTPException(409, '不能删除当前登录账号')
        if item.role == 'superadmin':
            raise HTTPException(409, '不能删除超级管理员')
        if item.role == 'admin' and item.active:
            other_admin = session.scalar(select(User.id).where(User.id != item.id, User.role.in_(('admin', 'superadmin')), User.active.is_(True)).limit(1))
            if other_admin is None:
                raise HTTPException(409, '至少需要保留一个启用的管理员账号')
        references = (
            select(Record.id).where(or_(Record.creator_id == user_id, Record.checker_id == user_id)),
            select(History.id).where(History.actor_id == user_id),
            select(Photo.id).where(Photo.owner_id == user_id),
            select(RecognitionJob.id).where(RecognitionJob.owner_id == user_id),
        )
        if any(session.scalar(query.limit(1)) is not None for query in references):
            raise HTTPException(409, '该账号已有业务记录、照片或识别历史，请改为停用账号，以保留责任人信息')
        session.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
        session.delete(item)
        session.commit()

    @app.delete('/api/ledgers/{ledger_id}', status_code=204)
    def delete_ledger(ledger_id: int, user: User = Depends(administrator), session: Session = Depends(db)):
        item = entry(session, Ledger, ledger_id, '台账')
        for model, label in ((Record, '查验记录'), (Photo, '照片'), (RecognitionJob, '识别任务')):
            if session.scalar(select(model.id).where(model.ledger_id == ledger_id).limit(1)) is not None:
                raise HTTPException(409, f'该台账已有{label}，不能删除；仅可删除空台账')
        session.delete(item)
        session.commit()
