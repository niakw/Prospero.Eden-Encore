# Eden Encore — quatre propriétaires de configuration, sauvegardes et diagnostic

**21 octobre 2026 — HEAD `fb533b652`.** Source-level inspection, distincte de la qualification console.

Ces quatre chemins, même lorsqu'ils sont situés sous `headless/` et liés au binaire du jeu, assurent surtout des fonctions de configuration, de gestion de bibliothèque et de diagnostic opt-in ; ils ne justifient aucun nouveau patch de la boucle GPU/JIT sans mesure ciblée. Chacun reste suivi par son **Git blob exact** et par son contrat original.

| Fichier | Contrat | Constat du code et décision |
| --- | --- | --- |
| `headless/ryujinx_saves.h` | `U63` | Import/export de fichiers Ryujinx via filesystem, avec interdiction de suivre les symlinks. N'est pas parcouru pendant les instructions invitées ni les commandes GPU ; associé à la gestion des sauvegardes depuis l'interface. |
| `headless/settings_store.h` | `U75` | Lecture/migration/écriture atomique du JSON de configuration, effectuées lors des actions de paramètres ou de lancement. Le fichier n'est pas décodé pour chaque instruction ou draw. |
| `headless/watch.h` | `U65` | Trace facultative de mémoire JIT activée par dev-settings watch=... ; callbacks et dumps volontairement coûteux seulement lorsque la sonde explicite est activée. |
| `headless/metadata_bridge.cpp` | `U13` | Extraction métadonnées NSP/XCI et gestion des sauvegardes, avec publication du snapshot addons après scan hors mutex ; opérations de bibliothèque/lancement et non par frame de jeu. |

## Réexamen du 23 octobre — U13, classification des conteneurs

La source `headless/metadata_bridge.cpp` a changé depuis son empreinte de
revue initiale `c15a5f3bac31d6206e61cfc39317be280a129c48`.
La comparaison des deux blobs confirme six modifications circonscrites :
ajout de `game_files.h`, conversion des suffixes stricts `.xci/.nsp`
en fonctions de reconnaissance `IsCardImageFile/IsPackageFile` dans la
lecture du Title ID et des langues, rejet explicite des fichiers
NRO/NSO/NCA/NAX/KIP sans Control RomFS dans l'extracteur, et application
de la même distinction au contrôle de version des glyphes.

Ces opérations sont invoquées lors de l'extraction de métadonnées de
fichier ou d'un lancement, **pas à chaque frame**, ni dans les
acquisitions de verrous buffer/texture, ni dans les compilations JIT.
Aucun gain F01–F06 n'est déduit de ces changements. Le blob courant
`43ed86fa7dec1da214051c291fc60c818b3d3eeb` devient la
référence U13 après cette revue ciblée. Le verrouillage d'empreinte dans
`tools/check-eden-optimization-coverage.py` reste **inchangé** :
toute modification ultérieure exige un nouveau réexamen.

## Réexamen du 23 octobre — U75, sélection de jeux persistée

La différence entre le blob revu
`ec168add36f89f8800b32e875a8f7bd7b95cdf99` et le blob courant
`ebcfe022c94cb74bbf20c74664ae28e04912289e` porte exclusivement
sur la validation des noms sauvegardés : ajout de `game_files.h`,
remplacement du test de suffixe NSP/XCI par `IsGameFile` et acceptation
contrôlée d'un dossier ExeFS sélectionné comme `<folder>/main`.
`IsDeconstructedGameSelection` impose une seule composante de répertoire
sans séparateurs et rejette `.` et `..`; le traitement rejette toujours
les caractères de contrôle et les backslashes. Le chargement JSON,
la publication atomique et les mutations de préférences restent inchangés.
Ce code n'est pas appelé par les instructions invitées ou chaque draw.
Aucune performance de F01–F06 ni qualification PS5 n'est déduite de
l'extension des formats. Toute nouvelle modification rouvrira cette revue.

**Périmètre :** 491 fichiers de code maintenus ; **396 pris en charge** ; **95 restant dans l'inventaire global**, dont **33 liés au moteur/runtime**, et **62 sources du lanceur** suivies à part. Ces quatre examens ne sont ni quatre optimisations créées ni une validation PS5. Le chantier prioritaire reste `src/memory_pages.cpp`, `headless/fastmem_handler.cpp`, les transferts Maxwell DMA, les barrières HLE et le cache pipelines Vulkan.
