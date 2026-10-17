# Encore Active : vrais overrides de sources

`vendor/sources/eden` = original conservé ; `vendor/encore-active` = versions maintenues.

| Chemin | Usage |
| --- | --- |
| `eden-threading/src/core/hle/kernel/k_thread.cpp` | Source compilée remplaçant l'original ; finalisation hors verrou |
| `eden-threading/src/core/hle/kernel/slab_helpers.h`, `k_worker_task_manager.h` | En-têtes maintenus copiés tels quels avant compilation, sans patch CMake |
| `eden-threading/src/core/hle/kernel/k_scheduler.cpp`, `k_thread.h`, `k_slab_heap.h` | Overrides coordonnés du threading |
| `eden-threading/src/core/hle/kernel/k_address_arbiter.cpp`, `k_condition_variable.cpp` | Sources HLE natives |
| `eden-threading/src/core/hle/kernel/svc/*.cpp` | Sources SVC natives |
| `eden-sync/src/core/hle/kernel/k_synchronization_object.h` | En-tête natif de synchronisation, aliasing corrigé |
| `eden-threading/native-hle-overrides.cmake` | Sélection de sources CMake, **pas** un correctif C++ généré |
| `eden-build/src/CMakeLists.txt` | Configuration de build maintenue copiée avant compilation |
| `eden-core/src/common/thread.cpp`, `src/common/fs/fs.cpp` | Sources runtime natives maintenues ; noms de workers et énumération des répertoires |
| `eden-core/src/core/hle/kernel/svc/svc_ipc.cpp`, `src/core/hle/service/service.cpp` | Mesures IPC/HLE du profil diagnostic, sélectionnées sans génération CMake |
| `eden-core/src/core/hle/service/{filesystem,nvdrv,nvnflinger}/` | Sources diagnostiques de fichiers, événements NVDRV et files de présentation |
| `eden-gpu`, `eden-vulkan`, `eden-core`, `ps5-mesa` et autres dossiers | Autres adaptations maintenues ; voir `docs/EDEN_OVERRIDE_MIGRATION_INVENTORY.md` |

Chaîne HLE : `headless/CMakeLists.txt` -> `eden-threading/native-hle-overrides.cmake` -> fichiers C++/en-têtes maintenus.

Tests associés : `tools/verify/hle/`. Ces tests ne sont pas inclus dans l'application native.

Pour le runtime et les diagnostics, `headless/CMakeLists.txt` ne fait
que sélectionner les unités maintenues et retirer la source d'origine de
la cible concernée. Il ne doit plus générer de copies C++ pour ces unités.
Les sources amont épinglées restent inchangées dans `vendor/sources/eden`.

L'inventaire couvre **66 appels générateurs** du CMake principal, **21**
dans les modules et **7 modules indirects** suivis séparément ; ce ne sont
pas des décomptes de fichiers uniques. Chaque nouvelle migration doit
conserver un test de parité et de sélection native.
