import { expect, type Page, test } from '@playwright/test'

import {
  hasSparc64Profile,
  hasSparc64ProfileUi,
  NODE,
  PASSWORD,
  type Pve,
  pveApi,
  pveExec,
  qemuAccepts,
  showcmd,
  vmConfFile,
  writeConfFile,
} from './_pve'

// The sparc64 profile (submodules/SPARC.md, "sparc64 (sun4u)"): sun4u with OpenBIOS, one CPU, up to
// 3072 MB, disks and CD-ROMs on the built-in IDE, the boot device as `-boot order=c|d` instead of
// bootindex (which OpenBIOS can't follow), no balloon device, at most four NICs (PCI bus B), the NIC
// models NetBSD drives, displays std/serial0/none. What qemu-server accepts and builds for it, what
// it refuses, and the wizard and Hardware editors that offer only it.

// TODO: drop the test.fail(!profile) and test.fail(!ui) markers once qemu-server and pve-manager with
// the sparc64 profile are published at debian.wshosting.no. Until then the PR e2e installs packages
// that build sparc64 VMs with SCSI and bootindex and refuse nothing.
let profile: boolean
let ui: boolean

const ISO_NAME = 'e2e-sparc64.iso'
const ISO = `local:iso/${ISO_NAME}`

let pve: Pve

test.beforeAll(async () => {
  const { code, output } = await pveExec([
    'sh',
    '-c',
    `mkdir -p /var/lib/vz/template/iso && truncate -s 1M /var/lib/vz/template/iso/${ISO_NAME}`,
  ])
  expect(code, output).toBe(0)
  profile = await hasSparc64Profile()
  ui = await hasSparc64ProfileUi()
})

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  const vms = await pve.get<{ status: string; vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { status, vmid } of vms) {
    if (status === 'running') await pveExec(['qm', 'stop', String(vmid)])
    await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
  }
})

async function createVm(params: Record<string, number | string>): Promise<number> {
  const vmid = Number(await pve.get<string>('/cluster/nextid'))
  const upid = await pve.post<string>(`/nodes/${NODE}/qemu`, { vmid, ...params })
  const path = `/nodes/${NODE}/tasks/${encodeURIComponent(upid)}/status`
  await expect
    .poll(async () => (await pve.get<{ status: string }>(path)).status, { intervals: [250], timeout: 30_000 })
    .toBe('stopped')
  const { exitstatus } = await pve.get<{ exitstatus: string }>(path)
  expect(exitstatus, `task ${upid}`).toBe('OK')
  return vmid
}

/** What the create wizard submits for sparc64 with an install CD (no boot order: the API's default). */
const WIZARD_LAYOUT = {
  arch: 'sparc64',
  ide0: 'local:0.0625,format=raw',
  ide2: `${ISO},media=cdrom`,
  memory: 512,
  name: 'sparc64-profile',
  net0: 'sunhme,bridge=vmbr0',
  ostype: 'other',
}

/** The `-boot` argument of a `qm showcmd --pretty` output. */
function bootArg(cmd: string): string | undefined {
  const line = cmd.split('\n').find((l) => l.trimStart().startsWith("-boot '"))
  return line?.trim().slice("-boot '".length).split("'")[0]
}

test.describe('sparc64, created through the API', () => {
  test('the wizard layout: IDE disk and CD-ROM, the CD boots first, no bootindex or balloon', async () => {
    test.fail(!profile, 'qemu-server without the sparc64 profile')
    const vmid = await createVm(WIZARD_LAYOUT)

    // the install CD first: OpenBIOS boots one device and doesn't fall back to the next
    expect(await vmConfFile(vmid)).toMatch(/^boot: order=ide2;ide0;net0$/m)

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc64 \\$/m)
    expect(cmd).toContain("-machine 'accel=tcg,type=sun4u+pve0'")
    expect(bootArg(cmd)).toMatch(/^order=d,menu=on,/)
    expect(cmd).toContain("-smp '1,sockets=1,cores=1,maxcpus=1'")
    expect(cmd).toContain('-vga std')
    expect(cmd).toContain('-m 512')
    expect(cmd).toContain("-device 'ide-hd,bus=ide.0,unit=0,drive=drive-ide0,id=ide0,")
    expect(cmd).toMatch(/-device 'ide-cd,bus=ide.1,unit=0,drive=drive-ide2,id=ide2,[^']*physical_block_size=512'/)
    expect(cmd).toMatch(/-device 'sunhme,mac=[\dA-F:]+,netdev=net0,id=net0,bus=pciB'/)
    for (const absent of ['bootindex', 'virtio-balloon', 'lsi', 'scsi-', '-cpu', '-bios', 'usb-tablet', 'vmgenid'])
      expect(cmd).not.toContain(absent)

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('the CD ejected (or the disk first in the boot order): the disk boots', async () => {
    test.fail(!profile, 'qemu-server without the sparc64 profile')
    const vmid = await createVm(WIZARD_LAYOUT)
    const config = `/nodes/${NODE}/qemu/${vmid}/config`

    await pve.put(config, { ide2: 'none,media=cdrom' })
    expect(bootArg(await showcmd(vmid))).toMatch(/^order=c,/)

    await pve.put(config, { boot: 'order=ide0;ide2', ide2: `${ISO},media=cdrom` })
    expect(bootArg(await showcmd(vmid))).toMatch(/^order=c,/)

    // only the network in the boot order: QEMU's default (the disk), no network boot
    await pve.put(config, { boot: 'order=net0' })
    expect(bootArg(await showcmd(vmid))).toMatch(/^menu=on,/)
  })

  test('a serial console on ttya (vga serial0)', async () => {
    test.fail(!profile, 'qemu-server without the sparc64 profile')
    const vmid = await createVm({ ...WIZARD_LAYOUT, serial0: 'socket', vga: 'serial0' })

    const cmd = await showcmd(vmid)
    expect(cmd).toContain(`-chardev 'socket,id=serial0,path=/var/run/qemu-server/${vmid}.serial0,server=on,wait=off'`)
    expect(cmd).toContain('-serial chardev:serial0')
    expect(cmd).toContain('-nographic')
    expect(cmd).not.toContain('isa-serial')
    expect(bootArg(cmd)).toMatch(/^order=d,/)

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('four NICs of the allowed models fill PCI bus B, and QEMU takes them', async () => {
    // Before the profile the virtio-balloon (no bus given) took one of pciB's four slots too, and
    // QEMU refused the fourth NIC: "PCI: no slot/function available for rtl8139".
    test.fail(!profile, 'qemu-server without the sparc64 profile')
    const vmid = await createVm({
      ...WIZARD_LAYOUT,
      net1: 'virtio,bridge=vmbr0',
      net2: 'e1000,bridge=vmbr0',
      net3: 'rtl8139,bridge=vmbr0',
    })
    const cmd = await showcmd(vmid)
    for (const model of ['sunhme', 'virtio-net-pci', 'e1000', 'rtl8139'])
      expect(cmd).toMatch(new RegExp(`-device '${model},[^']*bus=pciB'`))

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)

    // ne2k_pci in place of one of them
    await pve.put(`/nodes/${NODE}/qemu/${vmid}/config`, { net3: 'ne2k_pci,bridge=vmbr0' })
    const ne2k = await qemuAccepts(vmid)
    expect(ne2k.code, ne2k.output).toBe(0)
  })
})

test.describe('refused combinations', () => {
  const cases: { name: string; params: Record<string, number | string>; message: string }[] = [
    {
      message: "sparc64: scsi0 can't be used, disks and CD-ROMs go on the built-in IDE (ide0 to ide3)",
      name: 'a SCSI disk (OpenBIOS has no lsi driver)',
      params: { scsi0: 'local:0.0625,format=raw' },
    },
    {
      message: "sparc64: scsi2 can't be used, disks and CD-ROMs go on the built-in IDE (ide0 to ide3)",
      name: 'a SCSI CD-ROM (the old wizard default)',
      params: { scsi2: `${ISO},media=cdrom` },
    },
    {
      message: "sparc64: virtio0 can't be used, disks and CD-ROMs go on the built-in IDE (ide0 to ide3)",
      name: 'a virtio-blk disk (OpenBIOS can not boot it)',
      params: { virtio0: 'local:0.0625,format=raw' },
    },
    {
      message: "sparc64: sata0 can't be used, disks and CD-ROMs go on the built-in IDE (ide0 to ide3)",
      name: 'a SATA disk',
      params: { sata0: 'local:0.0625,format=raw' },
    },
    {
      message: 'sparc64: only one CPU is supported (sockets 1, cores 1), not 2',
      name: '2 cores',
      params: { cores: 2 },
    },
    {
      message: 'sparc64: only one CPU is supported (sockets 1, cores 1), not 2',
      name: '2 sockets',
      params: { sockets: 2 },
    },
    {
      message: 'sparc64: sun4u takes at most 3072 MB of memory, not 4096',
      name: '4096 MB (NetBSD panics)',
      params: { memory: 4096 },
    },
    {
      message: "sparc64: machine 'sun4v' is not supported, use sun4u",
      name: 'sun4v',
      params: { machine: 'sun4v' },
    },
    {
      message: "sparc64: firmware (bios) 'openbios-sparc32' is not supported, use openbios-sparc64",
      name: 'the sparc32 OpenBIOS',
      params: { bios: 'openbios-sparc32' },
    },
    {
      message: "sparc64: 'cpu' can't be set, the machine's default CPU is used",
      name: 'a CPU type',
      params: { cpu: 'kvm64' },
    },
    {
      message: "sparc64: display (vga) 'cirrus' is not supported, use one of: std, serial0, none",
      name: 'a display other than std, serial0 or none',
      params: { vga: 'cirrus' },
    },
    {
      message:
        "sparc64: network device model 'pcnet' is not supported, use one of: sunhme, virtio, e1000, rtl8139, ne2k_pci",
      name: 'pcnet (no NetBSD driver)',
      params: { net0: 'pcnet,bridge=vmbr0' },
    },
    {
      message: 'sparc64: at most 4 network devices fit on PCI bus B, not 5 (net0, net1, net2, net3, net4)',
      name: 'a fifth NIC',
      params: Object.fromEntries([0, 1, 2, 3, 4].map((i) => [`net${i}`, 'sunhme,bridge=vmbr0'])),
    },
    {
      message: 'sparc64: the QEMU guest agent is not supported',
      name: 'the guest agent',
      params: { agent: 1 },
    },
  ]

  for (const c of cases) {
    test(`create: ${c.name}`, async () => {
      test.fail(!profile, 'qemu-server without the sparc64 profile')
      const vmid = Number(await pve.get<string>('/cluster/nextid'))
      const refused = await pve.refused('POST', `/nodes/${NODE}/qemu`, {
        arch: 'sparc64',
        memory: 512,
        vmid,
        ...c.params,
      })
      expect(refused.message).toContain(c.message)
      const { code } = await pveExec(['test', '-e', `/etc/pve/qemu-server/${vmid}.conf`])
      expect(code, 'no config is left behind').not.toBe(0)
    })
  }

  test('update: the result must still match the profile', async () => {
    test.fail(!profile, 'qemu-server without the sparc64 profile')
    const vmid = await createVm(WIZARD_LAYOUT)
    const config = `/nodes/${NODE}/qemu/${vmid}/config`

    expect((await pve.refused('PUT', config, { memory: 4096 })).message).toContain(
      'sparc64: sun4u takes at most 3072 MB of memory, not 4096',
    )
    expect((await pve.refused('PUT', config, { cores: 2 })).message).toContain('sparc64: only one CPU is supported')
    expect((await pve.refused('PUT', config, { scsi1: 'local:0.0625,format=raw' })).message).toContain(
      "sparc64: scsi1 can't be used",
    )
    // a second disk on the IDE, and 3072 MB, are fine
    await pve.put(config, { ide1: 'local:0.0625,format=raw', memory: 3072 })
    const cmd = await showcmd(vmid)
    expect(cmd).toContain("-device 'ide-hd,bus=ide.0,unit=1,drive=drive-ide1,id=ide1,")
    expect(cmd).toContain('-m 3072')
  })

  test('an existing VM from the old wizard (SCSI) stays readable, but neither starts nor changes until fixed', async () => {
    test.fail(!profile, 'qemu-server without the sparc64 profile')
    const vmid = 964
    await writeConfFile(vmid, [
      'arch: sparc64',
      'boot: order=scsi0;scsi2;net0',
      'memory: 512',
      'name: sparc64-old',
      'net0: sunhme=BC:24:11:B2:46:64,bridge=vmbr0',
      'ostype: other',
      'scsi2: none,media=cdrom',
    ])
    const message = "sparc64: scsi2 can't be used, disks and CD-ROMs go on the built-in IDE (ide0 to ide3)"

    await pve.get(`/nodes/${NODE}/qemu/${vmid}/config`)
    const show = await pveExec(['qm', 'showcmd', String(vmid)])
    expect(show.code).not.toBe(0)
    expect(show.output).toContain(message)
    const start = await pveExec(['qm', 'start', String(vmid)])
    expect(start.code).not.toBe(0)
    expect(start.output).toContain(message)
    expect((await pve.refused('PUT', `/nodes/${NODE}/qemu/${vmid}/config`, { name: 'renamed' })).message).toContain(
      message,
    )

    // moving the CD-ROM to ide2 is accepted, and then it builds
    await pve.put(`/nodes/${NODE}/qemu/${vmid}/config`, {
      boot: 'order=ide2;net0',
      delete: 'scsi2',
      ide2: 'none,media=cdrom',
    })
    expect(await showcmd(vmid)).toContain("-device 'ide-cd,bus=ide.1,unit=0,id=ide2,")
  })
})

test.describe('web UI', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('create wizard: IDE disk and CD-ROM, sunhme, one CPU, 512 MB', async ({ page }) => {
    test.fail(!(ui && profile), 'pve-manager/qemu-server without the sparc64 profile')
    const vmid = Number(await pve.get<string>('/cluster/nextid'))
    const wizard = await openWizard(page, 'sparc64-ui')

    // General: the architecture (an advanced option).
    await pickCombo(page, wizard, 'vCPU Architecture', 'SPARC (64-bit)')
    await next(wizard)

    // OS: the install CD, Other.
    // (the second, disabled ISO selector is the Windows VirtIO drivers CD)
    await wizard.getByRole('combobox', { disabled: false, name: 'ISO image:' }).click()
    await page.getByRole('gridcell', { exact: true, name: ISO_NAME }).click() // a grid picker
    await pickCombo(page, wizard, 'Type', 'Other')
    await next(wizard)

    // System: the displays of the profile, VGA the default.
    expect(await comboOptions(page, wizard, 'Graphic card')).toEqual([
      'Default (Standard VGA)',
      'Serial terminal 0',
      'none',
    ])
    await next(wizard)

    // Disks: the first disk on the IDE's primary master.
    await expect(wizard.getByText('ide0', { exact: true })).toBeVisible()
    await next(wizard)

    // CPU: one, nothing to choose.
    await expect(wizard.getByLabel(fieldLabel('Sockets'))).toBeDisabled()
    await expect(wizard.getByLabel(fieldLabel('Cores'))).toBeDisabled()
    await next(wizard)

    // Memory: 512 MB, at most 3072.
    const memory = wizard.getByLabel(fieldLabel('Memory (MiB)'))
    await expect(memory).toHaveValue('512')
    await memory.fill('4096')
    await expect(wizard.getByRole('button', { name: 'Next' })).toBeDisabled()
    await memory.fill('512')
    await next(wizard)

    // Network: sunhme, and only the models NetBSD drives.
    await expect(wizard.getByLabel(fieldLabel('Model'))).toHaveValue(/Sun Happy Meal/)
    expect((await comboOptions(page, wizard, 'Model')).toSorted()).toEqual(
      [
        'Intel E1000',
        'Realtek RTL8139',
        'RTL8029 NE2000 PCI',
        'Sun Happy Meal (sparc64 only)',
        'VirtIO (paravirtualized)',
      ].toSorted(),
    )
    await next(wizard)

    await wizard.getByRole('button', { name: 'Finish' }).click()
    await expect.poll(async () => (await pveExec(['test', '-e', `/etc/pve/qemu-server/${vmid}.conf`])).code).toBe(0)
    await expect.poll(async () => (await vmConfFile(vmid)).includes('lock: create'), { timeout: 30_000 }).toBe(false)

    const conf = await vmConfFile(vmid)
    expect(conf).toMatch(/^arch: sparc64$/m)
    expect(conf).toMatch(/^ide0: local:\d+\/vm-\d+-disk-0/m)
    expect(conf).toContain(`ide2: ${ISO},media=cdrom`)
    expect(conf).toMatch(/^boot: order=ide2;ide0;net0$/m)
    expect(conf).toMatch(/^net0: sunhme=/m)
    for (const key of ['cpu', 'sockets', 'cores', 'vmgenid', 'scsi\\d+', 'scsihw'])
      expect(conf).not.toMatch(new RegExp(`^${key}:`, 'm'))

    const cmd = await showcmd(vmid)
    expect(bootArg(cmd)).toMatch(/^order=d,/)
    expect(cmd).not.toContain('bootindex')
    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test("Hardware: the editors offer only the profile's choices", async ({ page }) => {
    test.fail(!ui, 'pve-manager without the sparc64 profile')
    const vmid = await createVm({
      ...WIZARD_LAYOUT,
      net1: 'sunhme,bridge=vmbr0',
      net2: 'sunhme,bridge=vmbr0',
      net3: 'sunhme,bridge=vmbr0',
    })
    await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
    await page.reload() // the resource tree learns about VMs created after login only on a reload
    await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()
    const editor = (title: string) => page.locator('.x-window').filter({ hasText: `Edit: ${title}` })

    await page.getByText(/^Display$/).dblclick()
    expect(await comboOptions(page, editor('Display'), 'Graphic card')).toEqual([
      'Default (Standard VGA)',
      'Serial terminal 0',
      'none',
    ])
    await closeWindow(editor('Display'))

    await page.getByText(/^Processors$/).dblclick()
    await expect(editor('Processors').getByLabel(fieldLabel('Sockets'))).toBeDisabled()
    await expect(editor('Processors').getByLabel(fieldLabel('Cores'))).toBeDisabled()
    await closeWindow(editor('Processors'))

    await page.getByText(/^Memory$/).dblclick()
    await editor('Memory').getByLabel(fieldLabel('Memory (MiB)')).fill('4096')
    await expect(editor('Memory').getByRole('button', { name: 'OK' })).toBeDisabled()
    await closeWindow(editor('Memory'))

    // four NICs fill PCI bus B
    await page.getByRole('button', { name: 'Add' }).click()
    await expect(page.getByRole('menuitem', { name: 'Network Device' })).toBeDisabled()
  })
})

async function login(page: Page) {
  await page.goto('/')
  await page.locator('input[name=username]').fill('root')
  await page.locator('input[name=password]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Login' }).click()
  // Every login on a node without a subscription.
  await page.getByRole('button', { name: 'OK' }).click()
}

async function openWizard(page: Page, name: string) {
  await page.getByRole('button', { name: 'Create VM' }).click()
  const wizard = page.locator('.x-window').filter({ hasText: 'Create: Virtual Machine' })
  await wizard.getByLabel('Name').fill(name)
  await wizard.getByLabel('Advanced').check()
  return wizard
}

async function next(wizard: ReturnType<Page['locator']>) {
  await wizard.getByRole('button', { name: 'Next' }).click()
}

/** Opens the combo labelled `label` in `win` and picks the entry showing `option`. */
async function pickCombo(page: Page, win: ReturnType<Page['locator']>, label: string, option: string) {
  await win.getByLabel(fieldLabel(label)).click()
  await page.locator('.x-boundlist:visible li').filter({ hasText: option }).first().click()
}

/** The entries the combo labelled `label` offers. */
async function comboOptions(page: Page, win: ReturnType<Page['locator']>, label: string): Promise<string[]> {
  await win.getByLabel(fieldLabel(label)).click()
  const items = page.locator('.x-boundlist:visible li')
  await expect(items.first()).toBeVisible()
  const texts = await items.allInnerTexts()
  await page.keyboard.press('Escape')
  return texts.map((t) => t.trim())
}

/** An ExtJS field label: the text, then a colon. */
function fieldLabel(label: string): RegExp {
  return new RegExp(`^${label.replace(/[()]/g, '[$&]')}:?$`)
}

async function closeWindow(win: ReturnType<Page['locator']>) {
  await win.locator('.x-tool-close').click()
  await expect(win).toBeHidden()
}
