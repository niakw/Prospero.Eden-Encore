# Cloud source audit — 20 octobre 2026

Branche `dev/ps5-sparse-jit`, base `82c531d08641d8b28124bd2cebf37fcf85674179`.
Les preuves de cette passe proviennent de contrôles locaux ; elles ne constituent
pas une CI distante ni un binaire PS5 qualifié.
**Compteur courant : 398 fichiers / 96 P0 / 409 contrats.**
Les chiffres 400 / 98 / 411 ci-dessous décrivent le relevé initial.

**Dernier lot publié : `7ab0279711` — hôte, rejeu et paquet natif vérifiés.**
Les deux listes de métadonnées de résultats GPU sont recyclées après consommation
par `SyncValues`, qui possède les copies différées. Le témoin extrait les fragments
réels de préparation/conversion/recyclage et toute la méthode `SyncWrites` :
**820 → 0 allocations des deux listes après amorçage sur 128 lots**, métadonnées, ordre d’envoi
et drapeaux identiques sous ASan/UBSan. Il couvre aussi lots vides, appels répétés,
remplacement avant consommation et trois exclusions de pilotes. La preuve de
possession des copies de `SyncValues` reste assurée séparément par son vrai code.
Chaque liste garde sa capacité maximale jusqu’à destruction du streamer ; les
premières allocations et agrandissements ne sont pas supprimés.
Les six contrôles ciblés passent, ainsi que le rejeu exact du fichier modifié
(les quatre différences historiques non concernées sont conservées).
Preuves locales : `results/samples-scratch-batch-2026-10-20/host-summary.json`
et `replay-verified.json`. Compteurs **398 / 96 / 409**, sans preuve console ajoutée.

Le build release et le paquet de `7ab02797110aeb260b547d299452680fb7a56bca` passent après sept étapes
incrémentales, avec le SHA retrouvé dans l’ELF. Tous les contrôles après compilation
restent activés et passent : sparse 379 objets, verrou JIT 200 000 opérations et
code machine, RADV/OpenGL/ABI, inventaire du paquet, imports, alignement et intégrité.
`eboot.bin` : `c912b54adbb3b23d0382df5155de6c94483c64d45bba8cb29904bab8fa4c57e7`.
Journal : `/workspace/shared/eden-native-package-samples-scratch.log` ; preuve :
`results/samples-scratch-batch-2026-10-20/native-package.json`. Aucun build actif.

**Lot TFB précédent : `0b3e0436e5` — hôte, rejeu et paquet natif vérifiés.**
La synchronisation des compteurs transform feedback utilise directement le
résultat d’insertion dans la table des banques, supprimant une recherche par
requête retenue. Vraie méthode extraite, vraie table Boost et hasher instrumenté
à valeurs identiques : **2 048 → 1 024 appels** pour 1 024 requêtes d’une banque,
**2 077 → 1 053** pour 32 banques, réorganisations de table incluses. Sept
scénarios ASan/UBSan préservent ordre et données d’envoi, drapeaux, filtres et
fermeture vide. Les cinq contrôles ciblés passent ; le rejeu reproduit exactement
le fichier modifié, avec les quatre écarts historiques non concernés conservés.
Preuves : `results/tfb-lookup-batch-2026-10-20/host-summary.json` et
`replay-verified.json`. Les compteurs restent **398 / 96 / 409**. Le témoin ne
qualifie ni la progression GPU réelle ni les frametimes PS5.

Le paquet natif de `0b3e0436e51f33c03ca2cf731e9802dffdf34b6b` passe après sept étapes incrémentales,
avec le SHA retrouvé dans l’ELF et tous les contrôles après compilation activés :
sparse 379 objets, verrou JIT 200 000 opérations/code machine, RADV/OpenGL/ABI,
inventaire du paquet, imports, alignement et intégrité. Aucun build actif.
`eboot.bin` : `9e17c2abe27b182d1933ce74f917cce636a804ae0233bde099e8fb1133b6fb77`.
Journal : `/workspace/shared/eden-native-package-tfb-lookup.log` ; preuve :
`results/tfb-lookup-batch-2026-10-20/native-package.json`.

**Lot présentation précédent : `67c0a42c55` — hôte et paquet natif vérifiés.**
Les constantes, descripteurs et pipelines de chaque couche partagent une liste
possédée par la commande différée. Sa première entrée est stockée sans tas :
**6 → 0 allocations** pour une couche ; **6 → 1** pour 2/8/32 couches dans le témoin.
La vraie méthode `Draw` et les vrais blocs de commandes passent ASan/UBSan avec
comparaison exacte des commandes/données, trois images différées et quinze
configurations de couches/HUD, y compris suppression avant exécution des données
appelantes, débordement et réemploi du bloc. Le premier essai du témoin a buté sur
les initialiseurs Vulkan partiels existants ; sa politique de warnings a été
alignée sur celle du build natif. Les cinq autres contrôles ciblés passent.
Le rejeu depuis les backports natifs reproduit exactement le propriétaire modifié ;
les quatre écarts historiques non concernés restent inchangés. Voir
`results/present-storage-batch-2026-10-20/host-final-summary.json` et `replay-verified.json`.
Les compteurs restent **398 / 96 / 409** ; les pixels GPU réels et frametimes PS5
ne sont pas qualifiés par ces comparaisons de commandes hôte.

Le build release et le paquet de `67c0a42c55421b69408ded6826d20c196df5da3d` passent après sept
étapes incrémentales. Tous les contrôles après compilation restent activés :
sparse 379 objets, verrou JIT 200 000 opérations et code machine, liaison
RADV/OpenGL/ABI, inventaire, imports, alignement et intégrité. Le SHA est
présent dans `build/headless-native/eboot.elf`. Aucun build actif.
`eboot.bin` : `d118347e18735bd4e5d666dade2d9021af2d25a1723941a9b8071f1a58833361`.
Journal : `/workspace/shared/eden-native-package-present-storage.log` ; preuve :
`results/present-storage-batch-2026-10-20/native-package.json`.
Depuis la reprise `82c531d`, 19 fichiers C/C++ maintenus/headless/src ont changé
(correctifs, optimisations et variantes) ; les lots textures/audio et présentation
concernent trois de ces propriétaires. Le compteur de qualification reste 398 / 96 / 409.

**Lot textures/audio précédent : `fa30dc23e4` — hôte et paquet natif réussis.**
Deux propriétaires maintenus changent. Les décalages des mipmaps ASTC décompressés
et BCn incluent la profondeur ; les anciennes branches se recouvraient en 3D.
Le témoin compile la vraie méthode avec des décodeurs substitués qui écrivent
la taille volumique attendue : il démontre la disposition des sorties, pas la
qualité des pixels décodés. Les tableaux 2D et sorties recompressées BC1/BC3
conservent leur disposition. Les lectures du réglage de recompression passent
de trois à une pour trois mips, et restent nulles pour une conversion vide.

L’upmix audio conserve un vecteur par thread producteur au lieu de le réallouer
à chaque bloc. Le témoin utilise la vraie méthode et le vrai ring PCM : deux
producteurs, quatre paires de canaux, deux volumes et bouclage du ring, avec
**512 allocations supprimées sur 512 blocs d’upmix après amorçage**, PCM identique
et ordre de publication inchangé. La première allocation et les agrandissements
restent nécessaires ; la capacité maximale est retenue jusqu’à la fin du thread.
Les deux témoins ASan/UBSan et cinq contrôles de parité/inventaire/syntaxe passent.
Résultats locaux : `results/texture-audio-batch-2026-10-20/host-summary.json`.
Les workflows rapide et exhaustif les intègrent. **398 / 96 / 409** restent ouverts
à la qualification : ces preuves ne mesurent ni les frametimes PS5 ni les gels.

Le build release et le paquet natif de `fa30dc23e4c77af12d0b7d671e0d28282b7c295e` passent,
après neuf étapes incrémentales, avec tous les contrôles après compilation
activés : sparse 379 objets, verrou JIT 200 000 opérations/code machine,
RADV/OpenGL/ABI, inventaire, imports, alignement et intégrité du paquet.
Le SHA source a été retrouvé dans `build/headless-native/eboot.elf`.
`eboot.bin` : `09d495e4112243866899e044e1398700bbf28cdb1a95b42d087f8dac2baad650`.
Journal : `/workspace/shared/eden-native-package-texture-audio.log` ; preuve :
`results/texture-audio-batch-2026-10-20/native-package.json`. Aucun build actif.
Le test PS5 reste différé à la fin ; aucune CI distante n’est qualifiée ici.

**Lot GPU précédent : `033bff0b4f` — paquet natif validé hors console.**
Les trois unités Vulkan et la provenance ont été reconstruites en neuf étapes
incrémentales. Les contrôles après compilation et du paquet passent ;
le SHA `033bff0b4f515503fcbc612ce5f9ceb2a7655714` est présent dans l’ELF.
`eboot.bin` : `b9bf16cb80b8f29a1887c146e62495df6ecdb65e70ebd610ffef162cd3843270`.
Journal : `/workspace/shared/eden-native-package-deferred-copy.log` ; preuve :
`results/gpu-copy-batch-2026-10-20/native-package.json`. Le build précédent
ci-dessous est conservé comme historique. Aucun test PS5 ou résultat CI distant
n’est déduit de ces résultats locaux.

**État local du premier lot : build release et paquet réussis sur
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

## Suite — propriété des métadonnées de transfert GPU

Trois sources sont modifiées : `vk_buffer_cache_cost.cpp`,
`vk_texture_cache_cost.cpp` et `vulkan_query_cache.cpp`. Les captures des sept
chemins de copie de buffers, copie d’images, upload normal/MSAA et download
normal/MSAA prennent la propriété des vecteurs. Les commandes gardent donc
leurs données pendant l’exécution différée sans recopier leurs allocations.
Les deux chemins multi-destination réservent leurs conteneurs avant la boucle.
La réserve initiale des résultats de samples devient
`min(num_slots_used, pending_sync.size())` : chaque requête fournit au plus
un résultat, et le nouveau plafond n’augmente jamais l’estimation précédente.
Aucun transfert, ordre de commande, barrière, tick ou attente n’est supprimé.

Le nouveau témoin compile les captures réelles, les classes et les méthodes
Record/ExecuteAll du scheduler avec Boost et les types Vulkan épinglés. Sous
ASan/UBSan, il détruit les conteneurs appelants avant de rejouer les commandes,
force la reprise après débordement, vérifie les octets et recycle les blocs.
Pour les scénarios au-delà du stockage inline, chaque capture simple passe
de **1 à 0 allocation**, et chacun des deux scénarios imbriqués de **33 à 0**.
Ces chiffres portent uniquement sur la capture/enregistrement de métadonnées,
ni sur les allocations de ressources GPU ni sur les FPS PS5.

Les témoins existants de SyncValues, consolidation, inventaire et syntaxe
Python passent. Le rejeu part de la source après backports natifs, comme le
build, et reproduit exactement les trois unités modifiées. Comparaison de
41 sorties avant/après : quatre écarts préexistants et inchangés restent dans
l’ancien rejeu (HUD SPIR-V/en-tête généré et deux en-têtes de pipelines) ;
ils sont consignés dans `results/gpu-copy-batch-2026-10-20/replay-verified.json`.
La tentative initiale sur le snapshot brut est conservée séparément : elle
ne représente pas l’entrée backportée du build natif. Les sorties de ce rejeu
historique ne remplacent pas les propriétaires C++ compilés.

Le nouveau témoin rejoint les deux workflows. Les compteurs restent
**398 fichiers / 96 P0 / 409 contrats** ; la nouvelle compilation native est
regroupée après le lot, et le test PS5 reste reporté à la fin.

La validation native de cette suite a terminé : neuf étapes incrémentales,
contrôles sparse et verrou JIT, liaison RADV/OpenGL et ABI, puis inventaire,
imports, alignement et intégrité du paquet sont verts. Le nouveau paquet
remplace localement celui de `615510b20e` ; aucun build ne reste actif.
