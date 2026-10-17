"""User-facing request validation errors, without echoing submitted secrets."""
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

LABELS = {
    'arrival_date': '到货日期', 'production_dates': '生产日期', 'expiry_date': '保质期至',
    'inspection_date': '检验日期', 'material_name': '物料名称、型号', 'name': '名称',
    'specification': '规格', 'company_name': '供应商或生产商', 'address': '地址',
    'contact': '联系方式', 'shelf_life': '保质期', 'received_quantity': '接收数量',
    'certificates': '随车证件', 'sensory': '感官检验', 'sampling_items': '抽检项目',
    'notes': '备注', 'packaging': '包装', 'batch_number': '产品批号', 'basis': '检验依据',
    'conclusion': '判定结论', 'result': '检验结果', 'standard': '标准规定',
    'internal_report': '是否提供内检报告', 'items': '检验项目', 'image_ids': '包装照片',
    'record_ids': '所选记录', 'records': '所选记录', 'username': '账号', 'password': '密码',
    'model': '型号', 'aliases': '常用别名', 'kind': '单位类型', 'role': '账号权限',
    'material_id': '共享物料', 'scheme_id': '检验标准方案', 'ledger_id': '公司台账',
    'address_source': '地址来源', 'contact_source': '联系方式来源', 'version': '记录版本',
    'from_date': '开始日期', 'to_date': '结束日期', 'request_id': '批量保存编号',
    'inspection_enabled': '检验状态', 'mark_checked': '标记已核对', 'file': '上传文件',
}


def field_label(location, path):
    parts = []
    for index, key in enumerate(location):
        if key in ('body', 'query', 'path', 'fields', 'report'):
            continue
        if isinstance(key, int):
            previous = location[index - 1] if index else ''
            if previous == 'records':
                parts[-1] = f'本次提交第{key + 1}条记录'
            elif parts:
                parts[-1] += f'第{key + 1}项'
            continue
        label = LABELS.get(key, str(key))
        if key == 'name' and 'items' not in location:
            label = next((value for route, value in [('materials', '物料名称'), ('schemes', '方案名称'),
                         ('partners', '供应商或生产商名称'), ('ledgers', '公司台账名称')]
                          if f'/{route}' in path), label)
        parts.append(label)
    return ' → '.join(parts) or '提交内容'


def correction(error):
    kind, context = error['type'], error.get('ctx', {})
    if kind.startswith(('date_', 'datetime_')):
        return '请填写有效日期，例如 2026.01.14；检查月份和天数，多个生产日期用顿号分隔。不确定时可清空。'
    if kind in ('string_too_long', 'too_long'):
        unit = '个字符' if kind == 'string_too_long' else '项'
        return f'最多允许{context.get("max_length", "规定数量")}{unit}，请删减后再保存。'
    if kind in ('string_too_short', 'too_short'):
        unit = '个字符' if kind == 'string_too_short' else '项'
        return f'至少需要{context.get("min_length", 1)}{unit}，请补充填写或选择。'
    if kind == 'missing':
        return '此项为必填，请填写或重新选择。'
    if kind == 'literal_error':
        return '当前选项无效，请从下拉框重新选择。'
    if kind == 'extra_forbidden':
        return '此项不受支持，请保留当前填写内容并联系管理员检查页面版本。'
    if kind == 'value_error':
        message = str(error.get('msg', '')).removeprefix('Value error, ')
        if any('\u4e00' <= char <= '\u9fff' for char in message):
            return message + '，请修改此项。'
    if kind.startswith(('int_', 'float_', 'decimal_', 'greater_than', 'less_than')):
        return '请填写符合要求的数字；若为所选资料，请重新选择。'
    return '格式不正确，请核对该项内容或重新选择后再保存。'


async def validation_error_response(request, exc: RequestValidationError):
    messages = list(dict.fromkeys(f'{field_label(error["loc"], request.url.path)}：{correction(error)}'
                                 for error in exc.errors()))
    return JSONResponse(status_code=422, content={
        'detail': '请检查以下内容，修改后重新保存：\n' + '\n'.join(messages)})
