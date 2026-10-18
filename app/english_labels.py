"""Read explicit English labels locally. Translation is a separate cloud suggestion."""
import re
from datetime import date

LABELS = {
    'material_name': r'product\s*name|material\s*name|commodity|product',
    'company_name': r'manufactured\s*by|manufacturer|supplier|supplied\s*by|producer',
    'specification': r'net\s*(?:weight|wt\.?|content)|specification|pack\s*size',
    'address': r'manufacturer\s*address|supplier\s*address|address',
    'contact': r'contact|telephone|phone|tel\.?',
    'production_dates': r'manufactur(?:ing|e)\s*date|date\s*of\s*manufacture|production\s*date|mfg\.?\s*(?:date)?|mfd\.?',
    'expiry_date': r'expiry\s*date|expiration\s*date|expiry|expires|best\s*before(?:\s*end)?|use\s*by|exp\.?\s*(?:date)?',
    'shelf_life': r'shelf\s*life',
    'packaging': r'packaging|packing(?:\s*type)?',
    'batch_number': r'batch\s*(?:no\.?|number)|lot\s*(?:no\.?|number)',
    'basis': r'product\s*standard|standard',
    'received_quantity': r'received\s*quantity|delivered\s*quantity',
}
DATE_LABEL = re.compile(r'(?:' + LABELS['production_dates'] + '|' + LABELS['expiry_date'] + r')\s*[:：]?\s*', re.I)
PATTERNS = {key: re.compile(r'^(' + label + r')(?=\s|[:：]|\d|$)\s*[:：]?\s*(.*)$', re.I) for key, label in LABELS.items()}
MONTHS = {name: i for i, name in enumerate(('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'), 1)}


def is_english_packaging(texts):
    for line in texts:
        for key in ('material_name', 'company_name', 'address', 'packaging'):
            match = PATTERNS[key].match(line.strip())
            if match and re.search(r'[A-Za-z]{2}', match[2]) and not re.search(r'[\u4e00-\u9fff]', match[2]):
                return True
    text = ' '.join(texts)
    latin = len(re.findall(r'[A-Za-z]', text))
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    return latin >= 20 and latin > chinese * 3


def english_dates(value):
    candidates = []
    ymd = re.search(r'(?<!\d)(20\d{2})[./-]?(\d{2})[./-]?(\d{2})(?!\d)', value)
    if not ymd:
        ymd = re.search(r'(?<!\d)(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)', value)
    if ymd:
        candidates.append(tuple(map(int, ymd.groups())))
    else:
        named = re.search(r'(?<!\d)(\d{1,2})[\s./-]+([A-Za-z]{3,9})[\s./-]+(20\d{2})', value)
        if named and named[2][:3].upper() in MONTHS:
            candidates.append((int(named[3]), MONTHS[named[2][:3].upper()], int(named[1])))
        named = re.search(r'([A-Za-z]{3,9})[\s./-]+(\d{1,2})[\s,./-]+(20\d{2})', value)
        if named and named[1][:3].upper() in MONTHS:
            candidates.append((int(named[3]), MONTHS[named[1][:3].upper()], int(named[2])))
        numeric = re.search(r'(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?!\d)', value)
        if numeric:
            first, second, year = map(int, numeric.groups())
            candidates.extend([(year, second, first), (year, first, second)])
    dates = []
    for parts in candidates:
        try:
            formatted = date(*parts).isoformat()
            if formatted not in dates:
                dates.append(formatted)
        except ValueError:
            pass
    return dates


def parse_english_labels(texts, conflicts):
    fields, found, companies = {}, {}, {}
    for i, raw in enumerate(texts):
        line = raw.strip()
        # Long labels such as manufacturer address must precede manufacturer.
        for key in sorted(PATTERNS, key=lambda key: key not in ('address', 'production_dates', 'expiry_date', 'basis')):
            match = PATTERNS[key].match(line)
            if not match:
                continue
            label, value = match.groups()
            if not value and i + 1 < len(texts) and not any(p.match(texts[i + 1].strip()) for p in PATTERNS.values()):
                value = texts[i + 1].strip()
            if not value:
                break
            values = [value]
            if key in ('production_dates', 'expiry_date'):
                values = english_dates(value)
                if len(values) > 1:
                    conflicts[key] = list(dict.fromkeys(conflicts.get(key, []) + values))
                    break
            elif key == 'shelf_life':
                duration = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(years?|months?|days?)', value, re.I)
                if duration:
                    amount = float(duration[1]) * (12 if duration[2].lower().startswith('year') else 1)
                    values = [f'{amount:g}' + ('天' if duration[2].lower().startswith('day') else '个月')]
            elif key == 'company_name':
                source = 'supplier' if re.match(r'suppl', label, re.I) else 'manufacturer'
                companies.setdefault(source, []).append(value)
                break
            elif key == 'address' and re.match(r'manufacturer|supplier', label, re.I):
                fields['address_source'] = 'supplier' if label.lower().startswith('supplier') else 'manufacturer'
            for value in values:
                if value not in found.setdefault(key, []):
                    found[key].append(value)
            break
    if companies:
        found['company_name'] = companies.get('supplier') or companies['manufacturer']
    for key, values in found.items():
        if not values or key in conflicts:
            continue
        if key == 'production_dates':
            fields[key] = values
        elif len(values) == 1:
            fields[key] = values[0]
        else:
            conflicts[key] = values
    return fields
