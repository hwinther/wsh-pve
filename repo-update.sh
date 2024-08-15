#!/bin/bash

if command -v podman &> /dev/null
then
    DOCKER=podman
elif command -v docker &> /dev/null
then
    DOCKER=docker
else
    echo "Neither podman nor docker is installed."
    exit 1
fi

# Note: do not push this image to a remote registry as it contains the gpg key
$DOCKER build . -t repo -f repo.Dockerfile
$DOCKER run --rm -v repo:/opt/repo -it localhost/repo bash -c "cd /opt/repo && reprepro -Vb . includedeb bookworm /opt/repo-incoming/*.deb"

# Optionally, run a container with the repo mounted at /opt/repo
# $DOCKER run --rm -v repo:/opt/repo -v nginx/nginx-site.conf:/etc/nginx/conf.d/default.conf -p 8080:80 -it nginx
