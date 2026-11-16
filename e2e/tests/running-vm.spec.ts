import { expect, test } from '@playwright/test'

import { hasRunningSparcFixes, NODE, type Pve, pveApi, pveExec } from './_pve'

// Changes to a RUNNING VM (submodules/SPARC.md, "Operations on a running VM"): the QEMU that PVE
// started, under TCG and without a guest OS. Each sparc32 profile, sparc64 (sun4u) and an x86 VM as
// the control. What works live is checked in QEMU (`info block`, `info network`) and on the host
// (the tap's bridge, VLAN and qdisc); what can't be hot-plugged on sparc must become a pending change.

// TODO: drop the test.fail(!fixed) markers once qemu-server with these fixes is published at
// debian.wshosting.no. The published 9.2.15+wsh3 fails every machine version check of a running
// sparc VM ("cannot check version of invalid string '10'") and can't set the lance's link.
let fixed: boolean

interface Vm {
  name: string
  params: Record<string, number | string>
  /** the CD-ROM drive */
  cd: string
  /** the first disk */
  disk: string
  /** the NIC model in net0 */
  nic: string
  /** a memory size that is a valid change, but not hot-pluggable */
  memory: number
  sparc: boolean
}

const sparc32 = (name: string, machine: string, bios: string, memory: number): Vm => ({
  cd: 'scsi6',
  disk: 'scsi3',
  memory: 128,
  name,
  nic: 'lance',
  params: { arch: 'sparc', bios, machine, memory, ostype: 'solaris', scsi3: 'local:0.0625,format=qcow2' },
  sparc: true,
})

const SS5 = sparc32('sparc32 SS-5 OpenBIOS', 'SS-5', 'openbios-sparc32', 256)
const SUN4U: Vm = {
  cd: 'scsi6',
  disk: 'scsi0',
  memory: 256,
  name: 'sparc64 sun4u',
  nic: 'sunhme',
  params: { arch: 'sparc64', machine: 'sun4u', memory: 512, ostype: 'other', scsi0: 'local:0.0625,format=qcow2' },
  sparc: true,
}
const VMS: Vm[] = [
  SS5,
  sparc32('sparc32 SS-5 PROM', 'SS-5', 'ss5.bin', 256),
  sparc32('sparc32 SS-10 OpenBIOS', 'SS-10', 'openbios-sparc32', 512),
  sparc32('sparc32 SS-20 OpenBIOS', 'SS-20', 'openbios-sparc32', 512),
  sparc32('sparc32 SS-20 PROM', 'SS-20', 'ss20_v2.25_rom', 512),
  SUN4U,
  {
    cd: 'ide2',
    disk: 'scsi0',
    memory: 256,
    name: 'x86 control',
    nic: 'virtio',
    params: { kvm: 0, memory: 512, ostype: 'l26', scsi0: 'local:0.0625,format=qcow2' },
    sparc: false,
  },
]

const ISO_DIR = '/var/lib/vz/template/iso'
const ISO_A = 'e2e-running-a.iso'
const ISO_B = 'e2e-running-b.iso'
// A second, VLAN-aware bridge: a tag on vmbr0 (no physical port) is refused by the host setup.
const BRIDGE2 = 'vmbr1'

let pve: Pve

test.beforeAll(async () => {
  const { code, output } = await pveExec([
    'sh',
    '-c',
    `mkdir -p ${ISO_DIR} && truncate -s 1M ${ISO_DIR}/${ISO_A} ${ISO_DIR}/${ISO_B} &&
     { ip link show ${BRIDGE2} >/dev/null 2>&1 || ip link add ${BRIDGE2} type bridge vlan_filtering 1; } &&
     ip link set ${BRIDGE2} up`,
  ])
  expect(code, output).toBe(0)
  fixed = await hasRunningSparcFixes()
})

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  const vms = await pve.get<{ status: string; vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { status, vmid } of vms) {
    if (status === 'running') await stopVm(vmid)
    await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
  }
})

async function waitTask(upid: string): Promise<void> {
  const path = `/nodes/${NODE}/tasks/${encodeURIComponent(upid)}/status`
  await expect
    .poll(async () => (await pve.get<{ status: string }>(path)).status, { intervals: [250], timeout: 30_000 })
    .toBe('stopped')
  const { exitstatus } = await pve.get<{ exitstatus: string }>(path)
  expect(exitstatus, `task ${upid}`).toBe('OK')
}

/** Creates the VM with a CD in the drive and net0 on vmbr0, and starts it. */
async function startVm(vm: Vm, extra: Record<string, number | string> = {}): Promise<number> {
  const vmid = Number(await pve.get<string>('/cluster/nextid'))
  await waitTask(
    await pve.post<string>(`/nodes/${NODE}/qemu`, {
      name: vm.name.replaceAll(/[^\da-z]+/gi, '-'),
      net0: `${vm.nic},bridge=vmbr0`,
      vmid,
      [vm.cd]: `local:iso/${ISO_A},media=cdrom`,
      ...vm.params,
      ...extra,
    }),
  )
  await qm(['start', String(vmid)])
  return vmid
}

/** Runs `qm <args>` in the container and expects it to succeed. */
async function qm(args: string[]): Promise<string> {
  const { code, output } = await pveExec(['qm', ...args])
  expect(code, `qm ${args.join(' ')}: ${output}`).toBe(0)
  return output
}

/**
 * Stops the VM and waits for the `qm cleanup` that qmeventd runs after QEMU exits: it takes the
 * config lock, and a start or stop right behind it can time out waiting for that lock.
 */
async function stopVm(vmid: number): Promise<void> {
  await qm(['stop', String(vmid)])
  // qmeventd starts it shortly after QEMU is gone
  await sh(
    `sleep 1; for i in $(seq 120); do pgrep -f "[q]m cleanup ${vmid} " >/dev/null || exit 0; sleep 0.25; done; exit 1`,
  )
}

async function sh(script: string): Promise<string> {
  const { code, output } = await pveExec(['sh', '-c', script])
  expect(code, output).toBe(0)
  return output
}

async function monitor(vmid: number, command: string): Promise<string> {
  return pve.post<string>(`/nodes/${NODE}/qemu/${vmid}/monitor`, { command })
}

async function config(vmid: number): Promise<Record<string, string>> {
  return pve.get<Record<string, string>>(`/nodes/${NODE}/qemu/${vmid}/config`)
}

/** The options with a pending change or deletion. */
async function pending(vmid: number): Promise<string[]> {
  const rows = await pve.get<{ delete?: number; key: string; pending?: string }[]>(
    `/nodes/${NODE}/qemu/${vmid}/pending`,
  )
  return rows.filter((r) => r.pending !== undefined || r.delete).map((r) => r.key)
}

/** A config change through the API, applied to the running VM right away (PUT, as the web UI does). */
async function update(vmid: number, form: Record<string, number | string>): Promise<void> {
  await pve.put(`/nodes/${NODE}/qemu/${vmid}/config`, form)
}

/** The MAC qemu-server generated for net0. */
async function mac(vmid: number): Promise<string> {
  const net0 = (await config(vmid)).net0 ?? ''
  const found = /^\w+=([\dA-F:]+),/.exec(net0)?.[1]
  expect(found, net0).toBeDefined()
  return found ?? ''
}

test.describe('CD-ROM medium of a running VM', () => {
  for (const vm of VMS) {
    test(`${vm.name}: change, eject and insert`, async () => {
      test.fail(vm.sparc && !fixed, 'qemu-server without the running-sparc fixes')
      const vmid = await startVm(vm)

      const steps = [
        {
          block: new RegExp(`^drive-${vm.cd}: .*"filename": "${ISO_DIR}/${ISO_B}"`, 'm'),
          value: `local:iso/${ISO_B},media=cdrom`,
        },
        { block: new RegExp(String.raw`^${vm.cd}: \[not inserted\]`, 'm'), value: 'none,media=cdrom' },
        {
          block: new RegExp(`^drive-${vm.cd}: .*"filename": "${ISO_DIR}/${ISO_A}"`, 'm'),
          value: `local:iso/${ISO_A},media=cdrom`,
        },
      ]
      for (const { block, value } of steps) {
        await update(vmid, { [vm.cd]: value })
        expect(await pending(vmid)).toEqual([])
        expect((await config(vmid))[vm.cd]).toMatch(new RegExp(`^${value}(,|$)`))
        // QEMU has the new medium, not only the config
        expect(await monitor(vmid, 'info block')).toMatch(block)
      }
    })
  }
})

test.describe('net0 of a running VM', () => {
  for (const vm of VMS) {
    test(`${vm.name}: bridge, VLAN tag, link_down and rate apply live`, async () => {
      test.fail(vm.nic === 'lance' && !fixed, 'qemu-server without the running-sparc fixes')
      const vmid = await startVm(vm)
      const tap = `tap${vmid}i0`
      const net = `${vm.nic}=${await mac(vmid)}`

      // QEMU's NIC is peered with the tap netdev 'net0', which qemu-server's set_link addresses.
      // (QEMU doesn't report the link state itself; the NIC follows its peer's set_link.)
      expect(await monitor(vmid, 'info network')).toMatch(/^ \\ net0: index=0,type=tap,ifname=tap\d+i0,/m)

      const change = async (options: string): Promise<void> => {
        const net0 = `${net},${options}`
        await update(vmid, { net0 })
        expect(await pending(vmid)).toEqual([])
        expect((await config(vmid)).net0).toBe(net0)
      }

      await change(`bridge=${BRIDGE2}`)
      expect(await sh(`ip -color=never -o link show dev ${tap}`)).toContain(`master ${BRIDGE2}`)

      await change(`bridge=${BRIDGE2},tag=100`)
      expect(await sh(`bridge -color=never vlan show dev ${tap}`)).toMatch(/\b100\s+PVID\s+Egress\s+Untagged/)

      await change(`bridge=${BRIDGE2},link_down=1,tag=100`)
      await change(`bridge=${BRIDGE2},tag=100`)

      await change(`bridge=${BRIDGE2},rate=5,tag=100`)
      expect(await sh(`tc qdisc show dev ${tap}`)).toContain('qdisc htb 1: root')

      await change('bridge=vmbr0')
      expect(await sh(`ip -color=never -o link show dev ${tap}`)).toContain('master vmbr0')
    })
  }
})

test.describe('changes that wait for the next start on sparc', () => {
  for (const vm of VMS.filter((v) => v.sparc)) {
    test(`${vm.name}: a new MAC, a new disk and memory become pending`, async () => {
      test.fail(!fixed, 'qemu-server without the running-sparc fixes')
      const vmid = await startVm(vm)

      // the NIC can't be replaced while running (sun4m's lance is built in, sun4u's PCI has no hotplug)
      await update(vmid, { net0: `${vm.nic}=BC:24:11:00:00:99,bridge=vmbr0` })
      await update(vmid, { scsi1: 'local:0.0625,format=qcow2' })
      await update(vmid, { memory: vm.memory })
      expect((await pending(vmid)).toSorted()).toEqual(['memory', 'net0', 'scsi1'])
      expect(await qm(['status', String(vmid)])).toContain('status: running')

      // applied on the next start
      await stopVm(vmid)
      await qm(['start', String(vmid)])
      expect(await pending(vmid)).toEqual([])
      const conf = await config(vmid)
      expect(conf.net0).toBe(`${vm.nic}=BC:24:11:00:00:99,bridge=vmbr0`)
      expect(conf.memory).toBe(String(vm.memory))
      expect(await monitor(vmid, 'info block')).toMatch(/^drive-scsi1: /m)
    })
  }
})

test.describe('other operations on a running sparc VM', () => {
  for (const vm of [SS5, SUN4U]) {
    test(`${vm.name}: clone, move disk, suspend/resume, reset and status`, async () => {
      test.fail(!fixed, 'qemu-server without the running-sparc fixes')
      const vmid = await startVm(vm)
      const { disk } = vm

      // both mirror the running VM's disk (blockdev-mirror, chosen by the machine version)
      const clone = Number(await pve.get<string>('/cluster/nextid'))
      await qm(['clone', String(vmid), String(clone), '--full'])
      expect((await config(clone))[disk]).toMatch(new RegExp(`^local:${clone}/vm-${clone}-disk-0\\.qcow2`))

      await qm(['disk', 'move', String(vmid), disk, 'local', '--format', 'raw', '--delete', '1'])
      expect((await config(vmid))[disk]).toMatch(/\.raw,/)
      expect(await monitor(vmid, 'info block')).toMatch(new RegExp(`^drive-${disk}: .*\\.raw"`, 'm'))

      await qm(['suspend', String(vmid)])
      expect(await qm(['status', String(vmid), '--verbose'])).toContain('qmpstatus: paused')
      await qm(['resume', String(vmid)])
      await qm(['reset', String(vmid)])
      await qm(['sendkey', String(vmid), 'ret'])
      expect(await qm(['status', String(vmid), '--verbose'])).toContain('qmpstatus: running')
    })
  }

  test('sparc32 starts with net0 disconnected (link_down=1)', async () => {
    // the start sets the link of net0, which failed with "Device 'net0' not found"
    test.fail(!fixed, 'qemu-server without the running-sparc fixes')
    const vmid = Number(await pve.get<string>('/cluster/nextid'))
    await waitTask(
      await pve.post<string>(`/nodes/${NODE}/qemu`, {
        name: 'sparc32-link-down',
        net0: 'lance,bridge=vmbr0,link_down=1',
        vmid,
        ...SS5.params,
      }),
    )
    await qm(['start', String(vmid)])
    expect(await qm(['status', String(vmid)])).toContain('status: running')
  })
})
