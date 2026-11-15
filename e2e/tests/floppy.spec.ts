import { expect, type Page, test } from '@playwright/test'

import { NODE, PASSWORD, type Pve, pveApi, pveExec, qemuAccepts, showcmd, vmConfFile, writeConfFile } from './_pve'

// Floppy support across the three patched packages: the `floppy` storage content type
// (libpve-storage-perl), floppy0/floppy1 drives (qemu-server) and their UI (pve-manager).

const IMAGE_NAME = 'e2e-floppy.img'
const IMAGE = `local:floppy/${IMAGE_NAME}`
const UPLOAD_NAME = 'e2e-upload.img'

let pve: Pve

test.beforeAll(async () => {
  // TODO: remove this skip once floppy support is published at debian.wshosting.no. Until then the
  // image built from the published packages (the PR and main e2e runs) has no floppy drives.
  const probe = await pveExec([
    'perl',
    '-MPVE::QemuServer::Drive',
    '-e',
    'print PVE::QemuServer::Drive::is_valid_drivename("floppy0") ? "floppy=yes\\n" : "floppy=no\\n"',
  ])
  expect(probe.output, probe.output).toMatch(/floppy=(yes|no)/)
  // eslint-disable-next-line playwright/no-skipped-test -- conditional, until the packages are published
  test.skip(
    probe.output.includes('floppy=no'),
    'installed qemu-server has no floppy support (packages not published yet)',
  )

  // The floppy content type on the directory storage, and a blank 1.44 MB image to attach.
  for (const cmd of [
    ['pvesm', 'set', 'local', '--content', 'images,iso,vztmpl,backup,snippets,rootdir,floppy'],
    ['sh', '-c', `mkdir -p /var/lib/vz/template/floppy && truncate -s 1440K /var/lib/vz/template/floppy/${IMAGE_NAME}`],
  ]) {
    const { code, output } = await pveExec(cmd)
    expect(code, output).toBe(0)
  }
})

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  const vms = await pve.get<{ vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { vmid } of vms) await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
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

test('storage: the floppy image is listed as floppy content', async () => {
  const content = await pve.get<{ content: string; format: string; volid: string }[]>(
    `/nodes/${NODE}/storage/local/content?content=floppy`,
  )
  expect(content).toContainEqual(expect.objectContaining({ content: 'floppy', format: 'raw', volid: IMAGE }))
})

test('i440fx: a boot floppy uses the onboard controller', async () => {
  const vmid = await createVm({ boot: 'order=floppy0', floppy0: IMAGE, memory: 512, name: 'floppy-i440fx' })

  expect(await vmConfFile(vmid)).toMatch(new RegExp(`^floppy0: ${IMAGE}(,|$)`, 'm'))

  const cmd = await showcmd(vmid)
  expect(cmd).toContain("-device 'floppy,unit=0,drive=drive-floppy0,id=floppy0'")
  // The floppy device has no bootindex; the controller has one per unit.
  expect(cmd).toContain("-global 'isa-fdc.bootindexA=100'")
  expect(cmd).toContain(`/var/lib/vz/template/floppy/${IMAGE_NAME}`)
  expect(cmd).not.toContain("-device 'isa-fdc")

  const qemu = await qemuAccepts(vmid)
  expect(qemu.code, qemu.output).toBe(0)
})

test('q35: floppies get an isa-fdc controller', async () => {
  const vmid = await createVm({
    floppy0: IMAGE,
    floppy1: 'none',
    machine: 'q35',
    memory: 512,
    name: 'floppy-q35',
  })

  const cmd = await showcmd(vmid)
  expect(cmd.match(/-device 'isa-fdc,id=fdc'/g)).toHaveLength(1)
  expect(cmd).toContain("-device 'floppy,unit=0,drive=drive-floppy0,id=floppy0")
  // An empty drive has no block node to point at.
  expect(cmd).toContain("-device 'floppy,unit=1,id=floppy1'")

  const qemu = await qemuAccepts(vmid)
  expect(qemu.code, qemu.output).toBe(0)
})

test('a floppy on a non-x86 VM is refused', async () => {
  const vmid = 907
  await writeConfFile(vmid, [
    'arch: sparc',
    'balloon: 0',
    `floppy0: ${IMAGE}`,
    'machine: SS-5',
    'memory: 256',
    'name: floppy-sparc',
    'tablet: 0',
    'vga: cg3',
  ])

  const { code, output } = await pveExec(['qm', 'showcmd', String(vmid)])
  expect(code).not.toBe(0)
  expect(output).toContain('floppy drives are only supported on x86_64')
})

test.describe('web UI', () => {
  test('Hardware: Add -> Floppy Drive', async ({ page }) => {
    // Created before logging in, so the resource tree already knows it.
    const vmid = await createVm({ memory: 512, name: 'floppy-ui' })
    await login(page)
    await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
    await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()

    await page.getByRole('button', { name: 'Add' }).click()
    await page.getByRole('menuitem', { name: 'Floppy Drive' }).click()
    const win = page.locator('.x-window').filter({ hasText: 'Add: Floppy Drive' })
    await pickCombo(page, win, 'Storage', 'local')
    await pickCombo(page, win, 'Floppy image', IMAGE_NAME)
    await win.getByRole('button', { name: 'Add' }).click()
    await expect(win).toBeHidden()

    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^floppy0: ${IMAGE}(,|$)`, 'm'))
    await expect(page.getByText('Floppy Drive (floppy0)')).toBeVisible()
    expect(await showcmd(vmid)).toContain("-device 'floppy,unit=0,drive=drive-floppy0,id=floppy0")
    const qemu = await qemuAccepts(vmid)
    expect(qemu.code, qemu.output).toBe(0)
  })

  test('storage: Floppy Images tab uploads an image', async ({ page }) => {
    const volid = `local:floppy/${UPLOAD_NAME}`
    await pveExec(['rm', '-f', `/var/lib/vz/template/floppy/${UPLOAD_NAME}`])

    await login(page)
    // The datacenter search grid lists the storage; a double click opens it.
    await page.getByText(`local (${NODE})`, { exact: true }).dblclick()
    await page.getByText('Floppy Images', { exact: true }).click()
    await page.getByRole('button', { name: 'Upload' }).click()

    const win = page.locator('.x-window').filter({ has: page.locator('input[type=file]') })
    await win.locator('input[type=file]').setInputFiles({
      buffer: Buffer.alloc(1440 * 1024),
      mimeType: 'application/octet-stream',
      name: UPLOAD_NAME,
    })
    await win.getByRole('button', { name: 'Upload' }).click()

    await expect
      .poll(
        async () =>
          (await pve.get<{ volid: string }[]>(`/nodes/${NODE}/storage/local/content?content=floppy`)).map(
            (v) => v.volid,
          ),
        { timeout: 30_000 },
      )
      .toContain(volid)
    await pve.delete(`/nodes/${NODE}/storage/local/content/${encodeURIComponent(volid)}`)
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

/** Opens the combo labelled `label` in `win` and picks the entry showing `option`. */
async function pickCombo(page: Page, win: ReturnType<Page['locator']>, label: string, option: string) {
  await win.getByLabel(label).click()
  // Plain combos open a boundlist, the storage/file selectors a grid picker.
  await page
    .locator('.x-boundlist:visible li, .x-layer.x-grid:visible .x-grid-cell-inner')
    .filter({ hasText: new RegExp(`^${option.replaceAll('.', '\\.')}`) })
    .first()
    .click()
}
