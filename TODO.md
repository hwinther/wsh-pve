## pve-manager extensions

This is a collection pve UI extensions that cover the edge cases I've encountered with my usage pattern

- Add ne2k_pci and pcnet to network card selector
- Add sb16, adlib and pcspk to audio device selector (this will only work in combination with spice for now)
- Add cirrus as an explicit choice to VGA driver selector (while this can already be achieved through windows version in OS selection below version 6 (win2k, winxp) I prefer to define this explicitly)

TODO

- Create a public apt package repository
- Setup CI to deploy to the apt repo
- Add VNC audio support
- Add support for selecting in UI and using other architectures such as sparc64
- Add support for selecting floppy images in UI
- Add support for adding/changing hookscripts in UI
