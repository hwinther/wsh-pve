#!/bin/sh
# Builds Browser SPARC's binary files with web/Dockerfile (QEMU for WebAssembly, OpenBIOS, wisp's
# sparc32 kernel, xterm.js) into web/dist/, and copies them next to the page in
# docs/public/browser-sparc/ so that `npm run dev` in docs/, or any static server there, runs it.
#
#   web/build.sh [output dir]
#
# Environment: DOCKER_BUILD_ARGS (extra arguments for docker build, e.g. --build-arg DEBIAN=...).
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$ROOT/web/dist}

# shellcheck disable=SC2086
docker build -f "$ROOT/web/Dockerfile" --target dist -o "type=local,dest=$OUT" ${DOCKER_BUILD_ARGS:-} "$ROOT"
cp "$OUT"/* "$ROOT/docs/public/browser-sparc/"
cat "$OUT/versions.txt"
ls -l "$OUT"
