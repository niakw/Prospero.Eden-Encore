# F07 — scope de fonctions et preuves (28 octobre 2026)

**Branche unique :** `dev/ps5-sparse-jit`. **Périmètre actuel : 8 fichiers moteur, 38 points de fonction.** Cette liste sert à éviter les relectures circulaires. Elle ne prétend pas que 38 correctifs restent nécessaires : la plupart des fonctions ont déjà des gardes, et une revue source n'est pas une validation console.

| Priorité | Fichier source | Fonctions ciblées | Nombre |
| --- | --- | --- | ---: |
| P0.1 | `vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp` | `CurrentGraphicsPipeline`, `CurrentGraphicsPipelineSlowPath`, `CreateGraphicsPipeline`, `CurrentComputePipeline`, `CreateComputePipeline`, `LoadDiskResources`, `QueueVulkanPipelineCacheFlush` | 7 |
| P0.2 graphics | `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp` | `ConfigureImpl`, `ConfigureDraw`, `AddTransition`, `MakePipeline`, `QueueOptimizedPipeline` | 5 |
| P0.2 compute | `vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp` | `Configure`, `PreflightDescriptorScratch` | 2 |
| P0.2 descriptor | `vendor/encore-active/eden-vulkan/vk_descriptor_buffer_cost.cpp` | `PreflightFrameReuse`, `PreflightCapacity`, `Allocate` | 3 |
| P0.3 Vulkan | `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp` | `PrepareDraw`, `DispatchCompute`, `OnCPUWrite`, `AccelerateDisplay`, `TickFrame`, `FlushWork` | 6 |
| P0.3 guest bridge | `vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp` | `PrepareDraw`, `DispatchCompute`, `OnCPUWrite` | 3 |
| P0.4 texture state | `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h` | `QueueAsyncDecode`, `TickAsyncDecode`, `QueueAsyncUnswizzle`, `TickAsyncUnswizzle`, `RefreshContents`, `UploadImageContents`, `TryFindFramebufferImageView`, `SynchronizeAliases`, `TickFrame` | 9 |
| P0.4 Vulkan upload | `vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp` | `UploadStagingBuffer`, `TickFrame`, `AccelerateImageUpload` | 3 |
| **TOTAL** | **8 fichiers** | **38 points** | **38** |

## État observable et portes de clôture

- **P0.1 — ouvert :** la traduction CFG/IR/SPIR-V du premier usage reste synchrone sur le GPU owner. Les compteurs `graphics_pipeline_create`, `shader_cfg`, `shader_ir`, `shader_spirv` et `shader_module` existent derrière Detailed Logging ; ils ne prouvent pas un gain FPS console. Aucun offload des environnements invités sans preuve d'absence de races.
- **P0.2 — ouvert :** le worker attend le pipeline avant les commandes Vulkan. On conserve le store-release / load-acquire et l'ordre des draws. Une transition est un cache facultatif, non une raison d'abandonner le draw : les échecs d'allocation de ses deux vecteurs sont non fatals sur PS5, source et témoins O0/O2 vérifiés sur les builds précédents.
- **P0.3 — ouvert côté mesures :** pair-lock buffer/texture, preflight scheduler/descriptor ring et coût réel sous mutex restent à attribuer aux fenêtres de retard observées sur console. Les chemins natifs et leur miroir d'intégration sont comptés séparément.
- **P0.4 — ouvert côté console :** sélection conservatrice du framebuffer et refus des révisions périmées ; récupération des erreurs du worker de décodage. Dans le lot du 28/10, les uploads asynchrones 3D rétablissent le drapeau `CpuModified` après staging refusé ou incomplet. Sur PS5, les quatre frames d'espacement restent appliquées entre tâches **déjà en file**, mais ne se reportent plus après une file vide. Les textes/HUD réels ne sont pas encore qualifiés.

## Registre des changements récents et validation

- `783a93a` : **4/4 CI vert**, référence binaire publiée (fast gate, prévalidation, build natif, sécurité).
- `55a23f9` : décodage asynchrone ordinaire, récupération du staging absent/court ; validation CI propre à ce SHA à consulter.
- `60e2570` : décompression 3D, récupération d'allocation et suppression de la dette de cooldown inactive ; test source-extrait ajouté. Ce SHA a été remplacé immédiatement pour corriger la syntaxe du harnais, **ne pas en déduire une validation CI**.
- Le commit courant de suivi remplace cette erreur de test, sans ajouter de comportement GPU. Attendre les **4 validations sur le même SHA** avant nouvelle référence binaire.

## Règles de clôture

L'état d'une fonction peut être « relue sans changement », « corrigée et testée hôte », « intégrée/build 4/4 » ou « validée console ». Aucun de ces états n'est automatiquement la preuve que les 30 FPS sont stables, que le HUD est frais ou que les pauses/mi-temps ne bloquent plus. Une campagne PS5 commune, avec comparaison des retards >50/>100 ms, images réellement nouvelles et progression guest, reste nécessaire pour fermer les P0.

## Revue ciblée P0.1 — nouveaux échecs de traduction après saturation du budget

Les deux fonctions `CurrentGraphicsPipelineSlowPath` et `CurrentComputePipeline` sont modifiées dans le lot de reprise P0.1 : avec plus de 64 clés graphiques ou 32 clés compute ayant échoué, le nouvel échec obtient également **une tentative différée**. La carte de reprise reste plafonnée en recyclant la clé au délai `eligible_at` le plus ancien, sur le chemin **d'échec froid seulement**. Les clés rejetées par saturation restent sans nouvelle tentative ; il s'agit d'un compromis borné, pas d'un système de retries illimités. Les deux témoins C++ extraient le code réel, couvrent `-O0`/`-O2`, et démontrent la saturation ainsi que l'absence de tempête sur un même shader. Aucun chiffre FPS ou récupération HUD sur console n'est revendiqué.

## P0.2 — attente Vulkan unique par pipeline

Les fonctions GraphicsPipeline::ConfigureDraw et ComputePipeline::Configure ont maintenant un indicateur GPU-owner uniquement sur PS5. Une attente de compilation est enregistrée une seule fois pour chaque pipeline non prêt ; toutes les commandes ultérieures restent derrière elle dans la file FIFO, y compris entre les chunks. Le flag est écrit seulement après que scheduler.Record a réussi. Le test hôte extrait les deux portions C++ et compare PS5 et desktop sous O0/O2, avec 64 commandes, build retardé et rejet de Record. Pas de preuve FPS console.

## P0.1 — diagnostic à froid lors d'une exception de shader

La branche native de `CreateGraphicsPipeline(ShaderPools&, ...)` ne réanalyse plus les CFG et n'écrit plus de dumps `.ash` après une exception de traduction lorsque `dump_guest_shaders` est désactivé. Cette reconstruction est facultative et survient sur le GPU owner. L'option explicite restaure le diagnostic ; un échec secondaire du CFG ou de l'écriture est contenu sans masquer l'erreur shader d'origine. Le témoin hôte extrait ce handler exact en desktop/PS5, O0/O2. Ce correctif n'accélère pas les traductions réussies et ne constitue pas de preuve FPS console.
