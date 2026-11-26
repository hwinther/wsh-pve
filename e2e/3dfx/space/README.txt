wshspace - procedural 96 KB 3dfx space exploration & asteroid mining game
=========================================================================

A self-contained 3D space exploration, mining and dogfighting game in the spirit of .kkrieger and
late-1990s 3dfx space sims, built on the same portable C architecture and targets as wshdemo
(e2e/3dfx/demo). Every texture, 3D mesh, star system, HUD instrument, sound effect and ambient
music track is synthesized at run time from code -- zero external data files, under 96 KB per
executable, compiled for the original Pentium (-march=pentium, x87, no P6 CMOV/FCOMI).

Gameplay
  - Fly a 6DoF spacecraft from a 3D-cockpit canopy with a 3D holo-radar, target lock brackets and
    ballistic lead indicators.
  - Explore an 18-system procedural galaxy (Blue Giants, Solar G-Stars, Red Giants and Emerald
    Pulsars, each with nebulae, ringed planets, asteroid belts and orbital ring stations).
  - Shoot displaced 3D asteroids of four mineral types (FE, FUEL, AU, PLAS) to shatter them into
    fragments and scoop glowing resource crystals with your tractor beam.
  - Fight or evade patrolling Sentinel/Pirate interceptor drones in frontier star systems.
  - Dock near Orbital Outposts (or open the shipboard Field Synthesizer anywhere) to upgrade
    Plasma Lasers, Deflector Shields, Hyper Thrusters and Mining Tractors, refine Warp Fuel or
    patch Hull Plating, then engage Hyperspace Jumps through 3D warp tunnels to new star systems.

Targets
  WSHSPACE.EXE      Windows 9x/ME/2000/XP: Glide 2, Glide 3 or OpenGL (launcher menu or -api);
                    runtime-optional WinMM waveOut stereo synth audio
  DOS\WSHSPACE.EXE  DOS (DJGPP): Glide 2 through GLIDE2X.DXE; IRQ 9 hardware keyboard matrix,
                    INT 33h mouse flight, Sound Blaster auto-init DMA audio
  wshspace          i386 Linux (glibc 2.0+): Glide 2 through libglide.so.2; evdev + termios
                    input, OSS /dev/dsp stereo synth audio

Controls
  Arrows / Mouse    Pitch & yaw (press V to toggle mouse flight on Windows/DOS)
  W / S             Increase / decrease forward thrust & brake (+ / - step throttle)
  A / D or Q / E    Roll left / right
  Space / LMB       Fire converging plasma lasers
  Shift / B         Afterburner boost
  T                 Lock nearest hostile drone or asteroid in front of canopy
  M or Tab          Open / close Sector Galaxy Starmap (Arrows/WASD select system)
  J                 Engage Hyperspace Jump to selected nav-system
  U                 Open / close Outpost Engineering & Field Synthesizer (1..6 to build)
  F                 Toggle frame-rate & frame-time graph
  G / Shift+G       Gamma up / down
  R                 Cycle resolution: 640x480, 800x600, 1024x768
  Esc               Close overlay, or quit from cockpit

Options
  -api glide2|glide3|opengl   (Windows) select renderer directly
  -hostgl         (Windows) allow system OPENGL32.DLL in a window for host testing
  -res WxH        start at 640x480 (default), 800x600 or 1024x768
  -auto           autopilot demo mode (flies, mines, fights and jumps automatically)
  -seed N         custom galaxy seed
  -nosound        disable procedural synth audio
  -hud            start with the FPS graph visible
  -time S         quit after S seconds
  -bench N        benchmark N frames of full star-system flight without vsync
  -check          render deterministic scenes and verify pixel probes (exit 1 on mismatch)
  -audiotest      play the audio signature (below) through the platform's own sound backend, open
                  no display, and exit: PASS (exit 0) once the whole signal was mixed and 500 ms
                  more played out, FAIL (exit 1) without a sound device or after a 20 s timeout
  -nocom          (Windows, DOS) do not write to COM1

Audio test
  -audiotest plays the audio signature of e2e/wisp/audiosig.h (the header wisp's `soundtest sig`
  uses too): 8 segments of 500 ms, triangle waves of 400 + 100 k Hz on the left and 600 + 150 k Hz
  on the right in segment k, peak -6 dBFS, 4 s in all, at the backend's rate (22050 Hz on all
  three). e2e/audio/wavcheck.py --signature checks a recording of it (QEMU's -audiodev wav): each
  segment's frequency on each channel, the duration, no gaps over 2 ms, channels not swapped.
    Linux    OSS /dev/dsp, 16-bit stereo: audio-test.sh (a Debian kernel and initramfs, AC97;
             CI: audio-matrix.yml)
    DOS      Sound Blaster: 8-bit stereo auto-init DMA at exactly 22050 Hz on a DSP 4.x
             (SB16; older DSPs mono at 22222 Hz, which the check refuses as mono), BLASTER's
             A and D (default 220h, DMA 1), polled without an IRQ handler: 186 ms mixed ahead in
             a 743 ms ring, the DMA address read until both bytes agree, the bytes written and
             played counted so a bad reading or a step back of uclock() can't overwrite unplayed
             sound (it logs "AUDIO ... torn reads, glitches, clock steps back, resyncs" on
             close); e2e/3dfx/dos-test.sh runs it last in each boot on QEMU's sb16 (CI:
             3dfx-dos.yml)
    Windows  WinMM waveOut, 16-bit stereo, with no renderer (no menu, no Glide or OpenGL DLL
             loaded; -api only names one in the log). Passed wavcheck.py --signature once, by
             hand, in Windows 98 SE on AC97 with SigmaTel's STAC97 driver and pve-qemu-kvm's
             wsh/0170 (stage 3f, display reference): every frequency 0.68% high from Windows'
             22050 Hz conversion. The Windows 98 harness (e2e/3dfx/win98-test.sh, on the
             operator's own installed disk) could add such a run with `-audiodev wav`, as
             dos-test.sh does; COM1 carries the AUDIOTEST and PASS lines

Build
  make 3dfx-space
