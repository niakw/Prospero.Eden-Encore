# Encore — passe d'optimisation P0, six nouvelles sources actives
**20 octobre 2026 · branche `dev/ps5-sparse-jit` · lot sans nouveau patch.**

Ces **6 fichiers de production distincts** sont examinés pour déterminer si
une nouvelle optimisation est justifiée. Il ne s'agit pas d'une fermeture
de contrats HOST, ni d'une affirmation selon laquelle ils sont tous optimisés.

| Source | Observation source | Décision |
| --- | --- | --- |
| `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp` | `PrepareDraw` et `DispatchCompute` préparent des commandes et vidangent la file des descripteurs **avant** la prise conjointe des verrous GPU ; les appels de relecture après attente protègent des invalidations de mémoire invité | Ne pas réécrire l'ordre des verrous / les drains sans trace de détenteur fautif |
| `vendor/encore-active/eden-vulkan/vulkan_present_layer.cpp` | `ConfigureDraw` protège le cycle de vie des images avec `scheduler.Wait(resource_ticks)`; changement de pitch seul recycle uniquement le tampon et le changement AA attend la destruction sûre de ses ressources | Les `WaitIdle` sur transition de format/AA ne sont pas des attentes par frame ; garder la sécurité |
| `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp` | La branche de premier usage dispose déjà d'une lecture `acquire` sans verrou lorsque le pipeline est prêt ; sinon condition wait associé au build | Pas de raccourci GPU/JIT sûr identifié sans nouvel échantillon |
| `vendor/encore-active/ps5-mesa/src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c` | Poll du marker GPU flushé avant lecture, séquence 64 bits reconstruite, spin borné (1,5 ms) puis sommeil d'1 ms et seuil de non-progression 10 s | Coût potentiel à profiler, mais tout retrait arbitraire du flush ou timeout risque une fausse complétion |
| `vendor/encore-active/ps5-mesa/src/vulkan/wsi/wsi_common_videoout.c` | Worker flip attend le `VkFence` avant `sceVideoOutSubmitFlip` ; allocation des buffers protège `held/pending/on_screen` et attend vblank ou CV | Présentation FIFO dépend d'une image terminée ; ne pas sauter le fence pour gagner un faux FPS |
| `vendor/encore-active/eden-gpu/include/common/bounded_threadsafe_queue.h` | Producteur SPSC attend une place libre avec stop-token, fast path évitant le mutex quand libre ; consommateur charge les index en `acquire` | Implémentation déjà optimisée ; ne pas doubler une correction existante |

**Bilan de la passe de traitement de code** : 6 chemins actifs nouvellement
examinés sans patch ; le registre global d'optimisation passe à 41 chemins
traités ou examinés sur 491 et **450 chemins encore à traiter pour
l'optimisation**. Il ne faut pas dire « 450 correctifs requis » : le véritable
nombre de nouveaux patches dépend de l'analyse de ces 450 sources.
Les 397 en qualification et les 95 P0 sont **exclus de ce compteur**.
