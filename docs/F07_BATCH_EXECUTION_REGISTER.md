# F07 — registre d'exécution par lots, reprise sans boucle
_Mis en place le 28 octobre 2026 — branche d'exécution unique : `dev/ps5-sparse-jit`._

> **Document de reprise opérationnel** : lire ce fichier AVANT chaque nouvelle session `continue`, puis lire `docs/F07_FUNCTION_SCOPE_2026-10-28.md` et `docs/FC27_F07_MASTER_TRACKER.md`. Toujours relire le HEAD réel et les checks CI avant de modifier. Conserver la branche unique et le générateur du fork Vulkan en synchronisation avec les sources sélectionnées. **Reprise horaire programmée** : l'automatisation « Eden Encore — reprise F07 » lit ce registre et tente de progresser sur le dépôt une fois par heure. Elle n'assure pas une exécution ininterrompue ni une validation sur console ; conserver les checkpoints et poursuivre manuellement avec « continue » reste possible.

## Objectif et périmètre

Terminer **tous les changements identifiés, justifiés et sûrs** pour les 38 points de fonction / 8 fichiers recensés dans F07. **38 points ne signifient pas 38 corrections nouvelles**. Plusieurs protections sont déjà implémentées ; pour les autres, une revue sans modification est une issue valide. Le but n'est **pas** d'ajouter des optimisations spéculatives au détriment de l'exactitude des shaders, de la fraîcheur HUD, de l'ordre FIFO Vulkan, de la mémoire invitée ou de la stabilité.

**Règle de statut (fonction par fonction) :** `À AUDITER` → `SANS MODIF JUSTIFIÉE` ou `PATCH INTÉGRÉ` → `SOURCE ALIGNÉE` → `HÔTE/CI VALIDÉ` → `CONSOLE VALIDÉ`. On ne marque jamais `CONSOLE VALIDÉ` sur la seule base d'un harnais hôte. Ajouter hash/commit, témoin, décision et risque pour chaque point. Le total de « fonctions restantes » ne diminue que lorsque la décision est tracée, pas au nombre de commits.

## Point exact de reprise

- Dernière référence de modification métier connue au début du registre : `2eb610497ee800ba522390c42b7a56d16d8e208b` — second refus de `CommandChunk::Record` non silencieux sur PS5, rollback du mémo d'état Vulkan.
- **Échec CI confirmé sur ce SHA** : fast gate `40782741133`, étape `Pinned Vulkan source reproduction`, écart du fichier `include/video_core/renderer_vulkan/vk_scheduler.h` : le générateur n'ajoutait pas `#include <new>` alors que le fork livré l'avait. **Correction intégrée dans le lot créant ce registre**, recontrôler au prochain gate. Ce n'est pas un échec de rendu PS5 observé.
- **Aucune métrique matérielle nouvelle** ne démontre encore que FC 27 tient 30 FPS stables ni que les retards HUD/pause ont disparu.
- **Prochain acte** : parcourir B1 → B4 ci-dessous sans rouvrir les corrections déjà démontrées. Chaque patch Vulkan doit mettre à jour simultanément `vendor/encore-active/eden-vulkan/**`, `tools/prepare-vulkan-port.py` et les tests source-extraits affectés. Ne pas repartir sur la branche nouvelles fonctionnalités/spec.
- **Stop/reprise** : avant toute fin de session, consigner ici : SHA HEAD réel, lot terminé, fichiers touchés, fonction suivante, éventuel blocage, dernière preuve et état CI. Au prochain `continue`, repartir de ces lignes, pas d'un nouvel audit complet.

## Inventaire des 38 décisions : huit fichiers moteur

Légende : `[ ]` = décision finale encore à consigner ; un contrôle peut déboucher sur « déjà protégé, aucun changement ». Le texte décrit l'action **à vérifier**, non une panne avérée ni la promesse d'un patch.

### B1 — P0.1 : traductions shader et cache Vulkan (7)
Fichier : `vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp`

- [x] 01 `CurrentGraphicsPipeline` — conserver les hits rapides, vérifier absence de rescans ou de traduction cachée pour HUD identique ; comparer hit/miss.
- [x] 02 `CurrentGraphicsPipelineSlowPath` — auditer saturation/reprise bornée de 64 clés échouées et fraîcheur des caches invalidés.
- [x] 03 `CreateGraphicsPipeline` — attribuer CFG/IR/SPIR-V et coût synchrone initial, vérifier priorité des tâches vs optimiseur ; n'exporter hors owner que les parties thread-safe prouvées.
- [x] 04 `CurrentComputePipeline` — vérifier cache de pipeline, reprise bornée 32 clés et absence de nouvel essai à chaque dispatch.
- [x] 05 `CreateComputePipeline` — vérifier coût de traduction initiale, admission worker, timeout/exception et disponibilité.
- [x] 06 `LoadDiskResources` — vérifier préchauffage persistant limité à 8, contenu réel valide et absence d'arrêt du worker shader.
- [x] 07 `QueueVulkanPipelineCacheFlush` — vérifier coalescence, durée de vie du cache et rattrapage d'une tâche de sauvegarde rejetée.

**B1 — source audit completed, CI and console pending (407ad36).**

| No. | Function | Source decision | Evidence/remaining risk |
|---:|---|---|---|
| 01 | `CurrentGraphicsPipeline` | No speculative change | Transition hits avoid cache slow path; guest register refresh must be preserved. Console HUD frequency unmeasured. |
| 02 | `CurrentGraphicsPipelineSlowPath` | Existing guard retained | Failed shader recovery 64-key cap and one delayed retry, with cold-failure-only rotation. Host CI pending. |
| 03 | `CreateGraphicsPipeline` | No additional safe change proved | CFG/IR/SPIR-V translation still GPU-owner synchronous; first-use priority and detailed phase counters exist. Cold stalls not solved. |
| 04 | `CurrentComputePipeline` | Existing guard retained | Bounded 32-key retry, cold-failure-only rotation, no repeat translation on normal cache hits. |
| 05 | `CreateComputePipeline` | No additional safe change proved | Foreground priority and shader-phase instrumentation exist. Moving guest shader environments to other threads is not justified yet. |
| 06 | `LoadDiskResources` | Patch integrated | `407ad36`: both reader writes to `state.total` now share the worker mutex. Prewarm 8, reader-only cancellation and join preserved. |
| 07 | `QueueVulkanPipelineCacheFlush` | Existing guard retained | Single in-flight flush, bounded time gate, queue rejection rollback and atomic worker error handoff. |

These checkmarks record a SOURCE-LEVEL DECISION, NOT green CI, measured FPS or PS5 console validation. Do not silently promote these states.
**Porte B1 :** hot path cache hit sans coût superflu ; coûts froids et politiques de réessai bornés ; aucun shader invalide ni suppression de rendu pour « gagner » des FPS.

### B2 — P0.2 : pipeline graphique/compute et anneaux descripteurs (10)
Fichiers : `vk_graphics_pipeline_cost.cpp` (5), `vk_compute_pipeline_cost.cpp` (2), `vk_descriptor_buffer_cost.cpp` (3) sous `vendor/encore-active/eden-vulkan/`.

- [x] 08 `GraphicsPipeline::ConfigureImpl` — scratch préalloué avant verrous, TIC/TSC et buffers valides après invalidation.
- [x] 09 `GraphicsPipeline::ConfigureDraw` — commande wait unique ordonnée, publication acquire, réutilisation de descriptors uniquement si mêmes données/génération, rebind après refus de Record.
- [x] 10 `GraphicsPipeline::AddTransition` — cohérence des deux vecteurs si allocation refusée, aucune exception facultative cassant un draw valide.
- [x] 11 `GraphicsPipeline::MakePipeline` — builder/pipeline publication atomique, compteur priorité premier usage, exceptions et fermeture de completion.
- [x] 12 `GraphicsPipeline::QueueOptimizedPipeline` — quota de travaux spéculatifs, priorité au shader initial, absence de fuite des slots de queue.
- [x] 13 `ComputePipeline::Configure` — wait unique, scratch et payload, refus de pipeline nul, reliaison de descripteurs lors d'un reset.
- [x] 14 `ComputePipeline::PreflightDescriptorScratch` — allocations hors pair-lock et slots corrects en cas d'appels imbriqués.
- [x] 15 `DescriptorBufferRing::PreflightFrameReuse` — vérifier synchronisation tick/fence et absence de réutilisation avant libération.
- [x] 16 `DescriptorBufferRing::PreflightCapacity` — capacité réelle et garde avant acquisition des verrous guest.
- [x] 17 `DescriptorBufferRing::Allocate` — échec de réservation non silencieux, génération, durée de vie et retour correct au pool.

**B2 — 10/10 SOURCE reviews recorded (not console validated).**

| No. | Decision | Source observation / remaining risk |
|---:|---|---|
| 08 | Existing safeguard retained; no further safe patch proved | Scratch is leased/reused; image table sync bypassed for descriptor-free draws. Nested depth >=3 still uses safe fallback reserve under lock. |
| 09 | Existing safeguard retained; no further safe patch proved | FIFO wait once, acquire load, descriptor-set memo committed after Record; descriptor-buffer identity includes generation and payload. Reject/restore cases need gate. |
| 10 | Existing safeguard retained; no further safe patch proved | Both vectors rolled back together if optional append fails; gameplay draw kept. |
| 11 | Existing safeguard retained; no further safe patch proved | Completion guard releases waiter and shader notifier after Vulkan builder error; null pipeline remains rejected. |
| 12 | Existing safeguard retained; no further safe patch proved | 16-slot optional quota, quiet 16-ms window and cancel/exception slot release preserve first-use priority. |
| 13 | Existing safeguard retained; no further safe patch proved | FIFO wait recorded after acceptance, same-generation payload reuse and new descriptor allocation fallback. GPU completion cost not benchmarked. |
| 14 | Existing safeguard retained; no further safe patch proved | Reserves compute views/samplers and payload before guest pair-lock; nested fallback remains. |
| 15 | Existing safeguard retained; no further safe patch proved | Earlier wait uses matching previous frame tick, then disables frame_reused; no premature recycling intended. |
| 16 | Existing safeguard retained; no further safe patch proved | Full-ring scheduler.Finish moved before cache locks when allocation is known; uncertain cases retain fallback. |
| 17 | Existing safeguard retained; no further safe patch proved | Checks CanAllocate, ticks/generation and returns empty allocation on overflow; rare scheduler.Finish under pair-lock remains for correct fallback. |

These source-level decisions are not a claim of complete optimization or green CI. The fallback GPU waits under cache mutexes are still potentially expensive, but must not be removed without evidence that correctness is preserved. Host witnesses and console timings remain mandatory.
**Porte B2 :** aucune commande non acceptée considérée soumise, aucune attente pipeline sous pair-lock sans nécessité démontrée, correction des buffers/descripteurs préservée.

### B3 — P0.3 : coût sous verrous, progression GPU/CPU, présentation (9)
Fichiers : `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp` (6) et `vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp` (3). Ne pas traiter le miroir guest comme preuve du rendu final.

- [ ] 18 `RasterizerVulkan::PrepareDraw` — pair-lock, prévalidation descriptor/scheduler, fast path des draws sans descriptor, zéro perte d'état.
- [ ] 19 `RasterizerVulkan::DispatchCompute` — buffer indirect non nul, préallocation, pair-lock et rendez-vous worker.
- [ ] 20 `RasterizerVulkan::OnCPUWrite` — invalidation de pages, aliases et textures après écriture CPU, pas d'ancien HUD réutilisé.
- [ ] 21 `RasterizerVulkan::AccelerateDisplay` — choix d'une frame réellement produite, texture fraîche et aucune présentation fantôme.
- [ ] 22 `RasterizerVulkan::TickFrame` — nettoyage/éviction, pression mémoire et pas de travail synchrone lourd sous verrou inutile.
- [ ] 23 `RasterizerVulkan::FlushWork` — ordre GPU, frontières des batchs, absence de wait durable sans nouveau progrès.
- [ ] 24 `guest-bridge::RasterizerVulkan::PrepareDraw` — cohérence native/backport et mêmes préconditions de cache/descriptor.
- [ ] 25 `guest-bridge::RasterizerVulkan::DispatchCompute` — alignement du dispatch guest, mémoire et ordre des barrières.
- [ ] 26 `guest-bridge::RasterizerVulkan::OnCPUWrite` — invalidation guest complète et traçage de l'écriture jusqu'au cache GPU.

**Porte B3 :** distinguer frame non produite, commande non enregistrée, worker bloqué et image répétée ; corréler temps >50/100 ms, sans sacrifier la cohérence.

### B4 — P0.4 : textures, upload et fraîcheur HUD (12)
Fichiers : `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h` (9) et `vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp` (3).

- [ ] 27 `TextureCache::QueueAsyncDecode` — admission bornée, génération/pages courantes et annulation sûre en cas d'erreur.
- [ ] 28 `TextureCache::TickAsyncDecode` — récupération des résultats et exceptions, révision courante, file vide sans cooldown inutile.
- [ ] 29 `TextureCache::QueueAsyncUnswizzle` — valider budgets 3D, dimensions et compatibilité du passage BCn avant mise en file.
- [ ] 30 `TextureCache::TickAsyncUnswizzle` — rétablissement `CpuModified`, handles valides, rollback si refus/exception/remap.
- [ ] 31 `TextureCache::RefreshContents` — éviter de publier une texture « propre » avant transfert confirmé, vérifier le fallback synchrone.
- [ ] 32 `TextureCache::UploadImageContents` — staging >= taille ET handle Vulkan valide, synchronisation et retry sur échec.
- [ ] 33 `TextureCache::TryFindFramebufferImageView` — exclure aliases sales/décodage en cours, prendre seulement une image visible actuelle.
- [ ] 34 `TextureCache::SynchronizeAliases` — cohérence alias/remap/CPU-write, sans accès prématuré aux pixels périmés.
- [ ] 35 `TextureCache::TickFrame` — GC, readbacks différés, progression des jobs et absence de double travail de frame.
- [ ] 36 `TextureCacheRuntime::UploadStagingBuffer` — protéger refus d'allocation/handle nul/mapping court et barrières d'upload.
- [ ] 37 `TextureCacheRuntime::TickFrame` — recyclage GPU sûr et coût borné dans la cadence de frame.
- [ ] 38 `TextureCacheRuntime::AccelerateImageUpload` — BCn 3D chunk par chunk, état/layout/barrières corrects et rollback complet.

**Porte B4 :** pas de bandeau noir causé par ancien framebuffer propre sélectionné à tort ; toutes les erreurs d'upload gardent une source récupérable ; aucun gain HUD déclaré sans preuve console.

## B5 — intégration puis campagne de tests groupée

1. Après les **décisions sur les 38 points**, vérifier une fois la synchronisation du fork Vulkan généré, les dépendances pégées et le miroir guest. Ne modifier que des divergences démontrées.
2. Exécuter les **tests hôte par sous-système** et les scénarios de refus/récupération (native & desktop, O0/O2, ASan/UBSan quand applicable) puis **un seul gate de validation global sur un HEAD stabilisé** : fast gate, source preflight, build PS5 authentique, analyse sécurité. À noter : les workflows GitHub peuvent se déclencher automatiquement sur les pushes intermédiaires ; ne pas confondre cette exécution automatique avec une validation finale.
3. **Ne demander un test console qu'après l'intégration et les gates requis verts sur le même SHA.** Scènes identiques FC27 1440p/1× : froid/chaud, logging OFF pour FPS, HUD changement, pause et mi-temps, relance, puis BOTW. Mesurer frames >50 et >100 ms, pires écarts, progression du guest, contenu réellement nouveau (HUD), crash et commandes.
4. Si les critères échouent, rouvrir **uniquement** le sous-système incriminé avec preuve, pas l'inventaire entier. On n'annonce pas « optimisation totale » tant qu'il reste une anomalie mesurée, et l'absence de nouvel objectif de performance ne prouve jamais qu'aucune optimisation imaginable n'existe.

## Journal de lots

| Lot | État | Résultat/preuve | Prochaine action |
|---|---|---|---|
| B0 — registre + correction générateur du scheduler | **Intégré dans le commit qui ajoute ce fichier** | Réconciliation du `#include <new>` à vérifier par CI, échec précédent #40782741133 identifié | B1 P0.1 01→07 |
| B1 — shader/cache | **7/7 décisions source; CI/console ouvertes** | Réessais 64/32, priorité premier usage, prewarm 8 ; correction mutex `407ad36` | Gate hôte puis mesures console ; ne pas rouvrir sans échec observé |
| B2 — pipelines/descripteurs | **10/10 décisions source; CI/console ouvertes** | Scratch preflight, FIFO wait, rollback Record, ring/tick et quota optimiseur inspectés | CI groupée puis qualifier les attentes fallback réellement coûteuses sur console |
| B3 — rasterizer/guest | **À traiter** | Pair-lock/preflight et tests dispersés existants | Clore les 9 décisions |
| B4 — textures/HUD | **À traiter** | Nombreuses gardes async/readback/BCn déjà intégrées | Clore les 12 décisions |
| B5 — gates groupés + console | **Bloqué par B1–B4** | Build natif sur SHA unique, puis test physique FC27/BOTW | Fermer ou rouvrir par preuve |

**Reprise programmée :** tâche horaire « Eden Encore — reprise F07 » ; ses actions doivent être revérifiées via le HEAD, les commits et le journal de lots. Elle doit cesser lorsque les critères de clôture sont satisfaits et aucune modification ne doit être inventée si aucun outil n'est accessible.

**Commande de reprise utilisateur :** « continue Eden Encore d'après `docs/F07_BATCH_EXECUTION_REGISTER.md` ». En début de reprise, contrôler le HEAD réel, pas uniquement le SHA imprimé ici. Ne pas multiplier les branches/PR ni inventer de résultat CI.

## F07 checkpoint — 2026-10-28

- Source decision count: B1 7/7; B2 10/10; B3 0/9; B4 0/12. The resulting 21 remaining checks are audit decisions, not 21 proven defects. These remaining 31 are audit decisions, not 31 proven defects.
- Business code commit: `407ad36ef5207d4fef964074241cb197fb153248`. Fork generator and selected Vulkan source were changed together, with host witness updated.
- CI checks not yet proven green on `407ad36`; no console FPS or HUD freshness proof. No PR or secondary branch created.
- Next: B2 08–17 source review, targeted regressions, then B3/B4, followed by one coherent four-gate/console campaign.

- B2 n°08–17: 10 source decisions recorded from the three selected Vulkan modules. No performance gain or successful PS5 build has been inferred.
