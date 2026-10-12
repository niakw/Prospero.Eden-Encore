# R392 — fin du transform feedback Vulkan : garder les buffers du début

Source ciblée : [Eden officiel #4499, commit 6352612425](https://github.com/eden-emulator/mirror/commit/6352612425ae0765802eaa8c5904ff652b97222a), daté du 11 octobre 2026.

## Différence réelle confirmée

Le moteur Vulkan versionné dans Eden Encore conservait un appel à `UpdateBuffers()` dans `TFBCounterStreamer::FlushEndTFB()`, après `has_flushed_end_pending = false`. Cet appel peut modifier l'état des buffers de compteurs entre l'enregistrement de `BeginTransformFeedbackEXT` et celui de `EndTransformFeedbackEXT`. L'upstream Eden #4499 a retiré cet appel de la fin, sans retirer celui de `FlushBeginTFB()`.

R392 porte **strictement la même suppression** dans `vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp` et dans le remplacement source ciblé de `tools/prepare-vulkan-port.py`. Aucun autre appel de mise à jour des buffers, fence, mécanisme de rendu conditionnel, ni version de dépendance n'est modifié.

## Vérifications et limites

- Contrôle source nouveau `tools/check-ps5-tfb-counter-stability.py` : parser Python du générateur, exigeant exactement un remplacement depuis le fichier original épinglé, un `UpdateBuffers()` dans `FlushBeginTFB()` et aucun dans `FlushEndTFB()`.
- Contrôle ajouté aux workflows d'analyse source et de préparation native. Le contrôle complet `tools/check-vendored-vulkan-fork.py` doit également vérifier l'équivalence octet pour octet des 40 fichiers Vulkan générés/compilés.
- Les correctifs de buffers GPU et Kepler/Maxwell **#4473 et #4477 étaient déjà inclus**, via `headless/backports/eden-4473-4477.patch` et `vendor/encore-active/eden-backports/src/video_core/`. Ne pas les réappliquer.
- Les corrections Npad/notifications d'applet **#4442 étaient aussi déjà incluses** dans les backports actifs. Le diagnostic R384 ne démontre pas qu'elles résolvent le freeze du match.
- Aucun build ni test PS5 n'est demandé ici. Cette modification suit l'upstream pour préserver la cohérence des compteurs de transform feedback ; ni la correction visuelle ni le gain en performances FC27 ne sont établis sur console.

R391 a séparément autorisé les images `HasScaled()` dans les lots de récupération des textures Vulkan, avec les limites préexistantes de 40 images/32 Mio et des tests hôte sous sanitizers. Les changements R391/R392 devront être réunis dans **un seul essai PS5** après validation globale.
