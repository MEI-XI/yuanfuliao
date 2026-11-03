import { expect, test, type Page } from '@playwright/test'

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' })
})

async function enter(page: Page) {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: `名称候选${Date.now()}` } })).json()
  await page.reload()
  await page.getByRole('button', { name: `进入${ledger.name}`, exact: true }).click()
  await page.getByRole('button', { name: '上传与录入', exact: true }).click()
  await page.getByLabel('选择包装照片').setInputFiles('../tests/fixtures/label.png')
}

test('名称先默认填入候选并可切换，重识别保留人工输入，残缺规格不阻挡完整净含量', async ({ page }) => {
  await enter(page)
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    await route.fulfill({ response, json: { ...job, local_status: 'done', cloud_status: 'disabled',
      fields: { material_name: '鸡蛋黄粉制品', specification: '20kg' }, cloud_fields: {},
      conflicts: { material_name: ['鸡蛋黄粉制品', '鸡蛋黄粉'], specification: ['20kg/'] },
      candidate_defaults: { material_name: '鸡蛋黄粉制品', specification: '20kg' },
      field_warnings: [{ field: 'material_name', message: '名称存在待核对候选，请对照图片确认，可选择下方名称填入。' }, { field: 'specification', message: '识别到不完整规格，请核对包装单位。' }],
      review_suggestions: { fields: {}, conflicts: {}, sources: [] },
    } })
  })
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  const name = page.getByLabel('物料名称、型号', { exact: true })
  await expect(name).toHaveValue('鸡蛋黄粉制品')
  await expect(page.getByLabel('规格', { exact: true })).toHaveValue('20kg')
  const choices = page.getByRole('group', { name: '物料名称、型号识别建议', exact: true })
  await expect(choices).toContainText('待核对候选')
  await expect(choices.getByRole('button', { name: '填入：鸡蛋黄粉制品', exact: true })).toBeVisible()
  await choices.getByRole('button', { name: '填入：鸡蛋黄粉', exact: true }).click()
  await expect(name).toHaveValue('鸡蛋黄粉')
  await name.fill('人员自填名称')
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByRole('button', { name: '开始识别', exact: true })).toBeEnabled()
  await expect(name).toHaveValue('人员自填名称')
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  await page.getByRole('button', { name: '核对 / 编辑', exact: true }).click()
  await expect(name).toHaveValue('人员自填名称')
})

test('明确匹配后采用人员已核对名称，日期仍保留本次识别值', async ({ page }) => {
  await enter(page)
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    await route.fulfill({ response, json: { ...job, local_status: 'done', cloud_status: 'disabled',
      fields: { material_name: 'l-半胱氨酸', production_dates: ['2026-11-01'] }, cloud_fields: {}, conflicts: { material_name: ['l-半胱氨酸'] },
      candidate_defaults: { material_name: 'l-半胱氨酸' },
      review_suggestions: { fields: { material_name: 'L-半胱氨酸', specification: '25kg/桶' }, conflicts: {},
        sources: [{ record_id: 91, version: 2, ledger_name: '历史台账', checked_at: '2026-10-01T00:00:00Z' }], match_status: 'matched',
        inspection: { source_record_id: 91, scheme_name: '', report: {}, items: [], inspection_enabled: false, material_id: null },
      },
    } })
  })
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('L-半胱氨酸')
  await expect(page.getByLabel('生产日期', { exact: true })).toHaveValue('2026.11.01')
  await expect(page.getByLabel('规格', { exact: true })).toHaveValue('25kg/桶')
})
