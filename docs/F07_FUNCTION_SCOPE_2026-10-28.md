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

## P0.1 — refus de mise en file d’une sauvegarde de cache driver

La sauvegarde Vulkan différée conserve désormais le quota de pipelines atteint lorsqu’un `QueueWork` est refusé (exception connue ou inconnue). Le verrou `flush_in_flight` est libéré comme auparavant, et la fenêtre temporelle de limitation reste active : le premier nouvel appel après cette fenêtre peut réessayer sans exiger 128 compilations supplémentaires. Le témoin source-extrait vérifie le refus, l’absence de tempête de retry et la reprise du flush. La récupération d’une exception **dans** le worker n’est pas traitée par ce changement ; les tests console restent nécessaires.

## P0.4 — extension de formats d’images absente

La construction PS5 de `TextureCacheRuntime` initialise aussi le passage compute BCn 3D lorsque le pilote ne fournit pas `VK_KHR_image_format_list` : ce traitement de buffers n’utilise pas cette extension. Auparavant, le constructeur quittait avant la création du passage alors que `RefreshContents` pouvait continuer à placer ces textures dans la file GPU, avec risque de validation sans image transférée. La branche desktop reste inchangée. Le témoin compile la branche exacte en mode PS5/desktop O0/O2 et l’oracle de sources reconstruit ce delta. Pas de preuve console ni de gain FPS revendiqués.

## P0.4 — échec pendant la soumission d’une image décodée

En PS5 native, `TickAsyncDecode` intercepte désormais une exception du transfert `Image::UploadMemory` après la conversion asynchrone. Le contexte est relâché après déverrouillage, `IsDecoding` est effacé, la texture est détrackée et `CpuModified` est conservé pour un nouvel upload. Le staging ordinaire n’est pas libéré avec l’API différée (qui suppose une allocation `deferred`). Le témoin source-extrait force l’échec et vérifie la récupération au décodage suivant. Pas de preuve console/FPS.

## P0.4 — rejet de soumission des lots BCn 3D

Si `FullUploadSwizzles` ou `AccelerateImageUpload` échoue au cours d’un lot, la branche native abandonne la révision incomplète, restitue le staging en différé, conserve `CpuModified`, efface `IsDecoding`, détracke la texture et retire la tâche de la file. Le prochain upload peut reprendre sur les octets invités courants. Un harnais C++ source-extrait exécute les chemins échec et succès sous O0/O2. L’état de la console reste non mesuré.

## P0.4 — lecture mémoire invitée échouée durant un lot BCn 3D

Le chemin PS5 natif de `TickAsyncUnswizzle` capture les exceptions de `GpuMemory::ReadBlock` même lorsqu'une portion du staging a déjà été remplie. Il libère en différé la source des lots GPU antérieurs, conserve `CpuModified`, libère `IsDecoding` et retire le travail incomplet. Un témoin C++ source-extrait force l'échec initial, l'échec après une lecture partielle, le succès et la reprise sous O0/O2. La branche desktop reste inchangée ; aucun FPS réel n'est déduit.

## P0.2 — échec d’une compilation optimisée facultative

Une exception d’admission/OOM dans `QueueOptimizedPipeline` ne doit pas déclencher le gestionnaire critique de construction initiale après que `MakePipeline` a déjà publié le pipeline rapide. L’appelant PS5 absorbe les refus connus ou inconnus de la file facultative et laisse se poursuivre la collecte statistique. Le test C++ source-extrait vérifie le pipeline initial, les deux exceptions et le chemin direct en PS5 et desktop sous O0/O2. Le worker optimisé garde sa logique antérieure de libération des quotas ; aucun gain FPS console n’est affirmé.

## P0.1 — échec dans le worker de sauvegarde Vulkan

Après une erreur de sérialisation ou une exception pendant la lecture du cache driver, le worker PS5 transmet maintenant un indicateur `atomic_bool` au thread propriétaire GPU. Ce dernier restaure le quota des 128 pipelines à la prochaine opportunité, sous le délai existant de 30 s minimum (ou plus selon la taille du cache). Le compteur non atomique n'est jamais écrit depuis le worker. Le test C++ source-extrait vérifie exception connue, inconnue, délai de retry et préservation du chemin desktop. Ni performance graphique ni persistance réelle sur PS5 ne sont démontrées.

## P0.4 — manque de mémoire pendant l’upload synchrone

Sur PS5 native, une exception `std::bad_alloc` pendant le staging, la conversion ou la soumission synchrone laisse `CpuModified` pour le prochain passage et n'interrompt pas le rendu. Le garde de restauration existant détache l'image ; la barrière n'est jamais publiée comme succès sur le chemin en échec. Le témoin F04 C++ source-extrait injecte un échec d'allocation suivi d'un transfert réussi de la nouvelle révision. Les autres catégories d'erreurs restent visibles. Pas de preuve console.

## P0.4 — staging synchrone incomplet

La PS5 rejette maintenant un staging GPU vide ou trop court avant toute copie de pixels ou barrière. Le rollback existant préserve CpuModified pour une seconde tentative. Le témoin source-extrait exécute l'échec puis la reprise à O0/O2. Pas de validation console.

## P0.4 — passage BCn 3D absent ou désactivé

Une soumission BCn 3D sans passage compute disponible ne doit plus être silencieusement considérée comme terminée sur PS5 : `AccelerateImageUpload` signale une erreur explicite, que `TickAsyncUnswizzle` traite en restituant le staging différé, en conservant CpuModified et en libérant IsDecoding. Cela couvre aussi le changement de réglage après la création du runtime. Le comportement desktop reste identique. Un témoin C++ source-extrait teste les modes PS5/desktop O0/O2, le passage BCn valide et le chemin ASTC ; pixels réels/FPS non mesurés.

## F07 — reprise après erreur de l'oracle

Le rejet du passage BCn 3D absent est déjà appliqué par le générateur ; l'oracle le rejouait à tort une seconde fois. Deux doublons sont supprimés sans relâcher la comparaison octet par octet, tandis que les cinq deltas historiques restent strictement vérifiés.

## P0.3 — lecture d'une tranche BCn 3D plus large que le budget de frame

Auparavant, si une tranche BCn 3D dépassait `swizzle_chunk_size`, `TickAsyncUnswizzle` forçait la lecture d'une tranche entière sous le verrou texture, par exemple 64 Mio malgré un budget de 16 Mio. Sur PS5 native, la lecture d'une tranche est désormais découpée en morceaux au plus égaux au budget. La soumission compute reste conditionnée à une tranche complète via `bytes_ready` ; la révision stale/remappée conserve son mécanisme d'annulation. Le témoin C++ extrait l'arithmétique exacte avec tranches 4/32/64 Mio et PS5/desktop O0/O2. Aucun gain en frametime console n'est revendiqué avant mesure.

**Cas limite P0.3 :** si le budget de lecture devient nul après une modification des réglages, le chemin natif conserve une progression bornée par la tranche encore disponible, évitant une tâche `IsDecoding` indéfiniment en attente. Le témoin compare également ce cas au comportement desktop d'origine.

## P0.3 — rafale de décodages asynchrones terminés

`TickAsyncDecode` finalise désormais au maximum quatre contextes terminés par passage sur PS5. Les autres restent en file avec leur `IsDecoding` intact jusqu'au tick suivant, sans perdre leurs octets décodés. Chaque tick conserve sa barrière GPU unique s'il a transféré une ou plusieurs textures. Le test source-extrait exerce aussi une rafale de onze textures en trois ticks, ainsi que les refus de staging, les révisions CPU périmées et une soumission rejetée. Cette borne s'applique au nombre de contextes, pas au temps absolu d'un upload individuel. Aucun gain FPS console n'est encore mesuré.

Le test `check-ps5-f07-texture-upload-rollback-host.py` est également réaligné sur l'allocation `upload_size` du correctif de staging court, afin de supprimer son ancienne recherche d'ancre devenue invalide.

## P0.4 — activation tardive de l'unswizzle GPU

Si l'option GPU BCn 3D est activée après la construction du cache alors que les paramètres `swizzle_chunk_size` et `swizzle_slices_per_batch` sont nuls, l'upload passe par le chemin CPU synchrone au lieu de créer une tâche asynchrone impossible à terminer. Une tâche existante avec budget nul est annulée en différé avec `CpuModified` préservé et `IsDecoding` effacé. Les témoins source-extraits couvrent les deux budgets nuls et l'admission une fois les paramètres valides. La fluidité en jeu reste à mesurer.

## P0.3 — sondages mémoire évités pendant le nettoyage des textures propres

Dans `RunGarbageCollector`, le calcul `DirtyEvictions()` pouvait appeler la sonde directe de mémoire graphique avant de découvrir que la texture LRU n'avait aucun téléchargement GPU à effectuer. Ce sondage peut accéder au noyau et se répéter jusqu'au plafond existant de 8 192 visites, sous `texture_cache.mutex`. Le test et le garde sont inversés : seuls les candidats ayant réellement besoin d'un download consultent la sonde. Les décisions concernant les textures sales, coûteuses et le mode d'éviction agressif restent les mêmes. Le témoin C++ source-extrait vérifie 1 000 entrées propres sans sonde et les scénarios sales/agressifs en O0/O2. La mesure du frametime en console reste à effectuer.

## P0.3 — vérification de la liaison du buffer compute indirect

`DispatchCompute` utilisait `buffer->Handle()` après `ObtainBuffer` sans vérifier que le buffer indirect était disponible. Sur PS5, un retour nul provoquait une déréférence invalide après les revalidations des descripteurs et sous les deux verrous de caches. Le chemin natif refuse maintenant le dispatch avant de demander un contexte de rendu ou d'enregistrer une barrière. Le chemin desktop reste inchangé ; le dispatch indirect valide conserve son ordre et ses barrières. Un test C++ source-extrait doit vérifier buffer manquant/valide, pipeline non lié, et les modes PS5/desktop `-O0` et `-O2`. Aucun gain FPS console n'est présumé.

## P0.4 — taille des copies de réinterprétation Vulkan

Le rendu natif PS5 abandonne les réinterprétations sans copie, avant toute invalidation de shadow ou demande d'un buffer temporaire de taille zéro. Pour les copies non vides, la taille du buffer intermédiaire est désormais calculée en `size_t` avec contrôles explicites des dimensions nulles, des multiplications et de l'addition cumulée ; un format invalide ou un débordement est rejeté sans enregistrer la commande. Le chemin desktop demeure inchangé. Un témoin C++ extrait vérifie une copie valide, plusieurs copies, dimensions nulles, multiplications et somme débordantes sous UBSan O0/O2. Le résultat GPU réel reste à vérifier sur console.

**Contrôle supplémentaire F07 :** `GetTemporaryBuffer` dispose de `8*sizeof(size_t)` cases, chacune correspondant à une puissance de deux. La réinterprétation PS5 refuse maintenant toute taille totale supérieure à la plus haute case, même en l'absence de débordement `size_t`. Le témoin inclut une seule copie géante arithmétiquement représentable mais au-delà du tableau de scratch buffers.

## P0.4 — échec de la barrière de visibilité après upload asynchrone

Un lot natif de quatre décodages terminés maximum est suivi par ses identifiants d'images sur la pile, sans allocation supplémentaire sous `texture_cache.mutex`. Si `InsertUploadMemoryBarrier` rejette le transfert, tous les uploads du lot sont marqués `CpuModified` et désenregistrés de la mémoire suivie, pour éviter de conserver des textures HUD apparemment propres mais non visibles au GPU. Les décodeurs ont déjà été déverrouillés et détruits ; les tâches ne restent pas `IsDecoding`. Le témoin source-extrait teste deux uploads suivis d'un échec de barrière, l'annulation des deux révisions et un upload frais lors du tick suivant. Ce correctif ne démontre aucun gain FPS tant qu'il n'est pas exécuté sur console.

## P0.4 — conversion des coordonnées avant les copies Vulkan

`TextureCacheRuntime::ReinterpretImage` convertissait les abscisses et largeurs source avec une multiplication 32 bits **avant** les vérifications de dimension et d'allocation. Une valeur admissible après division pouvait donc être tronquée durant la multiplication. Sur PS5, les formats à ratio nul et les abscisses source négatives sont refusés, le calcul est fait en 64 bits, puis son résultat vérifié contre les bornes du type offset/extent avant de construire les `VkBufferImageCopy`. Le comportement desktop est conservé. Le test source-extrait vérifie le cas de multiplication 32 bits débordante mais de quotient valide, les formats invalides, les offsets négatifs et les largeurs converties invalides en O0/O2. Les performances et les pixels réels ne sont pas encore mesurés sur PS5.

## P0.4 — ne pas invalider un resolve MSAA pour une copie rejetée

Sur PS5, `ReinterpretImage` invalide désormais le shadow MSAA de destination uniquement après validation des copies et allocation réussie du scratch buffer. Les dimensions vides, formats invalides et dépassements de taille ne détruisent plus l'état du resolve déjà disponible ; toute copie valide garde une invalidation avant l'enregistrement Vulkan. Le témoin source-extrait vérifie le nombre d'invalidations en plus des allocations refusées, et conserve le comportement desktop original. Pas de mesure GPU console.

## P0.3 — staging incomplet pendant les téléchargements de textures évincées

`PrefetchDownloads` pouvait enregistrer `Image::DownloadMemory` avec une région de staging GPU plus courte que la texture, ou laisser propager un refus d'allocation sous `texture_cache.mutex`. Sur PS5, l'admission vérifie maintenant `mapped_span.size_bytes()` et traite une exception d'allocation comme un refus de préchargement. Un buffer différé partiellement obtenu est restitué ; la passe spéculative s'arrête sans annoncer d'upload valide, et le nettoyage autoritaire conserve sa politique et son attente GPU. Le témoin C++ source-extrait de balayage mixte est exécuté avec et sans `PS5_NATIVE` sous ASan/UBSan, incluant mapping court et allocation refusée. La copie effective du pilote et l'amélioration de frametime FC27 ne sont pas établies.

## P0.4 — ne jamais évincer une texture GPU sale après refus du staging individuel

Lorsque `PrefetchDownloads` ne fournit pas de copie, `Cleanup` déclenche un téléchargement GPU individuel avant de supprimer l'image. Si son allocation échoue avec `std::bad_alloc`, renvoie un handle nul ou une zone plus courte que la texture, le chemin natif PS5 conserve désormais la texture et passe à l'entrée LRU suivante. `IsDownloadable` et le suivi GPU restent intacts ; aucune fausse copie invitée n'est validée. Une allocation saine conserve `DownloadMemory`, `Finish` et `SwizzleImage` dans le même ordre. Le nouveau témoin source-extrait vérifie les refus ainsi que le succès normal en O0/O2, PS5 et desktop. Ce correctif est une protection de données, pas une preuve de fluidité FC27.


## P0.3/P0.4 — handles Vulkan nuls malgré un mapping complet

Les téléchargements anticipés du GC et les uploads synchrones refusent désormais sur PS5 native un buffer Vulkan nul même si le mapping expose assez d'octets. Le GC ne planifie aucune copie spéculative invalide ; l'upload conserve CpuModified pour réessayer. Le générateur du port garde ces deux gardes. Les tests source-extraits reproduisent explicitement le cas handle nul / mapping complet, en plus du staging court, du refus et du succès, sous compilation hôte. Aucune amélioration du frametime FC27 n'est déduite de ces tests.
