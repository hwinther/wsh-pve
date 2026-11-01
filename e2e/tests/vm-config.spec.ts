import { expect, test } from '@playwright/test'

import { NODE, type Pve, pveApi, qemuAccepts, showcmd, vmConfFile, writeConfFile } from './_pve'

// VMs with the WSH options, created through the API: the stored config, the QEMU command qemu-server
// builds from it (`qm showcmd`) and whether QEMU accepts that command. This is the layer the
// qemu-server patch changes, and the one an upstream refactor breaks (2026-11-01: the PCI bridge
// rework silently dropped four hunks).

let pve: Pve

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

async function createVm(params: Record<string, number | string>): Promise<number> {
  const vmid = Number(await pve.get<string>('/cluster/nextid'))
  // Creation runs as a background task (the config says `lock: create` until it's done).
  await waitForTask(await pve.post<string>(`/nodes/${NODE}/qemu`, { vmid, ...params }))
  return vmid
}

async function waitForTask(upid: string): Promise<void> {
  const path = `/nodes/${NODE}/tasks/${encodeURIComponent(upid)}/status`
  await expect
    .poll(async () => (await pve.get<{ status: string }>(path)).status, { intervals: [250], timeout: 30_000 })
    .toBe('stopped')
  const { exitstatus } = await pve.get<{ exitstatus: string }>(path)
  expect(exitstatus, `task ${upid}`).toBe('OK')
}

test.afterEach(async () => {
  const vms = await pve.get<{ vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { vmid } of vms) await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
})

test('x86: retro devices (sb16, cirrus, ne2k_pci) end up in the QEMU command', async () => {
  const vmid = await createVm({
    audio0: 'device=sb16,driver=none',
    memory: 512,
    name: 'x86-retro',
    net0: 'ne2k_pci,bridge=vmbr0',
    scsi0: 'local:1',
    vga: 'cirrus',
  })

  const conf = await vmConfFile(vmid)
  expect(conf).toContain('audio0: device=sb16,driver=none')
  expect(conf).toContain('vga: cirrus')
  expect(conf).toMatch(/^net0: ne2k_pci=[\dA-F:]+,bridge=vmbr0$/m)

  const cmd = await showcmd(vmid)
  expect(cmd).toContain("-device 'sb16,id=audiodev0,audiodev=none-backend0'")
  expect(cmd).toContain("-device 'cirrus-vga,id=vga,bus=pci.0,addr=0x2'")
  expect(cmd).toMatch(/-device 'ne2k_pci,mac=[\dA-F:]+,netdev=net0,/)

  const qemu = await qemuAccepts(vmid)
  expect(qemu.code, qemu.output).toBe(0)
})

test('x86: sb16 + adlib + pcspk combo device', async () => {
  const vmid = await createVm({ audio0: 'device=sb16-adlib-pcspk,driver=none', memory: 512, name: 'x86-audio' })

  const cmd = await showcmd(vmid)
  expect(cmd).toContain("-device 'sb16,audiodev=none-backend0'")
  expect(cmd).toContain("-device 'adlib,audiodev=none-backend0'")
  expect(cmd).toContain('pcspk-audiodev=none-backend0')

  const qemu = await qemuAccepts(vmid)
  expect(qemu.code, qemu.output).toBe(0)
})

// A real sparc32 VM (solaris26-sparc on pve-test3, created 2024-01). Like every sparc VM there, it
// turns off the tablet and balloon itself: the SS-5 has neither USB nor virtio.
const SOLARIS26_CONF = [
  'arch: sparc',
  'balloon: 0',
  'bios: ss5.bin',
  'boot: order=scsi3',
  'cores: 1',
  'machine: SS-5',
  'memory: 256',
  'name: solaris26-sparc',
  'net0: lance=BC:24:11:B2:46:01,bridge=vmbr0,tag=100',
  'numa: 0',
  'ostype: solaris',
  'sockets: 1',
  'tablet: 0',
  'vga: cg3',
]

test.describe('sparc32, config written to the file', () => {
  const vmid = 906

  test.beforeEach(async () => {
    await writeConfFile(vmid, SOLARIS26_CONF)
  })

  test('the command QEMU builds from a real sparc32 VM starts', async () => {
    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc \\$/m)
    expect(cmd).toContain('-bios ss5.bin')
    expect(cmd).toContain('-vga cg3')
    expect(cmd).toContain("-machine 'accel=tcg,type=SS-5+pve0'")
    expect(cmd).not.toContain('usb-tablet')
    expect(cmd).not.toContain('virtio-balloon')

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('the API reads the config and edits other options', async () => {
    // What the UI does with an existing sparc VM. (Only the `qm config` CLI verifies the result
    // against the schema and refuses it.)
    const conf = await pve.get<Record<string, string>>(`/nodes/${NODE}/qemu/${vmid}/config`)
    expect(conf.arch).toBe('sparc')
    await pve.post(`/nodes/${NODE}/qemu/${vmid}/config`, { memory: 128 })
    expect(await vmConfFile(vmid)).toContain('memory: 128')
  })

  test('the API sets arch (the Architecture panel)', async () => {
    // KNOWN BUG: `arch` is still enum x86_64/aarch64 (the pve-qm-cpu-arch standard option in
    // PVE::QemuServer::CPUConfig) and no patch extends it, so saving sparc/sparc64 is refused, and
    // so is creating a sparc VM.
    test.fail()
    await pve.post(`/nodes/${NODE}/qemu/${vmid}/config`, { arch: 'sparc64' })
    expect(await vmConfFile(vmid)).toContain('arch: sparc64')
  })

  test("the lance NIC uses the config's MAC address", async () => {
    // KNOWN BUG: the patch hardcodes macaddr=08:00:20:b5:09:67 for lance ("TODO: fix static hw"),
    // so every sparc32 VM on a bridge has the same MAC.
    test.fail()
    expect(await showcmd(vmid)).toContain("-net 'nic,model=lance,macaddr=BC:24:11:B2:46:01'")
  })
})

test.describe('sparc, created through the API', () => {
  // KNOWN BUG: the API refuses `arch: sparc|sparc64` (see "the API sets arch"). Once
  // that's fixed these also check the defaults: a sparc VM created without tablet/balloon settings
  // must not get a usb-tablet or virtio-balloon, which sparc32 doesn't have (and sparc64 has no USB
  // bus for). test.fail() turns red once it's fixed: remove it then.
  test.fail()

  test('sparc32 (SS-5) with cg3 and lance starts', async () => {
    const vmid = await createVm({ arch: 'sparc', memory: 256, name: 'sparc32', net0: 'lance,bridge=vmbr0', vga: 'cg3' })

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc \\$/m)
    expect(cmd).toContain('type=SS-5')

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('sparc64 (sun4u) with sunhme starts', async () => {
    const vmid = await createVm({ arch: 'sparc64', memory: 512, name: 'sparc64', net0: 'sunhme,bridge=vmbr0' })

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc64 \\$/m)
    expect(cmd).toContain('type=sun4u')

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })
})
