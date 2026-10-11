# R320 — PS5 duplicate adjacent texture-view fast path

The **1440p FC27 sessions** are the reference: 123, 37 and 70 five-second windows, not the shorter 1080p/4K sessions. In the 1440p recordings, `FillImageViews` reached 11.361 ms in one sampled draw, and cache conflicts peaked at 17,893 per five-second window. These costs do not prove duplicated bindings cause the peaks.

Pinned Eden `FillImageViews` calls `VisitImageView` for every descriptor, including immediately consecutive repeated TIC indices. For `blacklist=false` when the previous view ID was non-NULL and no image deletion was observed during the pass, no other texture operation can intervene, and the duplicate view has just been prepared.

R320 adds a PS5-only immediate reuse for this exact case, preserving NULL view retry (R314/R317), blacklisted/scale-down reprocessing, image-deletion retries, the paired GPU locks, synchronization, and non-PS5 behavior. It is deliberately narrow and unproven as an FC27 FPS optimization; it only helps adjacent identical successful sampled views.

Test `tools/check-ps5-adjacent-texture-view-reuse.py` SHA-checks the exact upstream source, replays the production patch, and compiles/runs the **actual** `FillImageViews` function with C++20 under PS5 and upstream conditions, including NULL recovery, blacklisting, and deletion-loop safety. Host and native gates include it.

Previous PS5 native R319 workflow [#38141622094](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38141622094) **SUCCESS**, All-On archive artifact ID 11702689609. R320 is **source-only** until native build; do not confuse artifacts.

## R320 native compilation

Core-source preflight [#38142726917](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38142726917): **SUCCESS** after correcting the test fixture's expected adjacent-duplicate visit count (three unique contiguous groups: 3,3,4,4,3,3). Native PS5 All-On qualification is triggered by this documentation-only commit. Only a successful native build and on-console FC27 test can qualify the effect on the 1440p reference workload.
