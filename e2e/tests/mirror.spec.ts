import { expect, type Locator, type Page, test } from '@playwright/test'

import { NODE, PASSWORD, type Pve, pveApi, pveExec, vmConfFile } from './_pve'

// A mirror storage (docs: reference/mirror, `wsh-lab mirror`): a dir storage whose template/iso and
// template/floppy hold symlinks to media elsewhere (a NAS), the folders kept in the link name with
// '__'. The backend part works with any libpve-storage-perl (stat() follows the link); the folder
// view is pve-manager's. The UI tests probe the installed pve-manager and are skipped on one
// without the folder view (published packages before it).

const STORAGE = 'mirror'
const NAS = '/srv/e2e-nas'
const MIRROR = '/srv/e2e-mirror'
const ISO = 'Solaris__2.6__solaris_2.6_598_sparc.iso'
const ISO_TARGET = `${NAS}/Solaris/2.6/solaris_2.6_598_sparc.iso`
const FLOPPY = 'DOS__6.22__disk1.img'
const FLOPPY_TARGET = `${NAS}/DOS/6.22/disk1.img`
const ISO_SIZE = 3 * 1024 * 1024

let pve: Pve
let folderUi = false

test.beforeAll(async () => {
  // The NAS tree and the storage of links. Sizes differ so the listed size shows it's the target's.
  const script = `
set -e
rm -rf ${NAS} ${MIRROR}
mkdir -p ${NAS}/Solaris/2.6 ${NAS}/Solaris/7 ${NAS}/DOS/6.22 ${MIRROR}/template/iso ${MIRROR}/template/floppy
truncate -s ${ISO_SIZE} ${ISO_TARGET}
truncate -s 2M ${NAS}/Solaris/7/sol-7-sparc.iso
truncate -s 1M ${NAS}/top-level.iso
truncate -s 1440K ${FLOPPY_TARGET}
cd ${MIRROR}/template/iso
ln -s ${ISO_TARGET} ${ISO}
ln -s ${NAS}/Solaris/7/sol-7-sparc.iso Solaris__7__sol-7-sparc.iso
ln -s ${NAS}/top-level.iso top-level.iso
ln -s ${FLOPPY_TARGET} ${MIRROR}/template/floppy/${FLOPPY}
pvesm status --storage ${STORAGE} > /dev/null 2>&1 && pvesm remove ${STORAGE}
pvesm add dir ${STORAGE} --path ${MIRROR} --content iso,floppy
`
  const { code, output } = await pveExec(['sh', '-c', script])
  expect(code, output).toBe(0)
  folderUi = (await pveExec(['grep', '-q', 'mirrorSeparator', '/usr/share/pve-manager/js/pvemanagerlib.js'])).code === 0
})

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  const vms = await pve.get<{ vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { vmid } of vms) await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
})

test.afterAll(async () => {
  await pveExec(['sh', '-c', `pvesm remove ${STORAGE}; rm -rf ${NAS} ${MIRROR}`])
})

interface Volume {
  content: string
  size: number
  volid: string
}

async function content(type: string): Promise<Volume[]> {
  return pve.get<Volume[]>(`/nodes/${NODE}/storage/${STORAGE}/content?content=${type}`)
}

async function createVm(params: Record<string, number | string>): Promise<number> {
  const vmid = Number(await pve.get<string>('/cluster/nextid'))
  const upid = await pve.post<string>(`/nodes/${NODE}/qemu`, { vmid, ...params })
  const path = `/nodes/${NODE}/tasks/${encodeURIComponent(upid)}/status`
  await expect
    .poll(async () => (await pve.get<{ status: string }>(path)).status, { intervals: [250], timeout: 30_000 })
    .toBe('stopped')
  return vmid
}

test("storage: symlinked ISO and floppy images are volumes with their names and the targets' sizes", async () => {
  const isos = await content('iso')
  expect(isos.map((v) => v.volid).sort()).toEqual(
    [`${STORAGE}:iso/${ISO}`, `${STORAGE}:iso/Solaris__7__sol-7-sparc.iso`, `${STORAGE}:iso/top-level.iso`].sort(),
  )
  expect(isos.find((v) => v.volid === `${STORAGE}:iso/${ISO}`)?.size).toBe(ISO_SIZE)
  const floppies = await content('floppy')
  expect(floppies).toContainEqual(expect.objectContaining({ size: 1440 * 1024, volid: `${STORAGE}:floppy/${FLOPPY}` }))
  // the volume's path is the link; QEMU opens the target through it
  const { code, output } = await pveExec(['pvesm', 'path', `${STORAGE}:iso/${ISO}`])
  expect(code, output).toBe(0)
  expect(output.trim()).toBe(`${MIRROR}/template/iso/${ISO}`)
})

test('storage: a dangling link is not listed', async () => {
  await pveExec(['ln', '-sf', `${NAS}/gone.iso`, `${MIRROR}/template/iso/Gone__gone.iso`])
  try {
    expect((await content('iso')).map((v) => v.volid)).not.toContain(`${STORAGE}:iso/Gone__gone.iso`)
  } finally {
    await pveExec(['rm', '-f', `${MIRROR}/template/iso/Gone__gone.iso`])
  }
})

test('storage: removing a volume removes the link and leaves the target', async () => {
  const link = `${MIRROR}/template/iso/Remove__me.iso`
  const target = `${NAS}/remove-me.iso`
  expect((await pveExec(['sh', '-c', `truncate -s 1M ${target} && ln -s ${target} ${link}`])).code).toBe(0)
  const volid = encodeURIComponent(`${STORAGE}:iso/Remove__me.iso`)
  await pve.delete(`/nodes/${NODE}/storage/${STORAGE}/content/${volid}`)
  expect((await pveExec(['test', '-L', link])).code).not.toBe(0)
  expect((await pveExec(['test', '-f', target])).code).toBe(0)
  await pveExec(['rm', '-f', target])
})

test('a VM with a mirrored ISO keeps the volume ID and QEMU gets the link', async () => {
  const vmid = await createVm({ ide2: `${STORAGE}:iso/${ISO},media=cdrom`, memory: 512, name: 'mirror-cd' })
  expect(await vmConfFile(vmid)).toMatch(new RegExp(`^ide2: ${STORAGE}:iso/${ISO},media=cdrom`, 'm'))
  const { code, output } = await pveExec(['qm', 'showcmd', String(vmid), '--pretty'])
  expect(code, output).toBe(0)
  expect(output).toContain(`${MIRROR}/template/iso/${ISO}`)
})

test.describe('web UI: folder view', () => {
  test.beforeEach(() => {
    // eslint-disable-next-line playwright/no-skipped-test -- until the published pve-manager has the folder view
    test.skip(!folderUi, 'the installed pve-manager has no folder view for mirror storages')
  })

  test('ISO Images: grouped by folder, file names in the rows, search on the full name', async ({ page }) => {
    await login(page)
    const grid = await openContent(page, 'ISO Images')
    await expect(groupHeader(grid, 'Solaris / 2.6')).toBeVisible()
    await expect(groupHeader(grid, 'Solaris / 7')).toBeVisible()
    await expect(groupHeader(grid, 'Top level')).toBeVisible()
    await expect(cell(grid, 'solaris_2.6_598_sparc.iso')).toBeVisible()
    await expect(cell(grid, 'top-level.iso')).toBeVisible()
    // the size column is the target's
    await expect(grid.locator('.x-grid-row', { hasText: 'solaris_2.6_598_sparc.iso' })).toContainText('3.00 MiB')

    // search matches the folder part of the name
    await grid.getByRole('textbox').fill('2.6')
    await expect(cell(grid, 'solaris_2.6_598_sparc.iso')).toBeVisible()
    await expect(cell(grid, 'top-level.iso')).toBeHidden()
    await expect(groupHeader(grid, 'Solaris / 7')).toBeHidden()
  })

  test('Floppy Images: grouped by folder', async ({ page }) => {
    await login(page)
    const grid = await openContent(page, 'Floppy Images')
    await expect(groupHeader(grid, 'DOS / 6.22')).toBeVisible()
    await expect(cell(grid, 'disk1.img')).toBeVisible()
  })

  test('ISO Images: Remove deletes the link, not the file on the NAS', async ({ page }) => {
    const link = `${MIRROR}/template/iso/Old__stuff__remove-ui.iso`
    const target = `${NAS}/remove-ui.iso`
    expect((await pveExec(['sh', '-c', `truncate -s 1M ${target} && ln -sf ${target} ${link}`])).code).toBe(0)
    await login(page)
    const grid = await openContent(page, 'ISO Images')
    await cell(grid, 'remove-ui.iso').click()
    await grid.getByRole('button', { name: 'Remove' }).click()
    const confirm = page.locator('.x-message-box')
    await expect(confirm).toContainText(`iso/Old__stuff__remove-ui.iso`)
    await confirm.getByRole('button', { name: 'Yes' }).click()
    await expect(cell(grid, 'remove-ui.iso')).toBeHidden({ timeout: 30_000 })
    await expect(groupHeader(grid, 'Old / stuff')).toBeHidden()
    expect((await pveExec(['test', '-L', link])).code).not.toBe(0)
    expect((await pveExec(['test', '-f', target])).code).toBe(0)
    await pveExec(['rm', '-f', target])
  })

  test('CD/DVD Drive: the ISO selector shows the path and keeps the volume ID', async ({ page }) => {
    const vmid = await createVm({ ide2: 'none,media=cdrom', memory: 512, name: 'mirror-cd-ui' })
    await login(page)
    await openHardware(page, vmid)
    await page.getByText('CD/DVD Drive (ide2)').dblclick()
    const win = page.locator('.x-window').filter({ hasText: 'Edit: CD/DVD Drive' })
    await win.getByText('Use CD/DVD disc image file (iso)').click()
    await pickCombo(page, win, 'Storage', STORAGE)
    await win.getByLabel('ISO image').click()
    const option = page.locator('.x-layer.x-grid:visible .x-grid-cell-inner', {
      hasText: 'Solaris / 2.6 / solaris_2.6_598_sparc.iso',
    })
    await expect(option).toBeVisible()
    // typing filters on the volume name (any part of it)
    await win.getByLabel('ISO image').fill('598')
    await expect(option).toBeVisible()
    await expect(page.locator('.x-layer.x-grid:visible .x-grid-cell-inner', { hasText: 'top-level.iso' })).toBeHidden()
    await option.click()
    await win.getByRole('button', { name: 'OK' }).click()
    await expect(win).toBeHidden()
    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^ide2: ${STORAGE}:iso/${ISO},media=cdrom`, 'm'))
  })

  test('Floppy Drive: the floppy selector shows the path and keeps the volume ID', async ({ page }) => {
    const vmid = await createVm({ memory: 512, name: 'mirror-floppy-ui' })
    await login(page)
    await openHardware(page, vmid)
    await page.getByRole('button', { name: 'Add' }).click()
    await page.getByRole('menuitem', { name: 'Floppy Drive' }).click()
    const win = page.locator('.x-window').filter({ hasText: 'Add: Floppy Drive' })
    await pickCombo(page, win, 'Storage', STORAGE)
    await pickCombo(page, win, 'Floppy image', 'DOS / 6.22 / disk1.img')
    await win.getByRole('button', { name: 'Add' }).click()
    await expect(win).toBeHidden()
    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^floppy0: ${STORAGE}:floppy/${FLOPPY}(,|$)`, 'm'))
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

async function openHardware(page: Page, vmid: number) {
  await page.goto(`/#v1:0:=qemu%2F${vmid}:4:=hardware`)
  await page.locator('.x-panel').getByText('Hardware', { exact: true }).first().click()
}

/** The mirror storage's content tab `tab` (ISO Images, Floppy Images): its grid panel. */
async function openContent(page: Page, tab: string): Promise<Locator> {
  // The datacenter search grid lists the storage; a double click opens it.
  await page.getByText(`${STORAGE} (${NODE})`, { exact: true }).dblclick()
  await page.getByText(tab, { exact: true }).click()
  return page.locator('.x-grid:visible').filter({ has: page.getByRole('button', { name: 'Upload' }) })
}

function groupHeader(grid: Locator, folder: string): Locator {
  // '<folder icon> Solaris / 2.6 (1)'
  return grid.locator('.x-grid-group-title', {
    hasText: new RegExp(`^\\s*${folder.replaceAll('.', '\\.')} \\(\\d+\\)$`),
  })
}

function cell(grid: Locator, text: string): Locator {
  return grid.locator('.x-grid-cell-inner', { hasText: new RegExp(`^${text.replaceAll('.', '\\.')}$`) })
}

/** Opens the combo labelled `label` in `win` and picks the entry showing `option`. */
async function pickCombo(page: Page, win: Locator, label: string, option: string) {
  // Plain combos open a boundlist, the storage/file selectors a grid picker.
  const entry = page
    .locator('.x-boundlist:visible li, .x-layer.x-grid:visible .x-grid-cell-inner')
    .filter({ hasText: new RegExp(`^${option.replaceAll('.', '\\.')}`) })
    .first()
  // A click right after the window opens can miss the picker (its store still loading): open it again.
  await expect(async () => {
    if (!(await entry.isVisible())) await win.getByLabel(label).click()
    await expect(entry).toBeVisible({ timeout: 2_000 })
  }).toPass({ timeout: 20_000 })
  await entry.click()
}
