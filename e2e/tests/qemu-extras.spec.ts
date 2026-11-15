import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

import { pveExec } from './_pve'

// The optional extras of the installed pve-qemu-kvm. The package build never fails on them (Makefile:
// pve-qemu-3dfx, openbios-sparc32, restore-sparc), so a package without one still publishes; the
// build reports it (build-deb.yml opens an issue), and these fail when a published package lost one.
// Each runs scripts/check-qemu-extras.sh in the container, the check the build runs on the .deb.

const CHECK = readFileSync(new URL('../../scripts/check-qemu-extras.sh', import.meta.url), 'utf8')

async function checkExtra(name: string): Promise<{ code: number; output: string }> {
  return pveExec(['bash', '-c', CHECK, 'check-qemu-extras', '--root', '/', '--only', name])
}

test('3dfx: qemu-system-x86_64-3dfx, built with qemu-3dfx', async () => {
  // KNOWN BUG: missing since 11.1.1-1+wsh1 (2026-10-01). The qemu-3dfx patch doesn't apply to QEMU
  // 11.1 (include/ui/console.h, ui/console.c) and the pve-qemu-3dfx target falls back.
  test.fail(true, 'pve-qemu-kvm without qemu-system-x86_64-3dfx')
  const check = await checkExtra('3dfx')
  expect(check.code, check.output).toBe(0)

  // The revision the guest's wrapper drivers have to match (docs: guides/3dfx).
  const version = await pveExec(['/usr/bin/qemu-system-x86_64-3dfx', '--version'])
  expect(version.code, version.output).toBe(0)
  expect(version.output).toMatch(/featuring qemu-3dfx@[\da-f]{7}/)
})

test('openbios: openbios-sparc32 and QEMU,cgthree.bin built from openbios/', async () => {
  const check = await checkExtra('openbios')
  expect(check.code, check.output).toBe(0)
})

test('sun-proms: ss5.bin, ss10_v2.25_rom and ss20_v2.25_rom', async () => {
  const check = await checkExtra('sun-proms')
  expect(check.code, check.output).toBe(0)
})
