# Eden Encore — inventaire des transformations CMake encore actives

**Branche :** `dev/ps5-sparse-jit`. **Dernière revue :** 18 octobre 2026.

Ce document inventorie **les appels restants à `write_derived()` dans
`headless/CMakeLists.txt`**, dans leur ordre réel. Il ne confond pas
les appels statiques avec les fichiers physiques : une cible comportant une
variable (`bits`, `unit_name`, etc.) peut produire **plusieurs fichiers**.
Toutes les variantes ne sont pas compilées au même moment ; le profil
développement, les options JIT expérimentales, les backends et le build
natif sélectionnent chacun leur sous-ensemble.

L'inventaire complémentaire `docs/EDEN_ACTIVE_SOURCE_CATALOG.md` suit les
243 fichiers de code et en-têtes dans `vendor/encore-active`,
y compris les backports de production et la dépendance graphique. Cette
couverture ne s'additionne pas aux sites de génération CMake ci-dessous.

## Synthèse vérifiable

- **26 appels générateurs** encore dans CMake ; contre **75 avant**
  les migrations de `fs_i_file.cpp`, `fs_i_storage.cpp`, `fs_i_filesystem.cpp`, `nvhost_ctrl.cpp` et `buffer_queue_producer.cpp`, puis `service.cpp` et `svc_ipc.cpp`. Le corps de la fonction utilitaire
  `write_derived` n'est pas compté comme une invocation.
- **33 lectures `file(READ`** et **141 remplacements
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
| `tools/build-headless-native.sh`, `tools/materialize-openssl-cert.py` | **ACTIF**, génération d'en-tête CA depuis un patch Eden épinglé | `cdeps/include/openssl/cert.h` en cache natif | Ressource OpenSSL requise ; **pas** une réécriture des fonctions du moteur |
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
| `headless/macro_recovery.cmake`, `slot_vector_recovery.cmake` | **BUILD**, écriture sans `write_derived` | Deux sorties CMake indirectes | Déjà indexées X01/X02 |
| `headless/checked-fastmem.cmake` et quatre autres modules indirects | **BUILD**, changement de variables source avant écriture | Unités dérivées du CMake principal | Déjà indexées X03–X07 |
| `headless/vulkan.cmake` | **BUILD**, copie/sélection d'un fork vérifié | `encore-active/eden-vulkan` | Aucun appel au générateur Python |

**Règle de lecture :** le compteur `26 + 15 = 41` décrit uniquement les
sites `write_derived`, pas les générateurs Python, les copies de dépendances,
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
| G01 | `${PORT_BUILD_DIR}/include/${code_relative}.h` | Dynarmic/JIT | En-tête source | 209 |
| G02 | `${PORT_BUILD_DIR}/block_of_code.cpp` | Dynarmic/JIT | Unité source | 273 |
| G03 | `${PORT_BUILD_DIR}/include/dynarmic/backend/x64/a64_emit_x64.h` | Dynarmic/JIT | En-tête source | 297 |
| G04 | `${PORT_BUILD_DIR}/a${bits}_emit_x64.cpp` | Dynarmic/JIT | Unité source | 309 |
| G05 | `${PORT_BUILD_DIR}/include/dynarmic/backend/block_range_information.h` | Dynarmic/JIT | En-tête source | 321 |
| G06 | `${PORT_BUILD_DIR}/emit_x64.cpp` | Dynarmic/JIT | Unité source | 351 |
| G07 | `${PORT_BUILD_DIR}/include/${memory_inc}` | Dynarmic/JIT | Cible variable | 497 |
| G08 | `${PORT_BUILD_DIR}/include/${memory_relative}` | Dynarmic/JIT | Cible variable | 517 |
| G09 | `${PORT_BUILD_DIR}/${memory_unit}` | Dynarmic/JIT | Cible variable | 528 |
| G10 | `${PORT_BUILD_DIR}/a64_interface.cpp` | Dynarmic/JIT | Unité source | 636 |
| G11 | `${PORT_BUILD_DIR}/a32_interface.cpp` | Dynarmic/JIT | Unité source | 664 |
| G12 | `${derived}` | CPU | Cible variable | 836 |
| G13 | `${PORT_BUILD_DIR}/physical_core.cpp` | CPU | Unité source | 918 |
| G14 | `${eden_native_memory_tu}` | Mémoire/chargement | Cible variable | 1157 |
| G15 | `${PORT_BUILD_DIR}/core.cpp` | Mémoire/chargement | Unité source | 1238 |
| G16 | `${PORT_BUILD_DIR}/nso.cpp` | Mémoire/chargement | Unité source | 1313 |
| G17 | `${PORT_BUILD_DIR}/k_page_table_base.cpp` | Kernel/IPC/entrées | Unité source | 1468 |
| G18 | `${PORT_BUILD_DIR}/k_process.cpp` | Kernel/IPC/entrées | Unité source | 1691 |
| G19 | `${PORT_BUILD_DIR}/include/${server_header}` | Kernel/IPC/entrées | Cible variable | 1708 |
| G20 | `${PORT_BUILD_DIR}/server_manager.cpp` | Kernel/IPC/entrées | Unité source | 1765 |
| G21 | `${PORT_BUILD_DIR}/kernel.cpp` | Kernel/IPC/entrées | Unité source | 1778 |
| G22 | `${PORT_BUILD_DIR}/gl_rasterizer.cpp` | Audio/graphique | Unité source | 2000 |
| G23 | `${PORT_BUILD_DIR}/${unit_name}.cpp` | GPU/vidéo | Unité source | 2095 |
| G24 | `${PORT_BUILD_DIR}/gpu.cpp` | GPU/vidéo | Unité source | 2192 |
| G25 | `${PORT_BUILD_DIR}/app_heap.c` | Runtime/FS/réseau | Unité source | 2400 |
| G26 | `${PORT_BUILD_DIR}/include/loading_scene_glsl.h` | Ressources | Ressource générée | 2595 |
<!-- OVERRIDE_GENERATORS_END -->

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
`memory_source` est enregistrée comme dette indirecte X08 et doit être
traitée avec l'ensemble de l'émetteur mémoire, sans la masquer.

## Blitter logiciel GPU : source maintenue

`sw_blitter_sized.cpp` n'est plus assemblé par CMake. Le sélecteur natif
utilise `vendor/encore-active/eden-core/src/video_core/engines/sw_blitter/blitter.cpp`,
calculé depuis **le backport de production** conservant la correction
des pixels RGBA. Un oracle rejoue les trois substitutions arithmétiques
hors compilation. Les générateurs Maxwell PRMT et Fermi2D restent distincts.

## Générateurs des modules CMake inclus — inventaire complémentaire

Le tableau principal n'indexe que `headless/CMakeLists.txt`. Les modules
inclus par ce fichier contiennent **15 autres appels `write_derived()`**
dans 4 fichiers. Le total de **41 appels** (26 + 15) est donc un **nombre de
sites CMake**, pas un dénombrement des fichiers réellement produits à
l'exécution. Un module inclus peut définir des macros sans les exécuter,
et plusieurs sorties sont explicitement conditionnées.

<!-- MODULE_GENERATORS_START -->
| ID | Module CMake | Sortie dérivée | Porte / périmètre |
| --- | --- | --- | --- |
| M01 | `headless/dynarmic/shared-jit.cmake` | `${PORT_BUILD_DIR}/include/${eden_jitstate_relative}` | Shared JIT OFF par défaut |
| M02 | `headless/dynarmic/shared-jit.cmake` | `${PORT_BUILD_DIR}/include/dynarmic/backend/x64/jit_group.h` | Shared JIT OFF par défaut |
| M03 | `headless/dynarmic/shared-jit.cmake` | `${PORT_BUILD_DIR}/callback.cpp` | Shared JIT OFF par défaut |
| M04 | `headless/gpu_native_observability.cmake` | `${PORT_BUILD_DIR}/maxwell_prmt_observed.cpp` | PS5_NATIVE |
| M05 | `headless/gpu_native_observability.cmake` | `${PORT_BUILD_DIR}/fermi_2d_observed.cpp` | PS5_NATIVE |
| M06 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/include/video_core/memory_manager.h` | Pont différé OFF |
| M07 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/deferred-core/core/gpu_dirty_memory_manager.h` | Pont différé OFF |
| M08 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/memory_manager_deferred.cpp` | Pont différé OFF |
| M09 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/vulkan_rasterizer_deferred.cpp` | Pont différé OFF |
| M10 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/dma_pusher_deferred.cpp` | Pont différé OFF |
| M11 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/maxwell_dma_deferred.cpp` | Pont différé OFF |
| M12 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/kepler_compute_deferred.cpp` | Pont différé OFF |
| M13 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/engine_upload_deferred.cpp` | Pont différé OFF |
| M14 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/memory-ps5-deferred.cpp` | Pont différé OFF |
| M15 | `headless/jit-alias.cmake` | `${PORT_BUILD_DIR}/include/xbyak/xbyak.h` | JIT/alias |
<!-- MODULE_GENERATORS_END -->

## Patches de sources hors générateurs CMake

**46 fichiers `.patch`** se trouvent encore dans `headless/backports/`.
Ils ne sont comptés ni dans les **41 sites** `write_derived()`, ni dans
les **4 modules indirects** ci-dessous :

- **44 appels `apply_one`** dans `tools/apply-eden-backports.sh`,
  sous contrôle d'identité et de hash. Il modifie **l'arbre Eden fourni
  en argument** via `git apply` ; il ne s'agit pas d'un sélecteur de
  C++ suivi dans `vendor/encore-active`. L'appel à
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
| P42 | `eden-ps5-adjacent-valid-view-reuse.patch` | `apply-eden-backports.sh` | 1027 | Replay avec validation |
| P43 | `eden-ps5-alias-current-tick-fastpath.patch` | `apply-eden-backports.sh` | 1049 | Replay avec validation |
| P44 | `eden-ps5-software-bilinear-source-coordinates.patch` | `apply-eden-backports.sh` | 1066 | Replay avec validation |
| P45 | `eden-dynarmic-icache-coherence.patch` | `install-active-core-backports.py` | — | Installation cœur active |
| P46 | `eden-sm-host-wait.patch` | `install-active-core-backports.py` | — | Installation cœur active |
<!-- SOURCE_PATCH_REPLAYS_END -->

## Couverture des cibles de patches

Les **46 fichiers de patches** touchent **90 chemins distincts**.
Les backports livrés sous `vendor/encore-active/eden-backports/` sont désormais
reconnus comme propriétaires. Les deux recettes CMake sont suivies via le
manifeste versionné ; les quatre sources hors snapshot par `H49`
(expérimental OFF), `H50`, `A08` et `A09` (SM/audio actifs).
Le contrôle impose **zéro cible de patch non attribuée**, sans prétendre
que chaque chemin a été validé sur console.

## Overrides indirects sans `write_derived()` local

Ces **5 modules supplémentaires** ne sont pas inclus dans les **42 appels**.
Tous modifient des variables-source ensuite écrites par le CMake principal.
Ils ne sont pas quatre sources C++ distinctes.

<!-- INDIRECT_OVERRIDES_START -->
| ID | Module | Origine / source réécrite | Mécanisme | État |
| --- | --- | --- | --- | --- |
| X03 | `headless/checked-fastmem.cmake` | `memory_emitter`, `memory_source` | Modifications de l'émetteur JIT dans les variables CMake | Non migré |
| X05 | `headless/native_guest_range_overflow.cmake` | `eden_cpu_memory` | Contrôle de débordement des adresses mémoire avant génération | Non migré |
| X06 | `headless/native_jit_memory_read_guard.cmake` | `wrapper` | Contrôle des lectures de mémoire invitée avant génération | Non migré |
| X07 | `headless/physical_core_interrupt_atomic.cmake` | `physical_core_source` | Accès atomiques aux interruptions avant génération | Non migré |
| X08 | `headless/scalar-memory.cmake` | `memory_source` | Insertion scalaire dans la variable source de l'émetteur mémoire CMake | Non migré |
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

Les quatre modules encore actifs `checked-fastmem.cmake`,
`native_guest_range_overflow.cmake`, `native_jit_memory_read_guard.cmake`
et `physical_core_interrupt_atomic.cmake` modifient des variables-source
qui sont ensuite écrites par CMake. Le correctif GPU des plages et de
`IsGranularRange` n'est plus dans un module : il vit dans la source C++
maintenue `vendor/encore-active/eden-core/src/video_core/memory_manager.cpp`.
Les tests hôtes comparent l'ancienne génération et la source sélectionnée.

À l'inverse, `headless/vulkan.cmake` copie déjà les sources réellement
maintenues dans `vendor/encore-active/eden-vulkan`, et le module HLE
`vendor/encore-active/eden-threading/native-hle-overrides.cmake`
sélectionne des sources et en-têtes maintenus. Leur CMake est un
sélecteur de build, pas un nouveau patch C++ par remplacement de texte.

**Priorité de migration :** garder le pont différé expérimental OFF,
ne pas activer le JIT partagé pour réduire artificiellement le nombre
de générateurs, migrer d'abord les unités normales/DEV réellement
sélectionnées avec preuve d'identité et sans changer leur comportement.
