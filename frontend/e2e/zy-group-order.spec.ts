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

async function mergeByMouse(page: Page, from: number, to: number) {
  const list = page.getByRole('list', { name: '图片分组' })
  await list.scrollIntoViewIfNeeded()
  const handle = await page.getByRole('button', { name: `拖动记录 ${from} 排序`, exact: true }).boundingBox()
  const target = await list.getByRole('listitem').nth(to - 1).boundingBox()
  if (!handle || !target) throw new Error('分组或手柄未显示')
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 12 })
  await expect(list.getByRole('listitem').nth(to - 1)).toHaveClass(/merge-target/)
  await page.mouse.up()
}

test('分组紧凑排列在图片左侧，子图片可切换到所属记录和指定图片', async ({ page }) => {
  const images = await openBatch(page)
  await expectGroupsBesidePhoto(page)
  const list = page.getByRole('list', { name: '图片分组' })
  await mergeByMouse(page, 2, 1)
  await page.getByRole('button', { name: '记录 2 · 1 张', exact: true }).click()
  await page.getByRole('button', { name: '预览记录 1 的图片 2', exact: true }).click()
  await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 2 张')
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序甲')
  await expect(page.getByAltText('当前包装原图', { exact: true })).toHaveAttribute('src', images[1]!)
  await expect(page.getByRole('button', { name: '预览记录 1 的图片 2', exact: true })).toHaveAttribute('aria-pressed', 'true')
})

test('拖到非相邻分组中心合并，保留目标字段和全部图片', async ({ page }) => {
  await openBatch(page)
  await mergeByMouse(page, 1, 3)
  const list = page.getByRole('list', { name: '图片分组' })
  await expect(list.getByRole('listitem')).toHaveCount(2)
  await expect(list.locator('.group-name')).toHaveText(['排序乙', '排序丙'])
  await expect(page.getByLabel('当前图片分组')).toHaveText('记录 2 · 2 张')
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序丙')
})

test('拖出分组列表后松手不排序也不合并', async ({ page }) => {
  await openBatch(page)
  const handle = await page.getByRole('button', { name: '拖动记录 1 排序', exact: true }).boundingBox()
  const list = page.getByRole('list', { name: '图片分组' })
  const last = await list.getByRole('listitem').last().boundingBox()
  if (!handle || !last) throw new Error('分组或手柄未显示')
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(last.x + last.width + 50, last.y + last.height / 2, { steps: 12 })
  await page.mouse.up()
  await expect(list.locator('.group-name')).toHaveText(['排序甲', '排序乙', '排序丙'])
})

test('键盘选择任意合并目标并可取消', async ({ page }) => {
  await openBatch(page)
  const handle = page.getByRole('button', { name: '拖动记录 1 排序', exact: true })
  const list = page.getByRole('list', { name: '图片分组' })
  await handle.press('m')
  await handle.press('ArrowDown')
  await expect(list.getByRole('listitem').nth(2)).toHaveClass(/merge-target/)
  await handle.press('Escape')
  await expect(list.getByRole('listitem')).toHaveCount(3)
  await handle.press('m')
  await handle.press('ArrowDown')
  await handle.press('Enter')
  await expect(list.locator('.group-name')).toHaveText(['排序乙', '排序丙'])
})

test('勾选记录不会切换正在编辑的分组', async ({ page }) => {
  await openBatch(page)
  const checkbox = page.getByRole('checkbox', { name: '选择分组 1', exact: true })
  await checkbox.setChecked(true)
  await expect(checkbox).toBeChecked()
  await expect(page.getByLabel('当前图片分组')).toHaveText('记录 3 · 1 张')
  await expect(page.getByLabel('物料名称、型号', { exact: true })).toHaveValue('排序丙')
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

  test('触摸拖到非相邻目标中心合并，离开列表取消', async ({ page, context }) => {
    await openBatch(page)
    const list = page.getByRole('list', { name: '图片分组' })
    await list.scrollIntoViewIfNeeded()
    const handle = await page.getByRole('button', { name: '拖动记录 3 排序', exact: true }).boundingBox()
    const first = await list.getByRole('listitem').first().boundingBox()
    if (!handle || !first) throw new Error('分组或手柄未显示')
    const session = await context.newCDPSession(page)
    const x = handle.x + handle.width / 2
    const startY = handle.y + handle.height / 2
    const endY = first.y + first.height / 2
    for (const outside of [true, false]) {
      await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: startY }] })
      const endX = first.x + (outside ? first.width + 50 : first.width / 2)
      for (let step = 1; step <= 12; step++) {
        await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + (endX - x) * step / 12, y: startY + (endY - startY) * step / 12 }] })
      }
      await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
      await expect(list.getByRole('listitem')).toHaveCount(outside ? 3 : 2)
    }
    await session.detach()
    await expect(list.locator('.group-name')).toHaveText(['排序甲', '排序乙'])
    await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 2 张')
  })

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
    await mergeByMouse(page, 2, 1)
    await expect(page.getByLabel('当前图片分组')).toHaveText('记录 1 · 2 张')
    await expect(page.getByAltText('包装图片缩略图')).toHaveCount(2)
  })
})
