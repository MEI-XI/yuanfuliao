"""Keep visibly unfinished OCR values reviewable without inventing their units."""
import re


def incomplete_specification(value):
    return bool(isinstance(value, str) and re.search(r'\d', value)
                and (re.search(r'[/×*（(]\s*$', value) or value.count('(') > value.count(')')
                     or value.count('（') > value.count('）')))


def incomplete_ocr_value(key, value):
    return (key == 'specification' and incomplete_specification(value)
            or key == 'shelf_life' and bool(re.fullmatch(r'\s*\d+(?:\.\d+)?\s*', str(value))))


def review_incomplete_values(fields, conflicts, texts):
    value = fields.get('specification', '')
    if incomplete_specification(value):
        conflicts.setdefault('specification', [])
        if value not in conflicts['specification']:
            conflicts['specification'].append(value)
        fields.pop('specification', None)
        weights = []
        for text in texts:
            match = re.fullmatch(r'(?:净含量|含量)[:：]\s*(\d+(?:\.\d+)?\s*(?:kg|g|千克|公斤|克))', text.strip(), re.I)
            if match and match[1] not in weights:
                weights.append(match[1])
        if len(weights) == 1:
            fields['specification'] = weights[0]
        elif weights:
            conflicts['specification'] = list(dict.fromkeys(conflicts['specification'] + weights))
    if not fields.get('shelf_life'):
        for text in texts:
            match = re.search(r'(?:保质期|质保期|保质期限|质期)[:：]?\s*(\d+)\s*$', text)
            if match:
                values = conflicts.setdefault('shelf_life', [])
                if match[1] not in values:
                    values.append(match[1])


def candidate_review(fields, cloud_fields, conflicts, *, english_detected=False):
    defaults, warnings = {}, []
    names = conflicts.get('material_name', [])
    name = fields.get('material_name') or cloud_fields.get('material_name') or next(iter(names), '')
    if english_detected and not re.search(r'[\u4e00-\u9fff]', name):
        name = next((value for value in [cloud_fields.get('material_name', ''), *names]
                     if re.search(r'[\u4e00-\u9fff]', value)), name)
    if name:
        defaults['material_name'] = name
    if names:
        warnings.append({'field': 'material_name', 'message': '名称存在待核对候选，请对照图片确认，可选择下方名称填入。'})
    specs = conflicts.get('specification', [])
    if any(incomplete_specification(value) for value in specs):
        warnings.append({'field': 'specification', 'message': '识别到不完整规格，请核对包装单位；完整净含量可先填入，但不能推断缺失的包装单位。'})
        value = fields.get('specification') or cloud_fields.get('specification')
        if value and not incomplete_specification(value) and all(v == value or incomplete_specification(v) for v in specs):
            defaults['specification'] = value
    if any(incomplete_ocr_value('shelf_life', value) for value in conflicts.get('shelf_life', [])):
        warnings.append({'field': 'shelf_life', 'message': '保质期只识别到数字，缺少年、月或天单位，请核对后填写。'})
    return defaults, warnings
