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

- [x] 18 `RasterizerVulkan::PrepareDraw` — pair-lock, prévalidation descriptor/scheduler, fast path des draws sans descriptor, zéro perte d'état.
- [x] 19 `RasterizerVulkan::DispatchCompute` — buffer indirect non nul, préallocation, pair-lock et rendez-vous worker.
- [x] 20 `RasterizerVulkan::OnCPUWrite` — invalidation de pages, aliases et textures après écriture CPU, pas d'ancien HUD réutilisé.
- [x] 21 `RasterizerVulkan::AccelerateDisplay` — choix d'une frame réellement produite, texture fraîche et aucune présentation fantôme.
- [x] 22 `RasterizerVulkan::TickFrame` — nettoyage/éviction, pression mémoire et pas de travail synchrone lourd sous verrou inutile.
- [x] 23 `RasterizerVulkan::FlushWork` — ordre GPU, frontières des batchs, absence de wait durable sans nouveau progrès.
- [x] 24 `guest-bridge::RasterizerVulkan::PrepareDraw` — cohérence native/backport et mêmes préconditions de cache/descriptor.
- [x] 25 `guest-bridge::RasterizerVulkan::DispatchCompute` — alignement du dispatch guest, mémoire et ordre des barrières.
- [x] 26 `guest-bridge::RasterizerVulkan::OnCPUWrite` — invalidation guest complète et traçage de l'écriture jusqu'au cache GPU.

**B3 — 9/9 décisions de revue source, mesures de frame toujours ouvertes.**

| N° | Fonction | Décision / risque |
|---:|---|---|
| 18 | Native PrepareDraw | Garde existante conservée, pas de changement spéculatif : Preflight scheduler and exact guest descriptors before pair-lock, reselect shader after waits; descriptor-free path avoids legacy queue. Rare fallback under lock still exists. |
| 19 | Native DispatchCompute | Garde existante conservée, pas de changement spéculatif : Null indirect buffer guard and prevalidation before cache pair, descriptor preflight and compute timing probes; false dispatch drop remains observable. |
| 20 | Native OnCPUWrite | Garde existante conservée, pas de changement spéculatif : Buffer/image page evidence guards independent cache locks, shader invalidation remains on non-short-circuit path. Early return of buffer-cache owner preserved, requires runtime proof. |
| 21 | Native AccelerateDisplay | Garde existante conservée, pas de changement spéculatif : Flushes guest invalidations before selecting the framebuffer under texture lock; cache rejects stale/dirty aliases in underlying selection function. FPS/real HUD unproven. |
| 22 | Native TickFrame | Garde existante conservée, pas de changement spéculatif : Resource ticks sequenced, texture/buffer tick each under their mutex; GC memory sampling exists. Actual frame-window cost still needs console. |
| 23 | Native FlushWork | Garde existante conservée, pas de changement spéculatif : Dispatch mask maintains FIFO, forced flush at 512 draws; no safe order change justified without trace. |
| 24 | Guest PrepareDraw | Garde existante conservée, pas de changement spéculatif : Mirrors native preflight path in guest-bridge source; integration mirror is not evidence of PS5 rendering. |
| 25 | Guest DispatchCompute | Garde existante conservée, pas de changement spéculatif : Mirrors native descriptor preflight/dispatch ordering; preserve explicit indirect buffer validity and barrier semantics. |
| 26 | Guest OnCPUWrite | Garde existante conservée, pas de changement spéculatif : Separate deferred guest-write branch intentionally differs from native; do not blindly copy native path, verify deferred flush on console. |

Le chemin `guest-bridge` est audité séparément du renderer PS5; les temps de cache-pair, de progression worker et de présentation ne peuvent pas être certifiés par simple inspection.
**Porte B3 :** distinguer frame non produite, commande non enregistrée, worker bloqué et image répétée ; corréler temps >50/100 ms, sans sacrifier la cohérence.

### B4 — P0.4 : textures, upload et fraîcheur HUD (12)
Fichiers : `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h` (9) et `vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp` (3).

- [x] 27 `TextureCache::QueueAsyncDecode` — admission bornée, génération/pages courantes et annulation sûre en cas d'erreur.
- [x] 28 `TextureCache::TickAsyncDecode` — récupération des résultats et exceptions, révision courante, file vide sans cooldown inutile.
- [x] 29 `TextureCache::QueueAsyncUnswizzle` — valider budgets 3D, dimensions et compatibilité du passage BCn avant mise en file.
- [x] 30 `TextureCache::TickAsyncUnswizzle` — rétablissement `CpuModified`, handles valides, rollback si refus/exception/remap.
- [x] 31 `TextureCache::RefreshContents` — éviter de publier une texture « propre » avant transfert confirmé, vérifier le fallback synchrone.
- [x] 32 `TextureCache::UploadImageContents` — staging >= taille ET handle Vulkan valide, synchronisation et retry sur échec.
- [x] 33 `TextureCache::TryFindFramebufferImageView` — exclure aliases sales/décodage en cours, prendre seulement une image visible actuelle.
- [x] 34 `TextureCache::SynchronizeAliases` — cohérence alias/remap/CPU-write, sans accès prématuré aux pixels périmés.
- [x] 35 `TextureCache::TickFrame` — GC, readbacks différés, progression des jobs et absence de double travail de frame.
- [x] 36 `TextureCacheRuntime::UploadStagingBuffer` — protéger refus d'allocation/handle nul/mapping court et barrières d'upload.
- [x] 37 `TextureCacheRuntime::TickFrame` — recyclage GPU sûr et coût borné dans la cadence de frame.
- [x] 38 `TextureCacheRuntime::AccelerateImageUpload` — BCn 3D chunk par chunk, état/layout/barrières corrects et rollback complet.

**B4 — 12/12 revues source documentées; comportement console encore non qualifié.**

| N° | Fonction | Décision de revue / limite |
|---:|---|---|
| 27 | `QueueAsyncDecode` | Protection existante conservée : Admission rollback avoids stranded IsDecoding and reclaims incomplete context; new active decode preserved. |
| 28 | `TickAsyncDecode` | Protection existante conservée : Four completed textures per tick, acquire completion, revisions/remap validation, staging/submit/barrier rollback; frame latency still unmeasured. |
| 29 | `QueueAsyncUnswizzle` | Protection existante conservée : Queues before IsDecoding commit, zero-budget/unsupported cases handled at refresh; no unsafe speculative queue change. |
| 30 | `TickAsyncUnswizzle` | Protection existante conservée : Slice-budget partial reads, stale remap cancellation, deferred staging lifetime and CpuModified restoration on failed GPU submission. |
| 31 | `RefreshContents` | Protection existante conservée : Dirty flag protected by scope rollback on failed native synchronous upload, asynchronous handoff separate, complete barrier required. |
| 32 | `UploadImageContents` | Protection existante conservée : Upload called only after native staging handle and mapping-size guards in RefreshContents. Converted/accelerated paths keep ordering; console pixels unproven. |
| 33 | `TryFindFramebufferImageView` | Protection existante conservée : One-pass no-allocation freshest view selection; any decoding, CpuModified or Remapped sibling address triggers raw framebuffer fallback. |
| 34 | `SynchronizeAliases` | Protection existante conservée : Latest modification tick short-circuit and ordered alias copy; actual remap/CPU-write freshness needs in-game proof. |
| 35 | `TextureCache TickFrame` | Protection existante conservée : Memory sampling at most every second frame while below watermark, every frame near GC; completion and GC ticks still under texture lock. |
| 36 | `Runtime UploadStagingBuffer` | Protection existante conservée : Wrapper returns pool staging; native callers check Vulkan handle and span before GPU use. Additional future callsites must preserve guard. |
| 37 | `Runtime TickFrame` | Protection existante conservée : Recycles MSAA/resolve shadows only after scheduler.IsFree tick; no premature GPU release. |
| 38 | `AccelerateImageUpload` | Protection existante conservée : ASTC and BCn-3D paths preserved, missing BCn compute pass raises error on PS5 for caller rollback; unsupported layouts still ASSERT, no new safe change without caller proof. |

Les vérifications de staging citées plus haut imposent **handle Vulkan réel ET taille suffisante** sur les appels PS5 concernés. L'absence de preuve sur des futurs callsites ou sur le HUD réel interdit de déclarer ce sous-système « totalement optimisé ».

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
| B3 — rasterizer/guest | **9/9 décisions source; mesures console ouvertes** | Preflight, pair-lock, writes guest, frame, FIFO audités ; miroir distinct | Traces >50/>100 ms, progression guest et captures HUD |
| B4 — textures/HUD | **12/12 décisions source; CI/console ouvertes** | Async rollback, staging nul/court, aliases, GC, BCn et recycler inspectés | Gate commun, puis HUD/mi-temps/bandeau noir sur console |
| B5 — gates groupés + console | **38/38 revues closes ; CI et console ouvertes** | Fast gate, prévalidation et CodeQL sur `63261b8` ; build natif lancé sur `9c16d89` (mêmes sources moteur, oracle hôte ultérieurement réparé) | Attendre verdicts ; résoudre uniquement un échec prouvé, puis retenir un SHA de build/gates qualifié avant essai console |

**Reprise programmée :** tâche horaire « Eden Encore — reprise F07 » ; ses actions doivent être revérifiées via le HEAD, les commits et le journal de lots. Elle doit cesser lorsque les critères de clôture sont satisfaits et aucune modification ne doit être inventée si aucun outil n'est accessible.

**Commande de reprise utilisateur :** « continue Eden Encore d'après `docs/F07_BATCH_EXECUTION_REGISTER.md` ». En début de reprise, contrôler le HEAD réel, pas uniquement le SHA imprimé ici. Ne pas multiplier les branches/PR ni inventer de résultat CI.

## F07 checkpoint — 2026-10-28

- Source decision count: B1 7/7; B2 10/10; B3 9/9; B4 12/12 = 38/38 SOURCE DECISIONS; not a final acceptance of CI or PS5. These remaining 31 are audit decisions, not 31 proven defects.
- Business code commit: `407ad36ef5207d4fef964074241cb197fb153248`. Fork generator and selected Vulkan source were changed together, with host witness updated.
- CI checks not yet proven green on `407ad36`; no console FPS or HUD freshness proof. No PR or secondary branch created.
- Next: B2 08–17 source review, targeted regressions, then B3/B4, followed by one coherent four-gate/console campaign.

- B2 n°08–17: 10 source decisions recorded from the three selected Vulkan modules. No performance gain or successful PS5 build has been inferred.

## Consolidation 38 fonctions — 2026-10-28

**38/38 décisions de revue source consignées.** La fermeture des 38 revues ne signifie ni 38 patchs, ni 38 gains de performances, ni 38 validations CI ou console. Le code nouveau et concret de ce passage est la synchronisation du compteur de préchargement shader sur `407ad36`; les autres protections inventoriées préexistaient et sont maintenues. La prochaine étape est B5 : comparer la source générée, compiler les témoins hôte et effectuer les quatre gates sur le **même SHA métier**, puis lancer une seule campagne console FC 27/BOTW. Le défaut P0 de traduction froide synchrone et les blocages HUD/pause restent ouverts tant que les mesures ne les ferment pas. Sans ces preuves, ne pas présenter F07 comme terminé.

## B5 — remise en marche des validations et build complet

- L'exécution fast gate `40783674481` sur le correctif métier `407ad36` a échoué dans le témoin `tools/check-vulkan-deferred-copy-ownership-host.py` : la portion réelle `RecordWithUploadBuffer` appelle désormais `InvalidateState`, absent de la classe minimale du harnais. Il s'agissait d'une erreur de compilation du **témoin**, non d'un défaut PS5 observé.
- Correctif `3384977ae8c0a296ea5a755d29fcba369962a217` : le harnais expose la méthode d'invalidation et vérifie aussi le double refus `CommandChunk::Record`, son signalement et une commande valide après récupération. Fast gate `40784547280`, prévalidation `40784547410` et sécurité : laisser la CI déterminer leurs résultats ; ne jamais les présumer verts.
- Ce checkpoint [full-build] déclenche une **compilation native authentique** du même arbre moteur après ce correctif de test, sans nouvelle divergence des sources ou du générateur Vulkan. Le paquet reste non qualifié tant que la CI et un essai FC 27/BOTW sur console ne l'ont pas confirmé.

- Suivi du fast gate : après le premier témoin réparé (sortie `DEFERRED_COPY_OWNERSHIP_PASS`), un **second** harnais historique `check-vulkan-present-draw-storage-host.py` échouait pour la même méthode `InvalidateState` absente de son Scheduler minimal. Correctif `26b09c8c93266624ffb7877991ff3ad2737550f3` : fonction simulée + assertion qu'aucune invalidation n'a lieu sur les 15 cas de présentations enregistrées. La compilation PS5 est relancée sur ce contenu de tests [full-build] plutôt que de poursuivre un candidat dont un témoin est déjà connu cassé.

## Reprise B5 sans relance inutile — 29 octobre 2026

**Source moteur inchangée depuis `407ad36` :** les commits de réparation de harnais `3384977`, `26b09c8`, `63261b8` ne modifient ni le moteur PS5, ni le générateur du fork Vulkan. Les échecs de tests qui les ont motivés ne prouvent pas des régressions du binaire GPU.

**Runs à lire avant tout nouveau patch :** fast gate [40785959436](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40785959436), source preflight [40785959512](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40785959512), CodeQL [40785959464](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40785959464) sur `63261b8`; build PS5 [40785052216](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40785052216) lancé sur `9c16d89` (avant dernière réparation de témoin, moteur identique). Aucun de ces runs n'était clos globalement au moment de cette note. Ne pas pousser de nouveaux correctifs GPU juste pour provoquer une nouvelle CI, ni relancer inutilement un build natif en cours.

**Décision immédiate :** si un gate échoue, lire la première vraie erreur et réparer la cause dans le plus petit lot cohérent (source + générateur + témoin lorsqu'il s'agit de Vulkan). Sinon conserver le candidat et le qualifier sur console, avec comparaison mesurée de FC27 froid/chaud, 1440p 1×, HUD, pause/mi-temps, et contrôle BOTW. La date/sha du paquet réellement testé doit être attachée aux résultats. La réussite CI ne démontre pas les 30 FPS stables.

## B5 — native texture copy closeout candidate (29 Oct 2026)

- Correctif source **`1455d0b`** : `TextureCacheRuntime::CopyImage` ne rend plus immédiatement son ancien MSAA resolve périmé lorsqu'il délègue une conversion de formats incompatibles à `ReinterpretImage`. Le délégué valide les tailles, le handle Vulkan du staging temporaire et invalide uniquement si la copie peut être soumise. Cette correction préserve les pixels précédemment valides lors d'une allocation refusée, sans faux gain FPS annoncé.
- Optimisation **`1c4ce8d`** : `CopyImage` ignore sur PS5 les appels avec zéro région et formats de même taille (ni invalidation de resolve ni commande Vulkan vide). Pour les formats incompatibles, le chemin qui matérialise une copie intégrale reste exécuté même si le tableau initial de régions est vide. Desktop inchangé.
- `tools/prepare-vulkan-port.py` et le témoin `tools/check-ps5-f07-reinterpret-image-budget-host.py` sont synchronisés avec la source native. Le témoin extrait réellement le garde de `CopyImage`, compile PS5 et desktop, teste refus null staging / conversion valide et refus no-op, en `-O0` et `-O2`. Attendre verdict CI, ne pas présumer la validité hôte, Vulkan ou matérielle.
- **Nouvelle candidate PS5** : reconstruire une fois l'arbre moteur contenant `1c4ce8d` pendant que CI exécute ses contrôles, puis vérifier les artefacts et effectuer la comparaison console sur le candidat effectivement qualifié. Le paquet antérieur `9c16d89` a compilé avec succès mais **ne contient pas** ce correctif.
