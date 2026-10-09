# Eden Encore — PlayStation glyph discovery via PC / Wii U / PSP editions

Last research update: 2026-10-09. The Switch game stays the authority for **Title ID, exact update, RomFS resources, visual meaning and PS5 runtime**. Ports are discovery *sources*, never default plug-and-play replacements.

## Source registers

* Main Switch-only corpus: [PS_GLYPH_SOURCE_INDEX.json](PS_GLYPH_SOURCE_INDEX.json) — 26 community references / 18 games, zero verified atlas positions.
* Additional cross-platform corpus: [PS_GLYPH_CROSS_PLATFORM_INDEX.json](PS_GLYPH_CROSS_PLATFORM_INDEX.json) — 22 other-platform sources linked to 16 Switch 1 games (including ten Nintendo-confirmed seeds), zero verified Switch rectangles.
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

## Bonus: detect pre-embedded PlayStation artwork in Switch games

Some multiplatform ports include **unused PS/Xbox/Nintendo texture variants already in their Switch asset files**. Their presence is game-specific and cannot be presumed. Before downloading unrelated mods, run the new offline read-only filename-family inventory on an authorized local RomFS:

```bash
python3 tools/ps-glyph-builtin-platform-assets.py \
  --romfs /path/own-game/extracted/romfs \
  --out /tmp/builtin-platform-ui.json
```

The tool groups names such as `UI/controller_buttons_ps4.png`, `UI/controller_buttons_switch.png` and `UI/controller_buttons_xbox.png` **only as possible related UI resources**, with no pixel/read-time/semantic claims. It rejects unsafe symlinks, limits enumeration to 100,000 files, and never opens/decompresses asset bytes. Some games hide these names **inside BNTX/Unity/Unreal archives**; their corresponding metadata scanners are needed for deeper discovery.

**Priority route:** First discover embedded native art, next research existing other-platform mod and actual name/path, and finally compare original image geometry with the matching Switch original. Until then native glyph art remains unverified.

## 2026-10-09 — Initial eight Nintendo-confirmed Switch 1 titles

Eight official Switch game listings are preserved in [PS_GLYPH_SWITCH1_GAME_SEEDS.json](PS_GLYPH_SWITCH1_GAME_SEEDS.json). They have PC glyph mods but no verified Switch glyph pack: **Sonic Frontiers**, **Sonic Superstars**, **Overcooked! 2**, **Atelier Ryza**, **NieR:Automata The End of YoRHa Edition**, **Enter the Gungeon**, **Sonic Mania** and **Stardew Valley**.

| Switch 1 game | External source | Mechanism and qualification need |
| --- | --- | --- |
| Sonic Frontiers | https://gamebanana.com/mods/412767 | PC v1.5.1 fixes Nintendo A/B and X/Y swaps; v1.5 adds edge padding to prevent bleed; actual Switch atlas paths unknown |
| Sonic Superstars | https://gamebanana.com/mods/474430 | PC-only controller palette/contrast and PS5/PS4/Switch prompt variants; must identify Switch files separately |
| Overcooked! 2 | https://www.nexusmods.com/overcooked2/mods/8 | PC UnityPy installer replaces 35 textures by **existing native PlayStation art in PC files**, retaining dimensions and names; 847 other textures preserved per author. No guarantee these PS art files ship on Switch |
| Overcooked! 2 | https://www.nexusmods.com/overcooked2/mods/9 | PC BepInEx dynamic player/scene UI glyph binding; conceptual model for shared and per-player prompts, not portable plugin code |
| Atelier Ryza | https://github.com/Skyyblaze/Atelier-Ryza-PS4-Switch-Button-Replacement | PC Special K DDS overrides; input touchpad/share behavior may also require Steam Input, not a simple sprite change |
| NieR:Automata | https://steamcommunity.com/sharedfiles/filedetails/?id=1368483795 | PC data/ui custom Nintendo artwork resizes existing Xbox UI sprites; Switch assets differ until compared |
| Enter the Gungeon | https://modworkshop.net/mod/25536 | PC sprite folders and SREM/DFSprite dependency; cropped/resized art; no inferred Switch offset |

**Initial scope at this stage:** 26 Switch-mod references / 18 directly indexed games, plus 20 cross-platform sources touching 14 Switch titles; eight initial title seeds brought the union to **26 unique Switch 1 games**. See the newer 28-title update below. No real game packs qualified. All real verified per-game art counts remain ZERO.

### Relocated original sprites: strict matching despite atlas rearrangement

The new `tools/ps-glyph-relocated-sprite.py` accepts user-reviewed sprite rectangles from a modified PC/Wii U/PSP texture pair and searches the original Switch atlas for a **unique, exact, visible-pixel identical** original sprite. This can find the same icon where source and target atlases have different dimensions and layout. Duplicate matches, invisible-only originals, weak anchors or changed pixels cause a refusal, not an automated mod.

```bash
python3 tools/ps-glyph-relocated-sprite.py \
  --source-original /path/pc/original.png \
  --source-modified /path/pc/modified.png \
  --switch-original /path/switch/original.png \
  --source-rect 24,48,48,48 \
  --switch-game 'Overcooked! 2' --source-platform PC --scene tutorial \
  --out /tmp/relocated-proposals.json
```

The `24,48,48,48` rectangle is **only an illustrative example**, NOT a measured coordinate from Overcooked. A real successful match still does not prove icon meaning, title/update, RomFS container equivalence, legal redistribution or PS5 rendering. `check-ps-glyph-relocated-sprite.py` adds synthetic tests but was not run.

The shared pixel comparator also now protects low-opacity differences: a source/target with alpha=1 and even a single RGB unit changed is NOT treated as identical. Invisible RGB differences at alpha=0 are allowed because they are not drawn.

## 2026-10-09 — Unity Sprite coordinates directly from serialized metadata

Some Unity games have explicit `Sprite.m_Rect` and `Sprite.m_RD.textureRect` fields. These provide **engine-serialized candidate texture rectangle coordinates**, a stronger lead than guessing pixel positions from a mod description. The rectangle orientation and packed/sliced sprite mapping must still be validated against a decoded texture and actual frame. The method applies to Unity titles such as BALL x PIT and Overcooked! 2.

Using the independently maintained [UnityPy](https://github.com/K0lb3/UnityPy) package (optional dependency, inspect the project/release before local installation), read **authorized local** game assets without exporting or modifying textures:

```bash
python3 tools/ps-glyph-unity-inventory.py --asset-file /pc/Overcooked2_Data/resources.assets --platform PC --out /tmp/pc-ui-objects.json
python3 tools/ps-glyph-unity-inventory.py --asset-file /switch/romfs/Data/resources.assets --platform Switch --out /tmp/switch-ui-objects.json
python3 tools/ps-glyph-unity-pair.py --pc-report /tmp/pc-ui-objects.json --switch-report /tmp/switch-ui-objects.json --out /tmp/pc-switch-sprites.json
```

The `/switch/romfs/Data/resources.assets` path is **an illustrative placeholder**, NOT a verified Overcooked! 2 Switch file. Find the real file in an authorized extracted game first. The inventory records actual Unity object names, path IDs, Texture2D dimensions, and, when its Unity version exposes them, serialized Sprite rects. Matching object names or rect dimensions do **not** prove equal RGBA, normalised texture UVs, title/version or in-game semantic action.

The pair tool records PC and Switch Sprite geometry side by side and lists potential PlayStation-named source textures absent from the target inventory, as a **missing-source hint only**. Both tools are read-only: no .assets rewriting, no game binaries committed, and no source archive bytes redistributed. Synthetic tests `check-ps-glyph-unity-inventory.py` and `check-ps-glyph-unity-pair.py` were added but **not executed**.

### Two further Switch 1 titles discovered through PC modding

- **Sonic Mania** (Nintendo Switch 1 confirmed by Nintendo): [PC PlayStation glyph mod](https://gamebanana.com/mods/31279) author states unused PlayStation icons **already in original PC game data**. Investigate the original Switch Retro Engine resources for identical icons; author's keyboard mappings and context limitations cannot automatically become Switch semantics.
- **Stardew Valley** (Nintendo Switch 1 confirmed by Nintendo): [PC Content Patcher controller icon pack](https://www.nexusmods.com/stardewvalley/mods/25148) includes PlayStation/Xbox/Switch variants, and [Star Control - CustomisationPlus](https://www.nexusmods.com/stardewvalley/mods/40470) v1.1.7 adds a hot-reloadable PS spritemap. Those are **SMAPI/Content Patcher PC mechanisms**, not valid Switch runtime injection without separate evidence.

Both are research-only seed games. Their Nintendo release proof is in [PS_GLYPH_SWITCH1_GAME_SEEDS.json](PS_GLYPH_SWITCH1_GAME_SEEDS.json). The index now holds **22** other-platform sources and **28** total distinct researched Switch 1 games; no new real atlas has been qualified.

## From the researched title set toward the full Switch 1 Title ID catalogue

The researched titles are **research candidates**, not the size of the actual Nintendo Switch 1 library. Public metadata-only databases such as [blawar/titledb](https://github.com/blawar/titledb) (multi-region JSON metadata, Title IDs, version history) and [ch0c01dxyz/nsw-titledb](https://github.com/ch0c01dxyz/nsw-titledb) contain the necessary starting vocabulary. Their listings are not in-game texture resources.

New local, read-only importer: `tools/ps-glyph-switch1-titledb.py`. Supply a separately obtained TitleDB JSON file (Title ID to title dictionary, title-object list, or region/NSUID to title object). It only considers **Switch 1 base application-shaped** IDs beginning 0100 and ending 000. Ambiguous titles sharing a name retain `candidate_title_id: null`; fuzzy matches, updates, DLC and Switch 2 title prefixes are not upgraded into a guess. An actual installed game's Title ID and update still have to be checked against game data.

```bash
python3 tools/ps-glyph-switch1-titledb.py --title-db /path/authorized/titledb/titles.json --out /tmp/switch1-existing-research-ids.json
python3 tools/ps-glyph-switch1-titledb.py --title-db /path/authorized/titledb/titles.json --all-base-games --out /tmp/switch1-entire-base-title-research-backlog.json
```

The importer does not download the database automatically, does not change the runtime glyph catalogue, and never marks a title/version supported based on its name or ID. It can produce a backlog of candidate Switch 1 titles for future public mod discovery. The script accepts bounded external metadata and is **not executed** in this source-only pass; `tools/check-ps-glyph-switch1-titledb.py` adds synthetic assertions for ambiguity, update IDs, Switch 2 exclusions and regional duplicates.

## Real public GitHub mod release assets: reproducible forensic intake

The [official GitHub release metadata register](PS_GLYPH_OFFICIAL_MOD_RELEASES.json) now records TWO exact release assets, their release tag and size, and SHA-256 when provided by GitHub:

* BALL x PIT Switch mod release **2**, game version **1.251**, ZIP **3,131,472 bytes**, GitHub-published SHA-256 `44a99655acdccbef885fa25568dcc6c462264ae007653baa24095c2d83f0b9f5`. The author documents `Data/resources.assets`, Unity `controller_btns_outlined` Texture2D and Switch Title ID `010086A022444000`.
* Atelier Ryza PC icon release **1.6**, ZIP **118,893,347 bytes**. GitHub metadata does not provide a digest, so none is claimed.

Use the exact official [BALL x PIT asset URL](https://github.com/mircowuffwuff/ball-x-pit-nsw-ver-playstation-button-prompts/releases/download/2/ball-x-pit-nsw-ver-playstation-prompts-2-1.251.zip) only as input to a local, authorized ZIP inventory:

```bash
python3 tools/ps-glyph-mod-inventory.py \
  /path/ball-x-pit-nsw-ver-playstation-prompts-2-1.251.zip \
  --platform Switch \
  --expect-sha256 44a99655acdccbef885fa25568dcc6c462264ae007653baa24095c2d83f0b9f5 \
  --out /tmp/ball-x-pit-mod-zip-index.json
```

The CLI rejects mismatched ZIP bytes, dangerous member paths, duplicate/case-colliding entries and oversized files; it does not extract Unity resources or reproduce game artwork. **Important:** this session was able to read the authoritative GitHub release asset metadata but could NOT download the ZIP's actual bytes in the available environment. Therefore the archive content/Texture2D positions have not been inspected and remain unverified. Do not mark BALL x PIT as verified for Eden Encore.

## 2026-10-09 — Read actual controller UI layout code in Switch-1 games

Two more *confirmed Nintendo Switch 1 game titles*, **Balatro** and **Don't Starve Together**, have been added to the official title seed register, expanding the combined index to **28 Switch 1 research targets**, with **22 cross-platform technical sources covering 16 games** (and still zero qualifying Switch in-game mod packs).

### Don't Starve Together: concrete controller asset names AND UI label coordinates

A public Lua game script dump provides a complete platform-dependent art lookup, independently of mod packaging:

* [frontend.lua](https://github.com/taichunmin/dont-starve-together-game-scripts/blob/main/prefabs/frontend.lua): PS4 `images/ps4_controllers.xml` and `.tex`, Switch `images/nx_controllers.xml` and `.tex`, Xbox `images/xb1_controllers.xml` and `.tex`.
* [optionsscreen.lua](https://github.com/taichunmin/dont-starve-together-game-scripts/blob/main/screens/redux/optionsscreen.lua): `CONTROLLER_IMAGES[DEVICE_DUALSHOCK4] = controls_image_ds4.tex`, `[DEVICE_SWITCH] = controls_image_nx.tex`; menu-help labels refer to `STRINGS.UI.CONTROLSSCREEN` keys.
* [Extracted, indexed menu label positions](PS_GLYPH_DST_CONTROL_UI_POSITIONS.json) from that **public Lua script**: **17 PlayStation controller labels + 17 Switch controller labels** with actual `(x,y)` anchor coordinates, alignment, semantic string keys and source blob SHA. Example from code: DualShock4 `TOUCHPAD` label anchor `(20,275)`; `LEFT_SIDE=-415`, `RIGHT_SIDE=415`, `LABEL_WIDTH=320`, `LABEL_HEIGHT=50`.

**Critical distinction:** the Lua `(x,y)` are **menu text-label layout coordinates, NOT texture sprite pixel rectangles**. They may not apply to a particular Switch executable/update. Do not feed these screen positions into the ROMFS glyph atlas generator.

To inspect a legally extracted matching Klei XML atlas without running game code or decoding proprietary `.tex`:

```bash
python3 tools/ps-glyph-klei-atlas.py \
  --atlas-xml /path/legitimate/romfs/images/nx_controllers.xml \
  --texture-width 512 --texture-height 512 \
  --out /tmp/dst-switch-atlas-uv.json
```

The `512×512` dimensions above are a **synthetic example** and must first be measured from the actual game texture. The parser stores named **normalized UVs** from real XML and computes two distinct texel coordinate candidates (bottom-origin and top-origin), or NULL if UVs are not texel-aligned. It does **not** decide image orientation, verify `.tex` hashes or claim semantic button glyphs. Parser and regression fixture `check-ps-glyph-klei-atlas.py` have been added but **not executed**.

### Balatro: runtime glyph style rather than modified sprite art

[Mod Lua source](https://github.com/NopoTheGamer/BalatroControllerGlyphs/blob/main/ControllerGlyphs.lua) overrides `G.CONTROLLER.get_console_from_gamepad` so the PC game chooses `Playstation` rather than `Xbox` or `Nintendo`; the source also mentions `G.F_PS4_PLAYSTATION_GLYPHS`. This confirms one **PC runtime style-selector technique**, not the availability of the same hook or artwork in the Switch build.

[Provenance-locked selector evidence](PS_GLYPH_BALATRO_RUNTIME_SELECTOR.json) stores exact hook name, public source blob SHA, expected behavior and negative qualification flags. No Lua changes or binary patches were made to the user's original game.

Both games show why universal replacements must support **texture atlases, screen-layout components, per-platform asset selection, and context-sensitive runtime logic**, with separate evidence for every game version and original file.
