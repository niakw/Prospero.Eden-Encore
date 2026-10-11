# R321 — PS5 global modification-tick alias fast path

Branch `dev/ps5-sparse-jit`. Source snapshot `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Motivation and correctness proof

Inside the paired rasterizer cache locks, `TextureCache<P>::PrepareImage` invokes `SynchronizeAliases` for textured images that have alias entries. The original implementation allocates a small-vector and scans all aliases to see if any alias's `modification_tick` is **strictly greater** than the current image's tick. If not, it returns without copying anything.

The cache-wide `TextureCache::modification_tick` is monotonically incremented by `MarkModification`. Newly joined/copied images inherit prior ticks; alias synchronization takes the maximum prior tick. No alias can have a tick greater than the current cache-wide tick. If the current image's tick already equals that cache-wide maximum, the alias search is **guaranteed to have an empty result**. R321 adds this O(1) PS5-only early return, preserving the original logic whenever the image's tick is older. This reduces scan overhead in eligible alias-bearing images and never skips a newer alias.

No edits to `RefreshContents`, `ScaleUp/Down`, CPU guest invalidation, graphics locks, Vulkan barriers, image deletion, or upstream code. This optimization may help active render-target textures with aliases but **does not establish** that FC27's 11.361 ms `FillImageViews` peak came from alias scans; no hardware performance delta has yet been measured.

## Source and regression

The production patch applies to the SHA-verified pinned `texture_cache.h`; `tools/check-ps5-alias-current-tick.py` extracts and compiles the real `SynchronizeAliases` function in PS5 and upstream variants, tests equal-to-global, newer alias, repeated synchronization, and unrelated modification. Host and full PS5 CI both invoke the test.

R320 native #38144510483 **SUCCESS** on `da7c77fd`; the R320 artifact is a separate version without this new source-only R321 optimization. Reference FC27 results remain the longer **1440p** sessions, not the shorter 1080p/4K experiments.
