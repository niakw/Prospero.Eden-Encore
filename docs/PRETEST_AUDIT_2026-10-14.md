# Encore — pre-test source, logs, upstream and package audit

**Audit date:** 14 October 2026. **Working branch:** `dev/ps5-sparse-jit`.
The repository and the already compiled console package must be identified by
**different immutable commit SHAs** if another commit lands after packaging.

## Decision

Do **not** call the outstanding gameplay problems resolved. A native All-On build
from `b5f0301a31cef17f70a8c4e19484d2fb638daa17` (Actions
[38587429272](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38587429272))
passed its packaging and debug-symbol artifacts, but changes to the launcher
and session-log capture landed afterward. That archive is **not** a binary of
the latest development branch.

The source preflight [38587774361](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38587774361)
passed at `4e4a3cd2`; later edits require their own successful validation.
Successful packaging is not an FC27 full-match stability, HUD or mapping test.

## Supplied hardware evidence (build 2efd8b3c)

- `heap.prev(8).log`: 422 five-second graphics windows from one longer
  session. Media/selected storage service-completion counters stop progressing
  in the late tail while draw, dispatch, IPC and CPU-write totals continue to
  advance. This is **suspected application/scene progression stall**, not a
  proven deadlock or a GPU hardware halt.
- `heap(20261014-112903).log`: 207 five-second graphics windows across
  two game starts, **not** one continuous match. Its beginning has already
  lost the one-time application source-SHA marker, though the preceding
  rotated log identifies `2efd8b3c`.
- `stderr(20261014-112909).log` records a fatal unmapped guest jump in
  `MuseLogicThread_match`; its other explicit directory-open messages
  report `errno=2` for an **optional** native OpenGL cache path on return
  to the launcher, not a second fatal crash.
- The files examined contain no NUL or invalid UTF-8 replacement characters.
  This **does not** prove every final write survived a forced application
  closure, nor that a rendered scene was correct.
- `result.tsv` contains stage PASS milestones; this **does not** mean the
  game finished a match successfully.

## Diagnostic completeness and overhead

The native developer package provides opt-in **Detailed Logging**, bounded
`heap`/`stderr` first-and-tail segments, guest services/IPC (including
age of ongoing IPC >500 ms when sampled), cache waits, GPU command
progress, JIT activity, memory ownership, CPU affinity evidence, and
driver/present state. Crash-only reports contain host registers and stack
addresses; a guest invalid-branch error now retains PC/LR/SP/FP, thread
identity and the attempted execution target.

What it **cannot** currently prove automatically during a visually frozen
match: scene-content freshness/pixel hashes, a complete consistent snapshot
of every live guest thread's wait owner/backtrace, which controller preset
the game's own UI stored and selected, or shader-cache **hits** merely from
a cache-directory configuration message.

The current log pipe copies files on worker threads and buffers stdout;
forced termination can lose a small unwritten tail. Long runs retain initial
and latest bounded segments, potentially discarding intervening history.
Detailed profiling itself may introduce measurement overhead. Therefore
**maximum evidence and zero measurement overhead are incompatible**.
Never enable synchronous per-draw stack dumps on the hot path just to claim
“all logs”.

### Collect once, before any further app restart

When Detailed Logging has been enabled in the launcher, retain the complete
diagnostic directory **without renaming or omitting first/previous files**:

- `/data/prosperoeden/logs/heap.log`, `heap.first.log`, `heap.prev.log`,
  `heap.prev.first.log` (only those that exist)
- `stderr.log`, `stderr.first.log`, `stderr.prev.log`,
  `stderr.prev.first.log`, `result.tsv`, `boot-trace*.txt`
- `network-accepted.log` if present; `crash-*.txt` if a native fatal
  signal produced one; `/data/prosperoeden/user/log/eden_log.txt` if present

The new one-line `EDEN_SESSION_SOURCE source_sha=<sha>` identifies the
build at **each** game session (alongside the startup `EDEN_BUILD_SOURCE`).
The offline guest-progress analyzer now segments by session start or reset
of cumulative graphics-frame count, rather than comparing independent
games as one run. It still emits a *candidate*, never an asserted root
cause, when work counters continue and selected service calls remain flat.

Do **not** delete shaders or saves again for this comparison; the previous
test already cleared cache. Record the rough elapsed match time, what was
visible when animation froze, whether the overlay still updated, and whether
the launcher could close the guest normally. A deliberate user close will
not necessarily produce `crash-*.txt`.

## External-source coverage and explicit gaps

Original upstream master (14 October) contains #156 lazy guest-memory
allocation and incremental JIT code commitment. Encore retains its
independently adapted sparse-table/JIT and dense fallbacks; those
upstream APIs and ownership changes are **not a qualified, active port**.
This is important pending memory work, but must not be batch-merged before
a baseline because executable alias ownership, fastmem and page-backings
are native-firmware-sensitive.

Other upstream updates on 14 October include the emulator FPS overlay's
own CPU/GPU information, menu key remapping and new translations. They are
not proof of a guest-generated FC27 HUD or in-match preset fix. They are
tracked, not claimed integrated into Encore's active native image.

The independent native-graphics/Wine fork remains distinct architecture.
The console shader disk-cache credential adaptation and unpresented
swapchain ownership transfer are selectively present in Encore's *active*
Mesa/WSI source; complete scaled-WSI parity and Wine stream-gate changes
are not. Frame interpolation can generate display images but cannot repair
an application deadlock, bad texture contents or in-game controls.
See `INTEGRATION_AUDIT_CPU_GPU_JIT_2026-10-14.md` and
`UPSTREAM_GAP_REGISTER_2026-10-14.md` for source-path references.

## Cleanup and documentation

- GitHub's branches API reported a **single remote branch**,
  `dev/ps5-sparse-jit`, when audited. This is **not** a claim that a local
  Mac checkout has no uncommitted changes or that no retained CI artifact
  exists.
- Marketing READMEs (`README.md`, `README.fr.md`), `SECURITY.md`,
  `MEMORY.md`, `THIRD_PARTY_NOTICES.md` and a populated `LICENSES/`
  are present. Their existence is verified; not every historical statement
  or third-party latest commit is proven current by the presence of the file.
- Native build and source preflight both need to succeed on the **specific
  final source SHA** chosen for the next device trial. Preserve its matching
  app ZIP and debug symbols, so a later guest fault can be symbolized.

**No claim of fully repaired gameplay:** the end-of-match progression stall,
late frames, texture/HUD freshness and guest custom mapping remain open
until a matching hardware run supports a conclusion.
