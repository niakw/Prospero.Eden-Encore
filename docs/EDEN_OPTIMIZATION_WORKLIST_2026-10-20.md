# Eden Encore — compteurs d'optimisations (≠ validation)

**20 octobre 2026 — premier lot d'optimisation dédié.**

Le registre existant recense **538 chemins inventoriés** (491 fichiers de code directement maintenus, plus 47 chemins épinglés hors du périmètre des corrections directes ; 83 des fichiers maintenus sont hors du graphe central). Ces nombres ne correspondent ni à
491 fichiers à optimiser, ni à 397 fichiers « restants à optimiser ».
Les 397 en attente sont une *dette de preuve*.

## Comptage explicite des corrections de code

Ne compter comme **reste à optimiser identifié** que les fichiers pour
lesquels un **coût évitable réel a été localisé dans le code** et pour lesquels
un changement précis est possible. La preuve hôte est conservée à part.
Un défaut de gameplay dont le propriétaire exact est inconnu
n'autorise **pas** de multiplier arbitrairement le nombre de fichiers.

| Lot | Chemins identifiés à modifier | Chemins corrigés par ce lot | Restants dans ce lot |
| --- | ---: | ---: | ---: |
| Publication du fence du worker GPU (deux variantes natives) | **2** | **2** | **0** |

### Les deux corrections

- `vendor/encore-active/eden-gpu/gpu_thread_quiet.cpp`
- `vendor/encore-active/eden-gpu/gpu_thread_dev.cpp`

Dans `ThreadManager::RunWorker`, chaque commande GPU terminée écrivait
son numéro de fence au moyen d'un `atomic::store` implicite
`memory_order_seq_cst`. Or les consommateurs existants lisent le numéro
avec `memory_order_acquire`. Un store `memory_order_release`
assure la publication de tous les effets de commande antérieurs
vers ces lectures sans imposer l'ordre global `seq_cst` :
sur une architecture x86, cela peut éviter une opération de
synchronisation globale coûteuse sur le chemin fréquent des commandes.

Le worker ne change ni l'ordre FIFO, ni le numéro de fence, ni les waits,
ni les notifications `condition_variable_any`, ni le stop/restart.
**Ce n'est pas** une démonstration d'augmentation FPS ou de guérison du gel.

`tools/check-native-gpu-fence-release-publication-host.py` compile les
fragments C++ réels de publication des deux variantes plus la
publication upstream en contrôle. 32 768 commandes sont consommées par
un thread indépendant sous ASan/UBSan, en vérifiant l'ordre et
la visibilité des écritures associées au numéro publié.
La comparaison historique `tools/check-native-gpu-thread.py` est
normalisée spécifiquement pour cette amélioration, sans réduire ses
autres assertions de parité.

**À ne pas tromper :** le nombre *global* de fichiers où une future
optimisation s'avérera nécessaire est **encore inconnu** sans examen
effectif de l'ensemble de la cartographie (491 chemins maintenus ; 538 avec les chemins épinglés). Ce document
présente un chiffre exact et vérifiable **pour les besoins identifiés**,
et non un faux « reste = total des fichiers non validés ».

## Couverture d'optimisation de code — compteur principal de traitement

Au HEAD `05846723c` (optimisation GPU `db6b6a6` et réparation CI `0584672`), l'inventaire versionné `tools/audit-cloud-worklist.py` recense **491 sources/en-têtes maintenus** (et 47 chemins épinglés additionnels, soit 538 inventoriés) sous `headless/`, `src/`, `vendor/encore-active/`. Par comparaison GitHub avec `82c531d08` : **23 chemins de code réellement modifiés**, sans prétendre qu'ils sont tous des gains de performance. Les revues P0 antérieures ajoutent **12 chemins actifs examinés sans modification** (13 chemins recensés, dont un recouvert par les 23), et la nouvelle [revue de six chemins GPU/Mesa](EDEN_OPTIMIZATION_REVIEW_MESA_VULKAN_2026-10-20.md) ajoute **6 chemins sans nouveau correctif**.

**Couverture effective : 41 fichiers de code traités/examinés ; reste à traiter dans le chantier d'optimisation : 450 fichiers (491 − 41).**

Cette mesure est un **compteur de travail d'optimisation**, pas de validation. Chaque nouveau fichier analysé pour ses points chauds ou corrigé une seule fois doit être ajouté au [manifeste des propriétaires](EDEN_OPTIMIZATION_COVERAGE_2026-10-20.json) : il fait alors baisser le compteur même s'il ne nécessite pas de patch. Cela évite de fabriquer des optimisations inutiles simplement pour faire diminuer un chiffre. Le nombre de fichiers qui **nécessitent impérativement un changement C++** reste inconnu jusqu'à leur diagnostic. Contrôle CI : `python3 -B tools/check-eden-optimization-coverage.py`.

## Accélération — sources déjà couvertes par des travaux antérieurs

**Lot du 20 octobre — sans nouveau patch moteur.** L'inventaire a recoupé
le manifeste de 41 chemins avec le registre central. **61 chemins distincts**
supplémentaires de `vendor/encore-active` disposent d'une attribution
historique explicite : **35** contrats `HOST` ciblés (tests/parité
ou propriétés précises) et **26** unités sources complètes déjà
maintenues, backportées ou sélectionnées (`SOURCE`; niveau de preuve
hôte et console non nécessairement atteint).

Ces 61 chemins n'ont **pas** été déclarés « FPS optimisé ».
Ils ont été retirés de la **première analyse de code à refaire**,
parce que leur propriétaire, leur intervention passée et une référence
de preuve sont déjà consignés. Tout nouveau défaut documenté rouvrira
le chemin pertinent sans cacher le problème.

| Comptage optimisation de code | Précédent | Maintenant |
| --- | ---: | ---: |
| Sources/en-têtes maintenus directement par Encore | 491 | 491 |
| Déjà modifiés ou examinés dans la passe récente | 41 | 41 |
| Revus par réception hôte existante | 0 | **35** |
| Revus par source déjà intégrée avec justificatif | 0 | **26** |
| **Restent à traiter dans la passe** | **450** | **389** |

**Ce nombre 389 n'est pas le nombre de correctifs nouveaux prouvés
nécessaires.** Le registre de qualification SOURCE/OPEN n'a pas changé.
Le contrôle CI exige que chacun de ces 61 chemins conserve son ID,
son statut et sa référence de preuve historique dans
`docs/EDEN_CORE_AUDIT_DEPENDENCIES.md`.
Le nombre de nouvelles modifications de code obligatoires demeure
inconnu avant diagnostic des sources non traitées.

## Réception rapide des backports de production déjà modifiés

**Nouveau lot : 78 fichiers déjà intégrés** sous
`vendor/encore-active/eden-backports/src/`, dont les fichiers C/C++
et en-têtes GPU, texture, synchronisation, IPC, réseau, audio et services.
Ils étaient absents du manifeste de progression mais pas du code produit.

Critères **cumulatifs** de sortie de la première revue : chemin source
exact référencé par un contrat `SOURCE` ; présence dans le manifeste
des **83 entrées de production** (81 fichiers C/C++ et 2 recettes CMake) ;
SHA256 actif distinct de l'empreinte amont ; empreinte et taille des
**78 fichiers** recontrôlées sur les véritables octets du dépôt lors de
chaque fast gate et prévalidation complète ; commit amont
`5f142c7926d0c7fcbbd0ce30794d72f638a43b2a` épinglé dans les
deux manifestes.

Les 78 ne sont **pas** de nouvelles optimisations de cette session :
ce sont des modifications de production **déjà reçues** et déjà
suivies par les vérifications de préparation / réception du fork.
Ne pas les classer `HOST` ni `FPS` : aucune qualification
matérielle n'est impliquée.

| Suivi du traitement du code | Avant | Après |
| --- | ---: | ---: |
| Sources maintenues | 491 | 491 |
| Fichiers traités ou changements existants reconnus | 102 | **180** |
| **Fichiers restant à examiner pour optimiser** | **389** | **311** |

Les fichiers concernés restent surveillés pour les bugs et les
régressions réels ; seul leur *premier tri d'optimisation* est évité.

## Réception accélérée des unités C++ maintenues et vérifiées historiquement

Le registre architectural permet de reconnaître **78 autres sources
distinctes** possédant déjà une intervention Encore (source complète,
variante de build ou ancien générateur CMake remplacé) et un témoin
source/parité **lancé dans la prévalidation CI**. Aucun nouveau patch
moteur n'est nécessaire pour répéter leur première étude.

Les variantes `DEV`, `OFF` et simplement préparées sont enregistrées
séparément comme `optional_or_staged` dans le manifeste ; ceci ne
prouve ni sélection en version normale ni optimisation GPU réelle.
Chaque chemin conserve son identifiant de contrat et sa preuve CI,
dont la présence est surveillée par
`tools/check-eden-optimization-coverage.py`.

| Suivi de la passe d'optimisation | Avant | Après |
| --- | ---: | ---: |
| Code maintenu recensé | 491 | 491 |
| Fichiers déjà traités / profil conservé | 180 | **258** |
| **Restent à traiter dans la passe** | **311** | **233** |

**Aucun contrat HOST ajouté. Aucune amélioration FPS PS5 affirmée.**

## Vulkan — deux fichiers corrigés pour publication de pipeline

Les fonctions graphiques et compute utilisaient déjà
`is_built.store(true, release)`, mais l'entrée *ready* de leurs chemins
`Configure` réalisait `load(relaxed)` et pouvait donc **sauter tout
verrou/acquire** avant l'accès à l'objet pipeline construit sur
un autre thread. Les deux chemins utilisent maintenant
`load(acquire)` et conservent le protocole existant en cas
de construction inachevée, sans verrou supplémentaire sur le
chemin déjà prêt.

Le témoin `tools/check-vulkan-pipeline-ready-publication-host.py`
relit les deux sources et exécute le chemin ready/wait sur un
payload non-atomique de test sous ASan/UBSan. Cette correction
vise la sûreté des pipelines et les potentiels états transitoires
GPU ; **aucun gain FPS ni guérison de freeze PS5 n'est encore démontré**.

Un fichier compute nouveau est pris en charge dans ce lot ; le
fichier graphics figurait déjà dans la revue des six sources.
**Optimisation restant à traiter : 232 sur 491 (259 pris en charge).**

## Lot de 20 sources natives déjà installées — RADV / Vulkan / SurfaceFlinger

Le registre d'optimisation reconnaît **20 chemins maintenus** déjà
propriétaires d'une implémentation sélectionnée et d'un contrôle de
contenu exécuté en CI : 6 unités RADV installées depuis la liste
exacte des 12 sources (`tools/install-vendored-radv.py`),
13 unités Vulkan du fork intégralement copié et vérifié par
`tools/check-vendored-vulkan-fork.py`, et une source SurfaceFlinger
installée depuis son commit Eden épinglé.

Les chemins RADV OpenCL `.cl` continuent d'être suivis dans le graphe
et le catalogue `vendor/encore-active`, mais ne sont actuellement
**pas inclus** dans le périmètre strict des 491 fichiers `.c/.cpp/.h`
et assimilés. La livraison sélectionnée ne garantit pas un gain FPS :
ces 20 fichiers sont classés « code existant à ne pas réétudier
sans nouveau défaut » et non « 20 optimisations réalisées maintenant ».

**Indicateur principal de la passe : 279 fichiers déjà pris en charge
sur 491 ; 212 fichiers à traiter dans l'optimisation**. Ce sont des
sources à trier, pas 212 correctifs nécessaires.

## 21 octobre — dix propriétaires natifs déjà examinés

Voir [EDEN_HEADLESS_RUNTIME_OPTIMIZATION_REVIEW_2026-10-21.md](EDEN_HEADLESS_RUNTIME_OPTIMIZATION_REVIEW_2026-10-21.md). Les dix sources `U02`–`U11` ont été lues directement, en distinguant leurs fast paths déjà présents et leurs fonctions seulement utilisées au démarrage, à l'arrêt ou en cas de crash. Sans anomalie de performance reproduite sur ces sources, aucun patch C++ additionnel n'a été créé. **289 sur 491 fichiers traités ; 202 restent à traiter pour l'optimisation.**

## 21 octobre — accélération des fragments historiques et profils désactivés

**19 fichiers maintenus supplémentaires** disposent d'un propriétaire exact
et d'un témoin exécuté par la CI : 5 fragments d'oracle Vulkan utilisés
uniquement pour reproduire le fork, 2 fragments du générateur scalaire
Dynarmic (dette CMake à surveiller), 9 unités du pont GPU différé
désactivé, 2 unités mémoire natives maintenues et 1 fragment de diagnostic
OpenGL DEV.

Ces chemins sont examinés pour leur **pertinence de performance dans le
profil livré**, pas déclarés « optimisations FPS ». L'expérience GPU différée
reste **OFF** ; le statut d'un fragment de génération n'est pas un correctif
du moteur. Tous les contrats originaux et scripts de preuve demeurent vérifiés.

**Avancement du chantier : 308 fichiers traités ou qualifiés pour le tri
sur 491, 183 fichiers restant à traiter pour l'optimisation.**
Le compteur de nouvelles corrections obligatoires reste à établir à mesure
de l'identification de véritables points chauds.

## Revue native et périmètre prioritaire (21 octobre)

[EDEN_NATIVE_POLICY_OPTIMIZATION_REVIEW_2026-10-21.md](EDEN_NATIVE_POLICY_OPTIMIZATION_REVIEW_2026-10-21.md) enregistre 16 fichiers natifs lus et leurs témoins CI. **324 / 491 traités ; 167 encore à examiner.** Parmi eux, 62 relèvent du frontend `headless/prosperoeden/` (hors `runtime_shims.cpp`, commun à tout l'exécutable) et sont suivis séparément. **105 sources moteur et infrastructure native** (dont `runtime_shims.cpp`) composent la file prioritaire CPU/JIT/GPU/HLE et infrastructure native ; elles ne sont pas 104 correctifs C++ confirmés.

## 21 octobre — huit politiques GPU/mémoire déjà optimisées

[EDEN_GPU_MEMORY_POLICY_REVIEW_2026-10-21.md](EDEN_GPU_MEMORY_POLICY_REVIEW_2026-10-21.md) contient l'inspection ciblée de huit chemins (direct pool, budgets GC, capacity latch, write-ahead et régions dirty) et leurs propriétaires CI. Aucun patch C++ supplémentaire n'est justifié sans nouvelle panne reproductible. **332 / 491 traités ; 159 restants dans le périmètre complet, dont 97 moteur/runtime prioritaires et 62 lanceur séparé.**

## 21 octobre — 16 entêtes / politiques natifs examinés sans nouveau patch

Voir [EDEN_NATIVE_HOTPATH_FAST_REVIEW_2026-10-21.md](EDEN_NATIVE_HOTPATH_FAST_REVIEW_2026-10-21.md). La revue a lu les politiques JIT, l’analyse SMT, l’observabilité GPU/HLE, les guards de défaut et le watchdog de sortie. Ces fonctions et headers disposent déjà de chemins bornés ou ne sont utilisés qu’en DEV/initialisation. Chaque source est verrouillée par son Git blob d’origine, contrôlé en CI. **348/491 fichiers pris en charge ; 143 restants (81 moteur + 62 lanceur).** Aucune retouche spéculative sur CPU/JIT/GPU n’a été engagée ; le nombre de nouvelles modifications réellement requises n’est pas confondu avec le reste à examiner.

## 21 octobre — accélération contrôlée des sources de lancement et de diagnostic

Voir [EDEN_NATIVE_STARTUP_DIAGNOSTIC_REVIEW_2026-10-21.md](EDEN_NATIVE_STARTUP_DIAGNOSTIC_REVIEW_2026-10-21.md). 20 nouveaux chemins revus et attachés à leurs empreintes Git et contrats ; aucune modification C++ speculative. **368/491 pris en charge, 123 restants (61 moteur et infrastructure, 62 lanceur).** Les chemins CPU/JIT/HLE/GPU critiques restent prioritaires même si les headers de diagnostic, de préférences et de sondes DEV sont désormais couverts par leur revue de code.

## 21 octobre — douze sources natives auxiliaires examinées

Voir [EDEN_NATIVE_LIGHTWEIGHT_SOURCE_REVIEW_2026-10-21.md](EDEN_NATIVE_LIGHTWEIGHT_SOURCE_REVIEW_2026-10-21.md). Les trois exécutables de test indépendants, deux profils constexpr générés, l'API d'élévation démarrage, le pont d'allocation native et le contrôle du ZBIC ne justifient aucun nouveau patch en l'absence d'un défaut mesuré. **380/491 pris en charge : 111 restants, dont 49 moteur et 62 lanceur.** Tous les examens sont verrouillés par empreinte Git ; les propriétaires JIT, HLE et GPU restent à traiter sans assimilation à la validation matérielle.

## 21 octobre — compteur moteur corrigé et lot de douze sources

Le compteur principal **exclut les 62 unités de l'interface du lanceur** `headless/prosperoeden/`. L'exception `runtime_shims.cpp` reste du côté moteur : elle définit des fonctions libc/pthread globales effectivement liées dans chaque application native. Au HEAD `f73075323`, la revue [EDEN_NATIVE_NON_HOT_OPTIMIZATION_REVIEW_2026-10-21.md](EDEN_NATIVE_NON_HOT_OPTIMIZATION_REVIEW_2026-10-21.md) examine sept sources de tests hôte, deux fichiers du helper de démarrage et trois composants GPU différés maintenus OFF. **392/491 traités ; 37 moteur/runtime à traiter ; 62 lanceur suivis séparément ; 99 globalement.** Ne pas présenter les 62 comme des sources du moteur à optimiser, ni les 12 comme de nouvelles optimisations FPS.

## 21 octobre — configuration, métadonnées, sauvegardes et sondes

La [revue de quatre unités natives](EDEN_NATIVE_CONFIG_METADATA_REVIEW_2026-10-21.md) vérifie les chemins de settings, imports de sauvegardes, métadonnées et watch DEV. Ces opérations sont associées aux actions de configuration/lancement ou à des sondes explicitement activées, pas à la boucle normale par frame. Chaque chemin reste verrouillé par son Git blob. **396/491 fichiers pris en charge, 33 moteur/runtime encore à traiter, 62 UI du lanceur séparés, 95 globaux.** Zéro correctif moteur ajouté à cette revue.

## 21 octobre — mémo vertex Vulkan + quatre chemins natifs

Voir [EDEN_NATIVE_REMAINING_ENGINE_REVIEW_2026-10-21.md](EDEN_NATIVE_REMAINING_ENGINE_REVIEW_2026-10-21.md). Correction du mémo de reconnaissance des vertex shaders alternants dans la source Vulkan active et son générateur, avec extension du test hôte existant. Quatre chemins conditionnels (rafraîchissement, budget JIT, liste JIT expérimentale, NPad DEV) examinés sans patch. **401/491 traités, 28 moteur/runtime à examiner, 62 lanceur séparés, 90 globalement.** Une amélioration ciblée source, aucun gain FPS ou freeze console encore prouvé.

## 21 octobre — mapping JIT RX/RW et quatre revues

Voir [EDEN_JIT_ALIAS_LOOKUP_OPTIMIZATION_2026-10-21.md](EDEN_JIT_ALIAS_LOOKUP_OPTIMIZATION_2026-10-21.md). Cache multi-entrées par thread et invalidation générationnelle dans l'allocateur JIT natif ; témoin C++ ASan/UBSan dans la prévalidation. Quatre chemins audio/assert/loader lus sans nouveau correctif. **406/491 traités ; 23 moteur/runtime à traiter ; 62 lanceur séparés ; 85 globalement.** Tests hôte et console restent des preuves indépendantes.

## 21 octobre — journal natif silencieux

Voir [EDEN_NATIVE_QUIET_LOG_REVIEW_2026-10-21.md](EDEN_NATIVE_QUIET_LOG_REVIEW_2026-10-21.md). Le formatage des messages sans backend actif est court-circuité dans le build natif, avec contrôle ASan/UBSan off/on/off. **407/491 pris en charge ; 22 fichiers moteur/runtime encore à traiter ; 62 UI du lanceur séparés ; 84 globalement.** Aucun FPS console prouvé.

## 21 octobre — mutex slab HLE / ABI / IPC cold-path

Voir [EDEN_HLE_SLAB_AND_RUNTIME_REVIEW_2026-10-21.md](EDEN_HLE_SLAB_AND_RUNTIME_REVIEW_2026-10-21.md). Modification ciblée de `k_slab_heap.h` : accès atomiques relaxed sous mutex déjà exclusif, avec test hôte multithread ASan/UBSan. Revue conservatrice de quatre sources (fastmem ABI, runtime C global, contrôleur audio et gestion des applications). **412/491 traités ; 17 moteur à examiner ; 62 UI séparés ; 79 globalement.** Aucun FPS PS5 qualifié.

## 21 octobre — trois accès à l'index du slab corrigés

Voir [EDEN_HLE_SLAB_INDEX_FIX_2026-10-21.md](EDEN_HLE_SLAB_INDEX_FIX_2026-10-21.md). `slab_helpers.h` appelait des méthodes/expressions non cohérentes avec le contrat du heap maintenu dans trois `GetSlabIndex`. Alignement sur `kernel.SlabHeap<Derived>().GetObjectIndex` ; test d'instanciation compilée C++20 ASan/UBSan ajouté à la CI. **413/491 traités ; 16 fichiers moteur/runtime à traiter ; 62 du lanceur séparés ; 78 globalement.** Correctif de robustesse, pas gain FPS déclaré.
