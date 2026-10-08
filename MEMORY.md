# Eden Encore — Project Memory

> Continuity file for work on `niakw/Prospero.Eden-Encore`.
> Read this file before changing architecture, UX, build/release behaviour or performance policy.
> Keep it concise but authoritative. Update it whenever a project-level decision changes.

## Repository / branch

- Repository: `niakw/Prospero.Eden-Encore`
- Remote release line: `fix/0.40-zbic-13.60`; active **local audit** branch: `local/no-build-polish` (HEAD `149df7a`).
- PS5 title ID: `PPSA99008`
- Current release line: Encore R1 / package `01.000.041`
- Active Mac worktree: `/Users/admin/Downloads/Prospero.Eden-Encore-work` (the former `...-legal-pass` path is no longer present).
- Do not trigger a new CI run until the current local pass has been fully reviewed and all intended changes are covered by gates.

## Working rules

- Execution-first: fix the repo, do not only describe changes.
- Do not restart a long native build unnecessarily.
- Do not claim a true Ninja resume unless the restored tree really preserves dependency timestamps/state.
- Before a push that triggers CI, inspect the full local diff, run all relevant gates, and scan for release `-Werror` issues such as dead constants/functions.
- One coherent pass is preferred to repeated 30+ minute red builds.
- Keep `main`/shipping branches clean; no automatic Brain-style proposal PR behaviour applies here.
- Never silently change a user-visible profile name or established UX contract.


## Latest CI history

- #180 — run `37615269357` — GREEN and last hardware-bootable reference before the #182 regression.
- #181 — run `37631564579` — RED near the end of native compilation (~1591/1601).
  - Failure: `hero_cover` became unused after the new hero design and release uses `-Werror`.
  - Fixed in the following release pass.
- #182 — run `37660484879` — CI GREEN on `200db3485e85a14234e21973933865cf6f042ae4`, but HARDWARE BROKEN.
  - PS5 FW 13.60 crash before the launcher/KStuff pause:
    - `0xa002030a`
    - `SYSTEM_ILLEGAL_FUNCTION_CALL`
    - thread `eboot.bin`
  - Reinstall + console reboot did not help.
  - Root cause isolated with high confidence to the new startup `statfs("/user")` path in `Ps5ConsoleStorage()`.
- #183 — run `37669275608` — FAILED EARLY before compilation on hotfix commit `97e92f01396545ecff8f7f4a55154dfa9894844f`.
  - The actual startup/filesystem/storage/legacy/video gates all passed.
  - `check-encore-ux.py` then false-positive failed because it searched the literal text `statfs(` in comments as well as executable code.
  - No native compile started; the run did **not** waste another full build.
  - The full ~2.86 GB cache from #182 restored successfully from key `...-37660484879`.
  - Local fix strips C/C++ comments before asserting that executable `eden_services.cpp` contains no direct `statfs/statvfs` calls.
  - The underlying boot hotfix remains unchanged: direct PS5 `statfs/statvfs` was removed and the previously boot-proven `std::filesystem::space(Eden::AssetsDir(), error)` path restored.
- CI-green is not sufficient for startup-sensitive PS5 changes: a hardware boot on FW 13.60 is a mandatory release gate.

- #184 — run `37670172143` — FAILED EARLY before compilation on `f5d2015337eb5fd7fbf3895133926f9819120f58`.
  - Metadata preflight passed.
  - License/SFX gate rejected the historical continuity file because it contained the literal name of the removed audio service.
  - This was documentary only; no package/audio regression and no native compile started.
  - The #182 ~2.86 GB cache restored successfully again.

## Build / cache policy

The old workflow restored caches but still appeared to rebuild from 1/N because:
- `tools/build-headless-native.sh` touched every fork-owned launcher source on every run.
- Git checkout mtimes make restored Ninja trees look stale.
- GitHub Actions rejects cache paths containing `../...`.

Local WIP replaces the global `touch` with a content-hash + mtime manifest:
- unchanged tracked headless sources recover their cached mtime;
- changed sources keep their fresh mtime;
- Ninja decides incrementally as intended.

Current local cache fix:
- all invalid `../...` entries are removed from `actions/cache`;
- the five heavy sibling repositories live physically under cacheable `.deps/repos/`;
- `tools/ci/link-sibling-deps.sh` recreates the historical `../repo-name` paths as symlinks for existing scripts;
- the native build replaces the old global source `touch` with a content-hash/mtime manifest so unchanged fork files retain cached timestamps;
- staged-app resume remains available when a staged app artifact exists.

The first run after introducing the mtime manifest cannot recover timestamps from a manifest that did not exist yet, but the expensive sibling repository/build outputs are immediately cacheable through `.deps`.

## Release / FTP

Canonical release keeps legal material:
- full ZIP
- FFPFSC
- `LICENSES/`
- `legal/`

A separate manual FTP archive is generated:
- `Prospero.Eden-Encore-R1-FTP.zip`
- contains runtime `PPSA99008/` only
- omits installed `legal/` and ShadowMount-only `ui/lang/*.txt`
- canonical `.po` catalogs remain
- FileZilla should use Binary transfer mode because the PS5 FTP server rejects ASCII `STOR`.

## Launcher UX direction

Target: clean modern console UI, inspired by a hypothetical next-generation console shell without branding it as Switch.

### Top navigation

Global top tabs:
1. Home
2. Library
3. Recently played
4. Settings

Expected navigation:
- from Library / Settings, Up can focus the top navigation;
- Left/Right moves between top tabs;
- Down or Circle returns to screen content;
- Cross opens the selected tab.
- Do not require Circle just to move back into the global menu when arrows should naturally work.

### Home quick settings

Important distinction:
- Cross to **enter** Quick Settings is intentional and should remain.
- While only highlighting the Quick Settings tile (not entered), Left must return to the neighbouring hero actions.
- Do not make the highlighted Quick Settings tile a horizontal navigation trap.

### Hero

The current shipped/green design was not acceptable:
- old square game cover looked like a legacy icon pasted into the hero;
- a dark rectangular plate was visually obvious.

Desired hero:
- real 16:9 banner first;
- gameplay screenshot fallback second;
- **never promote the square ROM icon to the large TV hero**;
- if no rich media exists, keep the shared backdrop + soft readability gradient rather than a giant cover block;
- text overlays the hero with a natural fade, not a dark card rectangle.

Media fallback order:
`Nlib banner -> Nlib gameplay screenshot -> neutral/shared backdrop`.

## Nlib media

Observed on PS5 logs before the local fix:
- `icon=0 hero=0 screens=0 players=0` for Zelda, FC27 and another title.
- Nlib itself is healthy from the Mac.
- Cloudflare returns 403 to an anonymous/default client but succeeds with an explicit User-Agent.
- PS5 homebrew also has no normal Unix CA store.

Current local network solution:
- explicit `User-Agent: Prospero.Eden-Encore/1`;
- `Accept: */*`;
- keep TLS certificate verification enabled;
- enable Eden's existing `YUZU_BUNDLED_OPENSSL` path on PS5;
- reconstruct Eden's own complete pinned OpenSSL CA bundle from
  `.patch/openssl/0001-add-bundled-cert.patch` into the native OpenSSL include tree.
- local materializer test produced 147 CA certificates from the exact pinned Eden patch.

Do not replace this with a service-specific certificate or disable TLS verification.


## Storage

The original UX problem remains: `std::filesystem::space(Eden::AssetsDir())` may expose only the selected Encore filesystem view (for example ~64 GB), so it must **not** be labelled as the physical PS5 SSD.

The attempted replacement in #182 was not safe:
- `Ps5ConsoleStorage()` called libc `statfs("/user")`, then `/system_data` and `/system_ex`;
- `Launcher::Launcher() -> read_home() -> services_.diagnostics()` executes this synchronously before the first UI frame;
- on real FW 13.60 hardware, #182 immediately crashed with `0xa002030a SYSTEM_ILLEGAL_FUNCTION_CALL`.

Current safety rule:
- do **not** call direct libc `statfs` / `statvfs` on the startup path unless independently proven on FW 13.60 hardware;
- hotfix #183 deliberately falls back to the already boot-proven `std::filesystem::space(Eden::AssetsDir(), error)`;
- UI wording must describe this as the selected/storage-root capacity, not as the physical console SSD;
- if real console-wide capacity is reintroduced later, use a PS5-specific API/path that has been isolated and hardware-proven first;
- keep **used / total** consistent with a used-capacity bar and keep free space available in Diagnostics.

## Video profiles

User-facing profiles:
1. Minimum
2. Recommended
3. High
4. Ultra
5. Custom (derived, not authored)

Profiles are title-aware through the generated Encore overrides database.
Manual edits produce Custom.

Current generated FC27 title ID:
- `0100C49025D3E000`

Important:
- a Custom profile must not silently force a heavy hidden runtime policy.
- Runtime policy should be derived from the effective settings/tier when Custom.

## Performance settings — automatic policy

ProsperoEden master exposes seven real runtime performance switches:
- `block_list` — compile ahead
- `async_shaders`
- `fast_gpu`
- `unsafe_cpu`
- `unsafe_dma`
- `reactive_flushing`
- `skip_invalidation`

Encore must account for all seven.

### Critical rule

**There is no manual “validated game” requirement.**
There are far too many games. The system must work generically.

Use:
- authored tier/profile;
- effective video/runtime cost;
- runtime telemetry/history when safe and available;
- optional title-specific database exceptions as hints, not as a prerequisite.

A game without a special database entry must still receive a complete automatic performance policy.

### Safety philosophy

The profile system owns complexity; the normal user should not need to understand seven emulator internals.

Suggested generic policy direction:
- Recommended: conservative stability-first defaults, with low-risk stutter improvements where supported.
- Minimum: favour speed more aggressively.
- High / Ultra: favour correctness/image quality over risky speed hacks.
- Custom: derive an appropriate runtime tier from effective settings rather than becoming implicitly “High”.

Riskier flags must have a generic policy; do not require hand-testing every title.

Current generic hidden policy:
- Minimum: async shaders ON, fast GPU ON; unsafe CPU/DMA OFF; reactive flushing ON; skip invalidation OFF.
- Recommended: async shaders ON, fast GPU OFF; unsafe CPU/DMA OFF; reactive flushing ON; skip invalidation OFF.
- High: async shaders OFF, fast GPU OFF; unsafe CPU/DMA OFF; reactive flushing ON; skip invalidation OFF.
- Ultra: async shaders OFF, fast GPU OFF; unsafe CPU/DMA OFF; reactive flushing ON; skip invalidation OFF.
- Compile ahead is owned by the policy but remains OFF in shipping because the current shipping architecture does not compile the shared-JIT path it requires.
- Safe Launch uses the conservative Recommended hidden policy even though it lowers visible render cost.

### Compile ahead / FC27

FC27 previously showed JIT pressure with saved-block compile-ahead:
- saved block list occupied a large part of JIT regions at boot;
- `EDEN_JIT_PRESSURE` and long stalls followed.

Current Encore shipping policy had therefore forced compile-ahead off.
Do not re-enable it blindly.

If compile-ahead becomes automatic, use a generic adaptive rule based on saved-list/JIT pressure/history and disable it automatically when pressure thresholds are exceeded. No manual title validation.

## FC27 performance / freezes

Observed on PS5:
- FPS presentation can remain at exactly ~30 while the visible game is frozen.
- Vulkan continues submitting/presenting.
- no clear RADV crash;
- no demonstrated OOM for the latest freeze;
- guest cores spend substantial time in synchronization/IPC waits such as:
  - `WaitProcessWideKeyAtomic (0x1C)`
  - `SendSyncRequest (0x21)`
  - `SleepThread (0x0B)`

Conclusion:
- large FC27 freeze is **not fixed yet**;
- do not claim it is fixed by graphics-profile tuning;
- low-cost Custom runtime policy can reduce stutters but is a separate issue.

Do not add an automatic game-kill/restart on the current signal alone: a legitimate paused/loading game could look similar.
Need a stronger progress signal before recovery logic.

## FC27 PlayStation glyphs

Current state:
- physical DualSense mapping can be PlayStation-style and function correctly;
- the Switch build of FC27 still renders Switch A/B/X/Y graphics.

Reason:
- the guest sees an emulated Switch Npad/Pro Controller;
- the button images are game UI assets, not generated by the host controller mapping.

Therefore:
- mapping alone cannot turn A/B/X/Y art into Cross/Circle/Square/Triangle;
- a true fix needs a game/UI texture replacement or patch path.
- Do not claim controller-type remapping alone solves visual glyphs.

## Controller profiles

Desired global modes:
- PlayStation (default)
- Switch
- Custom PS5
- Custom Switch

PlayStation mode:
- native-feeling DualSense semantics;
- visual launcher glyphs are PlayStation;
- game-internal glyph replacement is separate.

Keep support for game-requested controller/grip semantics without changing how the user physically holds the DualSense.
Local WIP includes horizontal single-Joy-Con logical rotation tests; review before next push.


## PS5 system overlay artwork

Observed on the #182 package:
- Encore's icon/logo is visible in the normal PS5 app/library list;
- the PlayStation system overlay for the running application does **not** show the expected Encore logo.

Treat this as a separate package/presentation issue from the boot crash.
Investigate `sce_sys` / package metadata and overlay-specific artwork requirements only after the eboot is hardware-bootable again.
Do not mix an unproven artwork/package experiment into a startup hotfix.

## Legal / SFX

Release has been hardened:
- original deterministic procedural launcher SFX, no external generated-audio service dependency;
- legal bundle / third-party notices included;
- exact license gate exists;
- do not claim absolute legal certainty; say materially hardened / notices bundled.


## Current local / remote state after #182

- Local Mac repo: `/Users/admin/Downloads/Prospero.Eden-Encore-legal-pass`.
- Local branch and GitHub branch are both at hotfix commit `97e92f01396545ecff8f7f4a55154dfa9894844f`.
- The pre-#182 WIP set (cache layout, bundled CA, performance policy, hero cleanup, CI gates, etc.) is already part of the pushed history; it is no longer hidden local WIP.
- Local working tree is clean except this richer `MEMORY.md` continuity file while #183 is running.
- #182 saved ~2.86 GB of compatible GitHub Actions cache data after staging. #183 is expected to restore that cache through the workflow prefix restore key rather than intentionally starting from a clean native tree.
- Do not create extra pushes while #183 is running unless a new defect is certain; the workflow concurrency policy can cancel useful work.

Deliberately excluded from this release lot:
- experimental horizontal single-Joy-Con rotation;
- connected-controller count as a fake fallback for a game's maximum player count.

## Gates before the next CI run

At minimum:
- `git diff --check`
- launcher/string catalogs check
- language runtime contract
- video preset contract
- Encore UX/media/profile contract
- JIT stability contract
- performance-policy contract covering all seven master settings
- controller/device checks
- storage/startup/filesystem contracts
- legal/license/SFX gate
- release metadata gate
- shell syntax for modified build/backport scripts
- scan modified C/C++ files for unused local constants/functions likely to fail under `-Werror`
- validate every patch applies to the pinned upstream commit

Only then push and allow CI to run.

For startup/runtime-affecting changes, add one more release gate after CI: **boot the produced artifact on real PS5 FW 13.60 and reach the launcher** before calling the release validated.


## 2026-10-08 Eden Encore post-#186 no-build audit checkpoint

User requirement: **NO application build, no GitHub push, no CI dispatch until explicit user OK**. Current shipping PS5 build is #186 at HEAD 149df7a (it boots, FC27 still stalls/freezes, Home/overlay metadata defects remain). Local work only on `local/no-build-polish` at `/Users/admin/Downloads/Prospero.Eden-Encore-work`.

Changes prepared locally but **not compiled into a PS5 binary or hardware-tested**:
- Home rebuilt to follow the approved wide-cinematic TV mockup with violet/rose branding, full-width banner, recently played rail, four utility cards, quick settings as overlay, corrected per-game player capacity vs connected DualSense count, opaque neutral fallback when Nlib has no game art, and no invented console-wide SSD capacity. Cached game list is local and Nlib fetch is targeted; per-title cache writes serialized.
- Native host networking: explicit `sceNetInit`, a sceNetResolver-based IPv4 `getaddrinfo` and friends (SDK imports can point to unloaded libScePosixForWebKit), dropped Mihawk RADV DNS EAI_FAIL stubs, socket `fcntl` wrapper using PS5 SO_NBIO, bundled CA + TLS verification intact, observable HTTP errors. Ref: ps5-native-app-boilerplate console_curl.c and docs/CURL.md. FC27 Nlib Mac returns 16:9 banner, 5 screenshots, 4 players; PS5 #186 returns zero media. PS5 network fix is unproven pending next hardware test.
- Log policy: global detailed Debug disabled for normal release; circular Eden logs bounded at 8 MiB segments; stderr/heap rotated to 8 MiB and previous-session files pruned. User explicitly requests max size and automatic cleanup.
- Release Dynarmic entry/exit CPU sampling and release watchdog removed from hot path; diagnostic mode retains probes. Test `check-performance.py` now expects 0 release SampleCpu calls, but its generated cached source predates this change and cannot be validated until user authorizes regeneration/build.
- Worker topology probe forces a scheduling point before x2APIC, resets old state, supports fallback and verified pinning. FC27 #186 logs `ready=0 distinct_cores=1`, all workers allowed on 13 CPUs; correction hardware unproven.
- Candidate HLE patches: dummy host-thread queue safety, ServiceManager host-wait / lazy audio initialization matched to Citron commits (f07609c..., c5b716..., 21813e8...), Dynarmic cross-core I-cache invalidation. All patches dry-run on exact pinned Eden; causal tie to FC27 soft-freeze unproven. Requalify separately in hardware A/B.
- Logo overlay: current /user/appmeta/PPSA99008 has icon0.png but not icon0.dds, while PS5 installed apps have icon0.dds size 262292. Local icon0.dds matches size and DDS header of observed asset. This is stronger evidence, not a guaranteed overlay fix.
- FC27 #186 actual hardware: Minimum/Vulkan/1080p/0.75x/FSR/AA off; significant 1.38s frame gap, median ~30 FPS, guest cores wait in SleepThread/WaitProcessWideKeyAtomic/IPC while Vulkan presents; raw RADV submit costs relatively small, so suspect CPU/HLE scheduling path; no demonstrated definitive root cause, GPU not ruled out. 30->60 via frame-gen should be separate later; Eden LSFG code depends on proprietary Lossless.dll shaders and is not redistributable as-is.
- RADV/Mesa pinned commit 0b2d6d... has same tree hash as later 504adad...: major shader cache/threaded recording gains already present, cannot promise performance from updating pin. OpenGL remains A/B alternative.

Local static contracts confirmed PASS: check-network-runtime, check-home-media, check-bounded-logs, check-release-hotpath, check-sm-host-wait, check-dummy-thread-waits, check-dynarmic-icache, check-exclusive-monitor (200k contention), check-worker-topology, check-worker-affinity (native C++ sanitizer harness with SDKROOT=MacOSX26.5.sdk), check-gpu-producer-stop (same SDKROOT), check-performance-policy, check-video-presets, check-encore-ux, check-startup-contract, check-licenses (64/20), check-release-metadata, git diff --check, bash -n all modified shell scripts. Four new backports apply to pinned Eden in patch --dry-run.

Broad 45-script sweep produced 11 failures: some require unavailable clang++-18 / llvm-nm-18 on Mac, two standalone data analyzers require input paths, one GPU producer harness needed SDKROOT=MacOSX26.5.sdk (subsequently PASS), check-game-capture-shutdown.py was obsolete and updated (PASS), and check-performance.py references stale generated code from #186 so cannot pass until regeneration; it now expects no release instrumentation. Distinguish tooling/unrun gates from actual source failures. Do not claim all 45 tests PASS.

Remaining before asking approval for **one** incremental CI build: finish code review of all WIP C/C++ and overlay packaging, restore reliable test coverage without masking true errors, run all feasible non-app-build gates, verify no unintentional branch/commit/push, consolidate release-vs-experimental fixes (keep inline exclusives and RADV threaded recording OFF initially), give honest final audit with unverified items and exact hardware test matrix. A GREEN CI build will still not be called PS5 validated until user boots it on firmware 13.60 and tests Nlib/artwork + FC27 long soak.


### 2026-10-08 follow-on static integration review (no application build)

- Mac connection transiently timed out, recovered. Repo remains `local/no-build-polish`, HEAD `149df7a`; no commits pushed, workflows triggered or app builds run.
- Found a real compiler error in `headless/ps5_net_compat.c`: `getnameinfo()` used `size_t` for the output lengths where the platform headers declare `socklen_t`. Corrected signature. Local `clang -std=c11 -Wall -Wextra -Werror -fsyntax-only` now PASS with SDKROOT MacOSX26.5.
- Added host-only C sanitizer harness `tools/check-ps5-net-unit.py` exercising the actual compatibility implementation with mocked `sceNetResolver`: IPv4 DNS, numeric addresses, service port, invalid/unsupported names, cleanup and `SO_NBIO` F_SETFL/F_GETFL via wrapped fcntl. AddressSanitizer/UBSan PASS. This is NOT proof of PS5 internet connectivity or TLS handshake.
- Fixed known `fcntl` varargs UB for F_SETFL/F_SETFD by reading the promoted `int` argument, instead of `intptr_t`.
- Native PS5 linking invokes `tools/link-headless-native.sh` in two passes. Added explicit `--wrap=fcntl` there rather than trusting the CMake link flag alone. Contract `tools/check-network-runtime.py` now guards both first/final native link passes and required flag.
- The `eden-dummy-thread-waits.patch` changes `KLightLock` wait-queue lifetime. Audit discovered `ClearWaitQueue()` can occur with `ThreadState::Waiting`, while `KThread::NotifyAvailable()` and `CancelWait()` can dereference `m_wait_queue` without a null guard. Therefore it is UNQUALIFIED and is now optional only with `EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS=ON`; default OFF.
- Separate Dynarmic cross-core I-cache coherence patch remains behind `EDEN_EXPERIMENTAL_ICACHE_COHERENCE=ON` (default OFF), as it is not proven to cause FC27 freeze.
- Added `tools/check-ps5-backport-policy.py` verifying both experimental defaults stay OFF. Static patch-application tests alone are not proof of runtime correctness.
- Rechecked real local `assets/icon0.dds`: 262,292 bytes, DDS DX10, 512x512 BC7. Packaging copies it into `sce_sys/icon0.dds`, release metadata and staged-app gates require matching bytes. Presence/format are proven locally; PS5 overlay behavior still needs hardware.
- Latest quick checks PASS: net compatibility C syntax, host sanitizer DNS+SO_NBIO harness, network link contract, experimental policy, Home media, log policy, Encore UX, release metadata, legal/SFX, modified shell syntax and `git diff --check`.
- No build or hardware results obtained. User approval remains necessary before any compiling/staging of PS5 application or CI push.


### 2026-10-08 resumed integration pass on active Mac worktree

- Confirmed real repo is `/Users/admin/Downloads/Prospero.Eden-Encore-work`, branch `local/no-build-polish`, HEAD `149df7a97ffb200841eb3f680ed61a5384c26a39`. The earlier `...-legal-pass` directory no longer exists. All existing 48 modified/untracked files retained. NO app build, push, commit, merge or CI dispatch.
- Detected a real Home compile regression: `draw_home()` still called `measure(chip, 18.0f)` after the local `measure` lambda had been deleted. Replaced it with existing `text_width(c, chip, 18.0f)`; verified its signature in `widgets.hpp`. This is a static source correction, not a PS5 compilation result.
- Home navigation: first utility (Quick Settings) now returns Left to hero/details instead of wrapping to the last utility. Adjusted legacy controller-artwork coordinates so they would not overlap the 506px player-capacity chip if that auxiliary draw routine is wired in later; currently `draw_controllers()` has no call sites, so do not claim visible icon changes. Strengthened UX contract checks.
- Native PS5 `__wrap_fcntl` was still reading `F_DUPFD`'s promoted int as `intptr_t` via `va_arg`; this is undefined behavior and `LogPipe::Attach()` uses `fcntl(fd, F_DUPFD, 3)`. Fixed and added a host sanitizer pass-through regression. This supplements the earlier F_SETFL/F_SETFD varargs fix.
- DNS shim now rejects malformed/negative/overflowing/out-of-range service ports instead of silently making them port 0; explicitly supports standard `http`/`https` service names unless `AI_NUMERICSERV`; rejects both node and service NULL; numeric getnameinfo now rejects undersized host/port buffers with EAI_OVERFLOW rather than returning silently truncated output. Added mocked ASAN/UBSAN cases including very long port numbers.
- New local validation: clang C11 `-Wall -Wextra -Werror -fsyntax-only` for ps5_net_compat.c PASS on Mac SDK; `check-ps5-net-unit.py` PASS with ASAN/UBSAN (mocked native PS5 resolver, NOT hardware proof); `check-encore-ux.py`, `check-home-media.py`, `check-network-runtime.py`, `check-ps5-backport-policy.py`, `check-bounded-logs.py`, `check-sm-host-wait.py`, `check-release-hotpath.py`, modified shell `bash -n` and `git diff --check` PASS.
- Expanded no-app-build gate sweep: **27 PASS out of 31 attempted**; remaining 4 (`check-filesystem-probe`, `check-legacy-migration`, `check-storage-contract`, `check-tsc-fallback`) did not execute because `clang++-18` is unavailable on this Mac. Do not report source-test failures for those, or assume that their Linux equivalent passes. Other gates still require dedicated inputs/Linux LLVM/native PS5 linker.
- Hard outstanding release gates: audit/qualify default-on service-manager HLE backport against real PS5, native PS5 compilation/link, Nlib HTTPS/certificates/media on console, overlay icon0.dds behavior, image UI and controller interactions, 30fps frame pacing and FC27 stability/long soak. FC27 freeze cause still unproven; frame generation separate feature, not a freeze remedy. Explicit user OK is required before any PS5 app build/push/CI.


### 2026-10-08 log-rotation fault-injection and future CI gate

- Additional bounded-logging audit found `LogPipe::Drain()` ignored a failed `Rotate()`. If a native PS5 `ftruncate`/seek or filesystem operation failed, it could keep appending beyond the cap. Corrected retry behavior: second segment falls back to `open(O_TRUNC)` if `ftruncate`/seek fails; when rotation genuinely fails the pipe keeps draining without writing unbounded data, and the next chunk retries rotation. The initial rotation now restores the original log path if reopening the new segment fails. Runtime PS5 behavior unverified.
- Added `tools/check-log-pipe-unit.py`, a host-only C++ harness that **forces ftruncate to return EINVAL** and verifies two segment files stay bounded, earliest entries survive, most recent entries survive, and `LogPipe::Detach()` completes. PASS on Apple Clang with the macOS SDK.
- `tools/check-ps5-net-unit.py` enhanced with boundary/overflow/error cases and portable Linux guards for `sockaddr_in.sin_len` in the C shim; CI now calls both network sanitizer and log-pipe host micro-tests before native build. Clang selection uses Apple Clang on macOS (Homebrew clang-18/ASAN timed out once), clang-18 first on Linux. Linux execution is not proven until CI is authorized.
- Re-ran unit tests and static gates: network ASAN/UBSAN PASS, bounded logging host fault-injection PASS, Home UX/media PASS, network contract PASS, logging contracts PASS, shell syntax PASS, `git diff --check` PASS. Latest local working set is 49 modified+untracked paths due to the new log unit test. No PS5 app build, Git commit, push or CI run.


### 2026-10-08 log-pipe handoff race follow-up

- A repeat of the real host log-pipe regression intermittently aborted on `fclose()` after `Detach()`. Review exposed an unsynchronized shared `file_fd`: the worker could close/replace it while `Detach()` used it in `dup2`. Added a mutex around worker rotation/write and the descriptor handoff. `Detach()` now first redirects the pipe writer under the lock (allowing EOF) and, after worker join, redirects to the final log segment. This is a source-level race repair; PS5 release remains untested.
- Repeated the fault-injected host test 5 consecutive times: 5/5 PASS, preserving bounded first/recent segments and the final entry. Network ASAN/UBSAN test PASS and `git diff --check` PASS. More stress and the actual PS5 runtime are still pending. Forwarding through `__real_fcntl` now preserves the promoted `int` argument type for `F_DUPFD/F_SETFL/F_SETFD` both when decoding and when invoking.


### 2026-10-08 resumed post-#186 audit (second pass; pending release)

- User authorized conditional merge/CI **only if confidence is complete after review/cleanup**. Continue local checks; never interpret source-only success as PS5 validation. Active Mac repo still `Prospero.Eden-Encore-work`, branch `local/no-build-polish`, base `149df7a`; no push/CI/app build triggered at this checkpoint.
- Targeted **actual PS5 Clang C++ `-fsyntax-only -Werror` using the cached native compile_commands** discovered another real Home compile error: `tr("Video") + " · "` was `const char* + const char[]`. Corrected with `std::string{tr("Video")}`. Target syntax then PASS: Home, Library, Launcher, Settings, `eden_services.cpp`, `main.cpp`, `performance.cpp`. The cached compile database pointed at an old `/tmp/encore-audit` tree; prepended the current source include paths so tests examined current headers instead of silently testing old ones.
- Targeted **x86_64-sie-ps5 C syntax** discovered the previous Mac-tested `getnameinfo` declaration *still* mismatched the PS5 Payload SDK: PS5 expects `size_t` (vs Darwin `socklen_t`) for host/service output sizes. Added conditional prototype matching the target; actual cross-target `clang-18 -fsyntax-only -Werror` now PASS. Mocked host resolver ASan/UBSan still PASS.
- Applied the three new Eden patches to **isolated temporary source copies** from the exact cached Eden pin and verified **PS5-targeted C++ syntax** for patched `logging.cpp`, `audio_controller.cpp`/SM header, and `net.cpp`: all PASS. No source cache was modified. This does *not* prove final link/runtime behavior.
- Identified potential self-recursive logging when `FS::IOFile::Flush`, `Open`, `SetSize` log a filesystem error during `FileBackend::RotatePs5()`. Patched candidate now temporarily sets `enabled=false` throughout filesystem rotation and restores it after reopening/writing; patch regenerated with valid unified diff; dry-run applies; static guard added to `check-bounded-logs.py`. No hardware storage-failure injection yet.
- Changed `eden-sm-host-wait.patch` from default-on to optional only via `EDEN_EXPERIMENTAL_SM_HOST_WAIT=ON` (default OFF). Dummy-thread-wait and Dynarmic I-cache proposals remain OFF. All 3 excluded from baseline until controlled A/B. Updated policy gate accordingly.
- Updated Markdown sources **README.md, SETTINGS.md, docs/BUILDING.md, docs/FORK_NOTES.md, MEMORY.md**. New sections explicitly distinguish shipped hardware-tested #186 vs unbuilt local candidate, correct formerly overstated SSD capacity and detailed Debug logging descriptions, record test gaps and provisional observations. Release Notes section `## Changes in Encore R1` left intact to preserve packaging extraction.
- Outstanding: full Linux LLVM/preflight (especially clang++-18-specific harnesses), native PS5 link/package and real console startup, Nlib HTTPS, UI image/overlay and FC27 soak. FC27 freeze is **not** fixed and FPS presentation ≠ guest progress. No merge/CI should occur just because source-only syntax is green.


### 2026-10-08 FPS, freeze-triage and human attribution continuation

- User stressed that a **significant** FPS increase is valuable, and asked that **authors/maintainers be named for every upstream repository** in credits (including passion/open-source projects). Continue CPU/HLE freeze mitigation and performance research as independent tasks. No performance gain or frame interpolation is claimed to exist yet.
- Confirmed `headless/graphics.cpp` already counts *presented* output frames and optional dev profiling logs GPU/JIT/HLE and `EDEN_PERF_CPU_POINT`. Host present FPS can remain 30 while FC27 guest is frozen, so do not use FPS alone to claim progress. `headless/display_refresh.h` controls presentation/requested refresh; 120 Hz is not native game 120 FPS. Existing `headless/dynarmic/jit_links.inc` performs optional halt_reason checks for backward/self JIT links in wall-clock timing; it remains a hardware-unproven candidate, not evidence of a successful FC27 repair.
- Created `docs/PERFORMANCE_ROADMAP.md`: Stage A solve FC27 freeze by correlated guest-PC/CPU/GPU/HLE timing and single-variable A/B of three OFF-by-default experimental backports; Stage B measure and optimize *native* frame latency, only opt-in game-specific 60 FPS patches with validated physics; Stage C research Vulkan AMD FSR 3.1 / standalone optical-flow **30 genuine → 60 presented FPS**, fully separate from emulation FPS and with strict VRAM, latency, HUD artifact and per-title fallback gates. No generation engine currently integrated into PS5 app. FSR 3 demands frame history/optical-flow/queue/pacing and UI handling and AMD recommends a faster-than-30-FPS input for low-latency results.
- Added offline `tools/analyze-fc27-trace.py` parser of `EDEN_GAME_FRAME`, `EDEN_DEV_FRAME`, `EDEN_PERF_CPU_POINT`, `EDEN_DEV_HLE`, `EDEN_DEV_QUEUE`; emits JSON or readable clues for long present gaps, *hypothesized* repeated PC spans, CPU-time delta and HLE costs. It explicitly refuses to claim gameplay liveness from FPS. Added `tools/check-fc27-trace.py` synthetic healthy/busy-loop/wait tests and installed gate into existing CI preflight; all PASS locally. No real PS5 trace analyzed in this continuation.
- Verified upstream repo owners/maintainer identities via GitHub app. Updated all **28** README repository credits with author or maintainer/team identification, e.g., BlackBearReloaded, Mihawk, John Törnblom, Mitsunari Shigeo, Sean T. Barrett, Victor Zverovich, Behdad Esfahbod, Jean-loup Gailly, Mark Adler and Fabrice Bellard; organization/team entries remain collective; Citron HLE reference commits authored by `@HopeSuffers`. Mirrored all 28 attributions into `THIRD_PARTY_NOTICES.md` for package-side legal text. Added `tools/check-credit-attribution.py` to validate perfect README/notices parity, wired into CI, and `CONTRIBUTING.md` policy requiring source author identification on future integrations. Automated attributions and license checks PASS. Names are attribution, not sole-authorship assertions.
- Updated README, SETTINGS.md, docs/FORK_NOTES.md, docs/BUILDING.md, docs/PERFORMANCE_ROADMAP.md, THIRD_PARTY_NOTICES.md, CONTRIBUTING.md and MEMORY.md; release notes `## Changes in Encore R1` preserved. Source-gate sweep **30/30 PASS**, legal/SFX metadata PASS, CI YAML PASS, `git diff --check` PASS, checks include FC27 parser and credit parity. All controls local/source-only; graphics frame generation remains prospective.
- The 2026-10-08 audited branch remains `local/no-build-polish` rooted at `149df7a`, **61 modified/untracked paths** currently, no native PS5 full app build, push, GitHub merge, CI run, or hardware PS5 test. User authorized merge/run only after exceptional confidence and cleanup; must not publish this as 100% qualified without real build/link and firmware 13.60 smoke/FC27 soak. Preserve local diffs and caches.


### 2026-10-08 CI red #37709145188 and staged-gate fix

- Local audited 61-file changes committed as `9c56ae2` and fast-forward merged/pushed to default branch `fix/0.40-zbic-13.60` (not `main`); first pushed workflow #37709145188 FAILED in **Validate startup, elevation and storage contracts**, *before native compile*. Previous startup/storage/network/JIT/log gates passed.
- Error: new `tools/check-dummy-thread-waits.py` accessed `.local/headless-cache` before GitHub runner ran `make prepare`. The companion `check-dynarmic-icache.py` had identical assumption and would fail next. This is a fixture lifecycle bug, not PS5 code compilation.
- Changed both checkers to always enforce source-patch invariants at early preflight, then *defer* exact source patch applicability when local `.local/headless-cache` is not present. `--require-pinned-source` explicitly refuses deferred behavior. Added strict second-stage checks in `tools/build-headless-native.sh` after pinned source is prepared and before native CMake/compile. Verified by temporarily hiding local cache record: both early policies PASS, strict missing source deliberately FAILS, restored pinned source strict checks PASS.
- Restored the `.local/headless-cache` record after the simulation. Do not rerun build #37709145188; commit/push the targeted fix and use new triggered run.


### 2026-10-08 CI red #37709504223: changed HTTP patch vs restored source cache

- Run #37709504223 at `d4a2b30` FAILED in `Prepare native build inputs` (`make prepare`), before native compilation. Error: `Backport changed; reset the Eden source cache: eden-ps5-net-user-agent.patch`. Cached Eden source had receipt for initial network patch SHA-256 `7117c1c3...` (UA+Accept only); revised patch added error reason to LOG_ERROR.
- Added strictly gated migration for *that exact old receipt* in `tools/apply-eden-backports.sh`. New `tools/migrate-net-user-agent-cache.py` changes only the verified `src/common/net/net.cpp` error log statement, checks UA/Accept, is idempotent and fails closed on unexpected source. Does not delete cached Eden, FFmpeg, CMake, or compiled objects.
- Added four-case migration unit `tools/check-net-cache-migration.py` to full CI preflight. Tested old upgrade/retry/pristine mismatch/unexpected source, all PASS. New and logging patch git-apply dry-runs against local pinned source PASS. This is a build-environment fix, not gameplay freeze repair.


### 2026-10-08 CI red #37710086280 (full native compile success; late stale validation)

- Run #37710086280 on `f44843f` successfully compiled PS5 app; `headless/check_package.py --check` said `Native package inventory, fixture, alignment and imports PASS`. Upload `Prospero.Eden-Encore-staged-app` artifact id 11521966412 (~37 MB) succeeded; late `tools/ci/check-staged-app.py` failed because it asserted obsolete `kHomeCache` present in Home source. Actual Home has `kHomeQuickPanel`, `kHomeQuickFirst`, `kHomeStorage`, `kHomeControllers`, and `kHomeFullSettings`.
- Replaced stale source marker in checker with real four-action navigation markers, added early check to `tools/check-encore-ux.py` for consistency. Downloaded actual artifact onto authorized Mac at gitignored `.local/resume-artifacts/PPSA99008`; full 162-file staged validator PASS, early Encore UX and CI-cache gates PASS. No new native compilation required; resume prior staged app with `workflow_dispatch` and input `resume_run_id=37710086280`, `publish=false`. Commit message `[publish-existing]` avoids redundant automatically triggered push build; release remains test-only.

### 2026-10-08 — Eden Encore post-approval work (GitHub only; UI render frozen by user)

- **Authoritative UI reference:** `maquetteunique.png`. User accepted native C++ launcher visuals from preview run #37720713295; **DO NOT rerun launcher-preview workflow** for this icon-only follow-up. The approved violet/pink logo, Home COVER background with dark left/bottom scrims, seven recent covers, 4 utilities, focus gradients and user-facing `Joueurs max.` / `Cache` remain.
- User requested only two last icon refinements: an unmistakable **eight-tooth gear** for Settings in tab/card and a more recognizable **PlayStation DualSense-style** controller outline for Home utility and players badge. Implemented once in shared `pe/ui/widgets.cpp` vector functions `settings_gear` and `dualsense_icon`; existing controller overlays now share this geometry. **Not native-rendered since the user forbade new GUI runs.**
- **Universal GPU/renderer hot paths:** when FPS overlay is hidden, neither OpenGL nor Vulkan formats HUD glyphs/queries-reset system performance stats every frame/second; presentation counters remain. The PS5 `sceSystemServiceHideSplashScreen` failure path now attempts once per GraphicsWindow, instead of potentially repeating a kernel call + log line every presented frame.
- **Nlib launcher I/O:** `Textures::pump` now decrements the per-frame load budget even for missing files (the previous `continue` skipped the decrement and could probe many missing images in a single frame). Retries for new image arrivals use 450 ms initial / 1.5 s / 3 s backoff, without a per-frame stat. All-game eager Nlib concurrent banner/icon/screens fetching remains.
- **CI:** fixed source-contract tests that still asserted obsolete per-game Home-only media and fixed 3-second texture retry. Added `tools/check-runtime-frame-budget.py` and lightweight `.github/workflows/encore-core-preflight.yml` (no native renderer, no PS5 build).
- **Latest source preflight:** GitHub Actions **#37721799353 SUCCESS**, including all-game HLE/DNS isolation, render hotpath, bounded logging, Nlib I/O, 7-profile performance policy, French UX contracts and full feature branch `git diff --check`. No PS5 firmware/gameplay runtime test; neither FC27 freezing nor increased FPS has been proven resolved. All post-preview commits are on `local/fc27-offline-no-build`, NOT merged into default `fix/0.40-zbic-13.60` and NOT published as PS5 package.
- **Next gate:** when core review is complete, build PS5 app *once* from the feature branch and check linker/asset/package checks; then only hardware can validate gameplay/VRAM and real Nlib loading. Avoid premature repeat full builds or claims about solved freezes.

### 2026-10-08 — Follow-up to four real PS5 screenshots (no runs)

- User supplied four real PS5 screenshots: FC27 blank Home/Library covers/screenshots, Zelda beautiful cover but clipped long title/intro and white sky reducing top-nav readability, Fire Emblem working with genuine screenshots. Only `maquetteunique.png` remains the approved composition; no image generation, no local Mac, no GitHub run at user's explicit request.
- Branch: `local/fc27-offline-no-build`. **All code changes are unbuilt and untested on console**. Do not interpret source-only checks as native build success and do not reuse prior green artifact as containing these edits.
- UI: Home long titles now wrap up to 2 lines; hero captions wrap to 2, metadata adjusted to clear button row; added top dark gradient over bright backgrounds; player count label centred within the region after the DualSense icon; navbar shortens to `Récents`; Home storage now says `Jeux · Cache` or real usage instead of exposing `/data/prosperoeden`.
- Nlib: validate cached uncompressed BGRA/TGA header, dimensions and payload length rather than trusting file existence; bad files can be re-fetched; accept JPEG or PNG from image endpoints; expose aggregate missing-media diagnostics; refresh sparse cached metadata to discover newly available artwork; bounded network retries of missing Home media (2 min), all installed games (5 min), and metadata (5/30 min) with a lightweight 8-second launcher check. Game network is still never required.
- Visual fallbacks: Library prefers Nlib/ROM square icon over panoramic banner for cards, uses contain for icon-only detail image, shows human-readable loading/unavailable states, hides invalid thumbnail slots. Home recent tiles also show status, no fake media. New French translations in fr-FR and fr-CA, with prior malformed literal newline entries repaired.
- New source guard `tools/check-nlib-ui-recovery.py`. No workflow run started, no PS5 build or merge; must compile/test before distributing another installable build. FC27 artwork depends on actual ROM extraction and Nlib availability; no hardcoded replacement is promised.

### 2026-10-08 — FC27 Nlib artwork cache audit (source only; no build)

- User reports that FC27 media exists on Nlib. Old complete schema-v2 metadata could persist indefinitely, including outdated artwork absence. Nlib schema v3 adds weekly persisted metadata refresh and monthly refresh of valid image files; retain existing files if downloads fail.
- A screenshot fallback must not count as an already-cached real banner.
- When an atomic download replaces a file under the same path, the launcher now invalidates its affected in-memory GL texture, instead of retaining stale artwork until restart.
- Source-contract guard updated. No native PS5 compilation, workflow dispatch, preview, or hardware validation. Never claim this is in the previously shipped package.

### 2026-10-08 — User-provided FC27 PS5 stutter logs; source-only fixes

- Current heap.log includes a 70.3-minute Vulkan session (29.58 mean present FPS,
  13/840 five-second windows below 20 FPS, 148 present gaps >100ms, worst 2641ms).
  Late `EDEN_JIT_PRESSURE` on cores 0/1/2 recurs near stutters; worker topology
  is still not proven (`ready=0 distinct_cores=1`). Shader/JIT caches were
  cleared from Diagnostics, some launches show 0 pipelines. Causality unproven.
- stderr.log and stderr.prev.log contain 32 PlayStation Auto context flips and
  1826 per-button event logs; user reports actual button layout reverting.
- Fixed launcher activation: PlayStation mapping now remains fixed across UI
  and gameplay (no automatic Nintendo-position switchover); raw button-event
  printf restricted to diagnostic builds. Added bounded Vulkan frame gap/streak
  counters to release frame summaries for next hardware investigation.
- Updated stale UX source contract left by prior Nlib cache-schema v3 change.
- FSR 3.1/ML, logical-core pinning, JIT pressure-aware reuse are investigation
  only; *nothing experimental enabled in shipping* without exact PS5 tests.
- Feature branch `local/fc27-offline-no-build`; no CI, PS5 build or preview,
  and no claim that new stutter fixes are installed on hardware.

### 2026-10-08 — Source-only opt-in runtime experiments

Feature branch `local/fc27-offline-no-build` has experimental A64 JIT
cache tiers (normal/256-224-224/320-256-256 MiB), guarded fallback to
distinct *logical* OS CPUs if PS5 topology is unreliable, passive Vulkan
frame-pacing histogram, and CPU affinity restoration on game return/failure.
Only explicit `/data/prosperoeden/config/experiments.json` per-title
settings activate them; Safe Launch always disables them. Stable mapping fix
and shipping GPU/CPU policies remain intact. Source-check script:
`tools/check-experimental-performance.py`; instructions:
`docs/FC27_EXPERIMENTS.md`. No compile, workflow run, real frame generation,
or PS5 hardware performance validation.

### 2026-10-08 — PS5-first global performance architecture (authoritative current checkpoint)

- **Branch / scope:** `dev/ps5-sparse-jit`, based on `local/fc27-offline-no-build`; isolated developer source changes, **not** merged, compiled or qualified on PS5 FW 13.60. No new launcher/UI build, CI native build, package or release has been launched from this branch. The old installed binary does not contain these changes.
- **FC27 A/B/C/D diagnostic campaign complete, no further user experiments:** A: 27.89 FPS / 17.7 >100ms gaps/min / 3.26 JIT pressure/min; B: 28.48 / 7.34 / 1.43; C: 28.63 / 5.26 / 0.71; D: 27.95 / 8.29 / 2.09. Different durations/scenes, so directional not controlled. C gave best observed pacing; D logical pinning not beneficial enough. FC27 hang remains unresolved. **Do not ship FC27-only hacks or assume GPU/CPU unused based on PS5 temperature.**
- **Universal emulation policy:** ALL titles share CPU worker and Vulkan pipeline scheduling policy and JIT memory management; ROM/title ID only identifies dev-log context or independently sourced exceptions for other concerns. Legacy A/B/C tier selection (including FC27-specific auto-C) **removed** from the actual normal app code. Former `experiments.json` is developer-only for CPU affinity tracing, frame histogram and, behind `EDEN_SPARSE_JIT_DEV`, sparse-mapping investigation; it no longer chooses A/B/C sizes.
- **Global JIT sizing now implemented for A64 and A32**, in `headless/experimental_performance.h`, launch path `headless/main.cpp` and generated Dynarmic wrappers `headless/CMakeLists.txt`: a one-time PS5 direct-memory query computes a **continuous per-guest-core code budget** based on free contiguous direct memory, retaining 3 GiB for other guest/GPU/system allocations and committing at most half of the pool beyond that as *initially dense* JIT. Allocate only active ISA and preserve core3 at 16 MiB; baseline A64=256/192/192, A32=512/64/64 MiB if unavailable/low memory or Safe Launch. Expanded sizes are **not limited by 320/256/256 C**; there is no 4 GiB global arbitrary cap. A **per Xbyak arena** safety bound of 1536 MiB remains due to x64 RIP-relative encoding; lifting it requires multi-segment JIT trampolines and code-pointer handling. IMPORTANT: today's allocated capacities are still physically **eager/dense**, not lazy on-demand; no auto-growth during gameplay yet. Shipping on PS5 not tested.
- **Developer-only sparse JIT** groundwork in `src/memory_pages.cpp`, `headless/jit-allocator.h` and code-generator rewrite: two stable RW/RX reservations, 2 MiB physical chunk commits, mapping/permission startup probe with dense fallback, accounting and teardown. Still **not production safe**: mid-session physical mapping/commit failure can abort instead of gracefully evicting; multi-arena expansion not implemented. Do not enable sparse for release; build option `EDEN_SPARSE_JIT_DEV=OFF` by default.
- **Vulkan pipeline concurrency global PS5 policy:** `tools/prepare-vulkan-port.py` uses actual OS-allowed CPU-affinity mask rather than desktop hardware_concurrency()-1; smaller background pool reserves resources for guest/GPU worker progress. Count logged once; no hardware-validated speedup claim. More parallel worker threads != more useful GPU throughput.
- **Shared GPU/CPU memory:** current port still uses biggest contiguous free direct memory block for conservative GPU cache budgeting; largest block != total free. `headless/performance.cpp` now contains lifecycle-only bounded memory region enumeration at real `core_initialized` and `core_shutdown`, plus virtual vs actually committed sparse JIT counters. Any change relaxing Vulkan texture/VRAM eviction **must** be based on actual usage, fragmentation and driver behavior, not guessed 16 GiB free. GPU budget and sync stalls remain to optimize.
- **Diagnostics and docs:** `docs/PS5_NATIVE_ARCHITECTURE.md`, `docs/FC27_EXPERIMENTS.md`, README and `tools/check-ps5-architecture.py` / `tools/check-experimental-performance.py` updated along this branch. No separate user-facing settings or visual rework. Confirm precise source gates and host C++ policy fixture before native promotion.
- **Outstanding architectural work (DO NOT CLAIM DONE):** (1) demand-committed JIT that survives real PS5 W^X/aliasing and OOM; (2) multi-segment growth past single-arena addressing, safe pointer retargeting; (3) memory coordination between guest JIT and Vulkan renderer; (4) measured guest-liveness/CPU/GPU scheduling and synchronization freezes; (5) separate image quality/upscaling optimisation; (6) native compile + 13.60 hardware tests and rollback. This checkpoint is **current project memory**, superseding older stale A/B/C-only instructions above without rewriting the historical experiment evidence.

### 2026-10-08 — Universal shader persistence / disk-pressure optimization

- **New global shader-cache policy, source-only on `dev/ps5-sparse-jit`:** RADV/Mesa no longer gets an arbitrary fixed 256 MiB disk cache limit when `std::filesystem::space(Eden::AssetsDir())` is available. Cache size scales with one eighth of available writable space on the **actual RADV cache filesystem**, expressed as `MESA_SHADER_CACHE_MAX_SIZE`, with fallback 256 MiB if the `space` query fails. This uses C++ `std::filesystem::space(cache)` (the same filesystem API family as the boot-proven assets-root query), NOT direct PS5 libc `statfs("/user")`. The cache path itself has not yet been hardware-tested.
- Native OpenGL shader cache **no longer prunes every session at an arbitrary 64 MiB total**. `headless/cache_budget.h` now keeps compiler records until filesystem free storage is low, then deletes the oldest valid `3-4 hex chars .bin` records just enough to restore a free-space floor (32 MiB minimum for small sandboxes, up to 1 GiB on a full filesystem). Non-cache files are not deleted. A failed `space` query causes NO speculative deletion. This cleanup is between game sessions, never on frame path.
- Added host-source fixtures `tools/check-jit-memory-policy.py` and `tools/check-shader-cache-pressure.py`; these compile small C++20 policy tests but **no native PS5 app build or firmware 13.60 run** has happened. Small equivalent host C++20 algorithm fixtures were run separately and passed, but the repo scripts and the full native app still require dedicated verification.
- This optimizes **persistent shader compilation**, which is distinct from GPU/VRAM/guest CPU throughput. Do not claim it solves FC27 freezing or is hardware-qualified. Keep `MEMORY.md` current on every major architecture decision.

### 2026-10-08 — Resource-budget accounting clarification

- The launch log `EDEN_PS5_JIT_POLICY` now labels `admission_budget_mib` separately from per-ISA `a64=...` and `a32=...` arena sizes; an admission budget is **not** the number of bytes actually resident. Dense JIT allocations still commit physical RAM upfront; developer sparse JIT emits `EDEN_JIT_SPARSE_MEMORY reserved / committed` at lifecycle boundaries only. Never infer spare PS5 RAM from capacity alone.
- Host C++20 equivalents of the universal JIT policy and disk-pressure trimming were compiled/run separately; both passed their tested invariants. Full repository scripts and the native PS5 application have **not** been run/validated yet. Both new host gates are now wired into the lightweight source workflow and the normal release preflight, but this feature branch is excluded from automatic PS5 builds.

### 2026-10-08 — Sparse JIT constructor safety, physical-memory reuse, dense telemetry

- Repository branch remains `dev/ps5-sparse-jit`, **not compiled, hardware-tested, merged or released**. User-approved launcher unchanged. No extra A/B/C/D modes or title whitelist. These source changes apply to all guest A64/A32 architectures, sparse implementation remains `EDEN_SPARSE_JIT_DEV=OFF` in regular builds.
- **Constructor ordering bug fixed:** upstream Dynarmic initializes a ~2 MiB constant pool in its member constructor, *before* its `BlockOfCode` constructor body invokes `EnsureMemoryCommitted`. Reserving two unbacked virtual code mappings and waiting for the latter call would fault immediately. `ReserveSparseJitCode` now commits a 4 MiB physical bootstrap before returning RW/RX addresses; if this initial physical commitment fails, it releases the sparse reservation and the allocator attempts its existing dense backend.
- **Sparse vs dense alias ownership:** an explicit `IsSparseJitCode` map check ensures `EnsureMemoryCommitted` requests physical pages only on actual sparse-owned regions. Sparse reservation failure must not attempt sparse commits into a dense fallback.
- **Physical memory pressure:** native `CommitSparseJitCode` returns false for direct-memory allocation failure before mapping. The derived `BlockOfCode::EnsureMemoryCommitted` raises `std::bad_alloc`; derived A64/A32 guest interfaces catch it once, call the existing cache-invalidation protocol (which rewinds the code cursor), then retry within **already committed pages**. This is a targeted opportunity to survive a *recoverable* growth failure; a second failure or an error after partial RW/RX mapping still cannot recover safely. Do **not** claim full OOM resilience or activate sparse in shipping without a real PS5/native test.
- **Measuring real native RAM:** dense JIT allocations now increment a global physical `dense_jit_direct_bytes` counter (including allocation header/alignment) and decrement it on corresponding frees / partial-failure paths. `EDEN_JIT_DENSE_MEMORY phase=... physically_owned=...` alongside sparse reserved/committed counters is emitted only at lifecycle snapshots, not each frame. This fixes the previous blind spot where only the experimental sparse cache had physical accounting.
- The offline `tools/check-ps5-architecture.py` source contract asserts constructor bootstrap, ownership query, dense allocation/free, A64/A32 one-shot recovery hooks and diagnostics. **It has not been run as a full GitHub runner/PS5 build**, so compiler/linker correctness and hardware success remain unproven.
- **Still required:** PS5 executable-alias hardware qualification, graceful handling of partial mapping errors, multi-arena executable JIT expansion and safe branch trampoline ownership, total CPU/GPU memory coordination, real host/guest GPU wait measurements, a successful native compile + firmware 13.60 smoke/soak test. No statement of full PS5 resource utilization is justified by temperature.

### 2026-10-08 — Host sparse-memory regression fixture and destruction snapshot

- Added `tools/check-jit-sparse-host.py` using the **real** `src/memory_pages.cpp` compiled with `PS5_NATIVE` and seven Linux mocks for the SDK direct-memory calls; validates fixed RW/RX virtual maps and alias visibility, 4 MiB early bootstrap, 2 MiB physical growth, deliberate pre-map OOM retaining prior bytes, release and cleanup after failed bootstrap. Wired it into `.github/workflows/encore-core-preflight.yml` and the release preflight without enabling a full PS5 build; **test script not executed in this session**.
- Extended existing `tools/check-jit-allocator.py` native host fixture to assert that dense JIT direct-memory accounting rises while compiled code exists, then returns to zero after cache destruction and native partial-error branches.
- Lifecycle direct-memory diagnostic now also reports at **`core_destroyed`**, after guest CPU teardown, to catch actual resource leakage. `tools/check-ps5-architecture.py` updated to require that emitted phase.
- Sparse physical-commit OOM fallback currently attempts one JIT cache evacuation/reuse for A64 and A32. **Do not claim full OOM resilience**: another allocation failure, mid-map failure, firmware protection mismatch and dynamic multi-arena growth are still open; normal PS5 builds still use dense allocation.
