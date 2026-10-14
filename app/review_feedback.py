"""Reuse checked packaging corrections without training or copying batch data."""
import re

from sqlalchemy import select

from app.models import Ledger, RecognitionJob, Record


def identity(fields):
    values = tuple(re.sub(r'\s+', '', fields.get(key, '')).casefold()
                   for key in ('material_name', 'company_name', 'specification'))
    return values if all(values) else None


def checked_suggestions(job, session):
    result = {'fields': {}, 'conflicts': {}, 'sources': []}
    signature = identity(job.fields)
    if job.local_status != 'done' or signature is None or any(
            key in job.conflicts for key in ('material_name', 'company_name', 'specification')):
        return result
    rows = session.execute(select(Record, RecognitionJob, Ledger.name)
        .join(RecognitionJob, Record.recognition_job_id == RecognitionJob.id)
        .join(Ledger, Record.ledger_id == Ledger.id)
        .where(Record.status == 'checked', RecognitionJob.local_status == 'done', RecognitionJob.id != job.id)
        .order_by(Record.checked_at.desc(), Record.id.desc()))
    candidates = []
    for record, original, ledger_name in rows:
        if any(key in original.conflicts for key in ('material_name', 'company_name', 'specification')):
            continue
        if signature not in (identity(original.fields), identity(record.fields)):
            continue
        candidates.append(record.fields)
        result['sources'].append({'record_id': record.id, 'version': record.version,
                                  'ledger_name': ledger_name, 'checked_at': record.checked_at})
    for key in ('material_name', 'specification', 'company_name', 'shelf_life', 'address', 'contact'):
        # Contact/address and their ownership travel together.
        paired = key in {'address', 'contact'}
        values = list(dict.fromkeys((fields[key], fields.get(key + '_source', '') if paired else '')
                                    for fields in candidates if fields.get(key)))
        if len(values) == 1:
            result['fields'][key] = values[0][0]
            if paired:
                result['fields'][key + '_source'] = values[0][1]
        elif values:
            result['conflicts'][key] = [value + ({'supplier': '（供应商）', 'manufacturer': '（生产商）'}.get(source, ''))
                                        for value, source in values]
    return result
