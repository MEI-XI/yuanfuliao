import { test, expect } from '@playwright/test'

test('历史检验内容只填空白，本次日期数量及人工输入保留', async ({ page }) => {
  await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '新建公司台账' })).toBeVisible()
  await page.request.post('/api/ledgers', { data: { name: '历史复用测试公司' } })
  await page.reload()
  await page.getByRole('button', { name: '进入历史复用测试公司' }).click()
  await page.getByRole('button', { name: '上传与录入' }).click()
  await page.getByRole('radio', { name: '检验', exact: true }).check()
  await page.getByLabel('检验依据', { exact: true }).fill('本次人工依据')
  await page.getByLabel('接收数量', { exact: true }).fill('8袋')
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    const inspection = { source_record_id: 91, scheme_name: '旧标准', report: { basis: '旧标准', packaging: '纸塑袋', conclusion: '合格' }, items: [{ name: '含量', standard: '≥98.5%', unit: '', result: '99.2%', conclusion: '合格' }] }
    await route.fulfill({ response, json: { ...job, local_status: 'done', cloud_status: 'disabled',
      fields: { material_name: '甘氨酸', production_dates: ['2026-10-01'], shelf_life: '24个月', received_quantity: '6袋' }, cloud_fields: {}, conflicts: {},
      review_suggestions: { fields: { material_name: '甘氨酸', sensory: '白色粉末' }, conflicts: {}, sources: [{ record_id: 91, version: 2, ledger_name: '公司', checked_at: '2025-01-01T00:00:00Z' }], inspection, inspection_choices: [inspection] },
    } })
  })
  await page.getByLabel('选择包装照片').setInputFiles('../tests/fixtures/label.png')
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByLabel('检验结果', { exact: true })).toHaveValue('99.2%')
  await expect(page.getByLabel('检验依据', { exact: true })).toHaveValue('本次人工依据')
  await expect(page.getByLabel('接收数量', { exact: true })).toHaveValue('8袋')
  await expect(page.getByLabel('生产日期', { exact: true })).toHaveValue('2026.10.01')
  await expect(page.getByLabel('保质期', { exact: true })).toHaveValue('24个月')
  await expect(page.getByLabel('感官检验', { exact: true })).toHaveValue('白色粉末')
  await expect(page.getByRole('region', { name: '历史复核参考' })).toContainText('需按本次实际检验核对')
  await page.getByLabel('检验结果', { exact: true }).fill('人工修改结果')
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByRole('button', { name: '开始识别', exact: true })).toBeEnabled()
  await expect(page.getByLabel('检验结果', { exact: true })).toHaveValue('人工修改结果')
  await page.getByRole('button', { name: '移除检验项目 含量', exact: true }).click()
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByRole('button', { name: '开始识别', exact: true })).toBeEnabled()
  await expect(page.getByLabel('检验结果', { exact: true })).toHaveCount(0)
})

test('英文原文可查看，中文翻译补空白且不覆盖人工输入', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '进入历史复用测试公司' }).click()
  await page.getByRole('button', { name: '上传与录入' }).click()
  await page.getByLabel('供应商或生产商', { exact: true }).fill('人工供应商')
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    await route.fulfill({ response, json: { ...job, local_status: 'done', cloud_status: 'done', english_detected: true,
      fields: { material_name: 'Glycine', company_name: 'Example Food Co.', production_dates: ['2026-01-14'] },
      cloud_fields: { material_name: '甘氨酸', company_name: '示例食品公司' },
      evidence: [{ texts: ['Product Name: Glycine'], boxes: [] }], conflicts: {},
      review_suggestions: { fields: {}, conflicts: {}, sources: [] },
    } })
  })
  await page.getByLabel('选择包装照片').setInputFiles('../tests/fixtures/label.png')
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('甘氨酸')
  await expect(page.getByLabel('供应商或生产商', { exact: true })).toHaveValue('人工供应商')
  await expect(page.getByLabel('生产日期', { exact: true })).toHaveValue('2026.01.14')
  await expect(page.getByRole('status', { name: '英文包装识别' })).toContainText('中文翻译')
  await page.getByRole('group', { name: '供应商或生产商识别建议', exact: true }).getByRole('button', { name: '填入：示例食品公司', exact: true }).click()
  await expect(page.getByLabel('供应商或生产商', { exact: true })).toHaveValue('示例食品公司')
})
