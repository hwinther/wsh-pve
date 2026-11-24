#!/usr/bin/env node
// The Browser SPARC page in a headless browser, once per machine (?arch=): types `mandel` before the
// resumed machine runs (the page holds the keys until the prompt), resumes the snapshot again,
// checks wisp's `mandel` against e2e/wisp/tests/mandel.txt, then compares the guest's uptime
// (wisp's `info`) with the wall clock, first idle and then with the page's main thread kept busy.
// The busy part is what made the SS-5's clock fall behind: QEMU's main loop sleeps in a poll()
// whose timeout is a setTimeout() on the page's thread, so it wakes up late and the sun4m timer
// runs several 10 ms periods at once (web/patches/slavio-timer-missed-ticks.patch). The other
// machines keep time from clocks that read QEMU's virtual clock, and are checked the same way.
//
//   node web/scripts/browser-check.mjs <dir with the page and its files> [seconds]
//
// The directory holds docs/public/browser-sparc/ and the build's files (web/dist/). It is served
// on 127.0.0.1 with the COOP/COEP headers the page needs. Environment: PLAYWRIGHT (the module to
// load, default playwright-core, resolved from the current directory), BROWSER (chromium or
// firefox, default chromium), CHANNEL (e.g. chrome: an installed browser instead of Playwright's)
// or EXECUTABLE (a browser binary, e.g. Debian's /usr/bin/chromium),
// ARCHES (comma-separated keys of machines.json, default all), MIN_RATIO (default 0.9), MANDEL
// (the expected rows, default e2e/wisp/tests/mandel.txt next to this script's checkout), BENCH=1
// (also runs `bench`), COLD=1 (also boots each machine from its firmware, ?cold, and times it).
// Prints a JSON line per machine with the numbers. Exits 1 when a check fails.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const dir = process.argv[2];
const seconds = Number(process.argv[3] || 30);
if (!dir) {
  console.error("usage: browser-check.mjs <dir> [seconds]");
  process.exit(2);
}
const require = createRequire(join(process.cwd(), "index.js"));
const pw = require(process.env.PLAYWRIGHT || "playwright-core");
const minRatio = Number(process.env.MIN_RATIO || 0.9);
const here = dirname(fileURLToPath(import.meta.url));
const mandelPath = process.env.MANDEL || join(here, "..", "..", "e2e", "wisp", "tests", "mandel.txt");
// the 20 rows, each closed with '|' so that no editor trims the spaces
const mandelWant = (await readFile(mandelPath, "utf8")).split("\n").filter(Boolean).map((l) => l.replace(/\|$/, ""));
const machines = JSON.parse(await readFile(join(dir, "machines.json"), "utf8"));
const arches = (process.env.ARCHES || Object.keys(machines).join(",")).split(",");

const types = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".wasm": "application/wasm", ".json": "application/json",
};
const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^([/\\])+/, "");
  try {
    const body = await readFile(join(dir, path || "index.html"));
    res.writeHead(200, {
      "Content-Type": types[extname(path)] || "application/octet-stream",
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
      "Cross-Origin-Resource-Policy": "same-origin",
    });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}/index.html`;

const browser = await pw[process.env.BROWSER || "chromium"].launch({
  headless: true,
  ...(process.env.CHANNEL ? { channel: process.env.CHANNEL } : {}),
  ...(process.env.EXECUTABLE ? { executablePath: process.env.EXECUTABLE } : {}),
});
const plain = (s) => s.replace(/\x1b\[[0-9;]*[A-Za-z]/g, "");
let failed = false;
const check = (rec, name, ok, detail) => {
  rec.checks[name] = ok ? "ok" : `FAILED${detail ? `: ${detail}` : ""}`;
  failed ||= !ok;
  console.log(`${rec.arch} ${name}: ${ok ? "ok" : "FAILED"}${detail ? ` (${detail})` : ""}`);
};

async function start(page, query, timeout) {
  await page.goto(`${base}?${query}`);
  await page.waitForFunction(
    () => ["running", "error", "stopped"].includes(window.browserSparc?.phase),
    null,
    { timeout, polling: 200 },
  );
  return page.evaluate(() => ({
    phase: window.browserSparc.phase, resume: window.browserSparc.resume,
    times: window.browserSparc.times, error: window.browserSparc.error,
  }));
}

// Types a command; returns the output after it once `done` matches, and the wall time it took.
async function run(page, command, done, timeout = 300000) {
  const before = await page.evaluate(() => window.browserSparc.output.length);
  await page.click("#terminal");
  const t0 = Date.now();
  await page.keyboard.type(`${command}\r`);
  await page.waitForFunction(
    ([b, re]) => new RegExp(re).test(window.browserSparc.output.slice(b).replace(/\x1b\[[0-9;]*[A-Za-z]/g, "")),
    [before, done.source],
    { timeout, polling: 100 },
  );
  const t1 = Date.now();
  const out = plain(await page.evaluate((b) => window.browserSparc.output.slice(b), before));
  return { out, t0, t1, ms: t1 - t0 };
}

// `mandel` typed as soon as the snapshot's transcript (with its prompt) is on the screen, before the
// machine runs: the page holds the keys until wisp's first prompt. Sent at once, the first ones
// went to the serial port before the snapshot replaced its state, and the shell got "andel".
async function earlyInput(page, query) {
  await page.goto(`${base}?${query}`);
  await page.waitForFunction(() => window.browserSparc?.times?.qemuStart !== undefined, null,
    { timeout: 180000, polling: 20 });
  await page.click("#terminal");
  const phase = await page.evaluate(() => window.browserSparc.phase);
  await page.keyboard.type("mandel\r");
  await page.waitForFunction(
    () => /points, \d+ iterations|unknown command/.test(window.browserSparc.output.replace(/\x1b\[[0-9;]*[A-Za-z]/g, "")),
    null,
    { timeout: 300000, polling: 100 },
  );
  const out = plain(await page.evaluate(() => window.browserSparc.output));
  return { typedIn: phase, ok: /points, \d+ iterations/.test(out), detail: (/\S*: unknown command/.exec(out) || [""])[0] };
}

async function checkMachine(arch) {
  const rec = { arch, checks: {} };
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.log(`${arch} page error:`, e.message));
  try {
    const query = arch === "sparc32" ? "" : `arch=${arch}`;
    const early = await earlyInput(page, query);
    check(rec, "early input", early.ok, early.detail || `typed while ${early.typedIn}`);
    const st = await start(page, query, 180000);
    rec.snapshot = { resume: st.resume, loadedMs: st.times.loaded, restoredMs: st.times.restored,
      promptAfterQemuStartMs: st.times.prompt - st.times.qemuStart };
    check(rec, "snapshot start", st.phase === "running" && st.resume, st.error || st.phase);
    if (st.phase !== "running") return rec;

    // mandel, row by row
    const m = await run(page, "mandel", /points, \d+ iterations, \d+ ms/);
    const lines = m.out.split(/\r?\n/);
    const footer = lines.findIndex((l) => /^ {2}\d+ x \d+ points, /.test(l));
    const rows = lines.slice(Math.max(0, footer - mandelWant.length), footer).map((l) => l.slice(1));
    const bad = mandelWant.map((w, i) => (rows[i] === w ? -1 : i)).filter((i) => i >= 0);
    rec.mandel = { guestMs: Number(/iterations, (\d+) ms/.exec(m.out)[1]), wallMs: m.ms };
    check(rec, "mandel", bad.length === 0, bad.length ? `rows ${bad.slice(0, 5)} differ` : "");

    if (process.env.BENCH) {
      const b = await run(page, "bench", /crc32 0x[0-9a-f]{8} after \d+ rounds \(\d+ KiB\) in \d+ ms/, 600000);
      rec.bench = { guestMs: Number(/in (\d+) ms/.exec(b.out)[1]), wallMs: b.ms };
      rec.bench.ratio = Number((rec.bench.guestMs / rec.bench.wallMs).toFixed(3));
      console.log(`${arch} bench: guest ${rec.bench.guestMs} ms in ${b.ms} ms of wall time`);
    }

    // wisp's uptime, against the wall clock half-way between typing the command and its answer
    const uptime = async () => {
      const r = await run(page, "info", /uptime\s+\d+\.\d+ s/, 120000);
      return { wall: (r.t0 + r.t1) / 2000, guest: Number(/uptime\s+(\d+\.\d+) s/.exec(r.out)[1]) };
    };
    const measure = async (label, busyMs) => {
      const a = await uptime();
      if (busyMs) {
        // tasks of busyMs back to back on the page's thread, as a page busy rendering would have
        await page.evaluate((ms) => {
          window.clockCheckBusy = setInterval(() => {
            const t = performance.now();
            while (performance.now() - t < ms);
          }, 1);
        }, busyMs);
      }
      await page.waitForTimeout(seconds * 1000);
      if (busyMs) {
        await page.evaluate(() => clearInterval(window.clockCheckBusy));
        // The first command after it waits for the input that queued up and, on the SS-5, for the
        // guest to take the timer ticks it was owed; its uptime is right, but the half-way point of
        // a long wait is not when it was read. The next one answers at once.
        await uptime();
      }
      const b = await uptime();
      const ratio = (b.guest - a.guest) / (b.wall - a.wall);
      rec[label] = Number(ratio.toFixed(3));
      check(rec, `clock ${label}`, ratio >= minRatio,
        `guest ${(b.guest - a.guest).toFixed(2)} s in ${(b.wall - a.wall).toFixed(2)} s, ratio ${ratio.toFixed(3)}, minimum ${minRatio}`);
    };
    await measure("idle", 0);
    await measure("busy", 30);

    if (process.env.COLD) {
      const c = await start(page, `${query ? `${query}&` : ""}cold`, 1800000);
      rec.cold = { promptAfterQemuStartMs: c.times.prompt - c.times.qemuStart,
        firstOutputMs: c.times.firstOutput - c.times.qemuStart,
        linuxMs: c.times.linux ? c.times.linux - c.times.qemuStart : null };
      check(rec, "cold boot", c.phase === "running" && !c.resume, c.error || c.phase);
    }
  } catch (e) {
    check(rec, "run", false, String(e.message || e).split("\n")[0]);
  } finally {
    await page.close();
  }
  return rec;
}

try {
  for (const arch of arches) {
    if (!machines[arch]) throw new Error(`no machine ${arch} in machines.json`);
    console.log(`RESULT ${JSON.stringify(await checkMachine(arch))}`);
  }
} finally {
  await browser.close();
  server.close();
}
process.exit(failed ? 1 : 0);
