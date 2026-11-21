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
export async function checkQemuExtra(name: string): Promise<{ code: number; output: string }> {
  return pveExec(['bash', '-c', CHECK_QEMU_EXTRAS, 'check-qemu-extras', '--root', '/', '--only', name])
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
 * Whether the installed qemu-server has `machine: ...,legacy-bios-layout=1` (NICs without option ROM, no
 * vapic ROM). TODO: remove with its test.fail() once a qemu-server with it is published.
 */
export async function hasLegacyBiosLayout(): Promise<boolean> {
  const probe = await pveExec([
    'perl',
    '-MPVE::QemuServer::Machine',
    '-e',
    `print defined(&PVE::QemuServer::Machine::legacy_bios_layout) ? 'legacy=yes' : 'legacy=no';`,
  ])
  expect(probe.output, probe.output).toMatch(/^legacy=(yes|no)$/m)
  return probe.output.includes('legacy=yes')
}

/**
 * Whether the installed pve-manager has the "Legacy BIOS memory layout" checkbox in the Machine editor.
 * TODO: remove with its test.fail() once a pve-manager with it is published.
 */
export async function hasLegacyBiosLayoutUi(): Promise<boolean> {
  const probe = await pveExec([
    'sh',
    '-c',
    'grep -q legacy-bios-layout /usr/share/pve-manager/js/pvemanagerlib.js && echo ui=yes || echo ui=no',
  ])
  expect(probe.output, probe.output).toMatch(/^ui=(yes|no)$/m)
  return probe.output.includes('ui=yes')
}

/**
 * Whether the installed qemu-server has `vga: ...,retrace=precise` (QEMU's precise VGA retrace emulation).
 * TODO: remove with its test.fail() once a qemu-server with it is published.
 */
export async function hasVgaRetrace(): Promise<boolean> {
  const probe = await pveExec([
    'perl',
    '-MPVE::QemuServer',
    '-e',
    `print defined(&PVE::QemuServer::assert_vga_retrace) ? 'retrace=yes' : 'retrace=no';`,
  ])
  expect(probe.output, probe.output).toMatch(/^retrace=(yes|no)$/m)
  return probe.output.includes('retrace=yes')
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

/**
 * Whether the installed pve-manager has the "VGA retrace" checkbox in the Display editor.
 * TODO: remove with its test.fail() once a pve-manager with it is published.
 */
export async function hasVgaRetraceUi(): Promise<boolean> {
  const probe = await pveExec([
    'sh',
    '-c',
    'grep -q retraceSupported /usr/share/pve-manager/js/pvemanagerlib.js && echo ui=yes || echo ui=no',
  ])
  expect(probe.output, probe.output).toMatch(/^ui=(yes|no)$/m)
  return probe.output.includes('ui=yes')
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
  esac
  args="$args '$(printf %s "$1" | sed "s/'/'\\\\''/g")'"
  shift
done
eval "set -- $args"
rm -f /tmp/e2e-${vmid}.pid
set +e
${display} timeout 20 "$bin" "$@" -S ${noDisplay} -monitor none -serial none -daemonize -pidfile /tmp/e2e-${vmid}.pid
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
