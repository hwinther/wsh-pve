#!/usr/bin/env node
/**
 * Generate docs/src/data/packages.json from the Debian repository Packages
 * file (preferred) or WSH changelog patches in submodules/ (fallback).
 *
 * Each package links to its GitHub release. Release tags are formed as
 * `<releaseName>-<version>` with the first `+` replaced by `-`, matching the
 * tag created by .github/workflows/build-deb.yml.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");

const REPO_URL = "https://github.com/hwinther/wsh-pve";

// `name` is the Debian package name (as published in the repo); `releaseName`
// is the value used as the build input / release tag prefix, which differs for
// the qemu package (built as `pve-qemu`, published as `pve-qemu-kvm`).
const PACKAGE_DEFS = [
  {
    name: "pve-manager",
    releaseName: "pve-manager",
    patch: "pve-manager.changelog.patch",
  },
  {
    name: "qemu-server",
    releaseName: "qemu-server",
    patch: "qemu-server.changelog.patch",
  },
  {
    name: "pve-qemu-kvm",
    releaseName: "pve-qemu",
    patch: "pve-qemu.changelog.patch",
  },
];

function parsePackagesFile(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  const versions = {};

  for (const block of content.split(/\r?\n\r?\n/)) {
    const nameMatch = block.match(/^Package: (.+)$/m);
    const versionMatch = block.match(/^Version: (.+)$/m);
    const archMatch = block.match(/^Architecture: (.+)$/m);

    if (!nameMatch || !versionMatch) {
      continue;
    }

    versions[nameMatch[1].trim()] = {
      version: versionMatch[1].trim(),
      architecture: archMatch?.[1].trim() ?? "amd64",
    };
  }

  return versions;
}

function latestWshVersionFromPatch(patchPath, packageName) {
  if (!fs.existsSync(patchPath)) {
    return null;
  }

  for (const rawLine of fs.readFileSync(patchPath, "utf8").split("\n")) {
    if (!rawLine.startsWith("+") || rawLine.startsWith("+++")) {
      continue;
    }

    const match = rawLine.slice(1).match(/^(\S+) \(([^)]+)\)/);
    if (match && match[1] === packageName && match[2].includes("+wsh")) {
      return match[2];
    }
  }

  return null;
}

function releaseInfo(releaseName, version) {
  if (!version || version === "unknown") {
    return { releaseTag: null, releaseUrl: null };
  }

  const releaseTag = `${releaseName}-${version.replace("+", "-")}`;
  return { releaseTag, releaseUrl: `${REPO_URL}/releases/tag/${releaseTag}` };
}

function main() {
  const packagesFile = process.argv[2];
  let source = "changelog";
  let repoVersions = {};

  if (packagesFile && fs.existsSync(packagesFile)) {
    repoVersions = parsePackagesFile(packagesFile);
    source = "repo";
  }

  const packages = PACKAGE_DEFS.map(({ name, releaseName, patch }) => {
    const repo = repoVersions[name];
    const patchVersion = latestWshVersionFromPatch(
      path.join(root, "submodules", patch),
      name,
    );
    const version = repo?.version ?? patchVersion ?? "unknown";

    return {
      name,
      version,
      architecture:
        repo?.architecture ?? (name === "pve-manager" ? "all" : "amd64"),
      suite: "stable",
      ...releaseInfo(releaseName, version),
    };
  });

  const output = {
    generatedAt: new Date().toISOString(),
    source,
    releasesUrl: `${REPO_URL}/releases`,
    packages,
  };

  const outPath = path.join(root, "docs", "src", "data", "packages.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, `${JSON.stringify(output, null, 2)}\n`);

  console.log(`Wrote ${outPath} (source: ${source})`);
  for (const pkg of packages) {
    console.log(`  ${pkg.name}: ${pkg.version} -> ${pkg.releaseTag ?? "(no release)"}`);
  }
}

main();
