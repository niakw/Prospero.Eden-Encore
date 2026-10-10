# Third-party DualSense controller artwork

- **Product:** PS5 Button Icons and Controls
- **Creator:** Zacksly
- **Source:** https://zacksly.itch.io
**License:** [Creative Commons Attribution 3.0 Unported (CC BY 3.0)](https://creativecommons.org/licenses/by/3.0/)

The user-supplied archive's `LICENSE.txt` permits redistribution and
adaptation with attribution. Eden Encore uses only the original asset
`Controller Images/Outline/Outline White 4k.png`.

**Changes made:** The outline illustration was rescaled and centered on a
144 × 100 transparent canvas; alpha was quantized to four levels and encoded
using (run length, alpha level) byte pairs in
`headless/prosperoeden/pe/ui/dualsense_mask_asset.hpp`. On startup the
launcher reconstructs a tinted GL texture; the source outline and placement
remain recognizable. This asset is **not** a Nintendo game glyph pack and
does not automatically replace game-provided button art.

This particular embedded resource is distributed under CC BY 3.0; nothing
here changes the licensing of original third-party contributions elsewhere
in the emulator. Attribution does not imply endorsement by Zacksly.

Original artwork: **PS5 Button Icons and Controls by Zacksly,
licensed under CC BY 3.0 — https://zacksly.itch.io**.
