# Native launch case artwork

The launcher has an optional, offline **two-faced retail case** presentation.
It runs only during the existing launcher-to-game handoff; it is not the game's
loading screen, does not intercept game input, and reports no fictitious percent.

## Priority, per face

1. Use a validated **actual local retail scan** for the selected game's title ID.
2. For a missing **front** use the game's existing cached icon/image and title in
   a stylized native case.
3. For a missing **back** create an **Eden-composed back** from locally cached
   gameplay screenshots, title, and localized description. This is not labelled
   as an official scan. If no screenshot exists, the cached icon is used.

## Automatic scans: public LaunchBox catalog

The build workflow obtains the public `Metadata.zip` from LaunchBox on its
**build host**. `tools/launcher/build-box-art-index.py` streams its XML and
generates only a compact **Switch** index (`ui/box-art-index.tsv`) containing
normalized game names and validated remote image basenames. The full database
is **never bundled with the app or downloaded on the console**.

When Home/Library performs its existing asynchronous Nlib media enrichment,
the same background worker also looks up the title in this index and downloads
available `Box - Front` / `Box - Back` JPEG/PNG files through the public
LaunchBox image CDN. The files are converted to the native cached TGA format,
stored under the game's title ID and reused offline. Each face is independent.
An existing manually supplied face always takes precedence. Missing images
retry after a bounded backoff; the launcher never waits for remote artwork.

Matching is **exact**, using an ASCII-normalized title and a ROM-name
fallback. Ambiguous catalog names are rejected; regions prefer France, Europe,
World, then other releases. No fuzzy match is used that could silently attach
an unrelated edition's artwork.

No API key or account is required. The source does not contain or redistribute
commercial scans; it only references images made available by the third-party
service. Their ownership and usage terms remain those of the rights holders.
The index builder intentionally ignores modern WebP-only entries until a
tested native decoder is available; those faces use the local composition.

If the optional external catalog is unreachable during compilation, the build
falls back to local images and Nlib without blocking the emulator build.
Nlib remains the source of existing **icons, banners, gameplay screenshots
and descriptions**, not physical back scans.

## Supplying original case scans

The local artwork directory is the same data/cache cover folder returned by
`Eden::CoversDir()` and already used for cached Nlib images.

Place either or both of the following files there, naming them after the
game's **16-digit uppercase hexadecimal title ID**:

- `box-front-01007EF00011E000.tga`
- `box-back-01007EF00011E000.tga`

Supported extensions, in fallback order: `.tga`, `.png`, `.jpg`, `.jpeg`.
Files can be replaced while the app is not running. Do not put downloads inside
the Git repository or native release packages. The displayed art is validated
for readable dimensions and bounded file sizes before it is queued for texture
decoding. An unavailable face never hides the other available face.

These filenames are examples of the naming contract, **not bundled scans**.
Use only covers you are allowed to use; the project does not grant rights to
third-party artwork.

## Runtime and performance

- The original Eden brand texture (`art/brand.tga`, built from
  `assets/icon0.png`) is reused without a substitute font or recoloring.
- A shared perspective-projected shell uses the existing batched OpenGL
  renderer: front and back are true projective planes with perspective-correct
  UVs, a separate red 28px-deep spine, translucent molded white plastic
  rims, side rails, glossy bevel and physical hinges. This identical geometry
  applies to EVERY game. No separate 3D engine or per-game model is required.
- **Reduce Motion** shows the front without spinning.
- The case makes one eased full 360-degree rotation: initial front hold
  1.2s, first half-turn 1.3s, **back cover readable for 4.5s**, return
  half-turn 1.3s, and 0.5s settle/fade (**8.8s total**). This deliberately
  delays the native guest handoff; it does not claim to measure guest progress.
- The rendering is source-independent: the PSD template provided for the
  case design is used solely as a geometry reference (587x995 document,
  approximately 45px spine), not copied, shipped or rendered as a texture.
  The launcher itself constructs the rounded polycarbonate shell, clear top
  and bottom faces, red spine and white rim. Third-party logos remain in the
  cover scan only, not baked into Encore's 3D material.
- The background metadata worker now stores up to six region-ranked original
  **flat** scans per side (FR > EU > World > other), choosing an available
  higher-resolution image if the first candidate is a thumbnail. Box - 3D
  preview images are never used as front/back surfaces.
- The 8.8s transition does not run network requests or decode artwork on the
  draw thread;
  no network, metadata scan, or image decode is performed in the draw loop.
- Texture loading remains asynchronous and budgeted through `Textures::pump`.
- A true game-loading overlay **after the emulator takes control** is not part
  of this change; it requires separate runtime coordination to avoid hiding
  crash or guest-progress diagnostics.

## Known limits

- The published catalog and CDN are third-party services and may change.
- WebP-only artwork and ambiguous regional/edition matches are not fetched.
- Source sharpness cannot be created by upscaling: the public CDN sometimes
  returns a 172x281 thumbnail. The host visual check prefers a real 1447x2343
  cover for BOTW; both host source dimensions are recorded in the receipt.
  Original commercial artwork remains outside this source repository.
- This is a **launch transition**, not an overlay during the emulator's game
  loading process.
- Successful code and CI checks do not guarantee CDN access on every console.

## Validation

The host source contract is `tools/check-launch-case-artwork.py`. CI runs it
in the source preflight and native build checks. A passing source test does not
replace a completed native build or an on-device visual check.

The actual CDN/download path remains subject to a real console network check; a green host-source test cannot prove that every indexed image URL resolves.

## Depth-first correction

The prior shader used a 28px flat spine and masked rounded 2D cover; the
screenshots made it look like a thin printed sheet. The new shell has a
64px projective depth and a molded 31px corner radius. Each exposed corner is
constructed from eight true 3D extruded arc segments with curved lighting;
the upper and lower plastic caps, the red sleeve side, the white rails and
the printed front/back all share the same 3D axis. Front and rear are placed
on different depth planes, not merely switched as two flat slides.
The frame is deliberately tested at a three-quarter viewing angle to make
its actual thickness perceptible. This is a custom rendered object, not an
existing 3D box image or a layer of the uploaded PSD.

A green host render verifies executable geometry, not a claim that the
material is now photorealistic. Inspect actual frame screenshots before
declaring the design ready; assess projection, printed-spine readability,
bevel shading, contact shadows and face sharpness.

## Real physical case material and printed side

The model is a **true volume** rather than two 2D sprites. It has two planes
64 virtual pixels apart, two solid connecting caps, left/right sides, a
31px corner radius built from eight extruded arc segments on each exposed
corner, curved plastic highlights, restrained specular edges and an ambient
object shadow. The shell and materials are owned entirely by Encore.

An optional independent **Box - Spine** flat scan is indexed and cached the
same way as Box - Front/Back, with region-ranked candidates. A real scanned
spine is texture-mapped onto the left red side of the model. The opposite
right-hand side is the semi-transparent hinged/latch edge; it does not reuse
the printed sleeve. Without a valid spine scan, the real side geometry still
uses a red unprinted fallback. No pre-rendered 3D cover or PSD component is
used as a game-side texture. The physical volume is the same for every game.

Attractive results depend on original source quality. The public test
source for the French back and European spine may still provide only low-
resolution thumbnails even when the catalog advertises high-res scans.
A successful shader test proves rendering works, not photorealism.

## Real renderer screenshot test

`.github/workflows/launcher-production-preview.yml` captures
`00-launch-case-front.png` and `01-launch-case-back.png` with the
existing `tools/launcher/preview.sh`, the original C++ launcher
`Launcher::draw_launch()`, and Mesa's real OpenGL shader backend.
The PNG files appear in the **Encore-launcher-native-render-1080p**
workflow artifact. Front, quarter-turn spine and back are captured.
A second host test verifies the exact same 3D geometry on a different
game using icon/hero fallbacks with no retail scans. For the dedicated
launch test only, GitHub retrieves
real **Zelda BOTW** Switch box scans (Europe front, France back) and an
existing BOTW landscape background from the public LaunchBox image CDN.
The downloaded TGA files are temporary GitHub runner inputs, **not**
repository assets or application content. The screenshots are produced
with C++/OpenGL using these source images, not AI image generation.
The test verifies that case textures are readable and different.

The launch screen now uses the selected game's existing Home Hero image
(Nlib banner then screenshot); all Home controls are omitted behind the
overlay. Dark gradients retain the game scene and text readability.
In the absence of a matching Hero, the existing Eden wallpaper remains.
The test's example screenshots depict actual original retail artwork
supplied by its external publisher; copyright stays with its owners.

Only commits containing `[preview-ready]` trigger this host-only
workflow automatically. No native console binary is implied by these
screenshots.

## Verification checkpoint

The shared three-dimensional case mesh, screenshot rendering, cache source selection,
and native build are validated through the dedicated source-preflight, OpenGL
preview, and native build workflows. A passing workflow is a prerequisite for
claiming a render is verified; actual on-device appearance still requires a
separate console test.

The revised rounded-plastic material shades edge normals with two virtual
light sources and simulates angle-dependent Fresnel on the molded front rim.
Its adequacy is assessed by the actual host GL screenshots rather than the
source preflight alone.

## October 14 material/render comparison

The case render is measured against the supplied PSD composite rather than
approved from a green CI status. The inset printed scans are separate from
our own 3D polycarbonate shell. The shell uses a 454x730 front silhouette,
31px extrusion rounding, 64px depth, a recessed insert, solid projected
upper/lower surfaces and directionally lit curved side/corner segments.
Transparent molded rim reflections use a grazing-angle Fresnel term; the
lighting avoids tinting the underlying printed artwork. Neither the PSD nor
any pre-rendered 3D box image is shipped as a game texture.

**Only the host C++/OpenGL visual-preview workflow is requested for this
iteration; do not invoke source preflight or a native console build.**
