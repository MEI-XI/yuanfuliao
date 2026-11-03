"""Rank names supported by printed labels and titles without a suffix gate."""
import math
import re
import statistics
import unicodedata


NAME_LABEL = re.compile(r'^(?:产品名称|品名|名称)[:：](.*)$')
CATEGORY_LINES = {'食品添加剂', '复配食品添加剂', '食品用香精', '食品配料', '食品原料'}
SECTION_LINES = CATEGORY_LINES | {'合格', '合格证', '营养成分表', '营养成分', '蛋白质', '脂肪', '碳水化合物', '能量', '钠', '配料', '配料表', '品名', '名称', '产品名称', '规格', '净含量', '生产日期', '保质期'}
PRODUCT_WORD = re.compile(r'酸|粉|油|酱|香精|提取物|抽提物|膜|袋|糖|盐|消泡剂|蛋白|淀粉|制品|调味料|香料')


def _clean(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).replace('：', ':')


def _possible_name(value, *, explicit=False):
    if not re.fullmatch(r'[A-Za-z0-9\u4e00-\u9fff()（）/.*×+\-]{2,60}', value) or not re.search(r'[\u4e00-\u9fff]', value):
        return False
    if value in SECTION_LINES and not explicit:
        return False
    # Reject information roles and sentences, not words inside product names.
    if re.search(r'(?:有限公司|有限责任公司|股份公司|集团公司|食品厂|加工厂)$', value):
        return False
    if re.match(r'^(?:生产日期|生产批号|生产地址|生产商|生产厂家|供应商|制造商|委托方|被委托方|地址|联系电话|联系方式|电话|传真|邮编|网址|产地|净含量|保质期|配料表|营养成分|产品标准|执行标准|许可证|贮存条件|储存条件|使用方法|使用范围|使用量)', value):
        return False
    if re.match(r'^(?:请|本品|本产品|用于|仅供|不可|不得|禁止|建议|应当|保存于|贮存于|储存于|含有)', value):
        return False
    if re.search(r'(?:置于|避免|储存|贮存|通风|阴凉|干燥处|见封口|见包装|见合格证|仅供参考)', value):
        return False
    if re.search(r'(?:省|市|县|区).*(?:路|街|镇|工业园)|(?:路|街)\d+号', value):
        return False
    if re.match(r'^(?:蛋白质|脂肪|碳水化合物|能量|钠)\d', value):
        return False
    return True


def _height(box):
    try:
        return min(math.dist(box[0], box[3]), math.dist(box[0], box[1]))
    except (IndexError, TypeError, ValueError):
        return 0


def material_candidates(texts, boxes=None, *, raw_text=''):
    """Return ordered names and whether the selected name needs review."""
    lines = [_clean(re.sub(r'^\s*#+\s*', '', text).replace('**', '')) for text in texts]
    headings = {_clean(re.sub(r'^\s*#+\s*', '', text).replace('**', ''))
                for text in raw_text.splitlines() if re.match(r'^\s*#+\s+', text)}
    heights = [_height(box) for box in boxes] if boxes is not None and len(boxes) == len(lines) else [0] * len(lines)
    baseline = statistics.median([height for height in heights if height > 0]) if any(heights) else 0
    explicit, scored = [], []
    for index, line in enumerate(lines):
        label = NAME_LABEL.match(line)
        if label:
            value = label[1]
            if not value and index + 1 < len(lines):
                value = lines[index + 1]
            if _possible_name(value, explicit=True) and value not in explicit:
                explicit.append(value)
        elif line in {'品名', '名称', '产品名称'} and index + 1 < len(lines) and _possible_name(lines[index + 1], explicit=True):
            if lines[index + 1] not in explicit:
                explicit.append(lines[index + 1])
        if not _possible_name(line):
            continue
        heading = bool(re.match(r'^\s*#+\s+', texts[index])) or line in headings
        prominent = baseline > 0 and heights[index] >= baseline * 1.5
        category = index > 0 and lines[index - 1] in CATEGORY_LINES
        product = bool(PRODUCT_WORD.search(line))
        bilingual_brand = re.fullmatch(r'[A-Za-z]+([\u4e00-\u9fff]{2,4})', line)
        if bilingual_brand and not (category or product) and any(
            re.search(re.escape(bilingual_brand[1]) + r'.*(?:公司|工厂)$', other) for other in lines
        ):
            continue
        if len(line) < 3 and not (category or product):
            continue
        if not (heading or prominent or category or product):
            continue
        score = (3 if heading else 0) + (3 if prominent else 0) + (3 if category else 0) + (1 if product else 0)
        scored.append((score, -index, line))
    if explicit:
        return explicit, len(explicit) > 1
    ordered = list(dict.fromkeys(value for _, _, value in sorted(scored, reverse=True)))
    # A title without an explicit name label remains a reviewable default.
    return ordered, bool(ordered)
