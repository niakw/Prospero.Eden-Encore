# Eden Encore — reste à faire pour FC27 (critères de sortie)

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
