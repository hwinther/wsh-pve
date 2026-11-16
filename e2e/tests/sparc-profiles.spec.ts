import { expect, type Page, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

import {
  hasSparc32Smp,
  hasSparc32SmpUi,
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

// The sparc32 profiles (submodules/SPARC.md, "Supported profiles"): the machine, firmware, CPU and
// RAM combinations qemu-server accepts for `arch: sparc` and builds the command for, the ones it
// refuses, the wizard that offers only them, and backup/restore of such a VM.

interface Profile {
  name: string
  machine: string
  bios: string
  /** the -cpu the profile needs (none: the machine's default) */
  cpu?: string
  memory: number
  /** the wizard's firmware entries for the machine, and the one to pick */
  firmwareOffered: string[]
  firmwarePick: string
  /** -bios when created through the wizard (none for the default, OpenBIOS) */
  wizardBios?: string
  /** the most CPUs (sockets x cores) it takes */
  maxCpus: number
}

const SS5_OPENBIOS: Profile = {
  bios: 'openbios-sparc32',
  firmwareOffered: ['Default (OpenBIOS)', 'SPARCstation 5 PROM'],
  firmwarePick: 'Default (OpenBIOS)',
  machine: 'SS-5',
  maxCpus: 1,
  memory: 256,
  name: 'ss5-openbios',
}
const SS20_PROM: Profile = {
  bios: 'ss20_v2.25_rom',
  cpu: 'TI-SuperSparc-50',
  firmwareOffered: ['Default (OpenBIOS)', 'SPARCstation 20 PROM'],
  firmwarePick: 'SPARCstation 20 PROM',
  machine: 'SS-20',
  maxCpus: 1,
  memory: 512,
  name: 'ss20-prom',
  wizardBios: 'ss20_v2.25_rom',
}
const PROFILES: Profile[] = [
  SS5_OPENBIOS,
  {
    bios: 'ss5.bin',
    firmwareOffered: ['Default (OpenBIOS)', 'SPARCstation 5 PROM'],
    firmwarePick: 'SPARCstation 5 PROM',
    machine: 'SS-5',
    maxCpus: 1,
    memory: 256,
    name: 'ss5-prom',
    wizardBios: 'ss5.bin',
  },
  {
    bios: 'openbios-sparc32',
    firmwareOffered: ['Default (OpenBIOS)'],
    firmwarePick: 'Default (OpenBIOS)',
    machine: 'SS-10',
    maxCpus: 4,
    memory: 512,
    name: 'ss10-openbios',
  },
  {
    bios: 'openbios-sparc32',
    firmwareOffered: ['Default (OpenBIOS)', 'SPARCstation 20 PROM'],
    firmwarePick: 'Default (OpenBIOS)',
    machine: 'SS-20',
    maxCpus: 4,
    memory: 512,
    name: 'ss20-openbios',
  },
  SS20_PROM,
]

/** The value of a QEMU option in `qm showcmd --pretty` output, if it is there. */
function arg(cmd: string, option: string): string | undefined {
  return new RegExp(String.raw`^\s*${option} (\S+)`, 'm').exec(cmd)?.[1]
}

const ISO_NAME = 'e2e-sparc.iso'
const ISO = `local:iso/${ISO_NAME}`

let pve: Pve
/** the installed qemu-server and pve-manager have the CPU limits per profile ("more than one CPU") */
let smp: boolean
let ui: boolean

test.beforeAll(async () => {
  smp = await hasSparc32Smp()
  ui = await hasSparc32SmpUi()
  // An empty "install CD" for target 6.
  const { code, output } = await pveExec([
    'sh',
    '-c',
    `mkdir -p /var/lib/vz/template/iso && truncate -s 1M /var/lib/vz/template/iso/${ISO_NAME}`,
  ])
  expect(code, output).toBe(0)
})

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  const vms = await pve.get<{ status: string; vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { status, vmid } of vms) {
    if (status === 'running') await qm(['stop', String(vmid)])
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

/** Runs `qm <args>` in the container and expects it to succeed. */
async function qm(args: string[]): Promise<string> {
  const { code, output } = await pveExec(['qm', ...args])
  expect(code, `qm ${args.join(' ')}: ${output}`).toBe(0)
  return output
}

function profileParams(p: Profile, extra: Record<string, number | string> = {}): Record<string, number | string> {
  return {
    arch: 'sparc',
    bios: p.bios,
    machine: p.machine,
    memory: p.memory,
    name: `sparc-${p.name}`,
    net0: 'lance,bridge=vmbr0',
    ostype: 'solaris',
    scsi3: 'local:0.0625,format=raw',
    scsi6: `${ISO},media=cdrom`,
    ...extra,
  }
}

const MAC = /^net0: lance=([\dA-F:]+),bridge=vmbr0/m

test.describe('profiles, created through the API', () => {
  for (const p of PROFILES) {
    test(`${p.name}: ${p.machine}, ${p.bios}, ${p.memory} MB`, async () => {
      const vmid = await createVm(profileParams(p))
      const conf = await vmConfFile(vmid)
      const mac = MAC.exec(conf)?.[1]
      expect(mac, conf).toBeDefined()

      const cmd = await showcmd(vmid)
      expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-sparc \\$/m)
      expect(cmd).toContain(`-machine 'accel=tcg,type=${p.machine}+pve0'`)
      expect(cmd).toContain(`-bios ${p.bios}`)
      expect(cmd).toContain(`-m ${p.memory}`)
      expect(cmd).toContain("-smp '1,sockets=1,cores=1,maxcpus=1'")
      expect(arg(cmd, '-cpu')).toBe(p.cpu)
      expect(cmd).toContain('-vga cg3')
      expect(cmd).toContain(`-net 'nic,model=lance,macaddr=${mac}`)
      expect(cmd).toContain("-device 'scsi-hd,channel=0,scsi-id=3,lun=0,drive=drive-scsi3,")
      expect(cmd).toMatch(/-device 'scsi-cd,channel=0,scsi-id=6,lun=0,drive=drive-scsi6,[^']*physical_block_size=512'/)
      for (const device of ['usb-tablet', 'virtio-balloon', 'vmgenid', 'isa-serial']) expect(cmd).not.toContain(device)

      const qemu = await qemuAccepts(vmid)
      expect(qemu.code, qemu.output).toBe(0)
    })
  }

  test('the defaults: SS-5, OpenBIOS, cg3, no -bios or -cpu', async () => {
    const vmid = await createVm({ arch: 'sparc', memory: 256, name: 'sparc-defaults', net0: 'lance,bridge=vmbr0' })

    const cmd = await showcmd(vmid)
    expect(cmd).toContain("-machine 'accel=tcg,type=SS-5+pve0'")
    expect(cmd).toContain('-vga cg3')
    for (const arg of ['-bios', '-cpu', 'usb-tablet', 'virtio-balloon', 'vmgenid']) expect(cmd).not.toContain(arg)

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('a serial console on ttya (vga serial0)', async () => {
    const vmid = await createVm({
      arch: 'sparc',
      machine: 'SS-20',
      memory: 512,
      name: 'sparc-serial',
      serial0: 'socket',
      vga: 'serial0',
    })

    const cmd = await showcmd(vmid)
    expect(cmd).toContain(`-chardev 'socket,id=serial0,path=/var/run/qemu-server/${vmid}.serial0,server=on,wait=off'`)
    expect(cmd).toContain('-serial chardev:serial0')
    expect(cmd).not.toContain('isa-serial')

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('an install CD copied to a read-only disk on target 6 answers as a disk', async () => {
    // How Solaris 2.4/2.5.1 boot their installer: the ISO as a disk image, not a CD-ROM.
    const vmid = await createVm({
      arch: 'sparc',
      memory: 256,
      name: 'sparc-cdhd',
      scsi3: 'local:0.0625,format=raw',
      scsi6: 'local:0.0625,format=raw,ro=1,backup=0',
    })

    const cmd = await showcmd(vmid)
    expect(cmd).toContain("-device 'scsi-hd,channel=0,scsi-id=6,lun=0,drive=drive-scsi6,")
    expect(cmd).toMatch(/"node-name":"drive-scsi6","read-only":true/)

    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })
})

test.describe('refused combinations', () => {
  const cases: { name: string; params: Record<string, number | string>; message: string }[] = [
    {
      message:
        "sparc: firmware (bios) 'ss20_v2.25_rom' is not supported on SS-5, use one of: openbios-sparc32, ss5.bin",
      name: 'the firmware of another machine',
      params: { bios: 'ss20_v2.25_rom', machine: 'SS-5', memory: 256 },
    },
    {
      message:
        "sparc: firmware (bios) 'ss5.bin' is not supported on SS-20, use one of: openbios-sparc32, ss20_v2.25_rom",
      name: 'the SS-5 PROM on SS-20',
      params: { bios: 'ss5.bin', machine: 'SS-20', memory: 512 },
    },
    {
      message:
        "sparc: firmware (bios) 'ss10_v2.25_rom' is not supported on SS-10 (the SS-10 PROM doesn't run on QEMU's SS-10; ss20_v2.25_rom runs on SS-20), use one of: openbios-sparc32",
      name: 'the SS-10 PROM',
      params: { bios: 'ss10_v2.25_rom', machine: 'SS-10', memory: 256 },
    },
    {
      message: 'sparc: SS-5 takes at most 256 MB of memory, not 512',
      name: 'more memory than SS-5 takes',
      params: { machine: 'SS-5', memory: 512 },
    },
    {
      message: 'sparc: SS-5 takes at most 256 MB of memory, not 512',
      name: 'the default memory (512 MB) on SS-5',
      params: {},
    },
    {
      message: 'sparc: SS-20 takes at most 512 MB of memory, not 1024',
      name: 'more memory than SS-20 takes',
      params: { machine: 'SS-20', memory: 1024 },
    },
    {
      message: "sparc: machine 'SS-4' is not supported, use one of: SS-10, SS-20, SS-5",
      name: 'a machine without a profile',
      params: { machine: 'SS-4', memory: 256 },
    },
    {
      message: "sparc: 'cpu' can't be set, the CPU follows the machine and firmware",
      name: 'an x86 CPU type',
      params: { cpu: 'x86-64-v2-AES', memory: 256 },
    },
    {
      message: "sparc: display (vga) 'std' is not supported, use one of: cg3, tcx, none, serial0, serial1",
      name: 'a display sparc32 does not have',
      params: { memory: 256, vga: 'std' },
    },
    {
      message: 'sparc: only one network device is supported (the built-in lance), not net0, net1',
      name: 'a second NIC',
      params: { memory: 256, net0: 'lance,bridge=vmbr0', net1: 'lance,bridge=vmbr0' },
    },
    {
      message: "sparc: network device model 'e1000' is not supported, use lance",
      name: 'a NIC other than lance',
      params: { memory: 256, net0: 'e1000,bridge=vmbr0' },
    },
    {
      message: 'sparc: the QEMU guest agent is not supported',
      name: 'the guest agent',
      params: { agent: 1, memory: 256 },
    },
  ]

  for (const c of cases) {
    test(`create: ${c.name}`, async () => {
      const vmid = Number(await pve.get<string>('/cluster/nextid'))
      const refused = await pve.refused('POST', `/nodes/${NODE}/qemu`, { arch: 'sparc', vmid, ...c.params })
      expect(refused.message).toContain(c.message)
      const { code } = await pveExec(['test', '-e', `/etc/pve/qemu-server/${vmid}.conf`])
      expect(code, 'no config is left behind').not.toBe(0)
    })
  }

  test('update: the result must still match a profile', async () => {
    const vmid = await createVm({ arch: 'sparc', memory: 256, name: 'sparc-update' })
    const config = `/nodes/${NODE}/qemu/${vmid}/config`

    expect((await pve.refused('PUT', config, { memory: 512 })).message).toContain(
      'sparc: SS-5 takes at most 256 MB of memory, not 512',
    )
    expect((await pve.refused('POST', config, { bios: 'ss20_v2.25_rom' })).message).toContain(
      "sparc: firmware (bios) 'ss20_v2.25_rom' is not supported on SS-5",
    )

    // Machine, firmware and memory together make a valid SS-20 PROM profile.
    await pve.post(config, { bios: 'ss20_v2.25_rom', machine: 'SS-20', memory: 512 })
    const conf = await vmConfFile(vmid)
    for (const line of ['bios: ss20_v2.25_rom', 'machine: SS-20', 'memory: 512']) expect(conf).toContain(line)
    expect(await showcmd(vmid)).toContain('-cpu TI-SuperSparc-50')

    // Back to SS-5 only with the memory and firmware that fit it.
    expect((await pve.refused('PUT', config, { machine: 'SS-5' })).message).toContain(
      "sparc: firmware (bios) 'ss20_v2.25_rom' is not supported on SS-5",
    )
  })

  test('arch: set on create only, for sparc and x86 alike', async () => {
    const sparc = await createVm({ arch: 'sparc', memory: 256, name: 'sparc-arch' })
    const x86 = await createVm({ memory: 512, name: 'x86-arch' })

    for (const [vmid, current, other] of [
      [sparc, 'sparc', 'x86_64'],
      [sparc, 'sparc', 'sparc64'],
      [x86, 'x86_64', 'aarch64'],
      [x86, 'x86_64', 'sparc'],
    ] as const) {
      const refused = await pve.refused('POST', `/nodes/${NODE}/qemu/${vmid}/config`, { arch: other })
      expect(refused.message).toContain(`the architecture of an existing VM can't be changed (it is '${current}')`)
    }
    // Deleting it would make a sparc VM x86_64.
    const deleted = await pve.refused('POST', `/nodes/${NODE}/qemu/${sparc}/config`, { delete: 'arch' })
    expect(deleted.message).toContain("the architecture of an existing VM can't be changed (it is 'sparc')")

    // The same value is no change.
    await pve.post(`/nodes/${NODE}/qemu/${x86}/config`, { arch: 'x86_64' })
    expect(await vmConfFile(x86)).toMatch(/^arch: x86_64$/m)
    expect(await vmConfFile(sparc)).toMatch(/^arch: sparc$/m)
  })

  test('an existing config outside the profiles stays readable, but neither starts nor changes', async () => {
    const vmid = 908
    await writeConfFile(vmid, ['arch: sparc', 'machine: SS-5', 'memory: 512', 'name: sparc-toobig'])

    const conf = await pve.get<Record<string, number | string>>(`/nodes/${NODE}/qemu/${vmid}/config`)
    expect(String(conf.memory)).toBe('512')
    const vms = await pve.get<{ vmid: number }[]>(`/nodes/${NODE}/qemu`)
    expect(vms.map((v) => v.vmid)).toContain(vmid)
    await qm(['config', String(vmid)])

    const show = await pveExec(['qm', 'showcmd', String(vmid)])
    expect(show.code).not.toBe(0)
    expect(show.output).toContain('sparc: SS-5 takes at most 256 MB of memory, not 512')
    const start = await pveExec(['qm', 'start', String(vmid)])
    expect(start.code).not.toBe(0)
    expect(start.output).toContain('sparc: SS-5 takes at most 256 MB of memory, not 512')

    expect((await pve.refused('PUT', `/nodes/${NODE}/qemu/${vmid}/config`, { name: 'renamed' })).message).toContain(
      'sparc: SS-5 takes at most 256 MB of memory, not 512',
    )
    // The change that fixes it is accepted.
    await pve.post(`/nodes/${NODE}/qemu/${vmid}/config`, { memory: 256, name: 'renamed' })
    expect(await showcmd(vmid)).toContain('-m 256')
  })
})

test.describe('backup and restore', () => {
  /** Fills the first 4 MB of the VM's scsi3 disk with random data, returns the image's sha256. */
  async function fillDisk(vmid: number): Promise<string> {
    const { code, output } = await pveExec([
      'sh',
      '-c',
      `p=$(pvesm path local:${vmid}/vm-${vmid}-disk-0.raw) && dd if=/dev/urandom of="$p" bs=1M count=4 conv=notrunc status=none && sha256sum "$p"`,
    ])
    expect(code, output).toBe(0)
    return output.split(' ')[0] ?? ''
  }

  async function diskSum(vmid: number): Promise<string> {
    const { code, output } = await pveExec([
      'sh',
      '-c',
      `sha256sum "$(pvesm path local:${vmid}/vm-${vmid}-disk-0.raw)"`,
    ])
    expect(code, output).toBe(0)
    return output.split(' ')[0] ?? ''
  }

  async function vzdump(vmid: number, mode: 'snapshot' | 'stop'): Promise<string> {
    const { code, output } = await pveExec(['vzdump', String(vmid), '--mode', mode, '--storage', 'local'])
    expect(code, output).toBe(0)
    expect(output).toContain(`backup mode: ${mode}`)
    expect(output).not.toContain('guest-agent')
    const archive = /creating vzdump archive '([^']+)'/.exec(output)?.[1]
    expect(archive, output).toBeDefined()
    return archive ?? ''
  }

  async function restore(archive: string): Promise<number> {
    const vmid = Number(await pve.get<string>('/cluster/nextid'))
    const { code, output } = await pveExec(['qmrestore', archive, String(vmid), '--storage', 'local'])
    expect(code, output).toBe(0)
    return vmid
  }

  /** The config without the disk line (its volume names the VMID) and the digest-like lines. */
  async function comparableConf(vmid: number): Promise<string[]> {
    return (await vmConfFile(vmid))
      .split('\n')
      .map((l) => l.trimEnd())
      .filter((l) => l && !l.startsWith('scsi3:'))
  }

  for (const p of PROFILES) {
    test(`${p.name}: stop mode, restored to a new VMID`, async () => {
      const vmid = await createVm(profileParams(p, { scsi6: 'none,media=cdrom' }))
      const sum = await fillDisk(vmid)

      const archive = await vzdump(vmid, 'stop')
      const restored = await restore(archive)

      expect(await comparableConf(restored)).toEqual(await comparableConf(vmid))
      expect(await vmConfFile(restored)).toContain(`scsi3: local:${restored}/vm-${restored}-disk-0.raw`)
      expect(await diskSum(restored)).toBe(sum)
      expect(await showcmd(restored)).toContain(`type=${p.machine}+pve0`)
    })
  }

  test('snapshot mode of a running VM (QEMU started, no guest OS)', async () => {
    const vmid = await createVm(profileParams(SS5_OPENBIOS, { scsi6: 'none,media=cdrom' }))
    const sum = await fillDisk(vmid)
    await qm(['start', String(vmid)])

    const archive = await vzdump(vmid, 'snapshot')
    expect(await qm(['status', String(vmid)])).toContain('status: running')
    await qm(['stop', String(vmid)])

    const restored = await restore(archive)
    expect(await diskSum(restored)).toBe(sum)
  })

  for (const p of [SS5_OPENBIOS, SS20_PROM]) {
    test(`${p.name}: a snapshot with RAM, rolled back`, async () => {
      const vmid = await createVm(profileParams(p, { scsi3: 'local:0.0625,format=qcow2', scsi6: 'none,media=cdrom' }))
      await qm(['start', String(vmid)])

      await qm(['snapshot', String(vmid), 'withram', '--vmstate', '1'])
      const conf = await vmConfFile(vmid)
      const section = conf.slice(conf.indexOf('[withram]'))
      expect(section).toMatch(/^vmstate: local:\d+\/vm-\d+-state-withram\.raw$/m)
      expect(section).toContain(`runningmachine: ${p.machine}+pve0`)
      expect(/^runningcpu: (\S+)$/m.exec(section)?.[1]).toBe(p.cpu)

      await qm(['stop', String(vmid)])
      await qm(['rollback', String(vmid), 'withram'])
      expect(await qm(['status', String(vmid)])).toContain('status: running')
    })
  }
})

// More than one CPU (submodules/SPARC.md, "SMP"): SS-10 and SS-20 with OpenBIOS take up to 4, the
// SS-20 PROM and SS-5 one. Needs qemu-server and pve-manager with the CPU limits per profile.
// TODO: drop the test.fail(!smp) and test.fail(!(ui && smp)) markers in this block, and the probes
// hasSparc32Smp/hasSparc32SmpUi in _pve.ts, once both packages with the limits are published.
test.describe('more than one CPU', () => {
  const SS10_OPENBIOS = PROFILES.find((p) => p.name === 'ss10-openbios') as Profile
  const SS20_OPENBIOS = PROFILES.find((p) => p.name === 'ss20-openbios') as Profile

  const accepted: { name: string; profile: Profile; sockets: number; cores: number }[] = [
    { cores: 1, name: 'SS-20, OpenBIOS, 2 CPUs (2 sockets)', profile: SS20_OPENBIOS, sockets: 2 },
    { cores: 2, name: 'SS-20, OpenBIOS, 4 CPUs (2 sockets x 2 cores)', profile: SS20_OPENBIOS, sockets: 2 },
    { cores: 4, name: 'SS-10, OpenBIOS, 4 CPUs (4 cores)', profile: SS10_OPENBIOS, sockets: 1 },
  ]
  for (const c of accepted) {
    test(`${c.name}: qm showcmd, and QEMU accepts it`, async () => {
      test.fail(!smp, 'qemu-server without the sparc32 CPU limits')
      const vmid = await createVm(profileParams(c.profile, { cores: c.cores, sockets: c.sockets }))
      const n = c.sockets * c.cores

      const cmd = await showcmd(vmid)
      expect(cmd).toContain(`-smp '${n},sockets=${c.sockets},cores=${c.cores},maxcpus=${n}'`)
      expect(cmd).toContain(`-machine 'accel=tcg,type=${c.profile.machine}+pve0'`)
      // QEMU's default of one thread per vCPU, no CPU devices to hot-plug, and no idle option:
      // solaris-idle/sunos-idle are QEMU's defaults and switch themselves off with more than one CPU
      for (const absent of ['thread=single', '-accel', 'solaris-idle', 'sunos-idle', '-cpu'])
        expect(cmd).not.toContain(absent)
      expect(cmd).not.toMatch(/-device '[^']*-cpu,/)

      const qemu = await qemuAccepts(vmid)
      expect(qemu.code, qemu.output).toBe(0)
    })
  }

  const refused: { name: string; params: Record<string, number | string>; message: string }[] = [
    {
      message: 'sparc: SS-20 with firmware openbios-sparc32 takes at most 4 CPUs (sockets x cores), not 5',
      name: '5 CPUs on SS-20',
      params: { cores: 5, machine: 'SS-20', memory: 512 },
    },
    {
      message: 'sparc: SS-10 with firmware openbios-sparc32 takes at most 4 CPUs (sockets x cores), not 6',
      name: '6 CPUs (3 sockets x 2 cores) on SS-10',
      params: { cores: 2, machine: 'SS-10', memory: 512, sockets: 3 },
    },
    {
      message:
        'sparc: SS-20 with firmware ss20_v2.25_rom takes at most 1 CPU (sockets x cores), not 2 (the Sun PROM starts only the first CPU; openbios-sparc32 takes up to 4)',
      name: '2 CPUs with the SS-20 PROM',
      params: { bios: 'ss20_v2.25_rom', machine: 'SS-20', memory: 512, sockets: 2 },
    },
    {
      message: 'sparc: SS-5 with firmware openbios-sparc32 takes at most 1 CPU (sockets x cores), not 2',
      name: '2 CPUs on SS-5',
      params: { cores: 2, machine: 'SS-5', memory: 256 },
    },
    {
      message: 'sparc: SS-5 with firmware ss5.bin takes at most 1 CPU (sockets x cores), not 2',
      name: '2 CPUs on SS-5 with its PROM',
      params: { bios: 'ss5.bin', machine: 'SS-5', memory: 256, sockets: 2 },
    },
    {
      message: "sparc: CPU hotplug is not supported, remove 'cpu' from 'hotplug'",
      name: 'CPU hotplug',
      params: { cores: 2, hotplug: 'network,disk,cpu', machine: 'SS-20', memory: 512 },
    },
    {
      message: "sparc: 'vcpus' must be the number of CPUs (sockets x cores, 4), not 2; CPU hotplug is not supported",
      name: 'fewer vcpus than CPUs',
      params: { cores: 4, machine: 'SS-20', memory: 512, vcpus: 2 },
    },
  ]
  for (const c of refused) {
    test(`create refused: ${c.name}`, async () => {
      test.fail(!smp, 'qemu-server without the sparc32 CPU limits')
      const vmid = Number(await pve.get<string>('/cluster/nextid'))
      const r = await pve.refused('POST', `/nodes/${NODE}/qemu`, { arch: 'sparc', vmid, ...c.params })
      expect(r.message).toContain(c.message)
      const { code } = await pveExec(['test', '-e', `/etc/pve/qemu-server/${vmid}.conf`])
      expect(code, 'no config is left behind').not.toBe(0)
    })
  }

  test('update: the CPU count follows the machine and firmware', async () => {
    test.fail(!smp, 'qemu-server without the sparc32 CPU limits')
    const ss5 = await createVm({ arch: 'sparc', memory: 256, name: 'sparc-ss5-cpus' })
    expect((await pve.refused('PUT', `/nodes/${NODE}/qemu/${ss5}/config`, { cores: 2 })).message).toContain(
      'sparc: SS-5 with firmware openbios-sparc32 takes at most 1 CPU (sockets x cores), not 2',
    )

    const vmid = await createVm(profileParams(SS20_OPENBIOS))
    const config = `/nodes/${NODE}/qemu/${vmid}/config`
    await pve.put(config, { cores: 2, sockets: 2 })
    expect(await showcmd(vmid)).toContain("-smp '4,sockets=2,cores=2,maxcpus=4'")
    expect((await pve.refused('PUT', config, { cores: 5, sockets: 1 })).message).toContain('takes at most 4 CPUs')
    // the PROM only with one CPU again
    expect((await pve.refused('PUT', config, { bios: 'ss20_v2.25_rom' })).message).toContain(
      'sparc: SS-20 with firmware ss20_v2.25_rom takes at most 1 CPU (sockets x cores), not 4',
    )
    await pve.put(config, { bios: 'ss20_v2.25_rom', delete: 'cores,sockets' })
    expect(await showcmd(vmid)).toContain("-smp '1,sockets=1,cores=1,maxcpus=1'")
  })

  test('a running VM: a CPU count change stays pending until the next start', async () => {
    test.fail(!smp, 'qemu-server without the sparc32 CPU limits')
    const vmid = await createVm(profileParams(SS20_OPENBIOS, { scsi6: 'none,media=cdrom' }))
    const cpus = async () => pve.post<string>(`/nodes/${NODE}/qemu/${vmid}/monitor`, { command: 'info cpus' })
    await qm(['start', String(vmid)])
    await pve.put(`/nodes/${NODE}/qemu/${vmid}/config`, { cores: 2 })
    const pending = await pve.get<{ key: string; pending?: number | string }[]>(`/nodes/${NODE}/qemu/${vmid}/pending`)
    expect(String(pending.find((e) => e.key === 'cores')?.pending)).toBe('2')
    expect(await cpus()).not.toMatch(/CPU #1/)

    await qm(['stop', String(vmid)])
    await qm(['start', String(vmid)])
    expect(await cpus()).toMatch(/CPU #1/)
  })

  test.describe('web UI', () => {
    test.beforeEach(async ({ page }) => {
      await login(page)
    })

    test('create wizard: sockets and cores per machine and firmware, capped', async ({ page }) => {
      test.fail(!(ui && smp), 'pve-manager/qemu-server without the sparc32 CPU limits')
      const vmid = Number(await pve.get<string>('/cluster/nextid'))
      const wizard = await openWizard(page, 'sparc-ui-smp')
      const sockets = wizard.getByLabel(fieldLabel('Sockets'))
      const cores = wizard.getByLabel(fieldLabel('Cores'))
      const nextButton = wizard.getByRole('button', { name: 'Next' })
      const back = async () => wizard.getByRole('button', { name: 'Back' }).click()

      await pickCombo(page, wizard, 'vCPU Architecture', 'SPARC (32-bit)')
      await next(wizard)
      await wizard.getByText('Do not use any media').click()
      await pickCombo(page, wizard, 'Type', 'Solaris Kernel')
      await next(wizard)

      // SS-20 with OpenBIOS: up to 4
      await pickCombo(page, wizard, 'Machine', 'SS-20')
      await next(wizard) // to Disks
      await next(wizard) // to CPU
      await expect(sockets).toBeEnabled()
      await expect(cores).toBeEnabled()
      await expect(wizard.getByText(/up to 4 CPUs .*keeps a host core busy/)).toBeVisible()
      await cores.fill('5')
      await expect(nextButton).toBeDisabled()
      await cores.fill('2')
      await sockets.fill('3')
      await expect(nextButton).toBeDisabled()
      await sockets.fill('2')
      await expect(nextButton).toBeEnabled()

      // the SS-20 PROM: one CPU, the fields reset and disabled
      await back() // Disks
      await back() // System
      await pickCombo(page, wizard, 'BIOS', 'SPARCstation 20 PROM')
      await next(wizard)
      await next(wizard)
      await expect(sockets).toBeDisabled()
      await expect(cores).toBeDisabled()
      await expect(sockets).toHaveValue('1')
      await expect(cores).toHaveValue('1')

      // back to OpenBIOS, 4 cores
      await back()
      await back()
      await pickCombo(page, wizard, 'BIOS', 'Default (OpenBIOS)')
      await next(wizard)
      await next(wizard)
      await expect(cores).toBeEnabled()
      await cores.fill('4')
      await next(wizard) // to Memory
      await next(wizard) // to Network
      await next(wizard) // to Confirm
      await wizard.getByRole('button', { name: 'Finish' }).click()
      await expect.poll(async () => (await pveExec(['test', '-e', `/etc/pve/qemu-server/${vmid}.conf`])).code).toBe(0)
      await expect.poll(async () => (await vmConfFile(vmid)).includes('lock: create'), { timeout: 30_000 }).toBe(false)

      const conf = await vmConfFile(vmid)
      expect(conf).toMatch(/^cores: 4$/m)
      expect(conf).not.toMatch(/^(vcpus|bios):/m)
      const cmd = await showcmd(vmid)
      expect(cmd).toContain("-smp '4,sockets=1,cores=4,maxcpus=4'")
      const qemu = await qemuAccepts(vmid)
      expect(qemu.code, qemu.output).toBe(0)
    })

    test('Hardware: Processors enabled and capped only where the profile takes more than one', async ({ page }) => {
      test.fail(!(ui && smp), 'pve-manager/qemu-server without the sparc32 CPU limits')
      const ss20 = await createVm(profileParams(SS20_OPENBIOS))
      const prom = await createVm(profileParams(SS20_PROM))
      const editor = page.locator('.x-window').filter({ hasText: 'Edit: Processors' })
      const openProcessors = async (vmid: number) => {
        await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
        await page.reload() // the resource tree learns about VMs created after login only on a reload
        await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()
        await page.getByText(/^Processors$/).dblclick()
        await expect(editor).toBeVisible()
      }

      await openProcessors(ss20)
      await expect(editor.getByLabel(fieldLabel('Sockets'))).toBeEnabled()
      await expect(editor.getByLabel(fieldLabel('Cores'))).toBeEnabled()
      await editor.getByLabel(fieldLabel('Cores')).fill('5')
      await expect(editor.getByRole('button', { name: 'OK' })).toBeDisabled()
      await editor.getByLabel(fieldLabel('Cores')).fill('2')
      await editor.getByRole('button', { name: 'OK' }).click()
      await expect(editor).toBeHidden()
      await expect.poll(async () => vmConfFile(ss20)).toMatch(/^cores: 2$/m)

      await openProcessors(prom)
      await expect(editor.getByLabel(fieldLabel('Sockets'))).toBeDisabled()
      await expect(editor.getByLabel(fieldLabel('Cores'))).toBeDisabled()
      await expect(editor.getByText(/one CPU on this machine and firmware/)).toBeVisible()
      await closeWindow(editor)
    })
  })
})

test.describe('the lab runs the same machines', () => {
  // e2e/sparc measures the profiles with its own QEMU command (scenarios/_sparc32.py). If the
  // machine-defining arguments drift apart, the measurements no longer describe what qemu-server runs.
  const lab = readFileSync(new URL('../sparc/scenarios/_sparc32.py', import.meta.url), 'utf8')
  const matrix = readFileSync(new URL('../sparc/matrix.py', import.meta.url), 'utf8')

  interface LabMachine {
    BIOS: string
    CPU?: string
    MACHINE: string
    MEM: string
    VGA: string
  }

  /** The lab's variables; an empty CPU means the machine's default, like a missing -cpu. */
  function labMachine(vars: Record<string, string>): LabMachine {
    const { BIOS = '', CPU = '', MACHINE = '', MEM = '', VGA = '' } = vars
    return { BIOS, CPU: CPU.length > 0 ? CPU : undefined, MACHINE, MEM, VGA }
  }

  /** A Python dict of string literals in the lab's source, e.g. `SS20PROM = {"MACHINE": ...}`. */
  function dict(source: string, name: string): Record<string, string> {
    const body = new RegExp(`${name} = \\{([^}]*)\\}`).exec(source)?.[1] ?? ''
    return Object.fromEntries([...body.matchAll(/"(\w+)": "([^"]*)"/g)].map((m) => [m[1], m[2]]))
  }

  test("qm showcmd has the lab's machine, firmware, CPU and device layout", async () => {
    const defaults = labMachine(dict(lab, 'DEFAULTS'))
    const ss20prom = labMachine({ ...dict(lab, 'DEFAULTS'), ...dict(matrix, 'SS20PROM') })
    expect(defaults.MACHINE).toBe('SS-5')
    expect(ss20prom.CPU).toBeTruthy()
    for (const layout of [
      'scsi-hd,channel=0,scsi-id=3,lun=0',
      'channel=0,scsi-id=6,lun=0',
      'physical_block_size=512',
    ]) {
      expect(lab).toContain(layout)
    }
    expect(lab).toContain('"nic,model=lance"')

    for (const v of [defaults, ss20prom]) {
      const vmid = await createVm({
        arch: 'sparc',
        bios: v.BIOS,
        machine: v.MACHINE,
        memory: Number(v.MEM),
        name: 'sparc-lab',
        net0: 'lance,bridge=vmbr0',
        scsi3: 'local:0.0625,format=raw',
        scsi6: `${ISO},media=cdrom`,
        vga: v.VGA,
      })
      const cmd = await showcmd(vmid)
      expect(cmd).toContain(`type=${v.MACHINE}+pve0`)
      expect(cmd).toContain(`-bios ${v.BIOS}`)
      expect(cmd).toContain(`-m ${v.MEM}`)
      expect(cmd).toContain(`-vga ${v.VGA}`)
      expect(arg(cmd, '-cpu')).toBe(v.CPU)
      expect(cmd).toContain("-device 'scsi-hd,channel=0,scsi-id=3,lun=0,")
      expect(cmd).toMatch(/-device 'scsi-cd,channel=0,scsi-id=6,lun=0,[^']*physical_block_size=512'/)
      expect(cmd).toContain("-net 'nic,model=lance,")
    }
  })
})

test.describe('web UI', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  for (const p of PROFILES) {
    test(`create wizard: ${p.name}`, async ({ page }) => {
      const vmid = Number(await pve.get<string>('/cluster/nextid'))
      const wizard = await openWizard(page, `sparc-ui-${p.name}`)

      // General: the architecture (an advanced option).
      await pickCombo(page, wizard, 'vCPU Architecture', 'SPARC (32-bit)')
      await next(wizard)

      // OS: no ISO, Solaris.
      await wizard.getByText('Do not use any media').click()
      await pickCombo(page, wizard, 'Type', 'Solaris Kernel')
      await next(wizard)

      // System: SS-5 (the default), SS-10, SS-20, and only the firmware the machine runs.
      expect(await comboOptions(page, wizard, 'Machine')).toEqual(['Default (SS-5)', 'SS-10', 'SS-20'])
      await pickCombo(page, wizard, 'Machine', p.machine)
      expect(await comboOptions(page, wizard, 'BIOS')).toEqual(p.firmwareOffered)
      await pickCombo(page, wizard, 'BIOS', p.firmwarePick)
      await next(wizard)

      // Disks: the first disk on SCSI target 3.
      await expect(wizard.getByText('scsi3', { exact: true })).toBeVisible()
      await next(wizard)

      // CPU: nothing to choose where the profile takes one CPU ("more than one CPU" has the rest).
      // TODO: `p.maxCpus === 1` alone once pve-manager with the CPU limits is published.
      const oneCpu = p.maxCpus === 1 || !ui
      await expect(wizard.getByLabel(fieldLabel('Sockets'))).toBeEnabled({ enabled: !oneCpu })
      await expect(wizard.getByLabel(fieldLabel('Cores'))).toBeEnabled({ enabled: !oneCpu })
      await next(wizard)

      // Memory: preset to and capped at the machine's maximum.
      const memory = wizard.getByLabel(fieldLabel('Memory (MiB)'))
      await expect(memory).toHaveValue(String(p.memory))
      await memory.fill(String(p.memory * 2))
      await expect(wizard.getByRole('button', { name: 'Next' })).toBeDisabled()
      await memory.fill(String(p.memory))
      await next(wizard)

      // Network: the built-in lance.
      await expect(wizard.getByLabel(fieldLabel('Model'))).toHaveValue(/Lance/)
      await next(wizard)

      await wizard.getByRole('button', { name: 'Finish' }).click()
      await expect.poll(async () => (await pveExec(['test', '-e', `/etc/pve/qemu-server/${vmid}.conf`])).code).toBe(0)
      await expect.poll(async () => (await vmConfFile(vmid)).includes('lock: create'), { timeout: 30_000 }).toBe(false)

      const conf = await vmConfFile(vmid)
      expect(conf).toMatch(/^arch: sparc$/m)
      expect(conf).toMatch(/^scsi3: local:\d+\/vm-\d+-disk-0/m)
      expect(conf).toMatch(MAC)
      for (const key of ['cpu', 'vmgenid']) expect(conf).not.toMatch(new RegExp(`^${key}:`, 'm'))
      // one CPU: no sockets/cores, or 1 where the fields are enabled (SS-10/SS-20 with OpenBIOS)
      expect(conf).not.toMatch(/^(sockets|cores): (?!1$)/m)

      const cmd = await showcmd(vmid)
      expect(cmd).toContain(`type=${p.machine}+pve0`)
      expect(cmd).toContain(`-m ${p.memory}`)
      expect(arg(cmd, '-bios')).toBe(p.wizardBios)
      expect(arg(cmd, '-cpu')).toBe(p.cpu)
      const qemu = await qemuAccepts(vmid)
      expect(qemu.code, qemu.output).toBe(0)
    })
  }

  test("Hardware: the editors offer only the profile's choices", async ({ page }) => {
    const vmid = await createVm({ arch: 'sparc', memory: 256, name: 'sparc-editors' })
    await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
    await page.reload() // the resource tree learns about VMs created after login only on a reload
    await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()
    const editor = (title: string) => page.locator('.x-window').filter({ hasText: `Edit: ${title}` })

    await page.getByText(/^Display$/).dblclick()
    expect(await comboOptions(page, editor('Display'), 'Graphic card')).toEqual([
      'Default (CG3 framebuffer)',
      'TCX framebuffer',
      'Serial terminal 0',
      'Serial terminal 1',
      'none', // Proxmox.Utils.noneText
    ])
    await closeWindow(editor('Display'))

    await page.getByText(/^Processors$/).dblclick()
    await expect(editor('Processors').getByLabel(fieldLabel('Sockets'))).toBeDisabled()
    await expect(editor('Processors').getByLabel(fieldLabel('Cores'))).toBeDisabled()
    await closeWindow(editor('Processors'))

    await page.getByText(/^Memory$/).dblclick()
    await editor('Memory').getByLabel(fieldLabel('Memory (MiB)')).fill('512')
    await expect(editor('Memory').getByRole('button', { name: 'OK' })).toBeDisabled()
    await closeWindow(editor('Memory'))

    await page.getByText(/^Machine$/).dblclick()
    expect(await comboOptions(page, editor('Machine'), 'Machine')).toEqual(['Default (SS-5)', 'SS-10', 'SS-20'])
    await pickCombo(page, editor('Machine'), 'Machine', 'SS-20')
    await editor('Machine').getByRole('button', { name: 'OK' }).click()
    await expect(editor('Machine')).toBeHidden()
    await expect.poll(async () => vmConfFile(vmid)).toMatch(/^machine: SS-20$/m)
  })

  test('Hardware: the architecture of an existing VM is read-only', async ({ page }) => {
    const vmid = await createVm({ arch: 'sparc', memory: 256, name: 'sparc-hw' })
    await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
    await page.reload() // the resource tree learns about VMs created after login only on a reload
    await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()

    await page.getByText('vCPU Architecture').click()
    await expect(page.getByRole('button', { name: 'Edit' })).toBeDisabled()
    await page.getByRole('button', { name: 'Add' }).click()
    await expect(page.getByRole('menuitem', { name: 'Architecture' })).toHaveCount(0)
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
