import re


def normalize_scheme_name(value: str) -> str:
    value = value.strip()
    cleaned = re.sub(r'^依据该公司提供的内检报告为准\s*[.。．:：；;]*\s*', '', value)
    if cleaned != value and cleaned.startswith('（') and cleaned.endswith('）'):
        cleaned = cleaned[1:-1].strip()
    return cleaned
