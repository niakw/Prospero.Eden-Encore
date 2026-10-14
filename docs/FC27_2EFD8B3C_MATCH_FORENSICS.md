# Gameplay session postmortem: native build 2efd8b3c

Read-only FTP collection and analysis on 14 October 2026. The owner reports a completed match with cleared game/shader cache, overridden in-game action assignments, image stutter, delayed HUD and an end-of-match freeze **with the game still open**. This testimony is independent evidence; none of the sampled counters are substituted for direct observation.

## Provenance and safety

`boot-trace.txt` and the beginning of `heap.log` independently give `source_sha=2efd8b3c96608667a2b22f1751eed1a475091cce`, firmware 13.60. The owner supplied the GitHub green package run `38484009009` at that SHA. The read-only acquisition covered `heap.log`, `stderr.log`, their previous rotated copies, `network-accepted.log` and two boot traces. Copies remain **only in the owner's Mac `/tmp/eden-encore-audit-20261014-test-2efd8b3c/`**. No raw logs, IP, username, title save, credentials or other console data was committed to the public GitHub repo. No filesystem writes were made over FTP and no game processes or caches were modified.

## Frame and workload evidence

- **415** consecutive native five-second performance windows: **2,083.795 s** (~34 min 44 s) of instrumentation, 60,955 cumulative compositor callbacks (not TV scanouts). PS5 output display reports **60 Hz**.
- **333** windows report ~30 FPS; **329** of those have no compositor interval over 38 ms. The output was **not smooth throughout**: there are **63** per-frame delays over 100 ms and **10** over 500 ms, with a maximum **1,288.129 ms**.
- Last **44** windows (~221 s) have a median exactly 30 FPS. Across that tail the GPU still advances **6,627 frames**, **2,630,919 draws** and **72,897 dispatch calls**; the guest concurrently advances **344,793 IPC calls** and **2,488,512 CPU writes**. None of the five `EDEN_GPU_DRAW_DROP` reasons (pipeline, configuration, descriptor, worker) has a nonzero total.
- No `EDEN_GPU_REPORT_STALLED` is present in the new `stderr.log`. This **differs materially** from the prior rotated session, whose GPU report stopped at frame 9,480 for over 28 minutes. These new logs **do not show a persistent renderer/GPU-owner deadlock**. They do show continued emulator activity with a visually frozen title.
- GPU queue saturation is unsupported: `gpu_full_ms=0` in all 415 windows, GPU idle ~3.77 s per five-second window (median) versus ~1.24 s dispatch, and no dropped draws.
- Early actual stutter is correlated with JIT compilation and cache contention: `corr(worst_ms, JIT_ms) ≈ 0.50`, `corr(FPS, cache_wait_ms) ≈ -0.48`, `corr(worst_ms, cache_wait_ms) ≈ 0.28`. The slow 35 windows (worst interval >100 ms) have median cache wait ~34 ms versus ~0.37 ms for 329 truly stable windows. **These are window-level correlations, not evidence that either operation alone blocked a specific frame.** Diagnostic mode was on (`EDEN_FRAME_PROFILE detailed=1`), which has nonzero instrumentation overhead.
- `IHOSBinderDriver` command 3 (`TransactParcelAuto`) consumes a median ~1,159 ms of **cumulative HLE time per five-second window**, but its correlation with the worst callback interval is about **-0.14**. This is not good evidence that its normal buffer IPC activity caused the actual stutters; do not change mutex, fences or queue depth based solely on cumulative HLE time.

## Strongest end-of-match transition

Around cumulative frames **32,000–32,500**, several **distinct guest services stop receiving requests** even as the GPU and graphics buffer submission continue:

| Service | First flat snapshot | Approximate flat tail |
| --- | ---: | ---: |
| `IStorage/0` | frame **32,190** | **963.9 seconds** |
| `IHardwareOpusDecoder/9` | frame **32,491** | **953.8 seconds** |
| `IHOSBinderDriver/3` | still incrementing at **60,955** | not stopped |

The last large (>100 ms) compositor callback spike is near frame 32,073. About **16 minutes** of further GPU draws, image submission and guest IPC follow without resumed requests to the two audio/storage endpoints. The title was visibly frozen after the match while still opened. Together these facts support **a candidate guest-application progression stall**, not a proven application deadlock: silent/static menus can intentionally stop requesting media/storage, and a new graphics buffer does not guarantee new gameplay/HUD state.

To reproduce the numeric inference offline, run `python3 -B tools/analyze-guest-progress-stall.py /path/to/heap.log`. The regression self-test, which also tests healthy and missing/unknown source cases, runs in both core and native preflight. It **never** concludes that guest game instructions stopped executing, nor infers a guest program-counter or save-file state from passive counters.

## Controller binding: fix the previous diagnostic interpretation

`stderr.log` confirms the physical PS pad sample reader remained active (506,250 polls, 1,363,726 usable samples, **0 reported read errors**). Physical face-button edges continued, including Cross 239 and Circle 212.

The title starts with:

```text
EDEN_PAD_MAPPING_FIXED title=0100c49025d3e000 layout=0 a=0 b=1 x=2 y=3 title_override=1 own_mapping=0
EDEN_PAD_MAPPING_CONTEXT title=0100c49025d3e000 mode=game_owned a=0 b=1 x=2 y=3
```

Here **`own_mapping=0` means no custom mapping in the *Encore per-title launcher preferences***, while `title_override=1` is triggered by the chosen per-title *layout*. The message `mode=game_owned` is a **literal text constant** printed at startup, not a detector that the **FC27 in-game match action settings were saved, loaded or applied**. Source runs `pad->SetMapping(mapping)` once, before the guest launches. The pad producer maps physical Cross -> guest A and Circle -> guest B consistently in menus and matches. No source changes the mapping on entry to gameplay. It is incorrect to assert, based on those logs alone, that Encore overwrites the title's custom match action assignments at runtime.

The in-game action scheme and its guest-save/profile ownership are not exposed in this telemetry. Whether FC27 is accepting its own custom action scheme in a match, or instead using a default player profile/controller type, is still an **open guest-level issue**. Do not mask it by swapping the launcher button mapping in the middle of gameplay: that would risk breaking menus, pauses and cutscenes and would not prove the user-configured actions work.

## Clear separation from prior fixes

Previous host simulations and bounded `vkAcquireNextImageKHR` changes were source-correctness work, **not sufficient proof of FC27 smoothness**. The earlier 28-minute *GPU counter stopped* signature is absent in this **one** new session; the build may have avoided that class of stall, but no causal assignment is possible. Persistent match judder and the post-match state stall both remain uncorrected.

**Correction order:** (1) preserve evidence at ~frame 32k without changing global rendering sync; identify the guest thread's last successful phase transition, profile/save requests and action-profile selection; (2) profile the real JIT and cache-lock stall sites during the first 32k frames; (3) only change the renderer if a completed present-frame versus actual scene freshness mismatch is demonstrated. A clean 30-FPS callback rate must never be used as a fix criterion. Avoid another user PS5 trial for forensic-only changes.

## Independent title compatibility evidence and next fix boundary

The emulator project's upstream issue [eden-emulator/Issue-Reports#692](https://github.com/eden-emulator/Issue-Reports/issues/692) remains open: it reports FC27 failure when entering offline Career or Tournament. **That reproduction is at mode entry, not a proven reproduction of the current end-of-match still-frame.** It motivates cross-platform investigation of guest execution and applet/FS behavior, not a blind native graphics substitution.

The official [FC27 input accessibility notes](https://www.ea.com/able/resources/ea-sports-fc/fc-27) describe separate controls for gameplay remapping versus menu navigation. Independent community reports from September 2026 describe FC27 custom-controller presets not being applied as expected and recommend rebuilding a new title-owned custom preset from Classic, explicitly using **Save FC Profile**, and relaunching the title. Those reports are not console-specific evidence and do not justify host remapping or tampering with guest saves.

Read-only save-directory **metadata only** show one active game save and one older directory containing only an emulator save-size marker. SaveDataFactory::ReadSaveDataSize and WriteSaveDataSize both invoke GetOrCreateDirectoryRelative, so an empty metadata-only directory is **not evidence of a competing active user profile**. Current evidence does not establish a save-profile mismatch; never migrate, merge, overwrite or delete user save content based on this observation. No game save contents, profile IDs, IPs or raw logs were committed.

Game progress stall and gameplay action profiles remain separately unresolved. **CI boundary:** tools/analyze-guest-progress-stall.py --self-test and tools/check-fc27-match-input-profile.py were both executed successfully on the owner's Mac. They verify forensic classification and constant physical-button routing only. A green source preflight does not prove smooth game animation, successful profile loading or actual in-match action correctness. Keep original tested baseline 2efd8b3c unmodified; no new console package is justified by a test-only change.


## Offline guest-thread transition and non-invasive follow-up

The pre-existing five-second repeated-workload analyzer on the original
`2efd8b3c` heap log finds a ~945-second stable tail from frame 32,641 to
60,955: approximately 397 draws, 376 guest CPU writes and 52 completed IPCs
per compositor callback. This is strong evidence of *repeated work* but
not a pixel hash, scanout capture, or verified frozen application state.

The `EDEN_PERF_CPU_POINT` records around frame 32,000 show a marked loss of
per-core observed PC diversity: core 0: 167 distinct PCs in 222 snapshots
before versus 10 in 193 after; core 1: 144 versus 29; core 2: 140
versus 12. Core 0's sampled `CpuPhase::Kernel` increases from 7/222 to
95/193. These are JIT entry/exit **boundary samples**, not an interrupt-time
backtrace of running guest instructions, and their pre-existing `thread=0`
was a placeholder. Core 3 has no valid sample. The CPU points establish
a changed workload, **not** which title thread is blocked or why.

The next development-native diagnostic records the actual guest thread ID
for an epoch-sampled CPU point, using `CpuSampleDue` to avoid a kernel
thread lookup on every JIT entry/exit. It also records `EDEN_DEV_IPC_ACTIVE`
for the eight longest still-in-flight guest IPCs exceeding 500 ms at each
five-second report. In contrast, `EDEN_DEV_IPC_THREAD` tracks only
**completed** waits. These probes are gated by detailed development profiling,
leave IPC return values and scheduling unmodified, and are explicitly **not a
gameplay fix**. The profiling itself can perturb frame timings.

No guest saves, control settings, network filters, renderer queue depth,
kernel scheduler priorities, or applet states were changed. A new console
package is not warranted solely by the source-level proof of these probes;
a future diagnostic run must correlate `EDEN_PERF_CPU_POINT thread=` with
`EDEN_DEV_IPC_ACTIVE tid=` and the freeze transition before choosing a
corrective patch.


## Paired upstream scheduler lock correction (new development candidate)

Source review identified a coherent two-part upstream kernel correction not
present in the pinned archive: upstream #4436 replaces actively spinning
context/slab locks with `std::mutex`; #4447 handles lazy mutex backing
materialization on libc++ before two scheduler unlock sites. The pinned
archive still had `Common::SpinLock`, so #4447 alone would be inapplicable.

Both source changes are maintained together under
`vendor/encore-active/eden-threading/src` and compiled as a curated,
reversible unit with `EDEN_BLOCKING_GUEST_CONTEXT_LOCKS=ON` (default);
`OFF` restores the pinned source and old guard headers. Native compilation
and title-level regression have not yet been established. The change follows
the upstream authors' paired correctness fix, not a conclusion that any
particular FC27 end-of-match wait is the root cause.

The candidate must pass source/host verification and full native packaging
before console evaluation. Do not alter user save data, network blocking or
controller mappings to evaluate it. Host tests cannot establish that a title
freeze is solved; a meaningful qualification must compare **actual game
progress and frame latency**, not compositor 30 FPS alone.

## Title-owned match action presets: cross-platform evidence (14 October 2026)

The old title log reports layout=0 and own_mapping=0, with stable physical
button mapping and HID samples continuing. These fields do **not** prove
which custom action preset was loaded by the guest at kickoff. The current
SaveDataFactory::Open/GetFullPath path-selection algorithm is identical
in the pinned guest source and the latest reference source inspected.

External players report a distinct game-level problem: customized controls
can be saved in the settings screen but not selected on the pre-match
Select Sides screen; another report suggests selecting and saving the
active in-game profile, restarting, and explicitly saving the game profile.
These reports are platform-specific anecdotal evidence, **not** a verified
root cause on this guest version. Sources:
- https://www.reddit.com/r/EASportsFC/comments/1uahomt/
- https://www.reddit.com/r/EASportsFC/comments/1wjhng8/
- https://www.ea.com/able/resources/ea-sports-fc/fc-27

Next qualification: compare the active controller preset at pre-match side
selection with the title's in-match controls. Preserve the user's saves;
do not synthesize gameplay actions from the launcher or confuse glyph
appearance with the title's own controller action scheme. No gameplay
mapping correction is claimed yet.

## Publisher-confirmed title action preset bug (14 October 2026)

The publisher's official FC27 update **1.0.1** explicitly lists a
gameplay bug where users with a custom control preset could sometimes
not perform the intended actions, and describes this as fixed. The
official international game-info hub states 1.0.1 released on all
platforms. Evidence:

- https://forums.ea.com/blog/ea-sports-fc-game-info-hub-it/ea-sports-fc%E2%84%A2-27-aggiornamento-1-0-1/13734810
- https://forums.ea.com/category/ea-sports-fc-en/blog/ea-sports-fc-game-info-hub-en
- https://forums.ea.com/idea/fc-27-bug-reports-en/custom-controls-are-broken-ps5-%E2%80%93-game-unplayable-during-early-access/13720070

This is independently supported as a **title defect**, not evidence
that Encore globally overwrites in-match actions. Other reports still
described issues after patch 1.0.1. Current game-update version loaded
on the test console is **not established** by `source_sha=2efd8b3c`,
firmware 13.60, title ID, or launcher `own_mapping=0`. Those identify
the emulator/kernel and launcher configuration, **not** guest update
content. Before touching any input mapping, verify the title's active
game update (at least 1.0.1 if available on the guest platform), the
custom preset selected for each player in the pre-match side selector,
and whether it remains active during the match. No save files should
be erased or automatically modified.

## Guest display version witness (development build candidate)

The title's own `IApplicationFunctions::GetDisplayVersion` now has
a **development-profile-only**, once-per-title diagnostic in the
maintained `vendor/encore-active/eden-core/src/core/hle/service/am/service/application_functions.cpp`.
When the guest requests its display version, it emits
`EDEN_GUEST_TITLE_VERSION title=... metadata=... version=...`.
If the guest metadata is missing, the witness reports `unknown`
rather than falsely treating the HLE's synthetic `1.0.0` fallback
as an installed content update.

The original upstream's null-metadata safety behavior is preserved,
and the pinned archive is not modified. This is a **candidate until
native compile and guest run**; absence of the line may mean the title
never called the service, not necessarily that the update is absent.
An installed version at least 1.0.1 is relevant to the publisher's
recognized custom action preset bug, but doesn't establish its
resolution on the guest or remove the need to inspect the preset
selected before the match.

## New native comparison candidate — source qualification (14 October 2026)

An earlier development build (Actions 38499769635) compiled and packaged
successfully and uploaded both the test application and debug symbols. That
build did **not** contain the later guest-version witness, HID lifecycle
source migration, maintained logging/loader sources or the updated package
memory declaration; it is not the final candidate for these changes.

For the next CI candidate, two generated CMake translation units (bounded
logging and 16 KiB-aligned loader) are maintained directly under
`vendor/encore-active/eden-core/src`, and the native package declares
`kernel.flexibleMemorySize=335544320`, matching the primary port's package
metadata. Host source parity and packaging contract tests have been added.
Remaining CMake generation debt: 79 `write_derived`, 89 `file(READ`,
227 `string(REPLACE` occurrences. These are **not closed**.

Current guest control investigation has not yet demonstrated a mapping
defect in Encore's physical controller layer. The guest display-version
witness only emits when the game requests that service; absence of its log
is not proof of an old game update. No game save or title-specific input
preset was edited. A real match and end-of-match progress test is
deferred to the console owner; the native CI is not an FC27 gameplay test.

## Post-replay qualification: contemporaneous progress and buffer witness (14 October)

The two provided rotated heap captures must not be mixed into one continuous
run. In the **long** capture, the last reported media/storage service calls
stay flat for roughly 16 minutes while the most recent ten sampled windows
continue to advance actual GPU draw/dispatch counts and guest IPC/write
counts. This is still a **candidate** application-progression stall: there
is no scene pixel hash, confirmed guest PC of the stalled thread, or IPC
wait ownership stack.

The original offline analyzer compared GPU/guest counters from the first to
last window of the *entire run*. This could falsely call a session active
even if both stopped during the later media plateau. The updated analyzer
now requires an overlapping audio/storage plateau of sufficient duration
and non-regressing actual work counters in its last ten sampled windows.
A synthetic regression keeps compositor frame totals advancing while guest
writes and GPU draws are frozen, and must **not** be classified active.

The shorter capture terminates following an unmapped guest jump from
\`MuseLogicThread_match\`. Neither capture contains
\`EDEN_JIT_SPARSE_OOM\` or \`EDEN_JIT_SPARSE_MAP_FAILED\`. This rules out only
those explicitly logged allocation-failure paths, **not** JIT correctness or
a stale guest call target. Recent source-side fault-PC capture is not present
in the tested \`2efd8b3c\` package.

**Targeted runtime change**: \`BufferPages::Mark\` still performs a release
atomic \`fetch_or\` for every newly seen/partially seen page word, preserving
concurrent registration and the never-clear safety rule, but skips redundant
RMW updates once all required bits were already published. The host contract
adds repeated and overlapping concurrent registration cases. This is an
optimization of unnecessary atomic traffic, **not** a claim that cache-lock
contention, the end-of-match stall, HUD freshness or texture faults are fixed.

Required before another device test: full source preflight, native build and
artifact integrity, then explicit comparison of gameplay progress and long
frame tails; do not use green CI or a 30 FPS average as the gameplay gate.

## Native candidate gate: fatal guest caller provenance and build isolation

A prior native compilation reached 641 of 643 Ninja objects with no compiler
error reported and was cancelled by a newer ordinary source push, not by the
compiler or an observed device failure. The development workflow now separates
build-capable pushes from skipped, unrelated pushes in its concurrency group;
only an explicitly requested new build candidate supersedes an older one.

The fatal guest-prefetch path now records `PC`, `LR`, `SP` and `FP` with
the guest thread identity once, after saving its live context and before
publishing the fatal error. No register sampling or cache flush is added to the
per-frame execution path. The original `2efd8b3c` capture did not contain
these fields, so it cannot be retroactively symbolized with them.

CI gate: the source preflight, native all-on package compilation and artifact
layout must pass on one specific commit. Do not claim a gameplay freeze fix or
user-visible frame-time improvement based only on this source-level validation.

### Concurrent development validation

Both native packaging and core source validation separate intentional
build/test pushes from ordinary no-op UI pushes in their workflow concurrency
groups. Native packages remain pinned to the launching SHA; a newer
explicit full-build request may still supersede an earlier build. This
prevents accidental cancellation of most of a long native compilation while
the single development branch receives unrelated interface edits.
