# Tools : ce qui est compilé, préparé et vérifié

**Aucun script Python dans `tools/verify/` ne constitue une correction du moteur.**

| Nature | Chemin | Effet |
| --- | --- | --- |
| Originaux amont | `vendor/sources/eden/src/` | Sources de référence conservées sans modification |
| Sources compilées / overrides | `vendor/encore-active/*/src/` | Fichiers C++, en-têtes et adaptations du moteur versionnés |
| Sélection HLE | `vendor/encore-active/eden-threading/native-hle-overrides.cmake` | Choisit les fichiers de `core`, sans modification textuelle du C++ |
| Orchestration native | `headless/inject.cmake`, `headless/CMakeLists.txt`, `tools/build-headless-native.sh` | Configure et lance la compilation |
| Préparation avant compilation | `tools/prepare-build.sh`, `tools/install-vendored-eden-build-flags.py` | Installe des copies contrôlées des configurations amont et maintenues |
| Vérification HLE uniquement | `tools/verify/hle/*.py` | Lit les vrais fichiers, peut compiler des témoins temporaires sur hôte ; ne modifie pas les sources produites |
| Autres vérifications héritées | `tools/check-*.py` | Tests et contrôles encore au niveau racine ; migration graduelle |

## Contrat

1. Une correction moteur appartient à `vendor/encore-active`, sous forme de fichier source complet et relisible.
2. CMake peut choisir le fichier, pas contenir son correctif en `string(REPLACE)` ou `write_derived`.
3. La préparation s'exécute **avant** compilation ; le test s'exécute **en dehors** du code produit.
4. La validation sur hôte ne démontre pas la reprise d'exécution sur console.
5. Les déplacements de tests mettent à jour atomiquement CI, registres et chemins internes.

**Périmètre réalisé :** HLE/threading. `headless/CMakeLists.txt` possède encore des transformations historiques d'autres sous-systèmes (GPU/HID/services). Elles restent visibles et nécessitent un audit par domaine avant suppression.
