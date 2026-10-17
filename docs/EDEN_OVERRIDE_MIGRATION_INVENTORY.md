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

- **74 appels générateurs** encore dans CMake ; contre **75 juste avant**
  la migration de `fs_i_file.cpp`. Le corps de la fonction utilitaire
  `write_derived` n'est pas compté comme une invocation.
- **85 lectures `file(READ`** et **232 remplacements
  `string(REPLACE`**, incluant certains usages de configuration ordinaires,
  pas seulement des réécritures de C++.
- La version diagnostique de `IFile::Read` est maintenant une source
  maintenue dans `vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp/`.
  La comparaison textuelle avec le CMake généré antérieurement est contrôlée
  par `tools/check-vendor-consolidation-debt.py`.
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
| G23 | `${PORT_BUILD_DIR}/fs_i_filesystem.cpp` | Services/HLE diag. | Unité source | 1089 |
| G24 | `${PORT_BUILD_DIR}/fs_i_storage.cpp` | Services/HLE diag. | Unité source | 1092 |
| G25 | `${PORT_BUILD_DIR}/hle_service.cpp` | Services/HLE diag. | Unité source | 1110 |
| G26 | `${PORT_BUILD_DIR}/svc_ipc.cpp` | Services/HLE diag. | Unité source | 1122 |
| G27 | `${PORT_BUILD_DIR}/memory.cpp` | Mémoire/chargement | Unité source | 1136 |
| G28 | `${eden_native_memory_tu}` | Mémoire/chargement | Cible variable | 1286 |
| G29 | `${PORT_BUILD_DIR}/core.cpp` | Mémoire/chargement | Unité source | 1367 |
| G30 | `${PORT_BUILD_DIR}/nso.cpp` | Mémoire/chargement | Unité source | 1442 |
| G31 | `${PORT_BUILD_DIR}/fsmitm_romfsbuild.cpp` | Mémoire/chargement | Unité source | 1456 |
| G32 | `${PORT_BUILD_DIR}/ips_layer.cpp` | Mémoire/chargement | Unité source | 1560 |
| G33 | `${PORT_BUILD_DIR}/patch_manager.cpp` | Mémoire/chargement | Unité source | 1574 |
| G34 | `${PORT_BUILD_DIR}/vi_conductor.cpp` | Kernel/IPC/entrées | Unité source | 1613 |
| G35 | `${PORT_BUILD_DIR}/nvdrv_container.cpp` | Kernel/IPC/entrées | Unité source | 1629 |
| G36 | `${PORT_BUILD_DIR}/npad_pause_diag.cpp` | Kernel/IPC/entrées | Unité source | 1692 |
| G37 | `${PORT_BUILD_DIR}/include/${ioctl_header}` | Kernel/IPC/entrées | Cible variable | 1709 |
| G38 | `${PORT_BUILD_DIR}/k_page_table_base.cpp` | Kernel/IPC/entrées | Unité source | 1748 |
| G39 | `${PORT_BUILD_DIR}/k_process.cpp` | Kernel/IPC/entrées | Unité source | 1971 |
| G40 | `${PORT_BUILD_DIR}/include/${server_header}` | Kernel/IPC/entrées | Cible variable | 1988 |
| G41 | `${PORT_BUILD_DIR}/server_manager.cpp` | Kernel/IPC/entrées | Unité source | 2045 |
| G42 | `${PORT_BUILD_DIR}/kernel.cpp` | Kernel/IPC/entrées | Unité source | 2058 |
| G43 | `${PORT_BUILD_DIR}/emulated_controller.cpp` | Kernel/IPC/entrées | Unité source | 2097 |
| G44 | `${PORT_BUILD_DIR}/npad.cpp` | Kernel/IPC/entrées | Unité source | 2125 |
| G45 | `${PORT_BUILD_DIR}/sink_stream.cpp` | Audio/graphique | Unité source | 2155 |
| G46 | `${PORT_BUILD_DIR}/video_core.cpp` | Audio/graphique | Unité source | 2183 |
| G47 | `${eden_gpu_span_tu}` | Audio/graphique | Cible variable | 2203 |
| G48 | `${PORT_BUILD_DIR}/gl_buffer_cache.cpp` | Audio/graphique | Unité source | 2247 |
| G49 | `${PORT_BUILD_DIR}/gl_query_cache.cpp` | Audio/graphique | Unité source | 2261 |
| G50 | `${PORT_BUILD_DIR}/gl_texture_cache.cpp` | Audio/graphique | Unité source | 2283 |
| G51 | `${PORT_BUILD_DIR}/gl_rasterizer.cpp` | Audio/graphique | Unité source | 2295 |
| G52 | `${PORT_BUILD_DIR}/renderer_opengl.cpp` | Audio/graphique | Unité source | 2299 |
| G53 | `${PORT_BUILD_DIR}/include/common/bounded_threadsafe_queue.h` | Audio/graphique | En-tête source | 2359 |
| G54 | `${PORT_BUILD_DIR}/gpu_thread.cpp` | GPU/vidéo | Unité source | 2508 |
| G55 | `${PORT_BUILD_DIR}/include/video_core/gpu_thread.h` | GPU/vidéo | En-tête source | 2513 |
| G56 | `${PORT_BUILD_DIR}/${unit_name}.cpp` | GPU/vidéo | Unité source | 2564 |
| G57 | `${PORT_BUILD_DIR}/gpu.cpp` | GPU/vidéo | Unité source | 2660 |
| G58 | `${PORT_BUILD_DIR}/maxwell_3d.cpp` | GPU/vidéo | Unité source | 2680 |
| G59 | `${PORT_BUILD_DIR}/shader_environment.cpp` | GPU/vidéo | Unité source | 2695 |
| G60 | `${PORT_BUILD_DIR}/texture_cache_util.cpp` | GPU/vidéo | Unité source | 2736 |
| G61 | `${PORT_BUILD_DIR}/path_util.cpp` | Runtime/FS/réseau | Unité source | 2758 |
| G62 | `${PORT_BUILD_DIR}/thread.cpp` | Runtime/FS/réseau | Unité source | 2763 |
| G63 | `${PORT_BUILD_DIR}/cpu_features.cpp` | Runtime/FS/réseau | Unité source | 2777 |
| G64 | `${PORT_BUILD_DIR}/fs.cpp` | Runtime/FS/réseau | Unité source | 2783 |
| G65 | `${PORT_BUILD_DIR}/audited_guest_dns.cpp` | Runtime/FS/réseau | Unité source | 2863 |
| G66 | `${PORT_BUILD_DIR}/audited_guest_bsd.cpp` | Runtime/FS/réseau | Unité source | 2925 |
| G67 | `${PORT_BUILD_DIR}/include/core/file_sys/bis_factory.h` | Runtime/FS/réseau | En-tête source | 2932 |
| G68 | `${PORT_BUILD_DIR}/bis_factory.cpp` | Runtime/FS/réseau | Unité source | 2943 |
| G69 | `${PORT_BUILD_DIR}/filesystem.cpp` | Runtime/FS/réseau | Unité source | 2952 |
| G70 | `${PORT_BUILD_DIR}/network.cpp` | Runtime/FS/réseau | Unité source | 3004 |
| G71 | `${PORT_BUILD_DIR}/network_interface.cpp` | Runtime/FS/réseau | Unité source | 3013 |
| G72 | `${PORT_BUILD_DIR}/app_heap.c` | Runtime/FS/réseau | Unité source | 3066 |
| G73 | `${eden_app_crt}` | Runtime/FS/réseau | Cible variable | 3078 |
| G74 | `${PORT_BUILD_DIR}/include/loading_scene_glsl.h` | Ressources | Ressource générée | 3263 |
<!-- OVERRIDE_GENERATORS_END -->

## Prochain ordre de migration

Le bloc `EDEN_DEV_PROFILE` de `nvhost_ctrl.cpp`,
`buffer_queue_producer.cpp`, `fs_i_storage.cpp`,
`fs_i_filesystem.cpp`, `hle_service.cpp`, puis `svc_ipc.cpp` forme
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
