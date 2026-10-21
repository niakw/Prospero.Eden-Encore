# Eden Encore — unique profil natif pour le test final

**21 octobre 2026, branche `dev/ps5-sparse-jit`**. Ce document est une décision de sélection, pas une affirmation de performance ou de compatibilité console.

## Sélection finale

- **Jeu** : Vulkan/RADV normal. **Lanceur et Safe Launch** : OpenGL maintenu, volontairement conservé (pas d'exclusion d'une dépendance fonctionnelle).
- **CPU invité** : Dynarmic per-core standard + protections mémoire et repli existants.
- **Sparse JIT expérimental** : OFF (chemin encore non qualifié pour les fautes d'exécution).
- **JIT partagé/batching, inlining exclusives** : OFF.
- **Pont différé CPU→GPU `EDEN_GUEST_WRITE_BRIDGE_DEV` : OFF**. Le module sélectionne huit unités remplaçant simultanément mémoire, rasterizer, DMA, Kepler et uploads sous profil DEV, **sans activation de `cpu_write_defer`**. Le build normal ne les sélectionne pas : le code source reste accessible pour traçabilité, mais pas de chemin de jeu expérimental dans le paquet final.
- **Fermi2D `EDEN_UNQUALIFIED_FERMI2D_COPY` : OFF** : conserver l'implémentation observée, non la copie 3D expérimentale.
- **`EDEN_DEV_PROFILE`, `EDEN_DEV_WAIT_CALLERS`, `EDEN_DEV_VULKAN`, `EDEN_GPU_PROBE` et `EDEN_DEVICE_FRONTEND`** : OFF. Les diagnostics hôte restent dans les tests CI, pas dans le runtime final.

## Garantie de sélection / preuves

`tools/build-package.sh` fixe les options OFF pour `release` et `release-stage`; `tools/build-headless-native.sh` les transmet explicitement à CMake, évitant les caches antérieurs non contrôlés. `headless/CMakeLists.txt` échoue si le profil final contient un pont/renderer non qualifié, un JIT expérimental ou un paramètre DEV. `tools/ci/check-release-experiments.py` vérifie ces flags du **CMakeCache compilé** (un simple texte de source ne suffit pas); `tools/ci/check-final-one-profile-source.py` contrôle le contrat en CI.

Les recettes `dev` historiques sont volontairement conservées mais non sélectionnées par `make release`. Aucun test matériel PS5 ni validation du freeze FC27 ne sont inférés de cette sélection.

**Compteur de sources moteur restant à optimiser/examiner : 14, inchangé ; 62 fichiers interface à part.** Cette phase fige le profil livré, elle ne marque aucune source moteur comme optimisée.
