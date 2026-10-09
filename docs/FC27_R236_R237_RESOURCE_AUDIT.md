# Eden Encore — FC27 R236/R237 CPU / GPU / VRAM / RAM audit

*2026-10-09. Real PS5 FTP logs read from the authorized Mac in memory, no Mac/PS5 writes. DEV branch only; no build or CI run authorized after R237.*

## Findings supported by the console logs

**R236:** `heap.prev.log`: 158 frame windows / 793.0 s; weighted presented FPS **26.61**, 24 5-second windows below 20 FPS, minimum **12.18**; 2,109 inter-frame intervals >50ms and 71 >100ms, maximum interval **760ms**.

**R237:** `heap.log`: current ongoing trace observed at 333 windows / 1671.2 s; earlier at 83 windows / 416.54 s weighted FPS **28.04**; matched first-83-window R236 baseline weighted FPS **28.13**. R237 matched prefix has 586 >50ms intervals vs R236 497, 44 >100ms intervals vs 50. These are **same duration, not necessarily same match scene**. The 8 bounded cache-lock spin attempts recovered ~20% of lock acquisitions without kernel blocking, but did **not** improve measured overall smoothness; default reverted to zero, while bounded `cache_spin=N` opt-in remains. Do not claim successful FPS improvement.

### CPU and Dynarmic

- `EDEN_WORKER_TOPOLOGY ready=1 distinct_cores=5 cpus=0,1,2,3,4 amd_ext=1 x2apic=1`. Core0/1/2 guest worker threads each have their own allowed logical CPU; GPU is separate. This does **not** identify spare parallel work inside a single guest thread. Core3 of the emulated Switch guest is inactive, which is not evidence of a misplaced physical PS5 core.
- The **owner-thread** CPU clocks were qualified (`EDEN_PERF_OWNER_CLOCK_CHECK valid=1`); cross-thread/process clocks were invalid (`EDEN_PERF_CPU_CLOCK_CHECK valid=0`). Never use cross-thread worker CPU metrics for percent utilization. At 12.54 FPS R236 window #90, guest owners each accrued ~5.0s CPU time in the ~5s sampling interval. At 29.9 FPS R236 #69, each accrued ~4.98s too: full thread occupancy *alone* does not isolate the slowdown.
- R236 #90 at 12.54 FPS: **26 ms** summed JIT compilation across all 3 guest cores in five seconds; **848** new compiled blocks. GPU queue-full wait **58 ms** in five seconds; GPU worker own CPU **~881 ms** and wait **~3993 ms**. Guest-dequeue wait near zero, guest IPC cumulative delta **~470 ms**. None of these individual sampled costs accounts for the huge 12-FPS drop by itself.
- R236 #89 at 12.18 FPS: JIT compile **81 ms**, queue-full **51 ms**, guest core owner CPUs **5.04/5.04/5.02 s**. R237 #69 at 15.28 FPS: JIT compile **69 ms**, queue-full **106 ms**, GPU worker CPU **975 ms**, queue-wait **3894 ms**, owner guest CPUs **5.03/5.04/5.04 s**. R237 #96 at ~15.5 FPS: JIT **44 ms**, queue-full **59 ms**, GPU worker waits **4077 ms**; guest CPU owners each ~5s. The late-match performance problem is not simply an incomplete JIT cache or slow GPU queue saturation.
- Some bad earlier windows (e.g. R236 #30 at ~17.9 FPS) **DO** coincide with ~1.22s summed JIT compiling and 50k new blocks/5s. There are therefore multiple causes at different game phases, not one universal FPS switch.
- Dynarmic per-core JIT is compiled and running. Cross-core JIT sharing/precompiled history/compile batching are disabled; they could affect first-visit compilation but would not explain the #90 late-match stall with 26ms compilation. Do not enable unsafe shared memory code globally without an independent correctness proof.
- `idle_spin_iterations=5000` retains the experimentally previously qualified short guest WFI spin. A slow 5s window cannot be interpreted as evidence of excessive WFI spinning without hot PC sampling or more detailed native thread profiling. More affinity or higher thread priority cannot speed up serial work already saturating a host core.

### Native GPU thread and hardware GPU

- R237 slow windows include GPU worker wait of roughly **3.9–4.2s / 5s**, with the worker actively running ~0.6–1.0s. Present/fence/queue-full durations are small compared with the 5-second window. This suggests the *emulator GPU dispatcher* is not the continuous hot host thread.
- **Important:** GPU worker wait is **not** a GPU hardware utilization percentage. Neither Vulkan GPU timestamp query-based timing nor AGC device utilization is proven in these logs. It is wrong to claim the hardware GPU is underutilized based solely on the host GPU worker.
- Vulkan shader cache loads successfully (~505 pipelines); initial `EDEN_GPU_PRMT_IMM_INDEX` notices remain compatibility evidence. They cannot be treated as a proven late-match FPS cause. No proof of repeated shader compilation every 5s.
- Renderer configuration during recorded tests: internal **1×**, output **1440p**, FXAA and Vulkan, 60 Hz requested / 59.94 Hz physical mode, async shaders ON, GPU accuracy High. Changing resolution/GPU accuracy may provide a bounded graphics A/B but cannot be assumed to solve a CPU-side bottleneck.

### VRAM / direct memory / JIT / RAM

- `EDEN_DEV_MEMORY direct_memory=12884901888`: **12 GiB direct-memory pool**, shared by native PS5 graphics and other allocations, not an independent PC-like dedicated VRAM allowance plus an unrelated RAM pool.
- R236 Vulkan texture-cache usage near the end: **4,494,196,736 bytes (~4.19 GiB)**, expected mark **4,724,464,026 bytes (~4.40 GiB)**, critical **5,583,457,485 bytes (~5.20 GiB)**; `memory_short=0` across samples. R237 near middle usage **4,427,087,872 bytes (~4.12 GiB)** below expected. This is **texture cache accounting**, not full hardware VRAM or GPU demand.
- Sparse JIT real physical commits grew from ~400 MiB at core start to **1,535,115,264 bytes (~1.43 GiB)** near the end of R236, **1,560,281,088 bytes (~1.45 GiB)** at the later R237 point, with ~**2,281,701,376 bytes (~2.13 GiB)** virtual reserve. No new `bad_alloc` or direct-memory shortage in these sessions. Increasing a JIT arena or forcibly lowering texture thresholds is not evidence-based when the slow period has almost no JIT compilation.
- The guest's `Memory_4Gb` layout specifies **guest emulated address space**, not a recommendation to allocate extra PS5 system RAM. Resident allocations, address maps, and GPU textures must not be summed as if all counters were unique physical allocations without checking aliasing.

### Menus and controller

- R236 launcher `slow frame: draw 130 ms`; R237 first launcher draw still **131 ms**, with a **34 ms texture upload**. The R237 triple VBO fix has not been proven to remove the startup draw stall. Keep approved visual design; targeted GL pipeline/shader warm-up and async resource upload measurements come before further rewrites.
- `EDEN_PAD_CONTEXT mode=gameplay reason=sustained_activity sticky=1` in R236/R237 proves the controller's *guest A/B/X/Y mapping* changed based on physical motion, not a game-supplied scene signal. This is intrinsically unreliable for FC27. The revised dev source now resolves the global or per-title selected layout **once before `Pad::Open`**, locks `SetMapping` after open, and applies the same mapping through gameplay, menus, and cinematics, with no heuristic/toggle. `ResolveSessionButtonMapping` is used in main launcher and game mapping UI. The live FC27 match previously used Switch-position mapping after the auto change: selecting a fixed PlayStation-face mapping **can change in-match physical behavior** and must be checked at next authorized hardware run. A fixed Switch-position mapping can instead be selected from the game's settings if that is the desired physical behavior.
- Native in-game glyph textures are separate from HID mapping. FC27 `rule=unsupported`, no verified title/version RomFS PS art. A fixed button map will NOT magically replace Nintendo artwork in menus/cinematics.

## Required next engineering step — not a blind memory/resource increase

1. **After user authorization ONLY:** compile the currently staged static mapping and smoke-test: launcher → FC27 menu → game → pause/menu → gameplay, including face buttons, triggers and Touchpad+L1; compare selected PlayStation/Switched mapping. No builds/runs without explicit permission.
2. Qualify **native host PC sampling on firmware 13.60** for guest CPU owners, or use verified low-overhead timing around Dynarmic run slices and guest/kernel scheduling. Collect *which native/guest functions* occupy cores in identical 30 FPS vs 12–16 FPS situations. Avoid enabling older firmware ucontext signal registers without checking ABI.
3. Add **Vulkan GPU timestamp / queue-fence evidence** (if current RADV/PS5 driver supports correctly), separately from GPU worker thread CPU/wait counters, to determine actual GPU-hardware bottlenecks before raising GPU accuracy/performance or lowering output.
4. Reproducible **scene-aligned** frame-window A/B (not merely matched elapsed time); separate shader/JIT-first-visit window from steady match. Use staged `tools/analyze-ps5-frame-windows.py` against the two original log snapshots; no file edits required by analyzer.
5. Only optimize the measured CPU/JIT, GPU submission, synchronization, and memory hot paths that correlate with the slow window. Do not combine multiple unmeasured experimental toggles in one build.

**Status:** static mapping source fixed but NOT native-compiled or PS5-tested; performance bottleneck narrowed to guest execution critical path, NOT yet fully identified; GPU utilization / glyph art still OPEN. All GitHub edits use `[skip ci]`; no new build or run initiated, and no Mac/PS5 files written.
