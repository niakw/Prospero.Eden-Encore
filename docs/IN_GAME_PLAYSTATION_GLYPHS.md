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

- `tools/ps-glyph-atlas.py discover`: lists candidate image/texture files
  in a local, extracted RomFS and identifies formats needing a separate
  decoder/encoder (BNTX, BFRES, SZS, DDS).
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
actual file hash and measured, non-overlapping **isolated glyph rectangles**.
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
