# Eden Encore — suivi maître F07 et exploitation PS5

**Date de référence :** 26 octobre 2026. **Branche :** `dev/ps5-sparse-jit`.
**Source relue :** `3ca07a442d1fd85aa0cc5de08eb02099c46f2bac` (avant création de ce suivi).
**Priorité produit :** fluidité réelle de FC 27, HUD/maillots/textures corrects, commandes réactives et absence de gel. **F07 ouvert.**

> Ce fichier est le point d'entrée des priorités. Les documents d'audit référencés plus bas contiennent le détail technique. Aucun test hôte ni build PS5 ne permet, seul, de conclure à un correctif visible en jeu. Les mesures console restent privées.

## États et règle de preuve

- **INTÉGRÉ (SOURCE)** : le chemin sélectionné est présent dans la branche ; pas de certification de son exécution sur PS5.
- **HÔTE** : test reproductible C++/Python/source sur le périmètre annoncé (souvent O0/O2 ou GPU simulé).
- **CI/BIN** : prévalidation complète, fast gate et vrai paquet PS5 réussis **sur le même SHA**, non « skipped ».
- **CONSOLE** : firmware 13.60, jeu, scène, paramètres et résultats réels comparables ; exigé pour déclarer jouabilité et gain de FPS.
- **OUVERT** : défaut observé non levé ou explication causale non démontrée, même lorsqu'un correctif partiel est intégré.

### Priorités fonctionnelles (ordre de traitement)

| Priorité | Sous-système et sources actives | État établi au 26/10 | Travail vérifiable pour fermer |
| --- | --- | --- | --- |
| **P0.1** | Première utilisation des shaders — `vk_pipeline_cache_cost.cpp::CurrentGraphicsPipelineSlowPath / CreateGraphicsPipeline` | **OUVERT**. Construction Vulkan parallèle et préchauffage borné à 8 entrées présents ; traduction guest IR → SPIR-V encore **synchrone au premier cache miss**. Tests hôte sur préchauffage/persistance, pas de réduction mesurée des à-coups PS5. | Isoler coût CPU de traduction vs création Vulkan sans écrire à chaque draw ; reproduire un problème exact, corriger sans shader invalide ni ordre de draw cassé. |
| **P0.2** | Attente des pipelines — `vk_graphics_pipeline_cost.cpp::ConfigureDraw`, scheduler/worker Vulkan | **OUVERT**. Chemin ready avec acquire et court-circuit ; une compilation non terminée pose toujours une **attente ordonnée** dans le worker. Correctifs de publication et callbacks testés sur hôte. | Mesurer l'attente réelle par fenêtre de frame et séparer compilations froides/attentes ; conserver les dépendances et fences, ne jamais réutiliser un pipeline non prêt. |
| **P0.3** | Contention caches buffer/texture — `vulkan_rasterizer.cpp::PrepareDraw/OnCPUWrite`, `vk_graphics_pipeline_cost.cpp`, `vk_texture_cache_cost.cpp` | **OUVERT**. Preflight, réutilisation sampler et exclusions de chemins chauds déjà intégrés. Les journaux montrent des attentes corrélées en partie aux retards, mais pas la causalité complète. | Identifier propriétaire et durée **sous verrou**, phase upload/désentrelacement, soumissions et attente GPU ; test régression avant toute réduction de verrou. |
| **P0.4** | Fraîcheur HUD, textures et transition blit → pipeline → present | **OUVERT**. Fix `DrawTexture` → `Scheduler::InvalidateState`, reprise TIC/TSC, barrières et tests hôte présents. Les bandeaux noirs / textes retardés restent observés sur console dans la version testée du 25/10. | Prouver que la **révision d'image/pixels** change bien jusqu'à la présentation, distinguer absence de draw, mauvais descripteur et ancienne image présentée ; confirmer sur PS5. |
| **P1.1** | JIT A32/A64, compilation/invalidation, progression guest | **PARTIEL / NON QUALIFIÉ CONSOLE**. Un seul sparse JIT natif est sélectionné, voir le tableau dédié. Les pauses longues et la progression CPU invité pendant les à-coups ne sont pas attribuées. | Mesurer compile/invalidation/états de threads et relier à l'image produite, tester cycle lancement → invalidation totale → recompilation → retour bibliothèque. |
| **P1.2** | HLE/NvDisp/Host1x/BufferQueue → renderer → présentation, manette → NPad | **HÔTE 6/6 F01–F06, CONSOLE OUVERTE**. Chaînes F05/F06 testées avec adaptateurs/WSI simulés ; 30 callbacks/s ne prouvent pas un match qui avance. | Distinguer jeu bloqué, guest éveillé sans progrès, nouveau rendu non présenté, HUD stale et commande retardée. |
| **P2.1** | VRAM, GC, mémoire directe, 4× OOM | **PARTIEL**. Budgets/limites prudents, observabilité de l'OOM, pas d'arbitrage dynamique JIT↔GPU↔guest intégral prouvé. | Gérer le 4× séparément du 1× ; suivre direct-mem libre/plus grand bloc, allocations VMA, scans et relance, sans agrandir aveuglément les caches. |

### Sparse JIT PS5 : ce qui est réellement fait

| Composant | État source/hôte | Ce qui **n'est pas terminé** |
| --- | --- | --- |
| **Unique allocator natif** | **INTÉGRÉ** : `headless/jit-allocator.h` réserve deux vues RX/RW et ne retombe plus sur le JIT dense en PS5 natif ; `main.cpp` impose `ProbeSparseJitAlias()` avant démarrage du titre. Sélecteur release natif contrôlé par `check-native-sparse-jit-release-selector-host.py`. | Validation de l'alias avec firmware 13.60 et capture d'un lancement effectif ; si l'alias échoue, démarrage refusé (aucun fallback dense). |
| **RAM physique à la demande** | **INTÉGRÉ + témoins HÔTE** : `BlockOfCode::EnsureMemoryCommitted` et `src/memory_pages.cpp` engagent par blocs physiques de 2 Mio au lieu de réserver tout le physique à la création ; taille d'arène virtuelle fixe pour préserver les adresses relatives. | Prouver l'engagement progressif, les plafonds et la résilience mémoire dans FC27 et BOTW sur longue session. Une vraie saturation peut encore provoquer `bad_alloc`/arrêt du titre. |
| **Retour de RAM JIT** | **INTÉGRÉ + témoin HÔTE** : `TrimSparseJitCode` peut décommitter la queue uniquement après invalidation **complète et quiescente**, protéger les deux alias puis libérer le backing ; `check-native-sparse-jit-trim-host.py` valide un modèle natif extrait. | Ni récupération fine à chaque invalidation partielle, ni arbitrage continu pression RAM JIT/GPU/guest, ni preuve de cycles réels d'arrêt/reprise PS5. |
| **A32/A64 code lifetime** | **SOURCE / HÔTE partiel** : plans d'arènes et gardes de capacité, alias memo/invalidation générationnelle ; plan physique distinct du virtuel. | Corréler les longs ralentissements aux compilations réelles, confirmer invalidations concurrentes/quiescence sur matériel. |
| **Répartition CPU/compilation shaders** | **POLITIQUE INTÉGRÉE / CONSOLE NON MESURÉE** : le nombre de workers est limité par le masque d'affinité effectivement exposé et les réservations pour workers primaires ; la présence de CPU logiques ≠ cœurs physiques distincts. | Aucune preuve que l'émulateur exploite « 100 % » du CPU ni que davantage de workers améliore les latences. Démontrer temps CPU, contention, GPU idle/busy par phase avant adaptation. |
| **Vulkan, RADV et VRAM partagée** | **ADAPTATIONS INTÉGRÉES / PARTIEL** : compilations de pipelines asynchrones, caches persistés, textures/barrières synchronisées et mesures de pression ; préchauffage de **8** pipelines, pas précompilation totale. | Premier usage synchrone restant, attente pipeline worker, contenu HUD, contrôle effectif pression mémoire GPU et cadence stable. |
| **Robustesse livrable** | **EN COURS** : profil `tools/build-package.sh release` unique, ID `PPSA99008`; remplacement des commentaires CMake invalides et retrait du test dense obsolète le 26/10. | Réunir fast gate + prévalidation + build/package + sécurité en **SUCCESS sur le même HEAD**, puis une seule campagne console consolidée. |

**Attention :** « sparse JIT intégré » ne signifie **ni** « JIT terminé », **ni** « GPU/CPU utilisés au maximum », **ni** « FC27 jouable sans saccades ». La console réserve des ressources au système et les temps de synchronisation réels comptent davantage que la saturation CPU/GPU. Les anciennes notes « sparse DEV seulement » de documents historiques ne décrivent plus la sélection `PS5_NATIVE` actuelle.

## Référence console et critères d'acceptation

- Baseline réellement observée et **non remplacée par des hypothèses** : `cd4857c8` (25/10), à 1440p/1× : 204 fenêtres de 5 s, FPS médian 29,56, minimum 14,48, frame la plus lente 689,834 ms et 142 retards >100 ms ; à 2160p/1,25×, pire frame 977,578 ms. Ces sessions **ne sont pas** des A/B contrôlés. Les latences des menus et le HUD tardif subsistent.
- Baseline ressentie la plus jouable : **cache vidé + journalisation détaillée désactivée**, sans constituer une preuve que les logs ou caches sont la cause.
- **Avant test PS5** : échec-before/réussite-after hôte (si bug nouveau), source propriétaire effective et ses gardes, fast/preflight verts et ZIP PS5 de **même commit**. Pas de multiplication des microtests console.
- **Test final groupé** : même scène FC27 1440p/1×, mêmes options, cache défini, logging OFF, comparer retards >50/>100 ms et pire intervalle, nouveaux pixels HUD, maillots/terrain, latence pause/manette, stabilité/retour à l'accueil et réouverture. Tests BOTW de compatibilité et de redémarrage ensuite. Des FPS affichés ≠ fraîcheur d'image ni simulation invitée.
- **Clôture F07** uniquement après disparition vérifiée des saccades bloquantes et HUD retardé/absent sur PS5 réelle. **F01–F06 : 6/6 hôte ; pas 6/6 jeu.**

## CI — point de capture

À l'instant du contrôle du SHA `3ca07a442`, les workflows suivants **n'avaient pas encore de résultat de succès final** :
- [Prévalidation #40398310462](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40398310462) : en attente.
- [Compilation native #40398310477](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40398310477) : en cours.
- [Sécurité #40398310506](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40398310506) : en cours.
- Les anciens échecs au `bbc097f` portaient notamment sur deux défauts indépendants : commentaires `//` dans `headless/CMakeLists.txt`, et harnais dense qui ne compilait plus contre l'unique sparse JIT. Correctifs commits `f386d8c`, `93bb6d0`, `3ca07a4`. **Les correctifs ne constituent pas un CI vert.**
- Tout commit ultérieur (y compris ce document) exige de consulter **ses propres** résultats CI, pas ceux d'un commit précédent.

## Règle anti-boucle et prochain ordre concret

1. **Stabiliser le build :** fast gate, prévalidation, build natif, sécurité sur le même commit, réparer seulement les échecs prouvés. Une doc ou un harnais de test réparé n'est pas un gain FPS.
2. **P0.1 + P0.2** : première traduction de shader et éventuel `wait` du pipeline dans le worker Vulkan ; révéler précisément où le frame est retenu. Ne pas désactiver les fences ou forcer la publication d'un pipeline inexécutable.
3. **P0.3 + P0.4** : retrouver l'origine exacte de la contention et du HUD obsolète ; préserver cohérence TIC/TSC, DMA, barrières et ordre de présentation.
4. **P1.1 + P1.2** : après stabilité P0, qualifier mémoire sparse JIT sur vraie PS5, progression A32/A64 et relation commandes → guest → image.
5. **P2** : pression VRAM/direct-mem et OOM extrême, puis réglages visuels seulement quand le chemin principal est stable.
6. **Une campagne console**, une fois le paquet complètement vert et le lot P0 testable. Aucun nouveau « 7/7 » tant que la jouabilité n'est pas prouvée.

## Dossiers de preuves existants

- [F07 — priorités et mesures](FC27_F07_STUTTER_HUD_PRIORITY_2026-10-26.md)
- [F07 — audit transversal et sparse JIT](FC27_F07_CROSS_SYSTEM_OPTIMIZATION_AUDIT_2026-10-26.md)
- [F01–F06 — critères de sortie, traces et historique CI](FC27_EXIT_GATES_2026-10-22.md)
- [Une seule version PS5 livrable](EDEN_ONE_SHIPPING_PROFILE_2026-10-26.md)
- [Tableau à deux axes — historique des fichiers examinés](EDEN_TWO_AXIS_PROGRESS_2026-10-20.md)
- [Architecture native et contraintes PS5](PS5_NATIVE_ARCHITECTURE.md)

**Ne pas réutiliser les compteurs documentaires « fichiers restants » comme nombre de corrections requises :** inventaire, optimisation et qualification sont trois axes différents.
