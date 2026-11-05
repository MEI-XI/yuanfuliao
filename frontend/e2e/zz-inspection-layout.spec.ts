import { expect, test, type Locator } from '@playwright/test'

const sensory = '呈均匀的白色或类白色粉末，无异味；无肉眼可见外来杂质，无受潮、结块现象。'
const packaging = '内外包装完整、清洁，无破损、渗漏及污染；标签应清晰标注产品名称、规格、生产厂家、生产日期及保质期。'
const packagingName = '包装完整性、清洁程度及产品标签标识检查'

async function expectFullText(control: Locator) {
  await expect.poll(() => control.evaluate(element => ({
    multiline: element instanceof HTMLTextAreaElement,
    fitsHeight: element.scrollHeight <= element.clientHeight + 1,
    fitsWidth: element.scrollWidth <= element.clientWidth + 1,
  }))).toEqual({ multiline: true, fitsHeight: true, fitsWidth: true })
}

test('长标准完整显示、随编辑和屏幕宽度增高，保存重开后保持内容', async ({ page }) => {
  test.setTimeout(60000)
  await page.setViewportSize({ width: 1488, height: 1056 })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  if ((await (await page.request.get('/api/setup')).json()).required) await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  const ledger = await (await page.request.post('/api/ledgers', { data: { name: `排版测试${Date.now()}` } })).json()
  const scheme = await (await page.request.post('/api/schemes', { data: {
    name: `原辅料通用检验方案（示例）${Date.now()}`,
    items: [{ name: '感官', standard: sensory }, { name: packagingName, standard: packaging }, { name: '水分', standard: '≤ 0.5%' }],
  } })).json()
  await page.reload()
  await page.getByRole('button', { name: `进入${ledger.name}`, exact: true }).click()
  await page.getByRole('button', { name: '上传与录入', exact: true }).click()
  await page.getByLabel('物料名称、型号', { exact: true }).fill('长标准示例物料')
  const photoWidth = (await page.locator('.image-panel').boundingBox())!.width
  const formWidth = (await page.locator('.form-panel').boundingBox())!.width
  await page.getByRole('radio', { name: '检验', exact: true }).check()
  await expect.poll(async () => (await page.locator('.image-panel').boundingBox())!.width).toBe(photoWidth)
  await expect.poll(async () => (await page.locator('.form-panel').boundingBox())!.width).toBe(formWidth)
  await page.getByRole('combobox', { name: '检验标准方案', exact: true }).fill(scheme.name)
  await page.getByRole('option', { name: scheme.name, exact: true }).click()
  const standards = page.getByRole('textbox', { name: '标准规定', exact: true })
  await expect(standards).toHaveCount(3)
  await expectFullText(standards.nth(1))
  const itemName = page.getByLabel('项目', { exact: true }).nth(1)
  await expectFullText(itemName)
  const longName = packagingName.repeat(3)
  await itemName.fill(longName)
  await expectFullText(itemName)
  expect((await itemName.boundingBox())!.height).toBeGreaterThan(70)
  await itemName.press('End')
  await itemName.press('Enter')
  await itemName.pressSequentially('再次检查')
  const enteredName = `${longName}\n再次检查`
  await expect(itemName).toHaveValue(enteredName)
  await expectFullText(itemName)
  const standardWidth = (await standards.first().boundingBox())!.width
  expect(standardWidth).toBeGreaterThan((await page.getByLabel('项目', { exact: true }).first().boundingBox())!.width)
  for (let index = 0; index < 3; index++) {
    await page.getByRole('combobox', { name: '检验结果', exact: true }).nth(index).fill('符合')
    await page.getByRole('combobox', { name: '判定结论', exact: true }).nth(index).fill('合格')
  }
  await standards.first().focus()
  const section = page.locator('.form-section').filter({ has: page.getByRole('heading', { name: '检验项目', exact: true }) })
  await section.evaluate(element => element.scrollIntoView({ block: 'start' }))
  await page.screenshot({ path: '../tmp/inspection-layout-desktop.png' })
  const extended = `${packaging}\n${sensory}\n${packaging}`
  const initialHeight = (await standards.nth(1).boundingBox())!.height
  await standards.nth(1).fill(extended)
  await expectFullText(standards.nth(1))
  expect((await standards.nth(1).boundingBox())!.height).toBeGreaterThan(initialHeight)
  await page.getByRole('button', { name: '保存为检验标准方案', exact: true }).click()
  const schemeDialog = page.getByRole('dialog', { name: '保存为检验标准方案', exact: true })
  await expectFullText(schemeDialog.getByLabel('项目名称', { exact: true }).nth(1))
  await expectFullText(schemeDialog.getByLabel('标准规定', { exact: true }).nth(1))
  await page.setViewportSize({ width: 390, height: 844 })
  await expectFullText(schemeDialog.getByLabel('项目名称', { exact: true }).nth(1))
  await expectFullText(schemeDialog.getByLabel('标准规定', { exact: true }).nth(1))
  await schemeDialog.getByRole('button', { name: '取消', exact: true }).click()
  await expectFullText(itemName)
  await expectFullText(standards.nth(1))
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await standards.nth(1).evaluate(element => {
    const row = element.closest('tr')!
    window.scrollBy(0, row.getBoundingClientRect().top - 150)
  })
  await page.screenshot({ path: '../tmp/inspection-layout-mobile.png' })
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  await page.getByRole('button', { name: '核对 / 编辑', exact: true }).click()
  await expect(standards.nth(1)).toHaveValue(extended)
  await expect(itemName).toHaveValue(enteredName)
  await expectFullText(standards.nth(1))
  await standards.nth(1).fill('≤ 0.5%')
  await expectFullText(standards.nth(1))
  expect((await standards.nth(1).boundingBox())!.height).toBeLessThan(initialHeight)
  await page.getByRole('button', { name: '移除检验项目 感官', exact: true }).click()
  await expect(standards).toHaveCount(2)
  await expect(standards.first()).toHaveValue('≤ 0.5%')
  await page.reload()
  await page.getByRole('button', { name: '管理与公共资料', exact: true }).click()
  await page.getByRole('button', { name: '检验标准方案', exact: true }).click()
  await page.getByRole('button', { name: '新增检验方案', exact: true }).click()
  const maintainedName = `多行维护${Date.now()}`
  await page.getByLabel('方案名称', { exact: true }).fill(maintainedName)
  await page.getByLabel('项目名称', { exact: true }).fill(enteredName)
  await page.getByLabel('标准规定', { exact: true }).fill(extended)
  await expectFullText(page.getByLabel('项目名称', { exact: true }))
  await expectFullText(page.getByLabel('标准规定', { exact: true }))
  await page.getByRole('button', { name: '保存方案', exact: true }).click()
  await page.locator('.maintenance-row').filter({ hasText: maintainedName }).getByRole('button', { name: '修改', exact: true }).click()
  await expect(page.getByLabel('项目名称', { exact: true })).toHaveValue(enteredName)
  await expect(page.getByLabel('标准规定', { exact: true })).toHaveValue(extended)
  await page.setViewportSize({ width: 1488, height: 1056 })
  await expectFullText(page.getByLabel('项目名称', { exact: true }))
  await expectFullText(page.getByLabel('标准规定', { exact: true }))
  expect(errors).toEqual([])
})
