import { test, expect, type Page } from '@playwright/test'

// Only the OS chooser and browser permission prompt are replaced. Files, handles,
// IndexedDB persistence, template downloads and exports use the real browser/server.
async function installDirectoryChooser(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'showDirectoryPicker', { configurable: true, value: async (options: { startIn?: FileSystemDirectoryHandle }) => {
      sessionStorage.setItem('picker-start', options.startIn?.name || '')
      const root = await navigator.storage.getDirectory()
      return root.getDirectoryHandle(sessionStorage.getItem('picker-folder') || 'personal-templates', { create: true })
    } })
    Object.defineProperty(FileSystemHandle.prototype, 'queryPermission', { configurable: true, value: async () => sessionStorage.getItem('permission') || 'granted' })
    Object.defineProperty(FileSystemHandle.prototype, 'requestPermission', { configurable: true, value: async () => sessionStorage.getItem('permission') === 'prompt' ? 'denied' : sessionStorage.getItem('permission') || 'granted' })
  })
}

async function login(page: Page, username = 'admin') {
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
}

async function exportFromPanel(page: Page, kind: 'xlsx' | 'docx', expected: string | null) {
  await page.getByRole('button', { name: '返回公司台账', exact: true }).click()
  await page.getByRole('button', { name: '进入青山科技' }).click()
  await page.locator('input[aria-label^="选择记录"]:enabled').first().check()
  const exportRequest = page.waitForRequest(request => request.url().endsWith(`/api/exports/${kind}`))
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: kind === 'xlsx' ? '导出 Excel' : '导出 Word', exact: true }).click()
  expect((await exportRequest).postDataJSON()).toHaveProperty('template_base64', expected)
  expect(await (await download).failure()).toBeNull()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
}

test.beforeEach(async ({ page }) => { page.on('dialog', dialog => dialog.accept()) })

test('个人目录初始化后跨刷新恢复，导出逐次读取修改后的真实文件', async ({ page }) => {
  await installDirectoryChooser(page)
  await login(page)
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  const files = await page.evaluate(async () => {
    const directory = await (await navigator.storage.getDirectory()).getDirectoryHandle('personal-templates')
    return Promise.all(['查验台账.xlsx', '检验报告.docx'].map(async name => (await (await directory.getFileHandle(name)).getFile()).size))
  })
  expect(files.every(size => size > 100)).toBeTruthy()
  await exportFromPanel(page, 'xlsx', null)
  await exportFromPanel(page, 'docx', null)
  await page.reload()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await page.getByRole('button', { name: '打开模板目录选择器', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  expect(await page.evaluate(() => sessionStorage.getItem('picker-start'))).toBe('personal-templates')
  const modified = await page.evaluate(async () => {
    const directory = await (await navigator.storage.getDirectory()).getDirectoryHandle('personal-templates')
    const handle = await directory.getFileHandle('查验台账.xlsx')
    const original = await (await handle.getFile()).arrayBuffer()
    const bytes = new Uint8Array(original.byteLength + 3)
    bytes.set(new Uint8Array(original)); bytes.set([65, 66, 67], original.byteLength)
    const writer = await handle.createWritable(); await writer.write(bytes); await writer.close()
    return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''))
  })
  await exportFromPanel(page, 'xlsx', modified)
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
  await page.getByRole('button', { name: '账号与权限', exact: true }).click()
  await page.getByLabel('人员账号', { exact: true }).fill('local-template-user')
  await page.getByLabel('初始密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '保存账号', exact: true }).click()
  await expect(page.getByRole('button', { name: /local-template-user/ })).toBeVisible()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, 'local-template-user')
  await expect(page.getByRole('status')).toContainText('服务器默认模板')
  await exportFromPanel(page, 'xlsx', null)
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await exportFromPanel(page, 'xlsx', modified)
  await page.getByRole('button', { name: '使用服务器默认模板', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('服务器默认模板')
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page)
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await exportFromPanel(page, 'xlsx', modified)
})

test('既有模板不覆盖，重新选择旧目录保留原基线，删除模板后使用默认', async ({ page }) => {
  await installDirectoryChooser(page)
  await login(page)
  const custom = await page.evaluate(async () => {
    const original = await (await fetch('/api/templates/docx')).arrayBuffer()
    const bytes = new Uint8Array(original.byteLength + 3)
    bytes.set(new Uint8Array(original)); bytes.set([65, 66, 67], original.byteLength)
    const directory = await (await navigator.storage.getDirectory()).getDirectoryHandle('personal-templates', { create: true })
    const writer = await (await directory.getFileHandle('检验报告.docx', { create: true })).createWritable()
    await writer.write(bytes); await writer.close()
    return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''))
  })
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await exportFromPanel(page, 'docx', custom)
  // A newer server default must not reclassify the untouched local baseline as custom.
  await page.route('**/api/templates/xlsx', route => route.fulfill({ body: 'new server default' }))
  await page.evaluate(() => sessionStorage.setItem('picker-folder', 'another-folder'))
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('another-folder')
  await page.evaluate(() => sessionStorage.setItem('picker-folder', 'personal-templates'))
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await exportFromPanel(page, 'xlsx', null)
  await exportFromPanel(page, 'docx', custom)
  await page.evaluate(async () => {
    const directory = await (await navigator.storage.getDirectory()).getDirectoryHandle('personal-templates')
    await directory.removeEntry('检验报告.docx')
  })
  await exportFromPanel(page, 'docx', null)
  expect(await page.evaluate(async () => {
    const directory = await (await navigator.storage.getDirectory()).getDirectoryHandle('personal-templates')
    try { await directory.getFileHandle('检验报告.docx'); return false }
    catch (error) { return error instanceof DOMException && error.name === 'NotFoundError' }
  })).toBeTruthy()
  await page.getByRole('button', { name: '使用服务器默认模板', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('服务器默认模板')
  await page.reload()
  await page.getByRole('button', { name: '我的模板', exact: true }).click()
  await exportFromPanel(page, 'xlsx', null)
})

test('拒绝读取目录时阻止导出并提供重新授权入口', async ({ page }) => {
  await installDirectoryChooser(page)
  await login(page)
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await page.evaluate(() => sessionStorage.setItem('permission', 'prompt'))
  await page.getByRole('button', { name: '返回公司台账', exact: true }).click()
  await page.getByRole('button', { name: '进入青山科技' }).click()
  await page.locator('input[aria-label^="选择记录"]:enabled').first().check()
  let exported = false
  page.on('request', request => { if (request.url().endsWith('/api/exports/xlsx')) exported = true })
  await page.getByRole('button', { name: '导出 Excel', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('我的模板')
  expect(exported).toBeFalsy()
})

test('不支持目录选择的浏览器保留服务器默认导出', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'showDirectoryPicker', { value: undefined }))
  await login(page)
  await expect(page.getByRole('button', { name: '选择 / 更换模板目录', exact: true })).toBeDisabled()
  await expect(page.getByRole('status')).toContainText('服务器默认模板')
  await exportFromPanel(page, 'docx', null)
})

test('超过 10 MiB 的个人模板在浏览器中停止导出', async ({ page }) => {
  await installDirectoryChooser(page)
  await login(page)
  await page.getByRole('button', { name: '选择 / 更换模板目录', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('personal-templates')
  await page.evaluate(async () => {
    const directory = await (await navigator.storage.getDirectory()).getDirectoryHandle('personal-templates')
    const writer = await (await directory.getFileHandle('查验台账.xlsx')).createWritable()
    await writer.write(new Uint8Array(10 * 1024 * 1024 + 1)); await writer.close()
  })
  await page.getByRole('button', { name: '返回公司台账', exact: true }).click()
  await page.getByRole('button', { name: '进入青山科技' }).click()
  await page.locator('input[aria-label^="选择记录"]:enabled').first().check()
  let exported = false
  page.on('request', request => { if (request.url().endsWith('/api/exports/xlsx')) exported = true })
  await page.getByRole('button', { name: '导出 Excel', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('超过 10 MiB')
  expect(exported).toBeFalsy()
})
