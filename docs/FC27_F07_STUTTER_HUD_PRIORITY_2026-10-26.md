# FC27 — F07: priority is visual stutter, HUD freshness and input-to-image (26 October 2026)

**Branch:** `dev/ps5-sparse-jit`. **Hardware baseline:** native `cd4857c8` (25 October).
**Status:** F01–F06 = 6/6 *host pre-console contracts*, NOT 6/6 gameplay fixes. **F07 OPEN**.
This note reconstructs previously documented hardware evidence rather than claiming a new fix.
Console logs and player screenshots remain private; never ship them as public GitHub artifacts.

## Critical feedback to preserve

- Worst *reported* playability: old cache with detailed logs; retaining the cache then reenabling logs also felt worse. **Cleared cache + quiet logging is the best playable user baseline**, still with visible stutter and imperfect HUD. Different sessions are not a controlled A/B of cache or logging cost.
- HUD/text/player names can appear long after a black rectangle, and their visible changes **coincide with perceived judder**. A black banner lasts until another scene refresh at introduction/half-time. Team-management/pause controls also lag, so the issue is **not only a font shader**.
- Changing 1440p/1x to 2160p/1.25x did not solve it; 0.25x–2x variants still stuttered; a separate experimental 4x mode triggered Vulkan device-memory exhaustion. **OOM is a separate stability subcase, not the main F07 goal.**
- The user's request is to resolve smooth frame/guest progress, then HUD/jersey/pitch correctness, without repeatedly asking for console tests before local source, sanitizer and native validation.

## Proven hardware trace chronology — distinct instruments

| Build / interval | Hardware evidence | What it does NOT prove |
| --- | --- | --- |
| 8 Oct dense JIT | 6,534 callbacks over ~226s, weighted 28.94 FPS, 102 >50ms and 26 >100ms, max 481.6ms; later bad_alloc with dense 4.3 GiB JIT budget | JIT exhaustion explains every later stutter |
| 12 Oct pre-R359 windows | slow periods had ~6.8x more guest cache-lock collisions, 4x longer CPU-write wall time; partial correlation with late frames after GPU workload adjustment | precise lock owner or direction of causality |
| 12–13 Oct R350/R402 | producer queue-full association +0.821 in an older trace; other freezes have 0 full-queue windows and render callback heartbeat. R400c HUD disappears progressively despite continuing gameplay, nine no-pipeline drops were early and stopped increasing | raising queue length or fixing startup pipeline drops alone recovers late HUD |
| 14 Oct `2efd8b3c` | 415 five-second windows, 858 intervals >50ms, 10 >500ms, worst 1288ms. After match, GPU/draw/IPC counters kept moving while visual game remained frozen; some storage/audio requests flatlined | healthy guest logic from 30-FPS presentation |
| 15 Oct native detailed `56293953` | 232 paired windows; 13 windows with >300ms interval; nine of those had >=500ms summed JIT time; distinct 285ms texture mutex wait in another sample | all large gaps due to buffer/texture contention |
| 21 Oct detailed vs quiet | 232 detailed windows, 466 >50ms and worst 1095.7ms; separate quiet build 270 windows, 873 >50ms, worst ~809ms. Different code/JIT settings, NOT matched logging benchmark | diagnostic logging alone caused stutter |
| 25 Oct `cd4857c8` | 1440p: 204 windows, median 29.56 FPS, minimum 14.48, worst 689.8ms, 142 >100ms, ~10.75s cumulative cache waits. 2160p: 48 windows, median 29.95, worst 977.6ms, 67 >100ms | HUD draw times or exact HUD-change-to-stall correlation |
| 26 Oct 4x crash | `VK_ERROR_OUT_OF_DEVICE_MEMORY` in a separate resolution/configuration experiment | root cause of 1x visual judder |

**Measurement rules:** per-5s CPU wait and JIT totals sum work across workers; do not subtract them directly from one frame's wall time. A compositor callback rate, frame `lateN` counts and zero draw drops cannot prove fresh pixels. Missing DEV counters in RELEASE are **unavailable**, not zero actual work.

## Relecture indépendante du dernier paquet RELEASE, sessions correctement séparées

L'ancien analyseur détaillé \`analyze-fc27-stutter.py\` attend les marqueurs
\`EDEN_DEV_GPU\`, absents des journaux RELEASE \`heap(20261025-225407).log\`.
Le nouvel outil \`tools/analyze-fc27-release-sessions.py\` utilise les marqueurs
\`EDEN_SESSION_SOURCE\` pour **séparer les deux sessions de même SHA** et apparie
les seuls \`EDEN_VULKAN_FRAME total=\` / \`EDEN_FRAME_PRESSURE frame=\`
disponibles.

| Mesure | 1440p/1× | 2160p/1,25× |
| --- | ---: | ---: |
| Fenêtres appariées | 204 | 48 |
| Retards de présentation >50ms (\`late50\`) | **1 073** | **192** |
| Retards >100ms (\`late100\`) | 142 | 67 |
| Plus longue présentation | 689,834ms | 977,578ms |
| Corrélation cinq secondes \`cache_wait_ms\` / \`late50\` | +0,222 | +0,313 |
| Fenêtres avec au moins cinq \`late50\` | 71 | 16 |
| Part des \`late50\` dans ces fenêtres | 90,8% | 91,1% |

Les fenêtres lentes se **concentrent en rafales** mais plusieurs rafales
surviennent avec peu de contention. À 2160p, la fenêtre se terminant à
\`frame=5439\` montre **37** retards >50ms et un intervalle de
**977,578ms**, pour seulement **15,283ms d'attente de cache agrégée**.
Le cache ne peut pas, à lui seul, expliquer le long intervalle. Le
\`jit_ms=0\` et \`guest_ipc_ms=0\` des journaux RELEASE ne sont **pas
des mesures de travail JIT/IPC nul**. Descriptions et données agrégées
uniquement : aucune archive de journaux privée publiée.

Les sessions diffèrent par résolution, longueur et contexte ;
ces chiffres ne constituent PAS un benchmark avant/après du GPU ni une
preuve de causalité HUD. Le ressenti avec journalisation coupée reste
la référence pratique.

## Causal paths to prioritize, in order

**P0: simultaneous FPS jitter and buffered HUD/correctness.** Audit the *currently compiled* draw path:
`vulkan_rasterizer.cpp::PrepareDraw / OnCPUWrite` versus
`vk_graphics_pipeline_cost.cpp::GraphicsPipeline::ConfigureImpl`,
especially the paired `buffer_cache.mutex / texture_cache.mutex` scope and guest CPU writes. In the Oct 21 diagnostic, blocked acquisitions were ~1,005,680 buffer (9.311s summed wait) and 66,038 texture (1.080s), with observed 5s correlations +0.325/+0.101 against `late50`. Reuse/preflight optimizations already exist; do not repeat or disable required invalidations and fences without a specific source-level failure.

**P0: HUD freshness, distinct from cadence.** Follow actual TIC/TSC descriptors, NULL-view revival, GPU remaps, dirty memory and the sequence DMA → texture registration/invalidation → shader/configuration → image view → guest frame → present. Relevant files:
`vulkan-cache/video_core/texture_cache/texture_cache.h::VisitImageView/FillImageViews/CheckFeedbackLoop`,
`vk_texture_cache_cost.cpp`,
`vk_graphics_pipeline_cost.cpp::PushImageDescriptors`,
`vulkan_present_manager.cpp`.
Earlier R312 / R314 and Oct 22 missing TIC/TSC map fixes have HOST witnesses; their console effect remains **unverified**. Later HUD loss cannot be attributed to the nine early R400c `no_pipeline` drops. Keep draw rejection/error accounting but do not skip invalid drawing, force full cache invalidation every frame, or introduce unsafe frame skipping.

**F07 DrawTexture→Vulkan pipeline handoff corrected (source/host, NOT console):** the raw-image
\`BlitImageHelper::BlitColor\` called by \`RasterizerVulkan::DrawTexture\` binds an independent
graphics pipeline and descriptor set directly in the Vulkan command buffer. Unlike
\`BlitImpl\`, this path never invalidated the scheduler's cached guest graphics pipeline.
The next guest draw with an unchanged pipeline pointer could thus **skip the Vulkan
rebind and retain the blit's pipeline**. On PS5, DrawTexture now calls
\`Scheduler::InvalidateState\` after queuing the raw blit, refreshing graphics pipeline,
rescaling and descriptor state on the next draw. The new F07 host test compiles the
real selected Scheduler methods at O0/O2, exhibits the stale-state route, and
requires recovery through the corrected source. No shader cache, guest fences,
rasterizer cache mutexes, game input or CPU/JIT timing policy is bypassed.
**This is a specific HUD/2D correctness candidate, not a measured FPS improvement.**

**P1: intermittent >300–1000ms pauses.** The Oct 15 long-gap subset was often JIT-heavy even with little cache wait; inspect real A32/A64 compile/retranslate/invalidation and async first-use pipeline blocking separately. Current standard per-core JIT DEV counters do not capture all invalidations in older logs. Do not activate sparse/shared JIT by default without controlled evidence.

**P1: guest progress and input-to-visible-state.** Binder/BufferQueue/NvDisp/Host1x/HLE wake correctness (F05 HOST), physical pad → NPad publications (F06 HOST) and title's own action profile are three distinct properties. The reported frozen menu/match can persist while backend Vulkan produces 30 callbacks/s. Use future evidence only if it pairs guest thread progress and image-content freshness; no guest-save edits or artificial HOME/Plus events.

**P2: VRAM/4x OOM.** `V109` adds failure-only image/VMA-heap logs. It does not address stutter at 1x, prove fragmentation, or justify a higher resolution. Keep pressure safeguards.

## Test acceptance / stop gate

Do not request a new on-console run for an instrumentation-only patch. First prove a specific bug in an exact native source owner, reproduce failure-before/pass-after in an O0/O2 host test with lock/fence/HUD invariants and obtain a complete green native PS5 package from the SAME commit. Then one consolidated firmware-13.60 comparison of the **same 1x/1440p scene, fresh cache and logging OFF** should evaluate `late38/50/100`, worst interval and frame-content freshness, black HUD panels, jersey/grass, input delay and shutdown stability. No promise of improved FPS/HUD until demonstrated.

**Sources:** `docs/FC27_EXIT_GATES_2026-10-22.md`,
`docs/PS5_R350_2026-10-12_FC27_GPU_STUTTER_FORENSICS.md`,
`docs/PS5_R364_2026-10-12_FC27_CACHE_DOMAIN_FORENSICS.md`,
`docs/PS5_R402_2026-10-13_FC27_R400C_FULL_MATCH_AUDIT.md`,
`docs/FC27_2EFD8B3C_MATCH_FORENSICS.md`,
`docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md`,
`docs/FC27_GPU_SOURCE_TARGETS_2026-10-21.md`,
`docs/FC27_CONSOLE_2026-10-26_AA_OOM_LOADING.md`.
