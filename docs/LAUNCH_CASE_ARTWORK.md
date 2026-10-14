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
- A lightweight faux-3D horizontal flip uses existing batched 2D draw calls
  and cached textures. No extra renderer, shader pipeline or 3D engine.
- **Reduce Motion** shows the front without spinning.
- Animation duration is capped at 1.85 s before the existing game-start path;
  no network, metadata scan, or image decode is performed in the draw loop.
- Texture loading remains asynchronous and budgeted through `Textures::pump`.
- A true game-loading overlay **after the emulator takes control** is not part
  of this change; it requires separate runtime coordination to avoid hiding
  crash or guest-progress diagnostics.

## Known limits

- The published catalog and CDN are third-party services and may change.
- WebP-only artwork and ambiguous regional/edition matches are not fetched.
- This is a **launch transition**, not an overlay during the emulator's game
  loading process.
- Successful code and CI checks do not guarantee CDN access on every console.

## Validation

The host source contract is `tools/check-launch-case-artwork.py`. CI runs it
in the source preflight and native build checks. A passing source test does not
replace a completed native build or an on-device visual check.

The actual CDN/download path remains subject to a real console network check; a green host-source test cannot prove that every indexed image URL resolves.

## Real renderer screenshot test

`.github/workflows/launcher-production-preview.yml` captures
`00-launch-case-front.png` and `01-launch-case-back.png` with the
existing `tools/launcher/preview.sh`, the original C++ launcher
`Launcher::draw_launch()`, and Mesa's real OpenGL shader backend.
The PNG files appear in the **Encore-launcher-native-render-1080p**
workflow artifact. For the dedicated launch test only, GitHub retrieves
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
