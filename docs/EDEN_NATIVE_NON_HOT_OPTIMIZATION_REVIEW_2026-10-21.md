# Eden Encore — douze unités non-hotpath classées hors optimisation moteur urgente

**21 octobre 2026 · branche `dev/ps5-sparse-jit` · revue à `f73075323`.**

Périmètre strict : **moteur et infrastructure**, sans les 62 sources d'interface
`headless/prosperoeden` (la source partagée `runtime_shims.cpp` reste
dans le périmètre moteur). Les douze fichiers ci-dessous ont été lus ; les
cibles compilées et le statut du pont expérimental ont été recoupés avec
`headless/CMakeLists.txt` et `headless/guest_write_deferred_bridge.cmake`.

| Source C/C++ ou en-tête | Contrat | Constat et décision |
| --- | --- | --- |
| `headless/devices_check.cpp` | `hors graphe` | Cible eden-devices-check séparée du jeu ; scénarios de manette/audio et ABI, aucun traitement dans une frame normale. |
| `headless/mock_devices.cpp` | `hors graphe` | Bibliothèque eden-device-mock dans la branche non-PS5 ; faux pad/audio pour tests, hors binaire natif normal. |
| `headless/mock_devices.h` | `hors graphe` | Déclarations et état des faux devices partagés par la bibliothèque de simulation, pas les périphériques PS5 réels. |
| `headless/mods_check.cpp` | `hors graphe` | Exécutable eden-mods-check distinct ; construit des fixtures IPS/pchtxt et vérifie les paramètres, absent du chemin jeu. |
| `headless/preferences_check.cpp` | `hors graphe` | Exécutable eden-settings-check distinct ; assertions JSON et migration de profils, pas d'itération par frame. |
| `headless/ryujinx_check.cpp` | `hors graphe` | Exécutable eden-ryujinx-check distinct ; génère et valide des sauvegardes de test, non lié à eden-headless. |
| `headless/memory_check.cpp` | `J08` | Exécutable eden-memory-check dédié aux instructions/JIT hôte ; sa longue batterie de stress n'est pas exécutée dans le jeu. |
| `headless/elevation/elevation.cpp` | `hors graphe` | Client d'élévation lié à eden-headless mais sollicité à l'initialisation/handshake ; pas de polling en boucle de rendu GPU. |
| `headless/elevation/helper/main.cpp` | `hors graphe` | Exécutable helper d'élévation pour une requête et opérations kernel délimitées ; hors exécution normale des frames. |
| `headless/gpu_deferred_replay.h` | `M02` | Post-store readiness fixé explicitement à false ; source expérimentale, activation sûre non prouvée, ne pas l'activer pour gagner du FPS. |
| `headless/gpu_deferred_store_publication.h` | `M05` | API de publication après écriture documentée comme source-only non branchée au cœur livré ; contrat de concurrence encore à prouver avant activation. |
| `headless/gpu_deferred_write_queue.h` | `U21` | File FIFO GPU différée utilisée par les essais du pont DEV ; EDEN_GUEST_WRITE_BRIDGE_DEV reste OFF dans le profil normal. |

Les sept premiers appartiennent aux tests hôte et à leur bibliothèque mock.
Les deux sources d'élévation sont de l'infrastructure de démarrage, **pas**
un chemin de rendu par image. Les trois sources de publication différée
GPU restent intentionnellement désactivées : cela **ne signifie pas** que
leur synchronisation inter-thread soit validée pour la production.

Chaque source est enregistrée avec son **Git blob exact**, et le contrôle
`tools/check-eden-optimization-coverage.py` invalide cette revue si le
fichier change. Aucun patch C++ n'a été créé dans ces douze sources.

| Indicateur | Avant | Après |
| --- | ---: | ---: |
| Sources de code maintenues, tous composants | 491 | 491 |
| Fichiers examinés/pris en charge | 380 | **392** |
| Sources encore à traiter dans le moteur/runtime | 49 | **37** |
| Sources d'interface/lanceur suivies séparément | 62 | **62** |
| Total restant, tous périmètres | 111 | **99** |

**37 = travail d'analyse/optimisation encore à effectuer, pas 37 bugs
certifiés.** Conserver en priorité le DMA Maxwell, les transitions HLE,
les allocations JIT et la mémoire GPU. Ne pas convertir les 62 composants UI
en dette d'optimisation du moteur.
