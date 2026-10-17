# Eden Encore — active native dependency audit register

**Branch:** dev/ps5-sparse-jit. **Updated:** 2026-10-17. **Baseline reviewed:** 436a102 (sources précédant cet enregistrement).
**Technical scope:** guest CPU/HLE, JIT, GPU worker, Vulkan, memory coherency,
native build/CI. Launcher and theme work belongs to its separate conversation.

This is the **single place to resume this technical audit**.
**Non, this is not an exhaustive repository-wide inventory.** The 38
indexed graph rows cover known high-relevance paths; the completed register
captures prior host checks, and unenumerated dependencies are separately
flagged below. New source discoveries must be added rather than forgotten. Do not open
previously reviewed files without naming a concrete new source change or new
evidence. Other chats may change the branch concurrently; re-read HEAD before
any operation, and avoid unrelated files.


## Déjà traité — contrôles terminés et preuves accessibles

**19 validations ciblées historiquement établies.** Elles recouvrent en
partie les lignes B/Q/D/V/J/M/S du graphe ci-dessous : **ne pas additionner
ces deux décomptes comme s'il s'agissait de travaux différents**.

La pastille verte signifie uniquement : **le test hôte cité a réussi
pour la propriété indiquée**. Elle ne signifie **ni validation console,
ni gain de FPS, ni disparition des freezes**. Certains tests verts
démontrent précisément qu'une approche est dangereuse.

| ID | Travail déjà effectué | Fonctions / composant | Test | Preuve datée | Limite encore ouverte |
| --- | --- | --- | --- | --- | --- |
| C01 | Lecture/écriture atomique du drapeau CPU | `PhysicalCore::IsInterrupted / Interrupt / ClearInterrupt` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-physical-core-atomic-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Preuve hôte et CodeQL réussies ; ne prouve pas la sortie JIT |
| C02 | Interruption demandée ≠ sortie effective du JIT | `PhysicalCore::RunThread` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-physical-core-interrupt-ack-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38985717189) | Test hôte terminé ; protocole de reprise non créé |
| C03 | Mémoire invitée : alias direct contre copie | `GuestMemory / SafeRead` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-guest-memory-coherence-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38984636283) | La copie n'est pas garantie par le simple indicateur SafeRead |
| C04 | Dépendances indirectes des commandes DMA | `DmaPusher::Step` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-dma-indirect-dependencies-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38983008233) | Test établit une limite, pas une autorisation de réordonner |
| C05 | Reprise naïve de DMA provoque un rejeu | `DispatchCalls / ProcessCommands` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-dma-resume-boundary-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38983923342) | Résultat négatif validé : ne pas activer ce mode |
| C06 | Risque d'interblocage lié au FIFO GPU | `GPU tick / quiescence` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-fifo-quiescence-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38982519437) | Modèle hôte validé, non-détection en jeu |
| C07 | Réutilisation des emplacements de la file GPU | `SPSCQueue / EmplaceWaitWithStopToken` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-queue-slot-lifetime-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38992155660) | Test isolé PASS, mais CI complète KO sur un garde-fou CMake distinct |
| C08 | Capture sûre des plages de lecture GPU | `RequestSyncOperation` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-read-capture-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Correctif source + test hôte, aucune preuve de fluidité |
| C09 | Bornes des régions dirty GPU | `GPUDirty / Collect` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-dirty-subregion-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Contrôle des sous-régions validé sur hôte |
| C10 | Bornes mémoire invitées/lectures auxiliaires | `GPU Read / guest spans` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-span-range-host.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Couvre les cas ciblés de limites de spans |
| C11 | Retry Vulkan en cas de perte de surface | `PresentManager::CopyToSwapchain` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-present-retry-liveness.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Liveness ciblée ; pas de validation matérielle |
| C12 | Bornes de retry lors d'acquisition swapchain | `Swapchain::AcquireNextImage` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-swapchain-acquire-bounds.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Le timeout est borné ; un GPU bloqué reste possible |
| C13 | Métadonnées swapchain entre threads | `Swapchain` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-swapchain-snapshot.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Vérifie les snapshots ; console non validée |
| C14 | Durée de vie des images et vues Vulkan | `Layer::ReleaseRawImages` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-raw-view-lifetime.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Évite un ordre de destruction dangereux dans le scénario testé |
| C15 | AA et ressources de rendu lors du resize | `Layer::RefreshResources` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-aa-lifetime.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Test de durée de vie hôte |
| C16 | Stride de staging et réallocation | `Layer::UpdateRawImage` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-stride-reallocation.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Test de borne/réallocation hôte |
| C17 | Transitions de couches Vulkan | `BlitScreen::DrawToFrame` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-layer-lifetime.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Test de cycle de vie des couches |
| C18 | Classification des fenêtres de stutter FC27 | `analyze-ps5-cache-contention.py` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-fc27-cache-contention-classifier.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38989960870) | Analyse offline vérifiée ; attribution à une seule frame interdite |
| C19 | File GPU : attente producteur interrompable | `ThreadManager::PushCommand` | [![OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-gpu-producer-stop.py) | [Preuve / CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38986808108) | Test source/hôte ; pas de conclusion hardware |

### Audits archivés à ne pas recommencer

Les rapports détaillés antérieurs sont conservés, notamment
[R327 — durée de vie des couches](PS5_R327_2026-10-11_VULKAN_LAYER_LIFETIME.md),
[R328 — AA](PS5_R328_2026-10-11_VULKAN_AA_RESIZE_LIFETIME.md),
[R329 — stride](PS5_R329_2026-10-11_VULKAN_FRAMEBUFFER_STRIDE.md),
[R331 — vues](PS5_R331_2026-10-11_VULKAN_RAW_VIEW_LIFETIME.md),
[R335 — surface](PS5_R335_2026-10-12_VULKAN_SURFACE_LOST_BOUNDED_RETRY.md),
[R336 — snapshot](PS5_R336_2026-10-12_VULKAN_SWAPCHAIN_SNAPSHOT_RACE.md),
[R337 — acquisition](PS5_R337_2026-10-12_VULKAN_ACQUIRE_RECREATION_BOUNDS.md),
[R386 — match figé malgré FPS](PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md)
et le [rapport intégration CPU/GPU/JIT](INTEGRATION_AUDIT_CPU_GPU_JIT_2026-10-14.md).
Une analyse historique n'est pas automatiquement un correctif ni un
test complet. Ces archives sont à relire **avant** d'ouvrir un doublon.


## Status is not success in game

- **HOST**: a *specific property* was exercised by a host test. A passing
  test may deliberately prove an unsafe behavior. It does NOT certify
  end-to-end console performance, correct emulation or freeze resolution.
- **SOURCE**: located and inspected in source, but no causal or end-to-end
  proof. Do not count it as solved.
- **OPEN**: concrete source-level question not resolved yet.
- **PARKED**: intentionally stopped. Deferred native bridge #187 stays OFF.

Priority **P0** means actual frozen gameplay/HUD/long-frame causality;
**P1** means correctness and native integration; **P2** means experimental
memory bridge safety. A HOST property can still have an unmet device gate.

## Dependency order / no more circular audits

- Runtime build: B01 => Q01/Q02/Q03 => V01 => V02/V04/V05 => S01/S02
- Guest progress: B01 => J01/J02/J03/J04 => H01/H02/H03
- Deferred bridge only: D01/D02 + M01/M02/M03/M04 (**PARKED**, not a
  prerequisite to fixing normal game freezes).

**Next work in order:** T01 resolve both historical generator ceilings; then
H03 using already reviewed H01/H02; then V02 and V04 if there is a
presentation/HUD stall distinct from guest progress; then J01 and V05
only for remaining *unattributed* long-frame events. Do not return to
aggregate JIT/cache statistics already studied.

## Source files, functions and acceptance criteria

IDs are stable across commits. Depends lists IDs that must be understood
first, not a claim that they are semantically proved. Source paths and
function/contract tokens are checked by CI for existence only; the
**Remaining acceptance** column is what still needs proof.

<!-- AUDIT_ROWS_START -->
| ID | Priorité | Dépend | Fichier | Fonctions / contrat | État technique | Preuve | Validation encore nécessaire | Visuel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | P1 | - | headless/CMakeLists.txt | EDEN_SHARED_JIT; EDEN_JIT_COMPILE_BATCH | SOURCE | tools/check-native-build-recipe.py | Verify selected native build flags before claiming integration | 🟡 Source étudiée |
| B02 | P1 | B01 | headless/CMakeLists.txt | write_derived; queue_slot_repair | HOST | tools/check-native-gpu-queue-slot-lifetime-host.py | Check native toolchain separately; host regression covers derived slot lifecycle | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-queue-slot-lifetime-host.py) |
| Q01 | P1 | B02 | vendor/sources/eden/src/common/bounded_threadsafe_queue.h | TryEmplace; Pop; std::construct_at | HOST | tools/check-native-gpu-queue-slot-lifetime-host.py | No claim about a specific game's resource lifetime | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-queue-slot-lifetime-host.py) |
| Q02 | P1 | Q01 | headless/gpu_queue_stop_wait.inc | EmplaceWaitWithStopToken | SOURCE | tools/check-gpu-producer-stop.py | Keep stop-aware producer wake and ownership checks | 🟡 Source étudiée |
| Q03 | P1 | Q01,Q02 | vendor/encore-active/eden-gpu/gpu_thread_dev.cpp | ThreadManager::RunWorker; ThreadManager::PushCommand; ThreadManager::Stop | SOURCE | tools/check-vendored-gpu-thread.py | Worker can stall without fatal exception; prove progress separately | 🟡 Source étudiée |
| Q04 | P1 | Q03 | vendor/sources/eden/src/video_core/gpu.cpp | GPU::OnCPURead; GPU::WaitForSyncOperation; GPU::TickWork | SOURCE | docs/2026-10-16_GPU_SYNC_TICK_SNAPSHOT.md | Check queued CPU read tick dependencies before any FIFO modification | 🟡 Source étudiée |
| D01 | P2 | Q03 | vendor/sources/eden/src/video_core/dma_pusher.cpp | DmaPusher::Step; DmaPusher::DispatchCalls; DmaPusher::ProcessCommands | HOST | tools/check-native-dma-resume-boundary-host.py | Unsafe restart proved; no native replay or partial continuation | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-dma-resume-boundary-host.py) |
| D02 | P2 | D01 | vendor/sources/eden/src/video_core/dma_pusher.cpp | DmaPusher::Step; DmaPusher::SetState | HOST | tools/check-native-dma-indirect-dependencies-host.py | Late guest-RAM command decoding remains unsealed | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-dma-indirect-dependencies-host.py) |
| V01 | P0 | Q03 | vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp | Scheduler::WorkerThread; Scheduler::WaitWorker; Scheduler::Finish | SOURCE | docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md | Separate worker queue drain from physical GPU device fence wait | 🟡 Source étudiée |
| V02 | P0 | V01 | vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp | PresentManager::GetRenderFrame; PresentManager::PresentThread; PresentManager::WaitPresent | SOURCE | tools/check-vulkan-present-wait-host.py | Identify actual presentation stall boundary versus guest HUD | 🟡 Source étudiée |
| V03 | P0 | V02 | vendor/encore-active/eden-vulkan/vulkan_swapchain.cpp | Swapchain::AcquireNextImage | HOST | tools/check-ps5-vulkan-swapchain-acquire-bounds.py | Acquire retries bounded; no device-liveness claim | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-ps5-vulkan-swapchain-acquire-bounds.py) |
| V04 | P0 | V02 | vendor/encore-active/eden-vulkan/vulkan_renderer.cpp | RendererVulkan::Composite; RendererVulkan::PresentLoading | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Prove compositor remains alive when guest match is frozen | 🟡 Source étudiée |
| V05 | P0 | V01,V04 | vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp | RasterizerVulkan::PrepareDraw; RasterizerVulkan::OnCPUWrite; RasterizerVulkan::GetFlushArea | SOURCE | tools/check-ps5-vulkan-cache-phases.py | Identify mutex owner for rare 285-ms texture wait; no guessing | 🟡 Source étudiée |
| V06 | P1 | V05 | vendor/sources/eden/src/video_core/texture_cache/texture_cache.h | TextureCache<P>::RunGarbageCollector; TextureCache<P>::TickFrame | SOURCE | tools/check-vulkan-gc-budget-host.py | Zero GC evictions near 3300-3600; deprioritized for that window | 🟡 Source étudiée |
| V07 | P1 | V05 | vendor/sources/eden/src/video_core/renderer_vulkan/vk_pipeline_cache.cpp | PipelineCache::CurrentGraphicsPipeline | SOURCE | tools/check-vulkan-shader-workers.py | Link pipeline work to an otherwise unexplained long frame | 🟡 Source étudiée |
| V08 | P1 | V05 | vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp | RasterizerVulkan::TickFrame | SOURCE | tools/check-ps5-vulkan-cache-phases.py | Only time critical sections if evidence identifies new window | 🟡 Source étudiée |
| J01 | P0 | B01 | headless/performance.cpp | eden_jit_compile; eden_jit_phases | SOURCE | docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md | Distinguish newly compiled blocks versus invalidation and duplicates | 🟡 Source étudiée |
| J02 | P1 | J01 | vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_64.cpp | ArmDynarmic64::SignalInterrupt | SOURCE | docs/DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md | Interrupt request alone is not JIT-exit acknowledgment | 🟡 Source étudiée |
| J03 | P1 | J02 | vendor/sources/eden/src/core/hle/kernel/physical_core.cpp | PhysicalCore::RunThread; PhysicalCore::Interrupt; PhysicalCore::ClearInterrupt; PhysicalCore::IsInterrupted | HOST | tools/check-native-physical-core-atomic-host.py | Atomic flag fixed in derived build; epoch handoff not implemented | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-physical-core-atomic-host.py) |
| J04 | P0 | J03 | vendor/sources/eden/src/core/cpu_manager.cpp | MultiCoreRunGuestThread | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Find the guest core wait versus actual resumed JIT execution | 🟡 Source étudiée |
| H01 | P0 | J04 | vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp | KConditionVariable::Wait; KConditionVariable::Signal | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Determine real wait/notify ownership; last-SVC sample is not a stack | 🟡 Source étudiée |
| H02 | P0 | H01 | vendor/sources/eden/src/core/hle/kernel/k_scheduler.cpp | KScheduler::Schedule; KScheduler::Preempt | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Verify whether guest progress stalls in scheduler/wakeup | 🟡 Source étudiée |
| H03 | P0 | H02 | vendor/sources/eden/src/core/hle/kernel/k_thread.cpp | KThread::SetState; KThread::Wait | OPEN | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Inspect actual blocked thread state transitions; no HUD cause yet | 🟠 À contrôler |
| H04 | P2 | J03 | vendor/sources/eden/src/core/hle/kernel/k_interrupt_manager.cpp | HandleInterrupt; ClearInterrupt | SOURCE | docs/DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md | Keep ordinary interrupt clearing independent of future epoch gate | 🟡 Source étudiée |
| M01 | P2 | J03,V05 | vendor/sources/eden/src/core/guest_memory.h | GetSpan; FlushRegion; ReadBlock | HOST | tools/check-native-guest-memory-coherence-host.py | Direct SafeRead aliases remain mutable; no sealed snapshot | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-guest-memory-coherence-host.py) |
| M02 | P2 | M01,D02 | headless/gpu_deferred_replay.h | kNativePostStorePublicationReady | PARKED | tools/check-deferred-native-bridge-contract.py | Bridge remains false until quiescence, FIFO and snapshot proofs | ⚪ Suspendu |
| M03 | P2 | J03,M02 | docs/DEFERRED_JIT_QUIESCENCE_ARCHITECTURE_2026-10-17.md | QUIESCE; CONFIRM | PARKED | tools/check-native-jit-quiescence-model-host.py | No active native JIT-exit ACK/transition generation yet | ⚪ Suspendu |
| M04 | P2 | D01,D02,M02 | docs/DEFERRED_GPU_INDIRECT_DEPENDENCY_2026-10-17.md | DmaPusher::Step | PARKED | tools/check-native-gpu-fifo-quiescence-host.py | No unsafe GPU-worker blocking wait or FIFO reorder | ⚪ Suspendu |
| S01 | P0 | J01,V05,V02 | tools/analyze-ps5-cache-contention.py | def windows(; def report( | HOST | tools/check-fc27-cache-contention-classifier.py | Five-second aggregates cannot attribute one long frame | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-fc27-cache-contention-classifier.py) |
| S02 | P0 | S01,H01,V04 | tools/analyze-fc27-frozen-workload.py | def analyze(; def self_test( | SOURCE | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Game logic can stop while compositor still emits 30 FPS | 🟡 Source étudiée |
| S03 | P0 | S01,V04 | docs/FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md | Root cause; Vulkan | SOURCE | tools/check-fc27-cache-contention-classifier.py | Do not reclassify existing October 15 logs without new evidence | 🟡 Source étudiée |
| T01 | P1 | B01 | tools/check-maintained-audio-units.py | cmake.count; gpu_producer_wait; gpu_read_capture | HOST | tools/check-maintained-audio-units.py | Allow exactly two named slot-lifetime rewrites; preserve old 227 ceiling | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-maintained-audio-units.py) |
| T02 | P1 | T01,Q01 | tools/check-native-gpu-queue-slot-lifetime-host.py | PINNED_GPU_QUEUE_SLOT_DESTRUCTOR_REUSE_PASS | HOST | tools/check-native-gpu-queue-slot-lifetime-host.py | Queue regression passed, but whole preflight failed on T01 gate | [![Test hôte OK](https://img.shields.io/badge/test_h%C3%B4te-OK-2ea44f?style=flat-square)](https://github.com/niakw/Prospero.Eden-Encore/blob/dev/ps5-sparse-jit/tools/check-native-gpu-queue-slot-lifetime-host.py) |
| H05 | P0 | H01,H02 | vendor/sources/eden/src/core/hle/kernel/k_synchronization_object.cpp | KSynchronizationObject::Wait; Signal | OPEN | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Check guest multiobject wake paths against frozen-match samples | 🟠 À contrôler |
| N01 | P1 | Q04 | vendor/sources/eden/src/core/hle/service/nvdrv/devices/nvhost_gpu.cpp | SubmitGPFIFO; Ioctl | OPEN | docs/INTEGRATION_AUDIT_CPU_GPU_JIT_2026-10-14.md | Trace IOCTL submit and fences only if guest GPU wait is implicated | 🟠 À contrôler |
| V09 | P0 | V04 | vendor/encore-active/eden-vulkan/vulkan_present_layer.cpp | Layer::UpdateRawImage; Layer::UpdateDescriptorSet | OPEN | docs/PS5_R331_2026-10-11_VULKAN_RAW_VIEW_LIFETIME.md | Check layer resource lifetime only for new present/HUD evidence | 🟠 À contrôler |
| A01 | P1 | H03 | vendor/sources/eden/src/audio_core/renderer/voice/voice_info.cpp | VoiceInfo::UpdateParameters; VoiceInfo::UpdatePlayState | OPEN | docs/PS5_R386_2026-10-12_FC27_FREEZE_FORENSICS.md | Validate audio voice state only if match stall traces demand it | 🟠 À contrôler |
| F01 | P1 | Q04 | vendor/sources/eden/src/video_core/host1x/host1x.cpp | Host1x | OPEN | docs/INTEGRATION_AUDIT_CPU_GPU_JIT_2026-10-14.md | Trace actual host syncpoint progression if GPU command progress stops | 🟠 À contrôler |
<!-- AUDIT_ROWS_END -->


## Couverture encore NON exhaustive (à inventorier, pas à déclarer OK)

Outre les **38 lignes du graphe**, le dépôt comprend d'autres composants
susceptibles d'influencer le symptôme observé, dont les interfaces HID/commandes
en jeu, l'ordonnancement des services IPC, la restitution audio et les chemins
host-syncpoint. **Ils ne sont pas tous vérifiés par le présent tableau.**

- **Entrées/HID et pause en match :** isoler les fonctions de
  `ControllerUpdate`, du routage d'entrées et de l'overlay dans les
  sources réellement sélectionnées par CMake ; l'existence d'un contrôleur
  fonctionnel ne prouve pas que le match reçoit ses événements.
- **Services IPC/HLE et synchronisation multiple :** compléter H01–H05
  avec les objets de réveil effectivement impliqués dans les états
  des threads invités ; prioritaire pour un rendu à 30 FPS avec
  simulation figée.
- **GPU IOCTL/syncpoints, audio et composition :** N01, F01, A01
  et V09 sont désormais **ouverts et non validés**. Ne les approfondir
  qu'avec une dépendance mesurable au scénario gelé.
- **Toutes les variantes upstream/vendor et modules UI :** NON
  couvertes par cet audit de stabilité native ; inventaire complet
  du dépôt ≠ assurance de correction de FC27.

**Règle de clôture :** aucune réponse ne doit présenter « 38 lignes »
comme « toutes les fonctions restantes ». L'inventaire s'étend à mesure
des véritables appels, et une tâche n'est verte que pour son critère
de validation nommé.

## Established findings — do not re-run without changed evidence

1. October 15 FC27 session uses **Vulkan**. The 285.3 ms mutex wait is
   time lost by a guest CPU callback; the mutex *owner* is unknown.
   Texture-GC evictions were zero around frames 3300-3600. An ~980 ms
   frame had much less lock contention. See S01/S03 and the linked triage.
2. Nearly perfect 30 FPS can coexist with the **guest match remaining
   frozen**. This is not evidence the guest simulation advances.
   Sampled last-SVC values are NOT actual live waiting stacks.
   See S02 and the earlier guest freeze forensic report.
3. Atomic native physical-core flag fix (8f88877): host PASS, but
   interrupt request is not JIT exit acknowledgment. DMA partial
   resume/restart is unsafe by the prior host witness.
4. Native GPU queue slot lifetime fix (3e5af13, 8ac4929): the
   specific queue host regression PASSED inside preflight 38992155660,
   but that entire workflow FAILED due to the independent T01
   generator budget guard. This register must be updated after T01 CI.
5. Native post-store #187 bridge is still DISABLED. Negative
   host witnesses for FIFO, aliases or DMA are not permission to
   enable the bridge or request a console build.

## How to update after each task

1. Read this register, the completed-audit index, the current branch HEAD, its linked evidence,
   then only the immediate caller/callee of the first relevant OPEN
   (or SOURCE with new evidence). Preserve concurrent work ownership.
2. Record an explicit hypothesis and a falsifiable check **before**
   changing behavior. If a previous hypothesis was disproved, do not
   reopen it without a code change or new observation.
3. After a narrow fix, update its row with the test, the *actual*
   completed CI URL/conclusion and the next still-unmet acceptance.
   A green test is not a green workflow; a green workflow is not
   a console game test.
4. When blocked or out of evidence, say so and leave the row open.
   Do not add another speculative test or pseudo-progress commit.
5. Keep source/derived file distinction. Console release/build
   only upon demonstrated benefit and authorization. No UI edits here.

The automated host register check validates paths, symbols, IDs,
dependency acyclicity and statuses, **not** behavior.
