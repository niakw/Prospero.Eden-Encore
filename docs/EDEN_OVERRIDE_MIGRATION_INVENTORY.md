# Eden Encore — inventaire des transformations CMake encore actives

**Branche :** `dev/ps5-sparse-jit`. **Dernière revue :** 19 octobre 2026.

Ce document inventorie **les appels restants à `write_derived()` dans
`headless/CMakeLists.txt`**, dans leur ordre réel. Il ne confond pas
les appels statiques avec les fichiers physiques : une cible comportant une
variable (`bits`, `unit_name`, etc.) peut produire **plusieurs fichiers**.
Toutes les variantes ne sont pas compilées au même moment ; le profil
développement, les options JIT expérimentales, les backends et le build
natif sélectionnent chacun leur sous-ensemble.

L'inventaire complémentaire `docs/EDEN_ACTIVE_SOURCE_CATALOG.md` suit les
fichiers de code et en-têtes dans `vendor/encore-active`,
y compris les backports de production et la dépendance graphique. Cette
couverture ne s'additionne pas aux sites de génération CMake ci-dessous.

## Synthèse vérifiable

- **1 appel générateur** encore dans CMake ; contre **75 avant**
  les migrations de `fs_i_file.cpp`, `fs_i_storage.cpp`, `fs_i_filesystem.cpp`, `nvhost_ctrl.cpp` et `buffer_queue_producer.cpp`, puis `service.cpp` et `svc_ipc.cpp`. Le corps de la fonction utilitaire
  `write_derived` n'est pas compté comme une invocation.
- **Garde-fou de non-régression renforcé (19 octobre 2026) :**
  `tools/check-vendor-consolidation-debt.py` limite désormais les sites
  de génération du CMake principal à l'unique destination G23
  recensées ci-dessous. Son plafond descendant est de **1** génération,
  **4** lectures et **2** remplacements après déduction des exceptions
  déjà justifiées ; il ne permet plus le retour aux budgets historiques.
  G23 reste une ressource GLSL, non une réécriture du moteur. Le module
  expérimental de pont différé ne génère plus de C++ ; le module
  Shared JIT ne fait plus que sélectionner les sources Encore.
- **4 lectures `file(READ`** et **2 remplacements
  `string(REPLACE`**, incluant certains usages de configuration ordinaires,
  pas seulement des réécritures de C++.
- Les versions diagnostiques de `IFile::Read`, `IStorage::Read` et des appels
  `IFileSystem::{OpenFile,OpenDirectory,GetEntryType}` sont
  maintenant des sources maintenues dans `vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp/`.
- L'attente hôte de syncpoint `nvhost_ctrl::IocCtrlEventWait` est également
  maintenue dans `vendor/encore-active/eden-core/src/core/hle/service/nvdrv/devices/`,
  et non générée par CMake. La politique de diagnostic reste inchangée.
- L'attente de slot de présentation `BufferQueueProducer::DequeueBuffer`
  utilise désormais la source maintenue dans `vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/`.
  Les profils normaux continuent de sélectionner la source d'origine.
  Leur comparaison textuelle avec le CMake généré antérieurement est contrôlée
  par `tools/check-vendor-consolidation-debt.py`, et leurs horloges
  de profilage restent vérifiées par `tools/check-ps5-quiet-cpu-io-clocks.py`
  directement à partir des fichiers maintenus.
- Les témoins `ServiceFrameworkBase::HandleSyncRequest` et `SendSyncRequestImpl`
  sont maintenant sélectionnés comme unités maintenues depuis
  `vendor/encore-active/eden-core/src/core/hle/service/service.cpp` et
  `vendor/encore-active/eden-core/src/core/hle/kernel/svc/svc_ipc.cpp`.
  Le contrôle de parité conserve les deux traces `IFileSystem` et
  l'attribution des attentes IPC à leur thread demandeur.
- **Ne pas supprimer à l'aveugle :** les générateurs de ressources (`glsl`),
  les patchs optionnels OFF et les modifications interdépendantes (mémoire,
  JIT, GPU) demandent des critères de sélection et une preuve d'équivalence.
- Une substitution par un module CMake ne serait **pas une migration de source**.
  La cible est une vraie unité maintenue dans `vendor/encore-active`
  avec remplacement de la source sélectionnée et témoin de non-régression.

## Ressource OpenSSL native : source maintenue, plus de reconstruction au build

Le header CA natif (`inline constexpr char kCert[]`, 147 certificats)
est maintenu intégralement sous
`vendor/encore-active/eden-build/openssl/cert.h`. Le script
`tools/materialize-openssl-cert.py` vérifie l'identité de son contenu
avec `vendor/sources/eden/.patch/openssl/0001-add-bundled-cert.patch`
puis copie uniquement la version maintenue dans
`cdeps/include/openssl/cert.h`. La liste de confiance demeure
strictement identique ; la validation TLS n'est pas désactivée.

Le contrôle hôte `tools/check-maintained-openssl-cert.py` vérifie
la copie identique, sa stabilité à une deuxième exécution et le refus
d'un patch amont modifié. Ceci ne qualifie pas TLS sur console.

## Overrides et générateurs hors CMake principal — audit des points d'entrée

La présence d'un script dans `tools/` ne signifie **pas** qu'il participe
à la compilation : certains opèrent sur l'arbre de travail jetable, d'autres
reconstruisent un témoin dans un répertoire temporaire, d'autres produisent
des ressources du launcher. Cette table décrit les **mécanismes identifiés**,
et non les 458 scripts Python/shell/CMake du seul dossier `tools/`.

| Point d'entrée | Sélection / rôle | Source compilée ou sortie | Dette |
| --- | --- | --- | --- |
| `tools/prepare-build.sh` | **ACTIF**, orchestrateur `make prepare` | Arbre Eden jetable, dépendances et RADV | Sélection uniquement |
| `tools/install-vendored-eden-backports.py` | **ACTIF**, copie vérifiée par manifest SHA | 83 fichiers suivis dans `encore-active/eden-backports` | Déjà matérialisé |
| `tools/install-vendored-eden-build-flags.py` | **ACTIF**, deux recettes suivies | `encore-active/eden-build` | Déjà matérialisé |
| `tools/install-vendored-surface-lifecycle.py` | **ACTIF**, copie de source complète | `encore-active/eden-surface-lifecycle` | Déjà matérialisé |
| `tools/install-vendored-radv.py` | **ACTIF**, copie de sources RADV maintenues | `encore-active/ps5-mesa` vers staging | Déjà matérialisé |
| `tools/install-active-core-backports.py` | **ACTIF**, copie de sources maintenues avec replay temporaire de parité | **5 chemins** CPU/I-cache et HLE SM/audio sous `encore-active/eden-core` | **Migré** : sources installées jamais fabriquées par les patches |
| `tools/refresh-eden-atomic-source-cache.py` | **ACTIF**, échange atomique d'un ancien cache identifié | Restaure archive épinglée, pas une nouvelle modification C++ | Maintenance de cache |
| `tools/vendor-eden-cpm.py`, `tools/deps.py`, `tools/stage-vendored-opengl-deps.py` | **ACTIF** selon préparation et configuration | Copie d'entrées épinglées, non-patch de C++ | Dépendances |
| `tools/build-headless-native.sh`, `tools/materialize-openssl-cert.py` | **ACTIF**, copie de l'en-tête CA maintenu dans `encore-active/eden-build/openssl/cert.h` | `cdeps/include/openssl/cert.h` en cache natif | Parité octet pour octet avec le patch Eden épinglé ; **pas** de transformation C++ pendant le build |
| `tools/build-radv-dependencies.sh` | **ACTIF**, remplace provisoirement deux paramètres du cross-file Meson pour `ccache` puis restaure sur `EXIT` | `tooling/radv/ps5-cross.ini` dans la dépendance externe | Override de configuration temporaire, **pas** une source RADV suivie |
| `tools/radv-active-inputs.py` | **ACTIF**, vérifie/écrit l'empreinte des inputs compilés RADV | `EDEN_ACTIVE_INPUTS_SHA256` | Reçu de build, aucun patch C++ |
| `tools/build-headless-host.sh` | **HÔTE SEUL**, remplace trois lignes FFmpeg dans le cache hôte | `externals/ffmpeg/CMakeLists.txt` en staging | Override de build hôte, **hors console** |
| `tools/build-opengl-sdk.sh` | **TEST HÔTE macOS**, modifie temporairement le test de surfaces | Copie restaurée après le test, pas source PS5 livrée | Ne pas confondre avec override du moteur |
| `tools/apply-eden-backports.sh` et `tools/migrate-*-cache.py` | **REPLAY HISTORIQUE** / reprise d'anciens caches | Patches + migration de deux fichiers sur source jetable | Non exécuté par le chemin normal `make prepare` |
| `tools/prepare-vulkan-port.py` | **ORACLE** dans `check-vendored-vulkan-fork.py` | Sources générées en répertoire de test, comparées au fork `eden-vulkan` | **Pas** de génération durant CMake |
| `tools/patch-radv-wsi.py` et `tools/radv_official_*_fix.py` | **ORACLE** explicite `--oracle` / `--check` | Vérification du fork `ps5-mesa` ; mutation par défaut désactivée | Aucun patch RADV en build |
| `tools/apply-upstream-4473.py` | **MANUEL / TEST**, `--dest` obligatoire pour écrire | Quatre unités GPU dérivées dans destination choisie | Pas dans la chaîne normale |
| `tools/sync-encore-overrides.py` | **RÉGÉNÉRATION EXPLICITE** | `headless/encore_overrides_generated.h` : profils/titres | Données de jeu, distinctes du moteur |
| `tools/sync-glyph-overrides.py` | **RÉGÉNÉRATION EXPLICITE** | `headless/glyph_overrides_generated.h` | Catalogue visuel, non-mapping HID |
| `tools/launcher/strings.py` | **RÉGÉNÉRATION EXPLICITE** | Catalogues PO et en-tête français `fr_fr_embedded.h` | Ressources locales |
| `tools/ps-glyph-*.py` | **OUTILS HORS BUILD** d'analyse/adaptation de mods | Fichiers de recherche / packs externes, pas un patch C++ de l'émulateur | Frontière à conserver |
| X01/X02 : anciens `macro_recovery.cmake` / `slot_vector_recovery.cmake` | **RETIRÉS du build**, fichiers absents | `eden-core/src/video_core/macro.cpp` et `eden-core/overrides/slot-vector/common/slot_vector.h` | Sources complètes sélectionnées, parité historique contrôlée |
| Aucun module indirect actif | Les corrections JIT sont des sources Encore | G11/X06 retirés du build | Oracles historiques séparés |
| `headless/vulkan.cmake` | **BUILD**, copie/sélection d'un fork vérifié | `encore-active/eden-vulkan` | Aucun appel au générateur Python |

**Règle de lecture :** le compteur de synthèse additionne uniquement les
sites `write_derived` du CMake principal et des modules, pas les générateurs Python, les copies de dépendances,
les recettes CMake ni les sorties de ressources. **Zéro source sans propriétaire
dans le catalogue `vendor/encore-active` n'implique pas zéro override hors de
ce répertoire.** Les cinq sources CPU/I-cache et HLE SM/audio sont désormais versionnées sous
`encore-active/eden-core`. Le script conserve un replay temporaire de
comparaison, mais **ne fabrique plus les fichiers livrés** : il copie les
sources maintenues après avoir vérifié l'identité exacte des cinq résultats.

## GPU — suppression des deux générateurs fantômes

Le chemin natif sélectionne déjà directement les quatre fichiers de
`vendor/encore-active/eden-gpu` (workers DEV/quiet, file et en-tête).
Les deux anciennes branches `if(PS5_NATIVE)` imbriquées dans le
`else()` non natif étaient inaccessibles ; leurs générateurs
`bounded_threadsafe_queue.h` et `gpu_thread.cpp` ont été supprimés.
Le dernier générateur GPU non natif `gpu_thread.h` a lui aussi été remplacé
par un fichier complet dans `eden-core/host-gpu`. La sélection CMake copie
ce fichier sans modification ; un test assure sa parité exacte avec les
deux anciennes substitutions et conserve distinctes les variantes GPU natives.

Les tests utilisent désormais les sources maintenues et exercent les
`configure_file` du véritable chemin natif ; le test hôte de durée
de vie compare la file livrée à la réparation historique exacte.

## R437 : cache GPU centralisé

Le header `video_core/buffer_cache/buffer_cache.h` du chemin natif est maintenu
dans `vendor/encore-active/eden-core/src/video_core/buffer_cache/`, à partir
du backport de production. CMake ne fait qu'une copie des octets suivis
dans son arbre d'inclusion. Le témoin R437 reconstruit l'ancienne transformation
et vérifie la parité, sans prétendre valider le comportement console.

## Runtime de démarrage RADV : sélection directe

Le profil natif RADV utilise désormais
`vendor/encore-active/eden-build/tooling/native/app_crt_radv.cpp`
comme source C++ maintenue. La variante réplique exactement l'ancienne
substitution de l'initialiseur IEEE dans le boilerplate épinglé et le
CMake ne produit plus `radv_app_crt.cpp` au moment de la configuration.
La parité source ne vaut pas validation d'exécution sur console.

## Dynarmic scalaire : unités maintenues

Les trois transformations de `scalar_impl.cpp` (désormais
`impl/impl.cpp`), `a64_translate.cpp` et `opt_passes.cpp` sont
matérialisées sous `vendor/encore-active/eden-core/src/dynarmic/`.
Le compilateur sélectionne les deux unités et leur include relatif.
`scalar-fold.inc` reste témoin de parité, non injecté par CMake.
La politique JIT reste inchangée. Build et essais console encore requis.

## Diagnostic conditionnel Maxwell : source maintenue

Le profil `EDEN_DEV_PROFILE` sélectionne désormais
`vendor/encore-active/eden-core/src/video_core/engines/maxwell_3d.cpp`.
Cette unité complète reproduit les deux compteurs de rendu conditionnel de
l'ancienne génération CMake. Le profil normal utilise toujours la source
Eden d'origine. Le contrôle de parité vérifie exactement les modifications,
sans conclure à une amélioration GPU sur console.

## Tables sparse : source complète et sélection identique

`common/sparse_large_vector.h` conserve désormais son implémentation native
complète dans `vendor/encore-active/eden-core/src/common/`. CMake copie le
fichier versionné dans l'ancien répertoire d'inclusion, sans construire du
C++ par `string(REPLACE)`. Le témoin de parité rejoue les onze substitutions
historiques uniquement dans `tools/check-maintained-sparse-vector.py`.
Les contrôles de compilation/console sont des qualifications distinctes.

## Finalisation KProcess : diagnostics DEV maintenus

`k_process.cpp` est une unité C++ complète maintenue dans
`vendor/encore-active/eden-core/src/core/hle/kernel/`. Le profil
`EDEN_DEV_PROFILE` la sélectionne directement, sans reconstituer les
cinq horodatages de finalisation via une fonction CMake. Le profil
normal compile toujours la source épinglée. Le témoin de parité hôte
rejoue exactement les cinq substitutions, à partir de
`KProcess::Finalize`, hors du chemin de production.

## Dynarmic : source unique du suivi des blocs compilés

`block_range_information.cpp` et son en-tête sont deux fichiers complets
dans `vendor/encore-active/eden-core/src/dynarmic/backend/`.
Les copies sources sous `headless/dynarmic/` sont supprimées, et CMake
sélectionne directement le nouveau .cpp et copie le .h sans générer du code.
Le test d'identité vérifie les blobs d'origine et l'absence des anciens
propriétaires. Le suivi par pages de 4 KiB et le profil JIT restent inchangés.

## OpenGL : sources normales et DEV maintenues

Le rasterizer OpenGL n'est plus produit par substitutions CMake.
Deux unités complètes, `gl_rasterizer.cpp` et `gl_rasterizer_dev.cpp`,
sont maintenues dans `vendor/encore-active/eden-core/src/video_core/renderer_opengl/`.
Le sélecteur conserve le chemin normal et la variante DEV avec
`CaptureDevelopmentPass` et timer, sans générer du code C++.
Un oracle hôte reconstruit les anciennes variantes pour la parité ;
la compilation native et les performances console sont non qualifiées.

## ServerManager : G17/G18 déplacés vers les sources maintenues

L'en-tête de service et les deux variantes de `server_manager.cpp` vivent désormais dans `vendor/encore-active/eden-core/src/core/hle/service/`. Le profil normal et le profil DEV sélectionnent chacun un couple source/en-tête complet, sans fabriquer du C++ depuis CMake. Le test `tools/check-maintained-server-manager.py` rejoue l'ancienne transformation du snapshot épinglé et vérifie l'équivalence exacte des deux profils ; il ne constitue pas une validation sur console.


## Chargeur NSO natif : G15 retiré

La variante native de `loader/nso.cpp` est une source complète suivie sous
`vendor/encore-active/eden-core/src/core/loader/nso.cpp`. Le profil normal
conserve le fichier Eden d'origine ; `PS5_NATIVE` copie exactement la source
maintenue sur l'ancien chemin `PORT_BUILD_DIR/nso.cpp`, sans `file(READ)`,
`string(REPLACE)` ni `write_derived` sur cette unité. Le témoin
`tools/check-maintained-nso.py` exécute l'ancien générateur **uniquement**
en répertoire temporaire et compare octet par octet les deux sources.
Le stress mémoire existant `tools/check-nso-memory.py` conserve son chemin
de lecture ; compilation native et exécution console restent à qualifier.


## Core::System : G14 retiré

Les profils normal et natif utilisent désormais deux unités complètes,
`vendor/encore-active/eden-core/src/core/core_standard.cpp` et
`core_native.cpp`, sélectionnées en COPYONLY vers `PORT_BUILD_DIR/core.cpp`.
Les changements communs de chargeur, de durée de vie DeviceMemory et de
fermeture de services sont maintenus une fois par variante. Le diagnostic
natif de fermeture est conservé sans chemin absolu dans son `#include`.
Le test `tools/check-maintained-core-system.py` rejoue le générateur G14
historique en répertoire temporaire pour chaque profil, avec une seule
normalisation de chemin pour l'en-tête de diagnostic. Ce témoin ne
certifie ni la compilation native ni les durées de fermeture sur console.

## Commandes GPU invité : G20 migré

Les quatre sources complètes normal/DEV de `dma_pusher` et
`engines/puller` résident sous `vendor/encore-active/eden-core/src/video_core/`.
Les gardes d'arrêt et les compteurs R405/R406 sont conservés exactement.
La version DMA part du backport de production #4473/#4477, tandis que
Puller part de l'original épinglé. `tools/check-maintained-guest-gpu-sync.py`
est l'oracle de parité des anciennes substitutions ; CMake ne sélectionne
plus que les unités suivies. Reste à prouver le comportement en jeu.

## Générateurs non encore déplacés

Les numéros Gxx sont les positions de cet inventaire, **pas** des validations.
La colonne « ligne » indique la position dans le CMake au moment du relevé ;
le contrôle automatique compare l'ensemble et l'ordre des cibles, pas les
numéros de ligne. Une « unité source » est encore dérivée au build ; cela
n'implique ni que sa transformation soit incorrecte ni qu'elle soit active
dans la version normale.

<!-- OVERRIDE_GENERATORS_START -->
| ID | Sortie `write_derived` | Domaine indicatif | Catégorie | Ligne CMake |
| --- | --- | --- | --- | ---: |
| G23 | `${PORT_BUILD_DIR}/include/loading_scene_glsl.h` | Ressources | Ressource générée | 2065 |
<!-- OVERRIDE_GENERATORS_END -->

Les identifiants historiques `G01`, `G02`, `G03`, `G04`, `G05`, `G06`, `G07`, `G08`, `G09`, `G14`, `G15`, `G16`, `G17`, `G18` et `G20` sont retirés, avec G09 maintenu dans les unités A64 standard/partagée ; `G01`/`G02` sont retirés avec X09 (sources complètes `BlockOfCode` sous `encore-active`).
L'identifiant historique `G22` est retiré : les deux variantes de l'allocateur
sont maintenues sous `vendor/encore-active/eden-build/tooling/native/`.
Les IDs G01–G23 sont stables et ne sont pas renumérotés.


## G11 + X06 — preuve des variantes avant centralisation

Le générateur C++ historique G11 produisait `arm_dynarmic_32.cpp` et
`arm_dynarmic_64.cpp` selon hôte/natif, normal/DEV et l'option
`EDEN_INLINE_EXCLUSIVES`. Le module X06 ajoutait ses gardes de lecture
RAM native à cette même chaîne ; tous deux sont retirés du build actif.

Le nouveau témoin `tools/check-g11-jit-profile-matrix-host.py` reconstitue
d'abord la source native réellement préparée, avec les patchs I-cache
J19/J20 **installés depuis `encore-active` avant CMake**, puis configure
la vraie recette G11 sur **huit profils**, soit **16 unités** A32/A64. Il
contrôle les propriétaires compilés une seule fois, les gardes de lecture
X06, les tailles des caches et le fallback JIT natif, les marqueurs DEV,
et les exclusivités monitor ou inline. Cette première preuve reste
entièrement **hôte**.

La macro des exclusivités inline est configurée **sur la directory de la cible `core`**
via `TARGET_DIRECTORY core`, exclusivement sur les deux sources JIT sélectionnées :
ce contrôle évite une validation trompeuse du seul répertoire `headless`.

Les huit sources complètes G11 sont maintenues sous
`eden-core/src/core/arm/dynarmic/g11/` : A32/A64 × hôte/natif ×
normal/DEV. L'option `EDEN_INLINE_EXCLUSIVES` garde deux expressions
conditionnelles en C++ dans chacune : la matrice contrôle leur
équivalence aux seize sorties historiques. Le build actif sélectionne
directement les huit variantes G11.
L'ancienne génération est archivée dans `tools/fixtures/legacy-g11-jit.cmake`
uniquement pour le test de parité.

Les unités `eden-core/src/core/arm/dynarmic/arm_dynarmic_{32,64}.cpp`
déjà cataloguées constituent **la base préparée** (I-cache incluse),
mais n'incluent pas encore toutes les modifications ultérieures de G11.
Le témoin interdit leur substitution directe comme sources finales.
L'ancienne hypothèse d'un G11 basé uniquement sur la source épinglée
brute aurait perdu la cohérence I-cache de production. Toute évolution devra préserver les variantes dans `encore-active`,
sans activer les exclusivités inline, désactivées par défaut.

## G19 — matrice kernel avant centralisation

Le générateur historique G19 produisait une unité `kernel.cpp` distincte pour le
profil normal et le profil DEV. Le témoin
`tools/check-g19-kernel-profile-matrix-host.py` exécute la vraie recette
CMake et vérifie la provenance effective de `KProcess`, `ServerManager`
et de l'unité kernel, sans double compilation. Il préserve les gardes de
clôture, les références des threads, l'arrêt des services et les marqueurs
de diagnostic DEV. Les résultats restent des preuves **hôte** uniquement.

Les deux variantes C++ complètes sont désormais présentes sous
`vendor/encore-active/eden-core/src/core/hle/kernel/` ; le contrôle hôte
exige leur parité exacte avec les sorties de G19, mais elles ne sont pas
encore sélectionnées par le build.

G19 sélectionne maintenant directement les deux C++ complets dans
`vendor/encore-active`. L'ancienne recette est archivée exclusivement dans
`tools/fixtures/legacy-g19-kernel.cmake` ; le témoin compare les deux sorties
et vérifie que le nouveau sélecteur ne compile jamais un kernel en double.

## G21 — matrice de dépendances avant centralisation

G21 ne génère plus `gpu.cpp` au build : la recette historique est archivée
dans `tools/fixtures/legacy-g21-gpu.cmake`, où elle sert d'oracle de parité.
Le témoin `tools/check-g21-gpu-profile-matrix-host.py` configure **la vraie
recette G21** dans six combinaisons représentatives, plutôt que de supposer
que le profil normal, DEV et les deux moteurs graphiques sont équivalents.
Le test vérifie également la durée de vie du worker, les clôtures
synchrones, l'annulation des attentes, la capture par valeur, les erreurs
du worker et les traces DEV. C'est une preuve hôte de génération uniquement.

Les propriétaires de la future migration sont `video_core/gpu.cpp`
(source épinglée), `eden-gpu/gpu_thread_{quiet,dev}.cpp` (workers),
`eden-core/src/video_core/{dma_pusher,engines/puller}*.cpp` (G20),
`eden-core/gpu-injections/gpu_sync_failure_wait.inc` (ancien oracle
de clôture) et `headless/CMakeLists.txt` (sélection). La parité doit être
vérifiée pour les sorties OpenGL hôte/natif normales et DEV ainsi que
Vulkan natif ; l'option DEV ne produit pas de différence G21 avec Vulkan
dans la recette actuelle. Aucun changement de moteur ou de GPU worker
n'est autorisé par ce relevé.

Les cinq candidates G21 sont maintenant archivées en fichiers C++ complets
sous `eden-core/src/video_core/gpu_{gl_host,gl_host_dev,gl_native,gl_native_dev,vulkan}.cpp`.
Le témoin compare chacun des cinq fichiers aux octets produits par CMake
après normalisation des anciens chemins d'en-têtes absolus. Les candidates
sont sélectionnées directement par le build. Le témoin de six configurations
vérifie également que la cible `video_core` utilise l'unique variante
attendue, et non un ancien fichier dérivé.

La migration G21 a retiré le générateur C++ et l'intégralité de ses
substitutions CMake, tout en conservant la sélection OpenGL des autres
sources GPU, G20 DMA/puller et les différences Vulkan/DEV.

Pour retirer G21, maintenir les unités C++ finales exclusivement sous
`vendor/encore-active`, archiver les substitutions CMake uniquement
comme oracle hôte, basculer le sélecteur vers une unique unité par profil
et adapter en une seule passe les vérifications de synchronisation et de
capture GPU. La compilation native et les essais console resteront requis.

## Prochain ordre de migration

- Huit sources de backport HLE ont des propriétaires `F19-F24`, `H41`,
  `N18` : firmware `SystemVersion`, enregistrement des services,
  création d'applications, RomFS et interfaces NS, sélection des manettes,
  couches d'affichage. Les marqueurs fonctionnels sont vérifiés contre
  la copie de production ; aucune source n'est dupliquée sous `eden-core`.


- Six backports supplémentaires (`A06`, `N15-N17`, `H40`, `V61`)
  sont indexés par fonction et par hunk réel : ID de session audio,
  IPC BSD, contrôle réseau NIFM, échantillonnage NPad, validation TIC.
  Les fichiers d'entrée du manifeste de production ne sont pas dupliqués.
  La prévalidation vérifie les marqueurs, pas leur exécution native.


- `hid_core/frontend/emulated_controller.cpp` (vibrations virtuelles) :
  source maintenue directement dans `eden-core/src/hid_core/frontend/`.
  Sélection identique dans `hid_core SOURCES`, sans mutation de CMake.
  Parité vérifiée depuis l'unité Eden épinglée pour `LoadDevices()`.
  Aucun ajustement des mappings des commandes ni preuve de vibrations console.


- **V53–V60** : huit nouveaux backports GPU/compute ont leurs fonctions et
  différences effectives enregistrées (buffer/texture/query/fence caches,
  état de canal, Kepler et DMA). Chaque marqueur source est vérifié contre
  le backport livré et contre l'original Eden. Ces entrées ne prouvent pas
  la disparition des blocages GPU sur la console.


- `core/hle/service/nvdrv/core/container.cpp` : session ownership
  `Container::OpenSession` et `CloseSession` repris en C++ maintenu,
  avec parité exacte des trois corrections et de l'ajout d'en-têtes.
  Le générateur `nvdrv_container.cpp` est retiré. La durée de vie du
  processus et les réactions en cascade restent à prouver sur console.


- Les **12 backports prioritaires** `M12-M14`, `H37-H38`,
  `N11-N14` et `V50-V52` ont leurs fonctions réellement modifiées
  enregistrées après comparaison des fichiers complets avec les sources
  épinglées : mappings, scheduler, nvmap, queue, DNS, caches GPU.
  Ces sources sont installées avant les overrides natifs optionnels ;
  leur présence sur disque ne prouve pas qu'elles sont la dernière unité
  effectivement compilée. Les marqueurs de hunks sont gardés par un test hôte.


- `ps5-mesa` : les **12 entrées réelles du pilote natif**, dont
  `src/amd/vulkan/cl/radv_gs_compute.cl`, sont maintenant suivies par
  `R12-R23` et recoupées avec les `PATHS` de
  `tools/install-vendored-radv.py`. Les empreintes de construction restent
  gérées par `tools/radv-active-inputs.py`. Aucune source pilote modifiée.


- Politique réseau guest : la version livrée `eden-backports` et son manifeste
  demeurent inchangés. Le build `PS5_NATIVE` utilise désormais l'en-tête
  prioritaire `eden-core/overrides/core/hle/service/sockets/encore_guest_network_policy.h`
  avec `kGuestNetworkOffline=true`. Vérifier séparément le trafic console :
  le test hôte assure les consommateurs DNS, BSD, NIFM et la sélection des includes.


- `core/memory.cpp` : sélection directe de la source maintenue
  `vendor/encore-active/eden-core/src/core/memory.cpp` **uniquement**
  lorsque `EDEN_A32_FASTMEM` est activé. Elle reproduit exactement le
  correctif de garde 32 bits après installation de
  `vendor/encore-active/eden-backports/src/core/memory.cpp`, pas après
  lecture du fichier Eden non patché. Le test refuse toute dérive des
  octets de la version de production.


- `gl_texture_cache.cpp` OpenGL en mode **EDEN_DEV_PROFILE** est maintenant
  une unité compilée depuis `vendor/encore-active/eden-core/src/` plutôt
  qu'une substitution de CMake. Le profil normal utilise toujours la source
  épinglée. Le test de consolidation compare exactement l'ajout de `<cstdio>`
  et les huit lignes de diagnostic du précédent générateur, sans valider
  de performances ou de comportements console.


- `compiler-rt/emutls.c` est maintenant compilé depuis
  `vendor/encore-active/compiler-rt/`, avec la même politique native
  `EMUTLS_SKIP_DESTRUCTOR_ROUNDS=1` que la génération CMake précédente.
  L'original LLVM épinglé `vendor/sources/compiler-rt/emutls.c` reste
  inchangé et l'en-tête `int_lib.h` vient toujours de `COMPILER_RT`.


- `gl_buffer_cache.cpp` et `gl_query_cache.cpp` sont des sources suivies
  sous `vendor/encore-active/eden-core/src/video_core/renderer_opengl/`.
  Les remplacements GL_RED_INTEGER et absence de slicing de requêtes
  dans le profil natif sont conservés exactement. La sélection reste
  conditionnée par `EDEN_PS5_OPENGL` et `PS5_NATIVE`.


- `video_core/renderer_opengl/renderer_opengl.cpp` n'a jamais eu de
  modification textuelle dans son générateur : la simple copie via
  `file(READ)` et `write_derived()` a été retirée. Le fichier source
  épinglé est conservé dans `video_sources`, sans ajouter un second
  override C++ dans `vendor/encore-active`.


- `video_core/video_core.cpp` n'est plus généré : le profil Vulkan utilise
  le fichier épinglé original, tandis que le profil sans Vulkan compile
  `vendor/encore-active/eden-core/src/video_core/video_core_opengl.cpp`,
  une version suivie identique aux deux anciennes suppressions CMake. La
  sélection explicite et la parité font partie du test hôte.


- `core/file_sys/bis_factory.h` et `.cpp` sont compilés depuis
  `vendor/encore-active/eden-core/` sans génération de contenu : l'en-tête
  vit dans `include/core/file_sys/`, isolé des autres en-têtes du fork,
  et la source dans `src/core/file_sys/`. Le test vérifie le contrat du
  constructeur, le cache firmware, le dossier de mods existant et le
  retrait de l'ancien en-tête dérivé. Aucun comportement en jeu n'est inféré.


- `core/file_sys/fsmitm_romfsbuild.cpp` est désormais maintenu dans
  `vendor/encore-active/eden-core/src/`. Les deux champs parent et les
  deux affectations sont identiques aux transformations CMake antérieures ;
  ils ne créent plus de cycles d'ownership et l'unité n'est plus générée.
  Le contrôleur `core` sélectionne la source directement, avec témoin
  de parité dans `tools/check-vendor-consolidation-debt.py`.


- `audio_core/sink/sink_stream.cpp` est compilé depuis
  `vendor/encore-active/eden-core/src/` plutôt que dérivé par CMake. Les
  quatre anciennes réécritures (capacité PCM, upmix mono, maintien de trame)
  sont reproduites exactement, avec un oracle de parité dans
  `tools/check-maintained-audio-units.py`. Le test n'atteste pas de l'audio
  sur console.


- `core/hle/service/filesystem/filesystem.cpp` est désormais maintenu dans `vendor/encore-active/eden-core/src/`. Le constructeur de `FileSystemController::CreateFactories` garde la même racine firmware ; sa sélection et sa parité sont contrôlées par le test hôte.


Les anciens générateurs `hle_service.cpp` et `svc_ipc.cpp`
ont été supprimés après migration des deux unités dans `vendor/encore-active`.
Leurs points d'échantillonnage, traces et garde-fous hors diagnostic
restent couverts par un test d'identité de transformation.
Le bloc ordinaire CPU/JIT et les correctifs GPU synchronisés se migrent
par unités de preuve distinctes, sans réécrire globalement les 3 000+ lignes
de CMake en une fois.

**Complément au registre :** les chemins de progression invité
`CpuManager::RunThread`, `KScheduler::ScheduleImplFiber`,
`KScheduler::SwitchThread`, `KScheduler::Unload`,
`KScheduler::Reload`, ainsi que la persistance du statut de suspension de
`KThread`, sont désormais référencés dans
`docs/EDEN_CORE_AUDIT_DEPENDENCIES.md`. Une existence de code ne prouve
pas que le PC invité avance après un réveil HLE.

- `Common::SetCurrentThreadName` et les deux boucles d'énumération
  `Common::FS::RemoveDirContentsRecursively` /
  `Common::FS::IterateDirEntries` sont désormais compilées depuis
  `vendor/encore-active/eden-core/src/common/`. Les fichiers épinglés
  restent inchangés ; le test de parité vérifie la capture du worker et
  les deux appels de l'itérateur natif.

- `common/cpu_features.cpp` (fréquence TSC invariante même sans
  CPUID leaf 0x15) et `common/fs/path_util.cpp` (racines natives
  utilisateur/cache/configuration) sont désormais maintenus sous
  `vendor/encore-active/eden-core/src/common/`. Leurs fichiers d'origine
  demeurent épinglés ; le contrôle compare les transformations exactes
  et la sélection unique par la cible `common`.

- `core/internal_network/network_interface.cpp` est aussi une unité
  maintenue sous `vendor/encore-active/eden-core/src/`. Les trois
  sélections de compilation FreeBSD ont été déplacées depuis CMake sans
  réécrire l'algorithme `getifaddrs` ni son fallback de route.

## Register allocator Dynarmic : source maintenue

Les versions complètes `reg_alloc.h` et `reg_alloc.cpp` sont désormais
maintenues dans `vendor/encore-active/eden-core/src/dynarmic/backend/x64/`.
Le module CMake `reg_alloc.cmake` sélectionne et copie ces sources,
sans réinjecter de méthodes C++. Le profil `EDEN_REGALLOC_VERIFY`
reste réservé à l'hôte. Un test de parité rejoue les cinq transformations
uniquement comme oracle, pas comme entrée de compilation.

## Pool JIT constant : source complète suivie

`constant_pool.cpp` est maintenu sous `vendor/encore-active/eden-core/src/dynarmic/backend/x64/`,
avec la modification exacte de l'alias mémoire auparavant reconstruite dans CMake.
Le module `jit-alias.cmake` sélectionne ce fichier pour la compilation, sans
produire une deuxième implémentation. Son générateur `xbyak.h` reste distinct.
L'oracle hôte reproduit l'ancienne transformation uniquement pour vérifier la parité.

## Émetteurs scalaires Dynarmic : deux unités maintenues

Les émetteurs `emit_x64_vector.cpp` et `emit_x64_data_processing.cpp`
sont désormais versionnés sous `vendor/encore-active/eden-core/src/dynarmic/backend/x64/`.
Le module CMake ne les réécrit plus ; les trois anciens remplacements ne
servent qu'au témoin de parité hôte. Sa transformation restante de
`memory_source` (X08) est désormais retirée de CMake et doit être
traitée avec l'ensemble de l'émetteur mémoire, sans la masquer.

## Blitter logiciel GPU : source maintenue

`sw_blitter_sized.cpp` n'est plus assemblé par CMake. Le sélecteur natif
utilise `vendor/encore-active/eden-core/src/video_core/engines/sw_blitter/blitter.cpp`,
calculé depuis **le backport de production** conservant la correction
des pixels RGBA. Un oracle rejoue les trois substitutions arithmétiques
hors compilation. Les générateurs Maxwell PRMT et Fermi2D restent distincts.

## Shader PRMT Maxwell : source maintenue

L'ancienne unité `maxwell_prmt_observed.cpp` n'est plus fabriquée par
`gpu_native_observability.cmake`. La source complète `not_implemented.cpp`
est maintenue dans `encore-active/eden-core/src/shader_recompiler/`,
avec ses deux traductions PRMT mode 0, échantillonnage borné et
assertions de référence. Le module conserve le générateur indépendant
Fermi2D, qui sera migré séparément.

## Fermi2D : module GPU réduit à un sélecteur

Le module `gpu_native_observability.cmake` ne construit plus aucun C++.
Deux variantes complètes sous `vendor/encore-active/eden-core/src/video_core/engines/`
reproduisent l'ancien code par défaut et les trois transformations du mode
`EDEN_UNQUALIFIED_FERMI2D_COPY`, toujours désactivé par défaut. Le contrôle
de parité hôte garantit les deux résultats compilés historiques, sans
promettre le comportement console ni activer la voie expérimentale.

## Xbyak 7.40.1 : en-tête complet maintenu

`headless/jit-alias.cmake` ne construit plus `xbyak.h` via huit
substitutions. Le fichier complet, conservant sa licence originale, réside
dans `vendor/encore-active/eden-build/third_party/xbyak/xbyak.h`.
Un contrôle vérifie les huit modifications et, si le cache CPM épinglé
est disponible, reconstruit l'ancien résultat pour comparer chaque octet.
La modification historique `code_source` X09 est retirée : les variantes
complètes de `BlockOfCode` sont maintenues sous `encore-active`.

## G13 / X05 / M12 — sélection maintenue

Les unités natives `memory_native_standard.cpp` et `memory_native_a32.cpp`
sont maintenant sélectionnées directement sous `vendor/encore-active/eden-core/src/core/`.
Elles conservent les onze limites de journalisation, les deux gardes de page,
la lecture auxiliaire et le contrôle de débordement historiquement X05.
Le choix entre les profils retire exactement l'ancien propriétaire de
`core` et maintient la définition `PS5_NATIVE=1` sur l'unité retenue.

Le module DEV M12 choisit les fichiers complets
`guest-bridge/memory_ps5_{standard,a32}.cpp` et ne réécrit plus
`memory-ps5.cpp` au moment de configurer CMake. Ce pont reste
**désactivé par défaut**, sans validation du fonctionnement sur console.

Les trois recettes CMake d'origine sont archivées dans
`tools/fixtures/legacy-*` uniquement comme **oracles historiques de tests**,
jamais sur un chemin de compilation. La prévalidation compare les quatre
variantes maintenues aux anciennes sorties après normalisation des
chemins absolus d'en-têtes.

## Générateurs des modules CMake inclus — inventaire complémentaire

Le tableau principal n'indexe que `headless/CMakeLists.txt`. Les modules
inclus par ce fichier contiennent **0 autre appel `write_derived()`**
dans aucun module CMake secondaire. Leur somme avec les générateurs du CMake principal est un **nombre de
sites CMake**, pas un dénombrement des fichiers réellement produits à
l'exécution. Un module inclus peut définir des macros sans les exécuter,
et plusieurs sorties sont explicitement conditionnées.

Chaque couple exact **module → destination générée** est maintenant comparé
à ce tableau par `tools/check-vendor-consolidation-debt.py` lors de la
prévalidation hôte. Le simple maintien du nombre total de générateurs
n'autorise pas la substitution silencieuse d'une cible C++ ou d'un module.

<!-- MODULE_GENERATORS_START -->
| ID | Module CMake | Sortie dérivée | Porte / périmètre |
| --- | --- | --- | --- |
<!-- MODULE_GENERATORS_END -->

M07 est retiré : la variante complète de `vulkan_rasterizer.cpp` est
maintenue dans `vendor/encore-active/eden-core/guest-bridge/` ; le
sélecteur ne modifie plus le corps Vulkan et copie uniquement les octets
versionnés. Le test hôte vérifie la parité des deux transformations
historiques avec normalisation de l'include de la racine du port ;
cette variante reste DEV OFF, non qualifiée sur console.

M08 est retiré : la version diagnostique G20 de `DmaPusher::DispatchCalls`
est maintenant la base réelle de la variante complète, maintenue sous
`vendor/encore-active/eden-core/guest-bridge/dma_pusher.cpp`.
Le sélecteur vérifie le propriétaire G20 en DEV et remplace sa source
effective, au lieu de réclamer un ancien `dma_pusher.cpp` généré inexistant.
Parité de contenu et sélection CMake contrôlées côté hôte ; pont OFF.

M09–M11 sont retirés : les unités moteur de DMA, de compute et d'upload différés
sont versionnées sous `vendor/encore-active/eden-core/guest-bridge/` et
sélectionnées via `configure_file(COPYONLY)`. Le témoin de parité hôte
reconstruit les trois anciennes injections. Le pont reste expérimental, OFF.

M06 est retiré : `guest-bridge/memory_manager.cpp` est une unité C++ complète
maintenue dans `vendor/encore-active`. CMake la copie via `COPYONLY`.
Le test dédié reconstruit l'ancien résultat depuis un oracle hors build et vérifie
les octets réellement sélectionnés, sans activer le pont différé.

M05 est retiré : la version synchronisée du collecteur GPU est un en-tête
complet sous `vendor/encore-active/eden-core/guest-bridge/`.
La copie CMake conserve les octets historiques et le test hôte vérifie sa parité.

M04 est retiré : `guest-bridge/memory_manager.h` est une source complète maintenue
sous `vendor/encore-active/eden-core` et sélectionnée par `COPYONLY`.
Le test du pont différé vérifie la parité et les octets de la sortie CMake.
Le pont reste expérimental et OFF par défaut.

M01/M02/M03 sont retirés : `a64_jitstate.h`, `jit_group.h` et `callback.cpp`
sont trois fichiers complets sous `vendor/encore-active/eden-core/dynarmic/shared-jit/`.
Le module CMake ne reconstruit plus de C++ : les copies `configure_file(COPYONLY)`
sont contrôlées par les témoins de parité M01 et M03. Shared JIT reste OFF.

## Patches de sources hors générateurs CMake

**46 fichiers `.patch`** se trouvent encore dans `headless/backports/`.
Ils ne sont comptés ni dans **l'unique site** `write_derived()` (G23 GLSL),
ni dans des modules indirects actifs, désormais au nombre de **0** :

- **44 appels `apply_one`** dans `tools/apply-eden-backports.sh`,
  sous contrôle d'identité et de hash. Il modifie **l'arbre Eden fourni
  en argument** via `git apply` lorsqu'il est rejoué explicitement comme
  oracle historique. Le build courant installe, sans `git apply`, les
  **sources complètes** versionnées dans `vendor/encore-active/eden-backports`
  après vérification de leurs empreintes. L'appel à
  `eden-dummy-thread-waits.patch` est expérimental et OFF par défaut.
- **2 patches cœur** (`eden-dynarmic-icache-coherence.patch` et
  `eden-sm-host-wait.patch`) sont installés séparément par
  `tools/install-active-core-backports.py`, qui prépare cinq fichiers
  dans l'arbre actif à partir d'une base épinglée.

Ces 46 éléments sont des **artefacts de patches**, et non 46 fichiers
compilés différents. Certains modifient plusieurs sources, d'autres
sont conditionnels ; ils ne doivent pas être déplacés en bloc sans
respecter les dépendances et les règles d'installation. La cible reste
de matérialiser les sources maintenues dans `vendor/encore-active`
et de limiter CMake à la sélection.

<!-- SOURCE_PATCH_REPLAYS_START -->
| ID | Fichier de patch | Mécanisme d'installation | Ligne du script de replay | Statut |
| --- | --- | --- | ---: | --- |
| P01 | `eden-4473-4477.patch` | `apply-eden-backports.sh` | 256 | Replay avec validation |
| P02 | `eden-nvnflinger-dequeue-wakeup.patch` | `apply-eden-backports.sh` | 258 | Replay avec validation |
| P03 | `eden-4436-spinlock-mutex.patch` | `apply-eden-backports.sh` | 259 | Replay avec validation |
| P04 | `eden-fw23-services.patch` | `apply-eden-backports.sh` | 260 | Replay avec validation |
| P05 | `eden-runtime-hid.patch` | `apply-eden-backports.sh` | 261 | Replay avec validation |
| P06 | `eden-fc27-hle-compat.patch` | `apply-eden-backports.sh` | 283 | Replay avec validation |
| P07 | `eden-ps5-guest-offline.patch` | `apply-eden-backports.sh` | 313 | Replay avec validation |
| P08 | `eden-ps5-guest-domain-filter.patch` | `apply-eden-backports.sh` | 333 | Replay avec validation |
| P09 | `eden-dummy-thread-waits.patch` | `apply-eden-backports.sh` | 339 | Expérimental OFF |
| P10 | `eden-ps5-hid-watchdog.patch` | `apply-eden-backports.sh` | 369 | Replay avec validation |
| P11 | `eden-ps5-net-user-agent.patch` | `apply-eden-backports.sh` | 371 | Replay avec validation |
| P12 | `eden-ps5-launcher-fast-http.patch` | `apply-eden-backports.sh` | 377 | Replay avec validation |
| P13 | `eden-ps5-bounded-logging.patch` | `apply-eden-backports.sh` | 378 | Replay avec validation |
| P14 | `eden-ps5-crash-only-logging.patch` | `apply-eden-backports.sh` | 401 | Replay avec validation |
| P15 | `eden-ps5-gpu-memory-mapping.patch` | `apply-eden-backports.sh` | 442 | Replay avec validation |
| P16 | `eden-ps5-gpu-remap-reverse.patch` | `apply-eden-backports.sh` | 456 | Replay avec validation |
| P17 | `eden-ps5-gpu-unmap-reverse-guard.patch` | `apply-eden-backports.sh` | 481 | Replay avec validation |
| P18 | `eden-ps5-gpu-multi-missing-guard.patch` | `apply-eden-backports.sh` | 494 | Replay avec validation |
| P19 | `eden-ps5-gpu-map-bounds.patch` | `apply-eden-backports.sh` | 507 | Replay avec validation |
| P20 | `eden-ps5-gpu-physical-capacity.patch` | `apply-eden-backports.sh` | 520 | Replay avec validation |
| P21 | `eden-ps5-gpu-remap-cache-invalidate.patch` | `apply-eden-backports.sh` | 535 | Replay avec validation |
| P22 | `eden-ps5-gpu-empty-multi-head.patch` | `apply-eden-backports.sh` | 547 | Replay avec validation |
| P23 | `eden-ps5-gpu-physical-read-bounds.patch` | `apply-eden-backports.sh` | 571 | Replay avec validation |
| P24 | `eden-ps5-gpu-block-flush-bounds.patch` | `apply-eden-backports.sh` | 593 | Replay avec validation |
| P25 | `eden-ps5-gpu-span-physical-bounds.patch` | `apply-eden-backports.sh` | 620 | Replay avec validation |
| P26 | `eden-ps5-gpu-reverse-inline-bounds.patch` | `apply-eden-backports.sh` | 636 | Replay avec validation |
| P27 | `eden-ps5-gpu-atomic-forward-table.patch` | `apply-eden-backports.sh` | 668 | Replay avec validation |
| P28 | `eden-ps5-gpu-atomic-reverse-table.patch` | `apply-eden-backports.sh` | 695 | Replay avec validation |
| P29 | `eden-ps5-gpu-asid-lifetime-guard.patch` | `apply-eden-backports.sh` | 732 | Replay avec validation |
| P30 | `eden-ps5-gpu-asid-no-reuse.patch` | `apply-eden-backports.sh` | 760 | Replay avec validation |
| P31 | `eden-ps5-guest-mapping-diagnostics.patch` | `apply-eden-backports.sh` | 773 | Replay avec validation |
| P32 | `eden-ps5-guest-walk.patch` | `apply-eden-backports.sh` | 786 | Replay avec validation |
| P33 | `eden-ps5-guest-zero-alias.patch` | `apply-eden-backports.sh` | 801 | Replay avec validation |
| P34 | `eden-ps5-guest-map-null-backing.patch` | `apply-eden-backports.sh` | 823 | Replay avec validation |
| P35 | `eden-ps5-guest-span.patch` | `apply-eden-backports.sh` | 837 | Replay avec validation |
| P36 | `eden-ps5-nvmap-alloc-rollback.patch` | `apply-eden-backports.sh` | 870 | Replay avec validation |
| P37 | `eden-ps5-texture-descriptor-residency.patch` | `apply-eden-backports.sh` | 897 | Replay avec validation |
| P38 | `eden-ps5-texture-null-view-remap.patch` | `apply-eden-backports.sh` | 936 | Replay avec validation |
| P39 | `eden-ps5-feedback-loop-view-key.patch` | `apply-eden-backports.sh` | 965 | Replay avec validation |
| P40 | `eden-ps5-texture-shared-null-new-slot.patch` | `apply-eden-backports.sh` | 986 | Replay avec validation |
| P41 | `eden-ps5-feedback-loop-no-depth-fastpath.patch` | `apply-eden-backports.sh` | 1007 | Replay avec validation |
| P42 | `eden-ps5-feedback-loop-serial-fastpath.patch` | `apply-eden-backports.sh` | 1027 | Replay avec validation |
| P43 | `eden-ps5-adjacent-valid-view-reuse.patch` | `apply-eden-backports.sh` | 1051 | Replay avec validation |
| P44 | `eden-ps5-alias-current-tick-fastpath.patch` | `apply-eden-backports.sh` | 1073 | Replay avec validation |
| P45 | `eden-ps5-software-bilinear-source-coordinates.patch` | `apply-eden-backports.sh` | 1090 | Replay avec validation |
| P46 | `eden-dynarmic-icache-coherence.patch` | `install-active-core-backports.py` | — | Installation cœur active |
| P47 | `eden-sm-host-wait.patch` | `install-active-core-backports.py` | — | Installation cœur active |
<!-- SOURCE_PATCH_REPLAYS_END -->

## Couverture des cibles de patches

Les **47 fichiers de patches** touchent **90 chemins distincts**.
Les backports livrés sous `vendor/encore-active/eden-backports/` sont désormais
reconnus comme propriétaires. Les deux recettes CMake sont suivies via le
manifeste versionné ; les quatre sources hors snapshot par `H49`
(expérimental OFF), `H50`, `A08` et `A09` (SM/audio actifs).
Le contrôle impose **zéro cible de patch non attribuée**, sans prétendre
que chaque chemin a été validé sur console.

## Overrides indirects sans `write_derived()` local

Il ne reste **aucun module CMake indirect actif** modifiant du C++.
X06 est conservé comme oracle hôte hors du build.

<!-- INDIRECT_OVERRIDES_START -->
| ID | Module | Origine / source réécrite | Mécanisme | État |
| --- | --- | --- | --- | --- |
<!-- INDIRECT_OVERRIDES_END -->

Le sélecteur `headless/vulkan.cmake` copie des fichiers déjà maintenus
dans `vendor/encore-active` : ce n'est pas une réécriture C++ par
substitution. `headless/inject.cmake` orchestre l'inclusion ; le
toolchain `headless/ps5.cmake` configure compilation et édition de liens.
Ils ne sont donc pas ajoutés artificiellement comme huitième ou
neuvième générateur.

Les deux générateurs indirects `macro_recovery.cmake` et
`slot_vector_recovery.cmake` ont été remplacés par des sources complètes
maintenues dans `vendor/encore-active/eden-core`, sélectionnées directement.
Leurs transformations historiques servent désormais uniquement de parité.

Les modules historiques de correction mémoire/JIT ne modifient plus
les sources C++ du build. L'ancien X06 est archivé sous
`tools/fixtures/legacy-x06-native-jit-memory-read-guard.cmake`.
Ses protections sont intégrées aux variantes G11 maintenues.

À l'inverse, `headless/vulkan.cmake` copie déjà les sources réellement
maintenues dans `vendor/encore-active/eden-vulkan`, et le module HLE
`vendor/encore-active/eden-threading/native-hle-overrides.cmake`
sélectionne des sources et en-têtes maintenus. Leur CMake est un
sélecteur de build, pas un nouveau patch C++ par remplacement de texte.

**Priorité de migration :** garder le pont différé expérimental OFF,
ne pas activer le JIT partagé pour réduire artificiellement le nombre
de générateurs, migrer d'abord les unités normales/DEV réellement
sélectionnées avec preuve d'identité et sans changer leur comportement.
