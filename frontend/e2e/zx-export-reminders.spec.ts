import { test, expect } from '@playwright/test'

test('未检验记录 Excel 直接导出，Word 弹窗阻止下载', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) {
    await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  }
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: '导出提醒测试' } })).json()
  const created = await page.request.post(`/api/ledgers/${ledger.id}/records`, {
    data: { fields: { material_name: '未检验提醒样本' } },
  })
  expect(created.status()).toBe(201)
  const record = await created.json()
  expect((await page.request.post(`/api/records/${record.id}/check`, { data: { version: record.version } })).status()).toBe(200)
  await page.reload()
  await page.getByRole('button', { name: '进入导出提醒测试' }).click()
  await page.getByRole('button', { name: '清空选择', exact: true }).click()
  await page.getByRole('row').filter({ hasText: '未检验提醒样本' }).getByRole('checkbox').check()
  const exports: string[] = []
  page.on('request', request => {
    if (/\/api\/exports\/(xlsx|docx)$/.test(request.url())) exports.push(request.url())
  })

  const excelDialogs: string[] = []
  const unexpectedDialog = async (dialog: import('@playwright/test').Dialog) => {
    excelDialogs.push(dialog.message())
    await dialog.dismiss()
  }
  page.on('dialog', unexpectedDialog)
  const download = page.waitForEvent('download', { timeout: 5000 })
  await page.getByRole('button', { name: '导出 Excel', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('原辅料查验记录.xlsx')
  expect(excelDialogs).toEqual([])
  expect(exports).toHaveLength(1)
  page.off('dialog', unexpectedDialog)

  const wordDialog = page.waitForEvent('dialog')
  const wordClick = page.getByRole('button', { name: '导出 Word', exact: true }).click()
  const blocked = await wordDialog
  expect(blocked.type()).toBe('alert')
  expect(blocked.message()).toContain('取消勾选未检验记录')
  await blocked.accept()
  await wordClick
  expect(exports).toHaveLength(1)
})
