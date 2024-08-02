#!/bin/bash
docker build . -f submodules/pve-manager.Dockerfile -t wsh-pve-manager
id=$(docker create wsh-pve-manager)
docker cp $id:/opt/repo/ ./build/
docker rm -v $id

docker build . -f submodules/qemu-server.Dockerfile -t wsh-qemu-server
id=$(docker create wsh-qemu-server)
docker cp $id:/opt/repo/ ./build/
docker rm -v $id

docker build . -f submodules/pve-qemu.Dockerfile -t wsh-pve-qemu
id=$(docker create wsh-pve-qemu)
docker cp $id:/opt/repo/ ./build/
docker rm -v $id
