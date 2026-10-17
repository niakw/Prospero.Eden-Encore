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

- **68 appels générateurs** encore dans CMake ; contre **75 avant**
  les migrations de `fs_i_file.cpp`, `fs_i_storage.cpp`, `fs_i_filesystem.cpp`, `nvhost_ctrl.cpp` et `buffer_queue_producer.cpp`, puis `service.cpp` et `svc_ipc.cpp`. Le corps de la fonction utilitaire
  `write_derived` n'est pas compté comme une invocation.
- **79 lectures `file(READ`** et **225 remplacements
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
| G21 | `${PORT_BUILD_DIR}/memory.cpp` | Mémoire/chargement | Unité source | 1101 |
| G22 | `${eden_native_memory_tu}` | Mémoire/chargement | Cible variable | 1251 |
| G23 | `${PORT_BUILD_DIR}/core.cpp` | Mémoire/chargement | Unité source | 1332 |
| G24 | `${PORT_BUILD_DIR}/nso.cpp` | Mémoire/chargement | Unité source | 1407 |
| G25 | `${PORT_BUILD_DIR}/fsmitm_romfsbuild.cpp` | Mémoire/chargement | Unité source | 1421 |
| G26 | `${PORT_BUILD_DIR}/ips_layer.cpp` | Mémoire/chargement | Unité source | 1525 |
| G27 | `${PORT_BUILD_DIR}/patch_manager.cpp` | Mémoire/chargement | Unité source | 1539 |
| G28 | `${PORT_BUILD_DIR}/vi_conductor.cpp` | Kernel/IPC/entrées | Unité source | 1578 |
| G29 | `${PORT_BUILD_DIR}/nvdrv_container.cpp` | Kernel/IPC/entrées | Unité source | 1594 |
| G30 | `${PORT_BUILD_DIR}/npad_pause_diag.cpp` | Kernel/IPC/entrées | Unité source | 1657 |
| G31 | `${PORT_BUILD_DIR}/include/${ioctl_header}` | Kernel/IPC/entrées | Cible variable | 1674 |
| G32 | `${PORT_BUILD_DIR}/k_page_table_base.cpp` | Kernel/IPC/entrées | Unité source | 1713 |
| G33 | `${PORT_BUILD_DIR}/k_process.cpp` | Kernel/IPC/entrées | Unité source | 1936 |
| G34 | `${PORT_BUILD_DIR}/include/${server_header}` | Kernel/IPC/entrées | Cible variable | 1953 |
| G35 | `${PORT_BUILD_DIR}/server_manager.cpp` | Kernel/IPC/entrées | Unité source | 2010 |
| G36 | `${PORT_BUILD_DIR}/kernel.cpp` | Kernel/IPC/entrées | Unité source | 2023 |
| G37 | `${PORT_BUILD_DIR}/emulated_controller.cpp` | Kernel/IPC/entrées | Unité source | 2062 |
| G38 | `${PORT_BUILD_DIR}/npad.cpp` | Kernel/IPC/entrées | Unité source | 2090 |
| G39 | `${PORT_BUILD_DIR}/sink_stream.cpp` | Audio/graphique | Unité source | 2120 |
| G40 | `${PORT_BUILD_DIR}/video_core.cpp` | Audio/graphique | Unité source | 2148 |
| G41 | `${eden_gpu_span_tu}` | Audio/graphique | Cible variable | 2168 |
| G42 | `${PORT_BUILD_DIR}/gl_buffer_cache.cpp` | Audio/graphique | Unité source | 2212 |
| G43 | `${PORT_BUILD_DIR}/gl_query_cache.cpp` | Audio/graphique | Unité source | 2226 |
| G44 | `${PORT_BUILD_DIR}/gl_texture_cache.cpp` | Audio/graphique | Unité source | 2248 |
| G45 | `${PORT_BUILD_DIR}/gl_rasterizer.cpp` | Audio/graphique | Unité source | 2260 |
| G46 | `${PORT_BUILD_DIR}/renderer_opengl.cpp` | Audio/graphique | Unité source | 2264 |
| G47 | `${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h` | Audio/graphique | En-tête source | 2324 |
| G48 | `${PORT_BUILD_DIR}/gpu_thread.cpp` | GPU/vidéo | Unité source | 2473 |
| G49 | `${PORT_BUILD_DIR}/include/video_core/gpu_thread.h` | GPU/vidéo | En-tête source | 2478 |
| G50 | `${PORT_BUILD_DIR}/${unit_name}.cpp` | GPU/vidéo | Unité source | 2529 |
| G51 | `${PORT_BUILD_DIR}/gpu.cpp` | GPU/vidéo | Unité source | 2625 |
| G52 | `${PORT_BUILD_DIR}/maxwell_3d.cpp` | GPU/vidéo | Unité source | 2645 |
| G53 | `${PORT_BUILD_DIR}/shader_environment.cpp` | GPU/vidéo | Unité source | 2660 |
| G54 | `${PORT_BUILD_DIR}/texture_cache_util.cpp` | GPU/vidéo | Unité source | 2701 |
| G55 | `${PORT_BUILD_DIR}/path_util.cpp` | Runtime/FS/réseau | Unité source | 2723 |
| G56 | `${PORT_BUILD_DIR}/thread.cpp` | Runtime/FS/réseau | Unité source | 2728 |
| G57 | `${PORT_BUILD_DIR}/cpu_features.cpp` | Runtime/FS/réseau | Unité source | 2742 |
| G58 | `${PORT_BUILD_DIR}/fs.cpp` | Runtime/FS/réseau | Unité source | 2748 |
| G59 | `${PORT_BUILD_DIR}/audited_guest_dns.cpp` | Runtime/FS/réseau | Unité source | 2828 |
| G60 | `${PORT_BUILD_DIR}/audited_guest_bsd.cpp` | Runtime/FS/réseau | Unité source | 2890 |
| G61 | `${PORT_BUILD_DIR}/include/core/file_sys/bis_factory.h` | Runtime/FS/réseau | En-tête source | 2897 |
| G62 | `${PORT_BUILD_DIR}/bis_factory.cpp` | Runtime/FS/réseau | Unité source | 2908 |
| G63 | `${PORT_BUILD_DIR}/filesystem.cpp` | Runtime/FS/réseau | Unité source | 2917 |
| G64 | `${PORT_BUILD_DIR}/network.cpp` | Runtime/FS/réseau | Unité source | 2969 |
| G65 | `${PORT_BUILD_DIR}/network_interface.cpp` | Runtime/FS/réseau | Unité source | 2978 |
| G66 | `${PORT_BUILD_DIR}/app_heap.c` | Runtime/FS/réseau | Unité source | 3031 |
| G67 | `${eden_app_crt}` | Runtime/FS/réseau | Cible variable | 3043 |
| G68 | `${PORT_BUILD_DIR}/include/loading_scene_glsl.h` | Ressources | Ressource générée | 3228 |
<!-- OVERRIDE_GENERATORS_END -->

## Prochain ordre de migration

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

## Générateurs des modules CMake inclus — inventaire complémentaire

Le tableau principal n'indexe que `headless/CMakeLists.txt`. Les modules
inclus par ce fichier contiennent **21 autres appels `write_derived()`**
dans 6 fichiers. Le total de **89 appels** (68 + 21) est donc un **nombre de
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

## Overrides indirects sans `write_derived()` local

Ces **7 modules supplémentaires** ne sont pas inclus dans le total de
**89 appels**. Deux matérialisent leur sortie via `file(WRITE)` ;
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
