import { expect, test, type Page } from '@playwright/test'

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: 'wait' }) })

async function enter(page: Page) {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: `辅助模式${Date.now()}` } })).json()
  await page.reload()
  await page.getByRole('button', { name: `进入${ledger.name}`, exact: true }).click()
  await page.getByRole('button', { name: '上传与录入', exact: true }).click()
  await page.getByLabel('选择包装照片').setInputFiles('../tests/fixtures/label.png')
}

test('DeepSeek 默认关闭思考，可选择低强度；辅助失败保留基础识别和人工输入', async ({ page }) => {
  await enter(page)
  const mode = page.getByRole('combobox', { name: '辅助思考模式', exact: true })
  await expect(mode).toHaveValue('disabled')
  const auxiliary = page.getByRole('checkbox', { name: '云端辅助', exact: true })
  await auxiliary.uncheck()
  await expect(mode).toBeDisabled()
  await auxiliary.check()

  let job: Record<string, unknown> = {}
  const requests: Record<string, unknown>[] = []
  await page.route('**/api/ledgers/*/recognition', async route => {
    const body = route.request().postDataJSON()
    requests.push(body)
    job = { id: 900 + requests.length, image_ids: body.image_ids, cloud_thinking: body.cloud_thinking,
      local_status: 'done', cloud_status: 'failed', fields: { material_name: '甘氨酸', specification: '25kg/袋' }, cloud_fields: {},
      evidence: [], conflicts: {}, error: '', cloud_error: 'DeepSeek 辅助暂不可用；基础识别结果已保留',
      review_suggestions: { fields: {}, conflicts: {}, sources: [] } }
    await route.fulfill({ status: 202, json: job })
  })
  await page.route('**/api/recognition/*', async route => { await route.fulfill({ json: job }) })
  const start = page.getByRole('button', { name: '开始识别', exact: true })
  await start.click()
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('甘氨酸')
  await expect(page.getByLabel('规格', { exact: true })).toHaveValue('25kg/袋')
  await expect(page.getByText('DeepSeek 辅助暂不可用；基础识别结果已保留', { exact: true })).toBeVisible()
  expect(requests[0]).toMatchObject({ cloud_enabled: true, cloud_thinking: 'disabled' })
  await page.getByLabel('物料名称、型号', { exact: true }).fill('人员核对名称')
  await mode.selectOption('low')
  await start.click()
  await expect(start).toBeEnabled()
  expect(requests[1]).toMatchObject({ cloud_enabled: true, cloud_thinking: 'low' })
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('人员核对名称')
  await expect(page.getByLabel('规格', { exact: true })).toHaveValue('25kg/袋')
  await mode.scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../tmp/deepseek-mode-desktop.png' })
  await page.setViewportSize({ width: 390, height: 844 })
  await mode.scrollIntoViewIfNeeded()
  await expect(mode).toBeInViewport()
  await page.screenshot({ path: '../tmp/deepseek-mode-mobile.png' })
})

test('历史辅助识别任务不误标为 DeepSeek 关闭思考', async ({ page }) => {
  await enter(page)
  const job = { id: 901, image_ids: [], cloud_thinking: null, local_status: 'done', cloud_status: 'done',
    fields: { material_name: '甘氨酸' }, cloud_fields: {}, evidence: [], conflicts: {}, error: '', cloud_error: '',
    review_suggestions: { fields: {}, conflicts: {}, sources: [] } }
  await page.route('**/api/ledgers/*/recognition', async route => { await route.fulfill({ status: 202, json: job }) })
  await page.route('**/api/recognition/*', async route => { await route.fulfill({ json: job }) })
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.locator('.recognition-progress')).toContainText('辅助识别（历史任务）：建议已返回')
  await expect(page.locator('.recognition-progress')).not.toContainText('DeepSeek')
})

test('管理员查看模型网关状态并测试连接，无需在网页填写密钥', async ({ page }) => {
  await enter(page)
  await page.route('**/api/settings/cloud', async route => { await route.fulfill({ json: { configured: true, model: 'deepseek-flash', provider: 'DeepSeek', default_thinking: 'disabled' } }) })
  await page.route('**/api/settings/cloud/test', async route => { await route.fulfill({ json: { ok: true, message: '连接成功：DeepSeek 模型可用。' } }) })
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
  await page.getByRole('button', { name: '云端与模板', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'DeepSeek 云端辅助', exact: true })).toBeVisible()
  await expect(page.getByText('模型：deepseek-flash', { exact: true })).toBeVisible()
  await expect(page.getByLabel('API 密钥')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /配置密钥|更新密钥|清除密钥/ })).toHaveCount(0)
  await page.getByRole('button', { name: '测试连接', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '连接成功：DeepSeek 模型可用。' })).toBeVisible()
})
