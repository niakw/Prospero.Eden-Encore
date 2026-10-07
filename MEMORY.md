# Eden Encore — Project Memory

> Continuity file for work on `niakw/Prospero.Eden-Encore`.
> Read this file before changing architecture, UX, build/release behaviour or performance policy.
> Keep it concise but authoritative. Update it whenever a project-level decision changes.

## Repository / branch

- Repository: `niakw/Prospero.Eden-Encore`
- Active branch: `fix/0.40-zbic-13.60`
- PS5 title ID: `PPSA99008`
- Current release line: Encore R1 / package `01.000.041`
- Local working tree used from the Mac: `/Users/admin/Downloads/Prospero.Eden-Encore-legal-pass`
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
- original deterministic procedural launcher SFX, no ElevenLabs dependency;
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
