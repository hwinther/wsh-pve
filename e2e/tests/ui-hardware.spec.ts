import { expect, type Page, test } from '@playwright/test'

import {
  NODE,
  PASSWORD,
  type Pve,
  pveApi,
  pveManagerHasDbusDisplay,
  pveManagerHasMesaDisplay,
  qemuAccepts,
  qemuServerHasDbusDisplay,
  qemuServerHasMesaDisplay,
  showcmd,
  vmConfFile,
} from './_pve'

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

test('display: Enable 3DFX/Mesa', async ({ page }) => {
  await page.getByText(/^Display$/).dblclick()
  const win = page.locator('.x-window').filter({ has: page.getByText('Graphic card:', { exact: true }) })
  await win.getByLabel('Graphic card').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'Standard VGA' }).click()
  await win.getByLabel('Enable 3DFX/Mesa').check()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()

  // The command (the 3dfx binary) and whether QEMU takes it: vm-config.spec.ts.
  expect(await vmConfFile(VMID)).toMatch(/^vga: std,mesa=1$/m)
})

test('display: 3DFX/Mesa display egl-headless', async ({ page }) => {
  test.skip(!(await pveManagerHasMesaDisplay()), 'the installed pve-manager has no 3DFX/Mesa display field yet')
  test.skip(!(await qemuServerHasMesaDisplay()), 'the installed qemu-server has no mesa-display yet')
  const display = async () => {
    await page.getByText(/^Display$/).dblclick()
    return page.locator('.x-window').filter({ has: page.getByText('Graphic card:', { exact: true }) })
  }

  let win = await display()
  await win.getByLabel('Graphic card').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'Standard VGA' }).click()
  // only with 3DFX/Mesa enabled
  await expect(win.getByLabel('3DFX/Mesa display')).toBeHidden()
  await win.getByLabel('Enable 3DFX/Mesa').check()
  await expect(win.getByLabel('3DFX/Mesa display')).toBeVisible()
  await win.getByLabel('3DFX/Mesa display').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'egl-headless' }).click()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  // the dialog sorts the keys
  expect(await vmConfFile(VMID)).toMatch(/^vga: std,mesa-display=egl-headless,mesa=1$/m)
  expect(await showcmd(VMID)).toMatch(/^ {2}-display egl-headless \\$/m)

  // reopened: the field shows it; 3DFX/Mesa off again takes the field (and the key) away
  win = await display()
  await expect(win.getByLabel('3DFX/Mesa display')).toHaveValue(/egl-headless/)
  await win.getByLabel('Enable 3DFX/Mesa').uncheck()
  await expect(win.getByLabel('3DFX/Mesa display')).toBeHidden()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  expect(await vmConfFile(VMID)).toMatch(/^vga: std,mesa=0$/m)
  expect(await showcmd(VMID)).not.toContain('-display')
})

test('display: VGA retrace Precise (DOS games)', async ({ page }) => {
  const display = async () => {
    await page.getByText(/^Display$/).dblclick()
    return page.locator('.x-window').filter({ has: page.getByText('Graphic card:', { exact: true }) })
  }
  const pick = async (win: Awaited<ReturnType<typeof display>>, option: string) => {
    await win.getByLabel('Graphic card').click()
    await page.locator('.x-boundlist:visible li', { hasText: option }).click()
  }

  let win = await display()
  await expect(win.getByLabel('VGA retrace')).toBeVisible({ timeout: 5000 })
  // only for display types with a VGA core
  await pick(win, 'Serial terminal 0')
  await expect(win.getByLabel('VGA retrace')).toBeHidden()
  await pick(win, 'Standard VGA')
  await win.getByLabel('VGA retrace').check()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  expect(await vmConfFile(VMID)).toMatch(/^vga: std,mesa=0,retrace=precise$/m)
  expect(await showcmd(VMID)).toContain("-vga 'none,retrace=precise'")
  const qemu = await qemuAccepts(VMID)
  expect(qemu.code, qemu.output).toBe(0)

  // unchecked again: the key goes
  win = await display()
  await expect(win.getByLabel('VGA retrace')).toBeChecked()
  await win.getByLabel('VGA retrace').uncheck()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  expect(await vmConfFile(VMID)).toMatch(/^vga: std,mesa=0$/m)
})

test('machine: Legacy BIOS memory layout', async ({ page }) => {
  const machine = async () => {
    await page.getByText(/^Machine$/).dblclick()
    const win = page.locator('.x-window').filter({ has: page.getByText('Machine:', { exact: true }) })
    await win.getByLabel('Advanced').check()
    return win
  }

  let win = await machine()
  await expect(win.getByLabel('Legacy BIOS memory layout')).toBeVisible({ timeout: 5000 })
  await win.getByLabel('Legacy BIOS memory layout').check()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  expect(await vmConfFile(VMID)).toMatch(/^machine: pc,legacy-bios-layout=1$/m)
  const cmd = await showcmd(VMID)
  expect(cmd).toContain("-global 'apic-common.vapic=off'")
  expect(cmd).toMatch(/-device 'e1000,mac=[^']*,romfile='/)

  // unchecked again: the key goes, and with it the whole machine line (the default type)
  win = await machine()
  await expect(win.getByLabel('Legacy BIOS memory layout')).toBeChecked()
  await win.getByLabel('Legacy BIOS memory layout').uncheck()
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  expect(await vmConfFile(VMID)).not.toMatch(/^machine:/m)
})

test('display: D-Bus display with refresh, and the D-Bus audio driver', async ({ page }) => {
  test.skip(!(await pveManagerHasDbusDisplay()), 'the installed pve-manager has no D-Bus display field yet')
  test.skip(!(await qemuServerHasDbusDisplay()), 'the installed qemu-server has no D-Bus display yet')
  const display = async () => {
    await page.getByText(/^Display$/).dblclick()
    return page.locator('.x-window').filter({ has: page.getByText('Graphic card:', { exact: true }) })
  }

  let win = await display()
  await win.getByLabel('Graphic card').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'Standard VGA' }).click()
  // the refresh only with the D-Bus display
  await expect(win.getByLabel('D-Bus refresh (ms)')).toBeHidden()
  await win.getByLabel('D-Bus display').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'D-Bus, next to VNC' }).click()
  await expect(win.getByLabel('D-Bus refresh (ms)')).toBeVisible()
  await win.getByLabel('D-Bus refresh (ms)').fill('14')
  await win.getByRole('button', { name: 'OK' }).click()
  await expect(win).toBeHidden()
  // the dialog sorts the keys
  expect(await vmConfFile(VMID)).toMatch(/^vga: std,dbus-refresh=14,display=dbus,mesa=0$/m)
  expect(await showcmd(VMID)).toContain(
    `-display 'dbus,addr=unix:path=/run/wsh-dbus-display/${VMID}.sock,refresh-ms=14'`,
  )

  // a SPICE card has no D-Bus display: the fields go
  win = await display()
  await expect(win.getByLabel('D-Bus display')).toHaveValue(/D-Bus, next to VNC/)
  await win.getByLabel('Graphic card').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'SPICE' }).first().click()
  await expect(win.getByLabel('D-Bus display')).toBeHidden()
  await expect(win.getByLabel('D-Bus refresh (ms)')).toBeHidden()
  // PVE's edit windows have OK and Reset, no Cancel: close it
  await win.locator('.x-tool-close').click()
  await expect(win).toBeHidden()

  // Add, Audio Device, with the D-Bus driver
  await page.getByRole('button', { name: 'Add' }).click()
  await page.getByRole('menuitem', { name: 'Audio Device' }).click()
  const audio = page.locator('.x-window').filter({ has: page.getByText('Backend Driver:', { exact: true }) })
  await audio.getByLabel('Audio Device').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'Intel AC97 Audio' }).click()
  await audio.getByLabel('Backend Driver').click()
  await page.locator('.x-boundlist:visible li', { hasText: 'D-Bus' }).click()
  await audio.getByRole('button', { name: 'Add' }).click()
  await expect(audio).toBeHidden()
  expect(await vmConfFile(VMID)).toMatch(/^audio0: device=AC97,driver=dbus$/m)
  const cmd = await showcmd(VMID)
  expect(cmd).toContain(',refresh-ms=14,audiodev=dbus-backend0')
  expect(cmd).toContain("-audiodev 'dbus,id=dbus-backend0,out.frequency=48000'")
})
