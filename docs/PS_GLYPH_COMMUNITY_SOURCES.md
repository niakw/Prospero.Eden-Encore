# PlayStation glyphs — verified community references (2026-10-09)

This is a source catalogue, NOT an Eden compatibility manifest or permission to redistribute mods/game artwork. Do not automatically install or enable any item.

| Title / tool | Upstream page | Qualification | Distribution caution |
| --- | --- | --- | --- |
| Zelda: Breath of the Wild **(Switch RomFS)** | https://gamebanana.com/mods/659253 | DS4 UI Mod v2 Western Layout; explicitly reports Cross/Circle + Square/Triangle swaps for interaction prompts, tutorials, and menus; fixes the previous mismatch between action prompts and a bottom-Cross PlayStation mapping. Game update/asset hashes and PS5 compatibility remain unverified | CC BY-NC-ND 4.0: link only; no automatic adaptation or bundling |
| Zelda: Tears of the Kingdom | https://gamebanana.com/mods/445517 | StavaasEVG DualSense UI v1.4.1; page lists game updates 1.1.0–1.1.2; changes controller layout, UI prompts and fonts; no Eden Encore runtime verification | CC BY-NC-ND 4.0: link only; no automatic adaptation |
| Metroid Dread | https://gamebanana.com/mods/330216 | Switch to PS5 Layout v3; replaces game-native prompts; game update unspecified and Eden Encore untested | CC BY-NC-ND 4.0: link only |
| Metroid Dread (PS4 alternative) | https://gamebanana.com/mods/330775 | Switch to PS4 Layout; page identifies Title ID 010093801237C000; not PS5 compatibility evidence | CC BY-NC-ND 4.0: link only |
| Switch Toolbox | https://github.com/KillzXGaming/Switch-Toolbox | Archived editor of BFRES/BNTX/BFLYT/BFLAN and more; not a validated automatic converter | GPL-3.0 and dependency license audit needed |
| Switch Toolbox Bugfixes | https://github.com/Filuz/Switch-Toolbox-Bugfixes | Community fork advertises import/export of BFRES/BNTX/BFLYT/BFLAN; not validated for Eden | Examine upstream and bundled licenses |

## Qualification gates before any runtime enablement

1. Index community pages as links with license and provenance, NOT their downloadable copyrighted assets.
2. Resolve the exact Title ID, game update, original texture hash, replacement hash, layout context and mapping. Treat absent fields as unverified.
3. For legitimately extracted local game files, run read-only discovery via tools/ps-glyph-atlas.py, tools/ps-glyph-scan.py, tools/ps-glyph-bntx-inspect.py. Candidate texture names or geometry do not prove button semantics.
4. Reuse mappings only with original byte-identical SHA and separately approved semantic context; the PlayStation Auto menu/gameplay layout can change the desired prompt.
5. Verify any proprietary texture unpack/repack including swizzle, ASTC/BC compression, mipmaps, and UI layout/font references. Validate on physical PS5 and ensure rollback before enablement.
6. The user-supplied Zacksly source art is CC BY 3.0 and requires visible attribution/modification notice (see headless/prosperoeden/ui/art/PS5_ICONS_ATTRIBUTION.md); it is not a per-title atlas.

**Status:** No verified game-native PlayStation art pack is embedded; issue #7 remains OPEN. Input mapping and launcher controller images are not equivalent to in-game glyph art.
