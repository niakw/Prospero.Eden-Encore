# Eden Encore — reste à faire pour FC27 (critères de sortie)

**État établi le 22 octobre 2026.** Branche unique :
`dev/ps5-sparse-jit`. Base native vérifiée :
[`69fdf79`](https://github.com/niakw/Prospero.Eden-Encore/commit/69fdf7912de4cb0264d95bcbfcf61ad49d20d95c).

> **Indicateur principal : 0 / 7 critères de résultat démontrés, 7 ouverts.**
> Cela **ne signifie pas sept fichiers à modifier**, ni sept défauts indépendants :
> une même correction peut fermer plusieurs critères, ou aucun si elle ne
> change pas le résultat sur console. Aucun critère n'est fermé parce que
> son code compile. Les `430/492` sources examinées et les `409`
> contrats SOURCE/OPEN sont des indicateurs historiques d'inventaire et de
> qualification, **pas des compteurs d'optimisations restantes**.

## Socle CI — terminé pour le SHA de référence

| Preuve | État | Exécution |
| --- | --- | --- |
| Fast gate et régressions hôte C++ | **VERT** | [39775426169](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426169) |
| Prévalidation de toutes les sources | **VERT** | [39775425826](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775425826) |
| Build/package natif PS5 | **VERT** | [39775426085](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426085) |
| Analyse sécurité CodeQL | **VERT** | [39775426078](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426078) |
| **Résultat FC27 sur matériel pour ce SHA** | **NON MESURÉ** | Aucun test console du SHA de référence |

Cette base inclut déjà les gardes TIC/TSC, les limites des buffers
indirects / SSBO / TBO / CBUF, les liaisons compute périmées, la
mise à jour des plages d'indices, le coût des samplers et le
correctif du registre AMD. Leur réussite en CI n'est pas une
qualification de performance, de HUD ou de fidélité des textures.

## Tableau des sept critères de sortie

Les états ont un sens strict : **OUVERT** = symptôme ou risque encore non
clos sur console ; **INVESTIGATION** = chemins exacts identifiés mais pas de
gain prouvé ; **À QUALIFIER** = une correction existe, sans preuve matérielle
du résultat. Tous les critères restent ouverts jusqu'à leur preuve de sortie.

| ID | Priorité | Résultat attendu | Situation vérifiée | Prochaine intervention ciblée | Clôture requise |
| --- | --- | --- | --- | --- | --- |
| **F01** | P0 | **Plus de saccades CPU/GPU liées aux buffers** | **INVESTIGATION.** 1 005 680 attentes du mutex buffers, 9,311 s cumulées dans la trace détaillée. Réductions partielles déjà intégrées : pages jamais possédées, préallocation des descripteurs, samplers consécutifs. | Isoler les sections réellement longues entre `RasterizerVulkan::OnCPUWrite`, `PrepareDraw` et `GraphicsPipeline::ConfigureImpl`. Réduire le travail immuable sous le verrou sans perdre une invalidation. | Même scène, même binaire : baisse des attentes longues et des images >50/100 ms, **sans** régression de contenu HUD/texture. |
| **F02** | P0 | **Supprimer les très gros pics de compilation JIT** | **INVESTIGATION.** Les traces comportent des images de plusieurs centaines de ms à plus d'une seconde et de fortes compilations JIT cumulées. Le sparse JIT expérimental est OFF en release ; l'ancienne session sparse utilisait un **autre SHA**. | Isoler par cœur les compilations froides/répétées, invalidations de blocs et limites du cache ; privilégier une correction ciblée plutôt que monter les tailles et les threads au hasard. | Absence de gros pics JIT récurrents en match, temps de frame meilleur à scène comparable, sans faute mémoire/JIT. |
| **F03** | P0 | **HUD présent et actualisé en continu** | **À QUALIFIER.** Gardes TIC/TSC et récupération de mappings manquants intégrés, mais la dernière console montrait encore des éléments de HUD figés/disparus. Zéro `EDEN_GPU_DRAW_DROP` observé dans l'ancienne trace ne prouve pas la fraîcheur des pixels. | Tracer le parcours TIC/TSC → image view → descripteur graphique → barrières/feedback → présentation, avec la durée de validité et les écritures CPU/GPU. | HUD complet, non figé, continuellement mis à jour dans jeu, menus et transitions. |
| **F04** | P0 | **Maillots, terrain et autres textures sans trous ni corruption** | **À QUALIFIER.** Limites DMA, vertex/index, slots SSBO/TBO et mappings textures corrigées côté source, sans preuve d'une restitution correcte de FC27. `memory_short=0` dans l'ancien relevé. | Vérifier alias/remap, invalidations de textures, vues périmées et échelles/régions d'upload ; distinguer géométrie absente et texture invalide. | Maillots, terrain et transitions entièrement rendus dans plusieurs séquences de match. |
| **F05** | P1 | **Image affichée = simulation du jeu qui avance** | **INVESTIGATION.** ~30 FPS Vulkan peuvent masquer une scène bloquée. L'ancien gel de pause/fin de match avait GPU et compositor actifs. Le service `IHOSBinderDriver` concentre des attentes IPC mais elles ne sont pas toutes des coûts évitables. | Corréler progression du jeu/HLE, transactions `TransactParcelAuto`, dequeue/queue de buffers, fences et horodatages de présentation. Ne pas forcer la cadence ni sauter un fence. | Aucune répétition prolongée d'une scène alors que les presents continuent ; transitions menu/mi-temps/fin de match vivantes. |
| **F06** | P1 | **Match complet : contrôles cohérents, pas de gel ni crash** | **À QUALIFIER.** La session console récente ne semblait plus planter/geler mais de forts lags persistaient ; les anciens gels pause/mi-temps/fin de match et paramètres de commandes non appliqués n'ont pas été clos sur la révision actuelle. | Vérifier le passage DualSense → HID/Npad → actions du jeu, les états de commande personnalisés et la progression HLE des menus/écrans de fin. Ne pas forcer de mapping global pendant le match. | Match complet + menus pause/mi-temps/fin de match + commandes personnalisées corrects, sans fermeture forcée. |
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
4. **F07** seulement sur une version avec diagnostics, tests hôte et
   paquet natif verts. Un passage sur console sera inévitable pour
   établir le résultat réel ; il ne faut pas le demander à chaque micro-patch.

Après chaque lot : noter dans ce tableau **le ou les IDs affectés**,
le commit, le contrôle CI et la preuve fonctionnelle, ou maintenir
explicitement **OUVERT**. Une baisse du nombre de sources restantes
n'est plus une métrique de progression ici.

**Sources de mesures :**
[FC27_GPU_SOURCE_TARGETS_2026-10-21.md](FC27_GPU_SOURCE_TARGETS_2026-10-21.md),
[FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md](FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md),
[FC27_PAUSE_FREEZE_R435.md](FC27_PAUSE_FREEZE_R435.md),
[FC27_TIC_TSC_MISSING_CHANNEL_MAPPING_2026-10-22.md](FC27_TIC_TSC_MISSING_CHANNEL_MAPPING_2026-10-22.md),
[EDEN_SINGLE_FINAL_RUNTIME_DECISIONS_2026-10-21.md](EDEN_SINGLE_FINAL_RUNTIME_DECISIONS_2026-10-21.md).

**Périmètre séparé :** travaux launcher/UI, couvertures 3D, avatar, jaquettes,
glyphes et traductions. Ne pas les mélanger à la mesure de stabilité du moteur.
