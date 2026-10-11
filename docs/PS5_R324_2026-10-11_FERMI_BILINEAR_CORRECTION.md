# R324 — Repair Fermi2D software bilinear coordinate math

Pinned Eden snapshot `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`, fork branch `dev/ps5-sparse-jit`.

## Source proof

Eden software Fermi2D `Bilinear` produces plain pixel coordinates by `floor/ceil(x*dx_du)`. Its `read_src` incorrectly indexes `((x*width+y)>>32)*4`, combining an unwarranted 32-bit shift with transposed X/Y. This often returns **the first texel for every sample**, yielding smeared or flat output when bilinear software filtering runs. In contrast `NearestNeighbor` advances 32.32 fixed-point coordinates and legitimately uses `>>32`; it remains unchanged.

R324 repairs only the source read index to `(y*width+x)*ir_components`, preserving interpolation, row layout, output conversion, memory safety, Vulkan barriers and other shader paths.

R322 FC27 1440p logs include 96 Fermi2D non-unit source-depth warnings around game time 103–105s. That is evidence of Fermi2D being used, **not proof** the warnings were all bilinear software copies or that this alone restores FC27 turf or HUD. R323 moves a specific descriptor ring wait outside GPU cache locks; R324 targets image correctness independently.

## Regression

`tools/check-ps5-software-bilinear.py` pins and SHA checks the exact Eden source, replays the production patch with `git apply --check`, compiles the actual Bilinear function in C++20, and checks: 3x2 unsized identity, 3x2→5x3 interpolation at corner/center with four channels, and degenerate 1x1→4x3 upscaling. Integrated in core and native preflight. R323's source generator fix #38157962597 PASS; both R323 and R324 require native All-On validation before any PS5 test. No FPS gain claimed.
