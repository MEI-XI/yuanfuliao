import { test, expect } from '@playwright/test'

test('手机无需内嵌PDF阅读器即可预览待上传及已保存的多页报告', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let downloads = 0
  page.on('download', () => downloads++)
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  for (const asset of ['cmaps/Adobe-GB1-UCS2.bcmap', 'standard_fonts/LiberationSans-Regular.ttf', 'wasm/openjpeg.wasm']) {
    const resource = await page.request.get(`/pdfjs/${asset}`)
    expect(resource.ok()).toBe(true)
    expect(resource.headers()['content-type']).not.toContain('text/html')
  }
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: `手机PDF${Date.now()}` } })).json()
  await page.reload()
  await page.getByRole('button', { name: `进入${ledger.name}`, exact: true }).click()
  await page.getByRole('button', { name: '上传与录入', exact: true }).click()
  await page.getByLabel('上传报告文件', { exact: true }).setInputFiles('../tests/fixtures/report-two-pages.pdf')
  await page.getByRole('button', { name: '查看待上传报告 report-two-pages.pdf', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'report-two-pages.pdf', exact: true })
  const renderedPage = dialog.getByRole('img', { name: 'PDF 第 1 页', exact: true })
  await expect(renderedPage).toBeVisible()
  await expect.poll(() => renderedPage.evaluate(el => {
    const canvas = el as HTMLCanvasElement
    const pixels = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data
    return pixels.some((v, i) => i % 4 === 0 && v < 200 && pixels[i + 3] > 0)
  })).toBe(true)
  await dialog.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(dialog.getByRole('img', { name: 'PDF 第 2 页', exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '放大', exact: true }).click()
  await expect(dialog.getByText('125%', { exact: true })).toBeVisible()
  await dialog.screenshot({ path: '../tmp/mobile-report-pdf.png' })
  await page.getByRole('button', { name: '关闭报告预览', exact: true }).click()
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  await page.getByRole('button', { name: '核对 / 编辑', exact: true }).click()
  await page.getByRole('button', { name: '查看报告 report-two-pages.pdf', exact: true }).click()
  await expect(renderedPage).toBeVisible()
  expect(downloads).toBe(0)
})

