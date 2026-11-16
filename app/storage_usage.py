"""Read-only storage inventory and application-owned conversion scratch space."""
import logging
import os
import shutil
import time
from datetime import timedelta
from pathlib import Path

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import utcnow

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def temporary_root():
    root = Path(os.getenv('DATA_DIR', 'data')) / 'runtime-temp'
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def purge_stale_temporary_files():
    root = Path(os.getenv('DATA_DIR', 'data')) / 'runtime-temp'
    if not root.exists() or root.is_symlink() or root.is_junction():
        return 0
    root = root.resolve()
    removed = 0
    cutoff = time.time() - 7 * 86400
    for entry in root.iterdir():
        if not entry.name.startswith(('office-preview-', 'template-convert-')):
            continue
        try:
            if entry.is_symlink() or entry.is_junction() or not entry.is_dir() or entry.stat().st_mtime >= cutoff:
                continue
            if entry.resolve().parent != root:
                continue
            # Never traverse links into unrelated directories during removal.
            if any(child.is_symlink() or child.is_junction() for child in entry.rglob('*')):
                continue
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            logger.exception('Temporary conversion cleanup failed for %s', entry.name)
    return removed


def folder_usage(root, seen):
    size = count = errors = 0
    root = Path(root)
    if not root.exists() or root.is_symlink() or root.is_junction():
        return size, count, errors
    pending = [str(root.resolve())]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if not os.path.isjunction(entry.path):
                                pending.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            key = os.path.normcase(entry.path)
                            if key not in seen:
                                seen.add(key)
                                size += entry.stat(follow_symlinks=False).st_size
                                count += 1
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return size, count, errors


def register_storage_routes(app, db, administrator):
    @app.get('/api/storage-usage')
    def storage_usage(user=Depends(administrator), session: Session = Depends(db)):
        data = Path(os.getenv('DATA_DIR', 'data')).resolve()
        rows = [
            ('images', '包装图片', data / 'images', '记录、历史或识别任务引用的图片保留；无引用且超过30天的图片自动回收。'),
            ('reports', '报告附件', data / 'report-attachments', '随业务记录保留；永久删除记录时回收附件，30天以上孤立文件定期回收。'),
            ('templates', '服务器默认模板', Path(os.getenv('TEMPLATE_DIR', 'templates')), '长期保留，不自动删除；用户个人模板在用户设备上，不计入。'),
            ('runtime_temp', '文档转换临时文件', data / 'runtime-temp', '正常转换结束立即删除；异常遗留超过7天自动清理。'),
            ('backups', '本机备份目录', data / 'backups', '不自动删除；迁移后需单独配置备份保留策略。'),
            ('development_temp', '开发、实验及旧临时目录', PROJECT_ROOT / 'tmp', '含数据库运行程序和实验资料，不能整体清空；不属于线上运行缓存，迁移时按需排除。'),
            ('python_runtime', 'Python 运行环境', PROJECT_ROOT / '.venv', '程序依赖，不自动删除；服务器上重新安装。'),
            ('frontend_dependencies', '前端构建依赖', PROJECT_ROOT / 'frontend/node_modules', '只用于构建，部署已构建网页时不必携带。'),
            ('frontend_dist', '网页发布文件', PROJECT_ROOT / 'frontend/dist', '网站运行文件，随发布替换，不自动删除。'),
            ('research', '研究资料', PROJECT_ROOT / 'research', '研究资料，不自动删除，迁移时按需排除。'),
        ]
        seen = set()
        categories = []
        for key, label, path, note in rows:
            size, count, errors = folder_usage(path, seen)
            categories.append({'key': key, 'label': label, 'bytes': size, 'files': count,
                               'note': note + (f' 有{errors}个文件暂时无法读取大小。' if errors else '')})
        disk = shutil.disk_usage(data if data.exists() else data.parent)
        database_bytes = session.scalar(text('SELECT pg_database_size(current_database())'))
        autovacuum = session.scalar(text('SHOW autovacuum'))
        return {'measured_at': utcnow().isoformat(), 'categories': categories,
                'database_bytes': database_bytes, 'disk': {'total': disk.total, 'free': disk.free},
                'cleanup': {'interval_hours': 1, 'retention_days': 30, 'notes': [
                    '服务启动时及每小时执行一次清理，服务停止期间不执行。',
                    '回收站记录和操作日志保留30天；正常业务记录、历史快照、模板不按年龄删除。',
                    '未关联且已结束的识别任务、未引用包装图片保留30天；旧数据从本次升级起计时。',
                    '过期登录会话自动清理；文档转换临时文件正常结束立即释放，异常残留保留7天。',
                    'Excel/Word导出不保存服务器副本；浏览器预览关闭后释放临时地址和PDF工作线程。',
                    f'PostgreSQL autovacuum：{autovacuum}；删除数据通常先形成可复用空间，不代表数据库文件立即缩小。',
                    '数据库大小为当前数据库统计，不含整个PostgreSQL安装/集群、其他数据库和外部备份；列表不是整台服务器总占用。',
                ]}}
