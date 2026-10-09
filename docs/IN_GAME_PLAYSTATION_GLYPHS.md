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

**PlayStation Auto** in Eden can switch its face-button interpretation
after sufficient gameplay motion. A *static RomFS image atlas* cannot
adapt to that menu→gameplay state automatically. One static symbol map
must not be asserted valid across both scenes without title-specific
verification; separate menu/gameplay atlases or a safe context-aware
replacement mechanism may be needed.

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
Source: https://zacksly.itch.io  
License: https://creativecommons.org/licenses/by/3.0/ (**CC BY 3.0**)  
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
- [Cross-platform source index](PS_GLYPH_CROSS_PLATFORM_INDEX.json): 10 additional publicly documented source references for six titles in the Switch corpus.
- [Multiplatform research guide](PS_GLYPH_MULTIPLATFORM_RESEARCH.md): BOTW Wii U layout variants, P3P PC/PSP sprites, P4AU four-controller variants, P5R PC L3/R3 bounding-box fix, Bravely Default II PC Unreal PAK Start/Select variants, SMTV edition mismatch caution.
- `tools/ps-glyph-cross-platform-image.py`: read-only three-input compare (other-platform original, other-platform mod, original Switch) returning tentative XYWH **only when the two original decoded images have identical rendered pixels/dimensions**.
- `tools/ps-glyph-platform-coverage.py`: generates research queue for every game in the Switch index, not just games with PC mods.
- `tools/ps-glyph-mod-inventory.py --platform PC ...`: source-path format hints for Unity/Unreal/CRI/Atlus/Nintendo family. These are names/extensions only, NOT decoded binary proof.
- Synthetic future checks `tools/check-ps-glyph-cross-platform-image.py`, `tools/check-ps-glyph-platform-coverage.py` not executed under no-build/run gate.

**Never directly import an original PC/Wii U/PSP replacement pack as a verified Switch/PS5 runtime rule.** The title ID, game update, original file SHA, per-screen button meaning and executable PS5 output must still be validated.
