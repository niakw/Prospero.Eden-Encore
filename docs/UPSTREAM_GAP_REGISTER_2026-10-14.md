# Upstream coverage register — 14 October 2026

Scope: active development branch `dev/ps5-sparse-jit`. This is a **gap inventory**, not a claim that every independent library's source changes have been reviewed or validated on hardware. Pinned versions are intentional and must not be blindly updated. Exact third-party project identifiers are retained in source URLs, technical manifests and mandatory attribution.

## Current baseline comparison

Comparison counts are relative to the immutable dependency manifest at this date; `+N/−M` indicates divergent ancestry, **not** missing fixes that can simply be cherry-picked. GitHub's comparison endpoint returned at most 300 changed files for the main emulator (file list incomplete).

| Manifest component | Compared to upstream | Commits ahead / behind | Risk and status |
|---|---|---:|---|
| `eden` | Yes; pin `5f142c79` | +84 / 0 | **P0** kernel, timing, guest JIT, rendering; backports require per-commit verification |
| `ffmpeg` | No; source SHA pinned | — | Version locked; codec diff outside present simulation fault analysis |
| `fmt` | No; 12.1.0 tag | — | Version locked; compatibility via compile |
| `zbic` | Yes | 0 / 0 | No upstream drift |
| `compiler-rt` | No; compiler runtime snapshot | — | SDK/toolchain ABI gate, not rolling-head dependency |
| `pacbrew` | No; immutable binary distribution 0.40.2 | — | Build/runtime contract only |
| `opengl-source` | Yes | +18 / 0 | **P1** native GL runtime and launcher; review changed GPU source paths |
| `harfbuzz` | No; 12.3.2 release | — | Text shaping; track explicit regressions |
| `boilerplate` | Yes | +43 / 0 | **P1** loader, native process, storage, packaging |
| `ps5-vulkan-tools` | Yes | +18 / 0 | **P1** native Vulkan runtime tools / WSI; changed broker/client code |
| `ps5-mesa` | Yes | +110 / −103 | **P0** divergent driver ABI and graphics correctness; never wholesale repin |
| `ps5-payload-sdk-fork` | Yes | +100 / −48 | **P0** divergent native ABI, scheduling and direct-memory/runtime APIs |
| `encore-overrides` | Yes | 0 / 0 | No upstream drift |
| `opengl-opengnm-psbc` | Yes | 0 / 0 | No upstream drift |
| `opengl-opengnm` | Yes | 0 / 0 | No upstream drift |
| `opengl-spirv-headers` | Yes | +8 / 0 | P2 interface/grammar updates; shader ABI review |
| `opengl-vulkan-headers` | Yes | +6 / 0 | P2 header/video API updates; build compatibility |
| `opengl-imgui` | Yes | +1498 / 0 | P2 UI dependency; large historic drift, no wholesale bump |
| `opengl-nanovg` | Yes | 0 / 0 | No upstream drift |
| `opengl-sokol` | Yes | +219 / 0 | P2 sample/render utility; targeted review only |
| `opengl-native-boilerplate` | Yes | +52 / 0 | P1 second pin of same loader project, independently versioned |
| `opengl-mesa-26-2` | No; frozen Mesa 26.2.0 release archive | — | P1 software/OpenGL build; validate against ported fork |

Totals: 22/22 manifest entries **inventoried**; 15 entries compared to active Git refs, 7 reference pinned archives/releases/toolchains for which no equivalent current-branch comparison was made. The 300-file API cap and the divergence of two native providers prevent describing this as a complete source-diff review. No title save data was read or changed.

## High-impact kernel/guest corrections and closure

| Upstream correction | Actual Encore disposition | Required proof |
|---|---|---|
| Guest context/slab locks and lazy mutex backing (#4436 + #4447) | Both ported together under `vendor/encore-active/eden-threading` at `8f30384f9`; switchable via `EDEN_BLOCKING_GUEST_CONTEXT_LOCKS` | Native compile, post-match progress and latency test pending |
| Guest A32 page-table x86 addressing (#4415/#4444) | Equivalent indexed addressing derived in `headless/CMakeLists.txt` and `headless/checked-fastmem.cmake` | Host source-anchor validation; no claim of faster gameplay |
| Guest control reconnect fallback (#4420) | ReconfigureControllers logic present in `vendor/encore-active/eden-backports/src/core/frontend/applets/controller.cpp` | **Does not prove the title uses saved custom in-match controls** |
| Guest HID/app lifecycle (#4442) | Covered by earlier backports; see vendor audit from 12 October | Observe actual title-owned action settings |
| Video/texture sync (#4473/#4477) and TFB buffer updates (#4499) | Previously ported, under active backport tests | HUD pixels/alias/descriptor freshness not proved |
| Guest scheduler and event-wait provenance | New IPC active-wait and CPU-thread diagnostics `8bee9e532` | Cross-correlate same title thread around stalled frame |
| GPU driver memory/WSI changes after pinned revision | **Open**; branch diverges significantly | ABI and image-coherency matrix; staged native binary verification |
| Alternative compiler/runtime and thread APIs after SDK pin | **Open**; divergent ABI | Examine source, build and firmware-valid API calls before port |

## Audit controls

1. Every new dependency must be entered in this register; an inventory checker rejects additions without review rows. This is a **coverage alarm**, not an automatic integration decision.
2. Classify each relevant upstream diff as implemented / equivalent / inapplicable / candidate / unresolved, with source and tests. Counts and green CI status do **not** replace per-commit evidence.
3. Preserve native pinned versions, public licenses, legal author attributions, and required artifact names. Public-facing CI step labels use neutral technical descriptions.
4. Focus next on driver divergence, runtime scheduling/handoff, real title save-action selection and frame/HUD freshness. Reserve the console test for one verified package; do not use blind A/B trial loops.
5. Keep branches limited to `dev/ps5-sparse-jit`. During an active native run, defer unrelated workflow-label commits so GitHub's cancel-in-progress concurrency does not invalidate the candidate build.

Reference material: `docs/UPSTREAM_VENDOR_AUDIT_2026-10-12.md`, `docs/EXTERNAL_PS5_EMULATOR_ECOSYSTEM_AUDIT_R438.md`, source pinning in `tools/deps.json`, and the publicly linked upstream commits identified in those audits.
