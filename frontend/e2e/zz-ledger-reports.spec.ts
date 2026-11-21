import { expect, test, type Page } from '@playwright/test'

async function signIn(page: Page, username: string) {
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
}

function reportFile(name: string, content: string) {
  return { name, mimeType: 'text/plain', buffer: Buffer.from(content) }
}

test('检验报告弹窗允许创建人反复上传和更换，其他普通用户只能查看', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await signIn(page, 'admin')
  const company = `报告入口${Date.now()}`
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: company } })).json()
  const creator = `report-creator-${Date.now()}`
  const reader = `report-reader-${Date.now()}`
  for (const username of [creator, reader]) {
    const response = await page.request.post('/api/users', { data: { username, password: 'browser-test-password', role: 'user' } })
    expect(response.status()).toBe(201)
  }
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await signIn(page, creator)
  let reportId = 0
  let recordId = 0
  for (const [name, inspected] of [['未检验物料', false], ['无报告物料', true], ['有报告物料', true]] as const) {
    const created = await page.request.post(`/api/ledgers/${ledger.id}/records`, { data: { fields: { material_name: name }, inspection_enabled: inspected } })
    expect(created.status()).toBe(201)
    const record = await created.json()
    if (name === '有报告物料') {
      recordId = record.id
      const uploaded = await page.request.post(`/api/records/${record.id}/reports`, { multipart: { version: String(record.version), file: reportFile('检验报告.txt', '报告内容：合格') } })
      expect(uploaded.ok()).toBeTruthy()
      reportId = (await uploaded.json()).attachment.id
    }
  }
  await page.reload()
  await page.getByRole('button', { name: `进入${company}` }).click()
  await expect(page.getByRole('row').filter({ hasText: '有报告物料' })).toContainText('1份报告')
  await expect(page.getByRole('row').filter({ hasText: '无报告物料' })).toContainText('未上传报告')
  await expect(page.getByRole('row').filter({ hasText: '未检验物料' })).toContainText('未上传报告')
  await page.getByLabel('筛选报告附件').selectOption('uploaded')
  await expect(page.locator('.ledger-table tbody tr')).toHaveCount(1)
  await expect(page.locator('.ledger-table tbody tr')).toContainText('有报告物料')
  await page.getByLabel('筛选报告附件').selectOption('missing')
  await expect(page.locator('.ledger-table tbody tr')).toHaveCount(2)
  await page.getByLabel('筛选检验状态').selectOption('inspected')
  await expect(page.locator('.ledger-table tbody tr')).toHaveCount(1)
  await expect(page.locator('.ledger-table tbody tr')).toContainText('无报告物料')
  await page.getByRole('button', { name: '清空筛选', exact: true }).click()
  await expect(page.getByLabel('筛选报告附件')).toHaveValue('')
  await expect(page.locator('.ledger-table tbody tr')).toHaveCount(3)
  await page.getByLabel('筛选报告附件').selectOption('uploaded')
  await page.getByLabel('筛选报告附件').selectOption('')
  await expect(page.locator('.ledger-table tbody tr')).toHaveCount(3)
  async function expectReportAlert(name: string, status: '未检验' | '检验', message: string) {
    const dialog = page.waitForEvent('dialog').then(async alert => {
      const text = alert.message()
      await alert.accept()
      return text
    })
    await page.getByRole('row').filter({ hasText: name }).getByRole('button', { name: status, exact: true }).click()
    expect(await dialog).toBe(message)
  }
  await expectReportAlert('未检验物料', '未检验', '该记录为未检验，无法查看检验报告')
  await page.getByRole('row').filter({ hasText: '无报告物料' }).getByRole('button', { name: '检验', exact: true }).click()
  const emptyReports = page.getByRole('dialog', { name: '检验报告附件 · 无报告物料', exact: true })
  await expect(emptyReports.getByLabel('上传报告文件', { exact: true })).toBeEnabled()
  await emptyReports.getByRole('button', { name: '关闭附件列表' }).click()

  const reportRow = page.getByRole('row').filter({ hasText: '有报告物料' })
  await reportRow.getByRole('button', { name: '检验', exact: true }).click()
  const reports = page.getByRole('dialog', { name: '检验报告附件 · 有报告物料', exact: true })
  await expect(reports.getByText('检验报告.txt', { exact: true })).toBeVisible()
  const picker = reports.getByLabel('上传报告文件', { exact: true })
  for (const name of ['补充报告.txt', '合格证.txt']) {
    await expect(picker).toBeEnabled()
    await picker.setInputFiles(reportFile(name, `报告内容：${name}`))
    await expect(reports.getByText(name, { exact: true })).toBeVisible()
  }
  const replace = reports.getByLabel('更换报告 检验报告.txt', { exact: true })
  await expect(replace).toBeEnabled()
  await replace.setInputFiles(reportFile('新版检验报告.txt', '新版报告内容：合格'))
  await expect(reports.getByText('新版检验报告.txt', { exact: true })).toBeVisible()
  await expect(reports.getByText('检验报告.txt', { exact: true })).toHaveCount(0)
  await expect(reportRow).toContainText('3份报告')
  const saved = await (await page.request.get(`/api/records/${recordId}/reports`)).json()
  expect(saved.map((attachment: { filename: string }) => attachment.filename)).toEqual(['新版检验报告.txt', '补充报告.txt', '合格证.txt'])
  expect(saved[0].id).toBe(reportId)
  await reports.getByRole('button', { name: '查看报告 新版检验报告.txt', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '新版检验报告.txt', exact: true })).toContainText('新版报告内容：合格')
  await page.getByRole('button', { name: '关闭报告预览' }).click()
  await reports.getByRole('button', { name: '关闭附件列表' }).click()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await signIn(page, reader)
  await page.getByRole('button', { name: `进入${company}` }).click()
  await expectReportAlert('无报告物料', '检验', '该记录尚未上传检验报告附件')
  await reportRow.getByRole('button', { name: '检验', exact: true }).click()
  await expect(reports.getByText('新版检验报告.txt', { exact: true })).toBeVisible()
  await expect(reports.getByLabel('上传报告文件', { exact: true })).toHaveCount(0)
  await expect(reports.getByLabel('更换报告 新版检验报告.txt', { exact: true })).toHaveCount(0)
})
