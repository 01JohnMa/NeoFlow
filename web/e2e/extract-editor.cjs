/* Standalone browser regression. Run with the documented pinned Playwright profile. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const base = process.env.EDITOR_TEST_URL || 'http://127.0.0.1:4173'
const row = (page, path) => page.locator(`tr[data-field-path="${path}"]`)
const top = (key) => `/properties/${key}`
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function main() {
  const browser = await chromium.launch({ headless: true })
  let passed = 0
  async function scenario(name, fn, suffix = '') {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    page.setDefaultTimeout(10000)
    const requests = []
    const runtimeErrors = []
    let rejectNext = false
    page.on('pageerror', (e) => runtimeErrors.push(String(e)))
    // Never contact a real API, auth provider, database or model from this fixture.
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== new URL(base).origin) return route.abort()
      if (url.pathname === '/api/admin/configurations/editor-fixture') {
        const payload = route.request().postDataJSON()
        requests.push(payload.definition)
        if (rejectNext) {
          rejectNext = false
          return route.fulfill({ status: 422, json: { detail: '字段校验失败（测试）' } })
        }
        return route.fulfill({ json: { success: true, data: {
          id: 'editor-fixture', tenant_id: 'fixture-tenant', project_id: 'fixture-project',
          name: '立项基本信息-药物注册类', code: 'fixture', type: 'extract', status: 'draft',
          description: '', draft_definition: payload.definition, current_revision_id: null,
          created_at: '2026-01-01T00:00:00Z', updated_at: `2026-01-01T00:00:${String(requests.length).padStart(2, '0')}Z`,
        } } })
      }
      return route.continue()
    })
    try {
      await page.goto(`${base}/e2e/extract-editor.html${suffix}`)
      await page.getByTestId('extract-schema-editor').waitFor()
      await fn(page, requests, () => { rejectNext = true })
      assert.deepEqual(runtimeErrors, [], 'no browser runtime errors')
      console.log(`PASS ${++passed}: ${name}`)
    } catch (error) {
      fs.mkdirSync('/tmp/extract-editor-browser', { recursive: true })
      await page.screenshot({ path: '/tmp/extract-editor-browser/failure.png', fullPage: true })
      fs.writeFileSync('/tmp/extract-editor-browser/failure.html', await page.content())
      console.error(`FAIL: ${name}`, error)
      throw error
    } finally { await page.close() }
  }
  const saved = (page, count = 1) => page.waitForFunction((n) => window.savedCount === n, count)
  const saveButton = (page) => page.getByRole('button', { name: '保存草稿', exact: true })
  const scroll = (page) => page.locator('#editor-scroll').evaluate((el) => el.scrollTop)
  const footerVisible = async (page) => {
    const box = await page.getByTestId('save-bar').boundingBox()
    assert.ok(box && box.y >= 64 && box.y + box.height <= 901, 'save bar remains in scroll viewport')
  }
  try {
    await scenario('38th row: multi-field edits and keyboard save include focused input; no scroll/reset', async (page, requests) => {
      assert.equal(await page.locator('tr[data-field-path]').count(), 38)
      await footerVisible(page)
      await row(page, top('registration_type')).getByRole('textbox', { name: '展示标签' }).fill('登记类型')
      await row(page, top('project_name')).getByRole('button', { name: /^抽取说明 / }).click()
      await page.getByRole('textbox', { name: '编辑抽取说明 项目名称', exact: true }).fill('只摘录完整名称')
      const last = row(page, top('control_products'))
      await last.getByRole('textbox', { name: '展示标签' }).fill('对照产品新标签')
      await last.getByRole('button', { name: /^抽取说明 / }).click()
      const hint = page.getByRole('textbox', { name: '编辑抽取说明 对照产品新标签', exact: true })
      await hint.fill('最后一行的最后一个字')
      const before = await scroll(page)
      assert.ok(before > 500)
      await footerVisible(page)
      await hint.press('Control+s')
      await saved(page)
      assert.equal(requests.length, 1)
      assert.equal(requests[0].data_schema.properties.control_products.description, '最后一行的最后一个字')
      assert.equal(requests[0].data_schema.properties.project_name.description, '只摘录完整名称')
      assert.equal(requests[0].ui[top('registration_type')].label, '登记类型')
      assert.ok(Math.abs(await scroll(page) - before) < 3, 'save must not jump to top')
      assert.equal(await hint.isVisible(), true, 'detail remains expanded after parent updated_at changes')
      assert.equal(await saveButton(page).isDisabled(), true)
    })
    await scenario('new object list: add five child definitions without intermediate saves', async (page, requests) => {
      await page.getByRole('combobox', { name: '新增字段类型' }).selectOption('object-list')
      await page.getByRole('button', { name: '新增字段', exact: true }).click()
      const parent = row(page, top('field_1'))
      await parent.getByRole('textbox', { name: '字段键名' }).fill('products_new')
      for (let i = 1; i <= 5; i++) {
        await parent.getByRole('button', { name: '＋子字段', exact: true }).click()
        const child = row(page, `${top('field_1')}/items/properties/field_${i}`)
        await child.getByRole('textbox', { name: '字段键名' }).fill(`child_${i}`)
        if (i === 1) await child.getByRole('checkbox', { name: '必填' }).check()
      }
      assert.equal(requests.length, 0)
      await page.keyboard.press('Control+s')
      await saved(page)
      assert.deepEqual(Object.keys(requests[0].data_schema.properties.products_new.items.properties), ['child_1', 'child_2', 'child_3', 'child_4', 'child_5'])
      assert.deepEqual(requests[0].data_schema.properties.products_new.items.required, ['child_1'])
      assert.equal(requests[0].data_schema.required, undefined)
      assert.equal(await row(page, `${top('products_new')}/items/properties/child_5`).isVisible(), true)
    })
    await scenario('copy container: nested enum edits independent; UI and required copied', async (page, requests) => {
      await row(page, top('control_products')).getByRole('button', { name: /^更多 / }).click()
      await page.getByRole('button', { name: '复制字段', exact: true }).click()
      const copy = row(page, top('control_products_copy'))
      await copy.getByRole('textbox', { name: '字段键名' }).fill('products_copy')
      const childPath = `${top('control_products_copy')}/items/properties/dosage_form`
      await row(page, childPath).getByRole('button', { name: /^候选值 / }).click()
      await page.getByRole('textbox', { name: '编辑候选值 剂型', exact: true }).fill('选项A\n选项B\n')
      await page.keyboard.press('Control+s')
      await saved(page)
      assert.deepEqual(requests[0].data_schema.properties.products_copy.items.properties.dosage_form.enum, ['选项A', '选项B'])
      assert.notDeepEqual(requests[0].data_schema.properties.control_products.items.properties.dosage_form.enum, ['选项A', '选项B'])
      assert.deepEqual(requests[0].data_schema.properties.products_copy.items.required, ['name'])
      assert.equal(requests[0].ui[`${top('products_copy')}/items/properties/name`].label, '产品名称')
    })
    await scenario('inline duplicate key does not block other rows; JSON errors and failed saves retain input', async (page, requests, failNext) => {
      const first = row(page, top('registration_type'))
      await first.getByRole('textbox', { name: '字段键名' }).fill('trial_type')
      await row(page, top('project_name')).getByRole('textbox', { name: '展示标签' }).fill('保留修改')
      assert.equal(await saveButton(page).isDisabled(), true)
      await page.getByRole('button', { name: /处错误，点击定位/ }).click()
      assert.equal(await first.getByRole('textbox', { name: '字段键名' }).evaluate((el) => el === document.activeElement), true)
      await first.getByRole('textbox', { name: '字段键名' }).fill('reg_type')
      await page.getByRole('tab', { name: 'JSON', exact: true }).click()
      const json = page.getByRole('textbox', { name: 'JSON Schema', exact: true })
      const valid = await json.inputValue()
      assert.ok(JSON.parse(valid).properties.reg_type)
      await json.fill('{')
      await saveButton(page).click()
      await page.getByRole('alert').waitFor()
      assert.equal(await json.inputValue(), '{')
      await json.fill(valid)
      await page.getByRole('tab', { name: 'Builder', exact: true }).click()
      failNext()
      await saveButton(page).click()
      await page.getByRole('alert').filter({ hasText: '字段校验失败' }).waitFor()
      assert.equal(await row(page, top('project_name')).getByRole('textbox', { name: '展示标签' }).inputValue(), '保留修改')
      await saveButton(page).click(); await saved(page)
      assert.equal(requests.length, 2)
      assert.equal(requests[1].ui[top('project_name')].label, '保留修改')
    })
    await scenario('search keeps parent context, active row, and search state across save', async (page) => {
      await page.getByRole('textbox', { name: '搜索字段' }).fill('产品英文名')
      const child = row(page, `${top('control_products')}/items/properties/name_en`)
      assert.equal(await child.isVisible(), true)
      assert.equal(await row(page, top('control_products')).isVisible(), true)
      await child.getByRole('textbox', { name: '展示标签' }).fill('新英文名')
      assert.equal(await child.isVisible(), true, 'search edit must not unmount the active row')
      await page.keyboard.press('Control+s'); await saved(page)
      assert.equal(await page.getByRole('textbox', { name: '搜索字段' }).inputValue(), '产品英文名')
      assert.equal(await child.isVisible(), true)
    })
    await scenario('object/list conversion and destructive cancel preserve child input', async (page, requests) => {
      const parent = row(page, top('control_products'))
      await parent.getByRole('button', { name: /^展开 / }).click()
      await row(page, `${top('control_products')}/items/properties/name`).getByRole('textbox', { name: '字段键名' }).fill('title')
      page.once('dialog', (dialog) => dialog.dismiss())
      await parent.getByRole('combobox', { name: '字段类型' }).selectOption('text')
      assert.equal(await parent.getByRole('combobox', { name: '字段类型' }).inputValue(), 'object-list')
      page.once('dialog', (dialog) => dialog.accept())
      await parent.getByRole('combobox', { name: '字段类型' }).selectOption('object')
      assert.equal(await row(page, `${top('control_products')}/properties/name`).getByRole('textbox', { name: '字段键名' }).inputValue(), 'title')
      await saveButton(page).click(); await saved(page)
      assert.deepEqual(requests[0].data_schema.properties.control_products.required, ['title'])
      assert.equal(requests[0].data_schema.properties.control_products.type, 'object')
    })
    await scenario('insert below, keyboard navigation, and Chinese IME Enter', async (page, requests) => {
      await row(page, top('trial_phase')).getByRole('button', { name: /^更多 / }).click()
      await page.getByRole('button', { name: '在下方插入', exact: true }).click()
      const input = row(page, top('field_1')).getByRole('textbox', { name: '字段键名' })
      await input.fill('inserted')
      await input.evaluate((el) => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, isComposing: true })))
      assert.equal(await input.evaluate((el) => el === document.activeElement), true)
      await input.press('Enter')
      assert.equal(await input.evaluate((el) => el === document.activeElement), false)
      const paths = await page.locator('tr[data-field-path]').evaluateAll((els) => els.map((el) => el.dataset.fieldPath))
      assert.equal(paths[paths.indexOf(top('trial_phase')) + 1], top('field_1'))
      await saveButton(page).click(); await saved(page)
      assert.ok(requests[0].data_schema.properties.inserted)
    })
    await scenario('archived configuration has no edit/save actions', async (page, requests) => {
      assert.equal(await row(page, top('trial_phase')).getByRole('textbox', { name: '字段键名' }).isDisabled(), true)
      assert.equal(await saveButton(page).count(), 0)
      await page.getByRole('tab', { name: 'JSON', exact: true }).click()
      assert.equal(await page.getByRole('textbox', { name: 'JSON Schema', exact: true }).isDisabled(), true)
      assert.equal(requests.length, 0)
    }, '?readonly=1')
    console.log(`Browser interaction checks: ${passed} passed`)
  } finally { await browser.close() }
}
main().catch((error) => { console.error(error); process.exitCode = 1 })
