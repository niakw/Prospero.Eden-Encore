# Eden Encore — inventaire des transformations CMake encore actives

**Branche :** `dev/ps5-sparse-jit`. **Dernière revue :** 17 octobre 2026.

Ce document inventorie **les appels restants à `write_derived()` dans
`headless/CMakeLists.txt`**, dans leur ordre réel. Il ne confond pas
les appels statiques avec les fichiers physiques : une cible comportant une
variable (`bits`, `unit_name`, etc.) peut produire **plusieurs fichiers**.
Toutes les variantes ne sont pas compilées au même moment ; le profil
développement, les options JIT expérimentales, les backends et le build
natif sélectionnent chacun leur sous-ensemble.

L'inventaire complémentaire `docs/EDEN_ACTIVE_SOURCE_CATALOG.md` suit les
186 fichiers de code et en-têtes dans `vendor/encore-active`,
y compris les backports de production et la dépendance graphique. Cette
couverture ne s'additionne pas aux sites de génération CMake ci-dessous.

## Synthèse vérifiable

- **53 appels générateurs** encore dans CMake ; contre **75 avant**
  les migrations de `fs_i_file.cpp`, `fs_i_storage.cpp`, `fs_i_filesystem.cpp`, `nvhost_ctrl.cpp` et `buffer_queue_producer.cpp`, puis `service.cpp` et `svc_ipc.cpp`. Le corps de la fonction utilitaire
  `write_derived` n'est pas compté comme une invocation.
- **64 lectures `file(READ`** et **201 remplacements
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
| G01 | `${PORT_BUILD_DIR}/buffer-pages/video_core/buffer_cache/buffer_cache.h` | Cache/outil natif | En-tête source | 62 |
| G02 | `${PORT_BUILD_DIR}/sparse/common/sparse_large_vector.h` | Dynarmic/JIT | En-tête source | 254 |
| G03 | `${PORT_BUILD_DIR}/include/${code_relative}.h` | Dynarmic/JIT | En-tête source | 288 |
| G04 | `${PORT_BUILD_DIR}/block_of_code.cpp` | Dynarmic/JIT | Unité source | 352 |
| G05 | `${PORT_BUILD_DIR}/include/dynarmic/backend/x64/a64_emit_x64.h` | Dynarmic/JIT | En-tête source | 376 |
| G06 | `${PORT_BUILD_DIR}/a${bits}_emit_x64.cpp` | Dynarmic/JIT | Unité source | 388 |
| G07 | `${PORT_BUILD_DIR}/include/dynarmic/backend/block_range_information.h` | Dynarmic/JIT | En-tête source | 400 |
| G08 | `${PORT_BUILD_DIR}/emit_x64.cpp` | Dynarmic/JIT | Unité source | 430 |
| G09 | `${PORT_BUILD_DIR}/scalar_impl.cpp` | Dynarmic/JIT | Unité source | 455 |
| G10 | `${PORT_BUILD_DIR}/a64_translate.cpp` | Dynarmic/JIT | Unité source | 458 |
| G11 | `${PORT_BUILD_DIR}/opt_passes.cpp` | Dynarmic/JIT | Unité source | 474 |
| G12 | `${PORT_BUILD_DIR}/include/${memory_inc}` | Dynarmic/JIT | Cible variable | 596 |
| G13 | `${PORT_BUILD_DIR}/include/${memory_relative}` | Dynarmic/JIT | Cible variable | 616 |
| G14 | `${PORT_BUILD_DIR}/${memory_unit}` | Dynarmic/JIT | Cible variable | 627 |
| G15 | `${PORT_BUILD_DIR}/spin_lock_x64.cpp` | Dynarmic/JIT | Unité source | 642 |
| G16 | `${PORT_BUILD_DIR}/a64_interface.cpp` | Dynarmic/JIT | Unité source | 737 |
| G17 | `${PORT_BUILD_DIR}/a32_interface.cpp` | Dynarmic/JIT | Unité source | 765 |
| G18 | `${derived}` | CPU | Cible variable | 937 |
| G19 | `${PORT_BUILD_DIR}/physical_core.cpp` | CPU | Unité source | 1019 |
| G20 | `${PORT_BUILD_DIR}/memory.cpp` | Mémoire/chargement | Unité source | 1104 |
| G21 | `${eden_native_memory_tu}` | Mémoire/chargement | Cible variable | 1254 |
| G22 | `${PORT_BUILD_DIR}/core.cpp` | Mémoire/chargement | Unité source | 1335 |
| G23 | `${PORT_BUILD_DIR}/nso.cpp` | Mémoire/chargement | Unité source | 1410 |
| G24 | `${PORT_BUILD_DIR}/ips_layer.cpp` | Mémoire/chargement | Unité source | 1528 |
| G25 | `${PORT_BUILD_DIR}/patch_manager.cpp` | Mémoire/chargement | Unité source | 1542 |
| G26 | `${PORT_BUILD_DIR}/vi_conductor.cpp` | Kernel/IPC/entrées | Unité source | 1581 |
| G27 | `${PORT_BUILD_DIR}/nvdrv_container.cpp` | Kernel/IPC/entrées | Unité source | 1597 |
| G28 | `${PORT_BUILD_DIR}/npad_pause_diag.cpp` | Kernel/IPC/entrées | Unité source | 1660 |
| G29 | `${PORT_BUILD_DIR}/include/${ioctl_header}` | Kernel/IPC/entrées | Cible variable | 1677 |
| G30 | `${PORT_BUILD_DIR}/k_page_table_base.cpp` | Kernel/IPC/entrées | Unité source | 1716 |
| G31 | `${PORT_BUILD_DIR}/k_process.cpp` | Kernel/IPC/entrées | Unité source | 1939 |
| G32 | `${PORT_BUILD_DIR}/include/${server_header}` | Kernel/IPC/entrées | Cible variable | 1956 |
| G33 | `${PORT_BUILD_DIR}/server_manager.cpp` | Kernel/IPC/entrées | Unité source | 2013 |
| G34 | `${PORT_BUILD_DIR}/kernel.cpp` | Kernel/IPC/entrées | Unité source | 2026 |
| G35 | `${PORT_BUILD_DIR}/emulated_controller.cpp` | Kernel/IPC/entrées | Unité source | 2065 |
| G36 | `${PORT_BUILD_DIR}/npad.cpp` | Kernel/IPC/entrées | Unité source | 2093 |
| G37 | `${eden_gpu_span_tu}` | Audio/graphique | Cible variable | 2167 |
| G38 | `${PORT_BUILD_DIR}/gl_texture_cache.cpp` | Audio/graphique | Unité source | 2248 |
| G39 | `${PORT_BUILD_DIR}/gl_rasterizer.cpp` | Audio/graphique | Unité source | 2260 |
| G40 | `${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h` | Audio/graphique | En-tête source | 2322 |
| G41 | `${PORT_BUILD_DIR}/gpu_thread.cpp` | GPU/vidéo | Unité source | 2471 |
| G42 | `${PORT_BUILD_DIR}/include/video_core/gpu_thread.h` | GPU/vidéo | En-tête source | 2476 |
| G43 | `${PORT_BUILD_DIR}/${unit_name}.cpp` | GPU/vidéo | Unité source | 2527 |
| G44 | `${PORT_BUILD_DIR}/gpu.cpp` | GPU/vidéo | Unité source | 2623 |
| G45 | `${PORT_BUILD_DIR}/maxwell_3d.cpp` | GPU/vidéo | Unité source | 2643 |
| G46 | `${PORT_BUILD_DIR}/shader_environment.cpp` | GPU/vidéo | Unité source | 2658 |
| G47 | `${PORT_BUILD_DIR}/texture_cache_util.cpp` | GPU/vidéo | Unité source | 2699 |
| G48 | `${PORT_BUILD_DIR}/audited_guest_dns.cpp` | Runtime/FS/réseau | Unité source | 2823 |
| G49 | `${PORT_BUILD_DIR}/audited_guest_bsd.cpp` | Runtime/FS/réseau | Unité source | 2885 |
| G50 | `${PORT_BUILD_DIR}/network.cpp` | Runtime/FS/réseau | Unité source | 2963 |
| G51 | `${PORT_BUILD_DIR}/app_heap.c` | Runtime/FS/réseau | Unité source | 3026 |
| G52 | `${eden_app_crt}` | Runtime/FS/réseau | Cible variable | 3038 |
| G53 | `${PORT_BUILD_DIR}/include/loading_scene_glsl.h` | Ressources | Ressource générée | 3223 |
<!-- OVERRIDE_GENERATORS_END -->

## Prochain ordre de migration

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

## Générateurs des modules CMake inclus — inventaire complémentaire

Le tableau principal n'indexe que `headless/CMakeLists.txt`. Les modules
inclus par ce fichier contiennent **21 autres appels `write_derived()`**
dans 6 fichiers. Le total de **74 appels** (63 + 21) est donc un **nombre de
sites CMake**, pas un dénombrement des fichiers réellement produits à
l'exécution. Un module inclus peut définir des macros sans les exécuter,
et plusieurs sorties sont explicitement conditionnées.

<!-- MODULE_GENERATORS_START -->
| ID | Module CMake | Sortie dérivée | Porte / périmètre |
| --- | --- | --- | --- |
| M01 | `headless/dynarmic/reg_alloc.cmake` | `${PORT_BUILD_DIR}/include/dynarmic/backend/x64/reg_alloc.h` | Dynarmic |
| M02 | `headless/dynarmic/reg_alloc.cmake` | `${PORT_BUILD_DIR}/reg_alloc.cpp` | Dynarmic |
| M03 | `headless/dynarmic/shared-jit.cmake` | `${PORT_BUILD_DIR}/include/${eden_jitstate_relative}` | Shared JIT OFF par défaut |
| M04 | `headless/dynarmic/shared-jit.cmake` | `${PORT_BUILD_DIR}/include/dynarmic/backend/x64/jit_group.h` | Shared JIT OFF par défaut |
| M05 | `headless/dynarmic/shared-jit.cmake` | `${PORT_BUILD_DIR}/callback.cpp` | Shared JIT OFF par défaut |
| M06 | `headless/gpu_native_observability.cmake` | `${PORT_BUILD_DIR}/maxwell_prmt_observed.cpp` | PS5_NATIVE |
| M07 | `headless/gpu_native_observability.cmake` | `${PORT_BUILD_DIR}/sw_blitter_sized.cpp` | PS5_NATIVE |
| M08 | `headless/gpu_native_observability.cmake` | `${PORT_BUILD_DIR}/fermi_2d_observed.cpp` | PS5_NATIVE |
| M09 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/include/video_core/memory_manager.h` | Pont différé OFF |
| M10 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/deferred-core/core/gpu_dirty_memory_manager.h` | Pont différé OFF |
| M11 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/memory_manager_deferred.cpp` | Pont différé OFF |
| M12 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/vulkan_rasterizer_deferred.cpp` | Pont différé OFF |
| M13 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/dma_pusher_deferred.cpp` | Pont différé OFF |
| M14 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/maxwell_dma_deferred.cpp` | Pont différé OFF |
| M15 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/kepler_compute_deferred.cpp` | Pont différé OFF |
| M16 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/engine_upload_deferred.cpp` | Pont différé OFF |
| M17 | `headless/guest_write_deferred_bridge.cmake` | `${PORT_BUILD_DIR}/memory-ps5-deferred.cpp` | Pont différé OFF |
| M18 | `headless/jit-alias.cmake` | `${PORT_BUILD_DIR}/include/xbyak/xbyak.h` | JIT/alias |
| M19 | `headless/jit-alias.cmake` | `${PORT_BUILD_DIR}/constant_pool.cpp` | JIT/alias |
| M20 | `headless/scalar-memory.cmake` | `${PORT_BUILD_DIR}/scalar_emit_x64_vector.cpp` | Emetteur scalaire |
| M21 | `headless/scalar-memory.cmake` | `${PORT_BUILD_DIR}/scalar_emit_x64_data_processing.cpp` | Emetteur scalaire |
<!-- MODULE_GENERATORS_END -->

## Patches de sources hors générateurs CMake

**46 fichiers `.patch`** se trouvent encore dans `headless/backports/`.
Ils ne sont comptés ni dans les **74 sites** `write_derived()`, ni dans
les **7 modules indirects** ci-dessous :

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

## Overrides indirects sans `write_derived()` local

Ces **7 modules supplémentaires** ne sont pas inclus dans le total de
**74 appels**. Deux matérialisent leur sortie via `file(WRITE)` ;
les cinq autres modifient une variable-source écrite ensuite par un
générateur du CMake principal. Ce sont **7 modules**, pas nécessairement
7 fichiers réellement produits.

<!-- INDIRECT_OVERRIDES_START -->
| ID | Module | Origine / source réécrite | Mécanisme | État |
| --- | --- | --- | --- | --- |
| X01 | `headless/macro_recovery.cmake` | `MACRO_INPUT` → `MACRO_OUTPUT` | `file(WRITE)` puis `configure_file(COPYONLY)` | Non migré |
| X02 | `headless/slot_vector_recovery.cmake` | `SLOT_VECTOR_INPUT` → `SLOT_VECTOR_OUTPUT` | `file(WRITE)` puis `configure_file(COPYONLY)` | Non migré |
| X03 | `headless/checked-fastmem.cmake` | `memory_emitter`, `memory_source` | Modifications de l'émetteur JIT dans les variables CMake | Non migré |
| X04 | `headless/native_gpu_granular_bounds.cmake` | `eden_gpu_span_src` | Contrôles des plages GPU avant génération | Non migré |
| X05 | `headless/native_guest_range_overflow.cmake` | `eden_cpu_memory` | Contrôle de débordement des adresses mémoire avant génération | Non migré |
| X06 | `headless/native_jit_memory_read_guard.cmake` | `wrapper` | Contrôle des lectures de mémoire invitée avant génération | Non migré |
| X07 | `headless/physical_core_interrupt_atomic.cmake` | `physical_core_source` | Accès atomiques aux interruptions avant génération | Non migré |
<!-- INDIRECT_OVERRIDES_END -->

Le sélecteur `headless/vulkan.cmake` copie des fichiers déjà maintenus
dans `vendor/encore-active` : ce n'est pas une réécriture C++ par
substitution. `headless/inject.cmake` orchestre l'inclusion ; le
toolchain `headless/ps5.cmake` configure compilation et édition de liens.
Ils ne sont donc pas ajoutés artificiellement comme huitième ou
neuvième générateur.

Deux autres modules (`macro_recovery.cmake` et
`slot_vector_recovery.cmake`) créent une source ou un en-tête dérivé au
moyen de `file(WRITE)` et `configure_file(COPYONLY)`, **sans appeler**
`write_derived()`. Les modules `checked-fastmem.cmake`,
`native_gpu_granular_bounds.cmake`, `native_guest_range_overflow.cmake`,
`native_jit_memory_read_guard.cmake` et
`physical_core_interrupt_atomic.cmake` modifient des variables-source
qui sont générées ensuite dans le CMake principal : **absence d'appel
`write_derived()` local ne signifie donc pas absence d'override**.

À l'inverse, `headless/vulkan.cmake` copie déjà les sources réellement
maintenues dans `vendor/encore-active/eden-vulkan`, et le module HLE
`vendor/encore-active/eden-threading/native-hle-overrides.cmake`
sélectionne des sources et en-têtes maintenus. Leur CMake est un
sélecteur de build, pas un nouveau patch C++ par remplacement de texte.

**Priorité de migration :** garder le pont différé expérimental OFF,
ne pas activer le JIT partagé pour réduire artificiellement le nombre
de générateurs, migrer d'abord les unités normales/DEV réellement
sélectionnées avec preuve d'identité et sans changer leur comportement.
