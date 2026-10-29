# F07 — checklist des optimisations restantes et critères de clôture

**Créé : 29 octobre 2026 (Europe/Paris)** · **Branche unique : `dev/ps5-sparse-jit`** · **Référence à la création : `52e3334fe9e1f058cf50d0764af76ccdb197758d`** · **Statut global : OUVERT**.

**But :** chaque optimisation restante *identifiée* doit disposer d'une case vérifiable et d'un résultat explicite. Ce document est le **tableau d'exécution** ; le [registre des 38 revues F07](F07_BATCH_EXECUTION_REGISTER.md), le [suivi maître](FC27_F07_MASTER_TRACKER.md) et les [critères de sortie FC27](FC27_EXIT_GATES_2026-10-22.md) sont les preuves de référence. Ne pas transformer « absence de défaut démontré » en « toutes les optimisations imaginables terminées ».

## Convention de suivi, impérative

- `[x]` = action décrite **effectuée avec preuve** (SHA, test, CI ou console selon la nature de la case). `[ ]` = **ouverte/non prouvée**. `SANS PATCH JUSTIFIÉ` peut **fermer une revue**, mais **ne ferme pas** l'objectif de performance console.
- Une optimisation suit les états `À MESURER → COÛT/BUG PROUVÉ ou SANS PATCH JUSTIFIÉ → PATCH + TEST HÔTE ou REJET MOTIVÉ → CI QUALIFIÉE → CONSOLE QUALIFIÉE`. N'ajouter une modification que si le propriétaire **compilé en production** et le coût évitable sont démontrés.
- **Deux vagues :** `PRÉ-BUILD` = revue, correctif éventuel et tests hôte avant le paquet final. `POST-BUILD` = **preuve console impossible avant compilation**, non exigible pour autoriser le premier build. Le premier build n'est autorisé qu'après toutes les décisions PRÉ-BUILD sûres et leurs gates ; les problèmes révélés ensuite rouvrent leur propriétaire, sans annoncer « terminé ».
- **Pour chaque case cochée :** ajouter immédiatement sous le lot une preuve concise `date / SHA / fichier::fonction / témoin+résultat / décision / risque restant`. Pas de « fait » sur une CI en cours, annulée ou *skipped*. Ne compter **ni tests hôte, ni shaders recompilés, ni fichiers relus** comme gains FPS sur PS5.
- **Pas de nouvelle branche, pas de PR, pas de build final anticipé.** Les pushes ordinaires peuvent déclencher automatiquement les gates hôte ; ce n'est pas l'autorisation de compiler un paquet PS5. Les changements de la branche *spec/fonctionnalités* restent hors scope.
- **Reprise :** lire le HEAD, les gates en cours, ce fichier ; travailler de haut en bas uniquement sur une anomalie ou opportunité démontrée. Ne pas rouvrir en boucle les 38 revues déjà closes. Si une autre optimisation réelle apparaît, ajouter une case **ID stable** sous sa catégorie, sa justification et son test avant de la modifier.
- **Limite d'inventaire :** les 38 fonctions B1–B4 ont une décision source ; la première passe de couverture moteur/launcher est un **audit de sources**, pas une preuve d'optimalité. Il n'existe pas de nombre démontrable de « toutes les optimisations possibles ». Le nombre de cases ouvertes ici décrit les **chantiers connus**, pas le nombre garanti de patchs nécessaires.

## 0. Acquis — ne pas refaire

- [x] **A-01** — B1 shader/cache : **7/7** décisions *revue source* consignées (pas console).
- [x] **A-02** — B2 pipeline/descripteurs : **10/10** décisions *revue source* consignées (pas console).
- [x] **A-03** — B3 rasterizer/guest : **9/9** décisions *revue source* consignées (pas console).
- [x] **A-04** — B4 textures/HUD : **12/12** décisions *revue source* consignées (pas console).
- [x] **A-05** — JIT sparse natif unique, commit physique à la demande 2 Mio et trim complet sous quiescence **intégrés en source / témoins hôte historiques**, pas prouvés sur PS5.
- [x] **A-06** — F01–F06 : **6/6 contrats pré-console hôte** ; aucune implication de six corrections de gameplay validées.
- [x] **A-07** — Première passe de revue moteur et lanceur documentée, y compris l'[audit lanceur release](EDEN_RELEASE_LAUNCHER_SOURCE_OPTIMIZATION_AUDIT_2026-10-26.md) ; pas de relecture générale sans nouvelle preuve.
- [x] **A-08** — Protections de staging : taille **et handle Vulkan non nul**, refus/rattrapages, témoin source-extrait ; aucune garantie de pixels HUD sans console.
- [x] **A-09** — Copies/uploads nuls, traitement BCn/MSAA et gardes de publication/récupération intégrés dans les sources actives ; verdict CI du HEAD courant **non** affirmé.

**Sources actives :** `vendor/encore-active/eden-vulkan/`, `vendor/encore-active/eden-core/`, `headless/`, `src/` ; les fichiers `guest-bridge` et DEV non livrés ne valent jamais preuve PS5.

## 1. P0.1 — shaders froids, IR/SPIR-V et cache persistant

- [ ] **S01 [PRÉ-BUILD]** — Séparer les coûts froids réels.** Attribuer `shader_cfg`, `shader_ir`, `shader_spirv`, `shader_module`, `graphics_pipeline_create` et compute à un **miss** précis plutôt qu'aux seuls intervalles de présentation. **Owner :** `vk_pipeline_cache_cost.cpp::CreateGraphicsPipeline/CreateComputePipeline`. **Sortie :** attribution reproductible, pas d'écriture/log par draw en mode silencieux.
- [ ] **S02 [PRÉ-BUILD]** — Éliminer uniquement le coût de traduction évitable prouvé.** Examiner les mêmes shaders/keys réutilisés, invalidations et allocations récurrentes ; si aucun déplacement hors GPU-owner n'est thread-safe, documenter `SANS PATCH JUSTIFIÉ`. **Sortie :** hit/miss conservé, shader final identique, témoin O0/O2 et absence de race.
- [ ] **S03 [PRÉ-BUILD]** — Qualifier le préchauffage persistant borné à 8.** Vérifier cache valide/miss/rejet, réouverture froid/chaud, survie du pool worker, arrêt et fermeture ; ne pas monter arbitrairement le quota. **Owner :** `LoadDiskResources`, `QueueVulkanPipelineCacheFlush`. **Sortie :** comparaison lancement/compilation et preuve de réutilisation.
- [ ] **S04 [PRÉ-BUILD]** — Revalider priorités first-use vs optimiseur.** Constater l'absence de famine, de jobs spéculatifs en priorité et de retry storm après échec. **Owner :** `Current*Pipeline* / QueueOptimizedPipeline`. **Sortie :** commandes réelles préservées, quotas bornés, hôte puis console.
- [ ] **S05 [POST-BUILD]** — Mesurer le résultat shader sur FC27 froid/chaud.** Le passage de compilation à un FPS régulier est **non prouvé**. **Sortie :** retards >50/>100 ms et temps shader comparables sur même build/scènes.

## 2. P0.2 — attente worker Vulkan / scheduler / descripteurs

- [ ] **V01 [PRÉ-BUILD]** — Isoler attente worker pipeline vs CPU shader.** Tracer publication release/acquire, attente commandée et temps réel de complétion. **Owner :** `vk_graphics_pipeline_cost.cpp::ConfigureDraw`, `vk_compute_pipeline_cost.cpp::Configure`, scheduler. **Sortie :** coût d'attente correctement attribué à une frame, sans désordre FIFO.
- [ ] **V02 [PRÉ-BUILD]** — Examiner les attente(s) supplémentaires démontrées sur les commandes acceptées.** Conserver la *seule attente ordonnée* intégrée ; aucun pipeline non construit exécuté, aucun `Record` refusé compté soumis. **Sortie :** O0/O2, refus puis reprise, hôte+console.
- [ ] **V03 [PRÉ-BUILD]** — Quantifier les `Finish` / `Wait` de repli sous pair-lock.** **Owner :** `vk_descriptor_buffer_cost.cpp::PreflightFrameReuse/PreflightCapacity/Allocate`. Déplacer un wait uniquement si la réservation hors verrous est certaine. **Sortie :** tick/génération/identité descripteur préservés.
- [ ] **V04 [PRÉ-BUILD]** — Requalifier la réutilisation des descripteurs graphiques/compute.** **Owner :** `GraphicsPipeline::ConfigureImpl/ConfigureDraw`, `ComputePipeline::Configure`. **Sortie :** payload, génération, lifetime et invalidation corrects après changement de HUD et échec de soumission.
- [ ] **V05 [PRÉ-BUILD]** — Vérifier les frontières scheduler/submit/barrières de copies.** **Owner :** `vulkan_scheduler.cpp`, `vk_texture_cache_cost.cpp`. **Sortie :** aucune suppression de barrière buffer/image utile ; témoin refus, rollover, copies successives et rebind.
- [ ] **V06 [POST-BUILD]** — Qualifier les blocages worker en jeu.** Comparer les attentes de pipeline à la progression réelle des commandes, images et invités ; ne pas conclure d'un simple callback à 30 Hz.

## 3. P0.3 — mutex buffer/texture, GPU progress, présentation

- [ ] **C01 [PRÉ-BUILD]** — Attribuer les verrous aux *détenteurs* (pas seulement aux demandeurs).** **Owner :** `vulkan_rasterizer.cpp::PrepareDraw/DispatchCompute/OnCPUWrite`. **Sortie :** durée et phase sous `buffer_cache.mutex` et `texture_cache.mutex` autour des fenêtres >50/>100 ms.
- [ ] **C02 [PRÉ-BUILD]** — Vérifier les preflights et fast paths sur séquences HUD.** **Owner :** `GraphicsPipeline::ConfigureImpl`, `TextureCache::RefreshContents`. **Sortie :** cache-hit sans acquisition/allocation superflue, tout état dirty et fallback correct.
- [ ] **C03 [PRÉ-BUILD]** — Mesurer les traitements par frame hors logique de jeu.** **Owner :** `RasterizerVulkan::TickFrame`, `TextureCacheRuntime::TickFrame`, `headless/graphics.cpp::OnFrameDisplayed`. **Sortie :** balayage/GC et histogrammes silencieux à coût borné, compteurs diagnostiques honnêtes.
- [ ] **C04 [PRÉ-BUILD]** — Vérifier la sélection de frames réelles.** **Owner :** `RasterizerVulkan::AccelerateDisplay`, `vulkan_present_manager.cpp`. **Sortie :** nouvel identifiant/contenu présenté, distinction attente worker / image répétée / frame guest absente.
- [ ] **C05 [PRÉ-BUILD]** — Corréler cache, JIT, GPU et HLE par fenêtre sans extrapolation causale.** **Sortie :** phases synchronisées et preuve directe d'un coût évitable avant nouveau patch.
- [ ] **C06 [POST-BUILD]** — Qualifier le gain sur console.** FPS moyen seul insuffisant ; retards, rafales, pire frame et blocage réel doivent reculer sans régression graphique ni perte de commandes.

## 4. P0.4 — HUD, texture, DMA, freshness

- [ ] **T01 [PRÉ-BUILD]** — Tracer l'intégralité DMA → write/alias → TIC/TSC → descriptors → draw → present.** **Owner :** `TextureCache::VisitImageView/FillImageViews/CheckFeedbackLoop`, `PushImageDescriptors`, rasterizer. **Sortie :** révision de pixel et génération associées à chaque transition de HUD.
- [ ] **T02 [PRÉ-BUILD]** — Vérifier le refus global des aliases sales/remappés/en décodage.** **Owner :** `TryFindFramebufferImageView`, `SynchronizeAliases`. **Sortie :** fallback vers pixels invités, absence de vue propre ancienne publiée sous alias concurrent.
- [ ] **T03 [PRÉ-BUILD]** — Valider l'ensemble des échecs d'upload après staging et soumission.** **Owner :** `RefreshContents/UploadImageContents`, `TickAsyncDecode/TickAsyncUnswizzle`, runtime staging. **Sortie :** handle Vulkan, taille, barrière, `CpuModified`, retry et jamais de `IsDecoding` bloqué.
- [ ] **T04 [PRÉ-BUILD]** — Valider cycle de vie MSAA/resolve et recyclage GPU.** **Owner :** `TextureCacheRuntime::AcquireMsaaScratchImage/TickFrame/CopyImage`. **Sortie :** aucun resolve recyclé avant completion tick, aucune invalidation prématurée si refus.
- [ ] **T05 [PRÉ-BUILD]** — Distinguer font/shader initial, descripteur nul, bandeau noir et affichage périmé.** **Sortie :** témoin reproductible par type de HUD (score/noms/popups/mi-temps), non simple hypothèse « shader texte ».
- [ ] **T06 [POST-BUILD]** — Confirmer textures/maillots/pelouse et HUD en FC27.** **Sortie :** pixels et révisions visibles réellement mis à jour sur PS5, sans bandeau noir persistant ni nouveau défaut.
- [ ] **T07 [PRÉ-BUILD]** — Maintenir les tests DMA F04 et copies format/BCn/MSAA après chaque changement natif.** **Sortie :** données source intactes, ordre barriers correct et absence de drop silencieux.

## 5. P1 — JIT A32/A64, progression invitée, IPC et commandes

- [ ] **J01 [PRÉ-BUILD]** — Attribuer compilation, évacuation et invalidation JIT dans les gros gaps.** **Owner :** Dynarmic A32/A64 natif, `block_of_code_native.cpp`, `headless/jit-allocator.h`. **Sortie :** coûts *par cœur* vs intervalle mur, sans addition abusive des workers.
- [ ] **J02 [POST-BUILD]** — Qualifier alias RX/RW natif, engagement 2 Mio, trim quiescent et recommit.** **Sortie :** preuve firmware 13.60, droits W^X, durée de vie des blocs, relance après titre fermé.
- [ ] **J03 [POST-BUILD]** — Auditer la vraie contention JIT/guest/GPU et la pression mémoire.** Pas de cache plus gros ni répartition CPU forcée sans mesure et budget sûr. **Sortie :** scénario saturé et absence de régression sous mémoire faible.
- [ ] **H01 [POST-BUILD]** — Isoler la progression invité durant pause/mi-temps/freezes.** **Owner :** KThread/condition vars/HIPC/NvDisp/Host1x/BufferQueue, F05. **Sortie :** preuve de nouvel état jeu et de consommations de buffers, pas seulement de frames présentées.
- [ ] **H02 [PRÉ-BUILD]** — Vérifier refus, réveils et reprises IPC/HLE.** **Sortie :** publication des waiters, fin de wait, timeout, fermeture et reprise exacts ; pas de réveils ou copies en double.
- [ ] **I01 [POST-BUILD]** — Mesurer manette → NPad → action guest → image visible.** **Owner :** F06 et mapping normal. **Sortie :** commandes PS toujours correctes en match/pause, pas de remapping Switch imprévu.
- [ ] **I02 [POST-BUILD]** — Déterminer si la latence de pause provient d'input, IPC, guest ou rendu.** **Sortie :** correctif ciblé seulement dans le propriétaire causal ; test de reprise, mi-temps et fin de partie.
- [ ] **G01 [PRÉ-BUILD]** — Valider F01–F06 ensemble sans changer leur contrat.** **Sortie :** 6/6 replays hôte toujours verts puis preuve matérielle de progression entrée et sortie.
- [ ] **G02 [POST-BUILD]** — Qualifier F01–F06 sur console : entrée, reprise, composition et sortie, sans confondre la preuve hôte et le jeu réel.

## 6. P2 — mémoire partagée, GC, modes extrêmes, bruit de production

- [ ] **M01 [POST-BUILD]** — Mesurer VRAM/VMA/direct-mem/JIT et fragmentation, séparément à 1× et 4×.** **Sortie :** mémoire restante/plus gros bloc, échec de réservation identifié, *pas* « 4× OOM explique 1× stutter ».
- [ ] **M02 [PRÉ-BUILD]** — Examiner coût du GC et des téléchargements synchrones sous pression.** **Owner :** `TextureCache::TickFrame`, runtime GC, `vulkan_rasterizer.cpp`. **Sortie :** éviction après completion, données dirty récupérables, pas de `Finish` gratuit.
- [ ] **M03 [PRÉ-BUILD]** — Arbitrage JIT ↔ GPU ↔ guest sous pression uniquement si sûreté démontrée.** **Sortie :** mécanisme borné/fallback testé ; sinon revue close `SANS PATCH JUSTIFIÉ` et dette explicite.
- [ ] **Q01 [PRÉ-BUILD]** — S'assurer que RELEASE silencieux ne formate/loggue/flush pas par frame.** **Owner :** `headless/graphics.cpp`, native logpipe, GPU/JIT timers ; **sortie :** coût observé, diagnostics activables sans falsifier le mode silencieux.
- [ ] **Q02 [POST-BUILD]** — Requalifier la topologie CPU et le placement des workers.** **Sortie :** utiliser seulement les affinités/coeurs réellement disponibles, A/B et pas d'hypothèse SMT.
- [ ] **Q03 [PRÉ-BUILD]** — Contrôler le lanceur sans réouvrir son audit global.** Startup/médias UI OpenGL hors gameplay ; revue ciblée uniquement si anomalie de latence/consommation avérée dans le build unique.

- [ ] **M04 [PRÉ-BUILD] — Sondes de pression pendant l'éviction texture.** **Owner :** `TextureCache::RunGarbageCollector::Cleanup`. **Source modifiée :** `3213cda88a0f758e61f9fa6164423933bfcd7c62` ; limite à huit visites sales par sonde sous mutex, réinitialise après éviction/passe critique, bypass immédiat au seuil critique. Mini-harnais C++ isolé O0/O2 + UBSan passé localement ; **témoin source-extrait et gates GitHub encore non qualifiés**, console non mesurée. Décider la clôture seulement après verdict hôte et preuve d'absence de régression GC.\n\n## 7. B5 — campagne de validation groupée (DERNIÈRE étape)

> **Verrou : ne pas cocher le build ni demander un test console tant que les optimisations sûres identifiées, leurs témoins et le gel des modifications moteur ne sont pas achevés.** On ne poursuit pas une optimisation infinie et spéculative pour prétendre à « zéro possible ». Une revue peut être close sans patch, avec preuve.

- [ ] **B01 — Inventaire de fermeture pré-build.** Toutes les cases marquées `PRÉ-BUILD` ci-dessus ont une décision prouvée (patch + test ou absence de patch justifiée), **pas** les cases `POST-BUILD` qui exigent la console ; les améliorations identifiées avant build sont intégrées et aucune anomalie de validation hôte ne reste ouverte.
- [ ] **B02 — Reproduire source native / générateur fork / dépendances / guest-bridge.** `tools/prepare-vulkan-port.py` donne les octets sélectionnés attendus ; pas de divergence de source active.
- [ ] **B03 — Hôte : tous les témoins ciblés, desktop/PS5, `-O0/-O2`, ASan/UBSan pertinents.** Aucune panne de test « historique » éludée.
- [ ] **B04 — Fast gate sur SHA stabilisé.** Run + verdict `success` :
- [ ] **B05 — Source preflight sur le même SHA.** Run + verdict `success` :
- [ ] **B06 — CodeQL sécurité sur le même SHA.** Run + verdict `success` :
- [ ] **B07 — Autoriser et effectuer alors une seule compilation native/package PS5, même SHA.** Run `success`, artefacts/empreintes et `PPSA99008` vérifiés. **Pas avant B01–B06.**
- [ ] **B08 — Console PS5 13.60 : FC27 1440p / 1× / logging OFF / même scène, caches froid puis chaud.** Consigner date, SHA et paramètres ; compter `late38/50/100/200/500`, pire frame, rafales, contenu HUD.
- [ ] **B09 — Scénarios gameplay réels.** Pause/mi-temps/HUD texte/maillots/pelouse, manette, progression CPU guest, sortie propre et relancement ; zéro gel durable.
- [ ] **B10 — Régression BOTW et stress mémoire.** Jouabilité, textures, performances et libération JIT/VRAM contrôlées.
- [ ] **B11 — Résultat final tracé.** Comparaison avant/après de **mêmes conditions**, risques restants/absence d'amélioration consignés ; si anomalie avérée, rouvrir uniquement son ID causal et retourner à B01 (ne pas recompter les 38 audits).

### Baseline de référence matérielle (pas un résultat du HEAD actuel)

`cd4857c8`, FC27 1440p/1× le 25 octobre : **204 fenêtres de 5 s**, FPS médian par fenêtre **29,56**, FPS minimum **14,48**, **142** intervalles >100 ms, pire intervalle **689,834 ms**. Sessions non A/B contrôlées ; HUD noir/retardé et réponse pause encore observés. Une amélioration n'est déclarée qu'après mesures de même configuration ; une moyenne proche de 30 FPS n'est pas suffisante.

### CI observée au moment de la création (ne pas rétro-cocher)

- HEAD `52e3334` : fast gate [40810682530](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40810682530), source preflight [40810682534](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40810682534), sécurité [40810682584](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40810682584) **en cours lors de la lecture**. Les workflows native build de ce HEAD sont `skipped`.
- Ancien fast gate `3b125ca` / [40810019386](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40810019386) : erreur de compilation dans le **témoin** MSAA (`int` → `u64` narrowing), corrigée dans `52e3334` ; cela **ne prouve pas encore le succès final**.
- Règle : après chaque nouveau HEAD, relire les runs plutôt que conserver des états de CI périmés dans les cases.

### Journal d'exécution (ajouter les preuves, ne pas écraser les anciennes)

| Date | HEAD | ID | Décision et preuve | Prochaine case / blocage |
| --- | --- | --- | --- | --- |
| 2026-10-29 | `52e3334` | CHECKLIST | Création du registre des chantiers connus ; aucun patch moteur, aucune compilation finale | Vérifier les gates existants ; puis S01/V01/C01/T01 selon la première preuve de coût |
| 2026-10-29 | `398fb5b` | B03 / T04 | Fast gate précédent [40810682530](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40810682530) : le témoin MSAA échouait **à l'exécution** car il attendait la libération de scratch après un seul tick libre. Correctif du **témoin uniquement** : vérifier la rétention à 1 puis 60 frames libres et l'éviction à la 61e ; ordre, source native et générateur inchangés. CI du nouveau SHA [40811858092](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40811858092) démarrée ; pas encore un PASS. | Lire le résultat du fast gate, puis preflight ; pas de build |
| 2026-10-29 | `9f2db8e` | T04 / C03 | Optimisation source MSAA : le sémaphore GPU est sondé une fois **seulement si** une clé scratch correspond. `vk_texture_cache_cost.cpp` + générateur strict + témoin source-extrait native/desktop, O0/O2. **CI et console non qualifiées**. | Fast gate [40812495433](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40812495433), remplacé par les lots suivants |
| 2026-10-29 | `3ee7b0c` | M02 / C03 | En PS5 natif, le budget mémoire du cache buffer n'interroge le driver qu'une frame sur deux **sous 2/3 du seuil GC** ; fréquence entière près du seuil. Test source-extrait et oracle R437 adaptés, desktop inchangé. **CI et console non qualifiées**. | Gate [40813024438](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813024438), remplacé par la source suivante |
| 2026-10-29 | `c5af10f` | C02 / M02 | Remplacement des deux décalages historiques uniform-cache `std::copy_n` sur plages chevauchantes par `std::copy_backward`. Préserve les compteurs par frame et l'heuristique de cache, sans UB de copie. Test source-extrait O0/O2 + oracle R437 synchronisés. **CI non qualifiée**. | [Fast #40813207369](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813207369), [prévalidation #40813207393](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813207393), [CodeQL #40813207378](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813207378) ; aucun build |
| 2026-10-29 | `bc28eea` | M02 / C03 | Correctif de GC buffers PS5 : lorsque `frame_tick < ticks_to_destroy`, empêcher le passage d'un seuil LRU `u64` sous-débordé à `ForEachItemBelow`. Tests source-extraits pour premières 60/120 frames, desktop conservé, oracle R437 synchronisé. **Non qualifié CI/console à ce stade.** | [Fast #40813636762](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813636762), [preflight #40813636657](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813636657), [CodeQL #40813636656](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813636656), sans build |
| 2026-10-29 | `6334a41` | M02 / C03 | Clamp natif du compteur mémoire GPU lors de `BufferCache::ChangeRegister<false>` : un snapshot driver inférieur à la taille du buffer ne peut plus produire `u64::max` et provoquer un GC sous pression fictive. Oracle R437 et test source-extrait `-O0/-O2` PS5/desktop ; mini-test C++ local réussi. **CI complète encore ouverte.** | [Fast #40813997301](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813997301), [prévalidation #40813997315](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813997315), [CodeQL #40813997345](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40813997345), paquet non construit |
| 2026-10-29 | `6109c1e` | B02 / M02 | Réparation de la synchronisation générateur : transformation GC natif déplacée après l'ancien traitement « entrées propres », sans nouvelle modification moteur. Fast gate [40815176131](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40815176131) : étapes **Pinned Vulkan source reproduction** et **Active native source ownership and graph parity** réussies ; étapes suivantes en cours. | Prévalidation [40815176144](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40815176144), sécurité [40815176137](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40815176137), aucun build |
| 2026-10-29 | `3213cda` | M02 / C03 | GC texture PS5 : borne à huit candidats sales les sondages répétés de pression mémoire directe sous mutex, remet le budget à zéro après une éviction et sur passe critique. Témoin source-extrait O0/O2 ; fast gate du SHA [40814938616](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40814938616) échoué sur **ordre générateur**, non sur le moteur. | Suite corrective `6109c1e` ; qualification finale encore ouverte |
| 2026-10-29 | `6109c1e` | B04 (intermédiaire) | Fast gate [40815176131](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40815176131) terminé **success**, y compris génération fork, témoins GPU/HLE et contrôles host ; source depuis modifiée, **B04 final non coché**. | Requalifier sur HEAD moteur final, préflight/CodeQL toujours en cours |
| 2026-10-29 | `953e7f4` | M02 / G01 | `BufferCache::TickFrame` native conserve la progression et le nettoyage des buffers/staging différés lorsque `channel_state == nullptr` (fermeture dernier canal, homebrew) ; desktop retourne comme avant. Oracle R437, témoin natif/desktop `-O0/-O2` ajoutés, **CI non encore qualifiée**. | [Fast #40816234259](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40816234259), [preflight #40816234465](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40816234465), [CodeQL #40816234498](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40816234498) |
