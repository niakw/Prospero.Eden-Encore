# Prospero.Eden Encore — Technical Notes

This document is the authoritative technical close-out for the Encore fork.

## Scope

- Base: **ProsperoEden v1.000.040**.
- Primary console target: **PS5 firmware 13.60**.
- Hardware status: **13.60 tested**.
- Default branch: `fix/0.40-zbic-13.60`.
- Divergent archive/reference branch: `>0.50-bug_13.60`.
- Goal: keep the working 1.000.040 filesystem-access behavior on 13.60 while selectively adding
  compatibility, stability, recovery, PS5 UX and release-engineering improvements.
- Newer ProsperoEden Lapy/elevation work is intentionally **not** merged wholesale.

## Firmware compatibility

| PS5 firmware | Encore status |
| --- | --- |
| **13.60** | **Tested / primary supported target** |
| Other firmware layouts supported by underlying tools | Not validated by Encore |
| Unknown/newer firmware layouts | No compatibility claim |

An offset existing in a payload SDK or another PS5 project is not treated as proof of Encore
compatibility. Hardware validation is required before adding a firmware to the supported table.

## Filesystem elevation

Encore keeps the 1.000.040 one-shot sandbox-elevation path and does not depend on Lapy.

### Request model

- `main.cpp` requests `Capability::filesystem` once during single-threaded startup.
- The packaged helper is `/app0/sandbox-elevator.elf`.
- The application connects to the local ELF-loader endpoint at `127.0.0.1:9021`.
- If elevation is unavailable or validation fails, the request returns an error and Encore remains
  sandboxed rather than reporting success.

### Safety / hardening properties

The helper is deliberately narrow at the protocol boundary:

1. Fixed 24-byte, little-endian, versioned protocol.
2. Magic/version/message-kind/PID/status validation.
3. Only the declared `filesystem` capability is accepted.
4. No arbitrary kernel pointer, address or privilege mask is sent by the application.
5. Requested PID must resolve to the exact application title ID `PPSA99008`.
6. Kernel pointers are checked and process traversal is bounded.
7. Original credential/filesystem state is read before modification.
8. The application performs the same-UID credential-clone handshake first.
9. The helper refuses to write if the credential pointer did not change or the clone does not match
   the captured original state.
10. The elevated state is read back and must exactly match the intended state.
11. A failed apply attempts a full write-back and verification of the original state.
12. Connect/send/receive operations have bounded five-second timeouts.
13. The helper serves one request and exits; Encore installs no persistent elevation service.
14. The packaged ELF is structurally validated so trailing data cannot corrupt the protocol stream.

### Security limitation

This is **not** a least-privilege sandbox after elevation. To escape the PS5 application sandbox,
the helper still applies broad process identity, authority/capabilities and root/jail vnode changes.

The hardening therefore reduces the risk of wrong-target writes, partial writes, silent failure,
protocol misuse and persistent-service exposure. It does not make a compromised elevated process,
jailbreak environment or local ELF loader safe.

The implementation-specific note lives in
[`headless/elevation/README.md`](../headless/elevation/README.md).

## Compatibility changes

### ZBIC NSO support

- Added ZBIC/zstd decompression for newer compressed NSO segments.
- Existing LZ4 decompression remains intact.
- Detection follows Eden's upstream ZBIC flag behavior.
- Pinned ZBIC source is built into the common target.
- ProsperoEden's low-memory/in-place PS5 NSO strategy is preserved.
- Host NSO memory checks understand the ZBIC helper.

This addresses newer software reaching the NSO loader and failing with
`Core load failed: 43` / `ErrorLoadingNSO` on the old loader path.

## PS5 UX and controls

- PlayStation-first face-button mapping by default.
- Nintendo-position layout remains available.
- Per-game controller-layout override.
- Vibration on/off and strength.
- Adjustable stick deadzone.
- Up to four controllers with runtime hotplug.
- Motion sensors retained.
- Analog L2/R2 guest trigger support retained.
- Touchpad shortcuts retained:
  - Touchpad + L1: return to launcher.
  - Touchpad + R1: toggle FPS HUD where supported.
- Launcher ownership follows the foreground PS5 user with initial-user fallback.

## Performance and recovery

### Defaults

Fresh configurations use conservative defaults:

- Vulkan.
- 1080p output.
- 1x internal resolution.
- Bilinear scaling.
- 60 Hz.
- FPS overlay off.
- PlayStation controller layout.
- 8% stick deadzone.
- Full vibration.
- Docked mode.

Existing saved preferences are not silently rewritten.

### Performance profiles

Encore exposes three user-facing profiles:

- **Recommended** — conservative accuracy/stability.
- **Smooth** — compile-ahead oriented.
- **Performance** — more aggressive performance trade-offs.

### Safe Launch

A Library Safe Launch is one-shot and does not rewrite saved preferences.

For that run only it selects:

- OpenGL.
- Handheld mode.
- 1x internal resolution.
- Bilinear.
- 60 Hz.
- 1080p output.
- Mods disabled.

### Reset paths

- Global **Restore recommended defaults**.
- Per-game **Reset overrides**.

## Launcher and storage hardening

- Library scanning is asynchronous.
- Cover loading is lazy and texture memory is bounded/LRU.
- Settings use temporary-file + rename semantics.
- Invalid JSON falls back safely.
- Per-game option indexes are range checked.
- RADV shader cache is capped at **256 MB**.
- Session logs rotate in bounded segments.
- Diagnostics reports filesystem mode, free space, shader/JIT cache size and log size.
- Diagnostics can safely clear shader/JIT caches without touching saves, settings, keys, firmware or
  game files.
- Game-files selection rejects `/` to avoid accidental console-root scanning.
- Git ignores explicitly cover keys, ROM/container formats and local save-transfer data.

## Save transfer hardening

Supported transfer behavior:

- Ryujinx save discovery/import.
- Hand-copied save import.
- Account and device saves handled independently.
- Export to a re-importable folder.
- Existing target moved to backup before replacement.
- Failed import removes partial output and restores the previous save.

Security fix:

- A symlink at the import root is rejected.
- Nested symlinks are rejected.
- Host regression tests verify a selected save tree cannot escape through a symlink.

## Language and accessibility

- Launcher catalogs cover the existing language set.
- French is treated as the strict complete catalog in release validation.
- Other incomplete catalogs safely fall back to English for missing strings while still validating
  existing placeholders/fonts.
- On a fresh config, game language is seeded once from the PS5 system locale when supported.
- Later user language choices remain authoritative.
- Contextual help explains renderer, performance profile, output/internal resolution, filter,
  refresh rate and controller choices.

## Eden / Encore identity

- Uses Eden's official logo as the project-facing source asset.
- Encore branding is used in repo/release-facing surfaces.
- Existing Title ID `PPSA99008` is preserved to keep the installation/data relationship.
- Internal package-title validation remains deterministic.
- Launcher TGA assets are generated in the exact uncompressed format supported by the runtime.

## Native build and packaging hardening

### RADV / Mesa weak imports

The PS5 RADV static archive contains optional weak dispatch references.

Encore uses a two-pass strategy:

1. Link against the real static/system providers.
2. Inspect weak imports that still survive.
3. Resolve only the surviving optional hooks to address zero.
4. Perform the final native link.
5. Reject the binary if an unresolved weak native import remains.

This avoids inventing fake PS5 SDK exports while preserving symbols actually provided by real
libraries.

### Reproducibility and release

- Git dependencies are pinned.
- Release preflight verifies checkout revisions.
- Hosted GitHub runners build the release.
- Translation validation runs before the native build.
- Release publication has write permission only in the publish job.
- ZIP timestamps are deterministic.
- Release output includes SHA-256 checksums.
- Compiled ZIP / FFPFSC assets are published only after the build/package job succeeds.
- Unstripped symbols are retained as CI artifacts for diagnosis.

## Validation history

Key findings that materially changed the release:

| Run | Result | Finding / closure |
| --- | --- | --- |
| `37209589337` | Failed | ZBIC include path missing from common target; fixed. |
| `37211222037` | Failed | Host NSO harness did not understand ZBIC; fixed. |
| `37214268693` | Failed | RADV weak import survived native packaging; led to two-pass linker hardening. |
| `37227976171` / `37229710339` | Failed | Removed obsolete Eden-theme helpers rejected by `-Werror`. |
| `37230146719` | **PASS** | Full audited baseline reached build/package artifact generation. |

Later closure work added Safe Launch, resets, storage bounds, diagnostics, save hardening, locale
behavior, full French catalog validation and the release workflow. Publication is gated on a green
build of the release head.

## Deliberately excluded from this release

Encore does not silently pull features merely because they exist in a newer upstream branch.

Deferred/excluded:

- Lapy/newer elevation rewrite.
- Automatic renderer fallback that silently changes persisted behavior.
- Network auto-updater.
- Large multi-profile/player subsystem.
- Arbitrary button-remapping UI.
- Cheat/patch-library expansion.
- Favorites/search/local compatibility database.
- New update/DLC enable-disable manager.
- FSR sharpening UI without a verified matching upstream contract.
- Extra per-title vibration/deadzone/FPS-HUD overrides without a demonstrated need.
- Controller calibration screen.

## PS5 FPKG / kstuff boundary

Prospero.Eden Encore does **not** implement or repair PS5 FPKG entitlement/PPR support.

On firmware 13.60, FPKG installation/launch remains a separate jailbreak/kstuff concern. The
presence of profiles or offsets does not make that path reliable, and failures such as
`CE-109297-8` must not be presented as emulator regressions fixed by Encore.

Encore's own homebrew application build, filesystem path and emulator runtime are validated
separately from that external limitation.
