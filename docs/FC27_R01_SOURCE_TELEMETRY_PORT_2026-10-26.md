# F07 — R01, import sélectif de télémétrie Vulkan (26 octobre 2026)

Branche finale : `dev/ps5-sparse-jit`. Source : `feat/graphics-network-achievements`.
**Intégré en source ; validation CI sur ce commit et PS5 non encore acquises.**

## Chemins retenus

- `headless/frame_metrics.h` : compteur optionnel réinitialisé par titre,
  distinct pour composite source, source ignorée, frame réelle/générée/chargement
  envoyée dans la file et appel Vulkan Present retourné.
- `vendor/encore-active/eden-vulkan/vulkan_renderer.cpp` :
  cinq sites d'événement, sans modifier les fences, shaders, descripteurs ou
  l'ordre de rendu. Le comptage généré reste compatible avec `HAS_LSFG`.
- `vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp` :
  API Present retournée, **pas un accusé de scan-out**.
- `headless/main.cpp` : réinitialisation uniquement entre deux titres ;
  `headless/performance.cpp` : échantillonnage sur le rapport GPU détaillé
  périodique, aucun chronométrage ajouté au mode silencieux.
- `tools/check-vendored-vulkan-fork.py` : rejoue six deltas contrôlés
  dans la génération Vulkan et compare **tous les fichiers produits**, après
  conservation des correctifs de transition visuelle de production.

## Dépendances, contrôles et acceptation

Le harnais `tools/check-feature-r01-native-frame-metrics-host.py` reprend
le test C++ de `extras/graphics/test_frame_metrics.cpp` en O0/O2 et UBSan.
Les fixtures de rendu F03/F05 reçoivent le vrai header `headless` pendant
leur compilation C++ hôte ; le test existant de cohérence des sources Vulkan
est conservé. L'analyseur `tools/analyze-r01-frame-metrics.py` et ses tests
isolent les sessions et les taux pondérés ; aucun chiffre synthétique n'est
présenté comme performance FC27. Prévalidation complète et fast gate sont
déclenchés sur le même commit ; le package natif est une validation séparée.

Cette instrumentation ne prouve **ni** le FPS de simulation invité, **ni**
l'âge réel des pixels HUD, **ni** la sortie HDMI, **ni** la latence manette.
Elle fournit des témoins complémentaires pour attribuer P0.2/P0.4/P1.2.
F07 reste ouvert tant que la fluidité/HUD ne sont pas confirmés en jeu.

R03 (14 sources RADV, garde NaN SPIR-V), R04 (AudioIn/RomFS) et R06
(framegen/FSR) ont été examinés, mais ne sont pas fusionnés :
ils nécessitent un portage à dépendances plus larges et une validation
native isolée pour ne pas introduire un nouveau goulot GPU.
