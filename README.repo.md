# Repo notes/instructions

Prerequisites: docker or podman for building the repo, nginx or similar to host it

1. Create the .gpg local file from secrets storage or generate a new one via gpg --full-generate-key and then export it, further details related to exporting the key pair and thumbprint can be found further down in this readme.
2. Run repo-update.sh or repo-update.ps1 depending on your platform - type in the gpg password to sign the packages
3. Host the repo folder, optionally using the nginx/nginx-site.conf configuration file, an example command is at the bottom of the sh/ps1 files.

Rerun step 2 when new packages come out.
TODO: automate this further in the future

## Old notes

First run dch in the root folder of the git repo:

$ dch

Then edit the changelog to use wsh suffix and include some descriptive text, and build the deb package

$ make deb

Finally add the deb package to the repo from the /mnt/dev/repo-root folder:
(All of the above, and especially this command should be executed as the regular user account so that file permissions are ok, nothing is installed on the build host, and the gpg keyring is easily located

$ reprepro -Vb . includedeb bookworm /mnt/dev/crono/pve-manager/pve-manager_8.2.4+wsh1_amd64.deb
$ reprepro -Vb . includedeb bookworm /mnt/dev/crono/qemu-server/qemu-server_8.2.2+wsh1_amd64.deb

# On the next machine:
# (Key generated via: gpg --armor --output wsh-pve.gpg.key --export-options export-minimal --export 6082CB267FE62087F23F343910DD95462E417289)
# (Sources file created via this guide https://wiki.debian.org/DebianRepository/SetupWithReprepro)
# wget -O - http://pve-test3.osl.wsh.no/conf/wsh-pve.gpg.key | apt-key add -
wget -O - http://pve-test3.osl.wsh.no/conf/wsh-pve.gpg.key | gpg --dearmor -o /etc/apt/keyrings/wsh-pve.gpg

wget -O /etc/apt/sources.list.d/wsh-pve.list http://pve-test3/conf/wsh-pve.list
