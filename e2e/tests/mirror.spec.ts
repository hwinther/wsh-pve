import { expect, type Locator, type Page, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

import { NODE, PASSWORD, type Pve, pveApi, pveExec, serviceLogs, vmConfFile } from './_pve'

// A mirror storage (docs: reference/mirror, `wsh-lab mirror`): a storage whose template/iso and
// template/floppy hold symlinks to media elsewhere (a NAS), the folders kept in the link name with
// '__'. The backend part works with any libpve-storage-perl (stat() follows the link); the folder
// view and the search field above the ISO/floppy selectors are pve-manager's. The UI tests probe the
// installed pve-manager and are skipped on one without them (published packages before them).
// Step 3, renaming a volume in place and linking a volume of another storage in (the API in
// libpve-storage-perl, the Rename and Add link buttons in pve-manager), is probed the same way.
//
// The four ways to use it (reference/mirror), one test each: 0 plain files renamed with '__'
// (PLAIN); 1 a local storage of links (STORAGE); 2 ISOs and links on one NFS export, relative links
// seen through two mount paths (the nfs service of docker-compose.e2e.yml); 3 an externally managed
// tree that changes is e2e/sparc/tests/test_mirror.py (plan/apply/import/tidy).

const STORAGE = 'mirror'
const NAS = '/srv/e2e-nas'
const MIRROR = '/srv/e2e-mirror'
const ISO = 'Solaris__2.6__solaris_2.6_598_sparc.iso'
const ISO_TARGET = `${NAS}/Solaris/2.6/solaris_2.6_598_sparc.iso`
const FLOPPY = 'DOS__6.22__disk1.img'
const FLOPPY_TARGET = `${NAS}/DOS/6.22/disk1.img`
const ISO_SIZE = 3 * 1024 * 1024
// case 0: regular files whose names carry the folders, in an ordinary dir storage
const PLAIN = 'plainnames'
const PLAIN_DIR = '/srv/e2e-plain'
const PLAIN_ISO = 'Plain__Folder__plain-a.iso'

let pve: Pve
let folderUi = false
let searchUi = false
let mediaApi = false
let mediaUi = false

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
rm -rf ${PLAIN_DIR}
mkdir -p ${PLAIN_DIR}/template/iso
truncate -s 1M ${PLAIN_DIR}/template/iso/${PLAIN_ISO}
truncate -s 2M ${PLAIN_DIR}/template/iso/plain-b.iso
pvesm status --storage ${PLAIN} > /dev/null 2>&1 && pvesm remove ${PLAIN}
pvesm add dir ${PLAIN} --path ${PLAIN_DIR} --content iso
`
  const { code, output } = await pveExec(['sh', '-c', script])
  expect(code, output).toBe(0)
  const lib = '/usr/share/pve-manager/js/pvemanagerlib.js'
  folderUi = (await pveExec(['grep', '-q', 'mirrorSeparator', lib])).code === 0
  searchUi = (await pveExec(['grep', '-q', 'isMediaSearch', lib])).code === 0
  mediaApi = (await pveExec(['grep', '-q', 'sub link_media_volume', '/usr/share/perl5/PVE/Storage.pm'])).code === 0
  mediaUi = mediaApi && (await pveExec(['grep', '-q', 'PVE.window.MediaRename', lib])).code === 0
})

test.beforeEach(async ({ request }) => {
  pve = await pveApi(request)
})

test.afterEach(async () => {
  const vms = await pve.get<{ vmid: number }[]>(`/nodes/${NODE}/qemu`)
  for (const { vmid } of vms) await pve.delete(`/nodes/${NODE}/qemu/${vmid}?purge=1&destroy-unreferenced-disks=1`)
})

test.afterAll(async () => {
  await pveExec(['sh', '-c', `pvesm remove ${STORAGE}; pvesm remove ${PLAIN}; rm -rf ${NAS} ${MIRROR} ${PLAIN_DIR}`])
})

interface Volume {
  content: string
  size: number
  unavailable?: number
  volid: string
}

async function content(type: string, storage = STORAGE): Promise<Volume[]> {
  return pve.get<Volume[]>(`/nodes/${NODE}/storage/${storage}/content?content=${type}`)
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

test('storage: a dangling link is not listed (a package without step 3)', async () => {
  // eslint-disable-next-line playwright/no-skipped-test -- the published libpve-storage-perl until step 3
  test.skip(mediaApi, 'the installed libpve-storage-perl lists it as unavailable')
  await pveExec(['ln', '-sf', `${NAS}/gone.iso`, `${MIRROR}/template/iso/Gone__gone.iso`])
  try {
    expect((await content('iso')).map((v) => v.volid)).not.toContain(`${STORAGE}:iso/Gone__gone.iso`)
  } finally {
    await pveExec(['rm', '-f', `${MIRROR}/template/iso/Gone__gone.iso`])
  }
})

test('storage: a dangling link is listed with size 0 and flagged unavailable', async () => {
  // eslint-disable-next-line playwright/no-skipped-test -- until the published libpve-storage-perl has step 3
  test.skip(!mediaApi, 'the installed libpve-storage-perl leaves it out')
  await pveExec(['ln', '-sf', `${NAS}/gone.iso`, `${MIRROR}/template/iso/Gone__gone.iso`])
  try {
    // a link whose target isn't reachable on this node, so it can be seen, renamed or removed
    const isos = await content('iso')
    expect(isos).toContainEqual(
      expect.objectContaining({ size: 0, unavailable: 1, volid: `${STORAGE}:iso/Gone__gone.iso` }),
    )
    expect(isos.find((v) => v.volid === `${STORAGE}:iso/${ISO}`)?.unavailable).toBeUndefined()
    // removing it removes the link
    const gone = contentPath(`${STORAGE}:iso/Gone__gone.iso`)
    await pve.delete(gone + '?delay=5')
    expect((await pveExec(['test', '-L', `${MIRROR}/template/iso/Gone__gone.iso`])).code).not.toBe(0)
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

test('case 0: plain files renamed with __ are volumes under their names, in any VM config', async () => {
  const isos = await content('iso', PLAIN)
  expect(isos.map((v) => v.volid).sort()).toEqual([`${PLAIN}:iso/${PLAIN_ISO}`, `${PLAIN}:iso/plain-b.iso`])
  const vmid = await createVm({ ide2: `${PLAIN}:iso/${PLAIN_ISO},media=cdrom`, memory: 512, name: 'plain-cd' })
  expect(await vmConfFile(vmid)).toMatch(new RegExp(`^ide2: ${PLAIN}:iso/${PLAIN_ISO},media=cdrom`, 'm'))
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

  test('case 0: renamed plain files in a dir storage show their folders', async ({ page }) => {
    await login(page)
    const grid = await openContent(page, 'ISO Images', PLAIN)
    await expect(groupHeader(grid, 'Plain / Folder')).toBeVisible()
    await expect(groupHeader(grid, 'Top level')).toBeVisible()
    await expect(cell(grid, 'plain-a.iso')).toBeVisible()
    await expect(cell(grid, 'plain-b.iso')).toBeVisible()
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
    await pickCombo(page, win.getByLabel('Storage'), STORAGE)
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
    await pickCombo(page, win.getByLabel('Storage'), STORAGE)
    await pickCombo(page, win.getByLabel('Floppy image'), 'DOS / 6.22 / disk1.img')
    await win.getByRole('button', { name: 'Add' }).click()
    await expect(win).toBeHidden()
    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^floppy0: ${STORAGE}:floppy/${FLOPPY}(,|$)`, 'm'))
  })
})

test.describe('web UI: the search field above the ISO and floppy selectors', () => {
  test.beforeEach(() => {
    // eslint-disable-next-line playwright/no-skipped-test -- until the published pve-manager has the search field
    test.skip(!searchUi, 'the installed pve-manager has no search field above the ISO/floppy selectors')
  })

  test('CD/DVD Drive: focused on open, every word must match, Enter picks the first match', async ({ page }) => {
    const vmid = await createVm({ ide2: `${STORAGE}:iso/top-level.iso,media=cdrom`, memory: 512, name: 'search-cd' })
    await login(page)
    await openHardware(page, vmid)
    await page.getByText('CD/DVD Drive (ide2)').dblclick()
    const win = page.locator('.x-window').filter({ hasText: 'Edit: CD/DVD Drive' })
    const search = win.getByLabel('Search')
    await expect(search).toBeFocused()
    // typed right away: any case, words anywhere in the name, folders included
    await page.keyboard.type('SOLARIS 2.6')
    const rows = pickerRows(page)
    await expect(rows.filter({ hasText: 'Solaris / 2.6 / solaris_2.6_598_sparc.iso' })).toBeVisible()
    await expect(rows).toHaveCount(1)
    await search.fill('solaris')
    await expect(rows).toHaveCount(2)
    await search.fill('solaris 7 598')
    await expect(rows).toHaveCount(0)
    await search.fill('sol 7')
    await expect(rows).toHaveCount(1)
    await search.press('Enter')
    await expect(win).toBeVisible() // the first Enter picks, it doesn't submit
    await expect(win.getByLabel('ISO image')).toHaveValue(/sol-7-sparc\.iso/)
    // an empty search shows everything again
    await search.fill('')
    await win.getByLabel('ISO image').click()
    await expect(rows).toHaveCount(3)
    await page.keyboard.press('Escape')
    await win.getByRole('button', { name: 'OK' }).click()
    await expect(win).toBeHidden()
    expect(await vmConfFile(vmid)).toMatch(
      new RegExp(`^ide2: ${STORAGE}:iso/Solaris__7__sol-7-sparc\\.iso,media=cdrom`, 'm'),
    )
  })

  test('CD/DVD Drive: a storage of plain names, and a second Enter submits', async ({ page }) => {
    const vmid = await createVm({ ide2: `${PLAIN}:iso/${PLAIN_ISO},media=cdrom`, memory: 512, name: 'search-plain' })
    await login(page)
    await openHardware(page, vmid)
    await page.getByText('CD/DVD Drive (ide2)').dblclick()
    const win = page.locator('.x-window').filter({ hasText: 'Edit: CD/DVD Drive' })
    await expect(win.getByLabel('Search')).toBeFocused()
    await page.keyboard.type('B.ISO')
    await expect(pickerRows(page)).toHaveCount(1)
    await page.keyboard.press('Enter')
    await expect(win.getByLabel('ISO image')).toHaveValue(/plain-b\.iso/)
    await expect(win.getByRole('button', { name: 'OK' })).toBeEnabled()
    await expect(win.getByLabel('Search')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(win).toBeHidden()
    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^ide2: ${PLAIN}:iso/plain-b\\.iso,media=cdrom`, 'm'))
  })

  test('Floppy Drive: focused on open, filters the floppy selector, Enter picks', async ({ page }) => {
    const vmid = await createVm({ memory: 512, name: 'search-floppy' })
    await login(page)
    await openHardware(page, vmid)
    await page.getByRole('button', { name: 'Add' }).click()
    await page.getByRole('menuitem', { name: 'Floppy Drive' }).click()
    const win = page.locator('.x-window').filter({ hasText: 'Add: Floppy Drive' })
    const search = win.getByLabel('Search')
    await expect(search).toBeFocused()
    await pickCombo(page, win.getByLabel('Storage'), STORAGE)
    await search.fill('dos disk')
    await expect(pickerRows(page).filter({ hasText: 'DOS / 6.22 / disk1.img' })).toBeVisible()
    await search.press('Enter')
    await expect(win.getByLabel('Floppy image')).toHaveValue(/disk1\.img/)
    await win.getByRole('button', { name: 'Add' }).click()
    await expect(win).toBeHidden()
    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^floppy0: ${STORAGE}:floppy/${FLOPPY}(,|$)`, 'm'))
  })

  test('create wizard: the OS tab focuses the search field above the ISO selector', async ({ page }) => {
    await login(page)
    await page.getByRole('button', { name: 'Create VM' }).click()
    const wizard = page.locator('.x-window').filter({ hasText: 'Create: Virtual Machine' })
    await wizard.getByLabel('Name').fill('search-wizard')
    await wizard.getByRole('button', { name: 'Next' }).click()
    // the OS tab also holds the hidden selector of a second (VirtIO driver) CD: the first is the CD's
    const search = wizard.getByLabel('Search').first()
    await expect(search).toBeFocused()
    await pickCombo(page, wizard.getByLabel('Storage').first(), STORAGE)
    await search.fill('598')
    await expect(pickerRows(page)).toHaveCount(1)
    await search.press('Enter')
    await expect(wizard.getByLabel('ISO image').first()).toHaveValue(/solaris_2\.6_598_sparc\.iso/)
    await wizard.locator('.x-tool-close').click()
    await expect(wizard).toBeHidden()
  })
})

// Step 3: PUT .../content/{volume} with `rename`, POST .../storage/{storage}/link-volume, the
// permissions they need, and the refusal on a storage whose links a description file keeps.
const LINK_USER = 'e2e-mirror-link@pve'
const AUDIT_USER = 'e2e-mirror-audit@pve'
const USER_PASSWORD = 'e2e-user-password'
const LINK_PATH = `/nodes/${NODE}/storage/${STORAGE}/link-volume`

function contentPath(volid: string, storage = STORAGE): string {
  return `/nodes/${NODE}/storage/${storage}/content/${volid}`
}

async function readlink(path: string): Promise<string> {
  const { code, output } = await pveExec(['readlink', path])
  expect(code, output).toBe(0)
  return output.trim()
}

test.describe('API: rename and link', () => {
  test.beforeEach(() => {
    // eslint-disable-next-line playwright/no-skipped-test -- until the published libpve-storage-perl has the API
    test.skip(!mediaApi, 'the installed libpve-storage-perl has no rename/link API')
  })

  test.afterAll(async () => {
    await pveExec([
      'sh',
      '-c',
      `pveum user delete ${LINK_USER}; pveum user delete ${AUDIT_USER}
pveum role delete E2EMirrorAllocate; pveum role delete E2EMirrorAudit; rm -f ${MIRROR}/wsh-mirror.yaml`,
    ])
  })

  test('rename: a link is renamed in place, its target stays, the volume ID changes', async () => {
    const volid = `${STORAGE}:iso/Solaris__7__sol-7-sparc.iso`
    const renamed = `${STORAGE}:iso/Sun__Solaris_7__sol-7-sparc.iso`
    await pve.put(contentPath(volid), { rename: 'Sun__Solaris_7__sol-7-sparc.iso' })
    try {
      expect(await readlink(`${MIRROR}/template/iso/Sun__Solaris_7__sol-7-sparc.iso`)).toBe(
        `${NAS}/Solaris/7/sol-7-sparc.iso`,
      )
      const ids = (await content('iso')).map((v) => v.volid)
      expect(ids).toContain(renamed)
      expect(ids).not.toContain(volid)
      expect((await pveExec(['test', '-f', `${NAS}/Solaris/7/sol-7-sparc.iso`])).code).toBe(0)
    } finally {
      await pve.put(contentPath(renamed), { rename: 'Solaris__7__sol-7-sparc.iso' })
    }
  })

  test('rename: a regular file and a floppy image', async () => {
    await pve.put(contentPath(`${PLAIN}:iso/plain-b.iso`, PLAIN), { rename: 'Moved__plain-b.iso' })
    expect((await pveExec(['test', '-f', `${PLAIN_DIR}/template/iso/Moved__plain-b.iso`])).code).toBe(0)
    await pve.put(contentPath(`${PLAIN}:iso/Moved__plain-b.iso`, PLAIN), { rename: 'plain-b.iso' })
    await pve.put(contentPath(`${STORAGE}:floppy/${FLOPPY}`), { rename: 'MS-DOS__disk1.img' })
    expect(await content('floppy')).toContainEqual(
      expect.objectContaining({ size: 1440 * 1024, volid: `${STORAGE}:floppy/MS-DOS__disk1.img` }),
    )
    await pve.put(contentPath(`${STORAGE}:floppy/MS-DOS__disk1.img`), { rename: FLOPPY })
  })

  test('rename: refuses a name that exists, a slash, another extension, and other attributes with it', async () => {
    const path = contentPath(`${STORAGE}:iso/top-level.iso`)
    expect((await pve.refused('PUT', path, { rename: ISO })).message).toContain('already exists')
    expect((await pve.refused('PUT', path, { rename: 'Solaris/top.iso' })).message).toContain("without '/'")
    expect((await pve.refused('PUT', path, { rename: 'top-level.vfd' })).message).toContain('end in .iso or .img')
    expect((await pve.refused('PUT', path, { notes: 'x', rename: 'x.iso' })).message).toContain("can't be combined")
    expect((await pveExec(['test', '-L', `${MIRROR}/template/iso/top-level.iso`])).code).toBe(0)
  })

  test('link: a volume of another storage, relative on one file system, listed with its size', async () => {
    const volid = await pve.post<string>(LINK_PATH, {
      filename: 'Linked__plain-b.iso',
      'source-storage': PLAIN,
      volume: 'iso/plain-b.iso',
    })
    try {
      expect(volid).toBe(`${STORAGE}:iso/Linked__plain-b.iso`)
      // both storages are on the container's file system: a relative link, as `wsh-lab mirror` makes
      expect(await readlink(`${MIRROR}/template/iso/Linked__plain-b.iso`)).toBe(
        '../../../e2e-plain/template/iso/plain-b.iso',
      )
      expect(await content('iso')).toContainEqual(expect.objectContaining({ size: 2 * 1024 * 1024, volid }))
      // the source volume's full ID works too; a name that exists is refused
      const again = await pve.refused('POST', LINK_PATH, {
        filename: 'Linked__plain-b.iso',
        'source-storage': PLAIN,
        volume: `${PLAIN}:iso/plain-b.iso`,
      })
      expect(again.message).toContain('already exists')
    } finally {
      await pveExec(['rm', '-f', `${MIRROR}/template/iso/Linked__plain-b.iso`])
    }
  })

  test('link: refuses a source in the same storage, a missing source and a bad name', async () => {
    const same = await pve.refused('POST', LINK_PATH, {
      filename: 'x.iso',
      'source-storage': STORAGE,
      volume: `iso/${ISO}`,
    })
    expect(same.message).toContain('rename the volume instead')
    const missing = await pve.refused('POST', LINK_PATH, {
      filename: 'x.iso',
      'source-storage': PLAIN,
      volume: 'iso/nope.iso',
    })
    expect(missing.message).toContain("isn't a file on this node")
    const bad = await pve.refused('POST', LINK_PATH, {
      filename: 'With space.iso',
      'source-storage': PLAIN,
      volume: 'iso/plain-b.iso',
    })
    expect(bad.message).toContain('only A-Z a-z 0-9')
  })

  test('permissions: rename needs Datastore.Allocate, link needs it on both storages', async ({ request }) => {
    await sh(`pveum role add E2EMirrorAllocate --privs Datastore.Allocate,Datastore.Audit
pveum role add E2EMirrorAudit --privs Datastore.Audit,Datastore.AllocateSpace
pveum user add ${LINK_USER} --password ${USER_PASSWORD}
pveum user add ${AUDIT_USER} --password ${USER_PASSWORD}
pveum acl modify /storage/${STORAGE} --users ${LINK_USER} --roles E2EMirrorAllocate
pveum acl modify /storage/${PLAIN} --users ${LINK_USER} --roles E2EMirrorAudit
pveum acl modify /storage/${STORAGE} --users ${AUDIT_USER} --roles E2EMirrorAudit`)
    const audit = await pveApi(request, { password: USER_PASSWORD, username: AUDIT_USER })
    const byAudit = await audit.refused('PUT', contentPath(`${STORAGE}:iso/top-level.iso`), {
      rename: 'Top__top-level.iso',
    })
    expect(byAudit.status).toBe(403)

    const linker = await pveApi(request, { password: USER_PASSWORD, username: LINK_USER })
    await linker.put(contentPath(`${STORAGE}:iso/top-level.iso`), { rename: 'Top__top-level.iso' })
    await linker.put(contentPath(`${STORAGE}:iso/Top__top-level.iso`), { rename: 'top-level.iso' })
    const link = { filename: 'Perm__plain-b.iso', 'source-storage': PLAIN, volume: 'iso/plain-b.iso' }
    // Datastore.Audit on the source isn't enough: the link hands the volume to everyone who may use the mirror
    expect((await linker.refused('POST', LINK_PATH, link)).status).toBe(403)
    await sh(`pveum acl modify /storage/${PLAIN} --users ${LINK_USER} --roles E2EMirrorAllocate`)
    expect(await linker.post<string>(LINK_PATH, link)).toBe(`${STORAGE}:iso/Perm__plain-b.iso`)
    await pveExec(['rm', '-f', `${MIRROR}/template/iso/Perm__plain-b.iso`])
  })

  test('a storage with a description file: rename and link are refused, the status says why', async () => {
    await sh(`printf 'version: 1\\nstorage: ${STORAGE}\\n' > ${MIRROR}/wsh-mirror.yaml`)
    try {
      const status = await pve.get<Record<string, unknown>>(`/nodes/${NODE}/storage/${STORAGE}/status`)
      expect(status['mirror-described']).toBe(1)
      const rename = await pve.refused('PUT', contentPath(`${STORAGE}:iso/top-level.iso`), { rename: 'x.iso' })
      expect(rename.message).toContain('description file')
      expect(rename.message).toContain('wsh-lab mirror apply')
      const link = await pve.refused('POST', LINK_PATH, {
        filename: 'x.iso',
        'source-storage': PLAIN,
        volume: 'iso/plain-b.iso',
      })
      expect(link.message).toContain('description file')
    } finally {
      await pveExec(['rm', '-f', `${MIRROR}/wsh-mirror.yaml`])
    }
    const status = await pve.get<Record<string, unknown>>(`/nodes/${NODE}/storage/${STORAGE}/status`)
    expect(status['mirror-described']).toBeUndefined()
  })
})

test.describe('web UI: rename and link', () => {
  test.beforeEach(() => {
    // eslint-disable-next-line playwright/no-skipped-test -- until the published packages have step 3
    test.skip(!mediaUi, 'the installed packages have no Rename / Add link in the ISO and floppy tabs')
  })

  test('Rename: folder and file name, the new volume ID, the VMs that use it', async ({ page }) => {
    const volid = `${STORAGE}:iso/Solaris__7__sol-7-sparc.iso`
    const vmid = await createVm({ ide2: `${volid},media=cdrom`, memory: 512, name: 'rename-user' })
    await login(page)
    const grid = await openContent(page, 'ISO Images')
    await cell(grid, 'sol-7-sparc.iso').click()
    await grid.getByRole('button', { name: 'Rename' }).click()
    const win = page.locator('.x-window').filter({ hasText: 'Current volume' })
    await expect(win.getByLabel('Folder')).toHaveValue('Solaris / 7')
    await expect(win.getByLabel('File name')).toHaveValue('sol-7-sparc.iso')
    await expect(win).toContainText(`Used by: ${vmid} (rename-user)`)
    // an extension of another content type can't be submitted
    await win.getByLabel('File name').fill('sol-7-sparc.vfd')
    await expect(win).toContainText('The file name must end in .iso, .img')
    await expect(win.getByRole('button', { name: 'Rename' })).toBeDisabled()
    await win.getByLabel('File name').fill('sol-7-sparc.iso')
    await win.getByLabel('Folder').fill('Sun / Solaris 7')
    await expect(win).toContainText(`${STORAGE}:iso/Sun__Solaris_7__sol-7-sparc.iso`)
    await win.getByRole('button', { name: 'Rename' }).click()
    await expect(win).toBeHidden()
    try {
      await expect(groupHeader(grid, 'Sun / Solaris_7')).toBeVisible()
      expect(await readlink(`${MIRROR}/template/iso/Sun__Solaris_7__sol-7-sparc.iso`)).toBe(
        `${NAS}/Solaris/7/sol-7-sparc.iso`,
      )
      // the VM still names the old volume ID
      expect(await vmConfFile(vmid)).toMatch(new RegExp(`^ide2: ${volid},media=cdrom`, 'm'))
    } finally {
      await pveExec([
        'mv',
        `${MIRROR}/template/iso/Sun__Solaris_7__sol-7-sparc.iso`,
        `${MIRROR}/template/iso/Solaris__7__sol-7-sparc.iso`,
      ])
    }
  })

  test('Add link from storage: the search-field selector, then folder and name', async ({ page }) => {
    await login(page)
    const grid = await openContent(page, 'ISO Images')
    await grid.getByRole('button', { name: 'Add link from storage' }).click()
    const win = page.locator('.x-window').filter({ hasText: 'Add link from storage' })
    await expect(win.getByLabel('Search')).toBeFocused()
    // the storage the link goes into isn't offered as a source
    const storages = page.locator('.x-layer.x-grid:visible .x-grid-cell-inner')
    await expect(async () => {
      if (!(await storages.first().isVisible())) await win.getByLabel('Storage').click()
      await expect(storages.filter({ hasText: /^plainnames$/ })).toBeVisible({ timeout: 2_000 })
    }).toPass({ timeout: 20_000 })
    await expect(storages.filter({ hasText: /^local$/ })).toBeVisible()
    await expect(storages.filter({ hasText: /^mirror$/ })).toBeHidden()
    await storages.filter({ hasText: /^plainnames$/ }).click()
    await expect(win.getByLabel('Storage')).toHaveValue(PLAIN)
    await win.getByLabel('Search').fill('plain-b')
    await expect(pickerRows(page)).toHaveCount(1)
    await win.getByLabel('Search').press('Enter')
    await expect(win.getByLabel('File name')).toHaveValue('plain-b.iso')
    await win.getByLabel('Folder').fill('Linked')
    await expect(win).toContainText(`${STORAGE}:iso/Linked__plain-b.iso`)
    await win.getByRole('button', { name: 'Add link' }).click()
    await expect(win).toBeHidden()
    try {
      await expect(groupHeader(grid, 'Linked')).toBeVisible()
      expect(await readlink(`${MIRROR}/template/iso/Linked__plain-b.iso`)).toBe(
        '../../../e2e-plain/template/iso/plain-b.iso',
      )
    } finally {
      await pveExec(['rm', '-f', `${MIRROR}/template/iso/Linked__plain-b.iso`])
    }
  })

  test('hidden on a storage with a description file; an unavailable link flagged, not offered', async ({ page }) => {
    await sh(`printf 'version: 1\\n' > ${MIRROR}/wsh-mirror.yaml
ln -sf ${NAS}/gone.iso ${MIRROR}/template/iso/Gone__gone.iso`)
    // created before the login, so the web UI's resource list has it
    const vmid = await createVm({ ide2: 'none,media=cdrom', memory: 512, name: 'unavailable-cd' })
    try {
      await login(page)
      const grid = await openContent(page, 'ISO Images')
      await expect(grid.locator('.x-grid-row', { hasText: 'gone.iso' })).toContainText('(unavailable on this node)')
      await expect(grid.getByRole('button', { name: 'Upload' })).toBeVisible()
      await expect(grid.getByRole('button', { name: 'Rename' })).toBeHidden()
      await expect(grid.getByRole('button', { name: 'Add link from storage' })).toBeHidden()
      // the selectors leave it out
      await openHardware(page, vmid)
      await page.getByText('CD/DVD Drive (ide2)').dblclick()
      const win = page.locator('.x-window').filter({ hasText: 'Edit: CD/DVD Drive' })
      await win.getByText('Use CD/DVD disc image file (iso)').click()
      await pickCombo(page, win.getByLabel('Storage'), STORAGE)
      await win.getByLabel('ISO image').click()
      await expect(pickerRows(page).filter({ hasText: 'top-level.iso' })).toBeVisible()
      await expect(pickerRows(page).filter({ hasText: 'gone.iso' })).toBeHidden()
    } finally {
      await pveExec(['rm', '-f', `${MIRROR}/wsh-mirror.yaml`, `${MIRROR}/template/iso/Gone__gone.iso`])
    }
  })
})

// Case 2: the ISOs and the mirror's links on one NFS export (from the nfs service, NFS-Ganesha in user
// space), mounted by PVE as an NFS storage; links relative, so a second mount of the same export at
// another path finds the files too. Without the nfs service, where the runner can't mount NFS, or where
// the export fails the probe (what the tool does on it: files and directories created, renamed and
// removed, a symlink replaced by rename) the same checks run on a dir storage and a bind mount; the
// test says so in an annotation and attaches the probe's output and the NFS server's log.
//
// NFS 4.0, not 4.1/4.2: Linux 7.0 (GitHub's runner) asks for directory delegations
// (GET_DIR_DELEGATION, 4.1+), NFS-Ganesha 6.5 answers NFS4ERR_OP_ILLEGAL, and removing a directory
// tree then fails (`rm -r`: EISDIR, EREMOTEIO). 4.0 has no directory delegations; the probe still
// tries 4.1 and 4.2 when it fails, and reports which work.
const NFS = 'e2enfs'
const NFS_ALT = '/mnt/e2e-nfs-alt'
const NFS_FALLBACK = '/srv/e2e-export'
const MIRROR_PY = '/root/wsh-mirror.py'
// What the tool does on the export, on scratch names; each step is echoed, so a failure names it.
const PROBE = `set -e
cd "$1"
p=.wsh-mirror-probe.$$
step() { echo "+ $*"; "$@"; }
step mkdir -p $p/dir/sub
step sh -c "echo data > $p/dir/file"
step mv $p/dir/file $p/dir/moved
step ln -s dir/moved $p/link
step ln -s dir/sub $p/link.tmp
step mv -T $p/link.tmp $p/link
step rm $p/link $p/dir/moved
step rmdir $p/dir/sub
step rmdir $p/dir
step mkdir -p $p/tree/a/b
step touch $p/tree/a/file
step rm -r $p/tree
step rmdir $p
echo probe ok`
// The probe through other mount options of the same export ($1), to tell a client from a server problem
const VARIANT = `mkdir -p /mnt/e2e-nfs-v && mount -t nfs4 -o "$1" nfs:/export /mnt/e2e-nfs-v || exit 1
sh -c "$2" probe /mnt/e2e-nfs-v; rc=$?
umount /mnt/e2e-nfs-v
exit $rc`
let nfsRoot = ''
let nfsNote = ''

async function sh(script: string): Promise<string> {
  const { code, output } = await pveExec(['sh', '-c', script])
  expect(code, output).toBe(0)
  return output
}

async function mirrorTool(args: string): Promise<{ code: number; output: string }> {
  return pveExec(['sh', '-c', `python3 ${MIRROR_PY} ${args}`])
}

test.describe('case 2: ISOs and links on one NFS export', () => {
  test.beforeAll(async ({}, testInfo) => {
    // the tool from this checkout, not the installed wsh-lab
    const py = gzipSync(readFileSync(new URL('../sparc/mirror.py', import.meta.url))).toString('base64')
    const copied = await pveExec(['sh', '-c', `echo "$1" | base64 -d | gunzip > ${MIRROR_PY}`, 'sh', py])
    expect(copied.code, copied.output).toBe(0)
    const nfs = await pveExec([
      'sh',
      '-c',
      `set -e
getent hosts nfs > /dev/null
pvesm status --storage ${NFS} > /dev/null 2>&1 && pvesm remove ${NFS}
pvesm add nfs ${NFS} --server nfs --export /export --options vers=4.0 --content iso,floppy
pvesm status --storage ${NFS} > /dev/null
mountpoint -q /mnt/pve/${NFS}
mkdir -p ${NFS_ALT}
mount -t nfs4 -o vers=4.0 nfs:/export ${NFS_ALT}`,
    ])
    const probe = nfs.code === 0 ? await pveExec(['sh', '-c', PROBE, 'probe', `/mnt/pve/${NFS}`]) : nfs
    if (probe.code === 0) {
      nfsRoot = `/mnt/pve/${NFS}`
    } else {
      const why = probe.output.trim().split('\n').slice(-2).join(': ')
      const what = nfs.code === 0 ? 'the NFS export failed the probe' : 'no NFS'
      nfsNote = `${what} (${why}): a dir storage and a bind mount instead`
      await testInfo.attach('nfs-probe.txt', { body: probe.output, contentType: 'text/plain' })
      await testInfo.attach('nfs-server.log', { body: await serviceLogs('nfs', 3000), contentType: 'text/plain' })
      if (nfs.code === 0) {
        const variants = [`kernel ${(await pveExec(['uname', '-r'])).output.trim()}`]
        for (const opts of ['vers=4.1', 'vers=4.2']) {
          const v = await pveExec(['sh', '-c', VARIANT, 'variant', opts, PROBE])
          variants.push(`${opts}: ${v.code === 0 ? 'ok' : v.output.trim().split('\n').slice(-2).join(': ')}`)
        }
        await testInfo.attach('nfs-variants.txt', { body: variants.join('\n'), contentType: 'text/plain' })
        console.log(variants.join('\n'))
      }
      console.log(`${nfsNote}\n${probe.output}\n${await serviceLogs('nfs', 60)}`)
      await pveExec(['umount', NFS_ALT])
      nfsRoot = NFS_FALLBACK
      await sh(`umount /mnt/pve/${NFS} 2> /dev/null; pvesm remove ${NFS} 2> /dev/null
mkdir -p ${NFS_FALLBACK} ${NFS_ALT}
pvesm add dir ${NFS} --path ${NFS_FALLBACK} --content iso,floppy
mount --bind ${NFS_FALLBACK} ${NFS_ALT}`)
    }
    await sh(`set -e
cd ${nfsRoot}
rm -rf archive template wsh-mirror.yaml .wsh-mirror-state.json .wsh-mirror.lock
mkdir -p archive/Solaris/2.6 archive/DOS archive/Incoming
truncate -s ${ISO_SIZE} archive/Solaris/2.6/sol26.iso
truncate -s 1440K archive/DOS/disk1.img
truncate -s 1M archive/Incoming/still-loading.iso.part
printf 'version: 1\\nstorage: ${NFS}\\nwatch:\\n  - archive\\nincomplete:\\n  min_age: 0\\n' > wsh-mirror.yaml
python3 ${MIRROR_PY} import --storage ${NFS}
python3 ${MIRROR_PY} apply --storage ${NFS}`)
  })

  test.beforeEach(() => {
    if (nfsNote) test.info().annotations.push({ description: nfsNote, type: 'fallback' })
  })

  test.afterAll(async () => {
    await pveExec([
      'sh',
      '-c',
      `python3 ${MIRROR_PY} timer --storage ${NFS} --remove > /dev/null 2>&1
rm -rf ${nfsRoot}/archive ${nfsRoot}/template ${nfsRoot}/wsh-mirror.yaml ${nfsRoot}/.wsh-mirror-state.json ${nfsRoot}/.wsh-mirror.lock
umount ${NFS_ALT}; pvesm remove ${NFS}; umount /mnt/pve/${NFS} 2> /dev/null; rm -rf ${NFS_FALLBACK} ${MIRROR_PY}`,
    ])
  })

  test('relative links, listed by PVE, found through a second mount path of the same export', async () => {
    const link = `template/iso/Solaris__2.6__sol26.iso`
    expect((await sh(`readlink ${nfsRoot}/${link}`)).trim()).toBe('../../archive/Solaris/2.6/sol26.iso')
    expect((await sh(`readlink ${nfsRoot}/template/floppy/DOS__disk1.img`)).trim()).toBe('../../archive/DOS/disk1.img')
    const isos = await content('iso', NFS)
    expect(isos).toContainEqual(
      expect.objectContaining({ size: ISO_SIZE, volid: `${NFS}:iso/Solaris__2.6__sol26.iso` }),
    )
    // the file still being written is not linked
    expect(isos.map((v) => v.volid).join()).not.toContain('still-loading')
    expect(await content('floppy', NFS)).toContainEqual(
      expect.objectContaining({ size: 1440 * 1024, volid: `${NFS}:floppy/DOS__disk1.img` }),
    )
    // the same link through the other mount path leads to the file under that path
    expect((await sh(`readlink -f ${NFS_ALT}/${link}`)).trim()).toBe(`${NFS_ALT}/archive/Solaris/2.6/sol26.iso`)
    expect((await sh(`stat -L -c %s ${NFS_ALT}/${link}`)).trim()).toBe(String(ISO_SIZE))
    const vmid = await createVm({ ide2: `${NFS}:iso/Solaris__2.6__sol26.iso,media=cdrom`, memory: 512, name: 'nfs-cd' })
    expect(await vmConfFile(vmid)).toMatch(new RegExp(`^ide2: ${NFS}:iso/Solaris__2.6__sol26\\.iso,media=cdrom`, 'm'))
    const { code, output } = await pveExec(['qm', 'showcmd', String(vmid), '--pretty'])
    expect(code, output).toBe(0)
    expect(output).toContain(`${nfsRoot}/${link}`)
  })

  test('apply is idempotent and gives up while another holds the lock on the export', async () => {
    const again = await mirrorTool(`apply --storage ${NFS}`)
    expect(again.code, again.output).toBe(0)
    expect(again.output).toContain('0 linked, 0 relinked, 0 unlinked, 2 in place')
    // the lock file through the other mount path is the same file on the export
    const busy = await pveExec([
      'sh',
      '-c',
      `flock ${NFS_ALT}/.wsh-mirror.lock python3 ${MIRROR_PY} apply --storage ${NFS}; echo "rc=$?"`,
    ])
    expect(busy.output).toContain('rc=75')
  })

  test('timer: a systemd timer whose service runs apply, and --remove', async () => {
    // a new file under the watched folder: linked by the timer's apply with auto_import
    await sh(`set -e
cd ${nfsRoot}
sed -i 's/^watch:/auto_import: true\\nwatch:/' wsh-mirror.yaml
mkdir -p archive/NetBSD && truncate -s 2M archive/NetBSD/netbsd.iso
python3 ${MIRROR_PY} timer --storage ${NFS} --interval 1h
systemctl is-enabled wsh-lab-mirror-${NFS}.timer
systemctl start wsh-lab-mirror-${NFS}.service`)
    expect((await sh(`readlink ${nfsRoot}/template/iso/NetBSD__netbsd.iso`)).trim()).toBe(
      '../../archive/NetBSD/netbsd.iso',
    )
    await sh(`python3 ${MIRROR_PY} timer --storage ${NFS} --remove
test ! -e /etc/systemd/system/wsh-lab-mirror-${NFS}.timer`)
  })

  test('step 3: no rename on the described export; its ISO linked into the local mirror', async () => {
    // eslint-disable-next-line playwright/no-skipped-test -- until the published libpve-storage-perl has the API
    test.skip(!mediaApi, 'the installed libpve-storage-perl has no rename/link API')
    const refused = await pve.refused('PUT', contentPath(`${NFS}:iso/Solaris__2.6__sol26.iso`, NFS), {
      rename: 'Other__sol26.iso',
    })
    expect(refused.message).toContain('description file')
    // a volume of the NFS storage (itself a relative link on the export) linked into the local mirror
    const volid = await pve.post<string>(LINK_PATH, {
      filename: 'NFS__sol26.iso',
      'source-storage': NFS,
      volume: 'iso/Solaris__2.6__sol26.iso',
    })
    try {
      expect(await content('iso')).toContainEqual(expect.objectContaining({ size: ISO_SIZE, volid }))
      const text = await readlink(`${MIRROR}/template/iso/NFS__sol26.iso`)
      // the NFS mount is another file system: absolute, the mount path PVE uses on every node; the
      // fallback's dir storage is on the container's file system: relative
      expect(text).toBe(
        nfsNote
          ? '../../../e2e-export/template/iso/Solaris__2.6__sol26.iso'
          : `/mnt/pve/${NFS}/template/iso/Solaris__2.6__sol26.iso`,
      )
    } finally {
      await pveExec(['rm', '-f', `${MIRROR}/template/iso/NFS__sol26.iso`])
    }
  })
})

/** The rows of the open ISO/floppy picker. */
function pickerRows(page: Page): Locator {
  return page.locator('.x-layer.x-grid:visible .x-grid-row')
}

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

/** A storage's content tab `tab` (ISO Images, Floppy Images): its grid panel. */
async function openContent(page: Page, tab: string, storage = STORAGE): Promise<Locator> {
  // The datacenter search grid lists the storage; a double click opens it.
  await page.getByText(`${storage} (${NODE})`, { exact: true }).dblclick()
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

/** Opens the combo `field` and picks the entry showing `option`. */
async function pickCombo(page: Page, field: Locator, option: string) {
  // Plain combos open a boundlist, the storage/file selectors a grid picker.
  const entry = page
    .locator('.x-boundlist:visible li, .x-layer.x-grid:visible .x-grid-cell-inner')
    .filter({ hasText: new RegExp(`^${option.replaceAll('.', '\\.')}`) })
    .first()
  // A click right after the window opens can miss the picker (its store still loading): open it again.
  await expect(async () => {
    if (!(await entry.isVisible())) await field.click()
    await expect(entry).toBeVisible({ timeout: 2_000 })
  }).toPass({ timeout: 20_000 })
  await entry.click()
}
