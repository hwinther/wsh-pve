#!/usr/bin/env node
/**
 * Download the assets of the `media` GitHub release (the sparc lab recordings the docs embed) into
 * docs/public/recordings/, so a local `npm run dev` / `npm run build` serves them at /recordings/
 * the way the deployed site does (repo-update.yml copies the same assets into the Pages site).
 *
 *   cd docs && npm run fetch-media            (GITHUB_TOKEN is used when set; the repo is public)
 *
 * The docs build doesn't need them: without the files the recording components show a placeholder.
 * A missing release or a failed download is reported and exits 0.
 */
const fs = require("fs");
const path = require("path");

const REPO = process.env.MEDIA_REPO || "hwinther/wsh-pve";
const TAG = "media";
const OUT = path.join(__dirname, "..", "docs", "public", "recordings");

async function main() {
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "wsh-pve-docs" };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/${TAG}`, { headers });
  if (!res.ok) {
    console.warn(`No ${TAG} release in ${REPO} (HTTP ${res.status}); the docs show placeholders.`);
    return;
  }
  const { assets } = await res.json();
  fs.mkdirSync(OUT, { recursive: true });
  for (const asset of assets) {
    const name = path.basename(asset.name); // never a path outside OUT
    const r = await fetch(asset.browser_download_url, { headers: { "User-Agent": "wsh-pve-docs" } });
    if (!r.ok) {
      console.warn(`${name}: HTTP ${r.status}, skipped`);
      continue;
    }
    fs.writeFileSync(path.join(OUT, name), Buffer.from(await r.arrayBuffer()));
    console.log(`${name} (${asset.size} bytes)`);
  }
  console.log(`${assets.length} assets of ${REPO}@${TAG} in ${path.relative(process.cwd(), OUT) || OUT}`);
}

main().catch((e) => console.warn(`fetch-media: ${e.message}; the docs show placeholders.`));
