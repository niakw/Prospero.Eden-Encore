# R314 — Recover streaming texture views after GPU remapping (PS5)

Branch: `dev/ps5-sparse-jit`. Pinned Eden source `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`.
Target PS5 `PPSA99008`, test game FC27 guest Title ID `0100C49025D3E000`.

## Observations requiring a real correction

The user reported FC27 jerseys/scoreboard HUD intermittent, pitch quality degrading
with motion, and stutter even with many near-30 FPS windows. In R310 logs, a
`TextureFormat=0` appeared once; that invalid guest descriptor previously
fell through Eden's `A8B8G8R8_UNORM` fallback. R312 rejects invalid/insufficiently
resident nonsparse TICs before they become fake RGBA8 textures.

The pinned Eden `TextureCache<P>::VisitImageView` additionally caches
`NULL_IMAGE_VIEW_ID` in `channel_state->image_view_ids` when the TIC is invalid
or the GPU backing is not available. After a later guest GPU address remap,
the TIC bytes may stay **unchanged**, so `DescriptorTable::Read` returns
`is_new=false` and upstream will keep returning the cached NULL view forever.
That explains a **real recoverability bug**, though does not prove a particular
FC27 shirt/scoreboard anomaly is specifically triggered by this pathway.

## Narrow PS5-only fix

`headless/backports/eden-ps5-texture-null-view-remap.patch` changes only the
`is_new=false` branch of `VisitImageView` under `#ifdef PS5_NATIVE`:

1. **Already-valid IDs** use Eden's existing direct `PrepareImageView` fast
   path unchanged. No extra GPU mapping lookups on those draws.
2. A cached **NULL** ID is revalidated with `IsValidEntry`. Remains NULL if
   its backing is still absent, TIC has invalid format 0, sparse residency
   conditions are not met, or address is invalid.
3. Once valid, reuse the corresponding descriptor's
   `channel_state->image_views` map entry if possible; if the entry itself
   is still NULL because a prior `CreateImageView` failed, **retry creation**.
4. If a non-null view has been recovered, increment `texture_bindings_serial`
   to invalidate `TextureCache::CheckFeedbackLoop`'s cached barrier decision.
   Otherwise the feedback loop could reuse a pre-remapping no-barrier result
   even though the sampled image changed. Never increment on persistent NULL.
5. Publish the updated `image_view_ids` entry and return it. Existing locks,
   submission/barriers, guest CPU writes and graphics memory ownership are
   untouched. Non-PS5 core and shipping branch are untouched.

The patch does not manufacture missing textures; it *recovers* genuinely valid
textures after the guest has provided backing. New malformed descriptor values
still follow the R312 rejection rule.

## Regression checks

`tools/check-ps5-null-texture-view-revival.py` downloads SHA-verified pinned
`src/video_core/texture_cache/texture_cache.h`, git applies this exact patch,
compiles the actual C++ `VisitImageView` against minimal doubles, and executes
both PS5 and upstream variants.

Tests:
- Initially unmapped descriptor becomes mapped WITHOUT descriptor rewrite:
  PS5 view recovers exactly once; upstream behavior stays unchanged.
- Normal cached valid view never recreates.
- Descriptor view creation fails once even though TIC is valid, then succeeds
  without new descriptor bytes; PS5 recovers. This tests both ID maps.
- `texture_bindings_serial` advances only when a formerly NULL view
  becomes valid; no extra invalidation on reused views or failed recreation.
- Compute and graphics slot-index tags remain independent; invalid format
  continues yielding NULL.

CI host fixture and actual PS5 native compilation are necessary but cannot
establish on-console improvement without a later matching-scene replay.

## Other work remains

R313 fast-first shaders already native-compiled in #38111020424; it may avoid
first-use missing draws but has no FC27 on-console visual proof. R311 nvmap
fail-closed correction built in #38109350300; it does not prove the game never
panics. Late-frame JIT spikes, shared guest cache lock waits and double
1440p→4K scaling are different open issues. Increasing the 64-draw dispatch
cadence to the 512-draw maximum is not a proven FPS unlock, and the 512-draw
hard flush limit remains required to avoid PS5 device faults.
