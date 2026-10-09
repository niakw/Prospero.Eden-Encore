# Eden Encore — Offline game-mod glyph reverse-engineering pipeline

Status 2026-10-09: **source-only implementation, not executed or PS5-qualified**. User-facing goal is graphical PlayStation prompts **inside games**, not just controller input or launcher icons. The exact source game/update and locally authorized files must match.

## Inputs and evidence levels

* `docs/PS_GLYPH_SOURCE_INDEX.json` is a list of **26 community mod references across 18 games**. These are leads, NOT installed assets, verified compatible titles, image rectangles, or proof that source files were fetched.
* Obtain legally usable original extracted game RomFS and a community mod ZIP or separately extracted folder. Do not include original Nintendo-owned bytes or unlicensed mod payloads in git.
* Keep distinct IDs: game **Title ID**, game **update version**, mod release version, ROMFS relative path, archive internal member, original/replacement SHA-256, and the screen-specific button semantics.
* Treat three positions separately: the **file/container offset in bytes**, the **texture/atlas rectangle in pixels**, and the **control action or prompt location in the game's UI context**. None implies the other automatically.

## Read-only inspection commands (local computer; NOT on PS5)

### 1. List the files present in a local mod ZIP

```bash
python3 tools/ps-glyph-mod-inventory.py /path/authorized-ps5-ui-mod.zip --out /tmp/mod-inventory.json
```

The ZIP archive is checked for path traversal, symlinks, duplicate paths, member size and count. This records member names, relative `romfs/` locations and ZIP CRC, but **ZIP CRC is not a content SHA-256**.

### 2. Determine exact changed-pixel positions on PNG/TGA resources

```bash
python3 tools/ps-glyph-mod-diff.py --mod-zip /path/authorized-ps5-ui-mod.zip --original-romfs /path/extracted-match/romfs --out /tmp/atlas-diff.json
```

The comparison opens both images in memory, hashes their exact file bytes and computes disconnected alpha-aware visible changed-pixel bounding boxes as `[x, y, width, height]` in **decoded** PNG/TGA pixels. It includes transparency-only changes, recognizes size changes, and reports proprietary/other formats as unsupported. The bounding boxes are **differences**, not yet renderer-ready rectangles or confirmed PS button names.

### 3. For .7z/.rar or mods installed as folders

After an authorized extraction (outside Eden), use:

```bash
python3 tools/ps-glyph-mod-folder-diff.py --mod-dir /path/extracted-community-mod --original-romfs /path/extracted-match/romfs --out /tmp/folder-diff.json
```

It refuses symlinks, hidden/unsafe components and case-colliding resource paths, and compares PNG/TGA with the same engine as the ZIP tool. **Neither tool automatically extracts archives or modifies original files.**

### 4. For BNTX/BFRES/BLARC and compressed Nintendo game assets

Inspect an actual BNTX file without decoding/replacing its textures:

```bash
python3 tools/ps-glyph-bntx-inspect.py /path/decompressed/__Combined.bntx
```

It inventories BRTI texture names/formats/mip counts and, when present, byte offsets of the BRTI headers, mip pointer tables and mip image data. These are **container file offsets, never pixel coordinates**. It does not parse BFRES, untile memory, decompress BC/ASTC or rebuild mipchains.

For a **previously decompressed** SARC/BLARC:

```bash
python3 tools/ps-glyph-sarc-inspect.py /path/decompressed/Common.blarc --out /tmp/sarc-members.json
```

The tool reads the SARC/SFAT/SFNT archive structure to enumerate internal names, absolute byte offsets and lengths without extracting files.

When the decompressed archive embeds `__Combined.bntx` or other named BNTX files, perform a **nested read-only scan without writing/extracting members**:

```bash
python3 tools/ps-glyph-sarc-bntx-chain.py /path/decompressed/Common.blarc --out /tmp/combined-texture-chain.json
```

This reports both the SARC member's absolute byte offset and each embedded BRTI texture's name, dimensions, format and mip byte pointers translated into positions within the outer decompressed SARC. **All offsets remain byte offsets, not XYWH texture pixel coordinates.** BNTX decode/repack/ASTC/BC/mip stability is still outside this source-only implementation.

**Known public TOTK research lead:**

```text
RomFS/UI/LayoutArchive/Common.Product.110.Nin_NX_NVN.blarc.zs
    [dictionary-aware Zstandard decompression, external step]
      Common.Product.110.Nin_NX_NVN.blarc (SARC/BLARC)
        __Combined.bntx
          Nt_KeyTexA_00^d.bftex   (community-reported texture)
```

This location was published in a comment on https://gamebanana.com/mods/443260 ; it has **not** been verified byte-for-byte in Eden. The `.zs` decompression may require the game dictionary from `romfs/Pack/ZsDic.pack.zs` (https://github.com/TotkMods/Research). External TkZstd provides a dictionary-aware tool (https://github.com/TotkMods/TkZstd). Do not assume all `.zs` files use the same dictionary. The SARC reader must receive an already decompressed archive, and embedded BNTX may be inventoried directly with the bounded read-only SARC-BNTX chain parser.

### 4b. Unity/other proprietary containers with external texture export

A documented BALL x PIT mod gives a useful exact **Unity asset identity**:

```text
Title ID: 010086A022444000
Game version reported by author: 1.251
RomFS container: Data/resources.assets
Unity Texture2D: controller_btns_outlined
Tools: AssetStudioMod (original texture export), UABEA (edited Texture2D)
Mod: https://github.com/mircowuffwuff/ball-x-pit-nsw-ver-playstation-button-prompts
```

The author describes replacing face buttons, L1/R1, L2/R2 and D-pad, while *not* replacing Start/Share because their atlas rectangles fit differently. They tested Eden Android 0.1.1, **not PS5/Eden Encore**. The original game reportedly already includes official PlayStation prompts; this is **author testimony only**, not proof those textures can be automatically selected at runtime on Switch.

Once both original and patched `Texture2D` have been legitimately exported as matching PNG files:

```bash
python3 tools/ps-glyph-exported-texture-diff.py \
  --original-image /path/original/controller_btns_outlined.png \
  --modified-image /path/modded/controller_btns_outlined.png \
  --texture-name controller_btns_outlined \
  --container Data/resources.assets \
  --out /tmp/ball-x-pit-texture-regions.json
```

The output provides visible changed-pixel bounding boxes and export image SHA-256. **It does not establish hashes of original/patched Unity resource containers, nor safely rebuild them.** This externally decoded approach also works with texture pairs exported from BNTX/BFRES by a separate licensed tool. Never mistake changed pixel rectangles for named glyph identities until each is visually identified and checked in context.

### 5. Identify semantics and generate a reversible game-specific pack

Only after the exact source atlas, game/update, intended context and Nintendo-to-PlayStation glyph identity are verified:

```bash
python3 tools/ps-glyph-scan.py --original-romfs /path/extracted-match/romfs --title-id 01007EF00011E000 --update-version 1.0.0 --spec-out /tmp/UNVERIFIED-draft.json
python3 tools/ps-glyph-atlas.py render --original-romfs /path/extracted-match/romfs --icons-zip '/path/PS5 Button Icons and Controls.zip' --spec /path/reviewed-spec.json --out /path/new-pack-dir
python3 tools/ps-glyph-pack.py verify --pack /path/new-pack-dir --original-romfs /path/extracted-match/romfs --title-id 01007EF00011E000
```

The title/version values above are **synthetic examples**, not compatibility claims. A newly generated atlas rectangle must include transparent safety margins, exact original SHA and an explicitly reviewed PlayStation button name. Validate **menu, HUD, battle, tutorial, idle/inactive button, +/−, L/R/ZL/ZR, touchpad/options and scene-specific controls** separately. Game scripts can remap A/B/X/Y across scenes, and standalone artwork cannot automatically follow all `PlayStation Auto` input transitions.

Installed-pack permission/attribution applies to adapted PlayStation source art and third-party mods as required by their licenses. Indexing names/path structures is different from redistributing bytes. No original game files or unlicensed mods should enter the repository.

## Minimum qualification gate for a real source entry

1. Fingerprint game `title_id + actual update + original file SHA-256` and source archive SHA-256.
2. Distinguish `mod archive path`, `romfs_path`, SARC internal member, BNTX internal texture, file byte offsets and pixel `rect_xywh`.
3. Confirm each region corresponds to a **particular glyph**, not a palette, background, font or unrelated modified sprite.
4. Confirm the correct PS physical/semantic mapping **for each scene**; update source index only with verified evidence.
5. Render and roundtrip the full required format, preserve mipmaps, swizzle/tiling, layout and compression, and verify no unintended changes.
6. Stage reversible LayeredFS assets, verify hash gates, and visually test actual game/version on PS5 firmware 13.60 before marking supported.

### Explicit remaining gaps

* No third-party mod archive was downloaded/unpacked during this source-only pass.
* Pixel rectangles are only generated **when matching original PNG/TGA and mod bytes are provided**. The 26 source index entries intentionally have `rect_xywh: null`.
* Direct editing/injection of BNTX, BFRES, BF(L)YT, BF(L)AN, fonts, ASTC/BC or dictionary compressed `.zs` remains unimplemented in this pass.
* Synthetic Python fixture scripts were created but **not executed** by request; no GitHub Actions, PS5 build or firmware runtime tests were invoked. Issues #7 (glyphs) and #8 (performance/JIT/GPU) remain open.

### 2026-10-09 — Additional proprietary container and nontexture cases

* **Persona 3 Portable (Switch)**: actual nested path from the mod author's published process: `data_EN/umd0.cpk` → `init_free.bin` → `init/camp.bin` → `pc_button.spr`, using CPK File Builder / Amicitia. A direct RomFS PNG patch cannot rebuild this proprietary packaging. Standard documented mapping is A→Circle, B→Cross.
* **Tokyo Mirage Sessions #FE Encore**: its author reports a world `Check` prompt that is **not texture-backed** and Start/Select/PS whose sprite slots do not fit. These must remain unsupported by an atlas-only path, even if all texture swaps succeed.
* Technical index now covers **26 community sources / 18 games**, while keeping every unverified XYWH as null and requiring per-version hardware evidence.

## 6. Expand the exact Switch title with PC/Wii U/PSP remakes or ports

Use [cross-platform index](PS_GLYPH_CROSS_PLATFORM_INDEX.json) and [multiplatform guide](PS_GLYPH_MULTIPLATFORM_RESEARCH.md). Particularly useful: BOTW Wii U layout differences, P3P PC original of the Switch mod, P4AU PS/Switch/Arcade variants, P5R PC L3/R3 bounding box bug fix and Bravely Default II PC Unreal PAK icon variants.

```bash
python3 tools/ps-glyph-mod-inventory.py --platform PC /path/authorized-pc-mod.zip --out /tmp/pc-mod-contents.json
python3 tools/ps-glyph-cross-platform-image.py \
  --source-original /path/pc/original-texture.png \
  --source-modified /path/pc/modded-texture.png \
  --switch-original /path/switch/original-texture.png \
  --switch-game 'Persona 5 Royal (Switch)' \
  --source-platform PC --scene menu --out /tmp/cross-platform.json
python3 tools/ps-glyph-platform-coverage.py --out /tmp/switch-cross-platform-worklist.json
```

Only exact same-size and same rendered-pixel original textures produce **candidate** Switch rectangle transfer. A renamed texture or shared game engine never qualifies an offset. The output never proves correct button semantics, original Switch container binding, original game update or PS5 gameplay.

The check scripts `tools/check-ps-glyph-cross-platform-index.py`, `tools/check-ps-glyph-cross-platform-image.py` and `tools/check-ps-glyph-platform-coverage.py` are source-only and have NOT been executed. No GitHub Actions/native builds have been triggered.

### Cross-platform coverage beyond known Switch mods

[Ten independently listed Switch 1 games](PS_GLYPH_SWITCH1_GAME_SEEDS.json) can be researched from external PC glyph mods even though no Switch-specific mod has been confirmed. The joint [22-source cross-platform register](PS_GLYPH_CROSS_PLATFORM_INDEX.json) now covers 16 target games, and the worklist generator includes 18 games with Switch mods plus ten seeded games. For different atlas arrangements, `tools/ps-glyph-relocated-sprite.py` compares each exact original sprite rectangle against candidate Switch texture regions and rejects every absent or ambiguous match. This does NOT perform platform resource repacking or semantic button verification. Low-opacity RGB differences are detected exactly rather than rounded away.


## 10 October 2026 — Automated mod-diff → independent glyph sprite draft

The source index now covers **28 distinct Switch game families**, with 26
community-Switch references and 22 cross-platform references. These are
**technical candidates**, not 28 working PS5 glyph packs.

There is a new real-data handoff that removes much of the manual XYWH work
for *decoded, isolated RGBA* prompt sheets, without importing a mod's artwork:

1. Compare the legally obtained matching Switch original RomFS against an
   existing Switch PNG/TGA mod ZIP or installed mod folder:

   ```sh
   python3 tools/ps-glyph-mod-diff.py \
     --mod-zip /authorized/switch-ui-mod.zip \
     --original-romfs /authorized/extracted-switch-romfs \
     --out /work/verified-image-differences.json
   ```

2. Reconcile changed-pixel components against independently scanned
   **original** alpha-isolated Switch sprites. A changed pixel is not
   automatically a complete button sprite. This step assigns **no** actions:

   ```sh
   python3 tools/ps-glyph-diff-to-evidence.py \
     --diff-report /work/verified-image-differences.json \
     --original-romfs /authorized/extracted-switch-romfs \
     --title-id 01007EF00011E000 \
     --update-version 1.6.0 \
     --profile playstation --scene world_interaction \
     --out /work/botw-world-interaction-UNAPPROVED.json
   ```

   The above BOTW parameters are **only an example of CLI invocation**.
   Public source material does not prove that BOTW has PNG/TGA UI resources
   ready for the scanner. It typically uses Nintendo compressed containers;
   it cannot be qualified with this PNG-only command unless an independently
   compatible decoded/assembled source is available.

3. For each unapproved slot, confirm the semantic **guest action** versus
   **physical controller face position** using actual game scene behavior;
   reject ambiguous/unmatched regions. Only after checking original version,
   PS5 static input profile, ownership/rights and the output renderer may
   the approved records enter `tools/ps-glyph-reconstruct.py spec`, then
   `tools/ps-glyph-atlas.py render`, pack verification and runtime catalogue.
   It is intentional that the draft's null `kind` is rejected by `spec`.

### BOTW Switch Yaz0/BLARC/BNTX inventory without extracting original bytes

BOTW packs often use Yaz0-wrapped SARC archives (`.sblarc`, `.ssarc`),
including original UI layouts and texture containers:

```sh
python3 tools/ps-glyph-botw-yaz0.py \
  /authorized/extracted-switch-romfs/Layout/Example.sblarc \
  --out /work/botw-ui-archive-inventory.json
```

The example archive basename is intentionally **not** presented as a
verified BOTW resource path. The tool accepts either actual Yaz0-wrapped
or plain SARC data, bounds the decompressed output to 128 MiB, inspects
internal named members, and traverses embedded BNTX/BRTI metadata
without staging original assets. Nintendo SARC offsets, BRTI pointers and
compressed file byte positions are **not glyph XYWH pixel coordinates**.

For compressed BNTX/BFRES texture content, a independently qualified
decode + ASTC/BC block and swizzle-compatible repack is still needed before
claiming a playable original PlayStation UI port. Using a Wii U byte offset
directly on Switch assets or copying a CC BY-NC-ND mod's binary game resources
would be an unsupported and legally problematic shortcut.

Both automation bridges are covered by host-only synthetic CI
`.github/workflows/check-ps-glyph-reconstruct.yml`. A green run validates
the bridge and parser, **not** real-game graphic output, compatibility, legal
redistribution or playable FC27/BOTW framerate.


### Compare BOTW's actual compressed original and modded UI archives

The decode-only reader can now be used as a **paired diff**: it locates
precisely which SARC member and which named BNTX encoded texture bytes
changed between two authorized copies of the same Switch UI resource.
No mod sprite or game-owned graphics are copied into Eden's repository.

```sh
python3 tools/ps-glyph-botw-archive-diff.py \
  --original /authorized/Switch/original/Layout/SomeOriginal.sblarc \
  --modded /authorized/Switch/modded/Layout/SomeOriginal.sblarc \
  --out /work/botw-ui-member-encoded-diff.json
```

`SomeOriginal.sblarc` is an illustrative name; choose a real matching
original/mod RomFS resource using the actual mod archive inventory. The
output has original/mod container SHA-256, changed member names, embedded
BNTX texture name/format/mip data fingerprints when verifiably bounded, and
**null pixel rectangle geometry**. Structural changes, unsupported formats,
unknown texture regions and changed containers cannot be promoted as
playable icons.

This identifies *where to focus* a legal, independent Switch Toolbox/Hyrule
Builder export/edit/repack with the existing Zacksly art. The next strict
gate is actual decoded original texture pixel geometry and action semantics;
`ps-glyph-diff-to-evidence.py` does that only for genuine original
RGBA PNG/TGA RomFS atlases, not BNTX binary offsets. Any changed modded
archive must still pass game/update matching, repack equivalence,
controller-session mapping and on-console screenshots.

No native PS5 run, gameplay benchmark or 28-title compatibility claim is
inferred from these host tests.


## October 10: direct Switch mod ZIP → actual glyph XYWH → independently authored PS art

**Important progress:** for existing Switch RomFS controller-UI mods such as
[BOTW DS4 UI Western Layout v2](https://gamebanana.com/mods/659253),
the MOD ITSELF already includes the modified texture resources and,
when compared with an original matching game/update, identifies the exact
source sprite positions. There is no reason to hand-transcribe every
PS4/Wii U game-screen anchor. The new tools use real decoded Switch
mod/image differences instead:

```sh
# No extraction and no mod graphic data is checked into GitHub.
python3 tools/ps-glyph-mod-zip-positions.py \
  --mod-zip /authorized/BOTW_DS4_UI_Western_standalone.zip \
  --original-romfs /authorized/Switch/BOTW_matching_original_RomFS \
  --scene world_interaction \
  --out /work/botw-mod-texture-positions.json

# Produce per-resource build plans using those original Switch pixels.
# Do NOT manually invent atlas texture coordinates.
python3 tools/ps-glyph-mod-auto-plan.py \
  --zip-positions /work/botw-mod-texture-positions.json \
  --title-id 01007EF00011E000 --update-version 1.6.0 \
  --out /work/botw-glyph-plans-unapproved.json
```

The names above illustrate locations, not downloaded files or confirmed
resource names/version in the actual release. The Standalone RomFS and
UKMM distributions have different containers and may expose resource
paths differently; unknown `.sbactorpack` / `.bfres` etc are reported
rather than silently skipped.

A changed modded ASTC texture is decompressed and compared with the decoded
original in-game UI texture. `ps-glyph-botw-mod-texture-positions.py`
reports actual pixel-difference components and alpha-isolated candidate
original Switch glyph rectangles. These are true original-texture XYWH,
not byte offsets, screen coordinates, or guesses from a PC screenshot.
Each unchanged texture is omitted. Unsupported ASTC layouts and non-SARC
formats are logged as unresolved with filenames.

The *action semantics* are separate: Nintendo game action A→PS Cross,
B→Circle, X→Square, Y→Triangle in Eden's fixed PlayStation session.
A controller drawing's physical right position is **Circle**, not "action
A" unless its own scene confirms that relation. Clearly named
`control_a_prompt`/ `button_b` textures supply a tentative label; other
sprites remain unlabeled. Human/independent game-scene confirmation of
this label is the last safety boundary, **not** a request to remeasure
the texture coordinates.

When explicit scene bindings have been checked, place their keyed records
in a small JSON file, for example:

```json
{
  "Layout/SomeUI.sblarc|__Combined.bntx|control_a_prompt|0": {
    "reviewed": true, "kind": "guest_action", "guest_button": "a"
  }
}
```

Only keys returned by the *actual original/mod ZIP* are valid, so
`SomeUI.sblarc` is not asserted to be a real BOTW path.

```sh
python3 tools/ps-glyph-mod-auto-plan.py \
  --zip-positions /work/botw-mod-texture-positions.json \
  --title-id 01007EF00011E000 --update-version 1.6.0 \
  --bindings /work/reviewed-action-bindings.json \
  --emit-approved-index 0 \
  --approved-out /work/botw-specific-reviewed-glyphs.json \
  --out /work/botw-reviewed-glyph-plans.json

python3 tools/ps-glyph-botw-auto-pack.py \
  --original /authorized/Switch/BOTW_matching_original_RomFS/Layout/SomeUI.sblarc \
  --spec /work/botw-specific-reviewed-glyphs.json \
  --icons-zip /authorized/PS5_Button_Icons_and_Controls.zip \
  --out /work/SomeUI.modified.sblarc \
  --report /work/SomeUI.receipt.json

python3 tools/ps-glyph-botw-stage-pack.py \
  --original-romfs /authorized/Switch/BOTW_matching_original_RomFS \
  --modified-archive /work/SomeUI.modified.sblarc \
  --receipt /work/SomeUI.receipt.json \
  --romfs-path Layout/SomeUI.sblarc \
  --title-id 01007EF00011E000 --update-version 1.6.0 \
  --pack-out /work/BOTW-Glyphs-STAGED-NOT-INSTALLED
```

The regenerated Yaz0/SARC archive changes only intended BNTX ASTC
128-bit compressed blocks, preserving the other SARC members and
unmodified texture bytes. Validated local pack manifests carry original
and replacement SHA-256, game title/update, and CC BY icon attribution.
The runtime still has **zero built-in published title rules**:
these are offline candidate packs, never automatically installed and
never declared usable without evidence on a real Switch title/update
and PS5 screenshot. Mod reference art is analyzed locally, **not
redistributed or copied** (Western Layout mod CC BY-NC-ND).

Testing:
`.github/workflows/check-ps-glyph-reconstruct.yml` checks the entire
synthetic original/modded ASTC→Yaz0/SARC→independent PlayStation art→
local LayeredFS pack path, including ZIP intake and normalized mappings.
None of that is a native PS5 FPS, visual-quality, or controller test.
