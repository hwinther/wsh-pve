// Browser SPARC: boots wisp's shell on qemu-system-sparc (WebAssembly, TCG interpreter) with its
// serial console in xterm.js.
//
// The console: QEMU opens /dev/wsh-serial with `-chardev pipe` (one path, read and write). That
// path is a character device this script registers in Emscripten's file system before QEMU starts.
// The file system lives on the page's main thread, and QEMU's threads reach it through proxied
// system calls, so the device's handlers run here, next to the terminal: write() goes straight to
// xterm.js, read() takes what was typed, and poll() reports input waiting. QEMU's main loop sleeps
// in poll(); typing wakes it through the device node's listener queue (Emscripten's asynchronous
// poll for threads).

const MACHINE = "SS-5";
const params = new URLSearchParams(location.search);
const MEMORY_MB = Math.min(256, Math.max(16, parseInt(params.get("mem"), 10) || 128));
const APPEND = "console=ttyS0 wisp=shell";
const PROMPT = "wisp:sparc32>";
const DEVICE = "/dev/wsh-serial";

const statusEl = document.getElementById("status");
const restartEl = document.getElementById("restart");

// For tests and the curious: timings in ms from the start of the page's script.
const state = (window.browserSparc = {
  phase: "starting",
  t0: performance.now(),
  times: {},
  output: "",
  lines: [],
  exitCode: null,
});

function mark(name) {
  state.times[name] = Math.round(performance.now() - state.t0);
}

function setStatus(text) {
  statusEl.textContent = text;
}

function seconds(ms) {
  return (ms / 1000).toFixed(1) + " s";
}

// SharedArrayBuffer needs a cross-origin isolated page. GitHub Pages can't send the headers, so a
// service worker adds them (coi-sw.js) and the page reloads once under its control.
async function ensureIsolated() {
  if (window.crossOriginIsolated) return true;
  if (!("serviceWorker" in navigator)) return false;
  const flag = "browser-sparc-reloaded";
  let reloaded = false;
  try {
    reloaded = sessionStorage.getItem(flag) === "1";
  } catch (e) {
    // storage blocked: try once anyway
  }
  if (reloaded) return false;
  setStatus("Setting up cross-origin isolation...");
  await navigator.serviceWorker.register("coi-sw.js", { scope: "./" });
  await navigator.serviceWorker.ready;
  try {
    sessionStorage.setItem(flag, "1");
  } catch (e) {
    // ignore
  }
  location.reload();
  return new Promise(() => {}); // the reload takes over
}

async function fetchBytes(url, label) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${label}: HTTP ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

function makeTerminal() {
  const term = new window.Terminal({
    cols: 80,
    rows: 24,
    convertEol: false,
    cursorBlink: true,
    scrollback: 1000,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "DejaVu Sans Mono", monospace',
    fontSize: 15,
    theme: { background: "#101418" },
  });
  term.open(document.getElementById("terminal"));
  return term;
}

function serialDevice(term) {
  const input = [];
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let node = null;
  let FS = null;
  let promptSeen = false;
  let lineBuf = "";
  const plain = (s) => s.replace(/\x1b\[[0-9;]*[A-Za-z]/g, "");
  const POLLIN = 1;
  const POLLOUT = 4;
  const EAGAIN = 6; // Emscripten's errno value

  const ops = {
    open(stream) {
      stream.seekable = false;
    },
    close() {},
    read(stream, buffer, offset, length) {
      if (input.length === 0) throw new FS.ErrnoError(EAGAIN);
      let n = 0;
      while (n < length && input.length) buffer[offset + n++] = input.shift();
      return n;
    },
    write(stream, buffer, offset, length) {
      // A copy: the heap is a SharedArrayBuffer, which xterm.js and TextDecoder don't take.
      const bytes = buffer.slice(offset, offset + length);
      term.write(bytes);
      const text = decoder.decode(bytes, { stream: true });
      state.output += text;
      if (state.output.length > 200000) state.output = state.output.slice(-100000);
      // The boot's console lines with their times, for the boot timings.
      for (const ch of text) {
        if (ch === "\n") {
          if (state.lines.length < 500) {
            state.lines.push([Math.round(performance.now() - state.t0), lineBuf.trimEnd()]);
          }
          lineBuf = "";
        } else lineBuf += ch;
      }
      if (!state.times.firstOutput) mark("firstOutput");
      if (!state.times.linux && state.output.includes("Linux version")) mark("linux");
      if (!state.times.banner && state.output.includes("WISP-BANNER")) mark("banner");
      // The prompt is coloured: compare without the escape sequences.
      if (!promptSeen && plain(state.output.slice(-200)).includes(PROMPT)) {
        promptSeen = true;
        mark("prompt");
        state.phase = "running";
        const took = seconds(state.times.prompt - state.times.qemuStart);
        setStatus(
          state.resume
            ? `Running, resumed from a snapshot of a booted machine in ${took}.`
            : `Running. Booted to the prompt in ${took}.`,
        );
      }
      return length;
    },
    poll() {
      return (input.length ? POLLIN : 0) | POLLOUT;
    },
  };

  return {
    install(module) {
      FS = module.FS;
      const dev = FS.makedev(64, 0);
      FS.registerDevice(dev, ops);
      FS.mkdev(DEVICE, dev);
      node = FS.lookupPath(DEVICE).node;
    },
    type(text) {
      for (const b of encoder.encode(text)) input.push(b);
      // Wakes QEMU's main loop if it sleeps in poll() on the device.
      if (node && node.notifyListeners) node.notifyListeners(POLLIN);
    },
  };
}

// Calls done() once QEMU has opened the snapshot and closed it again: the incoming migration is
// then loaded and the machine runs (QEMU starts it by itself without -S). The file system runs on
// this thread, so its open streams can be looked at directly.
function watchIncoming(FS, done) {
  let opened = false;
  const timer = setInterval(() => {
    const open = FS.streams.some((s) => s && s.path === "/snap/state");
    if (open) opened = true;
    else if (opened) {
      clearInterval(timer);
      setTimeout(done, 100);
    }
  }, 50);
}

async function main() {
  if (!(await ensureIsolated())) {
    setStatus(
      "This browser can't isolate the page (no service worker, or it was refused), so QEMU's " +
        "threads can't start. Try a current Firefox, Chrome or Safari, outside private mode.",
    );
    return;
  }
  mark("isolated");
  restartEl.addEventListener("click", () => location.reload());

  const term = makeTerminal();
  const serial = serialDevice(term);
  term.onData((data) => serial.type(data));
  term.focus();

  setStatus("Downloading QEMU, OpenBIOS and the wisp kernel...");
  // The snapshot: the machine saved at wisp's first prompt by a native QEMU built from the same
  // tree (web/scripts/make-snapshot.py), with the console transcript up to there. Optional: without
  // it (or with ?cold) the page boots from OpenBIOS.
  const snapName = `wisp-ss5-${MEMORY_MB}m`;
  const optional = (url) =>
    fetch(url)
      .then((r) => (r.ok ? r.arrayBuffer().then((b) => new Uint8Array(b)) : null))
      .catch(() => null);
  const [factory, bios, kernel, snapState, snapLog] = await Promise.all([
    import("./qemu-system-sparc.js").then((m) => m.default),
    fetchBytes("openbios-sparc32", "OpenBIOS"),
    fetchBytes("wisp-sparc32-kernel", "wisp kernel"),
    params.has("cold") ? null : optional(`${snapName}.state`),
    params.has("cold") ? null : optional(`${snapName}.log`),
  ]);
  const resume = Boolean(snapState && snapLog);
  state.resume = resume;
  const modeEl = document.getElementById("mode");
  if (!resume) {
    modeEl.href = location.pathname;
    modeEl.textContent = "Start from the snapshot";
    modeEl.hidden = !snapState && !params.has("cold");
  }
  mark("loaded");

  const args = [
    "-M", MACHINE,
    "-m", String(MEMORY_MB),
    "-nodefaults",
    "-display", "none",
    "-monitor", "none",
    "-chardev", `pipe,id=console,path=${DEVICE}`,
    "-serial", "chardev:console",
    "-bios", "/fw/openbios-sparc32",
    "-kernel", "/wisp/kernel",
    "-append", APPEND,
  ];
  if (resume) {
    args.push("-incoming", "file:/snap/state");
    term.write(snapLog);
    setStatus("Resuming the machine from a snapshot taken at wisp's prompt...");
  } else {
    setStatus("Booting: OpenBIOS, then Linux (this takes a few minutes)...");
  }
  state.args = args;
  mark("qemuStart");

  const stopped = (code) => {
    if (state.phase === "stopped") return;
    state.exitCode = code;
    state.phase = "stopped";
    mark("exit");
    setStatus(`The machine is off (QEMU exited with ${code}). Restart boots it again.`);
    term.write("\r\n\x1b[2m[QEMU exited]\x1b[0m\r\n");
  };

  await factory({
    arguments: args,
    print: (text) => console.log("qemu:", text),
    printErr: (text) => {
      console.warn("qemu:", text);
      // QEMU's exit() on power-off: Emscripten keeps the runtime alive for the pending
      // asynchronous work of its threads, so onExit isn't called; it says so on stderr.
      const m = /program exited \(with status: (-?\d+)\)/.exec(text);
      if (m) stopped(Number(m[1]));
    },
    preRun: [
      (module) => {
        module.FS.mkdir("/fw");
        module.FS.mkdir("/wisp");
        module.FS.writeFile("/fw/openbios-sparc32", bios);
        module.FS.writeFile("/wisp/kernel", kernel);
        serial.install(module);
        if (resume) {
          module.FS.mkdir("/snap");
          module.FS.writeFile("/snap/state", snapState);
          watchIncoming(module.FS, () => {
            mark("restored");
            // Ask the shell for a fresh prompt: it is waiting in read() at the one in the
            // transcript. The prompt it prints marks the machine as running.
            serial.type("\r");
          });
        }
      },
    ],
    onExit: stopped,
  });
  restartEl.disabled = false;
}

main().catch((error) => {
  console.error(error);
  state.phase = "error";
  state.error = String(error);
  setStatus(`Failed: ${error.message || error}`);
  restartEl.disabled = false;
});
