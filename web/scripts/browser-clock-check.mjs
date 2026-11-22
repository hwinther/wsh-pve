#!/usr/bin/env node
// The Browser SPARC page in a headless browser: resumes the snapshot, then compares the guest's
// uptime (wisp's `info`) with the wall clock, first idle and then with the page's main thread kept
// busy. The busy part is what made the guest's clock fall behind: QEMU's main loop sleeps in a
// poll() whose timeout is a setTimeout() on the page's thread, so it wakes up late and the sun4m
// timer runs several 10 ms periods at once (web/patches/slavio-timer-missed-ticks.patch).
//
//   node web/scripts/browser-clock-check.mjs <dir with the page and its files> [seconds]
//
// The directory holds docs/public/browser-sparc/ and the build's files (web/dist/). It is served
// on 127.0.0.1 with the COOP/COEP headers the page needs. Environment: PLAYWRIGHT (the module to
// load, default playwright-core, resolved from the current directory), BROWSER (chromium or
// firefox, default chromium), CHANNEL (e.g. chrome: an installed browser instead of Playwright's),
// MIN_RATIO (default 0.9). Exits 1 when a ratio is below it.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { extname, join, normalize } from "node:path";

const dir = process.argv[2];
const seconds = Number(process.argv[3] || 30);
if (!dir) {
  console.error("usage: browser-clock-check.mjs <dir> [seconds]");
  process.exit(2);
}
const require = createRequire(join(process.cwd(), "index.js"));
const pw = require(process.env.PLAYWRIGHT || "playwright-core");
const minRatio = Number(process.env.MIN_RATIO || 0.9);

const types = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".wasm": "application/wasm",
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
const url = `http://127.0.0.1:${server.address().port}/index.html`;

const browser = await pw[process.env.BROWSER || "chromium"].launch({
  headless: true,
  ...(process.env.CHANNEL ? { channel: process.env.CHANNEL } : {}),
});
let failed = false;
try {
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.log("page error:", e.message));
  await page.goto(url);
  await page.waitForFunction(() => window.browserSparc?.phase === "running" || window.browserSparc?.phase === "error",
    null, { timeout: 120000, polling: 200 });
  const st = await page.evaluate(() => ({ phase: window.browserSparc.phase, resume: window.browserSparc.resume,
    times: window.browserSparc.times, error: window.browserSparc.error }));
  console.log("page:", JSON.stringify(st));
  if (st.phase !== "running") throw new Error(`the page did not start: ${st.error}`);

  // wisp's uptime, against the wall clock half-way between typing the command and its answer
  const uptime = async () => {
    const before = await page.evaluate(() => window.browserSparc.output.length);
    await page.click("#terminal");
    const t0 = Date.now();
    await page.keyboard.type("info\r");
    await page.waitForFunction((b) => /uptime\s+\d+\.\d+ s/.test(window.browserSparc.output.slice(b)), before,
      { timeout: 120000, polling: 200 });
    const t1 = Date.now();
    const out = await page.evaluate((b) => window.browserSparc.output.slice(b), before);
    return { wall: (t0 + t1) / 2000, guest: Number(/uptime\s+(\d+\.\d+) s/.exec(out)[1]) };
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
      // The first command after it waits for the input that queued up and for the guest to take
      // the timer ticks it was owed, which takes several seconds; its uptime is right, but the
      // half-way point of a long wait is not when it was read. The next one answers at once.
      await uptime();
    }
    const b = await uptime();
    const ratio = (b.guest - a.guest) / (b.wall - a.wall);
    const ok = ratio >= minRatio;
    failed ||= !ok;
    console.log(`${label}: guest ${(b.guest - a.guest).toFixed(2)} s in ${(b.wall - a.wall).toFixed(2)} s of wall ` +
      `time, ratio ${ratio.toFixed(3)} (minimum ${minRatio}) ${ok ? "ok" : "FAILED"}`);
  };
  await measure("idle", 0);
  await measure("page thread busy (30 ms tasks)", 30);
} finally {
  await browser.close();
  server.close();
}
process.exit(failed ? 1 : 0);
