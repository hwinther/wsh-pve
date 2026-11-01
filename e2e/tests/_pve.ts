import { type APIRequestContext, expect } from '@playwright/test'
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
  delete: (path: string) => Promise<void>
}

/** An API client authenticated as root@pam (ticket cookie + CSRF header). */
export async function pveApi(request: APIRequestContext): Promise<Pve> {
  const login = await request.post('/api2/json/access/ticket', {
    form: { password: PASSWORD, username: 'root@pam' },
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
  }
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
 */
export async function qemuAccepts(vmid: number): Promise<{ code: number; output: string }> {
  const script = `
set -e
# The patches print notes ("-- Using ...", "... ignoring: ...") before the command; it's the last line.
cmd=$(qm showcmd ${vmid} | tail -n 1)
eval "set -- $cmd"
bin=$1; shift
args=""
while [ $# -gt 0 ]; do
  case "$1" in
    -chardev|-mon|-pidfile|-vnc) shift 2; continue ;;
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
timeout 20 "$bin" "$@" -S -display none -monitor none -serial none -daemonize -pidfile /tmp/e2e-${vmid}.pid
rc=$?
[ -f /tmp/e2e-${vmid}.pid ] && kill "$(cat /tmp/e2e-${vmid}.pid)"
exit $rc
`
  return pveExec(['sh', '-c', script])
}

function docker(method: string, path: string, body?: unknown, raw = false): Promise<unknown> {
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
          const text = Buffer.concat(chunks).toString('utf8')
          if ((res.statusCode ?? 500) >= 400) {
            reject(new Error(`docker ${method} ${path}: ${res.statusCode} ${text}`))
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
