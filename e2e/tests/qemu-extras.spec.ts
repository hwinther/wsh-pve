import { expect, test } from '@playwright/test'

import { checkQemuExtra, has3dfx, pveExec } from './_pve'

// The optional extras of the installed pve-qemu-kvm. The package build never fails on them (Makefile:
// pve-qemu-3dfx, openbios-sparc32, restore-sparc), so a package without one still publishes; the
// build reports it (build-deb.yml opens an issue), and these fail when a published package lost one.
// Each runs scripts/check-qemu-extras.sh in the container, the check the build runs on the .deb.

test('3dfx: qemu-system-x86_64-3dfx, built with qemu-3dfx', async () => {
  // TODO: remove this marker once a pve-qemu-kvm with qemu-system-x86_64-3dfx is published at
  // debian.wshosting.no. The published ones have had none since 11.1.1-1+wsh1 (2026-10-01: the
  // qemu-3dfx patch stopped applying to QEMU 11.1), and the e2e runs of PRs and main install those.
  test.fail(!(await has3dfx()), 'installed pve-qemu-kvm has no qemu-system-x86_64-3dfx (not published yet)')
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

test('sun-proms: ss5.bin, ss10_v2.25_rom and ss20_v2.25_rom', async () => {
  const check = await checkQemuExtra('sun-proms')
  expect(check.code, check.output).toBe(0)
})
