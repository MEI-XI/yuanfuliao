import { expect, test, type Page } from '@playwright/test'

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' })
})

async function openBatch(page: Page) {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: `批量暂存${Date.now()}` } })).json()
  await page.reload()
  await page.getByRole('button', { name: `进入${ledger.name}`, exact: true }).click()
  await page.getByRole('button', { name: '上传与录入', exact: true }).click()
  await page.getByRole('button', { name: '多种物料批量', exact: true }).click()
  await page.getByLabel('选择包装照片').setInputFiles(Array(3).fill('../tests/fixtures/label.png'))
  for (let index = 1; index <= 3; index++) {
    await page.getByRole('button', { name: `记录 ${index} · 1 张`, exact: true }).click()
    await page.getByLabel('物料名称、型号', { exact: true }).fill(`暂存物料${index}`)
  }
  return ledger.id as number
}

test('识别未完成时在图片旁选择分组，只能暂存所选记录为待核对', async ({ page }) => {
  const ledger = await openBatch(page)
  const pictureHeader = page.locator('.panel-heading').filter({ has: page.getByRole('heading', { name: '包装图片', exact: true }) })
  await expect(pictureHeader.getByRole('button', { name: '全选分组', exact: true })).toBeVisible()
  await pictureHeader.getByRole('button', { name: '全选分组', exact: true }).click()
  await pictureHeader.getByRole('button', { name: '全部清空', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '选择分组 1', exact: true })).not.toBeChecked()
  await page.getByRole('checkbox', { name: '选择分组 1', exact: true }).check()
  await page.getByRole('checkbox', { name: '选择分组 2', exact: true }).check()
  const check = page.getByRole('checkbox', { name: '同时标记为已核对', exact: true })
  await check.check()
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    await route.fulfill({ response, json: { ...job, local_status: 'running', cloud_status: 'queued', fields: {}, cloud_fields: {}, candidate_defaults: {}, conflicts: {}, review_suggestions: { fields: {}, conflicts: {}, sources: [] } } })
  })
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(check).toBeDisabled()
  await expect(check).not.toBeChecked()
  const save = page.getByRole('button', { name: '保存所选 2 条记录', exact: true })
  await expect(save).toBeEnabled()
  await expect(page.getByRole('status', { name: '识别中保存提示' })).toContainText('待核对')
  await pictureHeader.screenshot({ path: '../tmp/batch-selection-desktop.png' })
  const request = page.waitForRequest(request => request.url().endsWith('/records/batch') && request.method() === 'POST')
  await save.click()
  const body = (await request).postDataJSON()
  expect(body.mark_checked).toBe(false)
  expect(body.records).toHaveLength(2)
  expect(body.records.every((record: { recognition_job_id: unknown }) => Number.isInteger(record.recognition_job_id))).toBe(true)
  await expect(page.getByText('已保存 2 条记录，待核对；还剩 1 条未保存', { exact: true })).toBeVisible()
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('暂存物料3')
  await expect(page.getByRole('button', { name: '保存记录', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '保存并标记已核对', exact: true })).toBeDisabled()
  const records = await (await page.request.get(`/api/ledgers/${ledger}/records`)).json()
  expect(records.map((record: { fields: { material_name: string } }) => record.fields.material_name).sort()).toEqual(['暂存物料1', '暂存物料2'])
  expect(records.every((record: { status: string }) => record.status === 'pending')).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(pictureHeader.getByRole('button', { name: '全部清空', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.locator('.image-panel').screenshot({ path: '../tmp/batch-pending-mobile.png' })
})

test('所选组云端完成后可核对，其他组识别不阻挡保存，重试不重复创建', async ({ page }) => {
  const ledger = await openBatch(page)
  const firstImage = Number((await page.getByRole('button', { name: '预览记录 1 的图片 1', exact: true }).locator('img').getAttribute('src'))!.split('/').pop())
  await page.getByRole('checkbox', { name: '云端辅助', exact: true }).uncheck()
  await page.getByRole('checkbox', { name: '选择分组 1', exact: true }).check()
  let firstComplete = false
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    await route.fulfill({ response, json: { ...job, local_status: 'done',
      cloud_status: firstComplete && job.image_ids[0] === firstImage ? 'done' : 'running',
      fields: {}, cloud_fields: {}, candidate_defaults: {}, conflicts: {}, review_suggestions: { fields: {}, conflicts: {}, sources: [] },
    } })
  })
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  const check = page.getByRole('checkbox', { name: '同时标记为已核对', exact: true })
  await expect(check).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存所选 1 条记录', exact: true })).toBeEnabled()
  firstComplete = true
  await expect(check).toBeEnabled()
  await expect(check).not.toBeChecked()
  await check.check()
  const submissions: unknown[] = []
  await page.route('**/records/batch', async route => {
    submissions.push(route.request().postDataJSON())
    const response = await route.fetch()
    if (submissions.length === 1) await route.fulfill({ status: 502, json: { detail: '模拟响应中断' } })
    else await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '保存所选 1 条记录', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('尚未确认')
  await page.getByRole('button', { name: '重试批量保存', exact: true }).click()
  await expect(page.getByText('已保存 1 条记录，并标记为已核对；还剩 2 条未保存', { exact: true })).toBeVisible()
  expect(submissions).toHaveLength(2)
  expect(submissions[1]).toEqual(submissions[0])
  const records = await (await page.request.get(`/api/ledgers/${ledger}/records`)).json()
  expect(records).toHaveLength(1)
  expect(records[0].status).toBe('checked')
})
