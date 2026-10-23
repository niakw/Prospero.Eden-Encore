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

## Physical-case correction checkpoint

The transparent molded sleeve now stays within the projected front/back shell.
The printed scan is recessed only 7px, and the shell has a single subdued
translucent rim instead of stacked white backing rectangles. Case depth is
36px for a 454px-wide cover (~7.9%); both paper planes, spine ink, curved
edges, and upper/lower caps agree on this depth. The front and the real back
use the same slight angle; the back still pauses for 4.5 seconds. The public
CDN may supply a low-resolution original; source resolution is logged and
cannot be repaired by stretching it.

Validation is limited to the host-only, real C++/OpenGL visual preview;
no native app packaging or native platform compilation is requested.

## Printing under the transparent sleeve

The original flat front and back scans extend to within 3px of the outside
case silhouette. The radius of each printed corner follows the 22px
polycarbonate shell with an 18px paper mask: no independent opaque white frame
may stick out around the picture. Thin semi-transparent Fresnel highlights
remain on the single physical case. The body stays 36px deep, around eight
percent of the 454px front width. The same treatment applies to every title.

## Verified directional layout contract (all titles)

- **Front hold**: yaw +0.40 rad, showing more of the LEFT red printed spine;
  right side remains discreet.
- **Back hold**: yaw pi+0.57 rad, showing more of the LEFT clear opening;
  the opposite physical RED hinge appears only as a narrow seam on the RIGHT.
- The flat front/back scans use aspect-preserving containment and cannot
  stretch a region's back-cover descriptions. Genuine scans remain priority.
- An original unreadably tiny physical spine (under 64x600 px) is rejected;
  the universal fallback is a clean red neutral sleeve with pale, title-free
  molding marks, never a pixel-stretched title.
- Eden logo and title are moved into the right column with clear case margins.
- Same C++ shader and fixed geometry for every game. The 4.5 s back hold remains.

Only the host OpenGL case-visual workflow is requested here. Native console
packaging/compilation requires an explicit separate user approval.

## Directional render and media verification (October 14)

The physical case is common to all games. At the front pause (+0.52 rad),
the red hinge occupies more of the LEFT side. At the back pause
(pi+0.63 rad), the transparent opening on the LEFT is more prominent,
while a thin separate red seam is visible on the RIGHT. Shell depth is
44 virtual px (9.7% of the 454px front width), not a flat width-flipped image.
Both covers remain separate flat scans under the same translucent plastic.

The image worker considers multiple region-ranked originals separately for
front/back/spine. For BOTW, the user-identified 4b815... French back-cover
source resolved as an actual 1167x1878 scan in the host visual run, replacing
the tiny 174x281 thumbnail. The rendering preserves the original aspect ratio
rather than stretching the lettering. A source spine narrower than 64px or
shorter than 600px is not passed off as readable: the preview and native
resolver use the neutral empty red sleeve without an invented game title.

The full-screen game Hero and the right-hand Eden brand/title have additional
clearance. The back scan remains held for 4.5 seconds. The host screenshot is
still a *render verification*, not a claim of photorealistic 3D materials or a
successful native console build.

## Blank-spine manufacturing marks (host GL validation)

When an official original spine is missing or so small its printing cannot
be read, the common shader prints a sharp red blank spine with a small paired
white emblem and an unlettered outlined footer. These features are vector
shapes on the SAME projected 3D side, and no synthetic game title is shown.
The user-provided spine photo is a visual reference, not a distributed asset.
The original official flat spine remains the priority whenever its decoded
resolution is sufficient. Only the host OpenGL renderer is tested here.

## Quick spine transition / readable rear pose

The box does **not pause on its spine**. Both half-turns are eased 0.72-second
movements; the side is only briefly visible while passing through 90 degrees.
The actual back is presented at yaw pi+0.26 rad (approximately 15 degrees
away from straight-on), and is held for 4.5 seconds so its original flat scan
can be read. Its left clear opening is a projected physical side; there is
**no** artificial red graphic border on the right of the back. Only the real
shell's outer right edge remains. The front still exposes the real left
printed red hinge at +0.52 rad. No special-case per-game meshes are used.

The preview explicitly captures front, an instant of the passing spine, and
back in its reading hold. No native console build is authorized here.

## Retail-cover Library, rear popup and localization

- Library shelves use cached original **flat Box - Front** assets, not square ROM
  icons and not prebaked 3D boxes. Exactly five cover slots use portrait art
  with a common shelf and focused cover highlight.
- Selected details display the cached **Box - Back** on the left with its own
  selectable focus. Down focuses that print; Cross opens its full-size,
  aspect-preserving overlay; Circle closes it without launching a game.
- Existing async Nlib/retail media workers resolve and propagate the paths.
  No new filesystem scan/HTTP lookup occurs in a 60Hz paint or D-pad path.
- Detail dates adapt to the region chosen by the system/game language
  preference, genre tokens are translated independently, French GB is Go,
  and file formats display as .NSP/.XCI. The source metadata remains intact.
- Loader: the top and bottom clear shell surfaces render **over** back print,
  so it no longer looks like an unrestricted poster. The back remains mostly
  face-on and the real left opening side is preserved. Front printed branding
  has a local, conditional simplified Switch header without overwriting
  archived flat artwork.
- The host-only software OpenGL preview now captures the actual Library shelf,
  rear focus and opened/closed enlargement, in addition to its case sequence.
  **No native console packaging/build has been authorized.**

### Locale and preview verification

The French Library's directly referenced translation keys have been audited,
including the enlarged-jacket Close hint. Its date and metadata formatting
are UI-only; launcher strings and full media acquisition remain shared.
Only the host OpenGL screenshot workflow is requested for this checkpoint.

Actual test checkpoint: textual source contracts were reconciled with the
current Library implementation before this host-only rendering run.

## Library actual-image preview verification

The Library screenshot sequence must select the **actual indexed retail-art
fixture**, wait for the asynchronous texture worker, and capture the real front
shelf, selected back scan, enlarged back popup and post-close state. Earlier
screen captures selected a different sample without retail art and therefore
showed blank placeholders; those images are not accepted as visual validation.
For titles with no retail flat art at all, Library now draws a common
non-animated 2D fallback using the available icon/banner, real game title,
and known description. It must never appear as an empty rectangle or a
fabricated third-party box scan.

## Final actual-capture proof gate

Capture timing is controlled by loaded-texture state, not a blind fixed number
of frames. Both flat BOTW scans must be decoded and have completed their fade-in
before the host screenshot is accepted. The enlarged scan similarly must be
actually loaded at its higher texture bucket. Pixel-stat assertions reject
blank fronts or blank popups. Both compiled app states are captured directly
as 1920x1080 PNGs; there is no generated or composited mockup.

## Same-height paperback / Library transparent sleeve

The retail paper surface is always the SAME inset rectangle for FRONT and BACK:
physical outer shell 454x730; printed flat scan inset 9px horizontally and
13px vertically. Therefore both printed faces are 436x704, with a visible
single translucent molding above, below and beside them. Source art uses
aspect-preserving containment, never a stretched full-bleed back poster.
The rear is still readable at yaw pi+0.44, but exposes more of the actual
transparent left opening. Only the projected real wall is shown; no synthetic
red back-right stripe is added.

The Library, including the focusable/really enlarged rear cover, uses one
separate non-rotating sleeve treatment for both flat front and back. Its
outer edges and paper inset scale together; the popup is a portrait 500x807
case rather than an overly wide art panel. Translucent edge strips are drawn
WITHIN the outline so they cannot look like a floating second frame. These
rules apply to every title, including placeholder covers.

Only an actual host OpenGL render preview is authorized to validate this UI
iteration. Native console build/package is not authorized.

The static source contract was reconciled with the shared flat-case helper:
front, rear detail and rear zoom are rendered through the same sleeve, not
old independent image paths. The visual preview must confirm the paper stays
inside the clear top/bottom/lateral casing, with the rear opening visible at
its readable yaw. No platform-native compilation accompanies this validation.

Final dimensional consistency: the print on the spine now shares the
identical `physical.y + kPaperTopInset` and
`physical.h - 2*kPaperTopInset` vertical coordinates as the front/back
printed paper (704 units). The clear molded top/bottom shell remains 730
units high. Real host OpenGL screenshots are the acceptance evidence.

## Single wrap + independent plastic shell (physical invariant)

For **all games**, the artwork is one square-cornered printed paper wrap
spanning front, red inked spine, and back. These three planes share one
continuous top/bottom interval and exactly the same fold vertices. The shell
is a **separate**, translucent, rounded polycarbonate case outside this wrap.
Its visible lip is 7 virtual pixels LEFT and RIGHT of each face print, and
13 virtual pixels ABOVE and BELOW every face and printed spine. There are no
white frames or artificial empty stripes at the front/spine and spine/back
paper junctions. The spine itself spans all 44 pixels of physical case depth;
no 3px inset or shortened side print is permitted. Only molded plastic is
rounded; printed faces and spine are square-cornered. The static Library
front/back jackets share those same paper-vs-plastic rules.

Visual validation runs only with the host OpenGL renderer (front, crossing
spine, back and Library shelf/detail/zoom); do not compile the native PS5 app
without the user's explicit authorization.


## Recomposition when retail front/back are absent — 23 October 2026

This is **native UI composition, not AI image generation**. The user-provided
front-logo/back-footer decomposition is a visual layout reference; no retail
example image is copied into the app and no third-party legal footer is
reused for another game.

- **Front:** cached real hero/cover image plus optional game screenshot,
  red format mark and a lower title band; no enlarged lonely square icon.
- **Back:** a wide scene, two game screenshot panels where available,
  the cached title-specific Nlib description or intro (not fabricated
  from artwork), and a fixed neutral footer.
  Unknown ratings, official logos, player counts, manufacturer details
  and barcodes are never fabricated.
- **Scan priority:** existing physical Box - Front and Box - Back scans
  always win independently and are presented unmodified.
- **Cost:** reuse cached game media and ordinary UI draw operations, with
  no per-frame downloader, no generated cover files and no extra worker.

The **static Library** and **spinning launcher** now use the same
`draw_composed_case_face` native C++ front/back painter. For the animated
case, Encore renders each face once into a bounded 660×1056 temporary
OpenGL framebuffer after locally cached input artwork has decoded. That
texture is then mapped onto the unchanged projective front/back planes
of the **same physical 3D box**; the red spine and clear plastic remain
separate true-volume geometry. The framebuffer image is Y-flipped only
at the case texture boundary. No flat text overlay is glued onto the
rotating 3D box.

The artistically assembled paper contains a scenic hero or real screenshot,
a correctly proportioned cover/icon, the title, and (on the back) available
real Nlib synopsis plus a neutral information footer. If a second genuine
screenshot is not available, the back uses one distinct scene, never two
fake copies. Physical retail scans always supersede the composition per
face, including scans received asynchronously.

**Resource ceiling:** two temporary pages (front/back), each 660×1056
RGBA8 ≈2.7 MiB, cleared when changing titles and at texture teardown.
An unavailable offscreen framebuffer is attempted only once per face;
the prior single-artwork fallback remains valid. Neither the native
compression path nor game emulator graphics shaders are affected.

**Validation gate:** the source-contract tests verify this ownership,
and `.github/workflows/launcher-production-preview.yml` must confirm
the actual C++/OpenGL animated front/spine/back screenshots with the
retail scans disabled. Pending that host visual run (and later console
qualification), no claim is made that the 3D presentation is visually
approved on hardware.

Launcher-only L1/R1 navigation now selects Settings sections, modal
rows, per-game settings, mod rows and controller-mapping entries without
changing values. Existing gameplay shortcuts are untouched.
The source regression is tools/check-launcher-shoulder-and-cover.py.

## Authentic README Home screenshot

The workflow .github/workflows/launcher-readme-home-screenshot.yml renders
the actual C++/OpenGL home UI with Mesa, validates the 1920x1080 PNG,
then commits it under assets/screenshots/encore-home.png and swaps the
README.md and README.fr.md links together. On failure neither the
README nor the image is changed. This is real application UI rendered
on a host computer; it is **not** a screenshot captured on PS5.

The final documentation/preview opt-in is tied to this maintained
launcher iteration. The screenshot publisher only commits verified C++/OpenGL
pixels; a missing render must not replace the existing README hero.


## Native fallback preview acceptance — 23 October

The **actual** launcher host renderer now exercises three cases:

1. Original retail front/back: unchanged scans and existing 3D plastic/hinges.
2. Both scans missing: distinct native-composed front/back paper, projected
   on the same real C++/OpenGL three-dimensional case.
3. Missing/late individual scan: locally recomposed face is displayed until
   a readable scan supersedes it, without replacing the other known face.

The generic screenshot job records `EDEN_CASE_COMPOSE` once per visible
side and checks that front and rear screenshots are materially different.
It rejects a fallback that merely turns one square app icon into a
blank, mirrored, or repeatedly stretched back print. The dedicated
source test checks source/header ownership and the two-page GPU limit.
Both tests are **host-only**; no PS5 deployment or hardware test is
requested. The signed gameplay ABI, JIT, texture caches and FC27 exit
gates F01-F06 are unchanged by this UI work.

**Requested at this checkpoint:** launch the existing
`launcher-production-preview.yml` C++/OpenGL visual gate. The result
is **pending verification**, not asserted successful here. Any failing
visual check or native compilation must be resolved before declaring
the animated fallback complete.


## 23 October — distinct media, authentic README and reproducible previews

The fallback compositor now uses one small C++20 source-owned selector
(`pe/ui/case_media_selection.hpp`) for both printed faces:

- The **front** chooses the first locally cached screenshot that differs
  from the hero. If none exists, a distinct square icon is aspect-fitted
  into the secondary panel rather than cropped into a fake scene.
- The **back** considers *all* available cached screenshots, skipping
  empty entries, duplicates and the hero. It selects up to two truly
  different frames; if only one exists, the second slot can use a
  distinct cached icon/poster, aspect-fitted. Missing images are never
  invented or repeated to fill two apparent captures.
- Original `Box - Front` and `Box - Back` scans always override the
  generated print composition independently. This selector does not
  change the physical 3D shell, add network calls or allocate a new
  screenshot/description in the draw loop.

`tools/check-encore-case-media-selection-host.py` compiles the actual
selection header in C++20 and checks cases with duplicates, an icon-only
fallback, and absent media. It runs during both source preflight and the
OpenGL render-preview workflow. The two existing source-oracles have been
updated to require the new selection rules.

The README image is already a **real screenshot of the Encore C++/OpenGL
Home**, stored at `assets/screenshots/encore-home.png`. The screenshot
publisher is now *idempotent*: a fresh native render can update that same
asset and its README links without failing because the old wallpaper
has already been replaced. No generated illustration is involved.

The `[preview-ready]` workflow must prove pixel rendering, including
missing retail-art front/back, before calling these visual changes
verified. The `[full-build]` workflow separately checks PS5 compilation.
A host OpenGL screenshot is **not** a device gameplay qualification.


### 23 October — render-gate correction

A real `[preview-ready]` run exposed an existing case-sensitive
assertion error in `check-launch-case-artwork.py`: the footer text
was lowercased but the split marker `const Rect footer` was not.
The source contract is now corrected to `const rect footer`. This
was a test bug, not evidence of missing back-cover pixels.
The C++/OpenGL case rendering remains the acceptance criterion;
the next host preview should advance past the source-only gate.


### 23 October — native host CI gate follow-up

The first real case preview accepted the retail-scan and shoulder-key
source contracts, then found the new case-media host test using the
wrong include root (`-I headless` rather than
`-I headless/prosperoeden`). This test harness path is now corrected.
The NCZ source-gate's metadata bridge check has also been reconciled
with the central `IsPackageFile/IsCardImageFile` predicates.

The next marked commit requests another **actual C++/OpenGL render**
and native compile, not a fabricated image or console test. Only
published green workflow results count as verification.


### Latest two-panel fallback correction

When a real cached square cover icon fills one of the two lower rear
panels, `flat_back_fallback` now aspect-fits the icon **on either side**.
Only true landscape screenshots use the crop renderer. The prior
distinct-media selector remains unchanged; two independent screenshots
still take priority. Source regressions cover this branch, and a new
native host OpenGL render must verify the actual paper face.

The source CI also now rejects a stale NCZ/ExeFS scanner check and the
old Vulkan `PreflightLargeGuestDraw` audit symbol. Both had prevented
unrelated frontend changes from reaching the native compiler. They
were test/register corrections, not gameplay performance claims.
