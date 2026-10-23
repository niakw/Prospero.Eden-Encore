# Revue source : support des formats, distincte de F01–F06

**23 octobre 2026 — branche unique `dev/ps5-sparse-jit`.**

L'ancien instantané de couverture affichait 493 sources maintenues.
L'arbre Git actuel comporte **504 fichiers C/C++/en-têtes** dans
`headless/`, `src/` et `vendor/encore-active/`. Les onze sources
supplémentaires sont précisément dix unités de sélection/lecture de
conteneurs (ci-dessous) et
`headless/prosperoeden/pe/ui/case_media_selection.hpp` (interface UI
distincte). La revue physique de ces chemins évite d'en faire une
fausse dette d'optimisation JIT/GPU.

## Dix unités nouvelles de lecture/chargement

| Source | Git blob exact | Rôle et portée |
| --- | --- | --- |
| `headless/game_files.h` | `68fc45657fc87639d109592398003fb0e2859fb6` | Sélection et validation des neuf extensions et de l'ExeFS; sélection de titre, pas du frame GPU |
| `headless/ncz.cpp` | `7deff2ea1a82574b9e756ad9c2f0d869aa94612b` | Adaptateur de lecture NCZ et cache, sélectionné par CMake |
| `headless/ncz.h` | `85ced3460d83be2a8011f189c0df406b4dd32b8c` | Décompression NCZ, limites et protection du cache |
| `headless/ncz_check.cpp` | `65c9e5f4eb3625140add52ced2ea82e66bd224ab` | Harnais de vérification hôte; jamais un composant de rendu |
| `headless/ncz_vfs.h` | `176d89e5d385fe140211350ab4c20a38f1f496bd` | Pont VirtualFile utilisé par les sources NCZ maintenues |
| `vendor/encore-active/eden-core/src/core/file_sys/card_image.cpp` | `f843e7f9c977b509368e71eb6356066c1a5e0c50` | Lecteur de partition cartouche NCZ, source maintenue sélectionnée |
| `vendor/encore-active/eden-core/src/core/file_sys/registered_cache.cpp` | `6826d02a68a33b8733b5d3a50d804dedf3179955` | Détection NSZ/XCZ des contenus enregistrés |
| `vendor/encore-active/eden-core/src/core/file_sys/submission_package.cpp` | `29a46a6024cad1e867ac450a0bd651bebc1f0b29` | Ouverture NCZ comme archive de contenu d'un package |
| `vendor/encore-active/eden-core/src/core/loader/loader.cpp` | `e2e87827700a0a670f0d418262e80860e79a683a` | Routage des extensions au chargeur natif et NAX |
| `vendor/encore-active/eden-core/src/core/loader/nsp.cpp` | `b56195d24778a849bb768d463fdf4ceef3d5c33f` | Détection des membres NCZ d'un NSP/NSZ |

## Garanties et limites

- Les cinq sources complètes `vendor/encore-active/eden-core/src/core/`
  ont une reproduction octet à octet depuis les sources Eden épinglées,
  vérifiée par `tools/check-encore-ncz-sources.py`, y compris le
  correctif NAX du routeur. `headless/CMakeLists.txt` les sélectionne à
  la place de leur traduction épinglée.
- `headless/ncz.cpp` est sélectionné par CMake. `ncz.h` et
  `ncz_vfs.h` sont des en-têtes de l'adaptateur et des lecteurs NCZ.
  `ncz_check.cpp` est un **test hôte uniquement**. Les preuves sont
  `tools/check-ncz.py`, `tools/check-encore-ncz-sources.py` et
  `tools/check-exefs-directory-host.py`.
- `game_files.h` borne les types de conteneurs et refuse les layouts
  ExeFS traversant des répertoires. Le chargeur natif décide finalement
  si le fichier sélectionné est réellement exécutable.
- La compression/décompression NCZ peut devenir un coût d'I/O pour un
  titre NSZ/XCZ, mais **les anciens essais FC27 en conteneurs classiques
  ne démontrent aucune contribution de ces sources aux saccades**.
  Aucun cache GPU, shader, commande Vulkan, boucle HID ou JIT n'est
  modifié par l'inscription de cette revue.
- L'inscription dans le registre signale `format_feature_source_integrated`,
  **jamais FPS optimisé**. Les empreintes ci-dessus sont contrôlées en CI
  et toute modification forcera un réexamen.
- Le nombre des six objectifs F01–F06 clôturés demeure **0/6** ;
  aucune preuve console n'est créée ici. La source UI supplémentaire
  reste dans le périmètre UI, sans être comptée parmi les dix unités
  moteur revues.

Références : `docs/CONTENT_FORMAT_MATRIX_2026-10-23.md` et
`docs/FC27_EXIT_GATES_2026-10-22.md`.
