# Repo notes/instructions

Prerequisites: docker or podman for building the repo, nginx or similar to host it

1. Create the .gpg local file from secrets storage or generate a new one via gpg --full-generate-key and then export it, further details related to exporting the key pair and thumbprint can be found further down in this readme.
2. Put your gpg password in a file named .gpg-password in the format of SIGNING_PASSWORD=password-value-here, or change the makefile so that it uses the interactive password prompt command instead of passing it through this env file
3. Run sudo make repo-update
4. Host the repo folder, optionally using the nginx/nginx-site.conf configuration file, an example command is at the bottom of the sh/ps1 files.

Rerun step 2 when new packages come out.
TODO: automate this further in the future

## Old notes

First run dch in the root folder of the git repo:

$ dch

Then edit the changelog to use wsh suffix and include some descriptive text, and build the deb package

$ make deb

Finally add the deb package to the repo from the /mnt/dev/repo-root folder:
(All of the above, and especially this command should be executed as the regular user account so that file permissions are ok, nothing is installed on the build host, and the gpg keyring is easily located

$ reprepro -Vb . includedeb trixie /mnt/dev/user/pve-manager/pve-manager_8.2.4+wsh1_amd64.deb
$ reprepro -Vb . includedeb trixie /mnt/dev/user/qemu-server/qemu-server_8.2.2+wsh1_amd64.deb

# On the next machine

# (Key generated via: gpg --armor --output wsh-pve.gpg.key --export-options export-minimal --export 6082CB267FE62087F23F343910DD95462E417289)
# (Sources file created via this guide https://wiki.debian.org/DebianRepository/SetupWithReprepro)

See [setup docs](docs/src/content/docs/guides/setup.md) for consumer installation instructions.

## Change password

gpg -k # list keys to find the id
gpg --edit-key DCE56A79F1A14BF110B7B74386C3B9485CA734A3
> type passwd then enter old and new password, then save and exit
gpg --armor --output .gpg --export-secret-keys DCE56A79F1A14BF110B7B74386C3B9485CA734A3
