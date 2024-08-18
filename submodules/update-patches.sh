#!/bin/bash
rm -rf pve-manager pve-qemu qemu-server
git submodule update --init

pushd pve-manager
patch -p1 < ../pve-manager.patch && git diff -p > ../pve-manager.patch
popd

pushd pve-qemu
patch -p1 < ../pve-qemu.patch && git diff -p > ../pve-qemu.patch
popd

pushd qemu-server
patch -p1 < ../qemu-server.patch && git diff -p > ../qemu-server.patch
popd
