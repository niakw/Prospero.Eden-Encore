# Eden Encore — FC27: triage CPU/JIT, caches, GPU et gel visuel

Date : 19 octobre 2026 · Branche : `dev/ps5-sparse-jit`

## État des preuves

La cartographie physique des sources permet de commencer les revues
fonctionnelles. Elle **n'est pas** une preuve que les 476 contrats
dépendance/fonction ont tous été exécutés et validés sur PS5.
Ne jamais confondre succès du préflight hôte, compilation, stabilité console
et fluidité perçue. Le launcher et ses thèmes restent hors périmètre.

La capture historisée `tools/fixtures/fc27-2efd8b3c-stutter-windows.json`
contient **415 fenêtres de télémétrie de cinq secondes**, source
`2efd8b3c96608667a2b22f1751eed1a475091cce`. Ce n'est **pas**
un benchmark des correctifs d'octobre 2026. Elle n'autorise pas de
comparaison de FPS « avant/après » avec le HEAD courant.

## Résultats reproductibles et séparation des domaines

Exécuter `python3 -B tools/check-fc27-stutter-regimes.py --self-test --json`
pour reproduire les calculs et invariants. Le champ
`bottleneck_signals` explicite les populations, sans inférence causale.

| Signal de la capture | Valeur | Interprétation acceptable |
|---|---:|---|
| Présentations de plus de 50 ms | 858 | Vraies irrégularités visibles possibles |
| Présentations de plus de 500 ms | 10 | Queues extrêmes à réduire sans casser la correction GPU |
| Plus longue présentation | 1 288,129 ms | Incident individuel, pas le framerate moyen |
| Fenêtres à ≥29,9 FPS | 341/415 | Une bonne moyenne n'atteste pas de la progression du jeu |
| Intervalles >50 ms dans ces fenêtres | 5 | Le gel d'image peut exister malgré l'affichage régulier |
| Fenêtres à moins de 25 FPS | 28/415 | Contiennent 668 des 858 intervalles >50 ms |
| Fenêtres JIT ≥500 ms cumulées | 25/415 | Compilation coûteuse, souvent au démarrage |
| Fenêtres cache-wait ≥100 ms cumulées | 17/415 | Contention distincte, surtout en jeu |
| Longues fenêtres ≥500 ms avec JIT ≥500 ms | 8/10 | Association forte, causalité par frame NON prouvée |
| Longues fenêtres ≥500 ms sans JIT ≥500 ms | 2/10 | Le JIT ne peut pas expliquer seul toute la queue |
| Fenêtres de saturation de file GPU mesurée | 0/415 | Aucune raison de gonfler la file pour **cette** capture |

Par phase : démarrage 42 fenêtres et 109 `late50` ;
gameplay 180 fenêtres et 679 `late50` ;
fin de session 193 fenêtres et 70 `late50`.
Les trois phases regroupent **la même capture**, pas trois benchmarks.
L'âge ou la fraîcheur des pixels n'est pas mesuré dans ce fichier.

## Ordre d'audit source recommandé

1. **P0 — JIT A32/A64 et temps de compilation initiale** :
   reconstituer le chemin réellement sélectionné pour les variantes
   native/release/DEV, distinguer re-traduction, invalidation, création
   de blocs et compilation simultanée. Le sélecteur source G11/X06
   est déjà migré et son tableau de variantes possède un témoin CMake ;
   restent à qualifier les invalidations effectives et les attentes
   JIT en exécution. Le compteur de
   compilation cumule plusieurs cœurs ; un pic ne prouve pas que le
   compositeur attendait un bloc donné. Priorité : trouver pourquoi
   8 des 10 grandes interruptions partagent de fortes compilations.
2. **P0 — Véritable progression du jeu durant le gel** :
   départager nouveau rendu du guest, réutilisation de buffer, callback
   de présentation et état des threads/HLE. La session R384 présentait
   encore des milliers de draws pendant un gel rapporté ; ni queue GPU
   ni FPS 30 ne prouvent que la scène progresse.
3. **P1 — Contention cache tampon/texture en gameplay** :
   identifier le détenteur du verrou et **sa durée de possession**,
   pas seulement le temps d'attente cumulé d'autres threads. Tracer
   les dépendances aux barrières, dirty invalidations et fences avant
   toute modification de portée d'un mutex.
4. **P1 — Intégrité HUD / textures / aliasing et copy sources** :
   tester les invalidations de descripteurs, frontières de durée de vie
   et ordre DMA → cache → draw → present. Préserver la correction du
   Fermi2D maintenu (#55/#56), dont l'élargissement de l'offset
   est un correctif sécurité et **pas un gain de FPS mesuré**.
5. **P2 — Affinité, capacité des workers, cache et mémoire** :
   garder l'affinité système comme témoin de référence, sans
   supposer la topologie SMT à partir d'identifiants logiques.
   Ne pas augmenter d'office les files, caches ou le JIT, ne pas
   libérer de mémoire sans propriétaires prouvés.

## Conditions avant modification des chemins chauds

- Associer une anomalie reproductible à la **fonction active** et à son
  graphe d'appel, puis prouver la sélection du fichier dans la
  compilation native (pas simplement sa présence sous `encore-active`).
- Ajouter un témoin hôte C++ du comportement précédent et du
  comportement corrigé, y compris les cas limites, les erreurs,
  le shutdown et les invariants d'ordre GPU/HLE/JIT.
- Garder les options expérimentales OFF et ne pas désactiver un mutex,
  un flush, un synchroniseur invité, une barrière ou un drain de GPU
  sur une simple corrélation.
- Prévalidation complète, analyse C/C++ et build PS5 identifié par SHA.
  Ensuite seulement comparer sur console **même scène/même réglages**
  p50/p95/p99 en frametime, incidents >50/>100/>500 ms,
  entrée-vers-image, HUD, mémoire physique et fermeture du jeu.

**Aucun gain FPS, réparation de freeze ou suppression de corruption
graphique n'est revendiqué par ce relevé.** Son utilité est de
prioriser les changements les moins spéculatifs et de prévenir
les « optimisations » qui masqueraient la véritable cause.


## Premier correctif moteur candidat : écriture CPU sans texture enregistrée

**Changement de code maintenu** :
`vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`,
`RasterizerVulkan::OnCPUWrite`.

La voie CPU-write native avait déjà une preuve monotone des pages
tampon jamais enregistrées, mais prenait systématiquement le mutex du
cache texture, même si la plage n'avait jamais appartenu à une image.
`ImagePages::NeverHeld(addr,size)` existait déjà pour la lecture
`GetFlushArea`. `TextureCache::RegisterImage` publie
`ImagePages::Mark` **avant** de remplir `slot_map_views`, y compris
pour les images clairsemées. `TextureCache::WriteMemory` ne visite que
les images actuellement enregistrées dans ce mapping.

`OnCPUWrite` évite désormais le mutex et la recherche texture pour
une écriture jamais vue dans une image, bornée à 256 KiB et dans l'espace
suivi. Dès qu'une page a été enregistrée, que la plage est inconnue,
hors bornes ou trop grande, le chemin verrouillé original est utilisé.
Les invalidations de shaders restent **toujours exécutées** lorsque
le buffer cache ne retourne pas la condition de sortie historique.
Aucun changement aux fences, barrières GPU, identités de textures,
allocations, paramètres du jeu ou cadence de présentation.

Tests : `check-ps5-image-pages-r433.py` valide l'ordre de publication,
les limites et la monotonie du témoin ; le nouveau
`check-ps5-guest-texture-write-elision-host.py` compile le corps C++
**extrait de la véritable méthode**, sous ASan/UBSan, et compare les
effets sur les caches tampon/texture/shader pour petites pages inconnues,
pages enregistrées, plages trop grandes et sortie anticipée.

Cette optimisation élimine une acquisition de mutex sur les écritures
dont l'absence de texture est prouvée. Un **gain mesuré de frametime,
FPS ou correction du freeze n'est PAS encore démontré sur console**.
Comparer le même jeu et le même profil avec un package identifié,
sans attribuer à ce seul changement un éventuel résultat mélangé.


## Vulkan — invocations d'invalidation sans image inscrite

19 octobre 2026 : les chemins maintenus
`RasterizerVulkan::InvalidateRegion`,
`RasterizerVulkan::InnerInvalidation` et
`RasterizerVulkan::OnCacheInvalidation` réutilisent l'indice
monotone `ImagePages::NeverHeld` déjà éprouvé pour le CPU-write et le
flush-area. Les petites plages dont aucune page n'a jamais hébergé
d'image évitent l'acquisition du mutex de texture. En lot, si **une**
plage est enregistrée, inconnue ou trop grande, toutes les écritures
texture sont exécutées dans leur ordre d'origine avec le mutex.

**Inchangés** : invalidations buffer, query et shader ; vérification
d'adresse/zéro ; traitement des plages connues/grandes/hors bornes,
arbitrage du pipeline, fences, worker GPU et mode différé OFF.
Le pont expérimental suit la source maintenue à code identique pour
ces trois méthodes, sans être activé.

Le témoin `check-ps5-texture-invalidation-elision-host.py` compile
les **trois méthodes extraites des sources C++ réelles**, en
ASan/UBSan, et vérifie les appels et acquisitions de mutex dans
toutes les branches, dont les lots mixtes et les bornes hors espace.
Ce test démontre une réduction **structurelle** d'acquisitions
pour les pages jamais possédées, **pas** un gain de FPS mesuré sur
PS5 ni une correction attestée des freezes.


## Vulkan — accélération des copies inline vers la mémoire invitée

19 octobre 2026 : `RasterizerVulkan::AccelerateInlineToMemory` ne prend
plus le mutex texture pour une copie vers un espace CPU dont les pages
**n'ont jamais été enregistrées comme images** (preuve monotone
`ImagePages::NeverHeld`). Une image connue, une plage de plus de 256 KiB,
une plage inconnue/hors suivi ou un chevauchement enregistré déclenchent
toujours l'invalidation verrouillée originale.

Important : `buffer_cache.InlineMemory / WriteMemory`, la copie RAM
invitée, les invalidations shader et query et le chemin de translation
impossible restent inchangés. `BufferCache::WriteMemory` marque en
effet la région CPU modifiée même quand aucun buffer n'est enregistré :
**il serait incorrect d'éliminer ce traitement** par un indice de pages
jamais enregistrées.

Le témoin C++ `tools/check-ps5-inline-texture-elision-host.py` extrait
la méthode réelle, compile sous ASan/UBSan et contrôle les domaines
mémoire, texture, buffer, shader/query, l'absence de traduction et
le retour conservateur pour les bornes. Aucun gain de FPS / disparition
de freeze n'est revendiqué sans benchmark console à SHA identique.


## Vulkan — déverrouillage évité lors d'une libération de plage CPU jamais enregistrée

19 octobre 2026. `RasterizerVulkan::UnmapMemory` n'acquiert plus le
mutex texture si `ImagePages::NeverHeld(addr, size)` établit que la
plage CPU n'a jamais hébergé d'image. Les plages connues, grandes,
inconnues ou hors de l'espace suivi conservent le parcours complet
`TextureCache::UnmapMemory` sous verrou ; celui-ci désenregistre les
images et libère leurs ressources. L'invalidation du buffer
`buffer_cache.WriteMemory` et du pipeline
`pipeline_cache.OnCacheInvalidation` **reste toujours exécutée**.

`ModifyGPUMemory` n'est **pas** optimisée par cet indice : sa plage
est indexée en adresses **GPU**, et la preuve CPU ne doit pas être
utilisée pour sa table d'images GPU. Le test source-extrait
`tools/check-ps5-texture-unmap-elision-host.py` utilise ASan/UBSan et
vérifie expressément cette séparation de domaines, les chevauchements,
les plages incertaines et toutes les autres invalidations. Le
générateur historique et le pont expérimental désactivé conservent la
parité exacte. Pas de gain FPS ou de freeze corrigé revendiqué sans
benchmark natif au même SHA.


## Vulkan — contrôles de readback sans cache texture inscrit

19 octobre 2026. `FlushRegion` et `MustFlushRegion` utilisent la
preuve monotone CPU `ImagePages::NeverHeld` pour éviter le mutex et
le parcours texture uniquement lorsqu'aucune image n'a jamais occupé
la plage. Les demandes inconnues, enregistrées ou trop grandes gardent
le traitement original. Les tailles nulles de `MustFlushRegion`
conservent également le passage verrouillé, sans changer l'ordre
buffer → texture. Les téléchargements buffers et notifications de
requêtes ne sont pas supprimés.

Témoin `tools/check-ps5-texture-flush-elision-host.py` compilant les
vraies méthodes C++ sous ASan/UBSan : plages inconnues, images
enregistrées, dépassements, buffers GPU-modifiés, niveau GPU bas et
requêtes de taille zéro. La variante expérimentale désactivée et le
générateur historique sont synchronisés. Aucun gain de FPS démontré
avant benchmark PS5 comparable au même SHA.


## Vulkan — lecture des buffers jamais enregistrés

19 octobre 2026, troisième passe. Dans `FlushRegion` et
`MustFlushRegion`, l'indice CPU `BufferPages::NeverRegistered`
dispense du mutex de cache buffer et du scan des plages GPU modifiées
**uniquement pour une région qui n'a jamais été enregistrée comme
buffer**. L'indice est publié dans la source complète maintenue
`buffer_cache.h` avant publication de la plage en page table.
Toute image connue, taille zéro, plage de plus de 64 KiB, adresse
invalide ou incertitude repasse par l'ancien traitement.

**Exception impérative : `buffer_cache.WriteMemory` et
`buffer_cache.OnCPUWrite` ne sont pas supprimés ni reclassifiés ici.**
Les transferts CPU doivent conserver leurs marques de cohérence,
même lorsqu'aucun buffer n'existe encore. L'optimisation ne cible
que le readback/bilan GPU; elle ne saute ni les requêtes QueryCache ni
les traitements texture, ni les synchronisations ou fences.

Le témoin ASan/UBSan `tools/check-ps5-buffer-readback-elision-host.py`
extrait les méthodes réelles et teste pages absentes, enregistrées,
histoire monotone, borne 64 KiB, taille zéro, buffers GPU-modifiés et
l'indépendance du cache texture. Le test de texture existant
marque explicitement ses buffers enregistrés : ses invariants
ne sont donc pas affaiblis. Les gains réels de frametime restent
à mesurer sur matériel, sans activer d'option expérimentale.

## 20 octobre — ne pas reprendre le verrou pour une compilation Vulkan terminée

`GraphicsPipeline::ConfigureDraw` conserve le callback GPU ordonné et le
`build_condvar.wait` pour les shaders réellement en cours de construction.
Mais si le constructeur a déjà publié `is_built=true` avec une écriture
`release` avant que le callback soit dépilé, le chemin active lit ce bit
avec `acquire` et revient immédiatement, sans relocker `build_mutex`
ou démarrer un timer de blocage inutile. Une publication encore absente
utilise exactement la condition variable et le verrou d'origine. Les shaders
échoués restent refusés par les contrôles de draw déjà en place.

La recette `tools/prepare-vulkan-port.py` est mise à jour simultanément
avec la source `vendor/encore-active` afin de conserver la stricte parité
des 43 backports et de l'oracle Vulkan. Le nouveau test C++ extrait le
callback réel et vérifie sous ASan/UBSan l'absence de prise de verrou
lorsque le pipeline est prêt, puis le réveil correct lorsque la compilation
est encore en cours. Pas de mutation des fences, cache images ou ordres
GPU/guest. Le gain de latence PS5 reste à mesurer sur un paquet identifié.

## 20 octobre — recherche texture évitée dans les lots d'invalidation mixtes

`RasterizerVulkan::InnerInvalidation` évitait déjà complètement son
verrou texture si **toutes** les plages étaient exemptes d'image selon
`ImagePages::NeverHeld`. Lorsqu'une plage enregistrée (ou incertaine)
apparaissait, il conservait correctement ce verrou mais parcourait
**également** le cache texture pour les plages prouvées sans image.

Le code actif, sa copie de compatibilité et la recette de génération
recherchent maintenant uniquement les plages potentiellement enregistrées,
avec une vérification par plage **sous** le mutex texture. Les pages
connues, inconnues et trop grandes gardent le traitement complet.
L'ordre des recherches conservées et les invalidations buffer, query
et shader restent inchangés. Les tests source-extraits ASan/UBSan
vérifient les lots entièrement vides, mixtes, inconnus et surdimensionnés,
le nombre de verrous, de recherches texture et les autres caches.
C'est une réduction structurelle du travail des invalidations mixtes ;
elle ne démontre pas un gain FPS sur PS5.

## 20 octobre — réception IPC : index initialisé sur échec avant signalement

Lors de `ReplyAndReceiveImpl`, `KSynchronizationObject::Wait` peut
retourner une annulation ou une demande de terminaison **sans avoir rempli**
l'index de l'objet synchronisé. Ces chemins d'erreur passaient malgré tout
par `*out_index = index`, avec une variable locale précédemment non initialisée.
La voie native standard et la voie diagnostique initialisent désormais
l'index à `-1`, sans changer les durées d'attente, la signalisation,
les mutex, les renvois d'erreur ni l'index sur succès. Un timeout
continue de sortir avant la recopie de l'index.

Le nouveau témoin C++ compile la boucle réelle des deux variantes avec
ASan/UBSan, vérifie les erreurs immédiates, le succès et la reprise de
boucle lorsque `ReceiveRequest` renvoie `ResultNotFound`. Le test
antérieur de saturation du timeout conserve la parité au code amont
épinglé, en tenant compte uniquement de ces deux modifications natives.
L'amélioration concerne la sûreté du protocole HLE ; aucune baisse de
frametime ou réparation du gel FC27 n'est affirmée sans validation console.

## 20 octobre — file GPU : éviter le verrou quand un slot est déjà libre

La production GPU utilise la file SPSC avec un producteur sérialisé.
Après un `TryEmplace` ayant observé une file pleine, le consommateur
peut libérer un slot avant `EmplaceWaitWithStopToken`. L'ancien chemin
reprenait quand même le verrou de condition variable et enregistrait une
attente stoppable, même si la capacité était déjà disponible.

Le nouveau chemin relit l'index consommateur avec `acquire` ; si un slot
est maintenant libre, il conserve l'écriture et la notification FIFO
mais **évite** ce verrou et la registration de l'attente. Si la file
reste pleine, il conserve le mutex, la condition variable et l'annulation
par `stop_token` tels quels. Le contrôle du stop avant insertion reste
présent dans tous les cas. Un témoin C++ compile l'en-tête réellement
maintenu, vérifie réutilisation, file pleine, réveil du producteur,
annulation et absence d'insertion après arrêt avec ASan/UBSan.

Cette réduction n'affecte que le cas de course « pleine puis libérée ».
Elle ne doit pas être interprétée comme un gain FPS démontré ni comme
un correctif des attentes du GPU en général.

## 20 octobre — sémaphore GPU en cas d'échec fatal du worker

Le puller d'acquisition GPU (`Puller::ProcessSemaphoreAcquire`) conservait
une boucle tant que la valeur mémoire n'était pas atteinte et que le
système n'avait pas commencé son arrêt. Un autre worker GPU pouvait
pourtant publier une exception fatale sans que cette boucle, qui appelle
`ReleaseFences`, ne vérifie l'état d'échec. En cas de valeur qui ne
progressera plus, cette attente risquait de monopoliser son thread.

Sur PS5, cette acquisition consulte maintenant le registre d'échecs
GPU partagé au premier essai, puis une fois tous les 64 essais infructueux.
Elle propage l'exception existante sans fabriquer d'acquittement de
sémaphore, sans modifier le timeout invité, les fences, la mémoire
invitée, ni l'ordre des commandes. Les chemins hôte ne changent pas.
Les fichiers normal et DEV restent strictement dérivés de la source
épinglée via `check-maintained-guest-gpu-sync.py`.

Le témoin C++ ASan/UBSan extrait la vraie méthode dans les quatre
combinaisons PS5/hôte et normal/DEV ; il vérifie l'arrivée du sémaphore,
l'arrêt, l'erreur apparue pendant l'attente et une erreur déjà publiée.
C'est une protection contre une attente sans issue **après échec GPU**,
non une accélération mesurée ni une suppression prouvée du gel FC27.

## 20 octobre — conserver la cause GPU après sa livraison au launcher

Une seconde revue a montré une dépendance importante du correctif de
sémaphore : le thread de commandes du launcher utilise `TakeGpuFailure()`
pour signaler la panne au menu. Jusqu'ici cette fonction retirait la seule
référence de l'exception ; un autre thread CPU/GPU qui appelait
`PeekGpuFailure()` après cette livraison pouvait **manquer** la panne et
rester bloqué en attente d'un sémaphore ou d'un fence jamais confirmé.

Le registre `headless/gpu_failure.h` a maintenant deux rôles distincts :
un message d'erreur **livrable une seule fois** au launcher et une cause
fatale **conservée pour tous les waiters de la session**. Le launcher
réinitialise les deux uniquement au début d'un nouveau titre, à la
frontière où les anciens GPU workers ont été arrêtés. Le même diagnostic
reste accessible après livraison du message UI ; aucune fausse
confirmation GPU, aucun saut de fence ou nouveau timeout n'est introduit.

Les témoins GPU producer et sync existants vérifient la sémantique du
`Take` séparée du `Peek`. Le nouveau témoin C++ sous ASan/UBSan
contrôle huit lecteurs concurrents, deux exceptions successives, une
livraison unique et l'absence de propagation au titre suivant. Le
correctif est spécifique aux scénarios de panne fatale, non aux coûts
normaux de frametime.

## 20 octobre — présentation synchrone : rendre la frame libre sous mutex

`PresentManager::GetRenderFrame` attend sur `free_cv` en contrôlant
`free_queue` sous `free_mutex`. Sur le mode `async_presentation=OFF`,
`PresentManager::Present` réintroduisait jusqu'ici la frame directement
dans cette file **sans** le mutex et **sans notification**. Un lecteur
concurrent pouvait donc ne pas se réveiller et l'accès à `free_queue`
était non synchronisé. Le chemin asynchrone possédait déjà son
publication correcte dans `PresentThread`.

Le chemin synchrone garde `scheduler.WaitWorker` puis
`CopyToSwapchain` dans leur ordre d'origine. Un court verrou
`free_mutex` protège désormais uniquement `free_queue.push_back`,
suivi de `free_cv.notify_one()` après libération du verrou. Le mode
asynchrone, les fences, les erreurs de copie et les appels Vulkan ne
changent pas. Source active et recette de génération sont modifiées
ensemble ; le replay sur la source amont épinglée vérifie cette parité.
Un témoin C++ construit les méthodes natives extraites sous ASan/UBSan
et vérifie le réveil d'un consommateur, le verrouillage, l'absence de
recyclage après échec et l'absence de changement de la file asynchrone.
Il ne prouve pas encore un gain de FPS ni la disparition des gels FC27.

## 20 octobre — DMA : sortir d'une attente de fence après échec du GPU

Dans `DmaPusher::Step`, la condition `signal_sync && !synced` attendait
un acquittement par boucles `sync_cv.wait_for(10 ms)`, sans consulter
`PeekGpuFailure`. Un worker GPU mort avant la notification pouvait
laisser le producteur bloqué tant que l'arrêt global n'était pas annoncé.
Sur PS5 seulement, la boucle consulte maintenant le registre d'échec
GPU avant chaque attente et une seconde fois avant d'accepter un
acquittement concurrent. Une panne provoque la propagation de la cause
existante, **sans** créer de fence, modifier la mémoire invitée ou
déclarer `synced=true`. La variante DEV garde son timer de contention
et les chemins hôte ne changent pas. Le registre d'échec est remis à
zéro entre titres comme dans le correctif précédent.

Les deux implémentations normal/DEV et le contrôle de parité de leur
source d'origine évoluent ensemble. Le test C++ extrait les vraies
branches de `Step`, compile les quatre variantes avec ASan/UBSan, et
vérifie l'acquittement normal, l'arrêt, la panne antérieure/pendant
l'attente et la livraison unique au launcher. Il ne mesure pas les
frametimes FC27 ni les performances réelles sur console.

## 20 octobre — le worker Vulkan publie ses erreurs avant de rendre le verrou

L'absence de `catch` dans la boucle Vulkan permettait à une exception
émise par `CommandChunk::ExecuteAll`, `AllocateWorkerCommandBuffer`
ou un appel Vulkan de terminer le thread via `std::terminate`, alors
que `Scheduler::WaitWorker` attend une file qui peut demeurer non vide.
Sur PS5, le worker capture désormais l'exception **pendant que
`execution_mutex` est encore détenu** et la transmet au registre
`RecordGpuFailure`, puis notifie les attenteurs sur `event_cv`.
Le prédicat de vidage du producteur observe aussi le registre fatal et
réémet la cause sans fabriquer une soumission, un tick GPU ou une frame.
Un `catch` autour de l'entrée `std::jthread` couvre également les
exceptions d'initialisation, avant la prise des verrous d'exécution.
La variante non PS5 conserve son comportement d'origine.

Le test hôte extrait la vraie entrée du thread, sa boucle et
`WaitWorker`, et couvre les commandes normales, une exception avant
vidage de la file et une exception pendant la réallocation de commandes.
La source active et la recette de génération Vulkan sont synchronisées.
Cela ne valide ni le traitement des attentes d'un tick matériel perdu,
ni le comportement du pilote PS5 ; aucune mesure de FPS n'en découle.

## 20 octobre — intégrité de la clé Vulkan multi-plages

`MultiRangeBufferCache::HashSources` distinguait le buffer et son
décalage, mais omettait l'identité `VkDeviceMemory`, son offset physique
et le type mémoire. La réutilisation sous le même `VkBuffer` après
modification de l'adossement risquait de conserver une association sparse
obsolète. Ces trois propriétés rejoignent la clé de géométrie ;
`write_tick` reste exclusivement une invalidation du contenu et ne
déclenche pas de reconstruction physique inutile. Le témoin compilé
ASan/UBSan couvre les changements indépendants de mémoire, d'offset,
de type et de taille. Aucun gain FPS PS5 n'est encore mesuré.

## Vulkan — completion pipelines partagée (20 octobre 2026)

Le témoin `tools/check-native-vulkan-striped-wait-host.py` compile l'en-tête natif réellement
utilisé par les pipelines graphiques et compute, sous ASan/UBSan.
Il crée une collision contrôlée dans les 64 conditions partagées :
le réveil d'un pipeline ne doit ni terminer incorrectement l'autre
ni le bloquer indéfiniment. Seule cette propriété de concurrence
est qualifiée. **Aucun gain de FPS n'a été mesuré sur console.**

## 20 octobre — framebuffer invité absent, données upload périmées

`Layer::UpdateRawImage` copiait le buffer d'upload Vulkan même lorsque
`GetPointer` ne retournait aucun backing mémoire invité, risquant de
recopier les octets d'une ancienne frame. La nouvelle branche efface
uniquement la tranche correspondant à l'image absente, puis la flush
avant la commande de copie. Le chemin valide garde le désentrelacement
et son flush, sans nouveau travail. Un test C++ ASan/UBSan extrait les
fragments d'origine et maintenu, reproduit l'ancien comportement et
vérifie les cas source absente/présente ainsi que les tranches voisines.
Aucun gain FPS ou réparation complète du HUD PS5 n'est revendiqué.

## 20 octobre — correctif durée de vie du cache Vulkan multi-plages

Le chemin `MultiRangeBufferCache::Get` enregistrait les `owners`
**uniquement** si un bind sparse avait réussi. Lorsque le GPU utilisait
le fallback `gathered`, `DropOwner` ne retrouvait donc jamais le
buffer à retirer à la destruction d'une source. Les propriétaires sont
maintenant enregistrés pour les deux formes, et leur libération reste
déférée jusqu'à l'achèvement du tick via les méthodes d'origine.
Un témoin extrait du code natif, compilé sous ASan/UBSan, exerce les
deux chemins, les invalidations et le seuil de 256 retraits.
Cette correction cible les risques de textures/états GPU périmés,
sans démontrer de gain de FPS ni de réparation du HUD sur PS5.

## 20 octobre — garde GPU pour multi-plages gathered

`MultiRangeBufferCache::Get` valide désormais les handles, les tailles et
les débordements `offset + size` ainsi que la somme des copies **avant**
l'allocation et l'émission des commandes de repli `gathered`. Auparavant
le chemin sparse vérifiait ces limites, mais le chemin gathered ne les
appliquait pas, malgré une destination de taille `total`.
Un test ASan/UBSan extrait et compile la vérification native,
y compris la plage finale, les sources nulles et une destination trop
petite ; les demandes valides avec padding restent acceptées.
La parité générateur/Vulkan est conservée. Pas de gain FPS certifié.

## 20 octobre — inversion de condition de rendu conservée à tort

`QueryCacheRuntime::HostConditionalRenderingCompareValueImpl` retournait
sans reconfigurer le rendu conditionnel dès que le `VkBuffer` et son offset
restaient les mêmes. Or deux comparaisons consécutives peuvent inverser
`is_equal` sans changer le buffer de prédicat : conserver le flag précédent
peut supprimer un dessin valide ou afficher un dessin interdit.
La clé de réutilisation compare maintenant aussi les flags
`VK_CONDITIONAL_RENDERING_INVERTED_BIT_EXT`. Si la polarité change,
le code de pause/reprise existant rebâtit le prédicat; si elle ne change pas,
il conserve le retour anticipé performant.

`tools/check-vulkan-query-conditional-inversion-host.py` compile la méthode source exacte sous ASan/UBSan et
reproduit l'erreur ancienne (inversion non prise en compte) avant de
vérifier la transition dans la nouvelle. Aucune causalité spécifique
avec le HUD de FC27 ou gain de FPS n'est encore établie matériellement.

## 20 octobre — résultats de requêtes GPU traversant une page mémoire

La construction de `QueryCacheRuntime::SyncValues` n'allouait qu'une
page alignée sur l'adresse **initiale** de chaque résultat. Pour un
résultat de 8 octets commençant quatre octets avant la frontière,
la commande Vulkan pouvait copier au-delà de la plage obtenue.
La nouvelle plage couvre la dernière page réellement touchée et
étend une région déjà fusionnée en cas de chevauchement.
Les tailles cumulées, la fin de l'espace d'adressage et la limite
`u32` imposée par `ObtainCPUBuffer` sont vérifiées avant de demander
la mémoire GPU. Le test `tools/check-vulkan-query-page-span-host.py` compile la boucle native
extraite sous ASan/UBSan et vérifie les cas valides et limites.
Le correctif empêche un débordement logique du buffer de résultats ;
aucune mesure de saccades ni de FPS sur PS5 n'a été effectuée.

## 20 octobre — vidage de file lors du redémarrage du worker GPU

Les deux variantes natives `ThreadManager::Stop` rejoignaient le thread
sans retirer les commandes déjà placées dans la file SPSC. Sur un
redémarrage, celles-ci pouvaient donc être exécutées avec un nouveau
contexte graphique, ou retenir de la mémoire après fermeture. Le worker
est maintenant rejoint **avant** qu'une lecture de file avec le verrou
producteur ne détruise les commandes abandonnées. L'ordre FIFO du travail
normal et la gestion des exceptions du worker sont inchangés.

Le témoin `tools/check-native-gpu-worker-restart-drain-host.py` compile sous ASan/UBSan la méthode native
identique des variantes silencieuse/diagnostic avec la vraie SPSC,
teste la destruction des propriétaires, l'arrêt répété et le nouveau
cycle. Un gel à mi-temps et les FPS sur PS5 restent à mesurer.

## 20 octobre — retour anticipé sur une fence Vulkan déjà terminée

`InnerFence::Wait` appelait `Scheduler::Wait` même lorsque
`Scheduler::IsFree(wait_tick)` indiquait un tick de timeline achevé.
Le tick terminé étant monotone, la nouvelle voie quitte la fonction
avant le coût de synchronisation; les ticks en attente conservent
leur vraie attente GPU et la mesure de coût existante. Les fences
`stubbed` restent des opérations nulles. Le témoin
`tools/check-vulkan-fence-completed-wait-host.py` compile les deux méthodes native/épinglée sous
ASan/UBSan; sur un scénario de quatre appels dont un seul réellement
en attente, le témoin hôte passe de quatre appels d'attente à un seul.
Cela **ne prouve pas** que ce scénario se produit fréquemment en jeu
ni un gain de FPS sur PS5.
