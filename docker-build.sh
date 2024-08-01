#!/bin/bash
docker build . -f submodules/pve-manager.Dockerfile -t wsh-pve-manager
id=$(docker create wsh-pve-manager)
docker cp $id:/opt/repo/ ./build/
docker rm -v $id
