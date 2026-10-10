# PS5 R238 — October 10, 2026 crash, FC27/BOTW and GPU-memory fault audit

**Source:** user-supplied `crash-20261010-001622*.{txt,log}`, `crash-20261010-002039*.{txt,log}`, `heap(8).log`, `stderr(9).log`, `boot-trace(5).txt`. Firmware `0x13600007`; native **R1 built October 9 22:00:57**. These are *previously built console* results, not acceptance results for later `[skip ci]` developer commits. Analysis inspected all relevant uploaded files without running a build, host test, GitHub Action, or Mac/PS5 modification.

## 1. Two distinct **native launcher SIGSEGVs**

| PS5 local timestamp | Uptime | Thread/context | Fault address | RIP | largest contiguous direct-memory extent | committed heap |
|---|---:|---|---|---|---:|---:|
| 00:16:22 | 19 s | main / launcher | `0x46dfd5b0` | `0x8000a878d` | 11800 MiB | 128 MiB |
| 00:20:39 | 237 s | main / launcher, **after game teardown** | `0x46dfd5b0` | `0x8000a878d` | 4798 MiB | 1280 MiB |

Both crashes share the same code and fault addresses, and are reproduced with vastly different memory headroom. This does **NOT** demonstrate physical OOM. The native RIP is outside the eboot image; absent a verified matching system-library symbol map / binary offset, we cannot name the failing function. `eboot+...` entries shown with '?' are only stack candidates, not decoded frames. Distinguish the native launcher crash from `Job0` guest faults; no evidence supports collapsing them into one cause.

Launcher remains affected by image/upload hitches in the crash snapshots: native `slow frame: draw 134 ms` in crash #1; after returning from game in #2 `draw 690 ms` and `update 485 ms`. `EDEN_UI_HOTSPOT texture_upload` ~33–36 ms. Three ROMs are visible and Nlib cache icons/screens are populated, so "missing FC27" is not reproduced here.

## 2. FC27 guest fault + huge guest/GPU memory mismatch

`crash-20261010-002039-eden_log.txt` has **31,025 `Unmapped Device *Block` entries**: 22,642 ReadBlock and 8,383 WriteBlock. Their first timestamps occur at 28.945 s, up to 213.145 s; repeated hot addresses include `0x502a1f00`, `0x502a2600`, `0x502a1000` and `0x502a1e00`. There are separately about 5,120 `assert memory mapping base yield a nullptr within the table` and 2,122 `assert Mapped memory page without a pointer` messages in `build/headless/memory.cpp`. The latter begin *before* the first automatic retry and cannot be excused solely as later GPU garbage.

First FC27 guest session: `Unmapped Read64 @ 0x0/0x18`, `Cannot execute instruction at unmapped address 0x0` at 12.934 s; `Job0` stack traces through `Engine.Render.Core2.PlatformNvn.nrs`, then `EDEN_GUEST_FAULT_RETRY 1 after 11.2 s`. The exact source currently on dev **already removed the automatic retry** and throws into launcher instead (regression `tools/check-ps5-guest-fault-recovery.py`); do not reintroduce recovery loops or claim the installed R1 binary contains that fix. Later FC27 reaches a guest panic `0x1A80A` and persistent invalid GPU mappings. PRMT Index-mode warnings and Fermi2D z0 software-copy fallbacks appear but no causal link to this specific corruption has been established.

The underlying pinned Eden guest page-table/device-address mapping and GPU memory remap/lifecycle must be audited using this trace, not suppressed as harmless spam. **Do not fabricate GPU memory mapping fixes without symbol/owner evidence.**

## 3. Frame pacing and direct-memory retention (new runs)

`crash-20261010-002039-heap.log`: second FC27 Vulkan session, **32 five-second windows**, ~170.8 s observed, weighted presented **16.77 FPS**, **14 windows below 20 FPS** and **12 below 10 FPS**, lowest **0.342 FPS** / worst inter-present **3033.225 ms**. Approximately 1.28 GiB heap remains physically committed after game teardown (`1342177280` bytes); sparse JIT committed returns to zero.

`heap(8).log`: first Zelda BOTW **Ultra / 2x / 2160p**, 20 five-second windows, **28.36 weighted FPS**, minimum **23.84 FPS**, single worst gap **333.438 ms**. Later FC27 **OpenGL safe launch** hits `guest_fault` roughly 32 seconds after the OpenGL session start, not proof the Vulkan driver alone causes the guest mapping failure. The subsequent FC27 Vulkan session shows ~89.3 seconds/16 windows, weighted **18.56 FPS**, lowest **0.104 FPS** with **9627.471 ms** worst interval. Frame times are presentation statistics, NOT proof of guest simulation step rate.

For the second FC27 session in crash log, initial post-title `core_destroyed`: **1,025,569 live bytes** against 1,073,741,824 committed heap bytes; final `core_destroyed` committed heap **1,342,177,280 bytes**, sparse JIT remaining zero. Returning to launcher does NOT reclaim the heap's physical 128 MiB mspace pieces. Distinguish `largest contiguous free block` from total free PS5 RAM and driver-declared VRAM budgets.

## 4. Verified 13 logical CPU slots, but **CPUID topology decoder rejected**

`EDEN_PS5_CPU_ACCESS hardware_reported=16 affinity_allowed=13 allowed_mask=0x1fff`, followed by `EDEN_PS5_CPU_TOPOLOGY_REJECT more_than_8_physical_ids observed=13`; physical layout cannot actually have 13 distinct cores on a retail 8-core Zen 2 PS5. Native experiment binds primary guest/GPU worker IDs to 0,3,6,9,12 and other threads to secondary `0xdb6` (8 logical slots), but Vulkan shader compilation reported **1 worker**, `reserved=7 physical_verified=0`. The later dev-only verified-logical-secondary fix ([3f254d8a](https://github.com/niakw/Prospero.Eden-Encore/commit/3f254d8a69bbe5d9c988d4124653e899bb18e6fd)) has **NOT** been hardware qualified. More shader workers will not repair invalid GPU mappings or native SIGSEGV.

## 5. Source-only mitigation, not root-cause fix

The pinned common file backend in `headless/backports/eden-ps5-bounded-logging.patch` synchronously called `file->Flush()` on **every Error log**. With >38,000 severe mapping errors/assertions, that can magnify guest/video stalls and SSD load. In this checkpoint, source patch flushes **first Error and every 64th later Error**, always flushes `Critical`, retains all per-event messages, 8 MiB first+rolling log segments, and final explicit Flush() semantics. This does NOT repair the guest page tables; there is no measured FPS gain, and no host/native tests executed.

**Prioritized next engineering steps:** (1) symbolize native `0x8000a878d` against matching PS5 library information / correct ELF build, correlate GL draw and async Nlib lifetime; (2) review pinned guest page table mapping unmap/alias transitions and GPU DeviceMemoryManager owners, preserving unmapped access semantics; (3) verify error storm not dominated by synchronous log flush; (4) PS5 repeat FC27 guest/renderer and BOTW across titles after authorized native build. Continue memory reclaimer ownership work separately; keep issues #7/#8 OPEN. The controller glyph report still explicitly says Nintendo original and `rule=unsupported`.

### 2026-10-10 — Pinned source changes staged since this audit

- Direct pinned Eden `src/core/device_memory_manager.inc` source-level correction committed as `headless/backports/eden-ps5-gpu-memory-mapping.patch`: reset per-page mapping hints on Map/Unmap, verify each physical page before multi-page GPU copies/GetSpan, bypass unprotected cross-thread translation cache on PS5. Actual `ReadBlock` zero-fill and `WriteBlock` skip-on-unmapped behavior stays intact. **Both ReadBlock and Unsafe variants** are covered. Potential cause for missing/wrong textures; not yet measured or certified.
- Every unmapped GPU read/write is counted but only the first 8 and powers of two produce a formatted Error line; 31,025 earlier errors do not need 31,025 console file writes. Commit `baef555a`, with source preflight and telemetry in `1685c98b`. Old cached bounded-logging backport receipts receive a deterministic migration; no reset or destructive local changes.
- New pinned Eden `src/core/memory.cpp` backport `eden-ps5-guest-mapping-diagnostics.patch` samples the previous 5,120 Critical MapPages assertions and 2,122 null-mapped guest access assertions; maintains every failure in counters, logs the mapping's guest address, source target, backing and computed host delta for the first eight and power-of-two events. **These guest-pointer faults are not yet repaired**, because existing R1 console logs omit the backing pointer required to prove their origin. Commit `ab27dbe0`.
- `EDEN_GPU_UNMAPPED_COUNTERS read=... write=... guest_map_zero=... guest_null_mapped=...` is emitted in bounded periodic snapshots, to distinguish fault frequency from I/O amplification and verify what changed after compilation. Both pinned patch hunks have been replay-verified against exact archived source without executing or changing a native target. No hardware test, CI run, build, FPS improvement or fixed black textures claimed.

### Additional performance gate: mapping-walk scale

The first source revision of the PS5 GPU continuity guard walked all pages named by a possibly enormous stale hint, even when a single 16-byte GPU fetch needed only one page. Commit [466831b6](https://github.com/niakw/Prospero.Eden-Encore/commit/466831b686856ddb980481b48aa5ce2dfc186cc0) limits look-ahead to `min(hint, pages-needed-for-current-operation, remaining-table-pages)`. For a single-page operation the scan performs **no** next-page checks, restoring O(1) translation without using unsafe shared `t_slot`. Multi-page operations inspect only pages actually required. This is a source-complexity guarantee, NOT a measured FC27 frame gain.

## 7. Source-root refinement: a *valid* zero-delta guest page pointer (2026-10-10)

In the **pinned** engine `src/core/memory.cpp::MapPages` stores `host_pointer - (guest_page << 12)` in `PageEntryData`. The getter interprets a decoded **zero** as a missing pointer. But a zero can also describe an **identity host/guest VA** whose underlying DeviceMemory backing remains valid. A long contiguous region with that offset can therefore generate thousands of misleading `memory mapping base yield a nullptr` assertions, fail `GetPointerSilent()`, leave GPU `compressed_physical_ptr=0` and ultimately cause wrong/absent textures. This is a source-level explanation **consistent** with the R238 fault cascade; without the original `host_backing/host_delta` in R1 it is not yet proven to be the field root.

[`d075067b`](https://github.com/niakw/Prospero.Eden-Encore/commit/d075067b7992db8a8073e52352daeeaca5128072) adds pinned PS5-only `IsDirectBackingAlias(address, size)`. Only when the entire guest virtual range fits inside the **actual backing allocation**—obtained from `system.DeviceMemory().buffer.BackingBasePointer()` and the same `KSystemControl::Init::GetIntendedMemorySize()` that sizes that allocation—does it treat delta zero as a legitimate direct pointer in `GetPointerImpl` and the `WalkBlock` copy path. Otherwise it keeps the fail-closed zero-fill/write-discard behavior. The separate `guest_alias_mapped` and `guest_alias_access` counters measure recoveries.

[`f051fd1e`](https://github.com/niakw/Prospero.Eden-Encore/commit/f051fd1e69b53e8f5c28da75ec7618cb52aa985f) fixes CPU guest `GetSpan`'s off-by-one end page and checks all pages of a multi-page direct span, with a constant-work single-page fast path. [`12a98cda`](https://github.com/niakw/Prospero.Eden-Encore/commit/12a98cdabfdc52a1597dc06fd8305a66254ce55e) rejects out-of-range GPU block/pointer lookups before indexing the sparse GPU table. [`6f73b82c`](https://github.com/niakw/Prospero.Eden-Encore/commit/6f73b82c86c4536a8da6f0d1024f2cb58f898a9f) resets all counters at each new title before `system.Load`.

**Verification performed:** reconstructed the pinned CPU `memory.cpp` by replaying sequential diagnostics (3 hunks), guest walk (2), zero-alias (5) patches against Eden `5f142c79`; GPU translation (16 hunks) likewise replays against the same pin. New `GetSpan` patch has one additional validated source hunk; native C++ compilation, the source-only Python CI job, game launch, frame measurements and driver tests have **NOT** executed. The heap's retained physical mspaces, shader correctness, player-reported black UI, guest PC=0 boot abort, and native launcher library SIGSEGV remain independent hardware gates. Do not promote this source-derived hypothesis to a solved hardware issue.

## 8. Launcher SIGSEGV symbol provenance — no exact ELF match

The two R1 launcher crashes have identical RIP `0x00000008000a878d`, fault address `0x46dfd5b0`, and source-defined code size `0x231fe50`; they occur at 19 and 237 seconds, including one before loading a title. The symbol ZIP retrieved from GitHub run `37999170813` is **not the exact runtime image**: its ELF `.text` is `0x231f390`, a difference of `0xac0`. Raw stack-word scanner values ending in `?` are not validated returns. Attempts to assign `pe::fill` or `Launcher::draw_game` based on this different ELF were inconclusive; the sampled addresses do not end in CALL instructions at those positions. Do not claim an identified crash function or patch unrelated title strings.

`tools/symbolize-crash.py` now fails closed on code-size mismatch instead of merely warning before printing wrong symbols. Host crash-report check adds a mismatch rejection test. The earlier original R1 build run `37996073674` contains the all-on image but no unstripped ELF symbols archive. The exact source of this native crash remains OPEN; it needs exact matching symbols (or a fresh expressly authorized build + reproduction). No new PS5 build launched.

## 8. 2026-10-10 final source safety pass before next authorized native build

The previously-observed R1 guest/texture faults and FC27 frame collapses are **not** declared fixed. This review found three additional correctness issues in the pinned Eden engine:

1. **Sparse table boundary:** upstream `SparseLargeVector` accepted `index == count` in three range guards. The PS5 CMake-derived sparse header now replaces all three `>` checks with `>=` and enforces the expected patch count. [5be473e5](https://github.com/niakw/Prospero.Eden-Encore/commit/5be473e55c9c03a52c99167b582f51f088ab94ed).
2. **Undersized GPU physical reverse-map:** upstream `DeviceMemoryManager` allocates 4-GiB page count for Memory_4Gb and 8-GiB count for everything else, but `GetIntendedMemorySize` permits 4, 6, 8, 10 and 12 GiB. The patched **PS5-only** sparse table now reserves the true guest-DRAM physical index count, checks mapped host pointers against this range, rejects reverse physical lookups outside it, and checks typed access before returning a host pointer. This corrects the 10/12-GiB indexing contract **without eagerly committing the extra sparse slots**. [c8ababa3](https://github.com/niakw/Prospero.Eden-Encore/commit/c8ababa365bfd13cd3dbbaf8da835710e8ac1723).
3. **GPU cache stale after direct remap:** pinned `Unmap` calls `device_inter->InvalidateRegion`, but `Map` used to replace an already mapped physical page without invalidating the renderer's cached texture/buffer region. When old and new physical pages differ, the PS5 patch now invalidates once *after* releasing `mapping_guard`; initial map/same physical mapping incurs no new cache flush. [d08a837c](https://github.com/niakw/Prospero.Eden-Encore/commit/d08a837cedee767bc493df7ad9c5a89800b657a0).

Sampled failure telemetry adds `bad_physical` and `remap_cache_evictions`, with exact per-title counters. The seven ordered GPU patches replayed on pinned Eden `5f142c79`, **32 valid hunks** total. A source validation is not compilation: **no PS5 build, host source test execution, CI run or game FPS measurements** has taken place for this revision.

Heap lifetime: `eden_heap_release_current_tcache()` and its host regression checks already existed in this branch. It drains only already-freed small blocks from the surviving owner's private cache; it cannot release the observed ≈1.25-GiB physical pieces of Sony mspaces without per-piece ownership and quiescence proof. Native launcher SIGSEGV symbol attribution remains open. Keep issue #8 open until a console run with fresh logs confirms the texture, 0-FPS, and lifetime outcomes.

## 9. Host regressions green; FC27 physical heap retention measured (2026-10-10)

The actual R238 FC27 crash heap trace reports, after guest core destruction (phase=core_destroyed): Sony heap physically committed pieces **1,342,177,280 bytes = 1,280 MiB**; live requested allocator bytes **3,655,646 bytes = 3.49 MiB**; tracked blocks **186,450**; thread-local freed-block caches **1,050,495 bytes** before title-boundary drain; JIT sparse reserved/committed **0/0** and JIT dense owned **0**. Physically retained mspace memory is **367 times** accounted live bytes. This is a *fragmentation/ownership* problem, not proof the game has a 1.25 GiB live leak. Remaining mspace metadata, many very small live blocks and long-lived launcher/arena allocations prevent treating 1,280 MiB as instantly reclaimable. Reclamation requires per-piece ownership and a validated empty space before unmapping Sony direct memory; never release whole backing based on global bytes alone.

Latest fixes: [8926d4e8](https://github.com/niakw/Prospero.Eden-Encore/commit/8926d4e8236cbc356991d2635b62fe3b9fd765ce) physically zeroes retired sparse host pages even if another host page retains a 2 MiB slot; [0627ebe2](https://github.com/niakw/Prospero.Eden-Encore/commit/0627ebe2a29f082572c0d5605f9b7f1ac0bb871f) bounds inline CPU-to-GPU inverse lookups; [20aa520c](https://github.com/niakw/Prospero.Eden-Encore/commit/20aa520cb5396beffc611549cf8efe5abb1a5e83) guards an empty reverse-mapping head. All **47** GPU manager, GPU header and core guest-memory patch hunks replayed sequentially against pinned Eden 5f142c79.

**Host validation GREEN:** [core preflight #38032224808](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38032224808). Tests included the host-compiled actual derived sparse page method, JIT source/memory checks, approved launcher UX invariants and clean diff. Native PS5 emulator build and release jobs skipped by design. No hardware evidence yet establishes correct FC27 texture rendering, no 0-FPS dips, native launcher SIGSEGV resolution or full in-game PlayStation glyph replacement.


## 10. R239 — Sony mspace root-ownership ledger (2026-10-10, source-only)

The `1,280 MiB physically committed / 3.49 MiB logically live` sample does **not** establish that any individual 128-MiB piece is releasable. In `headless/heap_arenas.inc`, 8-MiB child mspaces are allocated from the parent Sony heap pieces and remain registered in `eden_heap_arena_list`, including after worker TLS exit; a child arena can therefore pin its parent even without game-visible live blocks. Furthermore, a growth mspace can cover multiple consecutive pieces, so the correct reclamation unit is a **root mspace**, not an arbitrary 128-MiB page.

New work, `fec15ed4` → `6bb8f4bd`:
- Per-root piece range and exact Sony direct physical-owner provenance are recorded on initial commit and on successful growth publication. Host anonymous/dense fallback records have no direct physical owner.
- Each root reports *physically still held application blocks/usable bytes* and the number of child arenas pinning it. Unlike existing logical live statistics, blocks temporarily retained by a thread's free-list stay counted until their original owner's tcache drain or destructor actually returns them to the Sony mspace.
- Deltas are batched in the **existing thread-local 64-operation counter flush** rather than issuing extra contended atomic writes for each `malloc/free`. Realloc within the same mspace accounts for usable-size changes; moves between root/large mappings debit the old root and credit the new root; failed allocations do not credit anything.
- After `core_destroyed`, the surviving runner thread drains its tcache and emits `EDEN_HEAP_ROOT phase=core_destroyed root=... pieces=... held_bytes=... held_blocks=... arena_pins=... physical_owner=... reclaim=disabled`. This is observational and can lag for other still-active/non-joined allocator clients.
- `tools/check-heap-growth.py` now includes host assertions that the root ledger balances to zero after all application blocks and thread caches are freed, **while the permanent arena pins remain**. The existing growth/rollback tests stay present.

**Critical limitation:** no published mspace has been destroyed or unmapped. Current root counts are not an exact quiescence certificate: other threads may still have unflushed deltas or enter mspace operations. A physical reclaimer needs an audited owner-by-owner shutdown/retirement protocol (including child arena destruction, hot-path exclusion and exact PA/VA release), and independent PS5 validation of any relevant Sony mspace destruction primitive. No host C/C++ test, Actions job, native build or console retest was executed for R239 in this revision. The earlier host-green #38032224808 applies to prior code only.

The root ledger is diagnostic evidence to select a safe next step, **not** proof the 1,280 MiB has been reclaimed; FC27 0-FPS/texture faults and the native launcher SIGSEGV remain open.

**R239 supplemental source controls:** `a1960d72` avoids a second TLS lookup for the normal uncached allocator path. `65c8e6f6` adds a cache-to-mspace delta conservation check. `a7eb94be` adds a new host `root-span` scenario (192-MiB request, 256-MiB root mspace across two pieces) to prove that physical accounting and PA ownership attach to the root, not to an arbitrary 128-MiB slice. All remain unexecuted until the authorized host/native validation window. No automatic reclaim, no measured FPS gain and no claims about native `SIGSEGV` fixes.


### R240 source hardening after R239 ledger

- `a0d9a766` / `a6744281`: `root_span` and `root_direct_owner` are atomic and the root span's release publication follows initialization of every piece owner and the root mspace slot; this removes a race between a title diagnostic and heap growth. The ownership counters remain relaxed/batched and must **never** be used to unmap from an unsynchronized read.
- `5d222a7c`: dirty-root bitmask limits 64-operation TLS flush work to the roots actually touched, rather than iterating all 24 possible Sony pieces. No additional per-frame allocation or mspace lookup.
- `886f8e82`: on title-boundary launcher TLS cache drain, reset small-mspace hint to root 0 to let the next title reuse lower existing mspaces before an additional piece is committed. This does **not** reduce already committed physical memory or guarantee fewer hitches.
- `33765f9a`: host-only core preflight now runs `tools/check-heap-growth.py` with UBSan/TSan and `tools/check-heap-growth-rollback-host.py` with clang-18. Prior green #38032224808 did **not** run these new tests. These checks are wired but not executed on the changed HEAD; the native PS5 workflow remains separately gated.

**Remaining prerequisite to safely return 128-MiB pieces:** firmware-supported `sceLibcMspaceDestroy` / `IsHeapEmpty` behavior must be proven with matching PS5 symbols, all block/cache/child-arena owners retired with an allocator-entry exclusion protocol, and the exact root's VA unmapped before its direct physical allocation is freed. Neither source-only instrumentation nor host sanitizer success would by itself establish that these conditions hold on a real PS5. No successful FPS/texture/launcher-crash outcome is claimed.


### R241 — bounded post-console log triage and moved realloc fast path

- `a21a557b` parses `EDEN_HEAP_ROOT` in the existing read-only log analyzer. Each bounded entry distinguishes roots pinned by child arenas, those retaining physical mspace blocks, dense/unknown PA ownership, and roots that merely **report** zero occupancy but lack a quiescence/SDK-empty proof. All report `reclaim=disabled`; the analyzer does not add or merge potentially overlapping session metrics.
- `978fd1d8` extends the synthetic analyzer test with three root categories and an out-of-range root rejection; inherited preflight `tools/check-ps5-log-analysis.py` will run it in the next host-only gate.
- `b6bf92ac` reuses a single resolved TLS record for both the new and old root accounting on a moved `realloc`; a failed TLS slot claim does not run registration a second time. `eden_heap_physical_note` no longer silently re-registers its own TLS context.
- Static source-only checks of the hooked code paths are consistent; **no host compiler/UBSan/TSan, new GitHub Action, Sony API invocation, game boot or FPS test has run for these revisions**.

Still open: root lifetimes/safe destruction on PS5 firmware 13.60, 1,280-MiB physical heap retention, FC27 native SIGSEGV/guest GPU mapping/black textures and severe frame collapse. No direct-memory release is enabled.


### R242 — root cause of continued 128-MiB heap growth, not a reclamation claim

A zero (or negative) relaxed root counter from a multithreaded title is **not** proof that its Sony mspace is empty or safe to destroy. R242 makes the next console trace explain **which requested allocation caused each new root** instead of relying on the global 1,280-MiB/3.49-MiB disparity.

- `d361d4f4` / `607be568`: always restore the main mspace allocation hint to zero on game teardown, even if the surviving launcher thread has no TLS record; synthetic host test detaches/restores TLS to exercise this.
- `ca184df4` / `d02862f7`: when root telemetry has negative or mismatched blocks/bytes, log triage identifies `inconsistent_or_transient_ledger` rather than an ostensibly reclaimable empty root.
- `9deda89b` / `cdce218c`: a bounded `EDEN_HEAP_GROW req_bytes=... root=... pieces=... spaces=... committed_mib=...` kernel record is emitted only after successful growth; it reports admission pressure *not* PS5 GPU VRAM totals. Standard malloc paths and every presented frame are unaffected.
- `67f0ee1a` / `682bc8e0`: read-only log triage + synthetic fixture correlate each new mspace with its originating request and enforce the 3-GiB range/contiguous piece publication.
- `05e67adc` / `2a9f001b`: host mock parses every emitted growth record to verify root/span and committed MiB, including the two-piece 192-MiB allocation test.
- `4360ecab`: print a `post_cache_drain` allocator snapshot alongside `core_destroyed` root data, to show whether the surviving TLS cache produced a logical-accounting change after destruction.

**Still NOT performed:** executable host UBSan/TSan run, GitHub Actions, native PS5 build, game/renderer tests, physical mspace release. Physical reclamation requires exact empty-space proof, owner quiescence, child arena retirement and a PS5 FW13.60-qualified destroy/import/unmap path. The PS4-mspace destruction pattern is informative but not native PS5 validation. Keep issue #8 open.


### R243 — keep blocking kernel-log formatting outside allocator serialization

Heap growth used `snprintf` and `sceKernelDebugOutText` while holding the allocator's `eden_heap_grow_lock`. The allocator can grow during a frame, so libc formatter initialization or slow kernel logging could unnecessarily serialize other allocation clients. `9285d934` encodes unsigned integers using a bounded stack-only encoder (no libc formatting); `d2e7f5de` fails closed on zero-capacity/invalid cursors. `fea4f460` captures the exact request, root and committed extent under the growth lock, unlocks, then emits the debug record. Concurrent growth records may arrive out of order; each record's captured fields remain correctly tied to its root. `9eb97196` adds a source-contract regression enforcing unlock-before-log, and the exact-source-extraction host fixture `tools/check-heap-growth-diagnostics-host.py` (`34a654f9`, `1e4ec3f1`) is wired into both host gates (`a34c1655`/`0f7aed15`). An **isolated local C reproduction** (not a repo checkout or CI Actions job) passed UBSan and ASan+UBSan checks for normal/malformed buffer cases; native SDK and full allocator thread execution remain untested.

A public PS4 symbol listing documents `sceLibcMspaceDestroy` and `sceLibcMspaceIsHeapEmpty` (https://www.psdevwiki.com/ps4/LibSceLibcInternal). A separately published PS5 native SDK notes that imported libc functions depend on each title's library/import catalog and firmware-compatible `libc.prx` (https://github.com/Rufidj/ps5link-sdk). **Neither source qualifies the exact destroy/empty ABI on FW 13.60.** No mspace is removed/unmapped and no GPU/FC27 FPS gain is claimed. Before enabling a reclaimer: native ABI verification, proof no guest or launcher allocations (including retained per-thread caches), child arena retirement, concurrent allocator exclusion, and strict unmap-then-release ordering.
