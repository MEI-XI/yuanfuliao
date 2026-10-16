import { test, expect } from '@playwright/test'
import path from 'node:path'
import { readFile } from 'node:fs/promises'

for (const mode of ['单条', '批量', '失败重试', '批量失败重试', '批量无效附件', '失败重试已保存合并']) test(`新增记录可先选报告附件，保存并核对后可查看附件 ${mode}`, async ({ page }) => {
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const name = `新增附件-${Date.now()}`
  const ledger = await (await page.request.post('/api/ledgers', { data: { name } })).json()
  await page.reload()
  await page.getByRole('button', { name: `进入${name}` }).click()
  await page.getByRole('button', { name: '上传与录入', exact: true }).click()
  if (mode === '失败重试已保存合并') {
    await page.getByRole('button', { name: '多种物料批量', exact: true }).click()
    await page.getByLabel('选择包装照片').setInputFiles(['../tests/fixtures/label.png', '../tests/fixtures/label.png'])
    await page.getByRole('button', { name: '记录 1 · 1 张', exact: true }).click()
  }
  await expect(page.getByLabel('上传报告文件', { exact: true })).toHaveCount(1)
  await page.getByLabel('上传报告文件', { exact: true }).setInputFiles({ name: '新增报告.png', mimeType: 'image/png', buffer: mode === '批量无效附件' ? Buffer.from('invalid image') : await readFile(path.resolve('../tests/fixtures/label.png')) })
  await expect(page.getByText('新增报告.png', { exact: true })).toBeVisible()
  if (mode === '单条') {
    await page.getByRole('button', { name: '查看待上传报告 新增报告.png', exact: true }).click()
    await expect(page.getByRole('dialog').getByAltText('新增报告.png')).toBeVisible()
    await page.getByRole('button', { name: '关闭报告预览', exact: true }).click()
    await page.getByLabel('上传报告文件', { exact: true }).setInputFiles({ name: '未保存报告.txt', mimeType: 'text/plain', buffer: Buffer.from('待保存报告的中文内容') })
    await page.getByRole('button', { name: '查看待上传报告 未保存报告.txt', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('待保存报告的中文内容')
    await page.getByRole('button', { name: '关闭报告预览', exact: true }).click()
    await page.getByRole('button', { name: '移除待上传报告 未保存报告.txt', exact: true }).click()
  }
  expect(await (await page.request.get(`/api/ledgers/${ledger.id}/records`)).json()).toHaveLength(0)
  if (mode.includes('失败重试')) {
    let rejected = false
    await page.route('**/api/records/*/reports', async route => {
      if (route.request().method() === 'POST' && !rejected) { rejected = true; await route.fulfill({ status: 503, json: { detail: '模拟上传失败' } }) }
      else await route.continue()
    })
  }
  if (mode.includes('批量')) {
    await page.getByRole('button', { name: '多种物料批量', exact: true }).click()
    await page.getByRole('button', { name: '全选分组', exact: true }).click()
    await page.getByLabel('同时标记为已核对', { exact: true }).check()
    await page.getByRole('button', { name: '保存所选 1 条记录', exact: true }).click()
  } else await page.getByRole('button', { name: '保存并标记已核对', exact: true }).click()
  if (mode.includes('失败重试')) {
    await expect(page.getByText(/记录已保存，报告.*上传未完成/)).toBeVisible()
    const partial = await (await page.request.get(`/api/ledgers/${ledger.id}/records`)).json()
    expect(partial).toHaveLength(1)
    expect(partial[0].status).toBe('pending')
    if (mode === '失败重试已保存合并') {
      const handle = page.getByRole('button', { name: '拖动记录 1 排序', exact: true })
      await handle.press('m'); await handle.press('Enter')
      await expect(page.getByRole('alert')).toContainText('这组记录已保存，请先完成附件上传；已保存记录不能合并。')
      await expect(page.getByRole('button', { name: '记录 1 · 1 张', exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: '记录 2 · 1 张', exact: true })).toBeVisible()
      return
    }
    await page.getByRole('button', { name: mode.includes('批量') ? '重试批量保存' : '保存并标记已核对', exact: true }).click()
  }
  if (mode === '批量无效附件') {
    await expect(page.getByText(/记录已保存，报告.*上传未完成/)).toBeVisible()
    await page.getByRole('button', { name: '移除待上传报告 新增报告.png', exact: true }).click()
    await page.getByRole('button', { name: '重试批量保存', exact: true }).click()
  }
  await expect(page.getByRole('button', { name: '上传与录入', exact: true })).toBeVisible()
  const records = await (await page.request.get(`/api/ledgers/${ledger.id}/records`)).json()
  expect(records).toHaveLength(1)
  expect(records[0].status).toBe('checked')
  const reports = await (await page.request.get(`/api/records/${records[0].id}/reports`)).json()
  expect(reports.map((entry: {filename:string}) => entry.filename)).toEqual(mode === '批量无效附件' ? [] : ['新增报告.png'])
  if (mode === '批量无效附件') return
  await page.getByRole('button', { name: '核对 / 编辑', exact: true }).click()
  await page.getByRole('button', { name: '查看报告 新增报告.png', exact: true }).click()
  await expect(page.getByRole('dialog').getByAltText('新增报告.png')).toBeVisible()
})

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
