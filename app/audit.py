"""HTTP operation audit; request bodies, cookies and credential values are never read."""
from datetime import date, datetime, time, timedelta, timezone
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.schemas import AuditLogSelection
from app import models


def purge_expired_audit_logs(session):
    session.execute(delete(AuditLog).where(AuditLog.at < models.utcnow() - timedelta(days=30)))


ACTIONS = {
    'login': '登录', 'logout': '退出登录', 'setup': '初始化系统',
    'add_user': '创建账号', 'change_user': '修改账号', 'delete_user': '删除账号',
    'reveal_password': '查看密码', 'add_ledger': '创建台账', 'rename_ledger': '修改台账',
    'delete_ledger': '删除台账', 'add_material': '创建物料', 'edit_material': '修改物料',
    'delete_material': '删除物料', 'add_scheme': '创建检验方案', 'edit_scheme': '修改检验方案',
    'delete_scheme': '删除检验方案', 'add_partner': '创建单位资料', 'edit_partner': '修改单位资料',
    'delete_partner': '删除单位资料', 'void_record': '作废记录', 'batch_void_records': '批量作废记录',
    'restore_record': '还原记录', 'check_record': '核对记录', 'set_cloud': '更新云端设置',
    'test_cloud': '测试云端连接',
    'add_record': '创建记录', 'add_batch': '批量创建记录', 'edit_record': '修改记录',
    'export_excel': '导出台账', 'export_word': '导出检验报告', 'upload_image': '上传照片',
    'recognize': '发起识别',
    'upload_report': '上传检验报告', 'delete_report': '删除检验报告',
    'preview_export': '预览导出',
    'delete_recycled_record': '永久删除记录',
    'batch_restore_records': '批量还原记录',
    'batch_delete_recycled_records': '批量永久删除记录',
    'batch_delete_audit_logs': '批量删除操作日志',
}


def register_audit(app, engine, db, current_user):
    @app.middleware('http')
    async def audit_operation(request, call_next):
        response = await call_next(request)
        actor = getattr(request.state, 'audit_actor', None)
        route = request.scope.get('route')
        name = getattr(route, 'name', '')
        if name in {'derive_expiry', 'preview_unsaved_report'}:
            return response
        if actor and 200 <= response.status_code < 300 and (
            request.method in ('POST', 'PUT', 'PATCH', 'DELETE') or name == 'reveal_password'
        ):
            details = {'method': request.method, 'route': getattr(route, 'path', '')}
            details.update(getattr(request.state, 'audit_details', {}))
            with Session(engine) as session:
                session.add(AuditLog(actor_id=actor[0], actor_username=actor[1],
                    action=ACTIONS.get(name, '执行操作'), target=request.url.path,
                    status_code=response.status_code, details=details))
                session.commit()
        return response

    @app.post('/api/audit-logs/batch-delete', status_code=204)
    def batch_delete_audit_logs(body: AuditLogSelection, request: Request,
                                user: User = Depends(current_user), session: Session = Depends(db)):
        if user.role != 'superadmin':
            raise HTTPException(403, '只有超级管理员可以删除操作日志')
        ids = list(session.scalars(select(AuditLog.id).where(AuditLog.id.in_(body.ids))
                                  .order_by(AuditLog.id).with_for_update()))
        if len(ids) != len(body.ids):
            raise HTTPException(409, '所选日志已被删除，本次未删除任何日志，请刷新后重新选择')
        session.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
        session.commit()
        request.state.audit_details = {'log_ids': body.ids, 'count': len(ids)}

    @app.get('/api/audit-logs')
    def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                   actor: str = '', action: str = '', target: str = '',
                   from_date: date | None = None, to_date: date | None = None,
                   user: User = Depends(current_user), session: Session = Depends(db)):
        if user.role != 'superadmin':
            raise HTTPException(403, '只有超级管理员可以查看操作日志')
        if from_date and to_date and from_date > to_date:
            raise HTTPException(422, '开始日期不能晚于结束日期')
        filters = []
        if actor.strip():
            filters.append(AuditLog.actor_username.contains(actor.strip(), autoescape=True))
        if action:
            filters.append(AuditLog.action == action)
        if target.strip():
            filters.append(AuditLog.target.contains(target.strip(), autoescape=True))
        local_timezone = timezone(timedelta(hours=8))
        if from_date:
            filters.append(AuditLog.at >= datetime.combine(from_date, time.min, local_timezone))
        if to_date:
            filters.append(AuditLog.at <= datetime.combine(to_date, time.max, local_timezone))
        rows = session.scalars(select(AuditLog).where(*filters).order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))
        return {'items': [{key: getattr(row, key) for key in (
            'id', 'actor_id', 'actor_username', 'at', 'action', 'target', 'status_code', 'details')}
            for row in rows], 'total': session.scalar(select(func.count()).select_from(AuditLog).where(*filters)),
            'actions': list(session.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action))),
            'actors': list(session.scalars(select(AuditLog.actor_username).distinct().order_by(AuditLog.actor_username))),
            'page': page, 'page_size': page_size}
