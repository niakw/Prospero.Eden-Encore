# Eden Encore — PlayStation glyph discovery via PC / Wii U / PSP editions

Last research update: 2026-10-09. The Switch game stays the authority for **Title ID, exact update, RomFS resources, visual meaning and PS5 runtime**. Ports are discovery *sources*, never default plug-and-play replacements.

## Source registers

* Main Switch-only corpus: [PS_GLYPH_SOURCE_INDEX.json](PS_GLYPH_SOURCE_INDEX.json) — 26 community references / 18 games, zero verified atlas positions.
* Additional cross-platform corpus: [PS_GLYPH_CROSS_PLATFORM_INDEX.json](PS_GLYPH_CROSS_PLATFORM_INDEX.json) — 10 additional sources linked to 6 games already in the Switch corpus, zero verified Switch rectangles.
* Integrity gates (source-only, **not executed**): `tools/check-ps-glyph-community-index.py`, `tools/check-ps-glyph-cross-platform-index.py`.

## Highest-value cross-platform relationships

| Switch title | Source | Exactly documented information | What is transferable / NOT transferable |
| --- | --- | --- | --- |
| Zelda: Breath of the Wild | [Wii U PS4 UI Complete](https://gamebanana.com/mods/33531) | Standard/Western/PE control-map variants, pause help/gamepad view, tutorial prompts. Author relays v1.5.0 reports, not firsthand tests | Scene and mapping facts are useful; Wii U bytes and atlas offsets require separate Switch asset comparison |
| Persona 3 Portable | [PC Controller UI Overhaul](https://gamebanana.com/mods/423178), [PSP icon variants](https://gamebanana.com/mods/354109) | Switch mod [explicitly ports PC design](https://gamebanana.com/mods/461733). PSP mod offers PS/Switch/Xbox/keyboard, SD and HD formats | Compare SPR sprite meaning, bounds and variants. Switch's known `data_EN/umd0.cpk → init_free.bin → init/camp.bin → pc_button.spr` is **not automatically the PC path** |
| Persona 4 Arena Ultimax | [PC Controller UI Overhaul 2.1](https://gamebanana.com/mods/385908) | PS4/Xbox/Switch/Arcade variants, fighting-input diagrams, menu hints and ABXY inversion | Variant-to-variant analysis can locate UI elements; Reloaded II files are not Switch LayeredFS files |
| Persona 5 Royal | [Game Pass DS4 prompts](https://gamebanana.com/mods/408074) | Bug fix specifically for **L3/R3 bounding boxes**, Xbox art replaced with DS4; [colour variants](https://gamebanana.com/mods/408571) | The L3/R3 mod revision is a priority bounding-rectangle test case. PC CPK and file-emulator paths may differ from Switch; no exact Switch offset yet |
| Persona 5 Royal | [PC modding architecture](https://docs.shrinefox.com/getting-started/persona-5-royal-pc-mod-support) | `BASE.CPK`, `EN.CPK`, Reloaded II and Persona Essentials; SPD/AWB/PAK/BF/BMD merge hooks | Toolchain and archive taxonomy, not a proof that Switch assets are byte-identical |
| Bravely Default II | [PC PlayStation prompts](https://www.nexusmods.com/bravelydefault2/mods/14) | Unreal `.pak` in `Bravely_Default_II/Content/Paks/~mods/`; **five Start/Select variants** including touchpad halves, arrows and Options/Share | Resolve inner Unreal package name and UI glyph atlas, then find same semantic Switch resource. The PC `.pak` is not an installable Switch mod |
| Shin Megami Tensei V | [Vengeance Steam→Switch mod](https://gamebanana.com/mods/533409) | Import of Steam localization causes mixed Xbox/Nintendo prompt artwork | Important **negative case**: Vengeance is a different edition, not proof that SMT V original has same archive layout or offset |
| Persona 3 Portable | [PC overlapping-archive conflict](https://gamebanana.com/mods/423473) | Another PC mod shares `init_free.bin` with Controller UI Overhaul, creating conflicts despite touching a different sprite | Never overwrite an entire parent archive based on one glyph edit without merging all referenced data |

## Format-family priority for title-by-title coverage

1. **Atlus/Persona (SPR/CPK/BIN, SPD)**: P3P, P5R, P4AU and adjacent Switch titles. Extract names and sprite data; translate meanings via PC PS/Nintendo variant pairs. Test merging of parent archive, localized layouts, each update.
2. **Unreal (PAK/UAsset/UMAP)**: Bravely Default II and games from the wider Switch library. Search mod file tree and Unreal object path; compare exported UTexture2D from both platform builds. Preserve engine version, cooked texture platform encoding and mip levels.
3. **Unity (resources.assets/Texture2D)**: BALL x PIT already has exact Switch title and Texture2D `controller_btns_outlined`. PC/Switch archives may expose an analogous logical asset name but must be independently verified. Use the existing exported-image comparison, never assume identical texture coordinates.
4. **Nintendo custom UIs (BNTX/BFRES/BFLYT, BLARC/SARC, ZSTD)**: BOTW Wii U vs Switch and TOTK Switch-only. Wii U art can reveal scenes and controls; byte and swizzle layouts differ. Nested SARC→BNTX inventory is read-only.
5. **Nontexture prompts**: Tokyo Mirage Sessions and titles using fonts, layout nodes, text, programmatic glyphs or 3D meshes. Atlas matching cannot claim full coverage.

## Use three exported images to prove a possible cross-platform geometry match

The following command requires independently acquired/extracted original game textures. All images must be legally accessible on the local computer. No source game assets are stored in GitHub.

```bash
python3 tools/ps-glyph-cross-platform-image.py \
  --source-original /path/pc/original_controller_texture.png \
  --source-modified /path/pc/modded_controller_texture.png \
  --switch-original /path/switch/original_controller_texture.png \
  --switch-game 'Persona 5 Royal (Switch)' \
  --source-platform 'PC' --scene 'menu' \
  --out /tmp/cross-platform-evidence.json
```

The script compares **the original PC image to the original Switch image**. It returns possible changed-pixel XYWH regions **only when their decoded dimensions and all rendered RGBA pixels match** (invisible RGB under alpha=0 ignored). If pixels or size differ, `switch_candidate_rects_xywh` stays `null`. This is intentionally strict, not an AI-based semantic button detector. Even an identical image still needs exact Switch source SHA, container identity, active game update, icon naming, layout/scene proof and PS5 visual tests before activation. It never emits an enabled glyph pack.

See the synthetic-only regression files `tools/check-ps-glyph-cross-platform-image.py` and `tools/check-ps-glyph-mod-diff.py`. **These were created, not run; no GitHub Actions, SDK build or PS5 execution was triggered.**

## Source admission protocol

* Store source platform and edition explicitly: PC Game Pass and Steam are distinct sources; BOTW Wii U and Switch are distinct content trees; original SMT V and Vengeance are distinct editions.
* Extract the mod author's real `source resource`, named sprite/texture, changed rectangles and layout variants if visible. An online description alone never proves pixel XYWH.
* Compare exact local game-asset hashes, image channel masks, sprite shape, scaling and origin. Qualify every menu/gameplay/tutorial/control context separately.
* Keep inferred geometry `null` unless the originals meet the strict cross-platform image or independent direct Switch image proof. Do not auto-enable a source mod as a PS5 emulator rule.
* Rights still constrain redistributing third-party art; technical knowledge and locally performed comparisons need no rehosting of game-owned asset bytes.

**Current status: 0 verified per-game in-game PlayStation art packs and 0 native PS5 glyph qualifications. Issues #7 and #8 remain open.**
