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

### 2026-10-08 — Audit cross-dependency PS5-first: Dynarmic, Xbyak and Vulkan persistent workers

- **Upstream status clarified:** Dynarmic is not universally dormant since 2024. The `azahar-emu/dynarmic` fork has Git commits on 2026-06-24 and 2026-09-26; a more recent upstream commit does not automatically make the fork's ABI or memory ownership compatible with Eden Encore. The pinned emulator source in `UPSTREAM.json` is Eden commit `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a` and its `src/dynarmic` is a **vendored directory**, not a standalone Git submodule that can simply be updated. Compare/fix per source unit, keep author/license notices; **do not blindly replace all vendor code** or imply a full upgrade happened.
- **Dynarmic/Xbyak actual startup bug class:** global A64/A32 JIT capacities may exceed small contiguous free physical blocks and fail *before any guest execution*. Added `headless/jit-startup-retry.h` plus generated core-wrapper call in `headless/CMakeLists.txt`: only `Xbyak::ERR_CANT_ALLOC` and `std::bad_alloc` trigger halving the requested code arena until its original per-core A64/A32 baseline. Other Xbyak errors propagate without retries; 8 MiB null-JIT instances are not artificially grown. Bounded one-shot per-failure retry logs `EDEN_JIT_STARTUP_RETRY` only on actual memory errors, not per frame. Source-only; PS5 native constructor/link qualification pending. Added host fixture `tools/check-jit-startup-retry.py` with a minimal Xbyak exception shim (no vendor download) for retry and error-propagation tests.
- **Important Vulkan worker cancellation trap:** pinned Eden `Common::StatefulThreadWorker::WaitForRequests(stop_token)` attaches a stop callback that invokes `thread.request_stop()` on each **persistent shader compiler thread**, so naïvely passing a cancellable preload timeout would permanently stop later on-demand compiler workers. Do **not** add that. Fixed PS5 lazy pipeline-cache initialization in `tools/prepare-vulkan-port.py`: for an already-requested stop token, `Vulkan::PipelineCache::LoadDiskResources` first sets the game's shader pipeline filename and optionally loads the Vulkan driver pipeline cache, then returns **before scheduling or cancelling the worker pool**. Main's `EDEN_PS5_VULKAN` path calls the initialization once per game after GPU ready, enables `use_disk_shader_cache` and `use_vulkan_driver_pipeline_cache` for real games, and prints `EDEN_VULKAN_SHADER_CACHE ... mode=lazy-persistent`. This restores serializing **newly** generated guest pipelines across sessions without forcing full old-cache precompilation at game startup. Earlier stored guest pipeline entries are **not proactively loaded** by this lazy path; this is not an FPS fix proven on console.
- **Global design:** foreground console gameplay has one demanding guest; the launcher may still do OS/background work, and the PS5 OS/driver continue running. Do not forcibly claim mono-CPU occupancy or assume all eight CPU cores or all 16 GiB accessible to the app. The Vulkan pipeline worker pool is limited based on process CPU affinity as previously coded. Keep native GPU/CPU frame pacing, liveness, RAM pressure and per-game metadata separate.
- **Preflight tests:** new `tools/check-vulkan-pipeline-persistence.py` (static non-destructive worker and cache initialization assertions) and `tools/check-jit-startup-retry.py` (host C++20 fixture) added to both lightweight and release CI preflight definitions. No PS5 build or hardware test executed for this developer branch and **new scripts have not been run**. The approved launcher and memory documentation remain intact.
- **Next execution gates:** check generated CMake wrappers for both architectures, pinned driver behavior of native Vulkan driver-pipeline cache data, shader serialization on launch-exit-relaunch, native 13.60 physical JIT memory recovery, and complete GPU/CPU bottleneck instrumentation before claiming stutter-free play.

### 2026-10-08 — Pin-anchored source checks and driver cache compatibility follow-up

- Added PS5-specific `LoadVulkanPipelineCache` fallback in the Vulkan source transformation: an incompatible RADV Vulkan pipeline cache blob now logs an incompatibility and retries `CreatePipelineCache` with no initial blob. If *empty* cache construction itself fails, error still propagates. The valid guest shader serialized cache remains separate from the Vulkan driver's binary cache. This preserves launch after potential driver updates without claiming driver-cache data remains binary compatible.
- Extended `tools/check-vulkan-pipeline-persistence.py` to assert the exact pinned loader anchor, empty-data fallback, no worker-pool cancellation and true lazy startup. **Not executed on PS5.**
- Direct comparison against the pinned vendored Eden source `5f142c79` yielded **8/8 structural checks**: one A64 and one A32 `m_jit.emplace(config)` constructor injection site; one Vulkan lazy and one driver-cache loader insertion site; persistent worker stop-token behavior; and the guarded transformations. These checks are only source-contract evidence, not a native CMake compile, renderer startup, guest shader serialization success or FPS measurement.

### 2026-10-08 — Core↔Xbyak CMake linkage and source-only CI attempt

- The pinned Dynarmic CMake links `xbyak::xbyak` **PRIVATE**. The new PS5 `core`-side typed constructor retry includes `<xbyak/xbyak.h>`, so CMake now also links `core PRIVATE xbyak::xbyak` on PS5. This reuses the *same pinned Xbyak* rather than importing another revision. `tools/check-ps5-architecture.py` checks the exact target link and bounded retry behavior.
- The lightweight `.github/workflows/encore-core-preflight.yml` is now allowed on `dev/ps5-sparse-jit`; push commit `6765fabf` with `[core-ready]` was made to request a **host-only source CI run**, no PS5 application build and no launcher/UI render. GitHub app workflow enumeration exposes only PR-triggered runs; push-run logs/status could **not** be confirmed during this conversation. **DO NOT CLAIM THE HOST CI RUN PASSED.** New commits after that trigger change the HEAD, so earlier run would not validate all subsequent Xbyak/driver-cache fixes anyway.
- Before a release, all new host scripts (`check-jit-startup-retry.py`, `check-vulkan-pipeline-persistence.py`, `check-jit-sparse-host.py`), generated derivatives, and native PS5 compile/firmware 13.60 soak must be run on the **final** candidate HEAD. The existing branch still contains unqualified developer sparse JIT disabled by default.

### 2026-10-08 — PS5 JIT executable alias failure, macro compilation, Vulkan cache atomicity

- **Production-risk bug fixed in native dense Xbyak allocator:** if the executable RX alias failed to map or to gain PROT_EXEC, the native allocator previously returned the writable RW/NX direct-memory pointer as if it were executable JIT code. This violates PS5 dual-view W^X expectations and can cause guest CPU crashes/faults. \`headless/jit-allocator.h\` now logs alias failure, decrements physical JIT ownership, frees the dense direct-memory block and returns nullptr, letting Xbyak report \`ERR_CANT_ALLOC\` to the already implemented per-core constructor-size retry. \`tools/check-jit-allocator.py\` was corrected: all five fault-injection allocation stages MUST return nullptr; the old harness incorrectly accepted executing the unsafe RW-only fallback. This change applies to all games.
- **Macro wiring bug fixed:** PS5 native main executable and common library define \`PS5_NATIVE\`, but privately built Dynarmic code did not inherit it. As a result, the derived \`BlockOfCode::EnsureMemoryCommitted\` sparse branch (guarded with \`#ifdef PS5_NATIVE\`) could compile out even in developer sparse builds. CMake now attaches \`PS5_NATIVE=1\` **to the single generated \`block_of_code.cpp\` translation unit**, not the entire Dynarmic library. Existing Vulkan-specific CMake already declares \`PS5_NATIVE=1\` for \`video_core\` in \`headless/vulkan.cmake\`; do not duplicate it globally.
- **Vulkan shader persistence hardening for all titles:** upstream pinned Eden directly truncated \`vulkan_pipelines.bin\` when writing a driver cache, risking loss of the previous valid cache when the foreground PS5 process stops mid-save. \`tools/prepare-vulkan-port.py\` now generates a PS5-only transactional cache serializer that writes \`.new\` in the same directory, flushes and closes the stream, then renames over the prior cache; failures clean only the staging file, never the prior valid driver cache. A static mutex serializes concurrent save requests (background flush vs game exit). This is atomic replacement against typical process interruption, **not guaranteed power-loss durability without firmware-verified fsync**.
- **Source regressions/tests:** updated \`tools/check-ps5-architecture.py\` to require native translation-unit compile flags and reject RW/NX code pointers; updated \`tools/check-vulkan-pipeline-persistence.py\` for transactional save; added \`tools/check-vulkan-cache-atomic.py\`, a host-compiled fixture which extracts the actual generated serializer and tests replacement, failure preserving the old blob and competing saves. Both lightweight and release preflights invoke the new gate. These full repository checks and PS5 firmware tests have not been verified on the final HEAD.
- **Host smoke test done locally in this chat:** a small C++20 reproduction of the current \`jit-startup-retry.h\` was compiled and run with an Xbyak exception shim; A64/A32 OOM retries and exception passthrough passed. It is an intentionally reconstructed counterpart, not the exact repository fixture and not a PS5 build. No performance/FPS improvement measured yet.
- **Open major tasks:** production-safe sparse JIT with recoverable mid-map failures; growing beyond a single x64 arena with safe trampolines; dynamic JIT/GPU memory coordination; definitive PS5 CPU/GPU liveness and waiting metrics; native build and game-soak tests; no new frontend design or trial profile UX.

### 2026-10-08 — Continuity after the JIT/Vulkan correctness pass (host preflight)

- Recovered authoritative remote branch `dev/ps5-sparse-jit` at `ad3d829513bc` before further edits. Prior run [core-only #37825080703](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37825080703) **FAILED** on `tools/check-experimental-performance.py:55`: the script demanded the retired phrase `developer-build only` in `docs/FC27_EXPERIMENTS.md`. All later JIT/Vulkan checks were skipped; do not count this run as a JIT or Vulkan failure or success.
- Commit `4e4827b70225` replaces that stale text assertion with the actual source/documentation safeguards: `EDEN_SPARSE_JIT_DEV=ON`, `EDEN_DEV_PROFILE` and the prohibition against enabling unqualified flags on PS5. Commit `8f58294e5d6` updates the historical FC27 guidance, removes the suggestion to reapply retired tiers, and documents 4 MiB bootstrap before subsequent 2 MiB sparse code commits.
- This is a **source/test/documentation** fix only. The production dense JIT RX-alias failure fix and PS5 driver-cache transactional save remain unproven by PS5 native compilation and firmware 13.60 hardware; FC27 guest soft-freeze is still open. Sparse JIT remains disabled by default; no new A/B/C/D modes, game whitelist, UI redesign, or full console build.
- MacBook-Pro-de-ADMIN.local Desktop Commander device was reported **offline** during this recovery. The Mac's local worktree, uncommitted files and builds cannot be attested from GitHub. Run the host-only feature-branch preflight at the final HEAD before recording any green result; the last red preflight predates the RX-alias/Vulkan serializer changes.

### 2026-10-08 — Green source CI; dedicated dense RX-alias guard

- Host-only source run [#37828047337](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37828047337) **SUCCESS** on `7f97987f038d`: architecture contracts, universal A64/A32 memory plan, bounded constructor fallback, sparse PS5 direct-memory mock, exact generated Vulkan atomic cache saver, shader-disk pressure, approved unchanged UX, and full feature-branch diff check passed. **No PS5 native app build/firmware test** was executed; those claims are forbidden.
- Added `tools/check-jit-dense-alias-host.py` at `60d349d4d229`. Unlike the prior native JIT allocator regression that needs generated Dynarmic/Xbyak, this source-only host fixture compiles the **actual** `headless/jit-allocator.h` dense PS5 branch with a minimal Xbyak interface shim and explicitly injected allocation/alias failures, asserting that a failed RX alias never returns the RW/NX pointer and that all accounting/owned allocations are released. It is an ownership and fail-closed test, **not real sceKernelMapDirectMemory/RX firmware qualification**. Wired into host-only and full release preflight in `38dfcff0e582` and `c65b32330c30`.
- Pending at the moment of this entry: execute the new dense-alias gate on the final HEAD via source-only CI. No application build or console test approved/performed for this feature branch.

- First run of the new dense-alias host fixture, [#37828438442](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37828438442), **FAILED in the test mock**, not in the production allocator. Its `CountDenseJitDirect` mock wrongly asserted for `nullptr` after `allocator->free(nullptr)`; the real production function has an explicit null no-op. Fixed mock semantics in `79e683233be3`. Re-run the host-only workflow to qualify the corrected fixture; never label the first red run a production JIT regression.

### 2026-10-08 — Final source-only gate after RX-alias mock fix

- [Core source preflight #37828535877](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37828535877) **SUCCESS** on tested commit `e76a14451a82859365024930361055216aa04f57`. The log contains `PASS real PS5 dense JIT allocator: alias failure is fatal-to-attempt, no RW/NX fallback or owned-memory leak` and `CORE_PREFLIGHT_ALL_PASS`; other JIT/Vulkan and approved UX source gates are also green.
- This proves the current lightweight host checks, not native PS5 SDK compilation, true direct-memory alias permission mapping, Vulkan driver cache durability on console, full CPU/GPU/RAM utilization or FC27 freeze resolution. Keep sparse JIT disabled in release until those hardware/native qualifications.
- The only commit after the tested source SHA is this `MEMORY.md` status entry, tagged `[skip ci]` to avoid redundant source CI and any native or UI build.

### 2026-10-08 — Follow-up sparse rollback, branch/PR cleanup audit

- Repo default branch is **`fix/0.40-zbic-13.60`**, the shipping/release line (not a literal `main`). Preserve that and developer branch `dev/ps5-sparse-jit`. The latter is ahead of default and remains **not merged/not firmware-tested**. Do not silently rename the default branch.
- GitHub REST inventory found **0 open PRs**. The only PRs #2–#6 are closed/unmerged Dependabot GitHub Actions bumps; the shipping default CI already uses the corresponding SHA-pinned versions (checkout v7.0.1, cache/save and cache/restore v6.1.0, download-artifact v8.0.1, upload-artifact v7.0.1). Do **not** resurrect or force-merge these stale PRs.
- Five remote branches before cleanup: shipping `fix/0.40-zbic-13.60`; active `dev/ps5-sparse-jit`; obsolete ancestors `local/fc27-offline-no-build` (0 ahead/141 behind developer branch) and `wip/final-ui-freeze-audit` (0 ahead/333 behind); and divergent historical `>0.50-bug_13.60` (49 commits ahead/784 behind relative to developer branch). The obsolete ancestors can be deleted once a branch-delete capable authenticated GitHub client is available; **do not delete the divergent branch until its unique commits are reviewed/archived**. No remote branch has been deleted by the GitHub connector in this pass: its available operations cannot delete refs, and Desktop Commander Mac was offline.
- Removed superseded `local/fc27-offline-no-build` trigger from **feature-branch** lightweight source workflow and native build workflow. Native release CI on the shipping branch is unchanged. Developer branch still cannot trigger a native build via push.
- Prototype sparse JIT recovered a previously fatal partial map case in `src/memory_pages.cpp`: after a failed RW map, RX map, or RX permission change **before publishing the new page**, restore both corresponding virtual chunks to `PROT_NONE` via fixed anonymous remap; release the uncommitted physical allocation, preserve prior live code and unchanged accounting, return failure for the already bounded code-cache reuse path. Unexpected mapping addresses or unsuccessful guard restoration still abort (fail-closed); PS5 firmware semantics are unqualified.
- Extended real-source Linux kernel mocks with fault injection for RW mapping failure, an RW/RX syscall failure *after* mapping, execute-permission failure, preserved old executable bytes/owned counts and failed bootstrap cleanup. Source architecture gate asserts rollback branches. Tests and PS5 firmware still require qualification; **normal dense JIT remains unchanged**, and sparse stays developer-only/off.
- Next gates after source CI: native SDK compile of the generated Dynarmic CMake derivative; real fixed-page guard restoration and executing RX alias on FW 13.60; Vulkan driver actual persistence across crashes/relaunch; multi-segment code / branch trampoline design; precise CPU scheduler and unified-memory metrics before performance claims. Continue to avoid new GUI builds and unapproved native full builds.

### 2026-10-08 — Sparse rollback host CI green; dense alias tail audit

- [Host source run #37829448377](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37829448377) **SUCCESS**, including real-source kernel mocks for sparse partial RW, RX, mprotect fault injection, 4 MiB startup bootstrap and physical backing cleanup; `CORE_PREFLIGHT_ALL_PASS` emitted. This is NOT a PS5 SDK or firmware test.
- Extra audit identified dense RX alias teardown ambiguity for **non-2-MiB-aligned requests**. Native `MapExecutableAlias` maps `header.total-header.lead` (large-page rounded), while the allocator's mapping table previously recorded only 16 KiB-page-rounded Xbyak `size`. A 3 MiB request could map 4 MiB but unmap only 3 MiB on destruction. Fixed by `Common::ExecutableAliasSpan` and using the physical-header-derived actual span in successful mapping ownership and failed insertion cleanup. Extended real-header host fixture with 3 MiB -> 4 MiB mapping and a `mincore` unmap test. The very old generated-node native test is not a substitute for firmware qualification.
- Sparse map error diagnostic now emits a real newline. Updated architecture source contracts, documentation and [issue #8](https://github.com/niakw/Prospero.Eden-Encore/issues/8) to remove obsolete experimental 4 GiB "elastic" cache wording, and mark only host/source validation checks complete.
- PRs remain 0 open; all five closed/unmerged Dependabot PRs correspond to SHA-pinned action versions already present on the default shipping branch. The Mac remains offline; no branch deletion is possible via available GitHub connector action, and no risky force-ref rewrite has been attempted.
- **Run host-source tests again after this exact dense alias source change**. No full native PS5 app, firmware game run, frontend render or release merge authorized/claimed.

### 2026-10-08 — Dense JIT actual RX span and full ISA admission-budget audit

- [Host-only CI #37829868820](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37829868820) **SUCCESS** at `0029330cc908`: real header dense-alias injection tests, 3 MiB -> 4 MiB RX alias full unmap, sparse RW/RX/PROT_EXEC mid-map injected failures with inaccessible-guard rollback, universal performance and approved UX gates. This was **not** native firmware/SDK qualification.
- The global `ChooseJitMemoryPlan` floor used 640 MiB, while actual per-ISA four-core baselines A64/A32 are 656 MiB (256/192/192/16 and 512/64/64/16). This could overshoot `admission_budget_bytes` by up to 16 MiB, even before dense allocator overhead. Source policy now computes the exact four-core floor; `check-jit-memory-policy.py` checks both A64 and A32 total capacities against the admitted limit. This remains **a sizing plan**, not evidence the host/GPU can actually commit each allocation under fragmentation, and header/alignment overhead remains separately counted in the dense physical counter.
- Pending source-only CI after the precise floor change; keep PS5 native build, hardware FW 13.60, release promotion and UI rebuild disabled pending explicit user OK. Active branch remains `dev/ps5-sparse-jit`; default release branch `fix/0.40-zbic-13.60` untouched.

### 2026-10-08 — Final host-only PS5-first preflight green

- The final source candidate `569eabb4fc72e632aaec068e9538ad82f4f31d8c` completed [GitHub Actions #37830087702](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37830087702) **SUCCESS**. Workflow logs confirm all-title four-core A64/A32 budget fixture, bounded JIT construction retries, real dense allocator 3 MiB/4 MiB alias cleanup, sparse partial RW/RX/PROT_EXEC rollback host injections, exact derived Vulkan cache saving, and `CORE_PREFLIGHT_ALL_PASS`.
- This proves source/host test coverage ONLY. It is not evidence of native PS5 SDK compilation or actual firmware mapping, shader cache durability, multi-arena trampoline safety, dynamic CPU/GPU RAM rebalancing, FC27 unfreeze, or FPS uplift. The release branch was not touched; no new PS5 app/UI build or hardware execution occurred.
- Following this status-only `[skip ci]` commit, only documentation differs from that green source SHA. PR count 0 open, two obsolete ancestor branch refs remain pending deletion by a ref-delete capable client, and divergent `>0.50-bug_13.60` must first have its 49 unique commits reviewed/backed up. Do not force-update any refs to simulate deletion.

### 2026-10-08 — Latest continuation: only two branches, physical JIT budget and controller Issue #7

- Authoritative GitHub branch check now shows exactly **two remote branches**: default shipping `fix/0.40-zbic-13.60` and developer `dev/ps5-sparse-jit`. `local/fc27-offline-no-build` disappeared from remote during the audit. One-time tightly SHA/ancestry-gated GitHub Actions cleanup attempted to resolve that ref but GitHub answered 404 because it had already disappeared; it did **not** delete anything. The temporary workflow was subsequently deleted from the dev branch. No open PRs; do not recreate superseded branches.
- Removed the stale `local/fc27-offline-no-build` push trigger from developer launcher preview workflow. Its manual `workflow_dispatch` remains available but was not invoked, respecting approved unchanged launcher.
- Dense JIT per-ISA baseline is 656 MiB for four cores but four dense direct-memory allocations additionally commit **8 MiB (4 × 2 MiB)** of physical allocator header/alignment overhead. Corrected global A64/A32 admission formula to deduct those physical bytes from *growth*, so actual planned code capacity plus overhead fits admitted resources. `tools/check-jit-memory-policy.py` now includes all four cores, the four physical headers and near-threshold scenarios. This is an allocation-accounting correction, not a speed gain claim or sparse-JIT shipping authorization.
- Issue #8: strengthened `tools/check-jit-sparse-host.py` so a failed RW, RX or executable-permission mapping leaves the **new uncommitted chunk** inaccessible on both RW/RX aliases (fork/SIGSEGV assertions) while retaining earlier live code and physical ownership. Real PS5 MAP_FIXED/permission behavior remains unqualified.
- Issue #7: added `tools/check-controller-semantic-mapping.py`, compiling actual `headless/button_mapping.h` with PS5/Switch defaults, swapped/custom mappings, invertibility and invalid-key regression. Added to host-only and release source preflights. **No in-game PlayStation artwork/glyph swapping is implemented or claimed**; actual FC27 menu-vs-match behavior remains a separate hardware/game test.
- Updated `docs/PS5_NATIVE_ARCHITECTURE.md` and simplified workflows. Sparse dev option stays disabled by default; no PS5 native app build, UI render, release merge, or firmware 13.60 test performed.
- Pending as of this entry: run all host-source gates on current HEAD; only call them green after inspecting that run, then update Issues #7/#8 with specific results and remaining requirements. Preserve user instruction to keep `MEMORY.md` authoritative.

### 2026-10-08 — Host core preflight success and final branch/issue cleanup

- [Source-only CI #37831190524](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37831190524) **SUCCESS** on `2128fc85a78c`. Logs show passing actual PlayStation/Switch button mapping contract, four-core A64/A32 JIT physical budget including 8 MiB dense allocation headers, real-source sparse RW/RX inaccessible-guard rollback tests, Vulkan serializer and UX-invariant checks; `CORE_PREFLIGHT_ALL_PASS`. No native PS5 app build or firmware test was triggered.
- Both tracked GitHub Issues were updated with exact results and remaining requirements: [#7 controller input mapping vs in-game glyph artwork](https://github.com/niakw/Prospero.Eden-Encore/issues/7) remains OPEN, and [#8 sparse executable JIT/PS5 hardware qualification](https://github.com/niakw/Prospero.Eden-Encore/issues/8) remains OPEN. No issue was marked completely solved without console evidence.
- The branch inventory after cleanup contains **only** `fix/0.40-zbic-13.60` (default release) and `dev/ps5-sparse-jit` (work branch). The one-time cleanup workflow did **not** delete `local/fc27-offline-no-build`: it saw 404 because the branch had already disappeared. The temporary workflow was subsequently removed. Native build workflow and preview workflow no longer push-trigger off that obsolete branch; the latter retains manual dispatch only. Zero PRs open.
- Further `tools/check-jit-sparse-host.py` fault injection now covers *failure of the second physical 2 MiB bootstrap allocation*, after the first was already mapped, requiring full cleanup and zero owned direct chunks. This test is not claimed green until the next source-only CI run.
- Do not promote sparse JIT, multi-arena claims, FC27 freeze fixes or full GPU/CPU resource utilization without PS5 native compilation and actual FW 13.60 testing. The approved launcher interface is unchanged, and no full build was authorized.

### 2026-10-08 — User correction: in-game PlayStation glyph **art**, not input remapping

- User clarified: the sought #7 feature is **visual replacement** of Switch A/B/X/Y glyphs INSIDE the emulated games with PlayStation Cross/Circle/Square/Triangle artwork. The DualSense-to-Switch BUTTON MAPPING was already addressed. Previous mapping-only regression tests are not implementation evidence for glyph visuals, and no mapping was modified in this pass.
- Existing `headless/mods.h` and `main.cpp` already provide a usable LayeredFS/RomFS game-file replacement path per title ID, including a per-mod disable switch. Game-controlled prompts need game-specific texture atlas, font, layout or shader files; no universal symbol injection is defensible.
- Added source-only tooling `tools/ps-glyph-pack.py` for manifest-verified, legally supplied, per-title *in-game graphical* resource packs, with strict supplied title+40/64-digit build ID, RomFS source SHA-256 and replacement SHA-256, path/symlink/duplicate/size rejection, staged non-destructive installation into `mods/<TITLE>/Eden Encore PS Glyphs/romfs/`. Installer leaves original Nintendo content untouched and does not overwrite existing packs or change controller mapping. `tools/check-ps-glyph-packs.py` includes synthetic host fixtures for successful staging and incompatible/malicious rejection; wired into host-only and release source preflights.
- Important LIMIT: verification currently requires a trusted original RomFS dump plus **caller-supplied** running build ID. It does **NOT** determine build ID from the actual active game or auto-disable already-installed packs after updates. No real game's PlayStation atlas is distributed/installed. Thus the all-games visual feature, native integration and per-title display evidence remain **open**. `docs/PS5_INGAME_GLYPHS.md` describes the staged path and explicit remaining gates. Do not claim in-game glyph replacement has occurred.
- No native PS5 app compilation, GUI re-render or game FPS test was requested/performed. #8 JIT feature branch remains developer-only with sparse JIT OFF by default. PR count zero, branches remain only shipping default and developer.
- The new glyph pack tool and its regression checks have not passed source CI yet as of this entry. Re-run on this HEAD before declaring test success.

### 2026-10-08 — Verified in-game artwork pack follow-up and Issue #7 correction

- First [source preflight #37832229876](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37832229876) **SUCCESS** at `b8dd34afae2e`, including synthetic legal PS-glyph RomFS pack verification/install, controller input regression (unchanged), previous JIT/Vulkan gates and approved UX contracts. It does **not** contain real in-game prompt changes or native PS5 qualification.
- The user explicitly corrected scope: #7 is about changing **button glyph DESIGN INSIDE GAMES**, not controller INPUT MAPPING. Updated [Issue #7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) title and priority wording accordingly; mapping regressions remain ancillary tests, not progress toward visible prompt replacement.
- A second audit of the new glyph-pack installer caught a real compatibility problem: the pinned `Mods::TitleFolder` resolves title directories case-insensitively. The installer must reuse an existing lowercase/uppercase title directory, and refuse duplicate/colliding mod names, otherwise a legitimate pack may be installed in a second directory which the game never loads. Fixed `tools/ps-glyph-pack.py` and added fixtures for existing lowercase title folder, case-colliding title variants, and conflicting glyph mod names. Test of THIS refinement awaits the next source preflight.
- `docs/PS5_INGAME_GLYPHS.md` documents manifests, legal requirements, actual LayeredFS install and hard limits. The tool stages legally supplied per-title graphical resources but cannot recognize the running title's build ID independently, nor synthesize game-specific textures. No legitimate per-title replacements are bundled. Automatic safe game/version selection, actual PlayStation artwork in games, delivery, and firmware 13.60 tests remain OPEN in #7.
- Issue #8 remains OPEN for hardware validation of JIT, multi-arena branch trampolines and CPU/GPU unified memory; its source-only checks stay in the preflight. The only two branches are developer and default delivery, with zero PRs open. No native PS5 build, UI preview or merge was launched.

### 2026-10-08 — Verified final glyph pack source gate / issue receipts

- [Host-only CI #37832402204](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37832402204) **SUCCESS** on candidate HEAD `198efe7781e0`, including `PASS legal PS glyph pack manifest`, checked SHA-256 matched original/replacements, mod-directory capitalization/collision handling and existing JIT/Vulkan/UX regressions, ending `CORE_PREFLIGHT_ALL_PASS`.
- Updated Issue [#7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) to make **in-game visual button glyph ART, NOT the previously corrected button mapping**, the explicit priority. The verified game-specific RomFS pack installer/test are a real infrastructure step, but neither a real glyph pack nor automatic runtime build-ID selection exists yet. Do not mark the feature complete; no PlayStation icons have been demonstrated inside FC27 or other running games.
- Issue [#8](https://github.com/niakw/Prospero.Eden-Encore/issues/8) remains OPEN for PS5 JIT firmware qualification, safe multi-arena expansion, unified RAM and CPU/GPU bottleneck measurements. The latest shared source CI checks did not introduce or qualify an SDK firmware build.
- No new renderer UI build, main/release branch merge, game binary delivery, or hardware FPS test. Only final documentation and issue status changed after the green tested candidate.

### 2026-10-08 — Encore-overrides-style visual-button catalogue (user-requested simplification)

- Instead of forcing the user through per-game manual graphic pack selection, the visual glyph pipeline now uses **niakw/encore-overrides/glyphs/manifest.json** as a curated, revisioned title/update/build rule list, beside the existing video profile JSON. This shared catalogue deliberately has **zero falsely supported titles** until real legally supplied and compatible assets exist. Added `tools/sync-glyph-overrides.py`, `data/glyph-overrides.json`, and generated `headless/glyph_overrides_generated.h` snapshot with optional newer `ConfigFile("encore-glyph-overrides.json")` runtime overlay (rejects stale revisions).
- New `headless/glyph_overrides_runtime.h` parses bounded per-game rules and author-installed pack provenance, uses the existing `mods/<title>/Eden Encore PS Glyphs/romfs/` replacement mechanism and rejects absent, mismatched or unknown installed update versions. Embedded rules are tested at launch, *not* by scanning the GPU hot path. In `headless/main.cpp`, added explicit rule-based enabling/disabling of this one graphics mod before `system.Load`, honoring Safe Launch, existing user-disabled mods and existing global Mods switch. A catalogue entry does NOT synthesize textures or change controller input mapping.
- Added a separate JSON presentation style in `headless/settings_store.h`: global `/appearance/ingame_button_glyphs` with `playstation` (preferred/default) or `switch` and a `/games/TITLE/ingame_button_glyphs` override. This is independent of the pre-existing physical DualSense mapping. No frontend layout or graphical settings screen changed.
- Added `tools/check-glyph-overrides-runtime.py` to compile the actual C++ runtime selector on Linux with nlohmann, with unknown/mismatched versions, mod evidence damage, JSON preference persistence and no action remapping; wired lightweight and release source CI. Added offline `tools/sync-glyph-overrides.py --manifest data/glyph-overrides.json --check` reproducibility gate. The tests have **not yet passed CI** as of this entry.
- Major remaining limitation **#7**: a game-specific legal PlayStation replacement atlas/font/layout is still required. The metadata bridge reports a scanned *update display version*, not independent actual loaded NSO build-ID verification; a catalogue-supplied build ID is a declaration, so real in-game behavior is unqualified. The workflow conservatively disables missing/unsupported graphics mods. Automatic pack distribution and native PS5 game screenshots are not complete.
- **#8** PS5 sparse JIT firmware13.60 and GPU/CPU resource optimization still open; no PS5 app build, UI re-render or main/release branch merge. Respect original launcher design, all-games performance and memory policy. Two GitHub branches; zero PR open.

### 2026-10-08 — Glyph-source CI diagnostics

- The first integration [host preflight #37833761194](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37833761194) failed in **Python source generation syntax** at `tools/sync-glyph-overrides.py:56`, before it reached the actual compiled C++ selector. This is not a renderer or PS5 regression. Fixed the generator row construction to ordinary string concatenation at `dd56394cbfd6`; source-only CI must be rerun before declaring the new catalogue green.

### 2026-10-08 — Verified in-game art catalogue after syntax fix; unified Encore sync

- [Host source CI #37833867119](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37833867119) **SUCCESS** at `183575dd8e6e`: source snapshot reproducibility, actual C++20 `glyph_overrides_runtime.h` selector (title/version match, user visual-style setting independent of DualSense input mapping, missing/corrupted mod, Nintendo fallback), synthetic legal RomFS asset staging, JIT/Vulkan checks, and approved UX contracts; log ends `CORE_PREFLIGHT_ALL_PASS`.
- The user explicitly asked for simplicity equivalent to `encore-overrides`. Added `niakw/encore-overrides/glyphs/manifest.json` (curated revision 1, **zero verified titles**, do not invent supported games) and explanatory glyphs README. Added generated `headless/glyph_overrides_generated.h` and `data/glyph-overrides.json` plus a newer-revision runtime JSON override; the same existing `tools/sync-encore-overrides.py --source ...` command now refreshes the glyph catalogue when it syncs video profiles, so no separate required action.
- In-game artwork policy is selected **once at game launch** in `headless/main.cpp`, before `system.Load`, via a verified `mods/<title>/Eden Encore PS Glyphs/romfs/` graphics mod. Unsupported version or absent rule is explicitly disabled; separate `appearance/ingame_button_glyphs` and per-game settings default to PlayStation preferred with Nintendo fallback. No new rendering subsystem or frame-time OCR, no mapping change, no frontend redesign.
- This is NOT automatic generation of replacements: no game-specific PlayStation texture/font/layout is bundled or verified on hardware yet. The scanned update version is NOT an authenticated running NSO build ID. Runtime source layer and compiler source checks require real firmware qualification before claiming actual glyph changes in FC27 or any other game. Issue [#7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) remains OPEN; Issue [#8](https://github.com/niakw/Prospero.Eden-Encore/issues/8) JIT still OPEN.
- The combined-sync tweak and docs/test guard after the green run require another host-only CI pass before their status can be declared green. No native PS5 app, package, UI preview, release merge or firmware 13.60 hardware test.

### 2026-10-08 — FINAL source gate for one-command Encore visual glyph overrides

- Final source-only [GitHub Actions #37834142981](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37834142981) **SUCCESS** at code tested SHA `152d030cb541cd5bb5a5956a5feed00fa95ef6df`. Logs explicitly contain `PASS glyph visual overrides` (generated shared snapshot reproducibility), `PASS real C++ in-game glyph override catalogue` (actual policy and separate visual preferences), `PASS legal PS glyph pack manifest`, and `CORE_PREFLIGHT_ALL_PASS`.
- The customary `python3 tools/sync-encore-overrides.py --source /path/to/encore-overrides` command now refreshes BOTH the existing video performance profiles and the curated `glyphs/manifest.json` visual-art catalogue when available. Optional targeted `tools/sync-glyph-overrides.py --source ...` retains a standalone path. Zero game rules are advertised without actual independently qualified replacement graphics.
- `headless/main.cpp` selects graphic RomFS mod availability at boot, not input semantics or per-frame GPU changes. Unsupported or mismatched game/update version = Nintendo original; a PlayStation preference alone never implies the game's artwork is actually replaced. Visual choice lives in JSON preferences separate from controller mapping. Firmware 13.60, real NSO build attestation, actual prompt atlas assets, automatic delivery, and title-by-title screenshots still remain unverified and belong to open Issue #7.
- Issue #8 remains OPEN for JIT resource architecture and PS5 firmware hardware testing; the final CI is **host-source-only**, no full PS5 build, UX render, release branch merge or real FPS qualification. Current shipping/default branch remains `fix/0.40-zbic-13.60` and active work branch remains `dev/ps5-sparse-jit`; no other branches or open PRs are intended.
- Following this status-only `[skip ci]` commit, the most recent source CI success still covers all code modifications.

### 2026-10-08 — Remove cheat Build ID dependency from visual glyph rules (pending CI)

- User rightly questioned requiring EdiZon / per-installation Build ID. Distinction: an NSO executable Build ID is associated with its executable build/version, not each player, and can change with updates; **RomFS graphic compatibility should instead follow title/version and the original graphic file's fingerprint**. No user should run EdiZon to enable game artwork.
- Promoted curated `niakw/encore-overrides/glyphs/manifest.json` to schema **2**, revision **2**, keeping **zero unverified game entries**. Synced Eden `data/glyph-overrides.json` and `headless/glyph_overrides_generated.h` to v2; `tools/sync-glyph-overrides.py` now emits `title_id + update_version` only. The existing combined `sync-encore-overrides.py` workflow remains. Updated shared source README and `docs/PS5_INGAME_GLYPHS.md`.
- `tools/ps-glyph-pack.py` now requires original/resource SHA-256, Title ID and author-selected update display version; **no --build-id** and no program/executable-specific assumptions. Staged provenance schema **2**; `headless/glyph_overrides_runtime.h` matches update rather than a declared NSO Build ID, still rejects unknown updates, malformed pack metadata and missing files. It additionally checks SHA-256 declaration format and rejects nested symlinks out of installed graphic directories. Synthetic installer and C++ runtime fixtures updated (version mismatch, bad update labels, symlink parents).
- Native launch metadata now calls `eden_game_glyph_display_version`, not `eden_game_addons` alone: if an update was scanned use its known version; if none exists read `RawNACP.version_string` from the selected base game's control.nacp. If the scanner did not finish, an installed update version is unreadable, the source file is missing, or the NACP version is invalid, the feature must **fail closed to original Nintendo artwork**. The actual pinned `RawNACP.version_string` field was confirmed in the pinned Eden source. The game scan is initiated by EdenServices home/library and may be missing when setup is not ready; fail closed. Added source-integration assertions to `tools/check-glyph-overrides-runtime.py`.
- IMPORTANT UNFINISHED: These are mostly **source/host tests**. Native SDK compile on FW13.60 and active effective RomFS byte fingerprint comparison, game-specific legal graphic packs (currently none), and automatic asset distribution are not proven. The display version is not cryptographic proof of a loaded binary; ignore the program Build ID for this *graphic* use case, but revalidate original asset fingerprint at native load before making strong compatibility claims. Issue #7 remains OPEN; issue #8 JIT/FPS remains OPEN. No console app/GUI build or branch merge.
- All v2 changes above **pending** new `[core-ready]` host-source preflight at this note; do not report green until log and job success confirmed.

### 2026-10-08 — v2 game-art host preflight green, all-title JIT cap redistribution next

- [Source-only GitHub Actions #37835534460](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37835534460) **SUCCESS** on candidate `59e3c3c32eb1`: visual glyph schema v2 without EdiZon/Build ID, original/replacement RomFS asset SHA test, title/update version and separate controls, native metadata source anchor, bounded shader/JIT checks, `CORE_PREFLIGHT_ALL_PASS`. This did **not** compile the PS5 native NACP reader or render in-game artwork.
- Issue [#7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) now reflects v2, no user Build ID, automatic base-game NACP / scanned update display version detection, and absent legal per-game glyph atlases / no effective RomFS live-original fingerprint gate. Remains OPEN.
- Additional universal A64/A32 optimization for Issue #8: source planner `headless/experimental_performance.h` now reassigns only the large-page-aligned **clamped surplus** from any guest worker's 1536 MiB addressing ceiling to other active-ISA worker arenas, without increasing overall 4-core physical budget or reintroducing FC27-only tiers. Each cache remains immutable during a session, growth still uses bounded retries, and physical overhead 4 × 2 MiB remains counted.
- Expanded `tools/check-jit-memory-policy.py`: monotonicity and budget checks in every 2 MiB increment across up to 15 GiB available physical memory, plus A32 core0/1 and A64 multi-core cap regression. Host source tests are NOT the same as firmware performance qualification; real FC27 freezes/FPS still unproven.
- `docs/PS5_NATIVE_ARCHITECTURE.md` records the change. `tools/check-ps-glyph-packs.py` CI pass message corrected from obsolete `title/build` wording to `title/update`. Following this note, a **new** host-only `[core-ready]` CI run must validate the JIT surplus optimization and updated tests. No PS5 native full build, launcher re-render, release merge or PR cleanup required; active branches still shipping + development.

### 2026-10-08 — Capped JIT reallocation green; v2 native glyph base metadata parser host gate

- [Host-only CI #37836045236](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37836045236) **SUCCESS** at tested source `1952686a4ed8`. Logs include `PASS shared JIT memory policy` (all-title A64/A32, monotonic at 2 MiB granularity, cap surplus spread, 8 MiB physical header overhead), `PASS glyph visual overrides`, `PASS real C++ in-game glyph override catalogue`, `PASS legal PS glyph pack manifest: verified title/update/original+replacement SHA256`, and `CORE_PREFLIGHT_ALL_PASS`. No PS5 SDK/native or gameplay testing was performed.
- Replaced the previous **11+ KiB chronologically contradictory issue #7 body** with a current concise statement: user wants in-game ART, not controller remapping; shared schema v2 does not require a Build ID or EdiZon; zero real graphical packs are yet qualified. Issue #8 body similarly refreshed with latest JIT capped redistribution, remaining console and GPU/RAM/FC27 validation gates. Both remain **OPEN**, no false "fixed" declarations.
- Isolated `headless/glyph_version.h`: source helper to decode the pinned `RawNACP.version_string` for a base game's version, bounded 16-byte field, printable ASCII only, null-terminated or full length, fail closed on malformed input. Used by `headless/metadata_bridge.cpp` and covered in actual C++ source-host fixture `tools/check-glyph-overrides-runtime.py`; the new C++ byte fixture was normalized to `'\\x01'` rather than a multicharacter literal. **Run CI again** for this final helper; no PS5 SDK compile done.
- Default release branch `fix/0.40-zbic-13.60` still untouched; developer branch `dev/ps5-sparse-jit`. No full PS5 build, UX render or PR merge. Details in docs/PS5_INGAME_GLYPHS.md and docs/PS5_NATIVE_ARCHITECTURE.md.

### 2026-10-08 — FINAL source-only green gate (no Build ID and universal JIT budget)

- [GitHub Actions #37836509250](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37836509250) **SUCCESS**, source-tested SHA `7329fa7c9bcb091dccef04fd3c4a42579654a19a`. Job and logs show `PASS glyph visual overrides`, `PASS real C++ in-game glyph override catalogue`, `PASS legal PS glyph pack manifest: verified title/update/original+replacement SHA256`, `PASS shared JIT memory policy`, `CORE_PREFLIGHT_ALL_PASS`.
- New `headless/glyph_version.h` is compiled and exercised by the C++ host fixture: valid/empty/invalid NACP control display versions, including a full 16-byte non-null-terminated field. Real native `metadata_bridge.cpp` consumes that same source helper; PS5 SDK/game compile remains untested. There is **no user-supplied NSO Build ID or EdiZon dependency** anywhere in the v2 glyph rule path.
- Latest host policy suite covers 2 MiB granularity and redistribution of otherwise capped guest JIT capacity for both A64/A32 within same physical reserve. This is a source capacity improvement, NOT proven FPS gain or hardware unfreeze.
- Both GitHub Issues [#7 visual game glyph artwork](https://github.com/niakw/Prospero.Eden-Encore/issues/7) and [#8 PS5 JIT/GPU/native qualification](https://github.com/niakw/Prospero.Eden-Encore/issues/8) have been replaced with current readable authoritative checklists, free of obsolete/contradictory mandatory Build ID and stale feature claims; both remain OPEN.
- No PS5 native full build, GUI redesign, firmware 13.60 test, title artwork extraction/distribution, or release-branch promotion was attempted. This concluding `[skip ci]` documentation commit differs from tested HEAD only in MEMORY.md.

### 2026-10-08 — Real glyph replacement asset digest verification (new source gate)

- Audit of Issue #7 found an actual correctness hole: runtime `GlyphOverrides::EvidenceMatches` verified pack metadata, path presence, SHA-256 *string format* and symlinks, but **never hashed the installed replacement file at launch**. A modified artwork file could still be enabled. This is now fixed with a bounded streaming SHA-256 over real installed bytes in new `headless/glyph_sha256.h`; integration in `headless/glyph_overrides_runtime.h` compares each replacement file digest with the staged artist-pack `replacement_sha256`. No per-frame reads, 32 KiB I/O chunks, 128 MiB per-file ceiling, rejects partial reads and mismatches.
- Expanded source-host C++ `tools/check-glyph-overrides-runtime.py` with independent standard SHA-256 vectors for empty input, segmented 'abc' and one million 'a', a genuine installed-atlas digest and a post-install same-path file tampering test. Missing, too-large, mismatched artwork fails closed to original Nintendo visuals; the base RomFS's actual effective version/file digest after patch layering is **still not attested**, catalog signing/automatic distribution remains open, no real compatible PlayStation art yet.
- This is an integrity improvement for genuine configured packs, not evidence that actual game glyph art is shipped. Source-only preflight still needs to validate newly added code. All build/firmware 13.60, screenshot and FC27 freeze/performance qualification remain unchanged and OPEN in issues #7/#8. Never imply the PS5 native launcher was built or tested.

### 2026-10-08 — Glyph art-integrity and ambiguous-mod collision audit (second source gate)

- First source-only [#37837138796](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37837138796) **SUCCESS**, including real C++ SHA-256 known vectors and post-install texture tamper rejection. Earlier runtime only checked declared SHA-256 formatting and file presence; the code now reads and **hashes the installed replacement bytes**, once before loading a game, 32 KiB streaming buffers, no GPU hotpath or unbounded file buffering.
- Additional fail-closed hardening added after the first green source CI: limit cumulative verified pack bytes to **512 MiB** and any asset to **128 MiB**, matching the original installer and preventing gigabytes of read/hashing at launch due to a malicious edited manifest. Added constant-time C++ budget predicate and fixture validating boundary/overflow, plus a 1,000,000-byte real on-disk file hashing test against independent SHA-256 known vector.
- Another actual ambiguity: Eden's `Mods::TitleFolder` resolves Title IDs case-insensitively and mod folders sort by case-sensitive name. Multiple case-colliding title folders or multiple differently capitalized `Eden Encore PS Glyphs` mods could apply graphics in an uncertain order. The selector now refuses duplicated title folders and mod names, and disallows title/mod symlinks; synthetic host tests cover these cases.
- **Scope**: This secures the replacement file present in `mods/`, but does not prove Nintendo's *original* RomFS bytes in the active game after updates, nor authenticate an unsigned external catalogue; a race to swap files between hash check and emulator overlay is still possible. No actual per-title PlayStation artwork has been published. Issue #7 remains OPEN. Issue #8 and native PS5 FW 13.60 performance/FC27 freezes remain OPEN.
- This group of *new* changes is pending a fresh source-only `[core-ready]` CI. No native SDK, full PS5 app build, UI redesign, release merge or hardware game tests performed.

### 2026-10-08 — FINAL source-only validation of installed in-game glyph artwork integrity

- Latest [source-only GitHub Actions #37837534296](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37837534296) **SUCCESS** for all technical changes at `3adc1707d5a487990eba5a32d630b43db16d96b8`. Host CI compiled the actual C++ `glyph_overrides_runtime.h` and SHA-256 implementation (independent known vectors plus 1 MiB real file); verified bytes tampered after staging are rejected; checked 128 MiB per-file/512 MiB aggregate cap, filename/title collisions and symlink trees; existing JIT A64/A32 policy, sparse memory fault injection and UX contracts all passed. Log ends `CORE_PREFLIGHT_ALL_PASS`.
- The once-per-game launch SHA-256 of **the installed replacement graphics**, not the true effective original game asset after update layering, is now sourced in `headless/glyph_sha256.h`; docs/PS5_INGAME_GLYPHS.md and Issue #7 describe accurate trust boundaries (unsigned manifest may be rewritten; disk TOCTOU; PS5 SDK/final game asset validation pending).
- Post-tested source changes consist only of documentation and GitHub Issue updates with `[skip ci]`. There remains **no PlayStation glyph artwork pack qualified for any actual game**, no automatic remote pack delivery, no PS5 firmware13.60 build or FC27 menu/match screenshot. Sparse JIT OFF by default; Issue #8 remains OPEN on actual hardware RAM/GPU/JIT/FC27 freezes. No full PS5 native build, UI preview, release merge or branch creation.

### 2026-10-08 — Developer in-game GPU stall observation for FC27 (host gate pending)

- Specific Issue #8 diagnostic hole: the existing `headless/stall_watchdog.h` watchdog was **disarmed immediately after `system.Run()`**, observing stalled boot stages but not FC27's **in-game** freeze. Added separate `headless/game_liveness.h` pure C++ `Probe`, sampled **only on the existing once-per-second watchdog thread**, never instrumenting JIT blocks/GPU frame hotpaths. Starts after `system.Run()`, stops at game completion/teardown via explicit DisarmGame and scope guard.
- Watch uses existing developer `Performance::gpu_dispatch.calls` and `rasterizer_draw.calls` counters. It needs evidence of a counter **change during this session** before reporting; if counters are absent/unavailable, records nothing, avoiding false claims. After **30 seconds** without *new counted GPU work*, emits `EDEN_GAME_GPU_STALL_SUSPECT` including dispatch/draw counts, GPU queue-full, guest sync wait and each guest CPU phase; repeat every ~30 sec with **max four reports total per game**, resetting delay after resumed progress. Does **not** exit/restart the game; menu pause or suspended presentation may also look idle, so these are suspects, not proof of bug cause.
- Only exists inside `EDEN_DEV_PROFILE && PS5_NATIVE` guarded header, with no additional per-frame work or shipping change. `tools/check-game-liveness.py` compiles actual portable policy on Linux and checks 30-second threshold, no GPU counters => no suspect, per-incident recovery, monotonic clock anomaly, cap four per session and source-side arming/disarming. Added lightweight and native release source preflights; **no firmware build/test yet**.
- Existing rasterizer/GPU counters must be confirmed to advance on the selected Vulkan/OpenGL backend before trusting negative diagnosis; no GPU activity report ≠ confirmed freeze. Source-only test awaiting next `[core-ready]` CI. No PS5 native build authorized and Issue #8 stays OPEN.

### 2026-10-08 — In-game GPU watchdog source gate green; strengthen native header check next

- [Host source CI #37838362140](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37838362140) **SUCCESS** at `d3c28dadc8f9`: `PASS developer-only in-game GPU liveness`, existing A64/A32 JIT, sparse/dense memory, glyph art SHA and UX regressions, `CORE_PREFLIGHT_ALL_PASS`. Device-only sessions are now excluded from the developer in-game watcher.
- Instrumentation supports **suspected** GPU progress stalls only after at least one GPU draw/dispatch count changed during this game, then 30 seconds of still counters; max four reports per game, non-shipping and no automatic restarts. The existing boot watchdog used to stop at game start; this is a separate opt-in developer diagnostic for **FC27 freezes after match start**, not evidence of a fixed freeze.
- Added stronger second-level host test to `tools/check-game-liveness.py`: compile **the actual** `headless/stall_watchdog.h` under `PS5_NATIVE=1, EDEN_DEV_PROFILE=1`, using real `headless/performance.h` plus tiny upstream CPU clock header stub; avoids linking/running SDK functions. This test and updated main.cpp game-only arming are **PENDING a fresh `[core-ready]` CI**. Docs/PS5_NATIVE_ARCHITECTURE.md updated with limits and log format.
- Firmware 13.60 native build/gameplay still NOT run. Actual vendor GPU counter instrumentation must be confirmed live; an alert can also be a deliberate pause, and absence of an alert is not evidence of no freeze. Issue #8 remains OPEN, #7 visual art/source compatibility still OPEN, release branch unchanged.

### 2026-10-08 — Final developer GPU stall host C++ compilation PASS

- Latest [GitHub Actions source-only CI #37838676286](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37838676286) **SUCCESS**, tested source HEAD `aa92b5d91ffdbc200f72c0a52c6594c42c75253c`. The logs explicitly say `PASS developer-only in-game GPU liveness: 30s threshold, four reports, no counters -> no false alert`, `PASS real PS5/DEV watchdog header compiles with host-only stub of pinned CPU clock`, and `CORE_PREFLIGHT_ALL_PASS`. All existing glyph SHA, A64/A32 JIT allocator and source UX gates also completed green.
- Unlike previous source-only regex coverage, the **real** `headless/stall_watchdog.h` is now compiled in `EDEN_DEV_PROFILE=1,PS5_NATIVE=1` mode on Linux, against the existing `performance.h`, with ONLY an upstream missing clock-header stub. This is NOT a complete PS5 SDK native compilation or console runtime validation.
- The actual in-game GPU counter monitor is armed only for game sessions, begins after `system.Run`, is stopped before tearing down the guest and guarded by scope exit for exceptions. A healthy game increments GPU dispatch/draw counts; if counters never advance the monitor abstains, and if previously observed counters stall for 30 sec it emits bounded **suspect-only** diagnostics (max 4), no automatic title restart.
- Remaining Issue #8 gates: actually build/run on PS5 FW13.60, confirm Vulkan/OpenGL GPU counters are instrumented and productive, capture real FC27 match freeze and determine guest CPU IPC/gpu queue root cause, fix and test. Issue #7 still needs real title-compatible PlayStation atlas packs and content authenticity. No full native app build or UI render attempted; shipping default branch untouched. The post-green commit updating MEMORY/issues is documentation only, `[skip ci]`.

### 2026-10-08 — Third-pass correctness: bounded glyph config, zero-overhead unsupported titles, watchdog session epochs (CI PENDING)

- Inspected the actual HEAD in `dev/ps5-sparse-jit`, including `headless/main.cpp`, `glyph_overrides_runtime.h`, `metadata_bridge.cpp`, `stall_watchdog.h` and JIT memory policy. Found **three real source-level correctness/efficiency problems** overlooked by earlier green CI:
  1. `GlyphOverrides::ReadBounded` checked JSON `file_size` then performed an **unbounded** `std::istreambuf_iterator` read. Under concurrent JSON growth/replacement it could allocate arbitrarily beyond the 128KiB input cap. Replaced with a 4KiB chunked read that refuses any bytes beyond the limit, rejects I/O error, and rechecks final size. New C++ fixture tests exact boundary, oversized, symlink, empty file.
  2. `main.cpp` always read the game's NACP/control RomFS for glyphs **even when no title rules or files existed** (currently the shared catalogue has ZERO qualified games). Added `GlyphOverrides::NeedsGameVersion`: require an eligible installed graphics mod and curated title rule, with PlayStation visual mode requested, game mods enabled, not Safe Launch nor already manually disabled. Only then call the expensive NACP metadata bridge; source and actual C++ tests protect the absent-rule, absent-mod, disabled-style path. The catalogue remains install-only; no per-frame work or mapping changes.
  3. In rapid back-to-back launches, the developer in-game GPU watcher could miss the `game_armed=false` window between its 1Hz samples and carry stale previous-title counters into the next title. Added `game_session_epoch`, incremented on every `ArmGame`, so Loop resets `GameLiveness::Probe` for every new title regardless of missed disarm edge; upgraded host fixture to compile/link/execute real developer watchdog header using tiny upstream CPU clock stub.
- Also fixed `LoadCatalogue` equal-revision ambiguity: local JSON now requires strictly **higher** revision than compiled snapshot, not `>=`, with a host regression for conflicting same-revision rules.
- Docs/PS5_INGAME_GLYPHS.md updated. New source-only `[core-ready]` CI must run before claiming PASS; no PS5 full native app build, UI re-render, release merge or real game artwork/FPS proof. Issues #7 and #8 both remain OPEN.

### 2026-10-08 — C++ glyph fast path/JSON cap CI retry after harness syntax mistake

- Source-only [GitHub Actions #37839447937](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37839447937) **FAILED ONLY due to a newly introduced Python syntax typo** in `tools/check-glyph-overrides-runtime.py` line 36 (assert expression split across lines without parentheses). `tools/check-game-liveness.py` **PASSED**, including host-link/execute of real DEV/PS5 watchdog header with session epoch. The core C++ glyph test did not execute in this failed run. Fixed the syntax in `552d9687cf78`; do not call this run green.
- Further native metadata audit: `eden_scan_addons()` left `UpdatesScanCompleted=false` whenever the `updates/` directory did not exist. For users with no updates directory, this wrongly blocked **all base-game NACP glyph rules**. Now treats an errno-free, verified ABSENT directory as an empty successful update scan; an unreadable/permission denied folder still fails closed. Also parses .xci case-insensitively for mixed-case extensions. Added guarded source invariants to the glyph host test. The C++ runtime no-rule NACP fast path and bounded JSON reading remain unchanged from previous note.
- This latest code requires a **new source-only `[core-ready]` CI**. No PS5 SDK build, console gameplay, JIT tuning, UI redraw or default branch merge was performed. Open issues #7, #8 remain active; avoid claiming actual glyph art rendered or frozen FC27 repaired.

### 2026-10-08 — THIRD PASS VALIDATED: no all-game NACP tax, bounded JSON, quick-switch liveness

- Final [source-only GitHub Actions #37839664421](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37839664421) **SUCCESS** on tested code SHA `9f0f85d995b36708f8cf3de5f1915f50b95eaa60`. Relevant logs: `PASS developer-only in-game GPU liveness`, `PASS real PS5/DEV watchdog header host-links and runs session-epoch reset check`, `PASS real C++ in-game glyph override catalogue`, `PASS legal PS glyph pack manifest`, `PASS shared JIT memory policy`, ending `CORE_PREFLIGHT_ALL_PASS`. The preceding CI #37839447937 had failed due to a Python syntax mistake in a new test, fixed before this green run.
- Core correctness fixes proven in actual source-host C++: bounded `ReadBounded` external manifest reading (4KiB chunks) preventing file growth beyond stat-time size, input size boundary/symlink/empty fixture; `NeedsGameVersion` no-container-read fast path for unsupported/absent/disabled art (critical while zero games verified); strict newer-revision JSON policy; `game_session_epoch` correctly resets developer 1Hz GPU progress probe across rapid consecutive launches.
- Native `eden_scan_addons` metadata recognizes **truly absent `updates/` folder** as an empty successful scan (not as an unreadable installed update) and handles mixed-case `.xci` extension, with source contract checks; this part has source-only checks, NOT native SDK build or real firmware test.
- GitHub Issues [#7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) and [#8](https://github.com/niakw/Prospero.Eden-Encore/issues/8) updated with exact work, earlier failed preflight and new correct green source checks. Both remain OPEN: real game PlayStation texture atlases, effective RomFS integrity, native PS5 13.60 compilation/qualification, JIT/VRAM/CPU occupancy and FC27 freeze cause remain unresolved.
- No PS5 app build, home UI redesign/run, main/delivery branch merge, game artwork pack distribution or true frame-rate measurement performed. Documentation-only `[skip ci]` commit after tested code preserves last CI code SHA.

### 2026-10-08 — Strict pre-native-build audit with user-authorized Mac tests

- User asked whether the emulator was truly ready **before a build** and authorized access to their ARM64 Mac **for TESTING ONLY, no commits on Mac**. Connected Desktop Commander online Mac, created a disposable shallow test checkout at `/tmp/eden-prebuild-audit.M6cSGy/repo`, never touched the owner's active project files and never committed/pushed on Mac. Git status stayed 100% clean; all GitHub source edits separately used the connected GitHub connector on `dev/ps5-sparse-jit`. User-facing UI and shipping branch unchanged.
- **Critical source race found and corrected**: `headless/metadata_bridge.cpp` had globally shared `ScannedAddOns() std::map` and completion boolean mutated in `eden_scan_addons` while `eden_game_addons`, `eden_game_language`, `eden_game_glyph_display_version` read them with no lock. Concurrent library scan + game launch was UB/crash-risk. Added `ScannedAddOnsMutex()` for short snapshot read/publication, build local std::map off-lock then `swap` once successful; the readers copy under lock, and unreadable scan fails closed. Added independent `ScanAddOnsJobMutex()` to serialize concurrent scan jobs, preventing stale scan superseding newer. Actual registry source declarations extracted and compiled by new `tools/check-addon-snapshot-host.py`, stress-tested on Mac with 3 readers + 3000 successive published update versions. Source review still needed on pinned native compiler, as this is only a host gate.
- Mac discovered default filesystem was case-insensitive APFS: old Python/C++ glyph collision tests falsely assumed one could create a second uppercase Title ID directory and might delete the genuine alias. Fixed **test-only** case-sensitive vs case-insensitive branches in `tools/check-ps-glyph-packs.py` and `tools/check-glyph-overrides-runtime.py`. Mac also revealed that its installed default macOS27 SDK had a newer `.tbd` format than its linker supports. Process-local `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk` allowed host C++ tests without any SDK installation/change.
- Mac ARM64 cannot execute x86 `__builtin_ia32_pause` DEV watchdog tests and lacks Linux-only sparse JIT mock `memfd_create` and `MAP_FIXED_NOREPLACE`. `tools/check-game-liveness.py` executes portable liveness on Mac, **cross-compiles** real PS5 watchdog header for x86_64, and continues link+execute on Linux/x86 host. `tools/check-jit-dense-alias-host.py` mocks the REAL host VM page size (16KiB on Mac vs 4KiB Linux) and keeps Linux-only `mincore` RX unmapped-tail check; portable mock JIT alias ownership/executable map failure passed on Mac. Source tests on Linux still necessary for sparse kernel fault injection.
- **Independent Mac regression sweep 9/9 PASS at GitHub source commit `1a8f4171ab738e1d2fbaca825306aad703288a96`**:
  `check-addon-snapshot-host.py`, `check-glyph-overrides-runtime.py`, `check-ps-glyph-packs.py`, `check-game-liveness.py`, `check-jit-memory-policy.py`, `check-jit-dense-alias-host.py`, `check-jit-startup-retry.py`, `check-vulkan-cache-atomic.py`, `check-controller-semantic-mapping.py`. MAC_TEST_FAILURES:0, TEMP_REPO_STATUS:0.
- Both light `encore-core-preflight.yml` and deliberate native `build-040-zbic.yml` source gates now execute the new concurrency stress check. **The final combined GitHub source-only CI on these new changes was not yet run when this entry was written**; require green `[core-ready]` CI and inspect logs before declaring readiness for a controlled native compile attempt. No native PS5 SDK/CMake build, console tests, FC27 freeze reproduction, shader physical performance, image/art replacement in any actual game or release merge were done. Issue #7 (glyph assets) and #8 (JIT/PS5 qualification) OPEN. Mac 9/9 PASS is NOT a warranty of PS5 native build success.

### 2026-10-08 — FINAL pre-native-build gate: Mac 9/9 + Linux source CI SUCCESS

- **Authoritative tested code SHA `836bf7fc8d8045478bcf9f62128621b5456ea901`** on `dev/ps5-sparse-jit`. [GitHub Actions source preflight #37841938131](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37841938131) **SUCCESS**. Logs include:
  - `PASS real C++ update registry: lock protected readers, serial scans, snapshot publication under 3 concurrent readers`
  - `PASS real C++ in-game glyph override catalogue`
  - `PASS real PS5 dense JIT allocator: alias failure is fatal-to-attempt, no RW/NX fallback or owned-memory leak`
  - `PASS sparse PS5 direct-memory mocks: alias/bootstrap/growth/OOM/partial-map rollback/cleanup`
  - `PASS shared JIT memory policy: all-title A64/A32 monotonicity, guard, alignment, reset`
  - `CORE_PREFLIGHT_ALL_PASS`, including existing UX and source-diff checks.
- Independent **ARM64 Mac host regression suite: 9/9 PASS**, including metadata snapshot concurrency, graphic glyph selector + pack, developer GPU liveness, A64/A32 JIT memory, dense alias with host page-size correctness, JIT startup retries, Vulkan cache atomicity and DualSense/Switch controller mapping. Temp test checkout **under `/tmp` unchanged and clean**; no commit/push whatsoever on the Mac; source commits exclusively via GitHub connector. Test environment only selected an already installed macOS26.5 SDK with `SDKROOT` because default macOS27.0 linker/SDK mismatch. Mac watchdog native header x86 cross-compiled, not executed on ARM; sparse PS5 Linux-only mock run validated in Linux CI.
- Real source crash hazard removed: concurrent read/write on global `ScannedAddOns std::map` while a library update scan overlaps title launch. Fixed serial scanner lock, local snapshot build and short atomically published map under reader lock, protected `eden_game_language`/`eden_game_addons`/`eden_game_glyph_display_version`. This path is source+host-tested; full native SDK compilation still to be attempted. No PS5 SDK workflow dispatch/full compile has been run here.
- Issues [#7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) and [#8](https://github.com/niakw/Prospero.Eden-Encore/issues/8) updated with the pre-build gate and remaining native/hardware work. **Readiness judgment**: all AVAILABLE source and independent Mac host gates PASS; acceptable to initiate a monitored *native build attempt* only when user requests it, with cache/stage-resume and no publication. Cannot guarantee native PS5 SDK compilation or runtime, nor assert FC27 freeze resolved, visual glyph replacements ready, or actual FPS gains. Approval of UI preserved; default shipping branch untouched.

### 2026-10-08 — Controlled PS5 native run launched; first pre-build gate failed; repaired and retrying

- User explicitly approved running the GitHub PS5 native build, no GitHub Release or shipping branch changes, no Mac-originated commits. GitHub connector does not offer `workflow_dispatch`, so dev branch was explicitly added to the native workflow's push branch filter and a `[full-build]` commit was used for a one-shot developer build. The workflow's build-job guard still ignores ordinary commits; **the release job now additionally requires the shipping ref**, so a dev build cannot publish a Release even if a future marker or dispatch is wrong.
- First native workflow [#37842678825](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37842678825) on `f1c3e0d3fe69` **FAILED DURING SOURCE PREFLIGHT**, before `make prepare`, native C++ or app staging. Compiler/toolchain/Meson/install+cache/dependency metadata checks passed, as did glyph asset SHA/JSON catalogue, update-registry concurrency host, A64/A32 JIT memory, dense alias, sparse fault mocks, Vulkan, network, logs and UX. **Exact failing script**: `tools/check-release-hotpath.py` asserted `'if(PS5_NATIVE)' not in section` over a CMake segment that now legitimately contains an all-game, production `if(PS5_NATIVE)` JIT allocation retry AFTER the `if(EDEN_DEV_PROFILE)` sampling block. This was an overbroad test, **not evidence that release JIT profiling was enabled**.
- Corrected `check-release-hotpath.py` to split that section at the specifically marked `# Do not silently lose a game` all-game JIT fallback, reject PS5-native code inside the earlier DEV-only profiling region, and assert the real `JitStartup::ConstructWithCapacityFallback` is still present in the later native section. Retains shipping hot-path protection while accepting legitimate native memory correctness changes.
- Following this note a new `[full-build]` commit starts the next controlled native job with `publish=false` semantics. Avoid touching `dev/ps5-sparse-jit` while the workflow is running: its concurrency group is `cancel-in-progress:true`; new dev commits, even skipped jobs, can cancel the active native job. No executable/PS5 artifact exists from the failed first attempt.

### 2026-10-08 — Second native build failed in Vulkan CMake derived-source generator; fixed for retry

- User correctly flagged RED status in GitHub and requested active reaction. Native build [#37843116788](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37843116788) on `9f20665fa1d5` completed all source validations, packaging preflight, `make prepare`, PS5 OpenGL/mesa SDK preparation and substantial dependencies, **then FAILED while staging native app** at CMake configure `headless/vulkan.cmake:4`: `tools/prepare-vulkan-port.py:1020 RuntimeError: Shader pipeline anchor changed: u32 cache_version) try {`. This was not a console binary compilation or user UI failure: the same generator had already rewritten the pinned cache serializer from `u32 cache_version) try {` to a **transactional** `u32 cache_version) {\n#ifdef PS5_NATIVE` above in the same script, so the *later* `shader_costs` instrumentation wrongly looked for the original signature after it had been eliminated.
- Fixed `tools/prepare-vulkan-port.py` to insert `Eden::Performance::VulkanTimer(18)` at the **post-rewrite final serializer signature**, preserving transactional .new flush/rename+rollback. Added an independent AST/real literal transformation-order test inside `tools/check-vulkan-pipeline-persistence.py` that reproduces the rewrite and fails if the *later* timer anchor does not appear exactly once; catches this before an expensive CMake/configure. Old Vulkan pipeline cache atomic C++ test retained.
- The failed run's **~2.86 GiB dependency/ccache snapshot was saved** with key `prospero-eden-encore-040-Linux-09d8585e66f81caae8fb4809ac86b7972d1a50db98350d71e530ca2e086f9039-37843116788`; use normal restore-key prefix for the next controlled full build. No staged app artifact exists from this run. No native binary was produced. No UI changes, no shipping branch merge, no published release, no Mac-side commits.
- Mac testing is currently unavailable (remote desktop device offline). Require the Linux source-only gate testing the new Vulkan patch-order regression before the next `[full-build]` controlled developer run; once green, follow native compilation to the next REAL failed stage and correct precisely rather than guessing. Keep Issues #7 and #8 open until hardware/gameplay qualification.

### 2026-10-08 — Third controlled PS5 build, Vulkan generator-order source gate GREEN

- [Core source CI #37843933337](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37843933337) **SUCCESS** after adjusting `prepare-vulkan-port.py` Vulkan cache serializer timer to use the generated transactional function signature. New `check-vulkan-pipeline-persistence.py` test statically evaluates the real AST literal `vulkan_cache_save_replacement` and `shader_costs` and confirms the timer anchor is present **exactly once after the earlier rewrite**, that the timer is injected before the PS5 branch, and that atomic rename persists. This addresses exact generator mismatch from native build #37843116788 without weakening fail-fast anchors.
- Launch next GitHub native PS5 workflow using this `[full-build]` commit on `dev/ps5-sparse-jit`, without publishing a Release and without touching shipping default. Restore already-saved dependencies/build caches; do not rename working artefacts or restart native build manually outside CI. Follow the native stages and fix first observed generator/SDK errors. This records launch intent only; do NOT claim a compiled app until native job and artifact are actually confirmed.
