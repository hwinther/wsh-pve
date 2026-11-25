import { expect, test } from '@playwright/test'

import {
  NODE,
  type Pve,
  pveApi,
  pveExec,
  qemuAccepts,
  qemuHasDbusRefresh,
  qemuServerHasDbusDisplay,
  qemuServerHasDbusDisplayUids,
  showcmd,
  vmConfFile,
} from './_pve'

// QEMU's D-Bus display next to the VNC console (vga: display=dbus; mesa-display=dbus is the same
// with GL for the 3dfx binary; audio0 driver dbus sends the sound to it): the command qemu-server
// builds, its refusals, and a real start, where qemu-server starts the VM's own bus
// (wsh-dbus-display@<vmid>, a dbus-daemon on /run/wsh-dbus-display/<vmid>.sock) before QEMU and
// stops it with the VM. What a client gets (frames, refresh rate, sound) is measured with
// e2e/3dfx/dbus-listener.py; see the 3dfx guide, "D-Bus display".

let pve: Pve

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
  test.skip(!(await qemuServerHasDbusDisplay()), 'the installed qemu-server has no D-Bus display yet')
})

test.afterEach(async () => {
  const vms = await pve.get<{ vmid: number; status: string }[]>(`/nodes/${NODE}/qemu`)
  for (const { vmid, status } of vms) {
    if (status === 'running') await pveExec(['qm', 'stop', String(vmid), '--skiplock', '1'])
    await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
  }
})

async function createVm(params: Record<string, number | string>): Promise<number> {
  const vmid = Number(await pve.get<string>('/cluster/nextid'))
  await pve.post(`/nodes/${NODE}/qemu`, { vmid, ...params })
  await expect.poll(async () => (await vmConfFile(vmid)).includes('lock: create')).toBe(false)
  return vmid
}

const busArg = (vmid: number, extra = '') =>
  `-display 'dbus,addr=unix:path=/run/wsh-dbus-display/${vmid}.sock${extra}'`

test('display=dbus adds the D-Bus display on the VM\'s own bus next to VNC', async () => {
  const vmid = await createVm({ memory: 512, name: 'x86-dbus', vga: 'std,display=dbus' })
  expect(await vmConfFile(vmid)).toContain('vga: std,display=dbus')
  const cmd = await showcmd(vmid)
  expect(cmd).toContain(busArg(vmid))
  expect(cmd).toContain(`-vnc 'unix:/var/run/qemu-server/${vmid}.vnc,password=on'`)
  const qemu = await qemuAccepts(vmid)
  expect(qemu.code, qemu.output).toBe(0)
})

test('dbus-refresh and audio driver dbus go to the D-Bus display', async () => {
  const vmid = await createVm({
    audio0: 'device=AC97,driver=dbus',
    memory: 512,
    name: 'x86-dbus-audio',
    vga: 'cirrus,display=dbus,dbus-refresh=14',
  })
  const cmd = await showcmd(vmid)
  expect(cmd).toContain(busArg(vmid, ',refresh-ms=14,audiodev=dbus-backend0'))
  expect(cmd).toContain("-audiodev 'dbus,id=dbus-backend0,out.frequency=48000'")
  expect(cmd).toContain('AC97,id=audiodev0')
  // QEMU without wsh/0131 doesn't know refresh-ms
  if (await qemuHasDbusRefresh()) {
    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  }
})

test('the D-Bus display on sparc32 (SS-5, cg3, the CS4231) and sparc64 (sun4u)', async () => {
  const ss5 = await createVm({
    arch: 'sparc',
    audio0: 'device=cs4231,driver=dbus',
    machine: 'SS-5',
    memory: 128,
    name: 'ss5-dbus',
    ostype: 'solaris',
    vga: 'cg3,display=dbus',
  })
  let cmd = await showcmd(ss5)
  expect(cmd).toContain('-vga cg3')
  expect(cmd).toContain(busArg(ss5, ',audiodev=dbus-backend0'))
  expect(cmd).toContain("-machine 'audiodev=dbus-backend0'")
  let qemu = await qemuAccepts(ss5)
  expect(qemu.code, qemu.output).toBe(0)

  const sun4u = await createVm({ arch: 'sparc64', memory: 512, name: 'sun4u-dbus', vga: 'std,display=dbus' })
  cmd = await showcmd(sun4u)
  expect(cmd).toContain(busArg(sun4u))
  qemu = await qemuAccepts(sun4u)
  expect(qemu.code, qemu.output).toBe(0)
})

test('mesa-display=dbus is the D-Bus display with GL for the 3dfx binary', async () => {
  const vmid = await createVm({ memory: 512, name: 'x86-3dfx-dbus', vga: 'std,mesa=1,mesa-display=dbus' })
  const cmd = await showcmd(vmid)
  expect(cmd).toMatch(/^\/usr\/bin\/qemu-system-x86_64-3dfx \\$/m)
  expect(cmd).toContain(busArg(vmid, ',gl=on'))
  expect(cmd).toContain(`-vnc 'unix:/var/run/qemu-server/${vmid}.vnc,password=on'`)
})

test('the D-Bus display is refused where it can\'t work', async () => {
  const create = `/nodes/${NODE}/qemu`
  const refusal = async (params: Record<string, string>) =>
    (await pve.refused('POST', create, { memory: 512, name: 'dbus-refused', vmid: 9398, ...params })).message
  expect(await refusal({ vga: 'std,dbus-refresh=14' })).toContain(
    "vga: 'dbus-refresh' needs the D-Bus display ('display=dbus')",
  )
  expect(await refusal({ audio0: 'device=AC97,driver=dbus', vga: 'std' })).toContain(
    "audio0: driver 'dbus' needs the D-Bus display (vga: 'display=dbus')",
  )
  expect(await refusal({ vga: 'std,display=dbus,server=:0' })).toContain(
    "vga: the D-Bus display can't be used with 'server' (the SDL display)",
  )
  expect(await refusal({ vga: 'qxl,display=dbus' })).toContain(
    "vga: the D-Bus display needs one of the types std, cirrus, vmware, virtio, tcx or cg3, not 'qxl'",
  )
  expect(await refusal({ vga: 'std,mesa=1,mesa-display=egl-headless,display=dbus' })).toContain(
    "vga: 'display=dbus' can't be used with 'mesa-display=egl-headless'",
  )
  expect(await refusal({ vga: 'std,mesa-display=dbus' })).toContain(
    "vga: 'mesa-display=dbus' needs 'mesa=1' on a VM of the host's architecture",
  )
  expect(await refusal({ vga: 'std,dbus-refresh=0,display=dbus' })).toMatch(/dbus-refresh/)
})

// A real start (TCG, no guest OS): the bus comes first, QEMU owns org.qemu on it with the console;
// VNC keeps working; QEMU outlives the bus; the stop takes the bus and its socket away.
test('a started VM gets its own bus; VNC stays; the bus goes with the VM', async () => {
  test.skip(!(await qemuHasDbusRefresh()), 'the installed pve-qemu-kvm has no refresh-ms yet')
  const vmid = await createVm({ memory: 256, name: 'x86-dbus-run', vga: 'std,display=dbus,dbus-refresh=14' })
  const sock = `/run/wsh-dbus-display/${vmid}.sock`
  const sh = (script: string) => pveExec(['sh', '-c', script])

  let r = await pveExec(['qm', 'start', String(vmid)])
  expect(r.code, r.output).toBe(0)
  r = await sh(`systemctl is-active wsh-dbus-display@${vmid}.service && stat -c '%a %U:%G %F' ${sock}`)
  expect(r.code, r.output).toBe(0)
  expect(r.output).toContain('root:wsh-display socket')
  r = await sh('stat -c "%a %U:%G" /run/wsh-dbus-display')
  expect(r.output).toContain('750 root:wsh-display')
  await expect
    .poll(async () => (await sh(`busctl --address=unix:path=${sock} tree org.qemu`)).output, { timeout: 15_000 })
    .toContain('/org/qemu/Display1/Console_0')

  // the VNC console: the RFB greeting on PVE's socket
  const vnc = `python3 -c "import socket;s=socket.socket(socket.AF_UNIX);s.settimeout(5);s.connect('/var/run/qemu-server/${vmid}.vnc');print(s.recv(12))"`
  r = await sh(vnc)
  expect(r.output).toContain('RFB 003.008')

  // someone outside root and wsh-display may not connect
  r = await sh(`setpriv --reuid=65534 --regid=65534 --clear-groups busctl --address=unix:path=${sock} tree org.qemu`)
  expect(r.code, r.output).not.toBe(0)

  // the bus killed: QEMU keeps running, VNC too
  r = await sh(`systemctl kill -s KILL wsh-dbus-display@${vmid}.service; sleep 1; qm status ${vmid}`)
  expect(r.output).toContain('status: running')
  r = await sh(vnc)
  expect(r.output).toContain('RFB 003.008')

  r = await pveExec(['qm', 'stop', String(vmid)])
  expect(r.code, r.output).toBe(0)
  await expect
    .poll(async () => (await sh(`systemctl is-active wsh-dbus-display@${vmid}.service; test -e ${sock}; echo $?`)).output)
    .toMatch(/inactive|failed/)
  r = await sh(`test -e ${sock}`)
  expect(r.code).not.toBe(0)
})

// dbus-display-uids: a host uid (an unprivileged container's root, 100000) gets onto this VM's bus
// and no other's. qemu-server writes the VM's bus configuration, gives the uid a user if it has none
// and an ACL entry on the socket directory while the VM runs. A process on the node with that uid
// is what the bus sees of the container's root, so setpriv stands in for the container here.
test('dbus-display-uids lets a container's uid onto that VM's bus, not others'', async () => {
  test.skip(!(await qemuServerHasDbusDisplayUids()), 'the installed qemu-server has no dbus-display-uids yet')
  const params = { 'dbus-display-uids': '100000', memory: 256, name: 'x86-dbus-uids' }
  const refused = await pve.refused('POST', `/nodes/${NODE}/qemu`, { ...params, vga: 'std', vmid: 9397 })
  expect(refused.message).toContain("dbus-display-uids needs the D-Bus display (vga: 'display=dbus')")

  const vmid = await createVm({ ...params, vga: 'std,display=dbus' })
  const other = await createVm({ memory: 256, name: 'x86-dbus-other', vga: 'std,display=dbus' })
  const sh = (script: string) => pveExec(['sh', '-c', script])
  const asUid = (uid: number, sock: string) =>
    sh(`setpriv --reuid=${uid} --regid=65534 --clear-groups busctl --address=unix:path=${sock} tree org.qemu`)
  for (const id of [vmid, other]) {
    const r = await pveExec(['qm', 'start', String(id)])
    expect(r.code, r.output).toBe(0)
  }
  let r = await sh(`cat /run/qemu-server/${vmid}.dbus-display.conf`)
  expect(r.output).toContain('<allow user="100000"/>')
  r = await sh('getent passwd 100000')
  expect(r.code, r.output).toBe(0)
  r = await sh('getfacl --numeric /run/wsh-dbus-display')
  expect(r.output).toContain('user:100000:--x')

  await expect
    .poll(async () => (await asUid(100000, `/run/wsh-dbus-display/${vmid}.sock`)).output, { timeout: 15_000 })
    .toContain('/org/qemu/Display1/Console_0')
  r = await asUid(100000, `/run/wsh-dbus-display/${other}.sock`)
  expect(r.code, r.output).not.toBe(0)
  r = await asUid(100001, `/run/wsh-dbus-display/${vmid}.sock`)
  expect(r.code, r.output).not.toBe(0)

  r = await pveExec(['qm', 'stop', String(vmid)])
  expect(r.code, r.output).toBe(0)
  await expect
    .poll(async () => (await sh('getfacl --numeric /run/wsh-dbus-display')).output)
    .not.toContain('user:100000:')
})
