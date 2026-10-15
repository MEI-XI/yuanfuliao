"""Fill missing shelf-life fields from explicit dates and durations."""
import calendar
import re
from datetime import date, timedelta


def normalize_shelf_life(value: str) -> str:
    """Express explicit years and months in months; retain other printed values."""
    compact = re.sub(r'\s+', '', value)
    number = r'(\d+|[一二三])'
    if re.fullmatch(r'\d+', compact):
        months = int(compact)
    else:
        duration = re.fullmatch(rf'(?:{number}年)?(?:{number}(?:个)?月)?', compact)
        if not duration or not any(duration.groups()):
            return value
        years, months = (int({'一': '1', '二': '2', '三': '3'}.get(part, part)) if part else 0
                         for part in duration.groups())
        months += years * 12
    return f'{months}个月' if months > 0 else value


def _add_months(start: date, months: int) -> date:
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    month += 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def derive_shelf_life(production_dates: list[str], shelf_life: str, expiry_date: str | None) -> dict:
    """Normalize duration units and fill blanks without replacing supplied dates."""
    shelf_life = normalize_shelf_life(shelf_life)
    result = {'shelf_life': shelf_life, 'expiry_date': expiry_date, 'warnings': []}
    warnings = result['warnings']
    duration = re.fullmatch(r'\s*(\d+|[一二三])\s*(?:个)?\s*(月|年|天|日)\s*', shelf_life)
    amount = int({'一': '1', '二': '2', '三': '3'}.get(duration[1], duration[1])) if duration else 0
    if shelf_life and (not duration or amount <= 0):
        warnings.append('保质期不是明确的正整数期限，请核对后填写年月或天数。')
    if duration and amount > 0 and duration[2] in {'天', '日'}:
        warnings.append('保质期以天数标注，已保留原文，请人工核对')
    if not production_dates:
        if shelf_life or expiry_date:
            warnings.append('缺少生产日期，无法自动补全保质期信息。')
        return result
    production = min(date.fromisoformat(value) for value in production_dates)
    if len(set(production_dates)) > 1:
        warnings.append(f'存在多个生产日期，按最早日期 {production.isoformat()} 计算，请核对。')
    expiry = date.fromisoformat(expiry_date) if expiry_date else None
    if expiry and expiry < production:
        warnings.append('保质期至早于生产日期，请核对。')
        return result
    if duration and amount > 0:
        try:
            if duration[2] in {'月', '年'}:
                calculated = _add_months(production, amount * (12 if duration[2] == '年' else 1)) - timedelta(days=1)
            else:
                calculated = production + timedelta(days=amount - 1)
        except (ValueError, OverflowError):
            warnings.append('保质期计算超出日期范围，请人工核对。')
            return result
        if expiry:
            if expiry != calculated:
                warnings.append(f'保质期至与期限计算结果 {calculated.isoformat()} 不一致，已保留填写的日期，请核对。')
        else:
            result['expiry_date'] = calculated.isoformat()
    elif not shelf_life and expiry:
        inclusive_days = (expiry - production).days + 1
        if expiry == date.max:
            result['shelf_life'] = f'{inclusive_days}天'
        else:
            exclusive_end = expiry + timedelta(days=1)
            months = (exclusive_end.year - production.year) * 12 + exclusive_end.month - production.month
            if months > 0 and _add_months(production, months) == exclusive_end:
                result['shelf_life'] = f'{months}个月'
            else:
                result['shelf_life'] = f'{inclusive_days}天'
        if result['shelf_life'].endswith('天'):
            warnings.append('保质期以天数标注，已保留原文，请人工核对')
    elif not shelf_life:
        warnings.append('缺少保质期或保质期至，无法自动计算。')
    return result


def complete_expiry_fields(fields: dict, conflicts: dict | None = None) -> dict:
    """Complete recognition output only after all printed evidence is combined."""
    if conflicts and {'shelf_life', 'expiry_date'} & conflicts.keys():
        return fields
    derived = derive_shelf_life(fields.get('production_dates', []), fields.get('shelf_life', ''), fields.get('expiry_date'))
    return fields | {key: derived[key] for key in ('shelf_life', 'expiry_date') if derived[key]}
