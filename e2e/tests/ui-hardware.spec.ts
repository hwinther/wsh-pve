import { expect, type Page, test } from '@playwright/test'

import { NODE, PASSWORD, type Pve, pveApi, qemuAccepts, showcmd, vmConfFile } from './_pve'

// The pve-manager additions, driven through the web UI: pick a WSH option in a VM's Hardware view,
// then check what qemu-server stored and built from it. A UI change that sends the wrong value, or a
// qemu-server change that drops it, fails here.

const VMID = 200
let pve: Pve

test.beforeEach(async ({ page, request }) => {
  pve = await pveApi(request)
  await pve.post(`/nodes/${NODE}/qemu`, { memory: 512, name: 'ui-hardware', net0: 'e1000,bridge=vmbr0', vmid: VMID })
  await expect.poll(async () => (await vmConfFile(VMID)).includes('lock: create')).toBe(false)
  await login(page)
  await openHardware(page, VMID)
})

test.afterEach(async () => {
  await pve.delete(`/nodes/${NODE}/qemu/${VMID}?purge=1&destroy-unreferenced-disks=1`)
})

async function login(page: Page) {
  await page.goto('/')
  await page.locator('input[name=username]').fill('root')
  await page.locator('input[name=password]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Login' }).click()
  // Every login on a node without a subscription.
  await page.getByRole('button', { name: 'OK' }).click()
}

async function openHardware(page: Page, vmid: number) {
  await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
  await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()
}

/** Opens a Hardware row's edit window, picks `option` in its `field` combo and saves. */
async function editHardware(page: Page, row: RegExp, field: string, option: string) {
  await page.getByText(row).dblclick()
  const win = page.locator('.x-window').filter({ has: page.getByText(`${field}:`, { exact: true }) })
  await win.getByLabel(field).click()
  await page.locator('.x-boundlist:visible li', { hasText: option }).click()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
}

test('network card: RTL8029 NE2000 PCI', async ({ page }) => {
  await editHardware(page, /Network Device \(net0\)/, 'Model', 'RTL8029 NE2000 PCI')

  expect(await vmConfFile(VMID)).toMatch(/^net0: ne2k_pci=[\dA-F:]+,bridge=vmbr0/m)
  expect(await showcmd(VMID)).toMatch(/-device 'ne2k_pci,mac=/)
  const qemu = await qemuAccepts(VMID)
  expect(qemu.code, qemu.output).toBe(0)
})

test('network card: AMD PCnet FAST', async ({ page }) => {
  await editHardware(page, /Network Device \(net0\)/, 'Model', 'AMD PCnet FAST')

  expect(await vmConfFile(VMID)).toMatch(/^net0: pcnet=[\dA-F:]+,bridge=vmbr0/m)
  expect(await showcmd(VMID)).toMatch(/-device 'pcnet,mac=/)
  const qemu = await qemuAccepts(VMID)
  expect(qemu.code, qemu.output).toBe(0)
})

test('display: Cirrus', async ({ page }) => {
  await editHardware(page, /^Display$/, 'Graphic card', 'Cirrus')

  // The Display dialog always writes the 3dfx/mesa checkbox too.
  expect(await vmConfFile(VMID)).toMatch(/^vga: cirrus,mesa=0$/m)
  expect(await showcmd(VMID)).toContain("-device 'cirrus-vga,")
  const qemu = await qemuAccepts(VMID)
  expect(qemu.code, qemu.output).toBe(0)
})
