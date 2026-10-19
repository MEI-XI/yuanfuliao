"""Keep all labelled parties and addresses, including their printed roles."""
import re

from pydantic import ValidationError

from app.english_labels import PATTERNS
from app.schemas import RecordFields


COMPANY = r'供应商|供货商|经销商|生产厂家|生产企业|生产商|制造商'
ADDRESS = rf'(?:{COMPANY})地址|生产地址|厂家地址|制造地址|注册地址|地址'
LABEL = re.compile(rf'({ADDRESS}|{COMPANY})\s*[:：]\s*')
STOP = re.compile(r'(?:电话|联系方式|邮编|传真|网址|保质期|生产日期|许可证编号|执行标准)\s*[:：]?|\b(?:Tel|Phone|Fax|Website)\s*:', re.I)


def merge_party_options(*groups):
    merged = {'company_name': [], 'address': []}
    for group in groups:
        if not isinstance(group, dict):
            continue
        for key in merged:
            options = group.get(key, [])
            if not isinstance(options, list):
                continue
            for option in options:
                if not isinstance(option, dict) or not isinstance(option.get('value'), str):
                    continue
                value = option['value'].strip()
                source = option.get('source', '')
                if not value or source not in ('', 'supplier', 'manufacturer'):
                    continue
                try:
                    RecordFields.model_validate({key: value})
                except ValidationError:
                    continue
                candidate = {'value': value, 'source': source}
                if candidate not in merged[key]:
                    merged[key].append(candidate)
    for key, options in merged.items():
        labelled = {item['value'] for item in options if item['source']}
        merged[key] = [item for item in options if item['source'] or item['value'] not in labelled]
    return merged


def extract_party_options(texts):
    options = {'company_name': [], 'address': []}
    for index, text in enumerate(texts):
        line = re.sub(r'\s+', '', text) if re.search(r'[\u4e00-\u9fff]', text) else text.strip()
        matches = list(LABEL.finditer(line))
        for position, match in enumerate(matches):
            label = match[1]
            key = 'address' if '地址' in label else 'company_name'
            end = matches[position + 1].start() if position + 1 < len(matches) else len(line)
            value = STOP.split(line[match.end():end], maxsplit=1)[0].strip(' ,，;；')
            if not value and index + 1 < len(texts):
                following = texts[index + 1].strip()
                if not re.search(r'[:：]', following):
                    if (key == 'company_name' and re.search(r'公司|工厂|加工厂|商行', following)) or (key == 'address' and re.search(r'省|市|县|区|镇|路|街|工业园', following)):
                        value = re.sub(r'\s+', '', following)
            source = 'supplier' if label.startswith(('供应', '供货', '经销')) else 'manufacturer' if label.startswith(('生产', '厂家', '制造')) else ''
            if value:
                options[key].append({'value': value, 'source': source})
        if matches:
            continue
        if re.fullmatch(r'[\u4e00-\u9fff（）()]{4,}(?:有限公司|有限责任公司|加工厂)', line):
            options['company_name'].append({'value': line, 'source': ''})
        for key in ('address', 'company_name'):
            match = PATTERNS[key].match(line)
            if not match:
                continue
            label, value = match.groups()
            if not value and index + 1 < len(texts) and not any(pattern.match(texts[index + 1].strip()) for pattern in PATTERNS.values()):
                value = texts[index + 1].strip()
            source = 'supplier' if re.match(r'suppl', label, re.I) else 'manufacturer' if re.match(r'manufactur|producer', label, re.I) else ''
            options[key].append({'value': STOP.split(value, maxsplit=1)[0].strip(), 'source': source})
            break
    # A split label may also be seen as an unlabelled company on the next line.
    for key, values in options.items():
        labelled = {item['value'] for item in values if item['source']}
        options[key] = [item for item in values if item['source'] or item['value'] not in labelled]
    return merge_party_options(options)


def apply_party_options(fields, conflicts, options):
    options = merge_party_options(options)
    for key, entries in options.items():
        if not entries:
            continue
        values = list(dict.fromkeys(entry['value'] for entry in entries))
        preferred = next((entry for entry in entries if entry['source'] == 'supplier'), entries[0])
        fields[key] = preferred['value']
        if key == 'address':
            fields['address_source'] = preferred['source']
        if len(values) > 1:
            conflicts[key] = list(dict.fromkeys(conflicts.get(key, []) + values))
    fields['_party_options'] = options
