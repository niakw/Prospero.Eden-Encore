# Eden Encore — audit ciblé de 10 chemins P0 Vulkan, présentation et textures

**Date :** 20 octobre 2026 · **Base :** `c3a61b4daa05291c504370c9e75122a0d48ae99d`
· **Branche :** `dev/ps5-sparse-jit`.

## Périmètre et portée

Lecture ciblée des fonctions, contrats et chemins d'appel de **10 fichiers P0 distincts**
non modifiés depuis la base de développement `82c531d`.
Cet examen vérifie les responsabilités, synchronisations et risques évidents.
Il **ne remplace ni** la compilation native, ni l'analyse instrumentée des
délais en jeu, ni les tests PS5. Aucun changement spéculatif de ces sources
n'est justifié par les éléments accessibles.

| Contrat | Source étudiée | Constat de code | Reste à démontrer |
| --- | --- | --- | --- |
| V04 | `vendor/encore-active/eden-vulkan/vulkan_renderer.cpp` | `RendererVulkan::Composite` présente la frame puis déclenche `DispatchWork` et `rasterizer.TickFrame` ; un callback de présentation ne prouve pas une nouvelle frame invitée | Séparer progrès du guest, exécution GPU et présentation écran, surtout durant une pause/mi-temps |
| V11 | `headless/graphics.cpp` | `eglSwapBuffers` et la comptabilité d'intervalles sont des observations hôte ; un rythme écran stable ne prouve pas le renouvellement du HUD | Couplage tick invité → texture consommée → image présentée |
| V26 | `vendor/encore-active/eden-vulkan/vulkan_device.cpp` | Sélection des extensions/features et contraintes descriptor-buffer bien distinctes ; ne pas forcer la fonctionnalité matériel lorsque le pilote la refuse | Transitions device-lost et budget effectif, sur le backend natif |
| V28 | `vendor/encore-active/eden-vulkan/vulkan_blit_screen.cpp` | `BlitScreen::WaitIdle` attend la présentation, `Scheduler::Finish`, puis le device : attente coûteuse mais potentiellement nécessaire aux destructions/transitions | Localiser ses appelants et mesurer son occurrence avant toute suppression/assouplissement |
| V31 | `vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_scheduler.h` | `Scheduler::Wait` conserve la synchronisation par tick et le flush du travail courant ; `PreflightDrawCommands` évite de déplacer des soumissions sous verrous | Identifier un tick GPU réellement bloqué, ne pas éliminer une barrière sur corrélation |
| V32 | `vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_present_manager.h` | API `Present`/`WaitPresent` et structures de frames définies ; responsabilités d'ownership visibles | Confirmer en exécution l'ordre de recyclage / swapchain / shutdown |
| V38 | `vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/pipeline_helper.h` | Écriture des descriptors par type et layout ; tailles propres aux features du device | Correspondance allocations / payload / pilotes, notamment sur les buffers non cohérents |
| V42 | `vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h` | Prévalidation de capacité GPU et zéro des octets inactifs d'union en mode descriptor-buffer existent déjà | Lier l'état de descripteur réellement utilisé au HUD/textures défaillantes |
| V46 | `vendor/encore-active/eden-vulkan/vulkan_descriptor_buffer.cpp` | `TickFrame`, `PreflightFrameReuse`, `PreflightCapacity`, `Allocate` imposent des waits de réutilisation quand nécessaire ; ne pas supprimer `Wait/Finish` sans preuve | Ticks réels et dépassements sous charge FC27, sélection exacte des unités compilées |
| V45 | `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h` | `VisitImageView` réessaie une vue NULL précédemment mise en cache si la TIC devient valide sans changement de descripteur ; serial de bindings invalidé en cas de reprise | Sur console, confirmer le retour des pixels et l'absence d'aliasing/stale HUD |

## Décision du lot

Les protections existantes contre les vues absentes, les attentes sous
verrous et les erreurs de durée de vie empêchent de conclure que
« réécrire davantage » est sans risque. Prioriser **l'instrumentation
ciblée des frontières** guest frame → descriptor/image → submit →
present, à effectuer uniquement avec un test identifié et la validation
native consolidée. Ne pas modifier plusieurs synchronisations en même
temps.

Cette seconde revue porte l'inventaire manuel des deux lots de ce tour
à **20 chemins P0 distincts** (10 IPC/HLE/CPU/GPU, 10 Vulkan).
Ce n'est **ni 20 optimisations**, ni 20 validations de performance :
les **397 chemins SOURCE+OPEN / 95 P0 / 408 contrats** restent
en attente de qualification selon leurs critères.
