import { expect, test } from '@playwright/test'

test('有记录台账只提醒禁止删除，空台账才确认删除', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const occupied = await (await page.request.post('/api/ledgers', { data: { name: `有记录${Date.now()}` } })).json()
  const empty = await (await page.request.post('/api/ledgers', { data: { name: `空台账${Date.now()}` } })).json()
  const record = await (await page.request.post(`/api/ledgers/${occupied.id}/records`, { data: {} })).json()
  await page.request.post(`/api/records/${record.id}/void`, { data: { version: record.version } })
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
  await page.getByRole('button', { name: '公司台账', exact: true }).click()
  const blockedDialog = page.waitForEvent('dialog').then(async dialog => {
    const result = { type: dialog.type(), message: dialog.message() }
    await dialog.dismiss()
    return result
  })
  await page.locator('.maintenance-row').filter({ hasText: occupied.name }).getByRole('button', { name: '删除', exact: true }).click()
  const blocked = await blockedDialog
  expect(blocked.type).toBe('alert')
  expect(blocked.message).toContain('不能删除')
  expect(blocked.message).not.toContain('确定删除')
  await expect(page.locator('.maintenance-row').filter({ hasText: occupied.name })).toBeVisible()
  for (const accept of [false, true]) {
    const confirmation = page.waitForEvent('dialog').then(async dialog => {
      const type = dialog.type()
      if (accept) await dialog.accept(); else await dialog.dismiss()
      return type
    })
    await page.locator('.maintenance-row').filter({ hasText: empty.name }).getByRole('button', { name: '删除', exact: true }).click()
    expect(await confirmation).toBe('confirm')
    await expect(page.locator('.maintenance-row').filter({ hasText: empty.name })).toHaveCount(accept ? 0 : 1)
  }
})
