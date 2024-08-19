#!/bin/bash
git submodule update --init submodules/qemu-3dfx

podman run --rm -v .git:/src/.git -v "./submodules/qemu-3dfx":"/src/submodules/qemu-3dfx" -w /src/submodules/qemu-3dfx/wrappers/3dfx -it ghcr.io/hwinther/wsh-pve/djgpp-build:12 bash -c "mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make && make clean"
podman run --rm -v .git:/src/.git -v "./submodules/qemu-3dfx":"/src/submodules/qemu-3dfx" -w /src/submodules/qemu-3dfx/wrappers/mesa -it ghcr.io/hwinther/wsh-pve/djgpp-build:12 bash -c "mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make && make clean"

ls -la submodules/qemu-3dfx/wrappers/3dfx/build
ls -la submodules/qemu-3dfx/wrappers/mesa/build

