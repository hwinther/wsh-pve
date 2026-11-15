# wsh-pve

WSH Proxmox Virtualization Environment patches

## Getting started

To get started continue to the [setup guide](https://debian.wshosting.no/guides/setup/)

## Build

Run `make build-containers` to build the PVE build image which creates debian packages from the submodules and the djgpp build image which is used to build windows drivers.
This is an optional step as the packages are already available in this github repository.

Run `make all` to build the debian packages and copy them into the build directory.
Run `make repo-update` to populate a debian package repository under the repo directory, you will need a gpg key in order to sign the packages.

Run `make 3dfx` to build the qemu-3dfx windows drivers and a patched version of the PVE QEMU package which supports passthrough

### Optional extras

`pve-qemu-kvm` (`make pve-qemu-bundle`) has three parts that never fail its build: when one doesn't build, the package is built and published without it.

| Extra | Make target | In the package | Without it |
| --- | --- | --- | --- |
| `3dfx` | `pve-qemu-3dfx` | `/usr/bin/qemu-system-x86_64-3dfx` | VMs with 3DFX/Mesa enabled don't start |
| `openbios` | `openbios-sparc32` | `openbios-sparc32`, `QEMU,cgthree.bin` from `openbios/` | QEMU's images, without the fixes in `submodules/SPARC.md` |
| `sun-proms` | `restore-sparc` (private `submodules/sparc`) | `ss5.bin`, `ss10_v2.25_rom`, `ss20_v2.25_rom` | VMs with a Sun PROM don't start |

A target whose extra drops out prints `WARNING: optional extra <name> missing: <reason>`. `scripts/check-qemu-extras.sh --deb <file>` (or `--root /` on a host) lists what a package has. The `build-deb.yml` run of `pve-qemu` puts that list in its job summary and release notes, opens an issue per missing extra (updated by later builds, closed by the first one that has it again; the Sun PROMs are only expected in this repository, not in forks), and the e2e tests (`e2e/tests/qemu-extras.spec.ts`) fail when a published package lacks one.

## Development

Run `make dev-links` to symlink the PVE pm and js files that are currently altered, in order to be able to reload and observe changes quickly.
Note: There are still manual steps in this process due to the pvemanagerlib.js file being cached in the browser, and changes to the PVE API will often require a `systemctl restart pvedaemon pveproxy`

## Usage

Once the packages have been installed on a PVE host, the proxmox frontend will have additional options, some of which are listed here:

* Support for sparc32 guests with OpenBios or original boot PROMS (TODO: merge into deb)
  * Limited to the tested profiles: SS-5 (256 MB), SS-10 or SS-20 (512 MB), one CPU; see the [SPARC guide](https://debian.wshosting.no/guides/sparc/).
  * TODO: include ready-to-use SUN formatted raw images
  * Audio does not seem to work, but network is working so long as it is present when solaris is installed
  * The installation process may take a long time, and CPU usage will be stuck at around 100% on the host - this is normal, but you may want to pin the cpu core to a low frequency core or stick to a test system so that the performance is not reduced for other guests.

* Floppy disk support: a dedicated `floppy` storage content type (stored in `template/floppy` next to the iso folder) with upload/listing in the UI, up to two floppy drives per VM (A:/B:) with boot-from-floppy and live media swap - see the [floppy reference](https://debian.wshosting.no/reference/floppy/)

* Selecting an architecture and CPU outside of the default x86(-64) set

* Support for forwarding GTK/SDL UI and alsa/pulseaudio/pipewire audio to the host.
* The reason behind this is that old operating systems do not have matching virtio drivers, and some even benefit from the older devices such as cirrus or cg3 display. Those displays can not be used in combination with SPICE and VNC can be challenging to use especially with the mouse pointer bug (which is hacked together through a mousepad driver for operating systems that recognize such a device)
* TODO: In a future version I will add support for running UI/audio through a sunshine container so that the host does not need to be running a graphical interface.
* TODO: Alternatively you can pipe to another desktop machine on your network.

* Operating systems that are known to work (TODO: link to separate guides for these) are Linux as old as 2.x, SunOS 2.4 and up, MS-DOS 3 and up (performance improved with a curated collection of drivers and patches), Windows 1.x and up, Windows 9x with vbe enhanced drivers and 3dfx/mesa passthrough for 3d acceleration via patched 3d drivers
  * Additional guides, driver packs etc will be added at a later time

### Graphical forwarding to host

1. Start X as a regular user
2. Run `xhost SI:localuser:root` to allow root to connect to your session
3. Configure pulseaudio or pipewire to allow unrestricted access (similar to the above)
4. Start the guest with - TODO: opt-in configuration not implemented yet

#### Pulseaudio configuration

* For pulseaudio, add the following to /etc/pulse/client.conf:

```bash
default-server = unix:/tmp/pulse-server
enable-memfd = yes
auto-connect-localhost = yes
cookie-file = /tmp/.pulse-cookie
```

* Edit /etc/pulse/default.pa and modify the line related to the unix protocol:

```bash
load-module module-native-protocol-unix auth-group=audio socket=/tmp/pulse-server
```

* Add root to the audio group:

```bash
sudo usermod -aG audio root
```

TODO: start pulseaudio inside a headless container running sunshine
~ $ export XDG_RUNTIME_DIR=$TMPDIR
~ $ pulseaudio --start --exit-idle-time=-1

#### Pipewire

* Add the following to the file `/usr/share/pipewire/pipewire-pulse.conf` under the addresses section:

```bash
# Find this
pulse.properties = {
    # the addresses this server listens on
    server.address = [
        # And add the following section:
        "unix:native"
        {
          address = "unix:/tmp/pulse-server"
          client.access = "unrestricted"
        }
```

* Restart the service and verify that the unix-socket is created under /tmp

```bash
systemctl --user restart pipewire-pulse.service

ls -la /tmp/pulse-server

srwxrwxrwx 1 user user 0 Sep  6 21:41 /tmp/pulse-server
```
