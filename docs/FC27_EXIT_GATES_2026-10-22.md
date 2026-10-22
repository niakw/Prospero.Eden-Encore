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
