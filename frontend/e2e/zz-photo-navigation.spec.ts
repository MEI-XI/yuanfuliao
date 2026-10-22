import { expect, test } from '@playwright/test'

test('包装原图按当前记录图片顺序切换，首尾按钮禁用', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const name = `图片切换${Date.now()}`
  await page.request.post('/api/ledgers', { data: { name } })
  await page.reload()
  await page.getByRole('button', { name: `进入${name}` }).click()
  await page.getByRole('button', { name: '上传与录入' }).click()
  await page.getByLabel('选择包装照片').setInputFiles(Array(3).fill('../tests/fixtures/label.png'))
  await expect(page.locator('.thumbnail')).toHaveCount(3)
  const images = await page.locator('.thumbnail img').evaluateAll(elements => elements.map(element => element.getAttribute('src')))
  await page.getByRole('button', { name: '放大原图' }).click()
  const dialog = page.getByRole('dialog', { name: '包装原图', exact: true })
  await expect(dialog.getByRole('button', { name: '上一张' })).toBeDisabled()
  await expect(dialog.getByText('1 / 3', { exact: true })).toBeVisible()
  for (const index of [1, 2]) {
    await dialog.getByRole('button', { name: '下一张' }).click()
    await expect(dialog.getByAltText('包装图片放大预览')).toHaveAttribute('src', images[index] || '')
  }
  await expect(dialog.getByRole('button', { name: '下一张' })).toBeDisabled()
  await dialog.getByRole('button', { name: '上一张' }).click()
  await expect(dialog.getByAltText('包装图片放大预览')).toHaveAttribute('src', images[1] || '')
  await expect(dialog.getByText('2 / 3', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(dialog.getByRole('button', { name: '上一张' })).toBeInViewport()
  await expect(dialog.getByRole('button', { name: '下一张' })).toBeInViewport()
  await page.screenshot({ path: '../tmp/photo-navigation-mobile.png' })
})
