wshkeep: Procedural 3dfx Subterranean Citadel & Dungeon Crawler (<= 96 KB)
==========================================================================

`wshkeep` is a `.kkrieger`-inspired procedural 3D first-person subterranean
dungeon crawler for 3dfx Glide 2, Glide 3, and OpenGL 1.1. Every ashlar stone
wall, gothic flagstone mosaic, iron-banded oak door, caustic water/magma canal,
sculpted 3D monster, held polearm/staff, flickering torch flame, and cathedral
pipe-organ + echo audio sample is synthesized at startup or runtime from compact
Pentium-safe (`-march=pentium`, `--no-p6`) x87 math with zero external data
files.


Building
--------
From the repository root:

    make 3dfx-keep

This builds all three guest binaries into `build/wshkeep/`:

  1. Windows 95/98/ME/2000/XP (`build/wshkeep/windows/WSHKEEP.EXE`):
     Single freestanding PE executable (< 96 KB, no MSVCRT dependency, static
     imports from `KERNEL32.DLL`, `USER32.DLL`, and `GDI32.DLL` only) supporting
     Glide 2 (`GLIDE2X.DLL`), Glide 3 (`GLIDE3X.DLL`), OpenGL (`OPENGL32.DLL`),
     and modern desktop OpenGL (`-hostgl`), with runtime-optional `WINMM.DLL`
     16-bit stereo `waveOut` audio.

  2. MS-DOS / FreeDOS (`build/wshkeep/dos/WSHKEEP.EXE`):
     DJGPP protected-mode DPMI executable supporting both Glide 2
     (`GLIDE2X.DXE`, default) and Glide 3 (`GLIDE3X.DXE`, via `-api glide3`),
     chained IRQ 9 scancode matrix for simultaneous held keys, optional INT 33h
     mouse look, and polled Sound Blaster 8-bit auto-init DMA audio.

  3. i386 Linux (`build/wshkeep/linux/wshkeep`):
     Freestanding `_start` ELF binary (< 96 KB, `GLIBC_2.0` symbol floor) linked
     against `libglide.so.2` and `libc.so.6` only, supporting `/dev/input/event*`
     simultaneous held keys, raw TTY fallback, and optional OSS `/dev/dsp` audio.


Dungeon Floors & Gameplay
-------------------------
Explore 4 procedurally carved subterranean floors (looping deeper with rising
difficulty):
  - Floor 1: OBSIDIAN BASTION   (torchlit ashlar vaults & underground cisterns)
  - Floor 2: FLOODED CATACOMBS  (mossy crypts & emerald subterranean canals)
  - Floor 3: EMBER FORGE        (basalt foundry halls & glowing magma channels)
  - Floor 4: ASTRAL SANCTUM     (obsidian citadel & Sanctum Archon guardian)

Seek the floating Golden Runic Key in each floor's vaults to unseal the
Runegate guarding the Sanctum, defeat its guardians, and step into the
shimmering Descent Portal!


Controls
--------
  W / S or Up / Down    Move forward / backward
  A / D                 Strafe left / right
  Left / Right or Q / C Turn left / right
  PgUp / PgDn           Look up / down
  V or Z                Toggle mouse look (turn + pitch + LMB attack / RMB door)
  Space / Ctrl / LMB    Attack with active weapon
  E / Enter / RMB       Open oak door / unseal Runegate (with Runic Key)
  Shift                 Sprint
  1 / 2 / 3             Select weapon:
                          [1] IRON HALBERD  (sweeping melee cleave, 0 Arcana)
                          [2] EMBER ROD     (rapid dynamic-light firebolts)
                          [3] STORM SCEPTER (area shockwave arcane orb)
  Tab or M              Toggle full-screen Citadel Automap overlay
  P                     Toggle BFS dungeon exploration & combat autopilot
  H                     Toggle HUD
  F                     Toggle FPS & frame-time graph
  G                     Cycle hardware gamma (1.0 .. 1.8)
  R                     Cycle supported resolutions (up to 1600x1200 on Glide,
                        1920x1080 on OpenGL)
  Esc                   Quit


Command-Line Options
--------------------
  -api glide2|glide3|opengl   Select 3D API (Windows: glide2/glide3/opengl;
                              DOS: glide2/glide3)
  -hostgl                     Run in a window on a modern Windows OpenGL ICD
  -res WxH                    Glide: 640x480, 856x480, 800x600, 960x720,
                              1024x768, 1280x1024, 1600x1200; OpenGL: 640x480,
                              800x600, 1024x768, 1280x960, 1280x1024,
                              1600x1200, 1920x1080
  -floor 1..4                 Start on a specific dungeon floor
  -seed N                     Set deterministic dungeon seed
  -auto                       Engage BFS dungeon autopilot on startup
  -nosound                    Disable procedural synth & SFX audio
  -hud / -nohud               Force HUD on or off
  -gamma G                    Set initial gamma (e.g. 1.3)
  -time S                     Exit cleanly after S seconds
  -check                      Render deterministic Citadel frame & verify 6
                              pixel probes (exits 0 on PASS, 1 on FAIL)
  -bench N                    Run N unthrottled benchmark frames and log FPS
  -audiotest                  Play the 4 s deterministic stereo triangle signature
                              (e2e/wisp/audiosig.h) without opening a 3D display
  -hold S / -wait S           Hold final frame or wait before opening 3D device
  -tag NAME                   Override log line prefix (default: WSHKEEP)
  -nocom                      Skip COM1 serial logging
  -log FILE                   Write log lines to FILE
