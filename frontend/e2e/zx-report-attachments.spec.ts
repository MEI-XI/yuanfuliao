import { test, expect } from '@playwright/test'
import path from 'node:path'
import { readFile } from 'node:fs/promises'

test('上传报告后可查看，未保存的表单内容保留，删除报告更新版本', async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) {
    await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  }
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const name = `报告附件-${Date.now()}`
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name } })).json()
  await page.request.post(`/api/ledgers/${ledger.id}/records`, { data: { fields: { material_name: name } } })
  await page.reload()
  await page.getByRole('button', { name: `进入${name}` }).click()
  const row = page.getByRole('row').filter({ hasText: name })
  await row.getByRole('button', { name: '核对 / 编辑' }).click()
  await page.getByLabel('备注', { exact: true }).fill('尚未保存的备注保留')
  await page.getByLabel('上传报告文件', { exact: true }).setInputFiles({
    name: '供应商报告.png', mimeType: 'image/png', buffer: await readFile(path.resolve('../tests/fixtures/label.png')),
  })
  const reports = page.getByRole('region', { name: '报告附件', exact: true })
  await expect(reports.getByText('供应商报告.png', { exact: true })).toBeVisible()
  await expect(page.getByLabel('备注', { exact: true })).toHaveValue('尚未保存的备注保留')
  await reports.getByRole('button', { name: '查看报告 供应商报告.png', exact: true }).click()
  await expect(page.getByRole('dialog').getByAltText('供应商报告.png')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '关闭报告预览', exact: true }).click()
  page.once('dialog', dialog => dialog.accept())
  await reports.getByRole('button', { name: '删除报告 供应商报告.png', exact: true }).click()
  await expect(reports.getByText('暂无报告附件', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '核对 / 编辑' }).click()
  await expect(page.getByLabel('备注', { exact: true })).toHaveValue('尚未保存的备注保留')
})
