import { test, expect, type Page } from '@playwright/test'

async function openBatch(page: Page) {
  page.on('dialog', dialog => dialog.accept())
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '进入青山科技' }).click()
  await page.getByRole('button', { name: '上传与录入' }).click()
  await page.getByRole('button', { name: '多种物料批量', exact: true }).click()
  await page.getByLabel('选择包装照片').setInputFiles(Array(3).fill('../tests/fixtures/label.png'))
  await expect(page.getByRole('button', { name: '记录 3 · 1 张', exact: true })).toBeVisible()
  const images: string[] = []
  for (const [index, name] of ['排序甲', '排序乙', '排序丙'].entries()) {
    await page.getByRole('button', { name: `记录 ${index + 1} · 1 张`, exact: true }).click()
    await page.getByLabel('物料名称、型号', { exact: true }).fill(name)
    images.push(await page.getByAltText('当前包装原图', { exact: true }).getAttribute('src') || '')
  }
  return images
}

async function expectGroupsBesidePhoto(page: Page, mobile = false) {
  const rail = await page.getByRole('region', { name: '批量记录排序' }).boundingBox()
  const photo = await page.locator('.photo-viewer').boundingBox()
  if (!rail || !photo) throw new Error('分组栏或图片未显示')
  expect(rail.x + rail.width).toBeLessThanOrEqual(photo.x)
  expect(rail.y).toBeLessThan(photo.y + photo.height)
  expect(rail.y + rail.height).toBeGreaterThan(photo.y)
  expect(rail.width).toBeLessThanOrEqual(mobile ? 120 : 210)
  expect(photo.width).toBeGreaterThan(rail.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.locator('.photo-workspace').screenshot({ path: `../tmp/group-rail-${mobile ? 'mobile' : 'desktop'}.png` })
}

test('分组紧凑排列在图片左侧，子图片可切换到所属记录和指定图片', async ({ page }) => {
  const images = await openBatch(page)
  await expectGroupsBesidePhoto(page)
  const list = page.getByRole('list', { name: '图片分组' })
  await list.getByRole('listitem').nth(1).getByRole('button', { name: '合并到上一组' }).click()
  await page.getByRole('button', { name: '记录 2 · 1 张', exact: true }).click()
  await page.getByRole('button', { name: '预览记录 1 的图片 2', exact: true }).click()
  await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 2 张')
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序甲')
  await expect(page.getByAltText('当前包装原图', { exact: true })).toHaveAttribute('src', images[1]!)
  await expect(page.getByRole('button', { name: '预览记录 1 的图片 2', exact: true })).toHaveAttribute('aria-pressed', 'true')
})

test('桌面纵向拖动分组后保留当前记录、填写内容和图片对应关系', async ({ page }) => {
  const images = await openBatch(page)
  const list = page.getByRole('list', { name: '图片分组' })
  await page.getByRole('button', { name: '记录 2 · 1 张', exact: true }).click()
  await list.scrollIntoViewIfNeeded()
  const first = await list.getByRole('listitem').nth(0).boundingBox()
  const last = await list.getByRole('listitem').nth(2).boundingBox()
  expect(first).not.toBeNull()
  expect(last).not.toBeNull()
  if (!first || !last) throw new Error('分组行未显示')
  expect(last.y).toBeGreaterThan(first.y + first.height)
  const handle = await page.getByRole('button', { name: '拖动记录 1 排序', exact: true }).boundingBox()
  if (!handle) throw new Error('排序手柄未显示')
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(handle.x + handle.width / 2, last.y + last.height - 4, { steps: 12 })
  await page.mouse.up()
  await expect(list.locator('.group-name')).toHaveText(['排序乙', '排序丙', '排序甲'])
  await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 1 张')
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序乙')
  await expect(page.getByAltText('当前包装原图', { exact: true })).toHaveAttribute('src', images[1]!)
  await page.getByRole('button', { name: '记录 3 · 1 张', exact: true }).click()
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序甲')
  await expect(page.getByAltText('当前包装原图', { exact: true })).toHaveAttribute('src', images[0]!)
  await page.getByRole('button', { name: '拖动记录 3 排序', exact: true }).press('ArrowUp')
  await expect(list.locator('.group-name')).toHaveText(['排序乙', '排序甲', '排序丙'])
  await expect(page.getByLabel('当前图片分组')).toHaveText('记录 2 · 1 张')
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序甲')
})

test.describe('手机触摸排序', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

  test('手机分组和子图片保持在预览左侧并可点选', async ({ page }) => {
    const images = await openBatch(page)
    await expectGroupsBesidePhoto(page, true)
    await page.getByRole('button', { name: '预览记录 1 的图片 1', exact: true }).click()
    await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序甲')
    await expect(page.getByAltText('当前包装原图', { exact: true })).toHaveAttribute('src', images[0]!)
  })

  test('触摸手柄把末组移到首组，记录内容随分组移动且可继续合并', async ({ page, context }) => {
    const images = await openBatch(page)
    const list = page.getByRole('list', { name: '图片分组' })
    await list.scrollIntoViewIfNeeded()
    const first = await list.getByRole('listitem').first().boundingBox()
    const handle = await page.getByRole('button', { name: '拖动记录 3 排序', exact: true }).boundingBox()
    if (!first || !handle) throw new Error('手机分组或手柄未显示')
    const x = handle.x + handle.width / 2
    const startY = handle.y + handle.height / 2
    const endY = first.y + 4
    const session = await context.newCDPSession(page)
    await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: startY }] })
    for (let step = 1; step <= 12; step++) {
      await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: startY + (endY - startY) * step / 12 }] })
    }
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await session.detach()
    await expect(list.locator('.group-name')).toHaveText(['排序丙', '排序甲', '排序乙'])
    await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 1 张')
    await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序丙')
    await expect(page.getByAltText('当前包装原图', { exact: true })).toHaveAttribute('src', images[2]!)
    await list.getByRole('listitem').nth(1).getByRole('button', { name: '合并到上一组' }).click()
    await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 2 张')
    await expect(page.getByAltText('包装图片缩略图')).toHaveCount(2)
  })
})
