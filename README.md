# wsh-pve

WSH Proxmox Virtualization Environment patches

## Build

Run `make build-containers` to build the PVE build image which creates debian packages from the submodules and the djgpp build image which is used to build windows drivers.
This is an optional step as the packages are already available in this github repository.

Run `make all` to build the debian packages and copy them into the build directory.
Run `./repo-update.sh` to populate a debian package repository under the repo directory, you will need a gpg key in order to sign the packages.

Run `make 3dfx` to build the qemu-3dfx windows drivers and a patched version of the PVE QEMU package which supports passthrough

## Development

Run `make dev-links` to symlink the PVE pm and js files that are currently altered, in order to be able to reload and observe changes quickly.
Note: There are still manual steps in this process due to the pvemanagerlib.js file being cached in the browser, and changes to the PVE API will often require a `systemctl restart pvedaemon pveproxy`

## Usage

Once the packages have been installed on a PVE host, the proxmox frontend will have additional options, some of which are listed here:

* Support for sparc32 guests with OpenBios or original boot PROMS (TODO: merge into deb)
  * This is often limited to SuperSparc 5, single cpu and 512mb ram, depending on the OS and other details.
  * TODO: include ready-to-use SUN formatted raw images
  * Audio does not seem to work, but network is working so long as it is present when solaris is installed
  * The installation process may take a long time, and CPU usage will be stuck at around 100% on the host - this is normal, but you may want to pin the cpu core to a low frequency core or stick to a test system so that the performance is not reduced for other guests.

* TODO: add feature for floppy mounting

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
