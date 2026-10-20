import { expect, test } from '@playwright/test'

test('点击检验状态可查看报告，未检验或无附件时提醒', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const company = `报告入口${Date.now()}`
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: company } })).json()
  for (const [name, inspected] of [['未检验物料', false], ['无报告物料', true], ['有报告物料', true]] as const) {
    const record = await (await page.request.post(`/api/ledgers/${ledger.id}/records`, { data: { fields: { material_name: name }, inspection_enabled: inspected } })).json()
    if (name === '有报告物料') {
      const uploaded = await page.request.post(`/api/records/${record.id}/reports`, { multipart: { version: String(record.version), file: { name: '检验报告.txt', mimeType: 'text/plain', buffer: Buffer.from('报告内容：合格') } } })
      expect(uploaded.ok()).toBeTruthy()
    }
  }
  await page.reload()
  await page.getByRole('button', { name: `进入${company}` }).click()
  await expect(page.getByRole('row').filter({ hasText: '有报告物料' })).toContainText('1份报告')
  await expect(page.getByRole('row').filter({ hasText: '无报告物料' })).toContainText('未上传报告')
  await expect(page.getByRole('row').filter({ hasText: '未检验物料' })).toContainText('未上传报告')
  for (const [name, status, message] of [['未检验物料', '未检验', '该记录为未检验，无法查看检验报告'], ['无报告物料', '检验', '该记录尚未上传检验报告附件']] as const) {
    const dialog = page.waitForEvent('dialog').then(async alert => {
      const text = alert.message()
      await alert.accept()
      return text
    })
    await page.getByRole('row').filter({ hasText: name }).getByRole('button', { name: status, exact: true }).click()
    expect(await dialog).toBe(message)
  }
  await page.getByRole('row').filter({ hasText: '有报告物料' }).getByRole('button', { name: '检验', exact: true }).click()
  const reports = page.getByRole('dialog', { name: '检验报告附件 · 有报告物料', exact: true })
  await expect(reports.getByText('检验报告.txt', { exact: true })).toBeVisible()
  await expect(reports.getByLabel('上传报告文件')).toHaveCount(0)
  await reports.getByRole('button', { name: '查看', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '检验报告.txt', exact: true })).toContainText('报告内容：合格')
  await page.getByRole('button', { name: '关闭报告预览' }).click()
  await reports.getByRole('button', { name: '关闭附件列表' }).click()
  await expect(page.locator('.ledger-table tbody tr')).toHaveCount(3)
})
