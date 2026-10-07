# Eden Encore — Project Memory

> Operational checkpoint for repo work. Keep this file current whenever a release/build/runtime decision changes. Do not rely on chat history alone.

## Authoritative repo state

- Repository: `niakw/Prospero.Eden-Encore`
- Active release branch: `fix/0.40-zbic-13.60`
- Target console/firmware: PS5, firmware 13.60.
- Current release family: Encore R1 / title ID `PPSA99008`.
- User requires execution-first repo work: inspect/modify/build/validate, not only recommendations.
- Keep branch/run churn low: group related fixes into one coherent commit so GitHub concurrency does not cancel useful runs.

## Build/runtime checkpoints — 2026-10-07

### Last hardware-bootable reference

- Build run **#180**: `37615269357` — CI fully green and used as the last known bootable reference before the regression below.
- Its compile reached all 1601 Ninja steps, linked, packaged, validated the staged app and uploaded release artifacts.
- Treat this build/runtime behavior as the safety baseline when a newer CI-green build fails before the UI.

### Run #181

- Run: `37631564579`.
- Failed at native compile near the end because `home.cpp` kept an unused `hero_cover` variable and warnings are errors.
- The failure was compile-only, not a hardware runtime signal.
- Fixed by commit `200db3485e85a14234e21973933865cf6f042ae4`.

### Run #182 — CI green but HARDWARE BROKEN

- Run: **`37660484879`**
- Commit: **`200db3485e85a14234e21973933865cf6f042ae4`**
- CI result: green through compile, link, package, staged-app validation and artifact upload.
- Hardware result on PS5 FW 13.60: **DOES NOT BOOT**.
- Console crash:
  - `PPSA99008 a planté avant la mise en pause de KStuff`
  - `0xa002030a`
  - `SYSTEM_ILLEGAL_FUNCTION_CALL`
  - thread: `eboot.bin`
- Reinstalling the app and rebooting the console did not change the crash.
- Therefore: **CI green is not sufficient evidence that a startup-affecting PS5 release is valid. Hardware boot is a required gate.**

## Root cause of the #182 boot regression

High-confidence regression isolated against #180:

- Commit `67dcc339...` added `Ps5ConsoleStorage()` in `headless/prosperoeden/eden_services.cpp`.
- It directly called libc `statfs("/user")`, then `statfs("/system_data")` and `statfs("/system_ex")`.
- Startup call chain is synchronous:
  - `Launcher::Launcher()`
  - `read_home()`
  - `services_.diagnostics()`
  - `Ps5ConsoleStorage()`
  - `statfs("/user")`
- This happens before the first launcher frame. On the affected FW 13.60 hardware it matches the observed immediate `SYSTEM_ILLEGAL_FUNCTION_CALL`.
- #180 did not contain this direct `statfs` path and booted.

### Mandatory startup-safety rule

- **Do not introduce direct libc `statfs` / `statvfs` calls (or other unproven BSD/libc wrappers) on the PS5 release startup path without hardware proof on FW 13.60.**
- For storage diagnostics, use the already proven `std::filesystem::space(Eden::AssetsDir(), error)` path until a console-capacity API is independently proven on hardware.
- Startup-critical changes must be compared against the last hardware-bootable build, not only against CI tests.
- Keep a source-level regression assertion preventing `statfs/statvfs` from returning to `eden_services.cpp` startup diagnostics.

## Build-time policy after #182

- Do **not** throw away successful build work after a late failure.
- #182 saved the CI caches after staging, including ccache and the native dependency/build cache paths.
- A small source fix should reuse those caches and compile only invalidated translation units + relink/package where possible.
- Never intentionally trigger multiple sequential pushes while diagnosing one runtime fault; they cancel/supersede useful runs.
- If a run fails late, prefer the resumable staged-app/incremental cache path already present in `.github/workflows/build-040-zbic.yml`.
- User explicitly does not want another avoidable ~50-minute clean rebuild.

## Other current hardware/UI issue

### Missing PlayStation overlay logo

- On PS5, the Encore logo is visible for the app in the normal app/library list.
- The PlayStation system overlay for the running app does **not** show the expected Encore logo.
- This is separate from the immediate #182 boot crash.
- Investigate PS5 package metadata/system artwork (`sce_sys` assets / package presentation) after restoring a bootable eboot.
- Do not mix an unproven logo/package-art experiment into a boot-crash hotfix unless independently verified.

## Performance/runtime decisions already established

- Four authored generic profiles: **Minimum / Recommended / High / Ultra**; Custom is derived when visible settings differ.
- Shipping compile-ahead remains disabled unless shared JIT is genuinely available; prior FC27 measurements showed saved-block/JIT pressure could introduce severe stalls.
- Current PS5 shipping runtime uses stable per-core Dynarmic.
- RADV memory budgeting was increased after FC27 texture-GC pressure around the old 4 GiB budget produced severe FPS degradation.
- Safe Launch must stay conservative.
- Nlib enrichment is launcher-only and must never make game launch depend on network availability.
- OpenSSL bundled CA support and Nlib HTTP identity compiled successfully in #182; they are not the primary suspect for the pre-UI illegal-function crash.

## Release/package notes

- Release artifacts include:
  - full ZIP
  - FTP-safe ZIP
  - ShadowMount `.ffpfsc`
  - checksums/symbols
- The FTP-safe ZIP branch was independently exercised against the #180 staged artifact and passed:
  - runtime files present
  - 29 `.po` catalogs retained
  - `legal/` excluded
  - ShadowMount-only `.txt` language companions excluded.
- Do not claim a release is “validated” solely because packaging checks pass; hardware boot remains required.

## User expectations for this project

- French, concise status updates, but exact run/commit/step facts.
- When asked “où ça en est / terminé ?”, re-query GitHub; never repeat stale status.
- If build succeeds, fetch the real artifact immediately and provide the app link.
- If build fails, inspect exact failing step/log and patch the narrow cause.
- Do not restart/rebuild everything when an incremental/resumable path exists.
- Keep README/credits/legal metadata and repo hygiene current.
- Update **this MEMORY.md** whenever a material repo state, run outcome, hardware finding, regression cause or architectural rule changes.
