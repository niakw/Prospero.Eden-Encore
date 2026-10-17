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
| `eden-gpu`, `eden-vulkan`, `eden-core`, `ps5-mesa` et autres dossiers | Autres adaptations maintenues, à inventorier séparément |

Chaîne HLE : `headless/CMakeLists.txt` -> `eden-threading/native-hle-overrides.cmake` -> fichiers C++/en-têtes maintenus.

Tests associés : `tools/verify/hle/`. Ces tests ne sont pas inclus dans l'application native.
