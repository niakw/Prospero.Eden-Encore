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

## P0.4 — sélection d'une image réellement fraîche à la présentation

Correctif du 27/10 : le framebuffer accéléré ne doit pas sélectionner un
`ImageView` dont le backing est `Remapped` ou dont les pixels invités ont
été modifiés (`CpuModified`) sans rafraîchissement de l'image Vulkan.
Dans `TryFindFramebufferImageView`, ces candidats sont désormais exclus
**uniquement sur PS5**. Sans vue accélérée admissible,
`RasterizerVulkan::AccelerateDisplay` laisse `Layer::ConfigureDraw`
utiliser `UpdateRawImage`, qui lit et charge le framebuffer invité actuel.
Les vues GPU propres continuent d'utiliser le chemin zéro-copie habituel.
En complément, `RasterizerVulkan::AccelerateDisplay` exécute maintenant
`gpu_memory->FlushCaching()` **avant** la prise du mutex texture ;
ainsi un remappage invité en attente ne peut pas faire sélectionner
un ancien framebuffer accéléré après le changement de mapping.
La source active, le générateur d'archives pinnées et le témoin C++ -O0/-O2
sont modifiés ensemble. Cela ferme un chemin de réutilisation périmée,
**pas** la validation finale des pixels/HUD sur l'écran de la console.

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

## Réutilisation ciblée depuis la branche expérimentale — 26 octobre

Le lot **R01** a été adapté dans les sources natives de production : compteurs
séparés des composites Vulkan, images réelles/générées mises en file, images
ignorées, écrans de chargement et retours d'appel `Present`. La mesure n'est
active qu'en profil de diagnostic détaillé ; les tests C++ natifs, analyseur
hors-ligne, replay F03/F05 et contrôle de parité du générateur sont intégrés.
**État : SOURCE INTÉGRÉE, CI ET CONSOLE NON QUALIFIÉES** ; aucun gain FPS/HUD ne
peut encore être revendiqué. R03 RADV/SPIR-V, R04 AudioIn/RomFS et R06
frame generation restent hors de ce lot (pas de fusion globale). Détails :
[FC27_R01_SOURCE_TELEMETRY_PORT_2026-10-26.md](FC27_R01_SOURCE_TELEMETRY_PORT_2026-10-26.md).

## P0.1 — temps de traduction des shaders, détail RELEASE

Une première création de pipeline appelle déjà des phases CPU distinctes
qui restaient masquées par les anciens timers Vulkan DEV. Le chemin natif
sélectionné mesure maintenant en **diagnostic détaillé uniquement** :
`shader_pool_reset`, `shader_cfg`, `shader_ir`, `shader_spirv`,
`shader_module`. Les durées, sous-phases de `graphics_pipeline_create`,
ne doivent pas être additionnées comme une seule frame si plusieurs workers
les rapportent. Aucun shader, fence ni ordre de dessin ne change.
**F07 reste ouvert :** c'est une attribution, pas un gain FPS démontré.
Le chemin silencieux ne prend aucun chronométrage supplémentaire.

## P0.2 — coût des attentes de pipeline Vulkan

Le chemin graphique et compute conservent leur vérification de disponibilité
acquire avant d'enregistrer et d'exécuter la callback du scheduler. Si la
compilation est encore en cours **au moment réel de la callback**, la section
bloquante signale maintenant respectivement `graphics_pipeline_wait`
ou `compute_pipeline_wait` dans `EDEN_GPU_CACHE_PHASE`, uniquement lorsque
la journalisation détaillée est activée. Cela mesure mutex + condition
d'attente, et non du temps GPU. Les tests extraient la callback C++ et couvrent
pipeline prêt en avance, construction inachevée, profil silencieux, et échec
de pipeline compute. Aucun `wait`, fence ou ordre de commande n'est supprimé.
**Ce changement apporte une attribution des blocages, sans gain FPS revendiqué.**
Les coûts agrégés des différents threads ne valent pas durée d'une frame.

## P0.2 — préservation des workers shader après annulation

Le générateur Vulkan et la source active dissocient l'annulation du lecteur
de cache de celle du pool de compilation PS5.
`StatefulThreadWorker::WaitForRequests(stop_token)` appelle
`request_stop()` sur **tous** les workers lorsque le jeton de chargement
est annulé. Un retour au lanceur pendant un chargement pouvait ainsi
rendre les compilateurs indisponibles pour les nouveaux shaders.

Sur PS5, `workers.WaitForRequests()` attend seulement la fin des
huit jobs de préchauffage au maximum, sans stopper les workers.
Les autres plateformes conservent `WaitForRequests(stop_loading)`.
Le test hôte reproduit une annulation après admission des jobs puis
l'acceptation d'un nouveau shader. Il n'y a aucune nouvelle attente
dans la boucle de dessin. Le gain FPS et le HUD restent à qualifier
sur matériel.

## Dossiers de preuves existants

- [F07 — priorités et mesures](FC27_F07_STUTTER_HUD_PRIORITY_2026-10-26.md)
- [F07 — audit transversal et sparse JIT](FC27_F07_CROSS_SYSTEM_OPTIMIZATION_AUDIT_2026-10-26.md)
- [F01–F06 — critères de sortie, traces et historique CI](FC27_EXIT_GATES_2026-10-22.md)
- [Une seule version PS5 livrable](EDEN_ONE_SHIPPING_PROFILE_2026-10-26.md)
- [Tableau à deux axes — historique des fichiers examinés](EDEN_TWO_AXIS_PROGRESS_2026-10-20.md)
- [Architecture native et contraintes PS5](PS5_NATIVE_ARCHITECTURE.md)

**Ne pas réutiliser les compteurs documentaires « fichiers restants » comme nombre de corrections requises :** inventaire, optimisation et qualification sont trois axes différents.

## P0.2 — vie des compilations optimisées en attente (27 octobre)

Le chemin « fast-first » maintenait `OptimizeState::running=false` entre
`QueueWork` et le début effectif du worker : le destructeur pouvait alors
libérer un `GraphicsPipeline` encore capturé par un job en file. La correction
marque le travail **en attente avant publication**, puis libère cet état pour
toutes les sorties (annulation avant démarrage, exceptions, fin normale et
échec de l'admission dans la file). Elle ne publie plus un pipeline optimisé
si le pilote retourne un handle Vulkan nul. Le témoin C++ natif vérifie les
cycles annulation/fermeture, pipeline manquant et refus de file, tandis que la
reproduction du générateur Vulkan conserve la parité avec la source sélectionnée.

C'est un correctif de **durée de vie et de validité des pipelines**, sans preuve
de réduction des saccades, ni levée du F07 sur console.

## Dernière base CI pleinement vérifiée

Sur `d76fc53a9ae553eef61e0898195d5ea374b1b2b0`, les quatre jobs
(native build, fast gate, preflight complet, analyse de sécurité) sont
`SUCCESS`. Toute modification après ce commit doit faire ses propres
contrôles CI au même SHA ; un résultat antérieur n'est pas transférable.

## P0.1 — rattrapage borné des shaders compute (27/10)

Une traduction compute retournant un pointeur nul demeurait en cache sans
nouvelle tentative. Le chemin natif PS5 permet maintenant **une seule reprise
après deux secondes**, bornée à **32 clés échouées**, sans lecture d'horloge ni
compilation supplémentaire pour les compute pipelines déjà valides. Un échec
persistant ne provoque aucune boucle. La source native et sa reproduction
Vulkan sont synchronisées ; un test C++ extrait la vraie politique et couvre
O0/O2 et le budget de retries. Le défaut distinct d'un handle Vulkan qui
échoue après création asynchrone n'est pas traité ici. **F07 et la preuve
HUD/FPS console restent ouverts.**

## P0.2 — fermeture du compteur de compilation compute

En production native, la notification shader-building du constructeur
compute précède les opérations d'initialisation du layout et l'admission
au worker. Une exception sur ces chemins pouvait garder le compteur en état
« compilation en cours ». La garde RAII native retourne maintenant la
notification avant le transfert ; après transfert, le SCOPE_EXIT existant de
la callback reste son unique propriétaire. Le test hôte reproduit la fuite
sur l'ancienne route et vérifie préparation échouée, file fermée, compilation
inline et worker différé en -O0/-O2. Aucun changement de synchronisation
des ressources invitées ni d'attente GPU. F07 console non qualifié.

## P0.4 — restauration de texture après erreur d'upload

TextureCache::RefreshContents efface CpuModified avant staging, copie et barrière Vulkan. Une exception sur ces étapes laissait une image considérée propre sans upload terminé. La source PS5 restaure maintenant CpuModified et annule le suivi de pages si cet upload synchrone échoue. Un upload et sa barrière terminés conservent l'état propre. Le générateur, l'en-tête actif et le témoin hôte O0/O2 sont synchronisés. Pas de modification aux branches de retour MSAA/async. Pas de preuve de correction du HUD/FC27 sur console.

## P0.3 — attribution compute du verrou buffer/texture

`DispatchCompute` acquiert la paire de mutex buffer/texture puis exécute `Configure` et la préparation des commandes. Jusqu'ici ses coûts ne contribuaient pas aux phases `pair_wait/pair_held` réservées aux draws graphiques. Trois phases spécifiques `compute_pair_wait`, `compute_pair_held`, `compute_configure` distinguent désormais sur le chemin PS5 l'attente de la paire, la durée sous verrou et la configuration du shader compute, avec le même échantillonnage 1/16 exclusivement en Detailed Logging. Aucun nouveau verrou, barrière, drainage ni appel d'horloge en mode silencieux. Le test hôte verrouille la parité entre enum/rapport, vrai chemin source et générateur; ce lot est un instrument de diagnostic, pas encore une optimisation FPS.

## F07 — réutilisation du quota des reprises de shaders échoués (27 octobre)

Les budgets natifs de métadonnées de reprise (64 clés graphiques et 32 compute)
comptaient encore les tentatives **déjà consommées mais toujours en échec**.
Après saturation, un nouveau shader transitoirement indisponible pouvait
rester définitivement nul, sans accès à son unique reprise différée. Le suivi
est désormais libéré après chaque tentative, réussie ou non : l'entrée nulle
du cache de pipeline continue à interdire toute nouvelle tentative pour cette
même clé. Aucun travail supplémentaire sur les shaders valides ni dans la
boucle chaude. Témoins source-extraits O0/O2 : épuisement initial du quota,
réutilisation, absence de seconde reprise et conservation du délai de 2 s.
**Correctif source/hôte à qualifier en CI ; pas de gain FPS/HUD démontré.**
