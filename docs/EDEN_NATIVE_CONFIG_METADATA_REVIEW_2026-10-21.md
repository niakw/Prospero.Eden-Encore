# Eden Encore — quatre propriétaires de configuration, sauvegardes et diagnostic

**21 octobre 2026 — HEAD `fb533b652`.** Source-level inspection, distincte de la qualification console.

Ces quatre chemins, même lorsqu'ils sont situés sous `headless/` et liés au binaire du jeu, assurent surtout des fonctions de configuration, de gestion de bibliothèque et de diagnostic opt-in ; ils ne justifient aucun nouveau patch de la boucle GPU/JIT sans mesure ciblée. Chacun reste suivi par son **Git blob exact** et par son contrat original.

| Fichier | Contrat | Constat du code et décision |
| --- | --- | --- |
| `headless/ryujinx_saves.h` | `U63` | Import/export de fichiers Ryujinx via filesystem, avec interdiction de suivre les symlinks. N'est pas parcouru pendant les instructions invitées ni les commandes GPU ; associé à la gestion des sauvegardes depuis l'interface. |
| `headless/settings_store.h` | `U75` | Lecture/migration/écriture atomique du JSON de configuration, effectuées lors des actions de paramètres ou de lancement. Le fichier n'est pas décodé pour chaque instruction ou draw. |
| `headless/watch.h` | `U65` | Trace facultative de mémoire JIT activée par dev-settings watch=... ; callbacks et dumps volontairement coûteux seulement lorsque la sonde explicite est activée. |
| `headless/metadata_bridge.cpp` | `U13` | Extraction métadonnées NSP/XCI et gestion des sauvegardes, avec publication du snapshot addons après scan hors mutex ; opérations de bibliothèque/lancement et non par frame de jeu. |

**Périmètre :** 491 fichiers de code maintenus ; **396 pris en charge** ; **95 restant dans l'inventaire global**, dont **33 liés au moteur/runtime**, et **62 sources du lanceur** suivies à part. Ces quatre examens ne sont ni quatre optimisations créées ni une validation PS5. Le chantier prioritaire reste `src/memory_pages.cpp`, `headless/fastmem_handler.cpp`, les transferts Maxwell DMA, les barrières HLE et le cache pipelines Vulkan.
