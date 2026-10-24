# Reconstructed jacket paper — source and render contract (24 October 2026)

Branch: `dev/ps5-sparse-jit`.

## One opaque paper sheet
For both the 2D Library and the rotating 3D launcher, the paper is a
**complete, opaque rectangular ink substrate** (`0x112235`). It sits behind
every game media item and caption, and in front of the independently modeled
plastic shell. A missing or loading bitmap leaves ink, never a local black
patch or transparent upper/lower gaps. The offscreen OpenGL page is cleared
to the same RGB and alpha=1. Original retailer scans also rest on the paper
when their natural aspect leaves small blank edges.

Source owners:
- `headless/prosperoeden/pe/ui/library.cpp`:
  `reconstructed_paper`, `reconstructed_cover`,
  `draw_composed_case_face`, `flat_retail_sleeve`,
  `composed_case_face_ready`.
- `headless/prosperoeden/pe/ui/case_media_selection.hpp`:
  `FrontPaper`, `BackScenes`.
- `headless/prosperoeden/pe/ui/textures.cpp`:
  `Textures::render_case_page`.
- `headless/prosperoeden/pe/ui/launcher.cpp`:
  `Launcher::draw_launch`.

## Front/back input contract
- A reconstructed **front** uses the cached hero, otherwise the first
  usable screenshot, otherwise the icon/cover. Cover fits the paper using
  equal X/Y image scale and centered UV cropping; no asymmetric stretching
  and no contained square floating over a contrasting rectangle.
- A reconstructed **back** must exclude the chosen front scene and cover
  icon. Only distinct real screenshots may appear behind/alongside the
  description. Without independent scenery, the upper paper remains
  plain stock; the immutable lower artwork/template and normal game
  description still draw directly onto their own print region.
- A **real retail scan** takes priority for its own face. If only one real
  scan exists, the other face is reconstructed independently.
- Readiness waits only for images that will actually be composited.
  The first 3D frames never show a raw front hero in place of the back
  while a generated page is pending.

## Validation
- Actual native C++/OpenGL 1080p production-preview workflow **green**:
  https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40073108453
  This exercises original, mixed original/reconstructed and all-fallback
  cases, plus Library back focus/zoom and the rendered stock-paper case.
- C++20 `-O0`/`-O2` host selector fixture excludes duplicate and front
  media, refuses icon insertion on the back, and verifies the icon-only
  front fallback.
- Source contracts verify complete paper on both faces, the same ink entry
  point for Library/launch, background `cover` crop UVs, no per-element
  black matte, and an opaque offscreen buffer.

A green host renderer verifies this composition, not a PS5 console
performance improvement or the independent F01–F06 FC27 exit gates.
