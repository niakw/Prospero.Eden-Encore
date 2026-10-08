# PlayStation glyph artwork *inside games* — verified RomFS route

## Scope — entirely separate from button mapping

The existing controller mapping already translates DualSense buttons to
emulated Switch actions. **Do not change that mapping.** This work targets
the Nintendo face-button artwork displayed *inside* games, replacing it
with compatible PlayStation art where legally supplied, game-specific
replacement resources exist.

Different Switch games render button hints using textures, atlases,
fonts, layout data or shaders. Merely choosing a controller profile cannot
rewrite game-owned artwork. There is no trustworthy one-size-fits-all
A/B/X/Y -> PlayStation transformation at the input layer.

Eden already supports RomFS overlays through its Mods directory:
mods/<TITLE_ID>/<MOD_NAME>/romfs/<GAME_RESOURCE_PATH>.
The new installer uses the mod name "Eden Encore PS Glyphs" and never
distributes an original Nintendo resource.

## What is implemented

tools/ps-glyph-pack.py validates a legal replacement pack whose manifest
declares exact 16-hex title ID, 40/64-hex program build ID, the author's
rights declaration, and original + replacement SHA-256 per RomFS asset.
One possible schema, with **fictional identifiers/hashes, not a real game**:

    {
      "schema": 1,
      "title_id": "0100123456789000",
      "build_id": "0123456789ABCDEF0123456789ABCDEF01234567",
      "rights": "Original replacement art, redistribution permitted",
      "files": [{
        "romfs_path": "UI/Shared/controller_prompt.bntx",
        "replacement": "files/dual-sense-controller_prompt.bntx",
        "original_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "replacement_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      }]
    }

Verification, using a legitimately dumped and version-matched original
RomFS directory for source hashes, plus legally created replacement art:

    python3 tools/ps-glyph-pack.py verify \
      --pack /path/to/legal-glyph-pack \
      --original-romfs /path/to/matching-romfs \
      --title-id 0100123456789000 \
      --build-id 0123456789ABCDEF0123456789ABCDEF01234567

After independent verification of the selected game's build ID:

    python3 tools/ps-glyph-pack.py install \
      --pack /path/to/legal-glyph-pack \
      --original-romfs /path/to/matching-romfs \
      --mods-root /path/to/game-files/mods \
      --title-id 0100123456789000 \
      --build-id 0123456789ABCDEF0123456789ABCDEF01234567

The installer checks all original/replacement hashes and rejects bad
title IDs, mismatched build IDs, path traversal, symlinks, duplicates,
unexpected metadata and excessive file sizes. It stages verified
resources in a temporary sibling directory before renaming to the
LayeredFS mod. Provenance metadata is stored OUTSIDE the romfs/
folder. It refuses to overwrite any existing pack. The normal Mods
switch can disable the pack without altering button semantics.

The installer needs an externally supplied actual build ID and an
original RomFS tree. It does NOT decrypt the running title, inspect
the game's live version, or generate a PlayStation prompt atlas
automatically. Unverified game updates can change files after pack
installation: disable/remove a stale pack until that version is verified.

## Remaining gates for a production all-games feature

1. Identify and legally source original replacement assets for each
   game/firmware build; no unlicensed or synthetic claims of real coverage.
2. Retrieve the actual running program build ID from Eden BEFORE the
   mod filesystem is composed; fail closed if version is unknown or
   source asset signature does not match. Do not auto-enable packs merely
   from title ID or artist-supplied metadata.
3. Build a verified catalogue, user opt-out, and automatic pack delivery
   without requiring manual file transfer; clearly expose fallback state.
4. Test native gameplay, menus, overlays, and button-art correctness across
   the title's scenes. No input remapping or frame-path OCR/shader interception.
5. PS5 firmware 13.60 build/game testing, performance, safe rollback,
   license audit, and actual screenshot evidence before making any claim
   that in-game PlayStation symbols are active.

Synthetic host-only checks are in tools/check-ps-glyph-packs.py.
Issue tracking: https://github.com/niakw/Prospero.Eden-Encore/issues/7

## Simpler Encore-overrides integration (2026-10-08)

The catalogue is now maintained alongside the existing profiles in
[niakw/encore-overrides/glyphs/manifest.json](https://github.com/niakw/encore-overrides/blob/main/glyphs/manifest.json).
It uses the same authoring model: one versioned JSON, per-title rules, a
generated C++ snapshot and an optional runtime JSON update.

Sync a reviewed source checkout with:

    python3 tools/sync-glyph-overrides.py --source /path/to/encore-overrides

This updates data/glyph-overrides.json and
headless/glyph_overrides_generated.h. The app loads the embedded snapshot,
or a newer valid config/encore-glyph-overrides.json (never an older revision).

An installed, verified `Eden Encore PS Glyphs` graphics mod is selected
*automatically at launch* only if the title ID, **latest scanned update
display version** and staged pack's asserted build ID match a curated rule.
Unsupported/mismatched packs are disabled, preserving Nintendo artwork.
The pack must still exist: the catalogue alone does not create replacement
textures, and a claimed build ID is **not independently verified from the
running NSO yet**.

Visual style is independent of controller mappings. In
prosperoeden.json:

    {"appearance":{"ingame_button_glyphs":"playstation"}}

Use "switch" for original Nintendo artwork. A single title may override
that setting under games/TITLE/ingame_button_glyphs. Default is PlayStation
*preferred*, with Nintendo fallback for unsupported titles. This is a
configuration-level choice, **not yet a new launcher setting/screen**.
The approved home design was deliberately not reworked.

Source-only tests compile the actual selector, verify the title/update and
mod evidence gates, reject unknown versions, check settings persistence and
prove that no controller mapping changes. No hot-path graphics search or
OCR is used.
