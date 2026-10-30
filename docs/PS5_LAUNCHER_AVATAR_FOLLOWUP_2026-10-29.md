# PS5 launcher — current-account avatar follow-up (2026-10-29)

## Scope and branch isolation
- Encore-only UI change: `fix/ps5-launcher-avatar-recovery`, based on `dev/ps5-sparse-jit` as of 2026-10-29. **Do not merge into F07 while technical optimizations are being applied in parallel.**
- NiakPS5 cooperating broker repair: `niakw/NiakPS5@fix/ps5-avatar-owner-marker-runtime`.
- No PS5 release package or emulator core/GPU/JIT change is part of this work.

## Verified from source
1. Encore already decodes PNG and DDS BC1/BC2/BC3; the native account cache lookup only ran once at launcher construction.
2. NiakPS5's broker reads the foreground account's profile PNG/DDS, stages a bounded copy under `/data/NiakPS5/assets`, and writes an owner+format marker `0x%08X png\n` or `0x%08X dds\n`. The old marker temporary file lived under `/data/homebrew/PPSA99386/assets`, not its destination directory, risking write/rename failure.
3. Encore now probes the direct cache or an optional **exact-user-matched** NiakPS5 stage from a background task. Its source fingerprint is checked every 5 s, so missing-at-start and replaced files can refresh without polling the filesystem or decoding on the UI/render thread.
4. NiakPS5 is optional. If neither source can be read, the fallback remains the neutral silhouette, never a made-up profile image.

## Offline validation
- Host compile/run of the real owner-marker header: valid marker accepted, different user rejected, wrong format rejected, symlink and corrupt marker rejected. No PS5 runtime inference from this test.
- Eden existing DDS host test remains in `tools/check-ps5-avatar-dds-host.py`; the expanded script includes owner-marker host testing and source contracts. Full repo CI not yet run.
- NiakPS5 regression test: `native/title/tests/test_title.py` checks that the owner marker is created in the app's writable runtime directory. Full repo CI not yet run.

## Console validation required before closing
1. On firmware 13.60 with the actual current user, observe which of `avatar.png`, `avatar440.dds`, `avatar260.dds`, `avatar128.dds` or `avatar64.dds` is readable in `/system_data/priv/cache/profile/0xXXXXXXXX/`. Do not send private user ID or portrait to public CI.
2. If NiakPS5 is installed and running, inspect `/data/NiakPS5/logs/autostart.log` for `Current user PNG avatar staged` / `Current user DDS avatar staged` or the marker refusal/inaccessible messages, plus owner marker/image presence in `/data/NiakPS5/assets/`.
3. Launch Encore and confirm the actual PS5 foreground-account image appears. With the cache/broker staged after launcher startup, confirm appearance without restart (up to one 5-second refresh plus asynchronous image upload).
4. Switch active PS5 user and confirm no previous user's avatar remains after the next refresh; test PNG, DDS, no-image and corrupt/missing marker cases. A user-switch may remain briefly stale until the next poll: stronger immediate account-switch detection would need a verified native event source.
5. Confirm no launcher stalls and no interaction with F07 emulator GPU/JIT work. Only after console evidence, merge the isolated avatar change and produce a combined release when F07 has completed its own gates.

**Status: source fix prepared; real console behavior pending.** Neither code review nor host checks prove that a PS5 title sandbox can read the NiakPS5 runtime assets on all firmware configurations.
