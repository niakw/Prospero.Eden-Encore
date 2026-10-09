# Switch 1 native RomFS: PlayStation prompts — researched candidates

*2026-10-09, source-only research. Do NOT treat these links as verified game asset fingerprints or redistribute mod binary art without its creator's rights. Do NOT trigger a CI build or modify the PS5.*

## Candidate for Zelda: Breath of the Wild (Nintendo Switch)

**BOTW DS4 UI Mod v2 — Western Layout** by the community, reported for the *Switch* game (not the Wii U/Cemu texture format). Sources:

- https://www.nexusmods.com/legendofzeldabreathofthewild/mods/98
- https://gamebanana.com/mods/659253

The release description explicitly claims a **Yuzu/Citron RomFS** mod that replaces Switch button UI, tips/tutorials, interaction prompts and the missing L2 prompt on horseback. Version 2 adds Western button ordering (Cross bottom as primary) for a DS4. It includes a standard Yuzu/RomFS package and a UKMM variant. **Candidate only:** the source description, Nintendo Switch title compatibility, the actual RomFS relative file paths, the user's exact game update, hashing and in-game visuals are **not yet verified on this PS5**. The maker credited in the release is anonymous; no redistribution permission for the art is established.

The game ID seen in the existing Eden Encore library/log for Zelda is `01007EF00011E000`. Eden's normal mod loader expects an installed legal mod folder beneath `<game-files>/mods/01007EF00011E000/<mod-name>/romfs/...`; it is separate from Eden's special `Eden-PS-Glyphs` verified/bundled glyph rule. The mod should be installed by the **user only**, after checking file integrity and the mod's actual compatibility; **do not automatically download/enable an untrusted third-party modification or silently bypass per-title SHA gates**. The stage `data/glyph-overrides.json` remains empty because we do not have a verified `update_version` and original/replacement RomFS content digests. The normal mod loader has its own normal on/off selection and does not imply that the special validated glyph mode is enabled.

The "**Western Layout**" variant should be assessed alongside Eden's *fixed* per-title PlayStation mapping so that the **on-screen art matches the actual physical action**. No per-scene A/B auto swapping; do not conflate artwork with HID input.

## Other Switch examples / reuse of established mod formats

- [Metroid Dread — Switch to PS4 Layout](https://gamebanana.com/mods/330775): explicitly documents a Switch `romfs` mod and Yuzu/Ryujinx installation folder, including controller-screen art. Use as a **per-engine format example**, not as reusable arbitrary game image paths.
- [Dragon Quest X Offline — PS4/PS5 Button Prompts](https://www.nexusmods.com/dragonquestxoffline/mods/5): explicitly offers separate *Switch version* mod payload under title `0100E2E0152E4000/romfs/Holiday/Content/Paks`; demonstrates Unreal PAK granularity. Creator's rights vary, so no asset copying by default.
- [Ryujinx guide](https://git.blizzard.systems/github-mirrors/ryujinx/wiki/FAQ-and-Troubleshooting): normal mod layout `mods/contents/<title>/<mod>/romfs` or `exefs`, conceptually compatible with Eden's title-scoped mod discovery.

## FC27 status

No source-verified Switch-native FC27 PlayStation RomFS asset pack or eligible hash/version has been identified. The normal DualSense-to-guest mapping does not alter image assets. The runtime correctly reports `rule=unsupported`; an automatic generic atlas is **not** a safe substitute without texture/asset identity proof.

## Validation prerequisites before marking any candidate ready

- Obtain a legally distributable/user-authorized **Switch-targeted** payload (not Wii U/PC version).
- Verify base title ID, game update version, versioned RomFS paths, container compression, and exact old/new file SHA-256 digests.
- Validate mod activation without breaking guest filesystem, save loading or performance.
- Confirm on-console that menu, cinema, hints, pause, item prompts and physical DualSense semantics agree.
- Keep source attribution and licensing; don't package anonymous author artwork into public builds by default.

Until then, no source claims automatic PlayStation glyph replacement in BOTW or FC27.
