import { expect, test } from '@playwright/test'

test('多个单位及地址完整显示，选择只填地址且重识别保留人工选择', async ({ page }) => {
  await page.request.post('/api/setup', { data: { username: 'admin', password: 'browser-test-password' } })
  await page.goto('/')
  await page.getByLabel('账号', { exact: true }).fill('admin')
  await page.getByLabel('密码', { exact: true }).fill('browser-test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出', exact: true })).toBeVisible()
  await page.request.post('/api/ledgers', { data: { name: '多单位候选台账' } })
  await page.reload()
  await page.getByRole('button', { name: '进入多单位候选台账' }).click()
  await page.getByRole('button', { name: '上传与录入' }).click()
  await page.getByLabel('选择包装照片').setInputFiles('../tests/fixtures/label.png')
  const companies = [{ value: '甲贸易公司', source: 'supplier' }, { value: '乙食品公司', source: 'manufacturer' }]
  const addresses = [{ value: '上海市甲路1号', source: 'supplier' }, { value: '河北省乙路2号', source: 'manufacturer' }, { value: '河北省丙路3号', source: 'manufacturer' }]
  await page.route('**/api/recognition/*', async route => {
    const response = await route.fetch()
    const job = await response.json()
    await route.fulfill({ response, json: { ...job, local_status: 'done', cloud_status: 'done',
      fields: { material_name: '甘氨酸', company_name: companies[0].value, address: addresses[0].value }, cloud_fields: {},
      conflicts: { company_name: companies.map(item => item.value), address: addresses.map(item => item.value) },
      party_options: { company_name: companies, address: addresses },
      review_suggestions: { conflicts: {}, fields: { company_name: '旧历史公司', address: '旧历史地址' }, sources: [{ record_id: 91, version: 2, ledger_name: '旧公司', checked_at: '2026-10-01T00:00:00Z' }],
        inspection: { source_record_id: 91, scheme_name: '', items: [], report: {} } },
    } })
  })
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  const companyChoices = page.getByRole('group', { name: '供应商或生产商识别建议', exact: true })
  const addressChoices = page.getByRole('group', { name: '地址识别建议', exact: true })
  await expect(companyChoices.getByRole('button', { name: '填入：供应商：甲贸易公司', exact: true })).toBeVisible()
  await expect(page.getByLabel('供应商或生产商', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('地址', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('地址来源', { exact: true })).toHaveValue('')
  await page.getByLabel('地址来源', { exact: true }).selectOption('supplier')
  for (const address of addresses) await expect(addressChoices).toContainText(address.value)
  await companyChoices.getByRole('button', { name: '填入：生产商：乙食品公司', exact: true }).click()
  await addressChoices.getByRole('button', { name: '填入：生产商：河北省乙路2号', exact: true }).click()
  await expect(page.getByLabel('地址来源', { exact: true })).toHaveValue('supplier')
  await expect(addressChoices).toContainText('河北省乙路2号')
  await page.getByRole('button', { name: '开始识别', exact: true }).click()
  await expect(page.getByRole('button', { name: '开始识别', exact: true })).toBeEnabled()
  await expect(page.getByLabel('供应商或生产商', { exact: true })).toHaveValue('乙食品公司')
  await expect(page.getByLabel('地址', { exact: true })).toHaveValue('河北省乙路2号')
  await page.setViewportSize({ width: 390, height: 844 })
  await addressChoices.scrollIntoViewIfNeeded()
  await page.screenshot({ path: '../tmp/party-options-mobile.png' })
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  await expect(page.getByRole('table')).toContainText('乙食品公司')
})
