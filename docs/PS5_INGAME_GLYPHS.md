# PlayStation-style buttons drawn INSIDE Nintendo Switch games

## Same approach as encore-overrides; no Build ID or EdiZon required

The user already has DualSense **input mapping**. This project changes
the **graphics drawn by the game**: Nintendo's A/B/X/Y artwork becomes
compatible PlayStation Cross/Circle/Square/Triangle artwork when verified
files exist. It does NOT remap game actions or modify the approved launcher.

The catalogue is maintained in
[niakw/encore-overrides/glyphs/manifest.json](https://github.com/niakw/encore-overrides/blob/main/glyphs/manifest.json).
It is a **schema_version 2** JSON with a revision and per-game
`title_id` + `update_version` rules. The same existing
`tools/sync-encore-overrides.py --source /path/to/encore-overrides`
command regenerates the C++ snapshot in Eden Encore (and a local JSON
copy); no second user workflow is necessary. Runtime configurations
can carry newer revisions at
`config/encore-glyph-overrides.json`.

### Why not a Build ID?

The Build ID is tied to a game **executable compilation**, and often
changes after updates. It is important for executable-address-based
cheats, where EdiZon can display it, but is not appropriate as a mandatory
identifier for *RomFS graphic assets*. Users are never asked for one.

A compatible graphics pack uses the game's Title ID and update display
version, with SHA-256 fingerprints of the exact **original graphics
resources** and artist-owned **replacement resources**. Those bytes are
checked **once at staging**. The live launcher additionally checks that
the installed pack's declared title/update matches its current known
title/update before enabling the existing LayeredFS mod.

### Game assets

The existing loader supports:

    mods/<TITLE_ID>/Eden Encore PS Glyphs/romfs/<GAME_RESOURCE_PATH>

A proposed author/maintainer manifest, with **fictional hashes/IDs**:

```json
{
  "schema": 2,
  "title_id": "0100123456789000",
  "update_version": "v1.2.0",
  "rights": "Original PlayStation-style artwork with redistribution rights",
  "files": [{
    "romfs_path": "UI/Shared/controller_prompt.bntx",
    "replacement": "files/controller-prompt-ps.bntx",
    "original_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "replacement_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }]
}
```

The author supplies already-version-matched original RomFS assets and
their legally distributable replacements. No Nintendo copyrighted atlas
is re-shipped. An author/maintainer can verify and stage once with:

```sh
python3 tools/ps-glyph-pack.py verify \
  --pack /path/to/artist-pack \
  --original-romfs /path/to/matching-original-romfs \
  --title-id 0100123456789000

python3 tools/ps-glyph-pack.py install \
  --pack /path/to/artist-pack \
  --original-romfs /path/to/matching-original-romfs \
  --mods-root /path/to/eden-game-files/mods \
  --title-id 0100123456789000
```

**These are pack-maintainer actions, not steps the player must perform.**
The last product step will be verified automatic catalogue + asset delivery.

### Runtime selection

At game boot (never in the per-frame renderer), Eden checks:

1. User visual style preference: PlayStation preferred or Nintendo.
2. Curated title/update rule (generated snapshot or newer runtime JSON).
3. Known running title/update display version, installed verified pack and
   per-title Mods opt-out.
4. Pack provenance/title/update and the presence of expected graphic files.

Missing, unknown or mismatched means **Nintendo graphics**. Safe Launch
disables all mods. Global JSON setting
`appearance/ingame_button_glyphs` accepts `playstation` (preferred,
default) and `switch`; a per-title key
`games/<TITLE_ID>/ingame_button_glyphs` can override it.

The host-only CI compiles the real C++ selector and tests synthetic
RomFS resource verification, compatibility rejections and the settings
round trip, alongside other JIT/Vulkan regressions.

### Still not qualified

- **Zero verified game-specific PlayStation artwork packs so far.**
  A central rule is not a resource generator.
- Exact base-game version detection and some unscanned updates need
  additional metadata support. An unknown version stays in Nintendo mode.
- The installer checks original resource hashes at packaging/staging,
  **not** the active game's decrypted resource bytes at native load.
  Therefore a similarly labelled but changed RomFS asset is not yet
  independently attested on console.
- Real FC27 menu/match graphics, other title scenes, runtime performance,
  automatic distribution and rollback need PS5 firmware 13.60 testing.
  No shader/OCR-based universal runtime icon rewriting is implemented.

Work and qualification are tracked in
[Issue #7](https://github.com/niakw/Prospero.Eden-Encore/issues/7).

### 8 October 2026 — Check installed artwork bytes, not only its filename

The original implementation checked that the pack's manifest declared
SHA-256 values and that each RomFS graphic file existed. This was
insufficient: a file overwritten after installation could still be
selected, even if its bytes no longer matched the verified pack.

The launcher now computes **SHA-256 of each installed replacement file**
once during game boot in streaming 32 KiB chunks and compares it with
the pack's recorded `replacement_sha256`. Any mismatched, deleted,
unreadable, symlinked or oversized asset disables the whole visual pack,
leaving Nintendo prompts in place. The same admission path also refuses
case-insensitive duplicate Title ID directories or competing mod names,
because Eden's original mod loader could otherwise choose and overlay
an ambiguous folder order.

Strict scan bounds match the offline package tool: up to **128 MiB per
graphic resource** and **512 MiB total**. No file hashing happens in
the renderer's per-frame path. Host tests cover independent SHA-256
vectors (empty, segmented `abc`, 1,000,000 bytes of `a`), actual
on-disk streaming reads, post-install file tampering, symlink escape
attempts and case-colliding mod paths.

**Remaining trust boundary:** a malicious actor with write access to
both the JSON manifest and graphic files can recompute an unsigned
checksum; SHA-256 here provides corruption/integrity detection against
the recorded manifest, NOT catalogue provenance authenticity. The
original graphic file actually loaded from the selected base/update
RomFS is NOT yet hashed on PS5. Files may also be changed between the
launch verification and the emulator's later filesystem read; production
qualification needs a stable filesystem snapshot or guarded asset
lifecycle. No game-specific PlayStation graphics are bundled yet.
