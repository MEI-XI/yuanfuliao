"""Reuse checked records while keeping this delivery's dates and quantities."""
import re
import unicodedata

from sqlalchemy import select

from app.models import Ledger, Material, RecognitionJob, Record


def material_name(value):
    return re.sub(r'[\s（）()]', '', unicodedata.normalize('NFKC', value or '')).casefold()


def recognized_names(job):
    if not job:
        return set()
    names = {name for fields in (job.fields, job.cloud_fields) if (name := material_name(fields.get('material_name')))}
    proposed = [*job.conflicts.get('material_name', []),
                *job.cloud_fields.get('_candidates', {}).get('material_name', [])]
    names.update(material_name(value) for value in proposed if material_name(value))
    # A single tentative reading can be confirmed by an exact checked name.
    # Multiple alternatives still cannot establish which material is pictured.
    return set() if len(names) > 1 else names


def catalog_name_suggestions(job, session):
    result = {'name': '', 'candidates': [], 'material_id': None}
    names = recognized_names(job)
    if len(names) != 1:
        return result
    matches = []
    for material in session.scalars(select(Material).order_by(Material.id)):
        canonical = ' '.join(part for part in (material.name, material.model) if part)
        aliases = {material_name(canonical), *(material_name(value) for value in re.split(r'[,，;；、\n|]+', material.aliases or '') if value.strip())}
        if names.intersection(aliases):
            matches.append((material, canonical))
    result['candidates'] = list(dict.fromkeys(name for _, name in matches))
    if len(matches) == 1:
        result['name'] = matches[0][1]
        result['material_id'] = matches[0][0].id
    return result


def checked_suggestions(job, session):
    result = {'fields': {}, 'conflicts': {}, 'sources': [], 'inspection': None, 'inspection_choices': [],
              'match_status': 'not_found', 'message': '尚未找到同种物料的已核对记录。'}
    if job.local_status != 'done' or job.cloud_status in {'queued', 'running'}:
        return result | {'match_status': 'waiting', 'message': '等待本次识别完成后匹配物料历史。'}
    names = recognized_names(job)
    if not names:
        return result | {'message': '本次尚未明确识别物料名称，未套用历史记录。'}
    catalog = catalog_name_suggestions(job, session)
    if catalog['name']:
        names.add(material_name(catalog['name']))
    rows = list(session.execute(select(Record, RecognitionJob, Ledger.name)
        .outerjoin(RecognitionJob, Record.recognition_job_id == RecognitionJob.id)
        .join(Ledger, Record.ledger_id == Ledger.id)
        .where(Record.status == 'checked')
        .order_by(Record.checked_at.desc(), Record.id.desc())))
    candidates = []
    for record, original, ledger_name in rows:
        canonical = material_name(record.fields.get('material_name'))
        if canonical and names.intersection(recognized_names(original) | {canonical}):
            candidates.append((record, original, ledger_name))
    # The same OCR title can be an alias of different manually corrected models.
    # Resolve that only with additional recognized evidence, never by photo ID.
    kinds = {material_name(record.fields.get('material_name')) for record, _, _ in candidates}
    direct_names = kinds.intersection(names)
    if len(direct_names) == 1:
        kinds = direct_names
    if len(kinds) > 1:
        for key in ('specification', 'company_name'):
            values = {re.sub(r'\s+', '', fields.get(key, '')).casefold()
                      for fields in (job.fields, job.cloud_fields) if fields.get(key)}
            narrowed = [(record, original, ledger_name) for record, original, ledger_name in candidates
                        if values.intersection(re.sub(r'\s+', '', fields.get(key, '')).casefold()
                            for fields in (record.fields, *( [original.fields, original.cloud_fields] if original else [])))]
            narrowed_kinds = {material_name(record.fields.get('material_name')) for record, _, _ in narrowed}
            if len(narrowed_kinds) == 1:
                kinds = narrowed_kinds
                break
        if len(kinds) > 1:
            choices = list(dict.fromkeys(record.fields['material_name'] for record, _, _ in candidates))
            return result | {'conflicts': {'material_name': choices}, 'match_status': 'ambiguous',
                             'message': '识别名称对应不同物料或型号，尚不能确认是同一种物料，未自动带入。'}
    if not kinds:
        return result
    canonical = next(iter(kinds))
    # Use one complete, most recently checked record. Do not mix old versions.
    record, _, ledger_name = next((record, original, ledger_name) for record, original, ledger_name in rows
        if material_name(record.fields.get('material_name')) == canonical)
    result['sources'] = [{'record_id': record.id, 'version': record.version,
                          'ledger_name': ledger_name, 'checked_at': record.checked_at}]
    stable_fields = ('material_name', 'specification', 'company_name', 'address', 'contact',
                     'address_source', 'contact_source', 'certificates', 'sensory', 'sampling_items', 'notes')
    result['fields'] = {key: record.fields.get(key, '') for key in stable_fields}
    report = {key: record.report.get(key, '') for key in ('packaging', 'basis', 'internal_report', 'conclusion')}
    result['inspection'] = {'items': record.items, 'report': report, 'scheme_name': record.scheme_name,
                            'inspection_enabled': record.inspection_enabled, 'material_id': record.material_id,
                            'source_record_id': record.id}
    result['match_status'] = 'matched'
    result['message'] = '已匹配同种物料，自动采用最近一次已核对记录，可继续修改。'
    return result
