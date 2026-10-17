# Eden Encore — inventaire des transformations CMake encore actives

**Branche :** `dev/ps5-sparse-jit`. **Dernière revue :** 17 octobre 2026.

Ce document inventorie **les appels restants à `write_derived()` dans
`headless/CMakeLists.txt`**, dans leur ordre réel. Il ne confond pas
les appels statiques avec les fichiers physiques : une cible comportant une
variable (`bits`, `unit_name`, etc.) peut produire **plusieurs fichiers**.
Toutes les variantes ne sont pas compilées au même moment ; le profil
développement, les options JIT expérimentales, les backends et le build
natif sélectionnent chacun leur sous-ensemble.

## Synthèse vérifiable

- **73 appels générateurs** encore dans CMake ; contre **75 juste avant**
  les migrations de `fs_i_file.cpp` et `fs_i_storage.cpp`. Le corps de la fonction utilitaire
  `write_derived` n'est pas compté comme une invocation.
- **84 lectures `file(READ`** et **231 remplacements
  `string(REPLACE`**, incluant certains usages de configuration ordinaires,
  pas seulement des réécritures de C++.
- Les versions diagnostiques de `IFile::Read` et `IStorage::Read` sont
  maintenant des sources maintenues dans `vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp/`.
  Leur comparaison textuelle avec le CMake généré antérieurement est contrôlée
  par `tools/check-vendor-consolidation-debt.py`, et leurs horloges
  de profilage restent vérifiées par `tools/check-ps5-quiet-cpu-io-clocks.py`
  directement à partir des fichiers maintenus.
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
| G02 | `${PORT_BUILD_DIR}/emutls.c` | Cache/outil natif | Unité source | 133 |
| G03 | `${PORT_BUILD_DIR}/sparse/common/sparse_large_vector.h` | Dynarmic/JIT | En-tête source | 251 |
| G04 | `${PORT_BUILD_DIR}/include/${code_relative}.h` | Dynarmic/JIT | En-tête source | 285 |
| G05 | `${PORT_BUILD_DIR}/block_of_code.cpp` | Dynarmic/JIT | Unité source | 349 |
| G06 | `${PORT_BUILD_DIR}/include/dynarmic/backend/x64/a64_emit_x64.h` | Dynarmic/JIT | En-tête source | 373 |
| G07 | `${PORT_BUILD_DIR}/a${bits}_emit_x64.cpp` | Dynarmic/JIT | Unité source | 385 |
| G08 | `${PORT_BUILD_DIR}/include/dynarmic/backend/block_range_information.h` | Dynarmic/JIT | En-tête source | 397 |
| G09 | `${PORT_BUILD_DIR}/emit_x64.cpp` | Dynarmic/JIT | Unité source | 427 |
| G10 | `${PORT_BUILD_DIR}/scalar_impl.cpp` | Dynarmic/JIT | Unité source | 452 |
| G11 | `${PORT_BUILD_DIR}/a64_translate.cpp` | Dynarmic/JIT | Unité source | 455 |
| G12 | `${PORT_BUILD_DIR}/opt_passes.cpp` | Dynarmic/JIT | Unité source | 471 |
| G13 | `${PORT_BUILD_DIR}/include/${memory_inc}` | Dynarmic/JIT | Cible variable | 593 |
| G14 | `${PORT_BUILD_DIR}/include/${memory_relative}` | Dynarmic/JIT | Cible variable | 613 |
| G15 | `${PORT_BUILD_DIR}/${memory_unit}` | Dynarmic/JIT | Cible variable | 624 |
| G16 | `${PORT_BUILD_DIR}/spin_lock_x64.cpp` | Dynarmic/JIT | Unité source | 639 |
| G17 | `${PORT_BUILD_DIR}/a64_interface.cpp` | Dynarmic/JIT | Unité source | 734 |
| G18 | `${PORT_BUILD_DIR}/a32_interface.cpp` | Dynarmic/JIT | Unité source | 762 |
| G19 | `${derived}` | CPU | Cible variable | 934 |
| G20 | `${PORT_BUILD_DIR}/physical_core.cpp` | CPU | Unité source | 1016 |
| G21 | `${PORT_BUILD_DIR}/nvhost_ctrl.cpp` | Services/HLE diag. | Unité source | 1038 |
| G22 | `${PORT_BUILD_DIR}/buffer_queue_producer.cpp` | Services/HLE diag. | Unité source | 1048 |
| G23 | `${PORT_BUILD_DIR}/fs_i_filesystem.cpp` | Services/HLE diag. | Unité source | 1086 |
| G24 | `${PORT_BUILD_DIR}/hle_service.cpp` | Services/HLE diag. | Unité source | 1106 |
| G25 | `${PORT_BUILD_DIR}/svc_ipc.cpp` | Services/HLE diag. | Unité source | 1118 |
| G26 | `${PORT_BUILD_DIR}/memory.cpp` | Mémoire/chargement | Unité source | 1132 |
| G27 | `${eden_native_memory_tu}` | Mémoire/chargement | Cible variable | 1282 |
| G28 | `${PORT_BUILD_DIR}/core.cpp` | Mémoire/chargement | Unité source | 1363 |
| G29 | `${PORT_BUILD_DIR}/nso.cpp` | Mémoire/chargement | Unité source | 1438 |
| G30 | `${PORT_BUILD_DIR}/fsmitm_romfsbuild.cpp` | Mémoire/chargement | Unité source | 1452 |
| G31 | `${PORT_BUILD_DIR}/ips_layer.cpp` | Mémoire/chargement | Unité source | 1556 |
| G32 | `${PORT_BUILD_DIR}/patch_manager.cpp` | Mémoire/chargement | Unité source | 1570 |
| G33 | `${PORT_BUILD_DIR}/vi_conductor.cpp` | Kernel/IPC/entrées | Unité source | 1609 |
| G34 | `${PORT_BUILD_DIR}/nvdrv_container.cpp` | Kernel/IPC/entrées | Unité source | 1625 |
| G35 | `${PORT_BUILD_DIR}/npad_pause_diag.cpp` | Kernel/IPC/entrées | Unité source | 1688 |
| G36 | `${PORT_BUILD_DIR}/include/${ioctl_header}` | Kernel/IPC/entrées | Cible variable | 1705 |
| G37 | `${PORT_BUILD_DIR}/k_page_table_base.cpp` | Kernel/IPC/entrées | Unité source | 1744 |
| G38 | `${PORT_BUILD_DIR}/k_process.cpp` | Kernel/IPC/entrées | Unité source | 1967 |
| G39 | `${PORT_BUILD_DIR}/include/${server_header}` | Kernel/IPC/entrées | Cible variable | 1984 |
| G40 | `${PORT_BUILD_DIR}/server_manager.cpp` | Kernel/IPC/entrées | Unité source | 2041 |
| G41 | `${PORT_BUILD_DIR}/kernel.cpp` | Kernel/IPC/entrées | Unité source | 2054 |
| G42 | `${PORT_BUILD_DIR}/emulated_controller.cpp` | Kernel/IPC/entrées | Unité source | 2093 |
| G43 | `${PORT_BUILD_DIR}/npad.cpp` | Kernel/IPC/entrées | Unité source | 2121 |
| G44 | `${PORT_BUILD_DIR}/sink_stream.cpp` | Audio/graphique | Unité source | 2151 |
| G45 | `${PORT_BUILD_DIR}/video_core.cpp` | Audio/graphique | Unité source | 2179 |
| G46 | `${eden_gpu_span_tu}` | Audio/graphique | Cible variable | 2199 |
| G47 | `${PORT_BUILD_DIR}/gl_buffer_cache.cpp` | Audio/graphique | Unité source | 2243 |
| G48 | `${PORT_BUILD_DIR}/gl_query_cache.cpp` | Audio/graphique | Unité source | 2257 |
| G49 | `${PORT_BUILD_DIR}/gl_texture_cache.cpp` | Audio/graphique | Unité source | 2279 |
| G50 | `${PORT_BUILD_DIR}/gl_rasterizer.cpp` | Audio/graphique | Unité source | 2291 |
| G51 | `${PORT_BUILD_DIR}/renderer_opengl.cpp` | Audio/graphique | Unité source | 2295 |
| G52 | `${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h` | Audio/graphique | En-tête source | 2355 |
| G53 | `${PORT_BUILD_DIR}/gpu_thread.cpp` | GPU/vidéo | Unité source | 2504 |
| G54 | `${PORT_BUILD_DIR}/include/video_core/gpu_thread.h` | GPU/vidéo | En-tête source | 2509 |
| G55 | `${PORT_BUILD_DIR}/${unit_name}.cpp` | GPU/vidéo | Unité source | 2560 |
| G56 | `${PORT_BUILD_DIR}/gpu.cpp` | GPU/vidéo | Unité source | 2656 |
| G57 | `${PORT_BUILD_DIR}/maxwell_3d.cpp` | GPU/vidéo | Unité source | 2676 |
| G58 | `${PORT_BUILD_DIR}/shader_environment.cpp` | GPU/vidéo | Unité source | 2691 |
| G59 | `${PORT_BUILD_DIR}/texture_cache_util.cpp` | GPU/vidéo | Unité source | 2732 |
| G60 | `${PORT_BUILD_DIR}/path_util.cpp` | Runtime/FS/réseau | Unité source | 2754 |
| G61 | `${PORT_BUILD_DIR}/thread.cpp` | Runtime/FS/réseau | Unité source | 2759 |
| G62 | `${PORT_BUILD_DIR}/cpu_features.cpp` | Runtime/FS/réseau | Unité source | 2773 |
| G63 | `${PORT_BUILD_DIR}/fs.cpp` | Runtime/FS/réseau | Unité source | 2779 |
| G64 | `${PORT_BUILD_DIR}/audited_guest_dns.cpp` | Runtime/FS/réseau | Unité source | 2859 |
| G65 | `${PORT_BUILD_DIR}/audited_guest_bsd.cpp` | Runtime/FS/réseau | Unité source | 2921 |
| G66 | `${PORT_BUILD_DIR}/include/core/file_sys/bis_factory.h` | Runtime/FS/réseau | En-tête source | 2928 |
| G67 | `${PORT_BUILD_DIR}/bis_factory.cpp` | Runtime/FS/réseau | Unité source | 2939 |
| G68 | `${PORT_BUILD_DIR}/filesystem.cpp` | Runtime/FS/réseau | Unité source | 2948 |
| G69 | `${PORT_BUILD_DIR}/network.cpp` | Runtime/FS/réseau | Unité source | 3000 |
| G70 | `${PORT_BUILD_DIR}/network_interface.cpp` | Runtime/FS/réseau | Unité source | 3009 |
| G71 | `${PORT_BUILD_DIR}/app_heap.c` | Runtime/FS/réseau | Unité source | 3062 |
| G72 | `${eden_app_crt}` | Runtime/FS/réseau | Cible variable | 3074 |
| G73 | `${PORT_BUILD_DIR}/include/loading_scene_glsl.h` | Ressources | Ressource générée | 3259 |
<!-- OVERRIDE_GENERATORS_END -->

## Prochain ordre de migration

Le bloc `EDEN_DEV_PROFILE` de `nvhost_ctrl.cpp`,
`buffer_queue_producer.cpp`, `fs_i_filesystem.cpp`, `hle_service.cpp`, puis `svc_ipc.cpp` forme
un groupe **d'observation** encore généré ; le déplacer exige de conserver
les points d'échantillonnage, les compteurs et le comportement hors diagnostic.
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

## Générateurs des modules CMake inclus — inventaire complémentaire

Le tableau principal n'indexe que `headless/CMakeLists.txt`. Les modules
inclus par ce fichier contiennent **21 autres appels `write_derived()`**
dans 6 fichiers. Le total de **94 appels** (73 + 21) est donc un **nombre de
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
