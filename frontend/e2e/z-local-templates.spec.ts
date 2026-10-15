import { test, expect, type Page } from '@playwright/test'
import { networkInterfaces } from 'node:os'

async function login(page: Page, username = 'admin') {
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
}

function templateRow(page: Page, kind: 'xlsx' | 'docx') {
  return page.getByRole('region', { name: kind === 'xlsx' ? 'Excel 查验台账模板' : 'Word 检验报告模板' })
}

async function exportFromPanel(page: Page, kind: 'xlsx' | 'docx', expected: string | null) {
  await page.getByRole('button', { name: '返回公司台账', exact: true }).click()
  await page.getByRole('button', { name: '进入青山科技' }).click()
  await page.getByRole('button', { name: '清空选择', exact: true }).click()
  const rows = page.getByRole('row').filter({ has: page.locator('input[aria-label^="选择记录"]:enabled') })
  const eligible = kind === 'docx' ? rows.filter({ has: page.getByText('检验', { exact: true }) }) : rows
  await eligible.first().getByRole('checkbox').check()
  const exportRequest = page.waitForRequest(request => request.url().endsWith(`/api/exports/${kind}`))
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: kind === 'xlsx' ? '导出 Excel' : '导出 Word', exact: true }).click()
  expect((await exportRequest).postDataJSON()).toHaveProperty('template_base64', expected)
  expect(await (await download).failure()).toBeNull()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
}

test.beforeAll(async ({ request }) => {
  if ((await (await request.get('/api/setup')).json()).required) {
    await request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  }
  await request.post('/api/login', { data: { username: 'admin', password: 'browser-test-password' } })
  const ledgers = await (await request.get('/api/ledgers')).json()
  const ledger = ledgers.find((entry: { name: string }) => entry.name === '青山科技') || await (await request.post('/api/ledgers', { data: { name: '青山科技' } })).json()
  const response = await request.post(`/api/ledgers/${ledger.id}/records`, {
    data: { inspection_enabled: true, fields: { material_name: '模板导出检验样本' } },
  })
  expect(response.status()).toBe(201)
  const record = await response.json()
  expect((await request.post(`/api/records/${record.id}/check`, { data: { version: record.version } })).status()).toBe(200)
})

test.beforeEach(async ({ page }) => { page.on('dialog', dialog => dialog.accept()) })

test('任意文件名分别选择 Word 和 Excel，刷新保留并逐项恢复默认', async ({ page }, testInfo) => {
  await login(page)
  const word = await (await page.request.get('/api/templates/docx')).body()
  const excel = await (await page.request.get('/api/templates/xlsx')).body()
  await expect(page.locator('input[webkitdirectory]')).toHaveCount(0)
  await templateRow(page, 'docx').getByLabel('选择 Word 模板文件').setInputFiles({ name: '我的检验格式.docx', mimeType: 'application/octet-stream', buffer: word })
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('我的检验格式.docx')
  await templateRow(page, 'xlsx').getByLabel('选择 Excel 模板文件').setInputFiles({ name: '供应商查验表.xlsx', mimeType: 'application/octet-stream', buffer: excel })
  await expect(templateRow(page, 'xlsx').getByRole('status')).toContainText('供应商查验表.xlsx')
  await page.screenshot({ path: testInfo.outputPath('template-panel.png'), fullPage: true })
  await exportFromPanel(page, 'docx', word.toString('base64'))
  await exportFromPanel(page, 'xlsx', excel.toString('base64'))
  await page.reload()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('我的检验格式.docx')
  await templateRow(page, 'docx').getByRole('button', { name: '恢复默认 Word 模板' }).click()
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('服务器默认模板')
  await expect(templateRow(page, 'xlsx').getByRole('status')).toContainText('供应商查验表.xlsx')
  await exportFromPanel(page, 'docx', null)
  await exportFromPanel(page, 'xlsx', excel.toString('base64'))
})

test('无效文件、取消选择和转换失败保留原模板，账号之间分别保存', async ({ page }) => {
  await login(page)
  const word = await (await page.request.get('/api/templates/docx')).body()
  const input = templateRow(page, 'docx').getByLabel('选择 Word 模板文件')
  await input.setInputFiles({ name: '保留此模板.docx', mimeType: 'application/octet-stream', buffer: word })
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('保留此模板.docx')
  await input.dispatchEvent('cancel')
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('保留此模板.docx')
  await input.setInputFiles({ name: '说明.txt', mimeType: 'text/plain', buffer: Buffer.from('not a template') })
  await expect(page.getByRole('alert')).toContainText('支持的 Word')
  await input.setInputFiles({ name: '超大文件.docx', mimeType: 'application/octet-stream', buffer: Buffer.alloc(10 * 1024 * 1024 + 1) })
  await expect(page.getByRole('alert')).toContainText('超过 10 MiB')
  await input.setInputFiles({ name: '损坏文件.docx', mimeType: 'application/octet-stream', buffer: Buffer.from('broken') })
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('保留此模板.docx')
  await exportFromPanel(page, 'docx', word.toString('base64'))
  const username = `file-template-${Date.now()}`
  expect((await page.request.post('/api/users', { data: { username, password: 'browser-test-password' } })).status()).toBe(201)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, username)
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('服务器默认模板')
  await exportFromPanel(page, 'docx', null)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page)
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('保留此模板.docx')
})

test('旧版 Word 和 Excel 文件通过转换接口保存，保留原文件名', async ({ page }) => {
  await login(page)
  // The UI seam uses normalized bytes; actual legacy conversion is covered by server tests.
  for (const kind of ['docx', 'xlsx'] satisfies ('docx' | 'xlsx')[]) {
    const normalized = await (await page.request.get(`/api/templates/${kind}`)).body()
    let uploaded = false
    await page.route(`**/api/templates/convert/${kind}`, async route => {
      expect(route.request().headers()['content-type']).toContain('multipart/form-data')
      expect(route.request().postDataBuffer()?.toString()).toContain('filename="')
      uploaded = true
      await route.fulfill({ body: normalized, contentType: 'application/octet-stream' })
    })
    const name = kind === 'docx' ? '旧版报告.doc' : '旧版台账.xls'
    await templateRow(page, kind).locator('input[type=file]').setInputFiles({ name, mimeType: 'application/octet-stream', buffer: Buffer.from('legacy-format-fixture') })
    await expect(templateRow(page, kind).getByRole('status')).toContainText(name)
    expect(uploaded).toBeTruthy()
    await exportFromPanel(page, kind, normalized.toString('base64'))
  }
})

test('真实局域网 HTTP 选择个人文件并导出，可下载默认模板', async ({ browser }) => {
  const address = Object.values(networkInterfaces()).flat().find(entry => entry?.family === 'IPv4' && !entry.internal)?.address
  test.skip(!address, '需要本机局域网 IPv4 地址')
  const context = await browser.newContext({ baseURL: `http://${address}:4173` })
  const page = await context.newPage()
  try {
    await login(page)
    expect(await page.evaluate(() => window.isSecureContext)).toBeFalsy()
    const bytes = await (await page.request.get('/api/templates/docx')).body()
    await templateRow(page, 'docx').locator('input[type=file]').setInputFiles({ name: '局域网报告.docx', mimeType: 'application/octet-stream', buffer: bytes })
    await expect(templateRow(page, 'docx').getByRole('status')).toContainText('局域网报告.docx')
    await exportFromPanel(page, 'docx', bytes.toString('base64'))
    const download = page.waitForEvent('download')
    await templateRow(page, 'docx').getByRole('button', { name: '下载默认 Word 模板' }).click()
    expect((await download).suggestedFilename()).toBe('检验报告.docx')
  } finally { await context.close() }
})

test('保留旧版个人副本，并让未改动的旧默认模板继续使用服务器默认', async ({ page }) => {
  await login(page)
  const word = await (await page.request.get('/api/templates/docx')).body()
  const excel = await (await page.request.get('/api/templates/xlsx')).body()
  const user = await (await page.request.get('/api/me')).json()
  await page.evaluate(async ({ userId, docx, xlsx }) => {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('personal-local-templates', 1)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction('users', 'readwrite')
      transaction.objectStore('users').put({ activeId: null, folders: [], activeSnapshot: true, snapshot: { name: '旧模板目录', files: { docx: { base64: docx, baseline: 'previous-default' }, xlsx: { base64: xlsx, baseline: xlsx } } } }, userId)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error)
    })
    database.close()
  }, { userId: user.id, docx: word.toString('base64'), xlsx: excel.toString('base64') })
  await page.reload()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
  await expect(templateRow(page, 'docx').getByRole('status')).toContainText('个人模板')
  await expect(templateRow(page, 'xlsx').getByRole('status')).toContainText('服务器默认模板')
  await exportFromPanel(page, 'docx', word.toString('base64'))
  await exportFromPanel(page, 'xlsx', null)
})
