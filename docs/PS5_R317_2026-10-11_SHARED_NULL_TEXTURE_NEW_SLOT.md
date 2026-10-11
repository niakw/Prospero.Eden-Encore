# R317 — Shared descriptor NULL view retry on first bind of another slot

Branch: `dev/ps5-sparse-jit`; pinned Eden `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.

## Defect and relevance

R314 rescues a cached `NULL_IMAGE_VIEW_ID` on the `DescriptorTable::Read is_new=false` path. Pinned Eden also stores the result in a *descriptor-keyed* `channel_state->image_views` map. If `CreateImageView` temporarily fails for slot 5, then another slot 6 reads the same valid descriptor for its first time, `Read` returns `is_new=true`, `try_emplace` finds the existing descriptor with NULL, and the code bypasses creation. The second slot unnecessarily misses its first draw, even though creation may already succeed.

## Narrow PS5 correction

`headless/backports/eden-ps5-texture-shared-null-new-slot.patch` changes **only** the `is_new=true` descriptor creation check under `PS5_NATIVE`: retry when the shared descriptor's value is NULL, not only when the descriptor map entry is new. R314's `is_new=false` recovery and R315's view-aware barrier decision stay in place. Already-valid views follow the unchanged path; persistent failures still return NULL safely. No guest mapping override, forced texture substitution, GPU lock change or draw cadence adjustment.

The pinned-source regression `tools/check-ps5-null-texture-view-revival.py` now applies both R314 and R317 production patches, compiles the exact combined `VisitImageView` function in PS5 and upstream modes, and reproduces a first creation failure followed by a distinct first-time texture index sharing the descriptor. No user test or native performance improvement is claimed.

Remaining separate issues: 30 FPS frame pacing, `FillImageViews` cache lock peaks, terrain LOD/streaming, and 1440p→4K filtering. R316 source validation was green in #38132469426.
