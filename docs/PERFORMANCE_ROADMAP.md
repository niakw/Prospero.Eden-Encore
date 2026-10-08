# Eden Encore — CPU/HLE stability and 30 → 60 FPS research

Status: **engineering investigation only**, 8 October 2026. No shipped feature or
measured PS5 performance improvement is claimed by this document.

## The two separate results

1. **True emulation FPS**: the guest CPU, game logic, physics and render production
   advance faster. Taking a 30 FPS engine from 33.33 ms per real frame to 60 FPS
   requires a 16.67 ms total frame budget *and* correct game timing, if a legitimate
   game-specific 60 FPS modification is available. Changing the TV from 60 Hz to
   120 Hz does not achieve this.
2. **Perceived/display FPS**: the game continues to advance at 30 genuine frames/s,
   while a separate renderer interpolates an intermediate image for every pair,
   potentially presenting 60 frames/s. This does **not** update controller
   responsiveness, guest physics or animation logic twice as often.

The first is a performance/compatibility improvement; the second is image
synthesis. Neither repairs a stalled guest. Do not report synthetic output as
native game FPS.

## Priority A: locate FC27's real freeze

Evidence already observed in a previous hardware trace: the guest PC
`0x124AA117A8` remained unchanged for an extended interval despite host
present telemetry continuing. That suggests (but does not prove) a CPU/JIT,
synchronization, or HLE waiting problem rather than simple GPU overload.

- Establish a **baseline** on the current unchanged PS5 firmware 13.60 build,
  with reproducible boot/game save point and the original conservative CPU/JIT
  settings. Preserve the exact ELF/symbols for every hardware session.
- Repeat once with developer profiling to collect `EDEN_PERF_CPU_POINT`,
  `EDEN_PERF_PROGRESS`, `EDEN_DEV_HLE`, `EDEN_DEV_QUEUE`, and
  `EDEN_GAME_FRAME`/`EDEN_DEV_FRAME`. These are *different* signals; counting
  host presents cannot establish guest progress.
- Analyse text with:
  `python3 -B tools/analyze-fc27-trace.py <session-log.txt> --json`.
  Repeated guest PCs are **hypotheses**, not a diagnosis: real polling loops
  can legitimately hold their PC while other guest state progresses.
- Conduct one-variable-at-a-time A/B experiments for (a) backward/self JIT
  loop pre-emption, (b) dummy-thread wait ownership/lifetime, (c) service
  initialization blocking, and (d) I-cache coherency. Retain a fix only after
  guest-state liveness, replayed behavior, and extended idle/shutdown coverage.
- Compare host CPU consumption and per-frame GPU work before reducing rendering
  resolution. A stuck guest cannot be fixed by FSR or extra rendered frames.

Current experimental source flags are **OFF by default**:
`EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS`,
`EDEN_EXPERIMENTAL_ICACHE_COHERENCE`, and
`EDEN_EXPERIMENTAL_SM_HOST_WAIT`. They must **never be bundled together
into the baseline** without individual tests. Stable default per-core Dynarmic
JIT remains the comparison point.

## Priority B: real FPS improvements

Once repeatable baseline performance exists:

- Profile CPU/JIT compilation, HLE service latency, GPU queues, Vulkan buffer
  synchronization and game-specific graphics load. Remove actual bottlenecks
  first; tune presets only on measured hardware evidence.
- Investigate **per-game**, legally distributable community 60 FPS mods where
  the game can keep correct audio, physics, timing and input. A generic forced
  60 Hz guest clock is not safe for games built around 30 FPS.
- Test the unchanged 30 FPS original alongside each candidate. Record native
  1% low, worst-frame time, timing glitches, memory/VRAM, temperatures where
  observable, and crashes; avoid claims without matched A/B sessions.
- Keep native frame unlocks title-specific with a per-game fallback. No
  unverified 60 FPS patch is activated globally.

## Priority C: experimental optical-flow frame interpolation

**Candidate:** AMD FidelityFX FSR 3.1's Vulkan optical-flow/frame interpolation,
or a purpose-built, engine-independent optical-flow approach where guest motion
vectors/depth are unavailable. The public AMD FSR 3 frame-generation APIs are
*not* a drop-in emulator switch: they expect coherent frame inputs, correct
presentation/swapchain ownership, pacing and careful UI handling.

Reference: https://gpuopen.com/fidelityfx-super-resolution-3/
Reference: https://gpuopen.com/manuals/fidelityfx_sdk/techniques/super-resolution-interpolation/

A testable design must:

1. Capture two **completed distinct game frames** from the selected presenter.
   Do not extrapolate frames while the guest is frozen, static, or a pause menu
   is on-screen. Limit history to a bounded number of surfaces.
2. Evaluate 1080p input and stable 30 FPS output first. At 30 real frames/s,
   source-frame spacing is **33.33 ms**. True interpolation of frames A and B
   cannot calculate the midpoint until **B is complete**. Pacing A, synthetic
   midpoint and B every ~16.67 ms therefore normally needs source-frame
   buffering/delayed presentation, adding latency. Unbuffered extrapolation
   instead predicts an unknown future and can increase artifacts. Measure both
   GPU execution time **and end-to-end input latency** before considering 60
   presented FPS a user-visible improvement.
3. Keep synthesized-frame presentation independent of the guest simulation
   clock; present 30 real + 30 synthetic at 60 Hz without changing input,
   audio, save state, emulated vsync or game timing.
4. Treat menus/HUD as a **separate layer where possible**. Motion synthesis
   over FC27 player labels, UI glyphs, stadium advertising, fast balls, cross
   dissolves and replay cuts can produce strong ghosting. Enable detection,
   conservative fallback and a user-controlled OFF switch.
5. Collect real latency, drop, motion-artifact and PS5 GPU-memory measurements
   for both Vulkan and OpenGL. Any transport between OpenGL and Vulkan has
   to demonstrate no extra expensive full-frame copies or cross-API stalls.
6. Keep optical flow and frame generation entirely behind a future explicit
   **experimental per-game option**, OFF by default and disabled in Safe Launch.

### Decision criteria

A pilot is worth continuing only if 1080p 30→60 *presented* FPS actually works
on the PS5 firmware 13.60 target with predictable GPU timing, reasonable
latency and no guest crashes, artifacts or increased FC27 hangs. AMD recommends
a faster base game than 30 FPS for its general frame-generation technology;
**60 smooth synthesized FPS from 30 source FPS is a research goal, not a
promise**. The PS5 AMD RDNA2 platform does not provide NVIDIA's
`VK_NV_optical_flow` hardware extension. Do not assume newer AMD RDNA4
machine-learning frame generation is available on PS5.

### Deliberately not implemented yet

- No fake `FPS boost` toggle or shader that merely duplicates frames.
- No forced emulation clock, broken game physics, or CPU/JIT patches by default.
- No external PC-only frame generator bundled into a native PS5 application.
- No assertion that frame interpolation resolves FC27's stalled guest.

## Reproducible output and credit requirements

Any performance feature must ship with baseline-vs-candidate traces, exact
source commit, console firmware, renderer, video settings, test duration,
real/presented FPS recorded separately, and an OFF/rollback path. If AMD code
or another optical-flow library is **actually integrated later**, its author,
project maintainers and license must be added to `README.md`,
`THIRD_PARTY_NOTICES.md` and the installed legal bundle first.

Offline trace analyzer: `tools/analyze-fc27-trace.py`.
Regression: `python3 -B tools/check-fc27-trace.py`.
