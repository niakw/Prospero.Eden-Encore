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

The native launcher does not ship external artwork, download scans, embed API
keys, or make new HTTPS requests during launch. Nlib remains the source of
existing **icon/banner/screenshots/description**, not official back scans.
API providers with credentials or special redistribution conditions are not
required, enabled, or silently scraped.

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

## Future source integration

A source for real back scans can be added as a separate cache-fill worker only
after its access and usage conditions are met **without mandatory contact or
permission requests**. Front and back must be identified independently and
tied to the correct region/edition and title ID; never treat screenshots,
promotional banners, or unrelated box art as a genuine back scan.
