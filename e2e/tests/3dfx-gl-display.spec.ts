import { expect, type Page, test } from '@playwright/test'

import {
  NODE,
  PASSWORD,
  type Pve,
  pveApi,
  pveExec,
  qemu3dfxHasGlDisplay,
  qemuServerHasMesaDisplay,
  showcmd,
} from './_pve'

// A 3dfx VM started by PVE, with its Glide frame checked where the user sees it: PVE's noVNC console.
// The guest is the Glide guest of e2e/3dfx/test.sh (Debian's kernel, glide-guest as /init, which
// draws the test scene of packages/wsh-openglide/tests/scene.h through qemu-3dfx's Linux guest
// wrapper), put into the container by e2e/3dfx/pve-guest-setup.sh; the VM boots it through `args`.
// GLIDE_GUEST_BENCH keeps the scene on screen while the console is read.
//
//   - `mesa-display=egl-headless`: QEMU gets a GL display next to VNC, the Glide frames go to it as a
//     dmabuf (wsh-openglide's exported buffer; on a node without a GPU through /dev/udmabuf, which
//     shows as open dmabuf files of QEMU's), and egl-headless reads them into the console for VNC.
//   - the default: no -display, the frames are read back into the console (stage 1).
//
// Needs the guest, a qemu-server with mesa-display, a 3dfx binary with the dmabuf scanout and, for
// the dmabuf, a wsh-openglide that exports one plus a render node or /dev/udmabuf (the container is
// privileged, so it sees the host's). Skipped without the guest or packages; the dmabuf check is
// skipped on a node with neither device. In CI (e2e.yml) the guest is set up before the run, and
// GitHub's runners have /dev/udmabuf, so both parts run there.

const GUEST = '/root/3dfx-guest'
const VMID = 9310
let pve: Pve

/** The scene's probes (scene.h) on the console's 640x480 Glide frame: x, y and the colour. */
const PROBES: [string, number, number, [number, number, number]][] = [
  ['clear, top left', 10, 10, [0x00, 0x00, 0x80]],
  ['clear, top right', 630, 10, [0x00, 0x00, 0x80]],
  ['red triangle', 166, 293, [0xff, 0x00, 0x00]],
  ['green triangle', 473, 293, [0x00, 0xff, 0x00]],
]
const TOLERANCE = 24

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

async function login(page: Page) {
  await page.goto('/')
  await page.locator('input[name=username]').fill('root')
  await page.locator('input[name=password]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Login' }).click()
  await page.getByRole('button', { name: 'OK' }).click()
}

/** The console canvas' pixel at x, y (noVNC draws the VM's screen 1:1 with resize=off). */
async function pixel(page: Page, x: number, y: number): Promise<number[]> {
  return page.evaluate(
    (at) => {
      const canvas = document.querySelector('canvas')
      const ctx = canvas?.getContext('2d')
      if (!canvas || !ctx || canvas.width < 640 || canvas.height < 480) return [-1, -1, -1]
      return Array.from(ctx.getImageData(at.x, at.y, 1, 1).data.slice(0, 3))
    },
    { x, y },
  )
}

const near = (got: number[], want: number[]) => got.every((c, i) => Math.abs(c - (want[i] ?? 0)) <= TOLERANCE)

/**
 * Boots the Glide guest in a VM with `vga`, waits for its frame and checks it in the noVNC console.
 * Returns how many dmabufs QEMU has open while the frame is up.
 */
async function glideFrame(page: Page, display: string, vga: string): Promise<number> {
  const serial = `/run/3dfx-guest-${VMID}.log`
  const append = 'console=ttyS0 rdinit=/init panic=-1 quiet GLIDE_GUEST_BENCH=200000'
  await pve.post(`/nodes/${NODE}/qemu`, {
    args: `-kernel ${GUEST}/vmlinuz -initrd ${GUEST}/glide.initrd -append "${append}" -serial file:${serial}`,
    kvm: 0,
    memory: 256,
    name: `glide-${display}`,
    tablet: 0,
    vga,
    vmid: VMID,
  })
  await expect
    .poll(async () => (await pveExec(['cat', `/etc/pve/qemu-server/${VMID}.conf`])).output)
    .not.toContain('lock: create')
  const cmd = await showcmd(VMID)
  if (display === 'none') expect(cmd).not.toContain('-display')
  else expect(cmd).toMatch(new RegExp(`^ {2}-display ${display} \\\\$`, 'm'))

  const start = await pveExec(['sh', '-c', `rm -f ${serial}; qm start ${VMID} 2>&1`])
  expect(start.code, start.output).toBe(0)
  await expect
    .poll(async () => (await pveExec(['cat', serial])).output, { intervals: [1000], timeout: 180_000 })
    .toContain('GLIDE-GUEST: FRAME')
  // what the guest read back through the pass-through (its verdict comes after the benchmark)
  const guestLog = (await pveExec(['cat', serial])).output
  expect(guestLog).not.toMatch(/^FAIL /m)
  expect(guestLog).not.toMatch(/GLIDE-GUEST: (?:FAIL|ERROR)/)

  // QEMU's open dmabufs (anonymous "dmabuf:" files) while the frame is up
  const fds = await pveExec([
    'sh',
    '-c',
    `ls -l /proc/$(cat /run/qemu-server/${VMID}.pid)/fd | grep -c 'dmabuf:' || true`,
  ])

  await page.goto(`/?console=kvm&novnc=1&vmid=${VMID}&vmname=glide-${display}&node=${NODE}&resize=off&cmd=`)
  await expect(page.locator('canvas')).toBeVisible()
  for (const [what, x, y, want] of PROBES) {
    await expect
      .poll(async () => near(await pixel(page, x, y), want), {
        message: `${display}: ${what} (${x},${y})`,
        timeout: 30_000,
      })
      .toBe(true)
  }
  await page.locator('canvas').screenshot({ path: test.info().outputPath(`novnc-glide-${display}.png`) })

  const stop = await pveExec(['sh', '-c', `qm stop ${VMID} && qm destroy ${VMID} --purge 1`])
  expect(stop.code, stop.output).toBe(0)
  return Number(fds.output.trim())
}

test('3dfx VM: the Glide frame in the noVNC console, read back and with egl-headless as a dmabuf', async ({ page }) => {
  test.setTimeout(420_000)
  test.skip(!(await qemuServerHasMesaDisplay()), 'the installed qemu-server has no mesa-display yet')
  test.skip(!(await qemu3dfxHasGlDisplay()), 'the installed 3dfx binary has no dmabuf scanout yet')
  const guest = await pveExec(['sh', '-c', `test -s ${GUEST}/glide.initrd && test -s ${GUEST}/vmlinuz`])
  // e2e.yml sets the guest up before the run and sets E2E_3DFX_GUEST=required: there a missing guest
  // (a failed setup) fails the test instead of skipping it
  test.skip(
    guest.code !== 0 && process.env.E2E_3DFX_GUEST !== 'required',
    `no Glide guest in ${GUEST} (e2e/3dfx/pve-guest-setup.sh)`,
  )
  expect(guest.code, `no Glide guest in ${GUEST}: e2e/3dfx/pve-guest-setup.sh failed (see its output)`).toBe(0)

  await login(page)
  // the default: no -display, the frames read back into the console
  const readback = await glideFrame(page, 'none', 'std,mesa=1')

  // egl-headless needs a render node or /dev/udmabuf (the container is privileged: the host's).
  // Without either, qemu-server refuses to start the VM, as QEMU's EGL display would stop it.
  const devices = await pveExec(['sh', '-c', 'ls /dev/dri/renderD* /dev/udmabuf 2> /dev/null | head -n 1'])
  if (devices.output.trim() === '') {
    await pve.post(`/nodes/${NODE}/qemu`, { memory: 256, vga: 'std,mesa=1,mesa-display=egl-headless', vmid: VMID })
    const start = await pveExec(['qm', 'start', String(VMID)])
    expect(start.code, start.output).not.toBe(0)
    expect(start.output).toContain('vga: mesa-display=egl-headless needs a GPU render node')
    test
      .info()
      .annotations.push({ description: 'no render node and no /dev/udmabuf: egl-headless refused', type: 'skip' })
    return
  }

  // egl-headless: the frames as a dmabuf, which egl-headless reads into the console for VNC
  const egl = await glideFrame(page, 'egl-headless', 'std,mesa=1,mesa-display=egl-headless')
  test
    .info()
    .annotations.push({ description: `open dmabufs: read back ${readback}, egl-headless ${egl}`, type: 'info' })
  // wsh-openglide's exported scanout buffer and egl-headless' import of it come on top of what the
  // renderer itself has open (an older wsh-openglide exports none: its frames are read back)
  const exports = await pveExec(['sh', '-c', 'grep -qa getOffscreenDmabuf /usr/lib/x86_64-linux-gnu/libglide2x.so.0'])
  if (exports.code === 0) expect(egl).toBeGreaterThan(readback)
  else test.info().annotations.push({ description: 'this wsh-openglide exports no dmabuf: read back', type: 'skip' })
})
