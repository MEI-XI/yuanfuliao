import { expect, test, type Page } from '@playwright/test'

async function openAdmin(page: Page) {
  if ((await (await page.request.get('/api/setup')).json()).required) {
    await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  }
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
}

test('物料新增和编辑在各自页面打开，取消不会保存草稿', async ({ page }) => {
  await openAdmin(page)
  await expect(page.getByLabel('物料名称', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '新增物料', exact: true }).click()
  const create = page.getByRole('region', { name: '新增物料', exact: true })
  await create.getByLabel('物料名称', { exact: true }).fill('窗口测试物料')
  await create.getByRole('button', { name: '创建物料', exact: true }).click()
  await expect(create).not.toBeVisible()
  const row = page.locator('.maintenance-row').filter({ hasText: '窗口测试物料' })
  await row.getByRole('button', { name: /修改/ }).click()
  const edit = page.getByRole('region', { name: '修改物料：窗口测试物料', exact: true })
  await expect(edit.getByLabel('物料名称', { exact: true })).toHaveValue('窗口测试物料')
  await edit.getByLabel('物料名称', { exact: true }).fill('未保存的新名称')
  await edit.getByRole('button', { name: '取消返回', exact: true }).click()
  await expect(edit).not.toBeVisible()
  await expect(row).toBeVisible()
  await page.getByRole('button', { name: '新增物料', exact: true }).click()
  await expect(create.getByLabel('物料名称', { exact: true })).toHaveValue('')
  await create.getByRole('button', { name: '取消返回', exact: true }).click()
  await row.getByRole('button', { name: /修改/ }).click()
  await edit.getByLabel('型号', { exact: true }).fill('A型')
  await edit.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(edit).not.toBeVisible()
  await expect(row).toContainText('A型')
  const materials = await (await page.request.get('/api/materials')).json()
  expect(materials.filter((entry: { name: string }) => entry.name === '窗口测试物料')).toHaveLength(1)
  expect(materials.some((entry: { name: string }) => entry.name === '未保存的新名称')).toBe(false)
})

test('各小模块从自己的列表进入新增和修改页面，返回后丢弃草稿', async ({ page }) => {
  await openAdmin(page)
  const cases = [
    { tab: '检验标准方案', noun: '检验方案', label: '方案名称', name: '分页面方案', resource: 'schemes' },
    { tab: '单位资料', noun: '单位', label: '单位名称', name: '分页面单位', resource: 'partners' },
    { tab: '账号与权限', noun: '账号', label: '人员账号', name: 'form-page-user', resource: 'users' },
    { tab: '公司台账', noun: '台账', label: '台账名称', name: '分页面台账', resource: 'ledgers' },
  ]
  for (const entry of cases) {
    await page.getByRole('button', { name: entry.tab, exact: true }).click()
    await expect(page.getByLabel(entry.label, { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: `新增${entry.noun}`, exact: true }).click()
    const create = page.getByRole('region', { name: `新增${entry.noun}`, exact: true })
    await create.getByLabel(entry.label, { exact: true }).fill(entry.name)
    if (entry.resource === 'users') await create.getByLabel('初始密码').fill('browser-test-password')
    if (entry.resource === 'schemes') {
      await create.getByLabel('项目名称').fill('外观')
      await create.getByLabel('标准规定', { exact: true }).fill('无异物')
    }
    await create.getByRole('button', { name: `创建${entry.noun}`, exact: true }).click()
    await expect(create).not.toBeVisible()
    const row = page.locator('.maintenance-row').filter({ hasText: entry.name })
    await row.getByRole('button', { name: /修改/ }).click()
    const edit = page.getByRole('region', { name: `修改${entry.noun}：${entry.name}`, exact: true })
    await expect(edit.getByLabel(entry.label, { exact: true })).toHaveValue(entry.name)
    const before = await (await page.request.get(`/api/${entry.resource}`)).json()
    if (entry.resource === 'users') await edit.getByRole('combobox', { name: '角色', exact: true }).selectOption('admin')
    else await edit.getByLabel(entry.label, { exact: true }).fill('不保存的修改')
    await edit.getByRole('button', { name: '返回列表', exact: true }).click()
    expect(await (await page.request.get(`/api/${entry.resource}`)).json()).toEqual(before)
    await page.getByRole('button', { name: `新增${entry.noun}`, exact: true }).click()
    await expect(create.getByLabel(entry.label, { exact: true })).toHaveValue('')
    await create.getByRole('button', { name: '取消返回', exact: true }).click()
    await row.getByRole('button', { name: /修改/ }).click()
    await edit.getByRole('button', { name: '保存修改', exact: true }).click()
    await expect(edit).not.toBeVisible()
    await expect(row).toBeVisible()
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '公司台账', exact: true }).click()
  await page.getByRole('button', { name: '新增台账', exact: true }).click()
  await expect(page.getByRole('heading', { name: '新增台账', exact: true })).toBeInViewport()
  await expect(page.getByRole('button', { name: '创建台账', exact: true })).toBeInViewport()
  await page.screenshot({ path: '../tmp/admin-create-mobile.png', fullPage: true })
})

test('云端密钥先配置再更新，取消更新保留已有配置', async ({ page }) => {
  await openAdmin(page)
  await page.getByRole('button', { name: '云端与模板', exact: true }).click()
  if (await page.getByRole('button', { name: '更新密钥', exact: true }).isVisible()) {
    await page.getByRole('button', { name: '清除密钥', exact: true }).click()
  }
  await page.getByRole('button', { name: '配置密钥', exact: true }).click()
  const configure = page.getByRole('region', { name: '配置密钥', exact: true })
  await configure.getByLabel('API 密钥').fill('browser-test-key')
  await configure.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(configure).not.toBeVisible()
  await page.getByRole('button', { name: '更新密钥', exact: true }).click()
  const update = page.getByRole('region', { name: '更新密钥', exact: true })
  await expect(update.getByLabel('API 密钥')).toHaveValue('')
  await update.getByLabel('API 密钥').fill('unsaved-key')
  await update.getByRole('button', { name: '取消返回', exact: true }).click()
  await expect(page.getByRole('button', { name: '测试连接', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '更新密钥', exact: true }).click()
  await expect(update.getByLabel('API 密钥')).toHaveValue('')
  await update.getByLabel('API 密钥').fill('browser-test-updated-key')
  await update.getByRole('button', { name: '保存更新', exact: true }).click()
  await expect(update).not.toBeVisible()
  await page.getByRole('button', { name: '清除密钥', exact: true }).click()
  await expect(page.getByRole('button', { name: '配置密钥', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '测试连接', exact: true })).toBeDisabled()
})
