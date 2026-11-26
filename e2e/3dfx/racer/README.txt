wshracer -- procedural 3dfx anti-gravity hover-racer (<= 96 KB, zero data files)
================================================================================

wshracer is a self-contained, .kkrieger-inspired 3D anti-gravity hover-racing
game for 3dfx Glide 2, Glide 3, and OpenGL 1.1. Every mipmapped texture, 3D
hovercraft and gantry mesh, closed-loop 3D spline circuit, and 138 BPM
electronic racing soundtrack + hover-turbine synthesizer is generated
procedurally at startup or run time with zero external asset files.

All binaries compile for an original Intel Pentium (-march=pentium, x87 FPU,
verified free of P6 CMOV/FCOMI/SSE instructions by check-3dfx-drivers-isa.sh)
and fit comfortably inside a 96 KB executable/game-code budget.


Targets & Building
------------------
Run `make 3dfx-racer` from the repository root to build all three guest targets
into `build/wshracer/{windows,dos,linux}`:

  1. Windows 9x/ME/2000/XP (`build/wshracer/windows/WSHRACER.EXE`):
     Single freestanding PE executable supporting Glide 2 (`GLIDE2X.DLL`),
     Glide 3 (`GLIDE3X.DLL`), and OpenGL 1.1 (`OPENGL32.DLL`). Imports only
     `KERNEL32.DLL`, `USER32.DLL`, and `GDI32.DLL` (`WINMM.DLL` is loaded at
     run time for 22050 Hz stereo `waveOut` audio if available). Pass `-hostgl`
     to run directly against a modern Windows host GPU OpenGL ICD in a window.

  2. MS-DOS / FreeDOS (`build/wshracer/dos/WSHRACER.EXE`):
     DJGPP protected-mode DPMI executable supporting both Glide 2
     (`GLIDE2X.DXE`, default) and Glide 3 (`GLIDE3X.DXE`, via `-api glide3`),
     chained IRQ 9 scancode matrix for simultaneous held keys, optional INT 33h
     mouse steering, and polled Sound Blaster 8-bit auto-init DMA audio (stereo
     on SB16 DSP >= 4.x, mono on older cards).

  3. Linux i386 (`build/wshracer/linux/wshracer`):
     32-bit ELF executable linked against `libglide.so.2` and `libc.so.6`
     requiring nothing newer than `GLIBC_2.0`, with Linux `evdev` + raw TTY
     input and non-blocking OSS `/dev/dsp` stereo audio.

  4. Host Surfaceless Mesa EGL (`plat_egl.c`):
     Headless OpenGL runner for automated `-check`, `-bench`, `-audiotest`,
     and screenshot generation without an X server.


Circuits & Controls
-------------------
Four distinct procedural 3D spline circuits with superelevated banked turns,
elevation crests/drops, enclosed neon tunnels, chevron turbo pads, energy
recharge strips, and 5 rival hovercraft teams:

  1. REDROCK CANYON   -- Sunlit desert sandstone cliffs & sweeping canyon S-bends
  2. NEON METROPOLIS  -- Midnight cyber-viaduct & glowing enclosed light-tunnels
  3. PACIFIC ATOLL    -- Turquoise ocean highway & sunlit island cliffs
  4. GLACIER PEAK     -- Alpine ice circuit with steep plunges & snow walls

Controls:
  Left / Right, A / D   Steer hovercraft
  Q / E                 Left / Right airbrakes (carve tight hairpins)
  Up / W / RMB          Thrust
  Down / S              Brake
  Space / Shift / LMB   Engage manual capacitor Turbo Boost
  Z                     Toggle mouse steering capture (Windows/DOS)
  C or V                Toggle Chase Camera / Nose Cockpit Camera
  1 .. 4                Switch racing circuit (1..4)
  Enter                 Advance to next circuit
  P                     Toggle AI autopilot
  M                     Toggle 138 BPM electronic music
  H                     Toggle HUD overlay
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
  -track 1..4                 Start on circuit 1..4
  -auto                       AI autopilot showcase mode (rotates circuits)
  -nosound                    Disable audio output
  -nohud / -hud               Hide or show HUD
  -gamma G                    Initial display gamma (0.3 .. 3.0)
  -time S                     Exit cleanly with PASS after S seconds
  -check                      Deterministic pixel-probe self-test (prints PASS/FAIL)
  -bench N                    Render N unthrottled frames and report FPS
  -audiotest                  Play the 4 s deterministic stereo triangle signature
                              (e2e/wisp/audiosig.h) without opening a 3D display
  -hold S / -wait S           Hold final frame or sleep before opening display
  -tag NAME                   Override log prefix (default: WSHRACER)
  -nocom                      Skip COM1 serial logging (Windows/DOS)
  -log FILE                   Append log lines to FILE (Windows)
