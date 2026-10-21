# Eden Encore — lot natif / optimisation GPU / chemins conditionnels

**21 octobre 2026 — base 46624ac9d.** Source-level triage, pas validation console.

## Correction code : pipeline graphique Vulkan (contrat V07)

`vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp` : le chemin graphique appelle `EdenAttributeless` quand `static_vertex_input=true` (valeur par défaut PS5). Un mémo d'une identité provoquait un verrou et une recherche dans `std::set` si deux vertex shaders alternaient ; la reconnaissance des shaders ne change pas. Nouveau mémo direct-map de **64 couples (vertex hash, génération)**, consulté par le thread GPU ; insertion de shader toujours synchronisée et publication release/acquire inchangée. Aucun changement des clés de pipeline, des descripteurs, ni de la synchronisation GPU.

La même modification est intégrée à `tools/prepare-vulkan-port.py` et à la source C++ dérivée maintenue. Le test existant `tools/check-ps5-vertex-identity-host.py` compile le helper extrait du vrai fichier sous ASan/UBSan ; il exige la parité générateur/source, teste la transition négatif→positif de génération et les collisions direct-map. Le résultat n'est pas une preuve de FPS console ou de correction d'un freeze.

## Sources revues sans nouveau correctif

| Fichier | Contrat | Constats et décision |
| --- | --- | --- |
| `headless/display_refresh.h` | `U53` | SkipFrame reste une lecture atomique et un CAS à chaque frame uniquement si le jeu produit plus d'images que le rafraîchissement. Le contrôle d'espacement et la synchronisation inter-renderers sont nécessaires ; aucune allocation ni verrou ; pas de retouche spéculative. Blob `79aa191d75bbdb0d042d3178d629f02641e9b12c` |
| `headless/experimental_performance.h` | `U23` | Plan de budget JIT calculé avant les threads invités (4 arènes, overhead direct, plafond relatif 1536 MiB). Atomiques de cache figées par titre ; aucun calcul du plan par bloc compilé ; la fragmentation nécessite une mesure matérielle avant rééquilibrage. Blob `3f3fd71a951147a17298118440b544ffcac13e72` |
| `headless/jit_list.h` | `J11` | Précompilation JIT expérimentale, protégée par EDEN_SHARED_JIT_AVAILABLE et opt-in ; chemin absent du rendu standard, historique borné et titre/build contrôlés. Ne pas rendre actif sans qualification de la quiescence JIT. Blob `405813ad83c313f619b1ab39e9e2fc362099e237` |
| `vendor/encore-active/eden-core/src/hid_core/resources/npad/npad_pause_diag.cpp` | `H52` | Implémentation NPad de diagnostic choisie seulement sous PS5_NATIVE + EDEN_DEV_PROFILE ; les trois compteurs atomiques et impressions de progression sont DEV, pas la voie de livraison. Conserver l'observabilité sans alourdir le chemin normal. Blob `ea1cee774ef6299aa52dda918cc609ddbf169bbf` |

**Compteurs de cette révision :** 401/491 traités ; **28 moteur/runtime restant à examiner** (33 avant) ; 62 fichiers d'interface séparés ; 90 globalement. Un chemin effectivement modifié, quatre revus sans correction. Vérification console et tests fonctionnels restent indépendants.
