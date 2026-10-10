# Eden Encore — PlayStation glyphs **inside games**

## Goal

Use **PS5 Button Icons and Controls** by Zacksly as the single shared
source of PlayStation icons for *every title we can qualify*. This is
distinct from the launcher controller picture, DualSense electrical/HID
mapping, and the emulator's own overlay or footer.

### What is universal, and what is not?

The **art library, conversion/installation pipeline and runtime selector**
are reusable across games and game versions.

Individual Switch titles do **not** share a guaranteed button-image resource.
Nintendo A/B/X/Y/L/R prompts can be encoded in BNTX, BFRES, DDS, PNG, TGA,
inside larger animated atlases, in fonts, or drawn procedurally. A blind
global replace risks changing decorative art, corrupting the renderer or
assigning the wrong button. A default of **Nintendo-original art** is
required until a replacement is qualified for a concrete game/build.

**Current built-in catalogue: 0 qualified titles** in
`headless/glyph_overrides_generated.h`. Adding a picture to the launcher
does not change this count.

## Shared offline tools

- `tools/ps-glyph-atlas.py discover`: ranks likely input/UI/HD button
  atlas resources across a local extracted RomFS, and returns exact SHA-256
  for compatible RGBA images. Discovery is ranked by button/controller/prompt
  names **before** the top-200 cap: it no longer depends on filesystem order.
- `tools/ps-glyph-scan.py`: finds transparent, isolated potential glyph
  rectangles in RGBA atlases, outputs a read-only JSON report and optionally
  an intentionally **unapproved** render-spec draft with `"button": null`.
  The scanner does not identify the Nintendo glyph or choose a PlayStation
  button. A person or separately qualified recognizer must fill each slot.
- `tools/ps-glyph-bntx-inspect.py`: reads Nintendo BNTX/NX container texture
  tables and bounded BRTI headers (texture name, width/height, format, mip
  count, tile mode); integrated into scanner reports. **Inspection only:**
  this does not unswizzle, decompress or repack BNTX, BFRES, SZS or DDS.
- `tools/ps-glyph-atlas.py render`: reads **the exact user-supplied ZIP**
  locally, validates original RGBA PNG/TGA image SHA-256 and explicit,
  non-overlapping sprite rectangles; composites licensed PlayStation icons;
  writes a **versioned, SHA-256-bound pack** with attribution.
- `tools/ps-glyph-pack.py verify/install`: existing vetted LayeredFS staging
  pathway; requires the matching original game RomFS. This is not included
  in the distribution, and no original Nintendo resources are shipped.
- `tools/ps-glyph-catalogue.py`: merges any number of verified game/version
  pack manifests with an existing catalogue; increments revision above
  native built-in revision, never overwrites an existing catalogue by
  accident and preserves already supported titles.

The generator runs on a PC/Mac with **Python 3 and Pillow**; it is not
executed on the PS5 during gameplay. No work is added to the GPU frame loop.

### 1. Identify candidate graphics

```sh
python tools/ps-glyph-atlas.py discover --original-romfs /local/FC27-romfs
```

An entry marked `PROPRIETARY` requires a qualified texture-format-specific
decoder/repacker before it can join this pipeline. Merely finding a BNTX
filename does not mean the game displays a Nintendo button atlas.

For the common RGBA sprite-sheet case, generate a **read-only candidate
inventory** and a deliberately incomplete spec containing the exact
coordinates. The title ID and version below are **illustrative**, not FC27:

```sh
python tools/ps-glyph-scan.py \
  --original-romfs /local/game-romfs \
  --title-id 0100000000000001 --update-version 1.0.0 \
  --out /local/glyph-candidates.json \
  --spec-out /local/glyph-map-UNAPPROVED.json
```

The scanner reports both `candidate_atlases` and `bntx_containers`.
Open the candidate atlas images yourself, identify the actual Nintendo
buttons and choose the correct PlayStation symbols. Every proposed sprite's
`button` is `null` until that step. `render` rejects such null buttons.

To inspect one BNTX texture table directly, without modifying it:

```sh
python tools/ps-glyph-bntx-inspect.py /local/game-romfs/UI/button_textures.bntx
```

Only recognized and structurally valid NX/BRTI containers are reported.
The BNTX inventory is based on public BNTX documentation (3DSkit and
BNTX-Injector) and is not a promise that every proprietary format, swizzle,
compression mode or internal asset name is understood.

### 2. Declare game/update-specific graphic replacements

Create a JSON spec. **Illustrative coordinates and hash only**, not a
confirmed FC27 rule:

```json
{
  "schema": 1,
  "title_id": "0100000000000001",
  "update_version": "1.0.0",
  "variant": "outline-white",
  "atlases": [
    {
      "romfs_path": "UI/controller_prompt.png",
      "original_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "slots": [
        {"button": "cross", "rect": [12, 10, 48, 48]},
        {"button": "circle", "rect": [68, 10, 48, 48]}
      ]
    }
  ]
}
```

A real pack **must** use a game title ID, exact game update version,
actual file hash and measured, non-overlapping **isolated glyph rectangles**,
including at least a **one-pixel fully transparent margin** around each
sprite within its rectangle. This prevents trimming neighboring artwork.
The generator rejects an atlas which changed after its hash was recorded.
Only plain RGBA PNG/TGA graphics with transparency in each glyph region are
accepted. It does **not** convert arbitrary formats, strip a texture
container, or guess the meaning of on-screen controls.

`button` is the **desired visible PlayStation symbol** in that sprite
rectangle. It is *not* inferred from Nintendo A/B labels. For example:

| Display policy | Nintendo A | Nintendo B | Nintendo X | Nintendo Y |
| --- | --- | --- | --- | --- |
| **Physical-position** Switch-to-DualSense | Circle (right) | Cross (bottom) | Triangle (top) | Square (left) |
| **Cross-confirm PlayStation menus** | Cross (confirm) | Circle (cancel) | Depends on game | Depends on game |

**Current Eden PS5 controller policy is static for each game session**:
the default PlayStation profile maps the Switch guest **A to Cross (bottom)**,
**B to Circle (right)**, **X to Square (left)** and **Y to Triangle (top)**.
The separate Switch-position profile maps guest A to Circle, B to Cross,
X to Triangle and Y to Square. No runtime PlayStation Auto layout switching
exists; a visual glyph pack must match the *selected session input mapping*.
Drawing a Nintendo A prompt on the right when the corresponding action is
physically on Cross is misleading even when guest controls technically work.

**BOTW Switch-specific lead:** [DS4 UI Mod v2 Western Layout](https://gamebanana.com/mods/659253)
reports both in-world interaction-prompt corrections and menu/tutorial art,
including Cross↔Circle and Square↔Triangle graphic swaps. The author's
Western layout is a useful reference for the PS5 Cross-confirm profile,
not proof of compatibility with the current Eden build. License CC BY-NC-ND:
do not import or redistribute those mod bytes without adequate permission.
The original matching Switch game assets, update version and measured
changed glyph regions remain unverified. Record the source as a lead;
do not add a fake active rule to the built-in catalogue.

### 3. Build and verify (offline)

```sh
python -m pip install Pillow
python tools/ps-glyph-atlas.py render \
  --icons-zip "/local/PS5 Button Icons and Controls.zip" \
  --original-romfs /local/game-romfs \
  --spec /local/game-ps-buttons.json \
  --out /local/ps-glyph-pack
python tools/ps-glyph-pack.py verify \
  --pack /local/ps-glyph-pack \
  --original-romfs /local/game-romfs \
  --title-id 0100000000000001
python tools/ps-glyph-pack.py install \
  --pack /local/ps-glyph-pack \
  --original-romfs /local/game-romfs \
  --mods-root /local/eden-files/mods \
  --title-id 0100000000000001
```

The installer copies a replacement atlas and `eden-glyph-pack.json`
outside the game's `romfs` directory, plus the Zacksly attribution if
present. The original game image remains owned by the user and is **not**
published or uploaded.

### Reuse identical UI atlases in another game/update

When two titles share the **identical original atlas bytes**, copy the
measured sprite coordinates without redrawing all rectangles:

```sh
python tools/ps-glyph-reuse.py \
  --source-spec /local/verified-original-game-spec.json \
  --target-romfs /local/other-game-romfs \
  --title-id 0100000000000002 --update-version 2.0.0 \
  --out /local/reused-UNAPPROVED.json
```

Every reused slot is unassigned by default. Only after checking the target
title's **actual menu and gameplay semantics** may you add
`--approve-same-semantics` to carry over its PS button labels. Reuse refuses
changed texture hashes and ambiguous duplicate matches; it never copies
game-owned texture bytes. Cross-title reuse is an optimization, **not**
evidence of universal glyph compatibility.

### 4. Activate the installed packs for multiple games

```sh
python tools/ps-glyph-catalogue.py \
  --pack /local/ps-glyph-pack \
  --pack /local/other-game-ps-glyph-pack \
  --out /local/encore-glyph-overrides.json
```

To preserve existing entries, also pass
`--existing /local/current-encore-glyph-overrides.json` and use a NEW
`--out` destination. Copy the finished JSON to Eden's configured
`encore-glyph-overrides.json`. In each supported game select PlayStation
in-game glyph artwork, enable mods, and do not use Safe Launch.

The per-title native selector in `headless/glyph_overrides_runtime.h`
confirms: matching title + running update version, enabled mod, unambiguous
mod directory, bounded evidence and SHA-256 of actual replacement assets.
If any gate fails, keep the **original game artwork**. This does not
authenticate the currently mounted original RomFS on the console; the
installer compares original source bytes on the user's machine.

## The next compatibility layer

To support BNTX/BFRES and other common Switch asset types, integrate a
**read-only format-aware extractor** and a repacker that preserves tile/swizzle,
mipmaps, compression, image dimensions and metadata. For actual *automatic*
detection, add offline bounded template analysis with confidence reporting,
manual approval for ambiguous symbols, and whole-game regression examples
before ever enabling replacements. A generic shader overlay of Cross/Circle
over detected letters is not equivalent to modifying a game's HUD assets.

No universal success has been claimed. On-console validation is still
required for both correct button semantics and rendering.

## License and attribution

**PS5 Button Icons and Controls — Zacksly**

- Source: https://zacksly.itch.io
- License: https://creativecommons.org/licenses/by/3.0/ (**CC BY 3.0**)
Adaptation: the selected icons are resized and composited into user-local
button atlas replacements. Any pack containing additional game artwork must
also respect that game's rights; **CC BY for Zacksly's icons does not
license Nintendo/publisher-owned image content**.

## Community-mod reverse-engineering references (2026-10-09, source-only)

- [Structured sources: 26 mod references, 18 games](PS_GLYPH_SOURCE_INDEX.json) — technical leads, not activated compatibility.
- [Game-specific architecture/paths](PS_GLYPH_MOD_TECHNICAL_ATLAS.md) — Unity BALL x PIT `Data/resources.assets/controller_btns_outlined`, Nintendo TOTK compressed BLARC/BNTX texture hierarchy, mapping variants.
- [End-to-end offline inspection procedures](PS_GLYPH_REVERSE_ENGINEERING_PIPELINE.md) — authorized local ZIP inventory, read-only mod versus original PNG/TGA diff, extracted .7z/.rar folder diff, externally decoded Unity/BNTX texture pair diff, decompressed SARC byte offsets and BNTX mip pointer inventory.
- New tools: `ps-glyph-mod-inventory.py`, `ps-glyph-mod-diff.py`, `ps-glyph-mod-folder-diff.py`, `ps-glyph-exported-texture-diff.py`, `ps-glyph-sarc-inspect.py`; research validation `check-ps-glyph-community-index.py`.
- **Do not confuse byte offsets, changed-pixel XYWH boxes, actual icon semantic labels, the controller input mapping or game title/update validity.** They are separate evidence levels. No community archive has been unpacked here, no real atlas position is verified and no code/test/native build was executed.

## Same-title PC / Wii U / PSP source discovery (2026-10-09)

The Switch game/version and its original RomFS remain authoritative. Cross-platform art is discovery data until pixel or sprite/container equivalence is measured on the Switch version. See:
- [Cross-platform source index](PS_GLYPH_CROSS_PLATFORM_INDEX.json): 22 other-platform references for 16 relevant Switch 1 titles, including ten Nintendo-confirmed seeds absent from the Switch-mod index.
- [Multiplatform research guide](PS_GLYPH_MULTIPLATFORM_RESEARCH.md): BOTW Wii U layout variants, P3P PC/PSP sprites, P4AU four-controller variants, P5R PC L3/R3 bounding-box fix, Bravely Default II PC Unreal PAK Start/Select variants, SMTV edition mismatch caution.
- `tools/ps-glyph-cross-platform-image.py`: read-only three-input compare (other-platform original, other-platform mod, original Switch) returning tentative XYWH **only when the two original decoded images have identical rendered pixels/dimensions**.
- `tools/ps-glyph-platform-coverage.py`: generates research queue for every game in the Switch index, not just games with PC mods.
- `tools/ps-glyph-mod-inventory.py --platform PC ...`: source-path format hints for Unity/Unreal/CRI/Atlus/Nintendo family. These are names/extensions only, NOT decoded binary proof.
- Synthetic future checks `tools/check-ps-glyph-cross-platform-image.py`, `tools/check-ps-glyph-platform-coverage.py` not executed under no-build/run gate.

**Never directly import an original PC/Wii U/PSP replacement pack as a verified Switch/PS5 runtime rule.** The title ID, game update, original file SHA, per-screen button meaning and executable PS5 output must still be validated.

### Multiplatform original artwork inventory

The new `tools/ps-glyph-builtin-platform-assets.py` can group **candidate** PS/Xbox/Switch artwork names already embedded in a locally extracted game RomFS (no extraction/texture decoding or writes). When an identical UI asset exists on another platform, `tools/ps-glyph-cross-platform-image.py` can propose coordinate rectangles *only after* exact decoded rendered-image equivalence. These steps expand discovery, **not** the number of supported Switch games. See [multiplatform guide](PS_GLYPH_MULTIPLATFORM_RESEARCH.md). Synthetic tests `tools/check-ps-glyph-builtin-platform-assets.py` were added but not executed.

The exact-match relocation tool `tools/ps-glyph-relocated-sprite.py` searches for one uniquely matching original sprite in a rearranged Switch atlas, retaining null positions when nothing matches or multiple occurrences match. Ten additional officially listed Nintendo Switch 1 games are indexed separately in [PS_GLYPH_SWITCH1_GAME_SEEDS.json](PS_GLYPH_SWITCH1_GAME_SEEDS.json), without falsely inventing Switch glyph mods. Synthetic source fixtures were added, not executed.

### Unity engine UI sprites and true serialized geometry (source-only)

New read-only inspector `tools/ps-glyph-unity-inventory.py` optionally uses UnityPy to enumerate actual `Texture2D` and `Sprite` objects in locally provided authorized .assets files. It reports **engine-serialized** `Sprite.m_Rect` / `m_RD.textureRect` when available, not guessed screenshots. `tools/ps-glyph-unity-pair.py` matches PC and Switch object names and presents their own rectangle coordinates, without assuming the original atlases share positions. See [multiplatform guide](PS_GLYPH_MULTIPLATFORM_RESEARCH.md) for source commands, version/coordinate-origin warnings and the Overcooked/BALL x PIT research path. No actual Unity .assets file has been inspected or qualified in this session, and corresponding host checkers have not been executed.

### Full Nintendo Switch 1 Title ID metadata discovery

New `tools/ps-glyph-switch1-titledb.py` accepts a **user-supplied local TitleDB JSON export** to resolve the 28 researched Switch 1 game names by strict non-ambiguous matching. Its optional `--all-base-games` mode generates a metadata-only backlog to expand mod discovery across the broader Switch 1 catalogue without including ROMs or image assets. Base-title ID candidates remain unverified until checked against an actual installed game and update. See [multiplatform research](PS_GLYPH_MULTIPLATFORM_RESEARCH.md). The matching/ambiguity synthetic tests have been added but not executed.

### Latest 2026-10-09 source-verified controller layout and native atlas parsing

- **28 researched Switch 1 titles, 22 multiplatform references** across 16 of the researched games; still 0 native validated PS5 glyph packs. The [Nintendo-certified title seed list](PS_GLYPH_SWITCH1_GAME_SEEDS.json) now includes **Balatro** and **Don't Starve Together**.
- [DST public script coordinates](PS_GLYPH_DST_CONTROL_UI_POSITIONS.json): 17 DualShock4 and 17 Switch menu-help label coordinate records, text semantic identifiers, labels' local X/Y rendering formula, and source screen parent transform. These are actual **Lua UI-layout positions** from a public script dump, never claimed to be texture XYWH nor confirmed Switch executable positions.
- [Balatro public runtime glyph selection](PS_GLYPH_BALATRO_RUNTIME_SELECTOR.json): the Steamodded PC code overrides `G.CONTROLLER.get_console_from_gamepad()` with a `Playstation` style. The Switch version still needs binary/version evidence.
- `tools/ps-glyph-klei-atlas.py`: read a real authorized Klei XML atlas and preserve UV normalized coordinates plus both top-/bottom-origin XYWH candidates with externally measured .tex dimensions. `tools/ps-glyph-klei-atlas-pair.py`: join PS4 and NX XML reports by exact element name; this is metadata-only, not confirmed pixel identity or installability. Fixture sources added but not executed.
