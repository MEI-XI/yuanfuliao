import { expect, test } from '@playwright/test'

test('搜索未填写物料匹配空名称和纯空格，并保留其他筛选条件', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: `空物料筛选${Date.now()}` } })).json()
  for (const [name, inspected] of [['', false], ['   ', true], ['甘氨酸', false]] as const) {
    const response = await page.request.post(`/api/ledgers/${ledger.id}/records`, { data: { fields: { material_name: name }, inspection_enabled: inspected } })
    expect(response.ok()).toBeTruthy()
  }
  await page.reload()
  await page.getByRole('button', { name: `进入${ledger.name}`, exact: true }).click()
  const rows = page.locator('.ledger-table tbody tr')
  await expect(rows).toHaveCount(3)
  await page.getByLabel('查找记录', { exact: true }).fill('未填写物料')
  await expect(rows).toHaveCount(2)
  await page.getByLabel('筛选检验状态', { exact: true }).selectOption('inspected')
  await expect(rows).toHaveCount(1)
  await page.getByLabel('筛选检验状态', { exact: true }).selectOption('')
  await page.getByLabel('查找记录', { exact: true }).fill('甘氨酸')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('甘氨酸')
})
