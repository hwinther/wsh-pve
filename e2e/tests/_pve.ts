import { type APIRequestContext, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import http from 'node:http'

// Helpers for the PVE node under test: its API (with a root@pam ticket) and commands run inside the
// container (qm showcmd, reading /etc/pve), through the Docker Engine API so the tests need no docker
// CLI. DOCKER_HOST=tcp://host:port or the default /var/run/docker.sock.

export const NODE = process.env.PVE_NODE ?? 'pve'
export const CONTAINER = process.env.PVE_CONTAINER ?? 'wsh-pve-e2e'
export const PASSWORD = process.env.PVE_ROOT_PASSWORD ?? 'e2e-password'

export interface Pve {
  get: <T>(path: string) => Promise<T>
  post: <T>(path: string, form: Record<string, number | string>) => Promise<T>
  /** A synchronous PUT (a config update applied to a running VM right away). */
  put: <T>(path: string, form: Record<string, number | string>) => Promise<T>
  delete: (path: string) => Promise<void>
  /** A POST/PUT expected to fail: its status and the error text (status line and body). */
  refused: (method: 'POST' | 'PUT', path: string, form: Record<string, number | string>) => Promise<Refusal>
}

export interface Refusal {
  status: number
  message: string
}

/** An API client authenticated as root@pam, or another user (ticket cookie + CSRF header). */
export async function pveApi(
  request: APIRequestContext,
  { password = PASSWORD, username = 'root@pam' }: { password?: string; username?: string } = {},
): Promise<Pve> {
  const login = await request.post('/api2/json/access/ticket', {
    form: { password, username },
  })
  expect(login.ok(), await login.text()).toBe(true)
  const { data } = (await login.json()) as { data: { CSRFPreventionToken: string; ticket: string } }
  const headers = { Cookie: `PVEAuthCookie=${data.ticket}`, CSRFPreventionToken: data.CSRFPreventionToken }

  const unwrap = async <T>(res: Awaited<ReturnType<APIRequestContext['get']>>): Promise<T> => {
    expect(res.ok(), `${res.url()}: ${res.status()} ${await res.text()}`).toBe(true)
    return ((await res.json()) as { data: T }).data
  }
  return {
    delete: async (path) => {
      await unwrap(await request.delete(`/api2/json${path}`, { headers }))
    },
    get: async (path) => unwrap(await request.get(`/api2/json${path}`, { headers })),
    post: async (path, form) => unwrap(await request.post(`/api2/json${path}`, { form, headers })),
    put: async (path, form) => unwrap(await request.put(`/api2/json${path}`, { form, headers })),
    refused: async (method, path, form) => {
      const res = await request.fetch(`/api2/json${path}`, { form, headers, method })
      const body = await res.text()
      expect(res.ok(), `${method} ${path} succeeded: ${body}`).toBe(false)
      return { message: `${res.statusText()} ${body}`, status: res.status() }
    },
  }
}

const CHECK_QEMU_EXTRAS = readFileSync(new URL('../../scripts/check-qemu-extras.sh', import.meta.url), 'utf8')

/**
 * scripts/check-qemu-extras.sh for one optional extra of the installed pve-qemu-kvm (3dfx, openbios,
 * openbios-sparc64, sun-proms): exit code 0 when it's there, 1 when it isn't.
 */
export async function checkQemuExtra(
  name: string,
  env: Record<string, string> = {},
): Promise<{ code: number; output: string }> {
  const vars = Object.entries(env).map(([k, v]) => `${k}=${v}`)
  return pveExec(['env', ...vars, 'bash', '-c', CHECK_QEMU_EXTRAS, 'check-qemu-extras', '--root', '/', '--only', name])
}

/** Runs a command in the PVE container and returns its combined output and exit code. */
export async function pveExec(cmd: string[]): Promise<{ code: number; output: string }> {
  const created = (await docker('POST', `/containers/${CONTAINER}/exec`, {
    AttachStderr: true,
    AttachStdout: true,
    Cmd: cmd,
    Tty: true, // one raw stream, no multiplexing headers
  })) as { Id: string }
  const output = (await docker('POST', `/exec/${created.Id}/start`, { Detach: false, Tty: true }, true)) as string
  const { ExitCode } = (await docker('GET', `/exec/${created.Id}/json`)) as { ExitCode: number }
  return { code: ExitCode, output }
}

/**
 * The last lines of the log of a compose service's container (by the compose service label), for a
 * test to attach when a helper service misbehaves. '' when there is no such container.
 */
export async function serviceLogs(service: string, tail = 200): Promise<string> {
  const filters = encodeURIComponent(JSON.stringify({ label: [`com.docker.compose.service=${service}`] }))
  const [found] = (await docker('GET', `/containers/json?filters=${filters}`)) as { Id: string }[]
  if (!found) return ''
  const path = `/containers/${found.Id}/logs?stdout=1&stderr=1&tail=${tail}`
  const raw = (await docker('GET', path, undefined, 'buffer')) as Buffer
  // without a TTY the log is frames: an 8-byte header (stream, 0, 0, 0, size as uint32 BE), then the text
  const lines: string[] = []
  for (let at = 0; at + 8 <= raw.length;) {
    const size = raw.readUInt32BE(at + 4)
    lines.push(raw.subarray(at + 8, at + 8 + size).toString('utf8'))
    at += 8 + size
  }
  return lines.join('')
}

/**
 * Whether the installed qemu-server gives the 3dfx binary OPENGLIDE_DIR, a directory of the VM's for
 * OpenGLide's files. TODO: remove with its test.fail() once a qemu-server with it is published.
 */
export async function hasQemu3dfxDir(): Promise<boolean> {
  const probe = await pveExec([
    'perl',
    '-MPVE::QemuServer::Helpers',
    '-e',
    `print defined(&PVE::QemuServer::Helpers::prepare_qemu_3dfx_env) ? 'dir=yes' : 'dir=no';`,
  ])
  expect(probe.output, probe.output).toMatch(/^dir=(yes|no)$/m)
  return probe.output.includes('dir=yes')
}

/** Whether the file in the container contains the text (a probe of an installed package). */
async function installedHas(file: string, text: string): Promise<boolean> {
  return (await pveExec(['grep', '-qF', '--', text, file])).code === 0
}

/**
 * Whether the installed qemu-server refuses efidisk0 and tpmstate0 on sparc32 (up to 9.2.20+wsh3 it
 * took a tpmstate0, and the VM then failed to start: qemu-system-sparc has no tpm-tis).
 * TODO: remove with its test.fail() once a qemu-server with it is published.
 */
export async function qemuServerRefusesSparcFwDisks(): Promise<boolean> {
  return installedHas('/usr/share/perl5/PVE/QemuServer/Machine.pm', 'sun4m has no UEFI firmware and no TPM')
}

/**
 * Whether the installed qemu-server prints nothing but the command in `qm showcmd` for a VM with a
 * vga `server` (up to 9.2.20+wsh3 it printed "-- Using <display> display ..." first).
 * TODO: remove with its test.fail() once a qemu-server with it is published.
 */
export async function qemuServerShowcmdClean(): Promise<boolean> {
  return !(await installedHas('/usr/share/perl5/PVE/QemuServer.pm', '-- Using $displayType display'))
}

/**
 * Whether the installed pve-manager hides EFI Disk and TPM State on sparc (Hardware → Add and the
 * create wizard's Add TPM). TODO: remove with its test.fail() once a pve-manager with it is published.
 */
export async function pveManagerHidesSparcFwDisks(): Promise<boolean> {
  return installedHas('/usr/share/pve-manager/js/pvemanagerlib.js', 'efidisk_menuitem.setHidden(isSparc)')
}

/**
 * Whether the installed qemu-server has the GL display of a 3dfx VM (`vga: ...,mesa-display=...`).
 * TODO: remove with the skips once a qemu-server with it is published.
 */
export async function qemuServerHasMesaDisplay(): Promise<boolean> {
  return installedHas('/usr/share/perl5/PVE/QemuServer.pm', "'mesa-display' => {")
}

/**
 * Whether the installed pve-manager has the "3DFX/Mesa display" field in the Display dialog.
 * TODO: remove with the skips once a pve-manager with it is published.
 */
export async function pveManagerHasMesaDisplay(): Promise<boolean> {
  return installedHas('/usr/share/pve-manager/js/pvemanagerlib.js', "name: 'mesa-display'")
}

/**
 * Whether the installed 3dfx binary hands Glide frames to a GL display as a dmabuf and starts
 * egl-headless without a render node (Mesa's surfaceless platform): pve-qemu-kvm with stage 2 of the
 * 3dfx ROADMAP entry. TODO: remove with the skips once a pve-qemu-kvm with it is published.
 */
export async function qemu3dfxHasGlDisplay(): Promise<boolean> {
  return installedHas('/usr/bin/qemu-system-x86_64-3dfx', "using Mesa's surfaceless EGL platform")
}

/**
 * Whether the installed qemu-server has the D-Bus display (vga: display=dbus, mesa-display=dbus,
 * audio0 driver dbus, the wsh-dbus-display@ unit). TODO: remove with the skips once published.
 */
export async function qemuServerHasDbusDisplay(): Promise<boolean> {
  return installedHas('/usr/share/perl5/PVE/QemuServer/DBusDisplay.pm', 'wsh-dbus-display')
}

/**
 * Whether the installed qemu-server has the VM option dbus-display-uids (more uids on a VM's
 * D-Bus display bus, for an unprivileged container). TODO: remove with the skip once published.
 */
export async function qemuServerHasDbusDisplayUids(): Promise<boolean> {
  return installedHas('/usr/share/perl5/PVE/QemuServer/DBusDisplay.pm', 'dbus-display-uids')
}

/**
 * Whether the installed pve-manager has the "D-Bus display" field in the Display dialog.
 * TODO: remove with the skips once a pve-manager with it is published.
 */
export async function pveManagerHasDbusDisplay(): Promise<boolean> {
  return installedHas('/usr/share/pve-manager/js/pvemanagerlib.js', "name: 'dbus-refresh'")
}

/**
 * Whether the installed QEMU takes -display dbus,refresh-ms= and VNC next to dbus,gl=on (pve-qemu
 * wsh/0130-0131). TODO: remove with the skips once a pve-qemu-kvm with them is published.
 */
export async function qemuHasDbusRefresh(): Promise<boolean> {
  return installedHas('/usr/bin/qemu-system-x86_64', 'refresh-ms must be at most')
}

/** The VM's config file as pmxcfs stores it. */
export async function vmConfFile(vmid: number): Promise<string> {
  const { code, output } = await pveExec(['cat', `/etc/pve/qemu-server/${vmid}.conf`])
  expect(code, output).toBe(0)
  return output
}

/**
 * Writes a VM config file directly, bypassing the API's schema check: how a config that the API would
 * refuse (or one copied from another node) reaches qemu-server.
 */
export async function writeConfFile(vmid: number, lines: string[]): Promise<void> {
  const { code, output } = await pveExec([
    'sh',
    '-c',
    'printf "%s\\n" "$@" > /etc/pve/qemu-server/$0.conf',
    String(vmid),
    ...lines,
  ])
  expect(code, output).toBe(0)
}

/** `qm showcmd <vmid>` as one argument per line, plus anything qm printed before it. */
export async function showcmd(vmid: number): Promise<string> {
  const { code, output } = await pveExec(['qm', 'showcmd', String(vmid), '--pretty'])
  expect(code, output).toBe(0)
  return output
}

/**
 * Starts the VM's QEMU command frozen (-S) with no display, monitor or network peer, then kills it:
 * QEMU validates every machine, device and bus argument at startup, so a command a real start would
 * reject fails here too, without running a guest. The QMP/VNC sockets and the tap netdev need a live
 * node, so the sockets are dropped and the tap becomes a hubport.
 *
 * `keepDisplay` keeps the command's own `-display` (the SDL display of a VM with a `server`) instead of
 * `-display none`, with SDL's dummy video driver: QEMU then sets up the SDL display without an X server,
 * so this checks that the binary has it and takes the options, not that the display works.
 *
 * A D-Bus display (`-display dbus,addr=...`) is kept with `p2p=yes` in place of the VM's bus, which
 * doesn't exist here: QEMU then waits for a client instead of connecting, and `-audiodev dbus` (which
 * QEMU refuses without the D-Bus display) and `refresh-ms` are checked too.
 */
export async function qemuAccepts(
  vmid: number,
  { keepDisplay = false }: { keepDisplay?: boolean } = {},
): Promise<{ code: number; output: string }> {
  const display = keepDisplay ? 'SDL_VIDEODRIVER=dummy' : ''
  const noDisplay = keepDisplay ? '' : '-display none'
  const script = `
set -e
# The patches print notes ("-- Using ...", "... ignoring: ...") before the command; it's the last line.
cmd=$(qm showcmd ${vmid} | tail -n 1)
eval "set -- $cmd"
bin=$1; shift
args=""
dbus=""
while [ $# -gt 0 ]; do
  case "$1" in
    # A serial port's socket chardev is kept: the device or -serial that uses it needs it.
    -chardev) case "$2" in *id=serial*) ;; *) shift 2; continue ;; esac ;;
    -mon|-pidfile|-vnc) shift 2; continue ;;
    -object) case "$2" in monitor-qmp*) shift 2; continue ;; esac ;;
    # A tap needs the host bridge; a hubport with the same id keeps the NIC's netdev= valid.
    -netdev) case "$2" in *type=tap*)
        id=$(printf %s "$2" | sed -n 's/.*[,]id=\\([^,]*\\).*/\\1/p')
        args="$args -netdev 'hubport,id=$id,hubid=0'"; shift 2; continue ;; esac ;;
    -net) case "$2" in *type=tap*) shift 2; continue ;; esac ;;
    -daemonize) shift; continue ;;
    -display) case "$2" in dbus*)
        dbus=1
        args="$args -display '$(printf %s "$2" | sed 's/addr=[^,]*/p2p=yes/')'"; shift 2; continue ;; esac ;;
  esac
  args="$args '$(printf %s "$1" | sed "s/'/'\\\\''/g")'"
  shift
done
eval "set -- $args"
nodisplay="${noDisplay}"
[ -n "$dbus" ] && nodisplay=""
rm -f /tmp/e2e-${vmid}.pid
set +e
${display} timeout 20 "$bin" "$@" -S $nodisplay -monitor none -serial none -daemonize -pidfile /tmp/e2e-${vmid}.pid
rc=$?
[ -f /tmp/e2e-${vmid}.pid ] && kill "$(cat /tmp/e2e-${vmid}.pid)"
exit $rc
`
  return pveExec(['sh', '-c', script])
}

function docker(method: string, path: string, body?: unknown, raw: boolean | 'buffer' = false): Promise<unknown> {
  const host = process.env.DOCKER_HOST
  const target = host?.startsWith('tcp://')
    ? (() => {
        const url = new URL(host.replace('tcp://', 'http://'))
        return { host: url.hostname, port: Number(url.port) }
      })()
    : { socketPath: host?.replace('unix://', '') ?? '/var/run/docker.sock' }
  const payload = body === undefined ? undefined : JSON.stringify(body)
  return new Promise((resolve, reject) => {
    const req = http.request(
      { ...target, headers: payload ? { 'Content-Type': 'application/json' } : {}, method, path: `/v1.43${path}` },
      (res) => {
        const chunks: Buffer[] = []
        res.on('data', (c: Buffer) => chunks.push(c))
        res.on('end', () => {
          const data = Buffer.concat(chunks)
          const text = data.toString('utf8')
          if ((res.statusCode ?? 500) >= 400) {
            reject(new Error(`docker ${method} ${path}: ${res.statusCode} ${text}`))
          } else if (raw === 'buffer') {
            resolve(data)
          } else {
            resolve(raw || !text ? text : JSON.parse(text))
          }
        })
      },
    )
    req.on('error', reject)
    if (payload) req.write(payload)
    req.end()
  })
}
