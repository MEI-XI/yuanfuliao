"""Reuse checked records while keeping this delivery's dates and quantities."""
import json
import re

from sqlalchemy import select

from app.models import Ledger, RecognitionJob, Record


def identity(fields):
    values = tuple(re.sub(r'\s+', '', fields.get(key, '')).casefold()
                   for key in ('material_name', 'company_name', 'specification'))
    return values if all(values) else None


def checked_suggestions(job, session):
    result = {'fields': {}, 'conflicts': {}, 'sources': [], 'inspection': None, 'inspection_choices': []}
    signatures = {value for value in (identity(job.fields), identity(job.cloud_fields)) if value is not None}
    if job.local_status != 'done' or not signatures or any(
            key in job.conflicts for key in ('material_name', 'company_name', 'specification')):
        return result
    if any(key in job.cloud_fields.get('_candidates', {}) for key in ('material_name', 'company_name', 'specification')):
        return result
    rows = session.execute(select(Record, RecognitionJob, Ledger.name)
        .join(RecognitionJob, Record.recognition_job_id == RecognitionJob.id)
        .join(Ledger, Record.ledger_id == Ledger.id)
        .where(Record.status == 'checked', RecognitionJob.local_status == 'done', RecognitionJob.id != job.id)
        .order_by(Record.checked_at.desc(), Record.id.desc()))
    candidates = []
    inspection_snapshots = set()
    for record, original, ledger_name in rows:
        if any(key in original.conflicts for key in ('material_name', 'company_name', 'specification')):
            continue
        if not signatures.intersection((identity(original.fields), identity(original.cloud_fields), identity(record.fields))):
            continue
        candidates.append(record.fields)
        result['sources'].append({'record_id': record.id, 'version': record.version,
                                  'ledger_name': ledger_name, 'checked_at': record.checked_at})
        if record.inspection_enabled:
            report = {key: record.report[key] for key in ('packaging', 'basis', 'conclusion') if record.report.get(key)}
            snapshot = {'items': record.items, 'report': report, 'scheme_name': record.scheme_name}
            fingerprint = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
            if (record.items or report) and fingerprint not in inspection_snapshots:
                inspection_snapshots.add(fingerprint)
                result['inspection_choices'].append(snapshot | {'source_record_id': record.id})
    if len(result['inspection_choices']) == 1:
        result['inspection'] = result['inspection_choices'][0]
    for key in ('material_name', 'specification', 'company_name', 'address', 'contact', 'certificates', 'sensory', 'sampling_items', 'notes'):
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
