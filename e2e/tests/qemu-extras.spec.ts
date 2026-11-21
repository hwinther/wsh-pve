import { expect, test } from '@playwright/test'

import { checkQemuExtra, pveExec } from './_pve'

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

test('openbios-sparc64: built from openbios/', async () => {
  const check = await checkQemuExtra('openbios-sparc64')
  expect(check.code, check.output).toBe(0)
})

test('sun-proms: ss5.bin, ss10_v2.25_rom, ss20_v2.25_rom and lx.bin', async () => {
  // Packages built before lx.bin was added (up to pve-qemu-kvm 11.1.3-3+wsh6) have the other three;
  // the build's own check on the .deb always expects all four. The PROMs count wherever they came
  // from: the check names the source of each (the package, wsh-sun-proms, or not recorded).
  const hasLx = (await pveExec(['test', '-e', '/usr/share/kvm/lx.bin'])).code === 0
  if (!hasLx) test.info().annotations.push({ description: 'no lx.bin: package from before it was added', type: 'note' })
  const check = await checkQemuExtra('sun-proms', hasLx ? {} : { SUN_PROMS: 'ss5.bin ss10_v2.25_rom ss20_v2.25_rom' })
  expect(check.code, check.output).toBe(0)
  const sources = /\(([^)]*)\)\s*$/m.exec(check.output.trim())
  if (sources) test.info().annotations.push({ description: sources[1], type: 'source' })
})

test('sun-proms: wsh-sun-proms verifies the PROMs there against its manifest', async () => {
  // Only where the wsh-lab package (which has wsh-sun-proms) is installed on the node
  const tool = await pveExec(['sh', '-c', 'command -v wsh-sun-proms'])
  test.skip(tool.code !== 0, 'wsh-sun-proms is not installed (package wsh-lab)')
  const verify = await pveExec(['wsh-sun-proms', 'verify'])
  expect(verify.code, verify.output).toBe(0)
})
