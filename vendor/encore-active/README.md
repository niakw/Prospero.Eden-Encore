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
| `eden-core/src/common/cpu_features.cpp`, `src/common/fs/path_util.cpp` | Détection de fréquence TSC et racines utilisateur/cache natives, auparavant générées par CMake |
| `eden-core/src/video_core/video_core_opengl.cpp` | Fabrique OpenGL-only maintenue ; fabrique Vulkan épinglée sélectionnée intacte |
| `eden-core/include/core/file_sys/bis_factory.h`, `eden-core/src/core/file_sys/bis_factory.cpp` | ABI BIS et choix du firmware/dossiers mods maintenus hors génération CMake |
| `eden-core/src/core/file_sys/fsmitm_romfsbuild.cpp` | Contextes RomFS sans cycles de propriété ; deux types de remplacement désormais en C++ maintenu |
| `eden-core/src/audio_core/sink/sink_stream.cpp` | File PCM, upmix et trame de maintien via source audio maintenue ; anciens générateurs supprimés |
| `eden-core/src/core/hle/service/filesystem/filesystem.cpp` | Racine firmware maintenue en C++, sans unité dérivée par CMake |
| `eden-core/src/core/internal_network/network_interface.cpp` | Choix de la branche FreeBSD pour l'énumération des interfaces, sans génération CMake |
| `eden-core/src/core/hle/kernel/svc/svc_ipc.cpp`, `src/core/hle/service/service.cpp` | Mesures IPC/HLE du profil diagnostic, sélectionnées sans génération CMake |
| `eden-core/src/core/hle/service/{filesystem,nvdrv,nvnflinger}/` | Sources diagnostiques de fichiers, événements NVDRV et files de présentation |
| `eden-gpu`, `eden-vulkan`, `eden-core`, `ps5-mesa` et autres dossiers | Autres adaptations maintenues ; voir `docs/EDEN_OVERRIDE_MIGRATION_INVENTORY.md` |

Chaîne HLE : `headless/CMakeLists.txt` -> `eden-threading/native-hle-overrides.cmake` -> fichiers C++/en-têtes maintenus.

Tests associés : `tools/verify/hle/`. Ces tests ne sont pas inclus dans l'application native.

Pour le runtime et les diagnostics, `headless/CMakeLists.txt` ne fait
que sélectionner les unités maintenues et retirer la source d'origine de
la cible concernée. Il ne doit plus générer de copies C++ pour ces unités.
Les sources amont épinglées restent inchangées dans `vendor/sources/eden`.

Les 81 sources et en-têtes de `eden-backports` sont des backports livrés en
production depuis le snapshot épinglé, contrôlés par empreintes et installés
par `tools/install-vendored-eden-backports.py` (pas de `git apply` au build).

Catalogue exhaustif des fichiers C/C++ actifs : `docs/EDEN_ACTIVE_SOURCE_CATALOG.md`
(183 fichiers enregistrés, 37 chemins présents dans le graphe technique).
Le recensement des fichiers n'est pas une validation de leurs fonctions.

L'inventaire couvre **57 appels générateurs** du CMake principal, **21**
dans les modules et **7 modules indirects** suivis séparément ; ce ne sont
pas des décomptes de fichiers uniques. Chaque nouvelle migration doit
conserver un test de parité et de sélection native.

**Dette non encore consolidée ici :** `headless/backports/` contient
46 patches sur le snapshot Eden épinglé : 44 appels `apply_one` depuis
`tools/apply-eden-backports.sh` et deux patches installés depuis
`tools/install-active-core-backports.py`. Leurs chemins et leur statut
sont catalogués dans `docs/EDEN_OVERRIDE_MIGRATION_INVENTORY.md`.
Ils ne sont **pas** des sources C++ maintenues, et il ne faut pas les
compter comme 46 fichiers de compilation supplémentaires.
