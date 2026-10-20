# Cloud source audit — 20 octobre 2026

Branche `dev/ps5-sparse-jit`, base `82c531d08641d8b28124bd2cebf37fcf85674179`.
Les preuves de cette passe proviennent de contrôles locaux ; elles ne constituent
pas une CI distante ni un binaire PS5 qualifié.
**Compteur courant : 398 fichiers / 96 P0 / 409 contrats.**
Les chiffres 400 / 98 / 411 ci-dessous décrivent le relevé initial.

**État final local : build release et paquet réussis sur
`615510b20edb161517c096e90b186a41db571ab6`.** Les lots de code ont été publiés
sur `dev/ps5-sparse-jit`. Les 939 étapes de recompilation Zen2 ont terminé,
puis cinq étapes incrémentales ont actualisé la provenance du binaire sans
relancer les précontrôles déjà réussis. Les contrôles après compilation sont
restés activés et passent : 379 dépendances sparse canoniques/dérivées identiques,
verrou JIT réel (200 000 opérations concurrentes et code machine), liaison
RADV/OpenGL et ABI, inventaire du paquet, imports, alignement et intégrité.
Les deux derniers contrôles natifs ont aussi été migrés depuis leurs anciens
fragments supprimés vers les propriétaires maintenus, sans retirer de preuve.

Paquet local : `build/release/PPSA99008`. Empreinte SHA-256 de `eboot.bin` :
`00425803a454697be35c54c4dbac589e03756d9313f4b8e0d8b699ee976d6a66`.
La chaîne du SHA source a été vérifiée dans l’ELF ; les commits documentaires
suivants ne changent pas le code compilé. Preuve locale :
`results/optimization-final-2026-10-20/native-package.json`, journal
`/workspace/shared/eden-native-package-current-sha.log`. Aucun résultat matériel
ou de CI distante n’est ajouté. Les étapes « en cours » ci-dessous décrivent
les passes intermédiaires et sont remplacées par cet état final.
 Le test PS5 est différé à la fin, à la demande de
l’utilisateur.

## Lot HLE, mémoire et Vulkan

- Deux oracles HLE réintègrent exactement le changement `b8793d2`, sans
  assouplir la comparaison complète des sources. Le témoin de `Wait` complet
  teste aussi la perte du mapping de clé après le premier contrôle, avec
  annulation du sommeil et absence d’inscription en attente.
- `src/host_memory.cpp` borne la longueur avant addition dans `Window::Pages`.
  L’ancienne expression reproduit une page hors fenêtre ; 90 cas limites
  vérifient le correctif sous ASan/UBSan. La reconstruction du bitmap conserve
  aussi la permission de la page suivante au lieu de la relire : 1 048 577
  évaluations au lieu de 2 097 152 pour la fenêtre complète, avec une carte
  résultante identique dans le témoin hôte. Voir
  [l’analyse fastmem](EDEN_FASTMEM_WINDOW_BOUNDS_2026-10-20.md).
- `QueryCacheRuntime::SyncValues` réserve les destinations avant le mutex et
  trie des indices pour fusionner les plages en O(N log N), avec redirections
  vers les requêtes d’origine. Les boucles de copie conservent leur ordre.
  Le témoin de 1 024 plages passe de **523 776 à 1 023 comparaisons** et de
  **11 allocations sous verrou à zéro** (une allocation avant verrou).
  Une plage traversant une page ne laisse plus deux groupes qui se recouvrent.
  Voir [les hypothèses et limites](EDEN_QUERY_SYNC_ALLOCATIONS_2026-10-20.md).
- Le fast gate exécute les nouveaux témoins et les deux anciens contrôles HLE
  qui avaient divergé. Aucun push, lancement de CI, release ou changement de
  réglage expérimental n’a été effectué.

Ces chiffres décrivent du travail hôte supprimé. Aucun gain FPS, correction de
mi-temps/fin de match ou reprise effective du PC invité n’est revendiqué.

Un second défaut HLE a été reproduit : l’échec du drapeau pouvait survenir
après le réveil du prochain propriétaire du mutex. Sa publication précède
maintenant ce transfert, sous le même verrou scheduler. Le témoin de `Wait`
complet démontre l’absence de transfert/réveil lorsque la publication échoue.
Voir [l’analyse du transfert CV](EDEN_HLE_CV_HANDOFF_2026-10-20.md).

Un défaut supplémentaire concernait le permis de contexte du thread initial :
son entrée directe dans la fibre précédait l’acquisition normale, alors que
`Unload` rendait ensuite ce permis. L’initialisation le réserve maintenant.
Le témoin extrait des vraies méthodes passe 64 cycles sous ASan/UBSan, avec
un contrôle négatif sur l’ancienne initialisation. Voir
[l’analyse du démarrage scheduler](EDEN_SCHEDULER_BOOTSTRAP_PERMIT_2026-10-20.md).

## Périmètre vérifié sans oublier les fichiers hors graphe

`python3 -B tools/audit-cloud-worklist.py --json` produit un inventaire
recalculable, avec hash de chaque source, identifiants de contrats, priorités
et critères encore attendus. Il joint le graphe aux sources C/C++ suivies sous
`headless/`, `src/` et `vendor/encore-active/`. Il n’attribue aucun statut HOST. Le JSON recense aussi les shaders, recettes de
compilation, CI, outils, manifestes et documents hors de ces fichiers C/C++,
y compris les nouveaux fichiers locaux non encore suivis par Git.

| Périmètre | Nombre |
| --- | ---: |
| Contrats indexés | 478 |
| Contrats SOURCE ou OPEN | 411 |
| Fichiers SOURCE ou OPEN | 400 |
| Fichiers P0 SOURCE ou OPEN | 98 |
| Fichiers C/C++ Encore suivis dans ce périmètre | 491 |
| Union des sources Encore et des sources référencées par le graphe | 538 |
| Fichiers Encore hors graphe principal | 83 |

Les 83 fichiers supplémentaires comprennent 5 fichiers `src/`, 63 fichiers
sous `headless/prosperoeden/` et 15 autres fichiers `headless/` (élévation,
fixtures de vérification et tables générées comprises). Ils sont **recensés**,
ce qui ne signifie pas qu’ils ont tous reçu une revue sémantique ou un test
matériel. Le launcher et les thèmes gardent leur périmètre séparé ; aucun
changement visuel n’est inclus. Les dépendances externes immuables restent
couvertes par leurs contrôles d’intégrité/provenance, et ne sont pas présentées
comme autant de nouveaux fichiers Encore optimisés.

Les 411 contrats sont conservés individuellement avec leurs exigences dans le
JSON. Les 317 contrats restants qui pointent vers un script réussi de la
première passe ne sont **pas** clôturés automatiquement : la portée de ce script
peut être uniquement parité, sélection CMake ou propriété hôte ciblée.
Les 94 autres requièrent leurs références ou une preuve distincte.

## Exécution et preuves

Première passe après correction HLE : 328 commandes de prévalidation hôte
exécutées. Un échec initial du heap provenait de l’absence de Clang 18 ; après
installation de Clang 18.1.8, son scénario complet est passé sous UBSan et
TSan, avec 480 000 opérations sur huit threads dans le scénario principal.
Les nouvelles optimisations ont ensuite passé leurs témoins ciblés et le
rejeu strict du générateur Vulkan.

Une nouvelle passe de **332 commandes**, complétée par les vérifications
ciblées après le raffinement des plages triées et du transfert HLE, est enregistrée sous
`results/batch-final-2026-10-20/summary.json`, avec un journal et un code de
sortie par commande. Le répertoire `results/` est ignoré par Git ; régénérer
l’inventaire avec la commande ci-dessus dans une nouvelle tâche.

La préparation du SDK, de FFmpeg, d’OpenGL et de RADV a réussi. Les 12 unités
RADV compilées ont reçu leur empreinte et 9 176 symboles d’implémentation ont
été isolés. La compilation et le package de l’application restent à qualifier.
Les **21 précontrôles natifs** passent après migration de leurs références
aux sources désormais maintenues (thread/TSC, assertions JIT, GPU, nvdrv,
OpenGL). Les témoins conservent leurs scénarios d’erreur et leurs contrôles
négatifs. Le témoin de cycle GPU utilise le vrai cycle maintenu : vidage des
anciennes commandes avant redémarrage et publication persistante d’une
exception du worker, plutôt que l’ancien fragment supprimé.

Le compilateur PS5 a accepté **19 unités**, émetteur A64 compris, avec les arguments du vrai
`compile_commands.json`, dont `host_memory.cpp`, la CV, le scheduler et le
query cache. Ces résultats ne constituent pas une édition de liens.
La construction complète release est lancée, avec ses options existantes :
`-O3`, ThinLTO sur les cibles prévues et `-march=znver2` sur video_core.
Les options shared/batch JIT restent désactivées. Journaux :
`results/native-preflight-2026-10-20/summary.json` et
`results/native-preflight-2026-10-20/native-syntax-19.log`.

Le niveau natif reste distinct :
pas de nouveau journal console et pas de comparaison de frametimes.
H03/H05/H06/H07 restent ouverts pour réveil → ordonnanceur → fibre/JIT →
instruction invitée ; R03/V05 attendent notamment une preuve du détenteur des
verrous et des attentes GPU réelles. Les expériences suspendues restent OFF.

## Régression de compilation A64 détectée par le build complet

Le premier build applicatif a compilé 393 étapes avant de rejeter une directive
préprocesseur insérée entre le type de retour et le nom de `A64EmitX64::Emit`.
Le `#endif` partageait aussi une ligne avec l’accolade d’ouverture. Le contrôle
de parité reproduisait exactement cette transformation invalide.

La variante standard remplace désormais la déclaration complète dans chacune
des branches. Le contrôle de parité conserve sa comparaison intégrale, mais
compile aussi les vraies frontières déclaration/définition dans les modes
normal, publish et shared ; un témoin négatif rejette l’ancienne signature.
Ce contrôle rejoint le fast gate et le contrôle natif anticipe la compilation
de l’émetteur complet. Aucun algorithme d’émission ou réglage JIT expérimental
n’est activé par cette correction. La construction reprend ses objets existants.

Le fast gate renforcé passe ses **19 contrôles** (18 en séquence, puis le nouveau
contrôle d’émetteurs après correction native). Les preuves sont conservées dans
`results/batch-final-2026-10-20/fast-final-summary.json`.

Un croisement local avec la base de compilation classe les 538 chemins du
worklist : 115 sources directes du checkout, 17 sources épinglées du cache et
77 unités sélectionnées au contenu identique. Les 329 autres chemins comprennent
notamment 197 en-têtes, 23 fragments, des variantes inactives, des outils et les
sources du pilote compilées par le build RADV séparé. Ce croisement ne déclare
aucun de ces chemins inutile ou qualifié : les dépendances d’en-têtes et les
chemins à l’exécution restent à considérer. Voir
`results/native-preflight-2026-10-20/worklist-native-selection.json`.

## Lot GPU / mémoire / intégration native supplémentaire

- Le clear DMA vérifiait l’enregistrement GPU avec un nombre de mots traité
  comme des octets. La vérification utilise toute la plage en octets ; elle
  refuse aussi les fills vides ou les tailles qui seraient tronquées par
  `FindBuffer(u32)`. Le chemin CPU existant est conservé. Le témoin compile
  les vrais `DMAClear` et `IsRegionRegistered`, reproduit le chevauchement
  tardif manqué, puis vérifie les octets GPU, les opérations de cache et le
  fallback sous ASan/UBSan. La parité complète R437 est conservée avec ce delta
  explicitement décrit dans ses deux oracles.
- Le premier build complet a révélé que l’override natif de DeviceMemoryManager
  remplaçait le backport actuel par une ancienne implémentation : `id_pool`
  n’existait plus dans son en-tête. La version native reprend maintenant tout
  le backport maintenu : atomiques de tables, protections de remappage,
  bornes physiques et registre ASID protégé sans réutilisation. La comparaison
  intégrale avec cette base autorise seulement les deux retours GetSpan décrits
  ci-dessous. Aucun manifeste de dépendance épinglée n’a été réécrit.
- Les deux vrais `GetSpan` réutilisent le numéro de page physique déjà validé.
  Cela supprime une seconde lecture atomique de la première page et les
  vérifications répétées de `GetPointer`. Le témoin démontre aussi le défaut
  précédent : un remappage entre validation et seconde recherche pouvait faire
  retourner une autre adresse physique, dont toute la plage n’avait pas été
  validée. Les variantes const/mutable, trous, remappages non contigus, bords
  virtuels/physiques et tombstones ASID passent sous ASan/UBSan. Cette propriété
  ne constitue pas un instantané atomique de toutes les pages pendant un remap.
- Les accès atomiques au bool d’interruption de PhysicalCore utilisent les
  builtins du compilateur, pris en charge par le SDK PS5. L’ABI bool et l’ordre
  relaxed restent identiques pour les lecteurs et les écrivains. Les deux
  profils maintenus et le témoin concurrent passent ; `std::atomic_ref` était
  indisponible dans ce SDK. Un include local redondant du memory manager GPU,
  devenu invalide après déplacement du fichier, a aussi été supprimé.
- Le tableau d’indices de SyncValues est dimensionné une fois pour le lot,
  au lieu de croître par `push_back`. La fusion et les copies gardent les
  résultats vérifiés précédemment.

La compilation en collecte d’erreurs a permis de traiter les deux derniers
échecs ensemble, puis de reprendre sur 13 étapes plutôt que de reconstruire
les dépendances. Le premier exécutable PS5 a été lié ; un package final incluant
le dernier changement GetSpan est en cours. Les nouvelles unités (memory
manager, PhysicalCore, instanciation DeviceMemoryManager) passent les vrais
arguments Clang PS5. Le précontrôle natif inclut désormais 22 unités.

Les vérifications restent ciblées après ces modifications : pas de relance
systématique des 332 commandes déjà exécutées. Les sept contrôles concernés
sont verts dans `native-batch-latest-summary.json`, avec les témoins DMA et
GetSpan additionnels. Les compteurs 400 / 98 / 411 restent soumis aux critères
individuels du registre, et les tests PS5 restent différés à la fin.

## Lot d’optimisation supplémentaire — contrôles hôte terminés

À la demande de l’utilisateur, les tests ont été regroupés après les modifications.
Les changements suivants sont écrits et leurs contrôles hôte ciblés passent :

- Query sync remplace les vecteurs de copies imbriqués par un tableau contigu
  et des offsets de groupes. Les copies conservent leur ordre au sein de chaque
  destination ; les vecteurs déplacés restent possédés par la commande différée.
  Le code évite une allocation par destination et préalloue les métadonnées
  avant le mutex du buffer cache. Le staging reste après la consolidation des
  buffers pour conserver son tick de durée de vie ; le callback vide ses
  anciens handles à chaque reprise après fusion. Le verrou protège toujours
  l’acquisition des buffers jusqu’à l’enregistrement de la commande. Le témoin de la méthode complète mesure
  **1 allocation au lieu de 1 024** pour les copies du premier lot, avec
  **zéro allocation de ces copies sous verrou** ; les copies de payload
  restent sous verrou. Il couvre les deux types de résultats, les lots
  différés, les chevauchements et la reprise après consolidation de buffers.
- Les probes BufferPages/ImagePages bornées lisent directement un ou deux mots
  de bitmap, avec les mêmes masques et ordres atomiques. Publication, fallback
  des plages invalides et double contrôle coverage_unknown sont conservés.
- Build PS5 : tuning Zen2 du code hôte common/core/dynarmic, sans élargir leur
  jeu d’instructions ; ISA Zen2 pour DSP/shader translation avec contraction
  mul/add désactivée. ThinLTO garde son périmètre précédent. Aucun réglage
  shared/batch JIT ou fast-math n’est activé. Aucun gain PS5 n’est encore mesuré.

Le compteur du registre est recalculé à **398 fichiers / 96 P0 / 409 contrats**
après qualification ciblée de M08 et V77. Les autres nouveaux changements ne
font pas baisser ce compteur avant leur preuve. Le build lié précédemment
précède ce lot ; son contrôle sparse post-build doit aussi être actualisé pour
reconnaître l’en-tête maintenu canonique, identique à la copie dérivée, tout en
rejetant l’ancien en-tête épinglé. Aucun package final courant n’est annoncé.

Le même lot supprime aussi les gros stockages inutilisés de `FiberImpl` :
la pile rewind de 2 Mio n’avait aucun consommateur dans l’implémentation
maintenue, et les fibres représentant des threads hôtes n’utilisent aucune
pile dédiée. La pile active de 2 Mio est maintenant allouée uniquement pour
les fibres exécutables, sans remplir ses octets à zéro ; deux canaris entourent
ce stockage. Les transferts de contexte et leur garde restent identiques.
Le témoin compile le vrai code avec les assembleurs Boost épinglés et UBSan :
128 transferts entre deux threads passent, avec canaris et sortie préservés.
Les grandes allocations mesurées passent de 4 194 472 à 2 097 160 octets
pour la fibre invitée ; les deux fibres hôtes passent de 8 388 944 à zéro.
Ces valeurs mesurent les allocations demandées, pas le RSS en jeu.

Les **20 contrôles ciblés du lot sont verts**. La première passe en avait
18 verts ; deux fixtures ont été corrigées (liaison C/C++ du témoin de fibres
et marqueur d’extraction de l’ancien query cache), puis ces deux contrôles
ont été rejoués. Les journaux sont dans
`results/optimization-final-2026-10-20/summary.json` et `rerun-summary.json`.
Une seule compilation native finale est lancée pour les options CPU, les
bitmaps, les fibres et le query cache ; elle inclut 23 unités de précontrôle
syntaxique et le contrôle sparse corrigé. Les résultats matériels restent
réservés au test PS5 final.

Le précontrôle Clang avec les vrais arguments PS5 a terminé : **23/23 unités
acceptées**, fibres et query cache actuels compris. La compilation complète
et les contrôles post-build restent en cours.

## Complément GPU — regroupement des invalidations dirty

`GPUDirtyMemoryManager::Gather` reconstitue les plages contiguës qui avaient
été divisées en masques de 2 Kio par le producteur. Il conserve l’ordre, les
trous et les doublons ; aucune allocation, aucun tri ni verrou n’est ajouté.
Chaque appel est limité à 256 Kio, borne du probe ImagePages, pour conserver
son filtrage et borner le travail des caches par appel. Les plages commençant
à zéro restent séparées : les deux rasterizers ignorent explicitement ces
invalidations et leur fusion ne doit pas absorber une plage non nulle.

Le témoin compile les classes complètes épinglée et maintenue sous ASan/UBSan.
Pour 2 Mio contigus, il mesure **1 024 → 8 appels**, puis compare exactement
la séquence de cellules couvertes sur 8 192 écritures dispersées, avec trous,
retours en arrière, doublons et filtrage de l’adresse zéro. Les collectes
vides, les époques successives et une écriture depuis le callback sont couvertes.
L’oracle intégral et le scénario concurrent de masque déplacé sont conservés.
Les trois contrôles du complément passent dans
`results/gpu-dirty-gather-2026-10-20/`. Le fast gate et la prévalidation incluent
le nouveau témoin. Le compteur reste **398 / 96 / 409** : M09 exige encore
une preuve aux frontières réelles des caches, sans gain FPS PS5 revendiqué.
