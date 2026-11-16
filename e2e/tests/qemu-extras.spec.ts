import { expect, test } from '@playwright/test'

import { checkQemuExtra, hasCmd646Latch, pveExec } from './_pve'

// The optional extras of the installed pve-qemu-kvm. The package build never fails on them (Makefile:
// pve-qemu-3dfx, openbios-sparc32, restore-sparc), so a package without one still publishes; the
// build reports it (build-deb.yml opens an issue), and these fail when a published package lost one.
// Each runs scripts/check-qemu-extras.sh in the container, the check the build runs on the .deb.

test('3dfx: qemu-system-x86_64-3dfx, built with qemu-3dfx', async () => {
  const check = await checkQemuExtra('3dfx')
  expect(check.code, check.output).toBe(0)

  // The revision the guest's wrapper drivers have to match (docs: guides/3dfx).
  const version = await pveExec(['/usr/bin/qemu-system-x86_64-3dfx', '--version'])
  expect(version.code, version.output).toBe(0)
  expect(version.output).toMatch(/featuring qemu-3dfx@[\da-f]{7}/)
})

test('openbios: openbios-sparc32 and QEMU,cgthree.bin built from openbios/', async () => {
  const check = await checkQemuExtra('openbios')
  expect(check.code, check.output).toBe(0)
})

// TODO: drop the test.fail(!latched) marker and the hasCmd646Latch probe in _pve.ts once the package
// built from this change (pve-qemu wsh/0021, openbios-sparc64 installed by debian/rules) is published.
test('openbios-sparc64: built from openbios/', async () => {
  const latched = await hasCmd646Latch()
  test.fail(!latched, 'pve-qemu-kvm from before openbios-sparc64 was packaged')
  const check = await checkQemuExtra('openbios-sparc64')
  expect(check.code, check.output).toBe(0)
})

test('sun-proms: ss5.bin, ss10_v2.25_rom and ss20_v2.25_rom', async () => {
  const check = await checkQemuExtra('sun-proms')
  expect(check.code, check.output).toBe(0)
})
