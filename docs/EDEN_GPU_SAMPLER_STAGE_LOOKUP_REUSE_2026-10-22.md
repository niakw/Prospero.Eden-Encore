# Graphics sampler stage-local reuse — 22 October 2026

## Measured motivation

The FC27 October 21 detailed trace logged ~1,116,606 graphics Configure calls.
The aggregated `stage_texture_handles` phase consumed ~0.94 s; that
measurement includes much more than sampler lookups, so it is not an
estimate of the benefit of this patch. Similarly, the `fill_views` phase
consumed ~0.97 s over the whole session.

## Maintained source change

Under both paired GPU cache mutexes, the selected native Vulkan graphics
pipeline read the exact same sampler handle repeatedly for consecutive
texture descriptors in the same Configure stage. Each lookup reads the
TSC table and consults sampler IDs. Reuse only the previously resolved
sampler ID when the next handle is identical. The cache is automatic
local state inside `config_stage`, recreated on every stage of every draw,
not persisted across stage/pipeline boundaries or guest invalidations.
Image view resolution, actual descriptor payload ordering, sampler
selection for different handles, and all synchronization remain intact.

An empty image-view vector skips `FillImageViews` (an empty loop).
Render-target refresh and feedback barriers still execute, and textured
draws keep full descriptor synchronization.

`tools/check-ps5-consecutive-sampler-reuse-host.py` extracts the
selected native sampler stage into C++ test fixtures and compiles/runs
O0/O2 UBSan. The oracle rebuilds the two precise native transformations
from the pinned generated source. The test checks empty, repeated,
alternating, multiple-descriptor and repeated-draw cases, plus the
separate render-target/feedback phases.

No synthetic timing is claimed as FC27 improvement. Runtime frame pacing,
HUD fidelity and memory pressure need independent PS5 proof.
