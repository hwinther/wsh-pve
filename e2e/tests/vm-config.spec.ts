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

/** A `-bios` argument in `qm showcmd --pretty` output (one argument per line). */
const BIOS_ARG = /^ {2}-bios /m

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
  expect(cmd, 'SeaBIOS is the default firmware').not.toMatch(BIOS_ARG)

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

// 3dfx/Mesa pass-through (Display → "Enable 3DFX/Mesa", `mesa=1`): qemu-server starts the VM with
// /usr/bin/qemu-system-x86_64-3dfx instead of /usr/bin/kvm, and with a `server` (the X display to show
// it on) with the SDL display. Pass-through itself needs the guest's wrapper drivers and the host's X
// server and GL; these check the command and that the 3dfx binary accepts it.
test.describe('x86: 3dfx/Mesa pass-through', () => {
  test('mesa=1 starts the VM with the 3dfx binary', async () => {
    const vmid = await createVm({ memory: 512, name: 'x86-3dfx', vga: 'std,mesa=1' })
    expect(await vmConfFile(vmid)).toContain('vga: std,mesa=1')

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-x86_64-3dfx \\$/m)
    expect(cmd).toContain("-device 'VGA,id=vga,bus=pci.0,addr=0x2'")

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('mesa=1 with a server uses the SDL display', async () => {
    const vmid = await createVm({ memory: 512, name: 'x86-3dfx-sdl', vga: 'std,mesa=1,server=:0' })

    const cmd = await showcmd(vmid)
    expect(cmd).toContain('-- Using sdl display with std driver and host :0')
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-x86_64-3dfx \\$/m)
    expect(cmd).toContain('-vga std')
    expect(cmd).toContain('-display sdl')

    // With SDL's dummy video driver: no X server here, so this doesn't show that the display works.
    const qemu = await qemuAccepts(vmid, { keepDisplay: true })
    expect(qemu.code, qemu.output).toBe(0)
  })
})

// UEFI VMs (`bios: ovmf`). qemu-server loads OVMF as two pflash drives: the firmware code read-only
// and the EFI vars (the efidisk, or a temporary copy without one). `-bios` is for the sparc firmware
// only (the sparc32 tests below check that it's still there); qemu-server up to 9.2.15+wsh2 also passed
// `-bios ovmf` for every OVMF VM, which x86 QEMU ignores next to the pflash drives and
// qemu-system-aarch64 refuses ("you cannot use both options at once").
test.describe('OVMF (UEFI)', () => {
  /** The two pflash drives: `code` read-only from pve-edk2-firmware, then the vars in `vars`. */
  function expectPflash(cmd: string, code: string, vars: string): void {
    expect(cmd).toContain(
      `-blockdev '{"driver":"raw","file":{"driver":"file","filename":"/usr/share/pve-edk2-firmware//${code}"},"node-name":"pflash0","read-only":true}'`,
    )
    const file = vars.replaceAll('.', '\\.')
    expect(cmd).toMatch(new RegExp(`"filename":"${file}".*"node-name":"drive-efidisk0","read-only":false`))
  }

  for (const { code, format, params, type } of [
    // What the create wizard makes on a directory storage: qcow2, 4M, Microsoft keys enrolled.
    {
      code: 'OVMF_CODE_4M.secboot.fd',
      format: 'qcow2',
      params: { efidisk0: 'local:1,efitype=4m,pre-enrolled-keys=1,format=qcow2', machine: 'q35' },
      type: 'q35',
    },
    // The default machine (i440fx), no keys.
    { code: 'OVMF_CODE_4M.fd', format: 'raw', params: { efidisk0: 'local:1,efitype=4m,format=raw' }, type: 'pc' },
  ]) {
    test(`x86 ${type}: OVMF with an efidisk is two pflash drives and no -bios`, async () => {
      const vmid = await createVm({ bios: 'ovmf', memory: 512, name: `x86-ovmf-${type}`, ...params })
      expect(await vmConfFile(vmid)).toMatch(new RegExp(`^efidisk0: local:${vmid}/vm-${vmid}-disk-0\\.${format},`, 'm'))

      const cmd = await showcmd(vmid)
      expect(cmd).toMatch(/^\/usr\/bin\/kvm \\$/m)
      expectPflash(cmd, code, `/var/lib/vz/images/${vmid}/vm-${vmid}-disk-0.${format}`)
      expect(cmd).toContain(`-machine 'pflash0=pflash0,pflash1=drive-efidisk0,type=${type}+pve0'`)

      const qemu = await qemuAccepts(vmid)
      expect(qemu.code, qemu.output).toBe(0)

      expect(cmd).not.toMatch(BIOS_ARG)
    })
  }

  test('x86: OVMF without an efidisk uses a temporary vars file and no -bios', async () => {
    const vmid = await createVm({ bios: 'ovmf', memory: 512, name: 'x86-ovmf-no-efidisk' })

    const cmd = await showcmd(vmid)
    expect(cmd).toContain('WARN: no efidisk configured! Using temporary efivars disk.')
    expectPflash(cmd, 'OVMF_CODE.fd', `/run/qemu-server/efidisk/${vmid}-ovmf.fd`)
    expect(cmd).toContain("-machine 'pflash0=pflash0,pflash1=drive-efidisk0,type=pc+pve0'")

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)

    expect(cmd).not.toMatch(BIOS_ARG)
  })

  test('aarch64: OVMF (AAVMF) with an efidisk starts, without -bios', async () => {
    // OVMF is the only firmware for `virt`. A serial console: aarch64's default display (virtio-gpu)
    // comes with SPICE, whose TLS port and vdagent chardev qemuAccepts can't start without a node.
    const vmid = await createVm({
      arch: 'aarch64',
      bios: 'ovmf',
      efidisk0: 'local:1',
      memory: 512,
      name: 'arm-ovmf',
      serial0: 'socket',
      vga: 'serial0',
    })

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-aarch64 \\$/m)
    expectPflash(cmd, 'AAVMF_CODE.fd', `/var/lib/vz/images/${vmid}/vm-${vmid}-disk-0.raw`)
    expect(cmd).toContain("-machine 'pflash0=pflash0,pflash1=drive-efidisk0,accel=tcg,type=virt+pve0'")

    expect(cmd).not.toMatch(BIOS_ARG)
    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })
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

  test('the API keeps arch and refuses to change it', async () => {
    // Before the sparc32 profiles: `arch` was enum x86_64/aarch64 (pve-qm-cpu-arch), so the API
    // refused sparc/sparc64 outright, and changing an existing VM's arch was not refused.
    await pve.post(`/nodes/${NODE}/qemu/${vmid}/config`, { arch: 'sparc' })
    expect(await vmConfFile(vmid)).toMatch(/^arch: sparc$/m)

    const refused = await pve.refused('POST', `/nodes/${NODE}/qemu/${vmid}/config`, { arch: 'sparc64' })
    expect(refused.message).toContain("the architecture of an existing VM can't be changed (it is 'sparc')")
    expect(await vmConfFile(vmid)).toMatch(/^arch: sparc$/m)
  })

  test("the lance NIC uses the config's MAC address", async () => {
    // Before the sparc32 profiles: macaddr=08:00:20:b5:09:67 was hardcoded for lance, so every
    // sparc32 VM on a bridge had the same MAC.
    expect(await showcmd(vmid)).toContain("-net 'nic,model=lance,macaddr=BC:24:11:B2:46:01'")
  })
})

test.describe('sparc, created through the API', () => {
  // Before the sparc32 profiles: the API refused `arch: sparc|sparc64`. These also check the
  // defaults: a sparc VM created without tablet/balloon settings must not get a usb-tablet or
  // virtio-balloon, which sparc32 doesn't have (and sparc64 has no USB bus for), nor a vmgenid.

  test('sparc32 (SS-5) with cg3 and lance starts', async () => {
    const vmid = await createVm({ arch: 'sparc', memory: 256, name: 'sparc32', net0: 'lance,bridge=vmbr0', vga: 'cg3' })

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc \\$/m)
    expect(cmd).toContain('type=SS-5')
    for (const device of ['usb-tablet', 'virtio-balloon', 'vmgenid']) expect(cmd).not.toContain(device)

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('sparc64 (sun4u) with sunhme starts', async () => {
    const vmid = await createVm({ arch: 'sparc64', memory: 512, name: 'sparc64', net0: 'sunhme,bridge=vmbr0' })

    const cmd = await showcmd(vmid)
    expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc64 \\$/m)
    expect(cmd).toContain('type=sun4u')
    for (const device of ['usb-tablet', 'vmgenid']) expect(cmd).not.toContain(device)

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })
})
