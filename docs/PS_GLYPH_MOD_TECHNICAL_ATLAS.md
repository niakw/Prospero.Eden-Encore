# Eden Encore — Community glyph mod technical atlas (research, not runtime support)

Updated 2026-10-09. **No game/mod archives were unpacked during this survey**. Data below come from public descriptions, not fabricated sprite coordinates. An unknown original RomFS path, resource format, title/update compatibility, bounding rectangle or texture offset must remain `null` in machine-readable evidence. This is a technical reference, not a right to rehost copyrighted assets. Attribution/license constraints still apply to actual redistribution.

| Game | Mod URL | Observed mapping / function | Resource/container evidence | Version evidence | Extraction next step |
| --- | --- | --- | --- | --- | --- |
| Breath of the Wild (Switch) | https://gamebanana.com/mods/659253 | DS4 UI v2 Western: author explicitly corrected interaction prompts that remained Nintendo despite menus/tips being converted; swapped Cross↔Circle and Square↔Triangle using Switch Toolbox; L2 horse interaction added | Switch Toolbox icon editing; exact file paths/atlas rectangles unknown | mod 2.0, game update unknown | inspect standalone RomFS/UKMM path tree, compare menu/tips/interaction images separately |
| Breath of the Wild (Switch) | https://gamebanana.com/mods/33340 | Xbox UI standard/western/PE layouts; western bottom confirm vs standard rightmost; only button prompts/icons | Switch RomFS prompt graphics; exact path unknown | unknown | diff three layout variants |
| Tears of the Kingdom | https://gamebanana.com/mods/443336 | Xbox UI v0.8.2: seven special action screens with alternate swap-action/jump variants; author's tooling uses layout/hex editing, Switch Toolbox, FontForge, bfttfutil, astcenc, Python | layout + font + texture pipeline, not necessarily one atlas | tags 1.1.0–1.2.1; tag is not per-file proof | inventory BF layouts/font patches/screens, track scene variants |
| Tears of the Kingdom | https://gamebanana.com/mods/445517 | DualSense UI changes prompts/layouts/fonts; controller layout dependent | UI layouts and text, paths unknown | upstream claims selected game versions; validate individually | compare files against same-version ROMFS |
| Metroid Dread | https://gamebanana.com/mods/330216 | PS5 layout v3; author corrected incorrect Triangle/Square swap over v1/v2; Accept is Circle, Parry is Square in this layout | romfs mod, path within game unknown | game update unknown | inspect v1→v3 changing assets and scene mapping |
| Metroid Dread | https://gamebanana.com/mods/330775 | PS4 layout, includes controller Controls view | atmosphere contents/010093801237C000/romfs | game update unknown | list exact replaced relative paths |
| Paper Mario: The Thousand-Year Door (Switch) | https://gamebanana.com/mods/515629 | PS button prompts require A/B swapped, X/Y swapped controller convention | image prompt replacement, exact file path unknown | game update unknown | inspect button prompt resource tree |
| Paper Mario: The Thousand-Year Door (Switch) | https://gamebanana.com/mods/518079 | GameCube prompts for battle and dialogue; gives separate UI coverage candidate | battle/text prompts, exact path unknown | unknown | compare with PS variant to identify shared atlas/resource targets |
| Zelda: Echoes of Wisdom | https://gamebanana.com/mods/544776 | DualSense UI shipped as mod-folder overlay | file structure unknown | game update unknown | inspect overlay manifest/tree |
| Zelda: Link's Awakening (Switch) | https://gamebanana.com/mods/540069 | Xbox standard/western/alternative layouts with explicit letter reassignment; one layout changes sword and item-slot functions | multiple resource variants, exact path unknown | developed for update 1.0.1; 1.0.0 unconfirmed | compare all variant resource trees and hash-equivalent files |
| Super Mario 3D World + Bowser's Fury | https://gamebanana.com/mods/34284 | PlayStation prompts v1.4; D-pad, hold power-up, Bowser's Fury power-up select, minus→touchpad, capture→create | Switch Toolbox import noted by author; exact paths unknown | mod 1.4, game update unknown | list changed assets across releases 1.1–1.4 |
| Shin Megami Tensei V (original Switch) | https://gamebanana.com/mods/350105 | PS4/PS5-styled prompt replacement; user mentions separate swapped ABXY modification | exact paths unknown | game update unknown | compare original and swapped layouts (with permission to access files) |

## Findings / required automation architecture

* **Three distinct mappings:** input physical binding, on-screen face-button art, and per-scene semantic action (accept/cancel/attack/parry/hold). An individual title can use different button assignments and images between menus, prompts and gameplay.
* **Multi-resource mods:** Nintendo UI may live in layout (BFLYT/BFLAN), text/font data, compressed ASTC/BNTX/BFRES and uncompressed sprites. One RGBA scanner cannot cover all.
* **Version vs evidence:** a mod release version (e.g. v1.4) is not a game update version. A GameBanana tag is evidence to investigate, not a validated source SHA.
* **Extract positions mechanically, never invent them:** read mod archive as local user-provided input, safely enumerate paths, record changed texture metadata, decode a supported image, and diff against exact legally extracted game originals. For layout files capture referenced texture and glyph IDs as well. Validate original/replacement SHA before writing atlas rectangles.
* **Community variants provide positive and negative examples** (Metroid Triangle/Square correction; BOTW interaction-menu discrepancy). Track per-screen test assertions separately.
* **Do not autoenable**: no entry here confirms a working PS5 FW13.60 file, per-game SHA, full glyph coordinates, legal redistribution, or runtime result.

### Evidence schema for future extraction

Per mod candidate: `source_url`, `mod_version`, `license`, `game_title`, `title_id`, `game_update`, `romfs_path`, `container`, `texture_name`, `original_sha256`, `replacement_sha256`, `rect_xywh`, `original_button`, `ps_button`, `scene_context`, `confidence`, `test_proof`. Unknowns are null, not inferred from screenshots or filenames.

This research catalogue does not imply actual game files were fetched or processed.

## 2026-10-09 — New high-value exact resource leads

### BALL x PIT (Unity)

Author's public [mod source](https://github.com/mircowuffwuff/ball-x-pit-nsw-ver-playstation-button-prompts) identifies:
- **Title ID** `010086A022444000`; **game version** 1.251 (author tested).
- **RomFS** `Data/resources.assets`; Unity **Texture2D** `controller_btns_outlined`.
- **Procedure**: AssetStudioMod export original Texture2D PNG, overlay PS button icons, UABEA `Edit texture` and `Load` new RGBA32 PNG, save patched whole `resources.assets`, install under `PlayStation prompts/romfs/Data/`.
- **Functional coverage**: face buttons, L/R→L1/R1, ZL/ZR→L2/R2 (1 pixel shorter), and DualSense-style D-pad; plus/minus→PS Start/Share **not converted** because source rectangles have incompatible sizing.
- **Environment**: tested in Eden Android 0.1.1; **not** qualified on PS5. The author's documentation mentions official PS4 prompt art bundled in the Switch game. This does not establish a universal run-time switcher in Eden.
- Our generic `ps-glyph-exported-texture-diff.py` accepts the original/modded texture PNG exports and calculates actual visible changed-pixel bounding boxes. Those exported texture bytes and the authored mod release ZIP have **not** been acquired/analyzed by Eden yet.

### Zelda: Tears of the Kingdom (compressed Nintendo UI)

A comment on the [Simple Xbox Mod](https://gamebanana.com/mods/443260) identifies a specific candidate resource hierarchy:
`UI/LayoutArchive/Common.Product.110.Nin_NX_NVN.blarc.zs` → `__Combined.bntx` → `Nt_KeyTexA_00^d.bftex` (B/X/Y icons reported in the same texture family).

This is a **community-supplied lead**, not a decoded binary observation. According to [TotK research](https://github.com/TotkMods/Research), `.zs` archives may need dictionary-aware ZSTD with dictionaries extracted from the user's `Pack/ZsDic.pack.zs`; see [TkZstd](https://github.com/TotkMods/TkZstd). A decompressed BLARC/SARC can be indexed byte-for-byte using `ps-glyph-sarc-inspect.py`. Contained BNTX texture/mipmap **byte offsets** can then be inventoried using `ps-glyph-bntx-inspect.py` once safely extracted. Actual texture swizzle/decompression and pixel rectangles remain unqualified.

### Source volume and evidence guard

The machine-readable `docs/PS_GLYPH_SOURCE_INDEX.json` now holds **26 community references across 18 games**. The `tools/check-ps-glyph-community-index.py` source gate refuses to mark a rectangle verified without inspected archive, title/update, original/replacement SHA and a sane XYWH rectangle. It also requires explicit native PS5 test evidence for a compatibility claim. Both the indexing and gate are **source-only; the checker has not been executed**.

### Persona 3 Portable (Switch) — nested non-BNTX resource chain

[Mod author instructions](https://gamebanana.com/mods/461733) identify an actual packaging chain: Title ID `0100DCD01525A000`, `romfs/data_EN/umd0.cpk` → `init_free.bin` → `init/camp.bin` → `pc_button.spr`. It uses CPK File Builder and Amicitia, NOT a PNG/TGA RomFS direct replacement. The author states Standard mapping **Nintendo A → Circle** and **Nintendo B → Cross**. This is an extraction/injection **lead**, not validated source bytes or pixel positions.

### Tokyo Mirage Sessions #FE Encore — glyphs that are not textures

[Mod documentation](https://gamebanana.com/mods/367516) says PlayStation ABXY and shoulder prompts were replaced; Start/Select/PS were left original due to sprite rectangle limits, and the world **Check** prompt is not a texture at all. This falsifies any plan to claim that a pixel atlas engine alone can replace every button in every game. Requires an unsupported/procedural UI classification and possibly a separate text/layout renderer adapter after real evidence.
