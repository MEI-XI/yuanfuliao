"""Compare saved model outputs with separately reviewed photo annotations.

Does not use the historical ledger as a source for new batch dates.
Usage: python scripts/compare_ocr_samples.py baseline.json improved.json labels.json report.md
"""
import json
import sys
from pathlib import Path
from statistics import median

baseline_path, improved_path, labels_path, report_path = map(Path, sys.argv[1:])
baseline = {r['file']: r for r in json.loads(baseline_path.read_text(encoding='utf-8'))}
improved = json.loads(improved_path.read_text(encoding='utf-8'))
labels = json.loads(labels_path.read_text(encoding='utf-8'))

def name_matches(value, label):
    return label['main_name'].replace(' ', '') in value.replace(' ', '')

def safe(value):
    return str(value or '未识别').replace('|', '/').replace('\n', ' ')

scores = {'before_name': 0, 'after_name': 0, 'date_total': 0, 'before_date': 0, 'after_date': 0}
rows = []
details = []
for current in improved:
    name = current['file']
    label = next(v for prefix, v in labels.items() if name.startswith(prefix))
    old = baseline[name]['fields']; new = current['fields']
    scores['before_name'] += name_matches(old.get('material_name', ''), label)
    scores['after_name'] += name_matches(new.get('material_name', ''), label)
    expected = label.get('date')
    if expected:
        scores['date_total'] += 1
        scores['before_date'] += old.get('production_dates') == [expected]
        scores['after_date'] += new.get('production_dates') == [expected]
    rows.append('| ' + ' | '.join(map(safe, [label['main_name'], old.get('material_name'), new.get('material_name'), expected or '本图不作日期评分', '、'.join(new.get('production_dates', [])), label['note']])) + ' |')
    details.append(f"### {label['main_name']}\n\n照片：`{name}`\n\n历史台账对照：{label['reference']}\n\n{label['note']}\n\n```json\n{json.dumps(new, ensure_ascii=False, indent=2)}\n```\n")

body = f'''# 包装照片本地识别对照

测试日期：2026-10-14。共 {len(improved)} 张，使用实际照片，不调用云端，不改写原图和历史台账。

## 结果与口径

- 物料主名称：{scores['before_name']}/{len(improved)} → {scores['after_name']}/{len(improved)}。以人工读图标注的主名称是否完整出现评分，不代表型号、厂家或所有字段准确。
- 生产日期：{scores['before_date']}/{scores['date_total']} → {scores['after_date']}/{scores['date_total']}。只统计包装上能明确确认的日期，ISO 日期完全一致才计正确；界面和导出显示为年月日点分格式。
- 改进后单图耗时 {min(r['seconds'] for r in improved):.1f}～{max(r['seconds'] for r in improved):.1f} 秒，中位数 {median(r['seconds'] for r in improved):.1f} 秒。本机 i5-14400、约16GB内存，CPU运行，同期有开发进程，非独占性能测试。

样本参与了规则调整，属于本组回归结果，不是独立测试集准确率。下一步需补充未见过的包装、不同光照与手机拍摄作为独立验收。

羊肚油、鸡蛋黄粉的日期区域未清晰展示；牛油包装标注“见合格证”，图中另有 20260815，但无法仅凭包装确定其性质，因此这三张不计生产日期分母，也不擅自填入拍摄水印或该数字。

历史台账 `原辅料查验记录2025年7月.xlsx` 用于核对字段与同物料资料。虽然文件名含2025年7月，实际数据延续至2026年，且并非这批照片的同批次记录。不同厂家、包装规格、日期不作为模型错误；历史数据不补写到识别结果。

## 逐张结果

| 照片主名称 | 首轮名称 | 改进名称 | 人工确认日期 | 改进日期 | 待核对事项 |
| --- | --- | --- | --- | --- | --- |
''' + '\n'.join(rows) + '\n\n## 字段与台账对照\n\n' + '\n'.join(details)
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(body, encoding='utf-8')
print(json.dumps(scores, ensure_ascii=False))
