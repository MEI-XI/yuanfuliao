"""Business object labels only; never read request bodies or credential fields."""
import re

from app.models import Ledger, Material, Partner, Record, Scheme, User


def record_subject(session, record_id):
    item = session.get(Record, record_id)
    if item is None:
        return f'查验记录（编号 {record_id}，原记录已删除）'
    ledger = session.get(Ledger, item.ledger_id)
    return f'{ledger.name if ledger else "公司台账"}台账 · {item.fields.get("material_name") or "未填写物料"}（记录编号 {item.id}）'


def describe_subject(session, path, details):
    if details.get('subjects'):
        return '；'.join(details['subjects'])
    if details.get('record_ids'):
        return '；'.join(record_subject(session, record_id) for record_id in details['record_ids'])
    if details.get('record_id'):
        subject = record_subject(session, details['record_id'])
        if details.get('material_name'):
            subject += f' · {details["material_name"]}'
        if details.get('filename'):
            subject += f' · 附件：{details["filename"]}'
        return subject
    path = details.get('subject_path', path)
    match = re.match(r'^/api/(records|recycle-bin|materials|schemes|partners|users|ledgers)/(\d+)(?:/|$)', path)
    if not match:
        return ''
    resource, raw_id = match.groups()
    entry_id = int(raw_id)
    if resource in ('records', 'recycle-bin'):
        return record_subject(session, entry_id)
    model, label = {
        'materials': (Material, '物料'), 'schemes': (Scheme, '检验方案'),
        'partners': (Partner, '单位资料'), 'users': (User, '账号'), 'ledgers': (Ledger, '公司台账'),
    }[resource]
    item = session.get(model, entry_id)
    name = (item.username if resource == 'users' else item.name) if item else '原资料已删除'
    return f'{label}：{name}（编号 {entry_id}）'


def describe_operation(action, subject):
    return f'{action}：{subject}' if subject else action


def historical_description(session, row):
    subject = describe_subject(session, row.target, row.details)
    if subject:
        return describe_operation(row.action, subject) + '（历史日志，名称按现有资料补充）'
    return row.action + '（旧日志未保存具体对象）'
