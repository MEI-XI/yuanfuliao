import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, username = 'admin', password = 'browser-test-password') {
  if ((await (await page.request.get('/api/setup')).json()).required) {
    await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  }
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
}

test('超级管理员修改账号并重置和查看密码，操作可在日志中追溯', async ({ page }) => {
  await login(page)
  const created = await page.request.post('/api/users', { data: { username: 'audit-ui-user', password: 'initial-password-123', role: 'user' } })
  expect(created.ok()).toBeTruthy()
  await page.getByRole('button', { name: '账号与权限', exact: true }).click()
  // The panel loaded before this account was created; re-enter to refresh the list.
  await page.getByRole('button', { name: '返回公司台账', exact: true }).click()
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
  await page.getByRole('button', { name: '账号与权限', exact: true }).click()
  await page.locator('.maintenance-row').filter({ hasText: 'audit-ui-user' }).getByRole('button', { name: /修改/ }).click()
  const edit = page.getByRole('region', { name: '修改账号：audit-ui-user', exact: true })
  await expect(edit.getByLabel('人员账号', { exact: true })).toBeEnabled()
  await edit.getByLabel('人员账号', { exact: true }).fill('audit-ui-renamed')
  await edit.getByLabel('重置密码，留空则不修改').fill('reset-password-123')
  await edit.getByRole('button', { name: '保存修改', exact: true }).click()
  const row = page.locator('.maintenance-row').filter({ hasText: 'audit-ui-renamed' })
  await row.getByRole('button', { name: /修改/ }).click()
  await page.getByRole('button', { name: '查看密码', exact: true }).click()
  await expect(page.getByLabel('当前密码', { exact: true })).toHaveValue('reset-password-123')
  await page.getByRole('button', { name: '隐藏密码', exact: true }).click()
  await expect(page.getByLabel('当前密码', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '返回列表', exact: true }).click()
  await row.getByRole('button', { name: /修改/ }).click()
  await expect(page.getByLabel('当前密码', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '操作日志', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: '操作人', exact: true })).toBeVisible()
  await expect(page.getByRole('table')).toContainText('admin')
  await expect(page.getByRole('table')).toContainText('查看密码')
  await expect(page.getByRole('table')).not.toContainText('reset-password-123')
})

test('操作日志按页浏览历史操作并保留操作人和目标', async ({ page }) => {
  await login(page)
  for (let index = 0; index < 51; index++) {
    expect((await page.request.post('/api/materials', { data: { name: `audit-page-material-${index}` } })).ok()).toBeTruthy()
  }
  await page.getByRole('button', { name: '操作日志', exact: true }).click()
  await expect(page.getByRole('table').getByRole('row')).toHaveCount(51)
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.getByText(/第 2 页/)).toBeVisible()
  await expect(page.getByRole('table')).toContainText('admin')
  await expect(page.getByRole('table')).toContainText('/api/materials')
  await page.getByRole('button', { name: '上一页', exact: true }).click()
  await expect(page.getByText(/第 1 页/)).toBeVisible()
})

test('普通管理员看不到操作日志或超级管理员的编辑与密码入口', async ({ page }) => {
  await login(page)
  expect((await page.request.post('/api/users', { data: { username: 'audit-ui-manager', password: 'manager-password-123', role: 'admin' } })).ok()).toBeTruthy()
  await page.request.post('/api/logout')
  await login(page, 'audit-ui-manager', 'manager-password-123')
  await expect(page.getByRole('button', { name: '操作日志', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '账号与权限', exact: true }).click()
  const root = page.locator('.maintenance-row').filter({ hasText: '超级管理员' })
  if (await root.count()) await expect(root.getByRole('button', { name: /修改/ })).toBeDisabled()
  await expect(page.getByRole('button', { name: '查看密码', exact: true })).toHaveCount(0)
  await page.locator('.maintenance-row').filter({ hasText: 'audit-ui-manager' }).getByRole('button', { name: /修改/ }).click()
  await page.getByLabel('重置密码，留空则不修改').fill('manager-reset-password-123')
  await page.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.getByRole('button', { name: '登录', exact: true })).toBeVisible()
  await login(page, 'audit-ui-manager', 'manager-reset-password-123')
  await expect(page.getByRole('button', { name: '账号与权限', exact: true })).toBeVisible()
})
