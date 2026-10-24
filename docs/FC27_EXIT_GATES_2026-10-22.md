# Eden Encore — reste à faire pour FC27 (critères de sortie)

## Tableau de bord de progression — 22 octobre, état après `da6d57c`

**Il reste six critères techniques ouverts (F01–F06), puis la qualification console F07.** Les correctifs et les contrôles hôte réussis font avancer des sous-chemins précis, **mais aucun critère technique complet n'a encore satisfait tous ses critères de clôture**.

**Ne pas confondre trois décomptes :**

- **Revue initiale des sources d'émulation : 0 fichier restant** (registre vérifié par `tools/check-eden-optimization-coverage.py`, fast/preflight `EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS`).
- **Revue source de tous les composants : 62 fichiers restants**, exclusivement dans `headless/prosperoeden/` et séparés de l'audit moteur. Le fichier commun `runtime_shims.cpp` a déjà été classé avec le moteur.
- **Nombre de fichiers exigeant encore un changement d'optimisation/correction : inconnu**. Un fichier déjà revu peut contenir un défaut découvert lors d'un rejeu ; ni « 0 » ni « 62 » ne mesure les corrections restantes.

| Critère | État technique | Dernier progrès démontrable | Travail empêchant la clôture |
| --- | --- | --- | --- |
| F01 — contention et saccades GPU/CPU | **INVESTIGATION** | Mémoire paginée, préflight GPU et déduplication de samplers par draw (`abbf9c5`, `da6d57c`), tests de sources en CI | Identifier et diminuer la section *réellement* responsable des attentes cache ; test de concurrence/benchmark avant-après et compilation native validés |
| F02 — pics de compilation JIT | **INVESTIGATION** | Invalidation et limites de cache précédemment gardées | Rejeu par cœur de la compilation et des invalidations avec compteurs et comportement pré/post correctif |
| F03 — HUD actualisé | **À QUALIFIER** | Récupération des mappings TIC/TSC, test hôte existant | Tests de fraîcheur TIC → vue → descripteur → barrières → présent, y compris alias et retour de NULL |
| F04 — maillots et terrain corrects | **À QUALIFIER** | Sécurités DMA, tailles d'index et transferts déjà intégrées | Rejeu de contenu des alias/remaps, upload et invalidations sans perte de données |
| F05 — simulation HLE qui avance | **INVESTIGATION** | Notifications producteur et horodatage conditionnel validés en hôte | Rejeu déterministe complet HID/HLE/IPC → queue → fence → present ; prouver les réveils et l'absence de frame périmée |
| F06 — commandes et match sans gel | **À QUALIFIER** | Parcours contrôleur et symptômes de pause documentés | Rejeu Npad/HID et commandes modifiées, transitions pause/mi-temps/fin |
| F07 — qualification console | **OUVERT** | Aucune comparaison A/B sur le même binaire récent | Une campagne finale, seulement lorsque F01–F06 disposent de preuves suffisantes |

**Contrats :** les six premiers se closent par preuve source + hôte + CI + compilation native ; **F07 est le seul critère nécessitant la console**. Les anciennes traces ne prouvent pas encore une amélioration de FPS ou la disparition des gels.

**Sélection de fichiers encore actifs sur les problèmes, déjà revus dans l'inventaire :**
`vulkan_rasterizer.cpp` (`OnCPUWrite`/`PrepareDraw`),
`vk_graphics_pipeline_cost.cpp` (`ConfigureImpl`),
`video_core/buffer_cache/buffer_cache.h`,
`texture_cache/texture_cache.h`,
`video_core/texture_cache/util.cpp`,
`video_core/memory_manager.cpp`,
`buffer_queue_producer.cpp`,
`buffer_queue_core.cpp` et `surface_flinger.cpp`.
Il ne s'agit **pas** d'une liste exhaustive des fichiers qui devront être modifiés.

**Temps de clôture : non estimable de manière fiable**, tant que les reproductions F01/F02 et les replays F03–F06 n'ont pas identifié l'effort exact. Remplacer ce constat par un nombre d'heures arbitraire serait une fausse visibilité. Le suivi porte sur les preuves manquantes, pas sur un calendrier inventé.

**Référence actuelle :** HEAD `da6d57c` (mémorisation de sampler par draw et test de génération), fast gate, prévalidation, CodeQL C++ et compilation native déclenchés mais non définitifs au moment de cette entrée. [Build natif](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39849801544), [Fast gate](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39849801419).

---

**État établi le 22 octobre 2026.** Branche unique :
`dev/ps5-sparse-jit`. Base native vérifiée :
[`69fdf79`](https://github.com/niakw/Prospero.Eden-Encore/commit/69fdf7912de4cb0264d95bcbfcf61ad49d20d95c).

> **Indicateurs séparés : 0 / 6 chantiers techniques clôturés sur code + tests,
> et F07 = qualification matérielle distincte.**
> Les six premiers chantiers **ne requièrent aucune nouvelle preuve sur console**.
> Une correction peut satisfaire plusieurs critères, ou aucun si les tests ne
> couvrent pas la cause identifiée. Une CI verte seule n'est pas une preuve
> que tous les chemins du sous-système sont couverts. Les `430/492` sources examinées et les `409`
> contrats SOURCE/OPEN sont des indicateurs historiques d'inventaire et de
> qualification, **pas des compteurs d'optimisations restantes**.

## Socle CI — terminé pour le SHA de référence

| Preuve | État | Exécution |
| --- | --- | --- |
| Fast gate et régressions hôte C++ | **VERT** | [39775426169](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426169) |
| Prévalidation de toutes les sources | **VERT** | [39775425826](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775425826) |
| Build/package natif PS5 | **VERT** | [39775426085](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426085) |
| Analyse sécurité CodeQL | **VERT** | [39775426078](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426078) |
| **Résultat FC27 sur matériel pour ce SHA (F07 uniquement)** | **NON MESURÉ** | Aucun test console du SHA de référence |

Cette base inclut déjà les gardes TIC/TSC, les limites des buffers
indirects / SSBO / TBO / CBUF, les liaisons compute périmées, la
mise à jour des plages d'indices, le coût des samplers et le
correctif du registre AMD. Leur réussite en CI n'est pas une
qualification de performance, de HUD ou de fidélité des textures.

## Tableau des sept critères de sortie

Les états ont un sens strict : **OUVERT** = une lacune de code, de reproduction ou
 de couverture de tests subsiste ; **INVESTIGATION** = les chemins propriétaires sont
repérés, la cause n'est pas totalement démontrée ; **À QUALIFIER** = un correctif
existe, mais il manque un test de non-régression ou une preuve de sélection native.
**F01–F06 se clôturent exclusivement avec preuves source, tests hôte, replay
et CI/native**, indépendamment d'un test console. **F07 seul** mesure le résultat
observable par l'utilisateur ; son état ne bloque pas la clôture des six premiers.

| ID | Priorité | Résultat attendu | Situation vérifiée | Prochaine intervention ciblée | Clôture requise |
| --- | --- | --- | --- | --- | --- |
| **F01** | P0 | **Plus de saccades CPU/GPU liées aux buffers** | **INVESTIGATION.** 1 005 680 attentes du mutex buffers, 9,311 s cumulées dans la trace détaillée. Réductions partielles déjà intégrées : pages jamais possédées, préallocation des descripteurs, samplers consécutifs. | Isoler les sections réellement longues entre `RasterizerVulkan::OnCPUWrite`, `PrepareDraw` et `GraphicsPipeline::ConfigureImpl`. Réduire le travail immuable sous le verrou sans perdre une invalidation. | Test source-extrait concurrents/ownership buffer+texture prouvant l'ordre des invalidations et absence de régression, plus microbenchmark hôte du chemin ciblé et build natif vert. Le gain FPS sur console reste F07. |
| **F02** | P0 | **Supprimer les très gros pics de compilation JIT** | **INVESTIGATION.** Les traces comportent des images de plusieurs centaines de ms à plus d'une seconde et de fortes compilations JIT cumulées. Le sparse JIT expérimental est OFF en release ; l'ancienne session sparse utilisait un **autre SHA**. | Isoler par cœur les compilations froides/répétées, invalidations de blocs et limites du cache ; privilégier une correction ciblée plutôt que monter les tailles et les threads au hasard. | Reproduction hôte des invalidations/compilations répétées par cœur avec compteur avant/après, tests JIT O0/O2, absence de corruption mémoire sous sanitizers et build natif vert. Aucun A/B console nécessaire pour cette clôture technique. |
| **F03** | P0 | **HUD présent et actualisé en continu** | **À QUALIFIER.** Gardes TIC/TSC et récupération de mappings manquants intégrés, mais la dernière console montrait encore des éléments de HUD figés/disparus. Zéro `EDEN_GPU_DRAW_DROP` observé dans l'ancienne trace ne prouve pas la fraîcheur des pixels. | Tracer le parcours TIC/TSC → image view → descripteur graphique → barrières/feedback → présentation, avec la durée de validité et les écritures CPU/GPU. | Tests déterministes TIC/TSC, vues NULL, réutilisation après remap et barrières/feedback couvrant le chemin sélectionné ; assertions de fraîcheur/invalidations et CI/native verts. L'aspect visuel sur console relève seulement de F07. |
| **F04** | P0 | **Maillots, terrain et autres textures sans trous ni corruption** | **À QUALIFIER.** Limites DMA, vertex/index, slots SSBO/TBO et mappings textures corrigées côté source, sans preuve d'une restitution correcte de FC27. `memory_short=0` dans l'ancien relevé. | Vérifier alias/remap, invalidations de textures, vues périmées et échelles/régions d'upload ; distinguer géométrie absente et texture invalide. | Tests host source-extraits couvrant les alias/remaps, régions DMA, vertex/index, uploads et formats pertinents, avec vérification du contenu et absence de dépassement ; sélection native verte. Fidélité réelle en match à vérifier dans F07. |
| **F05** | P1 | **Image affichée = simulation du jeu qui avance** | **INVESTIGATION.** ~30 FPS Vulkan peuvent masquer une scène bloquée. L'ancien gel de pause/fin de match avait GPU et compositor actifs. Le service `IHOSBinderDriver` concentre des attentes IPC mais elles ne sont pas toutes des coûts évitables. | Corréler progression du jeu/HLE, transactions `TransactParcelAuto`, dequeue/queue de buffers, fences et horodatages de présentation. Ne pas forcer la cadence ni sauter un fence. | Rejeu déterministe de la chaîne HID/HLE/IPC buffer queue → fence → present, invariants de progression, anti-double-present/notification perdue et tests de blocages ; CI/native verts. Réactivité ressentie en jeu uniquement F07. |
| **F06** | P1 | **Match complet : contrôles cohérents, pas de gel ni crash** | **À QUALIFIER.** La session console récente ne semblait plus planter/geler mais de forts lags persistaient ; les anciens gels pause/mi-temps/fin de match et paramètres de commandes non appliqués n'ont pas été clos sur la révision actuelle. | Vérifier le passage DualSense → HID/Npad → actions du jeu, les états de commande personnalisés et la progression HLE des menus/écrans de fin. Ne pas forcer de mapping global pendant le match. | Tests de bout en bout côté hôte pour transitions pause/mi-temps/fin, style HID/Npad, persistance et mapping de commande, plus analyses des attentes/signalements d'erreurs ; CI/native verts. Essai de match complet uniquement F07. |
| **F07** | P0, final | **Qualification reproductible sur PS5 FW 13.60** | **OUVERT** : CI verte ≠ résultat sur console. Les deux traces historiques les plus récentes ont des SHAs et des états sparse différents, non comparables comme A/B. | Quand des correctifs ciblés F01–F06 auront un candidat CI vert, figer une seule révision/paramétrage, lancer scénario froid **puis** scénario cache chaud, sans mélange des profils ni changements simultanés. | Relever `late50`, `late100`, intervalle maximal, p95/p99, progression du jeu, HUD, maillots, freeze et commandes. Comparaison contrôlée, effet attribuable, validation explicite. |

### Ce qui n'est **pas** une tâche restante

- Migrer d'autres centaines de fichiers **sans défaut précis**.
- Revalider comme « optimisation » un backport seulement parce qu'il est
  référencé par le graphe d'architecture.
- Agrandir d'office la queue GPU : `gpu_full_ms=0` dans les anciens relevés.
- Déverrouiller le cache pendant des invalidations CPU/GPU ou supprimer les
  fences sous prétexte que les FPS affichés restent proches de 30.
- Activer par défaut les variantes sparse/shared JIT, CPU→GPU différé, ou
  toute expérimentation DEV non qualifiée.
- Faire tester une nouvelle image uniquement pour valider des sources qui
  ne sont pas encore des candidates mesurables.

### Ordre d'exécution et journal de décision

1. **F01** et **F03/F04** d'abord, dans les fonctions effectivement
   responsables des acquisitions CPU/GPU et de la cohérence des descripteurs.
   Les correctifs successifs de sûreté SSBO sont terminés **au niveau CI**
   sur `69fdf79` ; ils ne ferment pas ces objectifs.
2. **F02** séparément : compilation et réutilisation des blocs par cœur ;
   ne pas confondre somme du travail JIT multi-cœur et temps perdu par image.
3. **F05/F06** : confirmer progression HLE, buffers de présentation et
   contrôle de jeu, plutôt que conclure d'après les FPS du compositor.
4. **F07** reste distinct : une seule éventuelle campagne de qualification
   matérielle finale. **Aucune preuve console n'est demandée pour fermer F01–F06**.
   Les tests hôte démontreront la correction technique, sans prétendre prédire
   précisément les images/sec ni l'aspect final en match.

Après chaque lot : noter **le ou les IDs techniques affectés**, le commit,
le test source-extrait/rejeu/benchmark, les résultats CI et le SHA de
sélection native. Fermer **F01–F06 sans passage sur console** dès que les
invariants correspondants sont établis. Garder F07 indépendant. Une baisse du nombre de sources restantes
n'est plus une métrique de progression ici.

**Sources de mesures :**
[FC27_GPU_SOURCE_TARGETS_2026-10-21.md](FC27_GPU_SOURCE_TARGETS_2026-10-21.md),
[FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md](FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md),
[FC27_PAUSE_FREEZE_R435.md](FC27_PAUSE_FREEZE_R435.md),
[FC27_TIC_TSC_MISSING_CHANNEL_MAPPING_2026-10-22.md](FC27_TIC_TSC_MISSING_CHANNEL_MAPPING_2026-10-22.md),
[EDEN_SINGLE_FINAL_RUNTIME_DECISIONS_2026-10-21.md](EDEN_SINGLE_FINAL_RUNTIME_DECISIONS_2026-10-21.md).

**Périmètre séparé :** travaux launcher/UI, couvertures 3D, avatar, jaquettes,
glyphes et traductions. Ne pas les mélanger à la mesure de stabilité du moteur.


## F05 — 22 octobre : réveil producteur après détachement du plus ancien tampon libre

**Source ciblée :** `eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`
(`BufferQueueProducer::DetachNextBuffer`, sélectionné directement par CMake).
Le chemin `DetachBuffer` publiait déjà `SignalDequeueCondition` après
`FreeBufferLocked`, mais `DetachNextBuffer` ne le faisait pas. Une
transition de la file pouvait donc passer inaperçue pour un producteur
attendant la génération suivante. Le chemin normal conserve l'ordre de
sélection du tampon le plus ancien, la propriété du buffer transféré et
les fences ; seule la notification est ajoutée, sous `core->mutex`.

**Preuve technique :** `tools/check-native-nvnflinger-detach-wake-host.py`
compile le corps C++ sélectionné à -O0/-O2 sous UBSan, vérifie
les refus sans signal, le choix du plus ancien tampon libre,
les transferts de fence et exactement un réveil après chaque détachement
réussi. La parité reproduit le changement depuis la source épinglée.
**F05 reste ouvert** : ce test ferme le sous-chemin « détachement sans réveil »,
pas toute la progression HLE/IPC / présentation.

## F05 — 22 octobre : conserver la frame réelle jusqu'à la notification

**Source native :** `vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`.
`QueueBuffer` construisait une `BufferItem` complète, mais vidait son
`graphic_buffer` et remplaçait son `slot` par `INVALID_BUFFER_SLOT` juste avant
d'appeler `OnFrameAvailable` ou `OnFrameReplaced`. Cela rompait le contrat de
notification avec tout consommateur utilisant les champs du paramètre.
Le consommateur `ConsumerBase` actuellement retenu ignore ces champs dans
ses callbacks : **aucun gain de FPS ou déblocage FC27 n'est donc prétendu**.

La correction conserve la frame et sa référence au buffer jusqu'à la fin
de la notification **hors verrou**, sans supprimer de fence ni modifier la
politique de remplacement des frames. Un test C++ extrait le dispatch
de la méthode réellement sélectionnée, compile à O0/O2 sous UBSan et
vérifie les callbacks « available » et « replaced », l'identité de la
frame/buffer/slot et l'absence de double notification. La parité
`check-vendor-consolidation-debt.py` est mise à jour ; fast gate et
prévalidation doivent rester verts. **F05 reste ouvert** jusqu'à la preuve
de progression de bout en bout.

## F01/F05 — 22 octobre : limiter les logs d'attente normale de NVNflinger

Dans `BufferQueueProducer::WaitForFreeSlotThenRelock`, le cas `queue.size() > max_buffer_count` représente une attente de retour de capacité, pas une erreur de service. Sa journalisation `LOG_ERROR` se produisait à chaque itération de la boucle et pouvait créer des écritures de log en rafale lorsque le consommateur était en retard, même sans diagnostic détaillé. Elle passe à `LOG_DEBUG`, tout en conservant la condition d'attente, les réveils, l'ordre des frames et les fences à l'identique. L'oracle de parité maintenue vérifie la substitution exacte depuis la source épinglée. **Amélioration préventive du coût CPU/log ; aucun gain FC27 ni correction de freeze n'est encore revendiqué.**

## F05 — 22 octobre : lecture des numéros de frame sous verrou

Le diagnostic de `DequeueBuffer` relisait `slots[*out_slot].frame_number` après la sortie de `core->mutex`, pendant qu'un autre producteur ou consommateur pouvait modifier les métadonnées du slot. Le numéro est maintenant capturé sous verrou à la sélection, puis actualisé dans le chemin de réallocation sous le même mutex. Seule cette copie est utilisée par `LOG_DEBUG`. Cela évite une lecture concurrente indéfinie et un diagnostic de frame incohérent, sans changer la propriété des buffers, les fences, la sélection du slot ni la synchronisation du jeu. L'oracle des sources maintenues reproduit chaque remplacement exactement depuis la version épinglée. **F05 demeure ouvert ; ce garde ne prouve pas un déblocage FC27.**

## F05 — producteur unifié en release et DEV

La sélection précédente du producteur épinglé en release omettait les correctifs NVNflinger retenus en DEV. L'introduction d'une seconde unité standard avait réparé la livraison, mais doublonnait le code et rendait l'inventaire architectural obsolète. Désormais **une seule source maintenue** (`vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`) est sélectionnée par CMake dans les deux profils. Le bloc `EDEN_NVNF_DEQUEUE_PROFILE` n'est compilé qu'en DEV et protège uniquement le chronométrage de dequeue ; les notifications, la préservation des métadonnées des frames et les gardes mémoire sont communs. Le fichier standard redondant est retiré, sans toucher à la source épinglée. Le catalogue d'architecture conserve ainsi sa cardinalité historique.

La parité exacte des sources et les tests hôte vérifient l'intégration. **F05 reste ouvert** : sélection native et compilation CI ne prouvent pas encore la progression de la simulation sur console.

## F01/F05 — 22 octobre : horloge de buffer uniquement lorsque l'historique est actif

Le chemin `BufferQueueProducer::QueueBuffer` du moteur sélectionné demandait `Common::g_wall_clock.GetTimeNS()` à chaque queue de frame, bien que `enable_buffer_history` soit désactivé par défaut. La correction lit le paramètre une seule fois sous le mutex existant et n'échantillonne l'horloge que si l'historique est actif. Le numéro de frame, le `queue_time`, les fences, les callbacks et les changements d'état restent inchangés. Un témoin hôte compile le fragment réel et exécute les deux configurations (`-O0`, `-O2`, UBSan), ajouté à la prévalidation et au fast gate. **Objectif : supprimer un coût inutile du chemin chaud ; aucun gain FPS PS5 ou déblocage FC27 n'est déduit de ce contrôle.**

## F01 — 22 octobre : réutilisation bornée des samplers par draw

`GraphicsPipeline::ConfigureImpl` invalidait sa petite mémorisation dès qu'un handle de sampler différent intervenait, puis la recréait à chaque étage shader. Or l'identité du sampler ne peut changer pendant cette configuration sous les deux mutex invités. Une table directe de 16 entrées sur la pile réutilise maintenant les identifiants correspondant à des handles non consécutifs et entre les étages **du même draw**, sans allocation ni identité rémanente entre draws. Les collisions ne compromettent rien : elles entraînent seulement une nouvelle recherche `GetSamplerId`. L'ordre des vues, les samplers dans les descripteurs, les invalidations et les locks restent identiques. Le test hôte exécute la logique C++ sélectionnée (table vide, A/B/A, passage d'étage, collisions, nouveau draw, même vue avec samplers différents) en `-O0` et `-O2`, avec UBSan. **F01 reste ouvert : économie de recherches démontrable, baisse de latence/FPS sur console non mesurée.**

## F05 — 22 octobre : insertion idempotente dans la pile de composition

Le chemin sélectionné `SurfaceFlinger::AddLayerToDisplayStack` permettait plusieurs insertions d'une même couche (`consumer_binder_id`) sur un même affichage. Le compositeur parcourt la pile à chaque frame, de sorte qu'une seconde insertion double inutilement le parcours et la composition de la même image. La source `vendor/encore-active/eden-surface-lifecycle/src/core/hle/service/nvnflinger/surface_flinger.cpp` refuse désormais une insertion si cet identifiant existe déjà **dans cet affichage uniquement**. L'ordre des autres couches et la possibilité d'une couche sur plusieurs affichages restent intacts. L'installateur de source active vérifie l'ordre de cette garde, et `tools/check-surface-lifecycle.py` compile et exécute les méthodes réelles : doublons, deux affichages, binder invalide, détachement et fences sans double libération.

**F05 reste ouvert :** correction d'une anomalie réelle de gestion des couches, mais rien dans les anciennes traces ne prouve que FC27 envoyait une commande d'attachement dupliquée. Il reste à démontrer la progression HLE/IPC→présentation de bout en bout.

## F02 — 22 octobre : invalidations de blocs JIT hors du verrou de publication

Les méthodes de JIT **A32** et **A64 standard** maintenues tenaient `invalidation_mutex` pendant `emitter.InvalidateCacheRanges` ou le vidage complet (`block_of_code.ClearCache` et `emitter.ClearCache`). Ce verrou protège en réalité l'arrivée des demandes depuis les autres threads. Le JIT partagé expérimental effectuait déjà un instantané des demandes, puis exécutait les invalidations après avoir rendu le verrou.

Les deux modes de release utilisent désormais **la même séparation** : sous verrou, effacement du bit de halt, capture et retrait atomique du flag de vidage complet et des plages (par `ranges.swap`) ; hors verrou, invalidation effective et restauration RSB. Les demandes arrivées durant l'exécution restent dans la file pour la prochaine itération au lieu d'être effacées à la fin de l'ancienne invalidation. Les compteurs DEV sont associés au snapshot réellement traité.

Le nouveau test `tools/check-native-jit-invalidation-snapshot-host.py` compile les corps des trois méthodes depuis les sources réelles A32/A64, en `-O0`/`-O2`, release et profil DEV. Il déclenche une invalidation **réentrante pendant le traitement**, puis vérifie que le mutex est libre, que les demandes suivantes survivent, que la plage exacte est appliquée et que le vidage complet n'efface pas les nouvelles demandes. Tests ajoutés au fast gate et à la prévalidation. **F02 reste ouvert : réduction du temps passé sous verrou démontrable, mais effet réel sur les pics de compilation et FPS non mesuré sur console.**


## État de qualification technique — 22 octobre, après correctif F02

- **HEAD moteur vérifié :** `e96d474` (les commits `b907007` à `e96d474` réparent uniquement les oracles/test fixtures, sans autre changement A32/A64 depuis `a607654`).
- **Fast gate : réussi** [39860743923](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39860743923). Source-extracted A32 et A64 : cas de vidage complet et de nouvelle invalidation pendant l'ancien traitement, `-O0` et `-O2`, release et DEV.
- **Prévalidation complète : réussie** [39860743911](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39860743911).
- **Build PS5 source moteur `a607654` : réussi** [39858896077](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39858896077). Une recompilation explicite de la source courante est demandée séparément, et son résultat n'est pas anticipé.
- **CodeQL C++ : en cours** [39860743939](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39860743939), alors que Python et Actions sont réussis. Ne pas annoncer CodeQL entièrement vert avant la fin.
- **F02** : sous-mécanisme d'invalidation concurrente corrigé et testé. Les durées globales de compilation JIT et l'effet sur les saccades restent non mesurés.
- **F01** : dans `PrepareDraw`, la section sous mutex inclut `ConfigureImpl` **mais aussi** les états dynamiques et l'enregistrement des draws. Elle ne doit pas être libérée prématurément : `DrawIndirect` accède à `buffer_cache`, et la durée de vie des vues/descripteurs d'un draw direct dépend de l'ordre de publication des commandes. Les anciennes mesures désignent la contention sur `buffer_cache.mutex`, mais ne prouvent pas qu'un déplacement de ces opérations hors verrou serait correct. Tant qu'une extraction sûre des données et des barrières n'est pas démontrée, **aucun unlock spéculatif**.
- **F03–F06** : restent ouverts. Aucun correctif de texture ni contrôle de match ne peut être considéré comme complet sur la seule base d'une compilation.

**Décision avant F07 :** continuer les preuves F01–F06 sans nouvelle session PS5, et conserver les tests de fidélité des caches, du HUD et des commandes. Les résultats de CI n'établissent ni une cadence stable des frames invitées ni un HUD correct.

## F04 — 22 octobre : bounds de la page-table BufferCache en cas d'adresse invalide

Le chemin maintenu `BufferCache::IsRegionRegistered` parcourait une table limitée à 16 Gio tout en calculant `addr + size` sans garde supérieure. Sur une adresse malformée, une plage débordante ou dépassant cette limite pouvait mener à un index hors de la table. Une garde rejette désormais les plages vides, hors domaine et non représentables avant tout calcul de borne haute ou accès `page_table[]`, sans changer le parcours des plages valides. Le test source-extrait `check-ps5-buffer-region-multipage-host.py` vérifie les plages valides multipages, les plages croisées au-delà de 16 Gio, les adresses proches de `UINT64_MAX` et zéro octet en `-O0` et `-O2` (UBSan). Les deux oracles de reproductibilité recomposent exactement la nouvelle source à partir du backport épinglé. **F04 reste ouvert :** cela prévient un accès hors limites, mais n'établit pas une correction visible des maillots ou du terrain FC27.

## F03/F05 — 23 octobre : ne jamais recomposer un buffer déjà libéré

`HardwareComposer::CacheFramebufferLocked` (source originale épinglée) renvoyait `CachedBufferReused` après l'échec d'acquisition d'un **ancien** buffer déjà libéré. Lorsque une autre couche présentait une image récente, la composition pouvait inclure ce buffer périmé, désormais disponible pour l'écriture du producteur. La nouvelle source maintenue `eden-surface-lifecycle/src/core/hle/service/nvnflinger/hardware_composer.cpp` renvoie `NoBufferAvailable` uniquement dans ce cas, conservant le cache encore acquis, la nouvelle acquisition et le traitement normal des couches indépendantes. `ComposeLocked` saute déjà explicitement les résultats `NoBufferAvailable` avant la lecture du pointeur de buffer.

L'installateur applique **les deux unités complètes** `SurfaceFlinger` et `HardwareComposer` dans l'arbre Eden temporaire ; il vérifie la source originale épinglée par empreinte Git, reconstruit les octets attendus du compositeur, contrôle les deux entrées avant toute écriture et rejette toute modification extérieure. Le test hôte `check-surface-lifecycle.py` exécute la méthode C++ extraite, avec premier manque, réutilisation pendant acquisition, libération puis nouvel échec, nouvelle image et couche indépendante, en `-O0` / `-O2` (UBSan).

**F03 et F05 restent ouverts** : le chemin de référence périmée est corrigé au niveau source, mais la preuve complète HUD et la progression IPC→présentation doivent encore être établies ; ce défaut n'est pas formellement relié aux anciennes traces FC27.


## Cartographie et build du correctif compositeur — 23 octobre

La nouvelle unité native `hardware_composer.cpp` est enregistrée sous le contrat **N23** dans `docs/EDEN_CORE_AUDIT_DEPENDENCIES.md` et `docs/EDEN_ACTIVE_SOURCE_CATALOG.md`. L'inventaire de revue source passe à **493 fichiers, dont 431 traités et 62 sources du lanceur à examiner séparément**. Le nombre de sources moteur restant à parcourir systématiquement reste zéro ; le nombre de corrections encore nécessaires reste inconnu.

La validation complète du correctif de buffer libéré nécessite un **build natif sur le HEAD contenant aussi l'installateur corrigé**, et non sur `ac04f33` (script initial) ou `d1358ab` (premier inventaire). Les anciens résultats ne doivent pas être attribués au nouveau HEAD. F03/F05 restent ouverts tant que l'intégration native et le rejeu global n'ont pas réussi.

## Reprise N23 — contrôle hôte réussi, build final réémis

Le fast gate du code `642f80f` est **vert** ([exécution 39865536857](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39865536857)). Le test compilant `HardwareComposer::CacheFramebufferLocked` depuis la source maintenue et la migration des deux TU passent ; le graphe d'architecture et l'inventaire passent le contrôle initial de prévalidation. Le tableau quantifié du graphe a été recalculé séparément : **480 contrats recensés, 410 SOURCE/OPEN** ; ceci ne correspond pas à des fichiers restant à optimiser.

La compilation native de `157e7e0` a été lancée **avant** la dernière rectification du tableau de graphe. Un build complet est donc redemandé sur cette version cohérente. Ne pas considérer la qualification native F03/F05 comme obtenue avant la fin de ce nouveau build.

## F03/F05 — 23 octobre : rejeu réel des couches composées

Le témoin `tools/check-native-hardware-composer-liveness-host.py` compile **les quatre méthodes C++ du HardwareComposer effectivement installées**, plus la fonction de cadence, en `-O0` et `-O2` sous UBSan. Seuls les objets périphériques (buffers entrants, display GPU et deux consommateurs) sont simulés. Le scénario alterne une couche jeu à cadence double, un HUD indépendant, le maintien d'un buffer encore acquis, sa libération, une acquisition manquante, un nouveau HUD et un nouveau jeu. Les identifiants des images réellement présentées sont comparés pour exclure la réintroduction d'une image libérée. Le test est appelé par le fast gate et la prévalidation via `check-surface-lifecycle.py`.

**Portée :** une preuve de non-régression du compositeur sur ce scénario HLE, non une preuve du comportement du jeu FC27, de l'IPC complet ou de la synchronisation effective de la console. F03/F05 restent ouverts.


## F03/F05 — 23 octobre : borne extrême de cadence du compositeur

Dans `NormalizeSwapInterval`, l'extension des intervalles négatifs évaluait `1 - swap_interval` en entier signé **avant** conversion flottante. Pour `INT32_MIN`, cela débordait en C++ (UBSan). La conversion a été déplacée avant la soustraction, sans changer le comportement des intervalles usuels ; la transformation est désormais contrôlée octet par octet depuis la source épinglée. Le rejeu natif teste `INT32_MIN`, `-1` et `0` en `-O0`/`-O2`, et doit faire échouer l'ancienne fonction sous UBSan. L'installateur accepte exactement la version maintenue précédente pour mettre à jour les staging temporaires, sans accepter de variante inconnue. **Il s'agit d'une correction de sûreté du calendrier de présentation, pas d'une preuve de gain de FPS ni d'une clôture F03/F05.**


## F05 — 23 octobre : un seul affichage par identifiant

`SurfaceFlinger::AddDisplay` créait auparavant une nouvelle pile à chaque appel,
même pour un `display_id` déjà présent. Or `FindDisplay` retourne la première
pile, tandis que `RemoveDisplay` efface toutes celles portant cet identifiant
après n'avoir libéré que les buffers de la première. Cela pouvait produire un
état de propriété incohérent en cas de création en double.

La source maintenue refuse désormais une création répétée avant
`emplace_back`, en conservant l'ordre et le comportement des identifiants
distincts. L'oracle `install-vendored-surface-lifecycle.py` vérifie le
nouveau garde-fou et n'autorise que les empreintes exactes des versions
maintenues précédentes lors d'un staging. Le test hôte
`check-surface-lifecycle.py` exerce deux créations identiques, l'attachement
d'une couche, son unique libération et la création d'autres affichages.

**Commits de ce sous-chemin :** `4cb3fcf` (source), `c955eea` et
`74229dc` (oracles/tests), `767a5d5`, `1475299` et
`8d45284` (migration et corrections de témoin). Un témoin C++ local
couvrant le scénario de doublon a réussi sous UBSan en `-O0`/`-O2`.
La validation complète du test source-extrait, la prévalidation et le
build natif doivent encore être vérifiés pour le dernier HEAD ; ne pas
confondre le témoin local avec une preuve CI.

**Portée :** sûreté d'un cas de duplication des piles d'affichage ;
aucune trace historique FC27 n'établit que cette duplication se produisait.
Aucun gain de FPS, de fraîcheur du HUD ou de déblocage du match n'est
revendiqué. **F05 reste ouvert** jusqu'au rejeu IPC→buffers→fences→présentation.


**Validation native demandée pour ce lot :** le workflow de build sur la branche
`dev/ps5-sparse-jit` est déclenché par un commit portant `[full-build]`.
Cette demande ne préjuge pas du résultat du fast gate, de la prévalidation,
de CodeQL ou du package natif. Aucun test console F07 n'est demandé.


## F04 — 23 octobre : scissor Vulkan, bornes de coordonnées invitées

La source maintenue réellement sélectionnée `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`
contenait des soustractions 32 bits `src.max_x - src.min_x` et
`clip_height - src.max_y` susceptibles de déborder en cas de valeurs de
registres invitées extrêmes. Le décalage dépendait également d'un compteur
`down_shift` sans borne. Un rectangle incorrect peut clipper un draw et
faire apparaître une portion de géométrie manquante, sans qu'une perte
de descripteur ou un draw rejeté soit nécessaire.

Le correctif `60a6661` calcule les différences en 64 bits et borne la
conversion au domaine `s32`. Pour les produits ordinaires représentables et
les décalages valides, il conserve les règles 32 bits originales, y compris
le traitement existant des coordonnées négatives ; la voie large ne couvre
que les valeurs hors plage ou les décalages excessifs.

Le témoin `tools/check-ps5-scissor-extremes-host.py` extrait la fonction
active et l'ancienne fonction épinglée, exige leur identité de résultat sur
un ensemble de rectangles ordinaires, et vérifie sous UBSan que la source
antérieure échoue sur `INT32_MIN`/`INT32_MAX`, quand la version maintenue
ne déborde pas. Les variantes `-O0` et `-O2` sont intégrées à la
prévalidation. Un témoin local de même logique a réussi avant intégration ;
l'exécution CI source-extraite et le package natif restent à vérifier.

**Effet performance non revendiqué :** dans un microbenchmark hôte
non représentatif du GPU PS5, la voie sécurisée a été environ 3–4 ns
plus coûteuse par appel que la voie historique sur l'échantillon ordinaire.
Le gain de sûreté ne clôt donc ni les saccades F01, ni la fidélité FC27 F04.
Aucun test console demandé avant F07.


## F01/F05 — 23 octobre : notification de construction Vulkan sans fuite

**Source native sélectionnée :** `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp`
(`GraphicsPipeline::GraphicsPipeline`). Avant ce lot, `MarkShaderBuilding`
était exécuté au début du constructeur, tandis que le seul
`MarkShaderComplete` garanti était dans la fonction de compilation,
créée après la préparation des métadonnées shader, des layouts,
des allocations de descripteurs et autres opérations pouvant lever
une exception. Un échec pendant cette préparation ou pendant
`QueueWork` pouvait laisser une construction comptabilisée
sans notification de fin.

La correction `c5652a3` ajoute une garde RAII au constructeur :
tant que la construction n'a pas été confiée à la fonction synchrone
ou au worker, toute sortie exceptionnelle appelle
`MarkShaderComplete`. Le constructeur achève maintenant
`ConfigureFunc(spv_modules, stage_infos)` **avant**
`worker_thread->QueueWork`, évitant qu'un worker lancé tôt
voie cette fonction de configuration incomplète. Une fois la mise en
file réussie, le worker conserve son `SCOPE_EXIT` original pour
publier `is_built`, réveiller `build_condvar` et notifier la fin
même en cas d'échec de validation ou de compilation.

**Preuve :** `tools/check-ps5-pipeline-build-handoff-host.py` extrait
la garde réelle et vérifie les invariants d'ordre du constructeur
natif. Son témoin C++ simule les échecs de préparation et de
queue, la compilation synchrone/asynchrone, un worker en échec
et l'absence de notificateur ; son témoin négatif démontre la fuite
de notification de l'ancien comportement. Les cas simulés ont
réussi localement sous GCC/Clang, `-O0`/`-O2` et UBSan. Ce
témoin ne compile pas la totalité de `GraphicsPipeline` ni Vulkan :
la prévalidation et le build natif doivent encore être confirmés.

**Portée limitée :** correction d'un risque démontrable d'attente
prolongée sur notification absente et d'initialisation asynchrone
incomplète. Aucun ancien log FC27 ne prouve que la création
d'un pipeline lançait l'une de ces exceptions. Cette correction
ne valide ni un gain de FPS, ni l'absence de freeze en match.
**F01/F05 restent ouverts**, ainsi que F02–F04/F06.


## F04 — 23 octobre : contrôle strict de parité des coordonnées négatives

Un audit supplémentaire du chemin `GetScissorState` a confirmé un point
subtil des promotions entières en C++ : l'opérande `up_scale` est
`u32`, donc l'expression historique `value * up_scale` suivie du
décalage se comporte en **non signé**, y compris lorsque `value < 0`.
Remplacer ce décalage par un décalage arithmétique signé changerait
la géométrie d'un titre valide. Cette variante a été rejetée puis le
comportement épinglé a été restauré, au lieu de faire passer une
rupture visuelle pour une optimisation.

Les commits `5a8a26f` et `aff4105` maintiennent donc le décalage
historique et ajoutent un témoin explicite : pour un offset
`-96`, `up_scale=1` et `down_shift=1`, le rectangle épinglé
et maintenu renvoient tous deux `-1` après la borne historique.
Une reproduction locale des deux méthodes C++ a été compilée et
exécutée sous **Clang et GCC**, `-O0`/`-O2`, UBSan : **3516**
configurations de rectangles ordinaires/extrêmes validées pour chacune
des quatre combinaisons. Ce test indépendant n'est pas une exécution
de la suite CI complète ni une mesure de performance réelle.

La protection contre les soustractions 32 bits overflow et le
décalage hors plage est conservée. **F04 reste ouvert** tant que la
fidélité du rendu invité n'est pas démontrée. Ne pas annoncer de
résolution du HUD, des maillots ou du terrain de FC27.


## F02 — 23 octobre : purge JIT sous verrou, y compris en pression mémoire

Les interfaces maintenues `a64_interface_standard.cpp` et
`a32_interface_native.cpp` utilisaient `invalidation_mutex` pour les
demandes de vidage provenant d'autres threads, mais **deux chemins
internes chacun** modifiaient directement le booléen partagé
`invalidate_entire_cache` : moins de 1 Mio de code disponible,
et nouvel essai après `std::bad_alloc` de `EnsureMemoryCommitted`.
Ces quatre écritures hors mutex pouvaient se produire en parallèle
avec `InvalidateCacheRange` / `ClearCache` et constituaient une
course de données (undefined behavior en C++).

**Correction appliquée :** les quatre chemins passent désormais par
`ClearCache()`, qui détient le mutex pour déclarer le vidage complet
et publier le signal `CacheInvalidation`, puis exécutent la méthode
`PerformRequestedCacheInvalidation` existante. La remise à zéro
des plages, le snapshot hors verrou, la taille limite d'1 Mio et le
profil standard par cœur restent inchangés. Aucun réglage du cache
JIT ou mode expérimental n'est activé.

**Contrôles :** `tools/check-native-jit-invalidation-snapshot-host.py`
recherche désormais exactement les **deux chemins** de purge de
chaque source A32/A64, sans écritures directes dans l'état de vidage.
Son témoin C++ utilise les méthodes d'invalidation extraites des
sources, vérifie la publication sous un mutex instrumenté,
rejoue une écriture invitée provenant d'un autre thread pendant
`emitter.ClearCache()` et rejette l'ancienne affectation sans verrou
par un contre-test négatif. Le contrat de reproduction octet à octet
du code A32 épinglé dans
`tools/check-maintained-a32-native-interface.py` a été actualisé
afin de garantir que la source réellement compilée intègre le
correctif sans modifications non revues.

**Statut :** source et tests poussés ; exécution de la suite CI,
ASan/UBSan du build complet et qualification native restent à
confirmer. Ce correctif supprime une course de données à
l'invalidation et **ne démontre pas** qu'il supprimera les
pics de recompilation FC27. F02 reste ouvert.



## F01 — 23 octobre : allocations de snapshots GPU hors verrou partagé

**Source active :** `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp`.
`GraphicsPipeline::ConfigureDraw` mémorise la charge utile des descripteurs
Vulkan dans `last_descriptor_payload`. Son premier `assign` pouvait
réserver de la mémoire alors que `PrepareDraw` détenait simultanément
`buffer_cache.mutex` et `texture_cache.mutex`, contribuant à la durée
de détention du verrou lors de la première utilisation d'un pipeline.

Le correctif `e633f3d` déplace **uniquement la réservation de capacité**
dans `GraphicsPipeline::PreflightDescriptorScratch`, déjà exécuté
par le propriétaire GPU **avant** les deux mutex. La réservation est
limitée au nombre immuable `num_descriptor_entries` et seulement aux
pipelines qui conservent réellement un snapshot (buffer de descripteurs
ou ensembles classiques, hors mode push-only). Les vues TIC/TSC,
les lectures mémoire invitées, les uploads et le contenu du payload ne
sont pas lus ou copiés hors du verrou. La branche de repli imbriquée
conserve ses gardes de réentrance.

Le générateur `tools/prepare-vulkan-port.py` et la déclaration C++
native générée ont été mis en cohérence (`4454bbf`), de sorte
qu'un staging natif ne réintroduise pas l'ancienne signature `const`.
Le test `tools/check-ps5-graphics-payload-preflight-host.py`
(`72265ac`, renforcé par `a9743ef`) extrait la vraie méthode
maintenue, vérifie l'identité octet à octet du corps dans le générateur,
et compile sa logique avec un allocateur instrumenté qui refuse une
allocation sous le double verrou. Il contrôle l'ensemble classique,
le buffer de descripteurs, le push-only, le pipeline vide et le
scratch imbriqué ; l'ancien code provoque le refus attendu.

Une **reproduction locale** de la méthode et de son allocateur a
réussi sous Clang et GCC, `-O0` et `-O2`, UBSan. Le script
source-extrait est intégré à la prévalidation ; il attend encore
une preuve CI sur le dernier HEAD. Ce changement retire une allocation
de la section critique lors de certaines premières utilisations,
mais **aucun gain de FPS, de `pair_held` ou de `late50` sur console
n'est encore démontré**. F01 reste ouvert.


## F01/F04 — 23 octobre : suppression de la décision feedback pour les draws sans texture

La source native sélectionnée `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h`
contient désormais un chemin direct lorsque `CheckFeedbackLoop` reçoit une liste
`views` vide. Aucun échantillon ne pouvant référencer un attachement,
il n'est pas nécessaire de comparer la clé des vues précédentes, de
réévaluer les rendertargets ou de construire un nouveau snapshot.
Le cache de décision et les numéros de série sont remis dans l'état
`false` existant, afin que **le draw texturé suivant** recalcule
obligatoirement la décision de barrière.

Le changement est présent dans la source maintenue (`92150c6`) et dans
son backport épinglé (`2fd4743`), pour éviter un écart entre le build
natif et l'arbre de développement. L'oracle du patch source est renforcé
(`69941db`), et `tools/check-ps5-feedback-loop-empty-fastpath-host.py`
(`7f75349`) compile la fonction réellement maintenue et rejoue
un ensemble de transitions `depth→other→depth→empty→depth→color-only→depth`
avec et sans `PS5_NATIVE`, `-O0`/`-O2` sous UBSan.

Une reproduction locale indépendante de ces transitions, compilée sous
Clang et GCC, a passé **huit combinaisons** (compilateur × niveau
d'optimisation × mode natif/amont). La suite native complète et le rejeu
du patch sur la totalité des fichiers épinglés restent à confirmer.

**Impact limité :** suppression d'un travail non nécessaire sur les draws
sans image ; aucune donnée de scène FC27 ne permet encore de quantifier
un gain de `pair_held`, `late50` ou FPS. Ce n'est pas une preuve de
correction des textures de maillots ou du HUD. F01, F03 et F04 restent ouverts.


## F01 — 23 octobre : hypothèse des prévalidations 1024 rejetée

La revue de `GuestDescriptorQueue::PreflightLargeGuestDraw` révèle un retour immédiat lorsque `entries <= 0x400`. `DescriptorEntryReservation()` renvoie précisément `0x400` pour un shader sans descripteur. Les six précontrôles supplémentaires ne pouvaient donc pas provoquer le `WaitWorker` soupçonné. Les changements d'optimisation correspondants ont été **annulés** après cette contre-vérification, et le témoin reposant sur cette fausse hypothèse retiré de CI. Aucun gain de FPS ni de contention n'est revendiqué sur cette piste ; F01 reste ouvert.


## F01 — 23 octobre : précontrôle exact des petits descripteurs après resélection

**Défaut établi dans la logique du code :** `UpdateDescriptorQueue::Acquire`
attend le worker lorsque `used + required_entries >= frame_payload_size`.
Cependant, `PreflightLargeGuestDraw` ignorait toute réservation
`entries <= 0x400`, même lorsqu'une attente était nécessaire. Cela
pouvait laisser un nouveau shader à petits descripteurs découvert
**après un premier drain et une resélection de pipeline** arriver à
`Acquire` sous le double verrou GPU et y déclencher `WaitWorker`.

Une première hypothèse, selon laquelle les shaders sans descripteurs
attendaient inutilement, a été réfutée : leur nombre de secours
`0x400` était explicitement ignoré par le précontrôle d'origine.
Cette modification a été annulée, avec retrait de son test invalide.

Le correctif retenu est différent : `PreflightExactGuestDraw`
reproduit maintenant la condition exacte d'`Acquire` pour **tout
nombre positif** d'entrées inférieur à la taille de la file. Il est
appelé sur trois sites graphiques et trois sites compute,
**uniquement si `HasDescriptorEntries()` est vrai**, avant de prendre
les mutex des caches. Les changements sont synchronisés dans
`vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp` et
`tools/prepare-vulkan-port.py` ; le test de provenance du générateur
doit empêcher le staging d'une ancienne implémentation.

**Témoin :** `tools/check-ps5-exact-descriptor-preflight-host.py`
extrait la méthode exacte issue du générateur et les six conditions
C++ maintenues. Il vérifie le seuil `Acquire` sur une petite file,
le contre-exemple historique (`4095/4096` entrées utilisées +
`1` entrée demandée), et les resélections vers un shader vide
ou de grande taille. Il est inscrit au fast gate hôte.
**Résultat d'exécution CI/native non confirmé** au moment de cette
mise à jour. Le cas reproduit est une possibilité de synchronisation
sous verrou ; les anciennes traces de FC27 ne permettent pas
d'attribuer un pic précis à ce chemin. **F01 reste ouvert.**


### F01 — ajustement final du seuil initial, source/en-tête natif vérifiés

La prévalidation initiale `PreflightGuestDraw` anticipait une réservation
fixe de **1 024 entrées**, même lorsqu'un pipeline graphique/compute
utilisait quelques descripteurs. Elle reçoit désormais
`pipeline->DescriptorEntryReservation()` et applique le seuil exact
`used + reserve >= frame_payload_size` de l'`Acquire` réel.
La valeur `0x400` reste disponible par défaut pour les autres appels
non revus. Les méthodes initiale et de resélection sont présentes
**à l'identique** dans `tools/prepare-vulkan-port.py` et dans
l'en-tête maintenu sélectionné
`vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h`.
Les deux sites initiaux et six sites de resélection sont présents
dans le rasterizer maintenu.

`tools/check-ps5-graphics-pipeline-aware-preflight-host.py`
a été adapté au paramètre supplémentaire ;
`tools/check-ps5-exact-descriptor-preflight-host.py` exige maintenant
la parité des deux méthodes dans l'en-tête et le générateur et vérifie
le précontrôle initial à la frontière de la file.

Une reproduction locale séparée du calcul a réussi sous GCC et
Clang, `-O0`/`-O2`, UBSan : **110 couples** remplissage/réservation
pour chaque configuration, contre-exemple historique inclus.
Ce n'est pas la suite source-extraite du dépôt, dont l'exécution
reste à confirmer. **Aucun gain en FPS n'est quantifié**, et les
attentes F01 autres que celles-ci restent ouvertes. La compilation
PS5 complète doit valider la cohérence des sources et du build
avant F07.


## 23 octobre — reprise F01–F06 sans nouveau test console

La dernière revue initiale recense **0 chemin moteur à parcourir de nouveau** ;
ce chiffre n'est toujours ni un compte de correctifs restant à écrire ni
une preuve d'optimisation FPS. Les **62 sources du lanceur** sont traitées
dans leur propre chantier. Les **six sorties F01–F06 restent ouvertes** tant
que les invariants complets du tableau initial ne sont pas démontrés.

Pour rendre les reprises diagnostiquables sans attendre le succès de tous les
contrôles génériques, `tools/check-fc27-six-gates-host.py` exécute maintenant
**douze témoins C++ source-extraits** indépendamment :

- **F01 :** réservation du payload avant mutex buffer/texture et déduplication
  de samplers ;
- **F02 :** invalidations JIT réentrantes A32/A64 et bornes du code JIT ;
- **F03 :** remappage TIC/TSC sans entrée et réutilisation correcte des couches
  HardwareComposer ;
- **F04 :** coordonnées scissor extrêmes et plages BufferCache multipages ;
- **F05 :** gestion des affichages SurfaceFlinger et réveil de producteur après
  détachement de buffer ;
- **F06 :** persistance de la conversion physique→guest au lancement et
  cadence HID du runtime.

Ce point de contrôle est exécuté dans la prévalidation hôte avec
`if: always()` : un échec indépendant de cartographie ou de reproduction de
source ne masque plus le résultat de chaque critère. **Il reste bloquant en
cas d'échec de l'un des douze témoins** et inscrit le résultat détaillé dans
le résumé du workflow. Un `HOST_SUBPATH_PASS` est un progrès de preuve
partielle, **pas une clôture de F01–F06**, ni un résultat PS5.

Le contrôle strict d'empreinte U13 a été remis à jour **après inspection des
six modifications** de `metadata_bridge.cpp` liées à la classification des
conteneurs. Le chemin CPU/GPU/JIT n'est pas modifié par cette revue et son
empreinte restera verrouillée. En parallèle, le fast gate de reproduction
Vulkan a signalé un écart entre le générateur et quatre sources maintenues
(`vk_graphics_pipeline.h`, `vk_graphics_pipeline_cost.cpp`,
`texture_cache.h`, `vulkan_rasterizer.cpp`) : **ne pas certifier la
parité/native de F01, F03 ou F04 sans résolution de cet écart**. Ne jamais
modifier l'oracle pour simplement ignorer la différence.

Le profil de livraison conserve le JIT normal, les verrous nécessaires, les
fences et les invalidations GPU. Aucun changement automatique de fréquence,
affinité, résolution, taille des caches ou file Vulkan. Une seule validation
matérielle finale demeure réservée à F07.


## 23 octobre — intégration des formats et compteur moteur restauré

Après la prise en charge des formats NSZ/XCZ, des modules directs et de
l'ExeFS, le registre d'audit historique à 493 fichiers n'était plus à jour.
Une comparaison exacte avec les objets de l'arbre Git de la branche a révélé
**11 nouvelles sources de code** : dix sont des unités de lecture, décompression
ou routage de formats ; la dernière est
`headless/prosperoeden/pe/ui/case_media_selection.hpp`, suivie dans le
périmètre UI. Aucun de ces onze fichiers ne constitue en lui-même un
correctif de saccades, de HUD ou de commandes FC27.

Au commit `540f4bb`, le nouveau registre distingue :

| Compteur de la première revue de code | Valeur |
| --- | ---: |
| Fichiers C/C++/headers détenus par Encore | **504** |
| Sources traitées, revues ou intégrées avec référence | **441** |
| Dont nouveaux propriétaires de formats, hors optimisations FPS | **10** |
| Première revue moteur restant à traiter | **0** |
| Première revue UI/launcher restant à traiter séparément | **63** |
| Nombre de correctifs moteur réellement encore nécessaires | **inconnu** |
| Critères FC27 F01–F06 techniquement clos | **0/6** |

La source et le test `tools/check-eden-optimization-coverage.py`
contrôlent désormais les dix nouveaux chemins par **empreinte Git exacte**,
preuve de sélection, référence à la prévalidation et distinction
native/hôte/en-tête. Voir
[la revue indépendante des formats](EDEN_FORMAT_SOURCE_REVIEW_2026-10-23.md).
Les **12 témoins hôte F01–F06** précédemment exécutés ont tous réussi,
mais la suite CI complète du dernier SHA demeure une qualification
indépendante. La reproduction Vulkan générateur/sources est passée dans
le fast gate de `d612c8c` ; des témoins de contrôle de préflight
compute ont été réalignés ensuite, sans modifier les fences ni désactiver
les verrous.

**Ne pas interpréter « 0 source moteur à revoir » comme « F01–F06
terminés ».** Les six critères restent à prouver au niveau bout-en-bout ;
F07 reste la seule validation physique sur PS5.


## 23 octobre — demande de qualification native du lot F01–F06

Le sous-contrôle source F01–F06 a donné **12/12 témoins hôte réussis**
sur la dernière base inspectée, et le registre exact a passé
`EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS` à 504/441.
La prévalidation complète et le fast gate demeurent des contrôles
**indépendants**. L'empreinte de la source A64 standard a été
réexaminée dans `tools/ci/check-final-engine-owner-contracts.py`
après l'introduction de deux purges via `ClearCache()` sous mutex.

La demande de compilation `[full-build]` est volontaire et porte
exclusivement sur la branche unique `dev/ps5-sparse-jit`.
Elle ne demande **aucun test physique de FC27 ni aucun essai sur PS5**.
Un artefact compilé prouverait la sélection du code native pour ce SHA,
**pas** une suppression des gels, du lag ou de la corruption visuelle.
F01–F06 restent ouverts et F07 demeure entièrement séparé.


## 23 octobre — reprise de la compilation native après validation des prérequis

Le [premier build natif déclenché au SHA `98291a0`](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40027498597)
a exécuté les contrôles C++ JIT, paquets, formats NCZ, SDK et validation de
l'interface, mais a **échoué avant de lancer la compilation native**.
Trois contrats de source incompatibles avec le nouveau code ont été trouvés :

1. `tools/check-nlib-ui-recovery.py` cherchait l'ancienne fonction
   `fit_fallback_art` et interdisait `cover_crop`, alors que le front
   reconstruit est désormais imprimé en plein format dans les deux vues.
   Ce contrôle impose désormais le plein format et le même compositeur
   Library/launcher.
2. `tools/check-ps5-vulkan-cache-phases.py` attendait la déclaration
   `PreflightDescriptorScratch() const`. Le passage en méthode mutable
   est intentionnel : elle préalloue les vecteurs avant les deux mutex.
   Le test vérifie la signature courante sans relâcher l'invariant
   préallocation-avant-verrou.
3. La politique de noms d'étapes CI refusait la mention d'une bibliothèque
   tierce dans un workflow de capture du README. Le libellé est neutralisé
   et la prévalidation se déclenche désormais lorsque ce workflow change.

**Nouvelle compilation demandée volontairement** avec `[full-build]` afin
de vérifier l'intégration PS5 de tous ces changements. Elle ne remplace pas
F07 : aucun test console ni promesse de gain de FPS ne découle de la
réussite éventuelle du build. L'ajout du témoin F03 de vues NULL transitoires
sous deux slots TIC protège la sélection texture quand le GPU cache vient
à peine de recréer une vue valide.


## 23 octobre — correctifs de prévalidation et reprise du build PS5

La qualification native lancée sur `10991c3` a été bloquée **avant** le
compilateur PS5 par quatre assertions restées sur des contrats abandonnés :
la silhouette de jaquette à largeur variable, le test XCI-only de glyphes,
`PreflightLargeGuestDraw` après l'introduction du contrôle exact, et
la vérification de l'attente du ring descripteur. Les vérifications ont été
réalignées sur les **sources actives** sans suppression des verrous, des
synchronisations de textures ou du repli de taille historique.

La prévalidation a également identifié un défaut réel de reproductibilité
M07 : la variante DEV CPU→GPU différée n'avait pas hérité des protections
de clipping GPU du rasterizer natif. Elle est maintenant reconstruite à
partir de celui-ci en ne conservant que ses deux modifications de pont.
Cette variante **reste désactivée** sur les builds normaux.

Enfin, `eden-ps5-feedback-loop-no-depth-fastpath.patch` (modifié le
23 octobre) et l'unité maintenue `eden-backports/src/video_core/texture_cache/texture_cache.h`
(dernière matérialisation datant d'octobre 11) divergeaient : le patch
ajoutait le cas `views.empty()`, absent de la source possédée.
Le bloc est maintenant intégré, et `manifest.json` verrouille ses
nouvelles empreintes **SHA-256 source + patch**, sans désactiver le
rejeu octet à octet de `install-vendored-eden-backports.py --replay`.

**Build [full-build] demandé à nouveau** avec cette base corrigée. La
preuve attendue est la compilation/link native de ce SHA et la sélection
des sources actualisées, pas un nouveau test de FC27 sur matériel.
**F01–F06 demeurent ouverts (0/6)** et F07 demeure séparé.

## 24 octobre 2026 — F01 : masques uniformes identiques sous verrou

Le chemin natif `BufferCache::SetUniformBuffersState`, appelé par
`GraphicsPipeline::ConfigureImpl` pendant la possession conjointe des
mutex buffer/texture, réécrivait `enabled_uniform_buffer_masks` même
lorsqu'il était identique à la configuration précédente.

Le commit `04d7821` évite cette affectation lors des rebinding sans
changement, **sans** supprimer la mise à jour inconditionnelle du pointeur
`uniform_buffer_sizes` et **sans** toucher aux invalidations lors d'une
transition effective. La reconstruction de la source native depuis le
backport et le rejeu du code original sont vérifiés respectivement par
`check-vendor-consolidation-debt.py` et
`check-native-uniform-mask-rebind-host.py`.

**Preuve attendue du test source-extrait :** quatre appels, deux changements
de masques, donc quatre affectations dans la source d'origine et deux dans
la source maintenue, en profils avec et sans cache uniforme persistant et
sous O0/O2/UBSan. Cette réduction de deux affectations ne mesure ni le
temps de verrou, ni les FPS, ni les freezes sur la console.

L'analyseur `analyze-fc27-stutter.py` expose aussi la part
`pipeline_configure / pair_held` *uniquement* pour des fenêtres dont les
échantillons GPU sont appariés. Les relevés incomplets restent inconnus.
**F01 demeure ouvert** : aucun gain de contention FC27 après ce changement
n'a été constaté. Cette révision demande seulement la vérification CI et
la compilation native, pas de test utilisateur sur PS5.
