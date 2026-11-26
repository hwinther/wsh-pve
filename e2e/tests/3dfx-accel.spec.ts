import { expect, test } from '@playwright/test'

import { NODE, type Pve, pveApi, pveExec, qemuServerNames3dfxAccel, showcmd } from './_pve'

// A 3dfx VM (`vga: ...,mesa=1`) runs /usr/bin/qemu-system-x86_64-3dfx instead of /usr/bin/kvm. Without
// an accelerator on its command line QEMU prefers KVM only when its program name ends in "kvm", so the
// 3dfx binary would run in TCG even with KVM on (the default). qemu-server names the accelerator for
// it: accel=kvm with the VM's kvm option on, accel=tcg with kvm: 0. Checked in the command line and in
// the running VM (QMP query-kvm, what `info kvm` in the monitor shows). The VM has no disk: SeaBIOS
// waits at its boot menu while it is asked.
//
// The KVM half needs /dev/kvm in the PVE container (privileged, so the host's): GitHub's hosted
// runners have it. Without it qemu-server refuses to start a VM with kvm on, and the test says so
// in an annotation instead of failing.

const VMID = 9312
let pve: Pve

interface QueryKvm {
  enabled: boolean
  present: boolean
}

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  await pveExec([
    'sh',
    '-c',
    `qm stop ${VMID} --skiplock 1 > /dev/null 2>&1; qm destroy ${VMID} --purge 1 > /dev/null 2>&1; true`,
  ])
})

/** The running VM's accelerator, from QMP query-kvm. */
async function queryKvm(vmid: number): Promise<QueryKvm> {
  const r = await pveExec([
    'perl',
    '-MPVE::QemuServer::Monitor=mon_cmd',
    '-MJSON',
    '-e',
    'print "query-kvm: ", to_json(mon_cmd(shift, "query-kvm"), { canonical => 1 }), "\\n"',
    String(vmid),
  ])
  expect(r.code, r.output).toBe(0)
  const json = /^query-kvm: (\{.*\})/m.exec(r.output)?.[1]
  expect(json, r.output).toBeDefined()
  return JSON.parse(json ?? '{}') as QueryKvm
}

/** Creates the 3dfx VM with the kvm option, checks its -machine and returns query-kvm while it runs. */
async function run3dfxVm(kvm: 0 | 1): Promise<QueryKvm> {
  await pve.post(`/nodes/${NODE}/qemu`, {
    kvm,
    memory: 64,
    name: `accel-kvm${kvm}`,
    tablet: 0,
    vga: 'std,mesa=1',
    vmid: VMID,
  })
  await expect
    .poll(async () => (await pveExec(['cat', `/etc/pve/qemu-server/${VMID}.conf`])).output)
    .not.toContain('lock: create')
  const cmd = await showcmd(VMID)
  expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-x86_64-3dfx \\$/m)
  expect(cmd).toMatch(new RegExp(`^ {2}-machine 'accel=${kvm ? 'kvm' : 'tcg'},`, 'm'))

  const start = await pveExec(['qm', 'start', String(VMID)])
  expect(start.code, start.output).toBe(0)
  const state = await queryKvm(VMID)
  const stop = await pveExec(['sh', '-c', `qm stop ${VMID} && qm destroy ${VMID} --purge 1`])
  expect(stop.code, stop.output).toBe(0)
  return state
}

test('3dfx VM: KVM with the kvm option on, TCG with kvm: 0', async () => {
  test.setTimeout(180_000)
  const binary = await pveExec(['test', '-x', '/usr/bin/qemu-system-x86_64-3dfx'])
  test.skip(binary.code !== 0, 'the installed pve-qemu-kvm has no 3dfx binary (the optional extra is missing)')
  test.skip(
    !(await qemuServerNames3dfxAccel()),
    'the installed qemu-server leaves the accelerator of the 3dfx binary to QEMU (TCG) yet',
  )

  const tcg = await run3dfxVm(0)
  expect(tcg.enabled, 'kvm: 0 runs in TCG').toBe(false)

  const dev = await pveExec(['test', '-c', '/dev/kvm'])
  if (dev.code !== 0) {
    test
      .info()
      .annotations.push({ description: 'no /dev/kvm on this runner: the KVM half is not checked', type: 'skip' })
    return
  }
  const kvm = await run3dfxVm(1)
  expect(kvm, 'the kvm option on runs in KVM (query-kvm, `info kvm`)').toEqual({ enabled: true, present: true })
})
