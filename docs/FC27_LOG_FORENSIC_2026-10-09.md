# Eden Encore — FC27 PS5 : constats vérifiés sur logs existants (9 octobre 2026)

## Périmètre de preuve

Analyse **hors console, sans nouveau build** de journaux précédemment fournis par l'utilisateur, datés du 8 octobre 2026. Les fichiers bruts restent privés ; le dépôt ne conserve ici que les résultats agrégés. Aucun de ces journaux ne provient d'une exécution JIT sparse activée.

**Attention aux doublons :** les contenus de `stderr(6).log` et `stderr(7).log` sont **strictement identiques en texte** (36149 caractères, 361 lignes dans l'export disponible). Ce sont donc **une seule et même preuve**, PAS deux tests répétés et indépendants. Ne jamais les compter deux fois dans les statistiques.

## FC27, build dense antérieur, crash vers 261 secondes

Source : journal matériel `crash-20261008-234818-heap.log`, 45 lignes `EDEN_VULKAN_FRAME` (agrégées par fenêtres de ~5 secondes).

| Indicateur | Valeur |
| --- | ---: |
| Fenêtres comptées | 45 |
| Frames comptées | 6 534 |
| Temps cumulé des fenêtres | 225,778088 s |
| FPS pondérés, frames / temps | 28,940 |
| Fenêtre ~5s minimale | 22,562 FPS |
| Image maximale signalée | 481,612 ms |
| `late38` cumulé (compteur natif) | 309 |
| `late50` cumulé (compteur natif) | 102 |
| `late100` cumulé (compteur natif) | 26 |
| `late200` cumulé (compteur natif) | 7 |
| `late500` cumulé (compteur natif) | 0 |

**Les groupes `lateN` sont des seuils cumulatifs qui se chevauchent : ne pas les additionner.** Les journaux fournissent les totaux par fenêtre, pas toutes les valeurs de frame time ; il n'est donc pas possible d'en calculer les véritables percentiles p95/p99 image par image. Les nombreux intervalles proches de 30 FPS ne masquent pas les gros retards individuels.

Le même build annonçait `EDEN_PS5_JIT_POLICY ... free_mib=11826 admission_budget_mib=4376 ... sparse=0`. Environ 4,3 Gio de budget d'arènes denses engagées au démarrage, contre un dernier bloc de mémoire directe contiguë de seulement 38 Mio au moment d'une requête échouée de **440 Mio**. Le rapport d'arrêt identifie `std::bad_alloc` sur `CPUCore_1`. Cette causalité du budget dense est une **hypothèse très forte**, mais sans symbolisation complète il faut éviter d'attribuer chaque allocation à un propriétaire précis.

## Menus et mapping

Le journal `stderr(6).log` (identique au `stderr(7).log`) contient **12 événements** `EDEN_PAD_CONTEXT` : 7 entrées `mode=gameplay` et 5 retours `mode=ui reason=navigation`. Cela documente une vraie oscillation du contexte de manette dans l'ancienne version. Le correctif source *sticky gameplay* supprime ce chemin de retour fondé sur la seule navigation, mais le comportement entre le match, une popup et un véritable menu reste à qualifier dans le jeu.

Ce même journal présente quatre `slow frame` de l'interface :

| Update | Draw | Present |
| ---: | ---: | ---: |
| 122 ms | 0 ms | 1 ms |
| 175 ms | 0 ms | 1 ms |
| 168 ms | 0 ms | 1 ms |
| 122 ms | 0 ms | 1 ms |

**Orientation diagnostique :** ces hitches mesurés sont dans l'`update` du lanceur, pas dans son `draw/present` pour ces quatre échantillons précis. L'optimisation du décodage Nlib hors UI existait déjà dans le code, et un nouveau garde-fou limite à **24 recherches de requêtes de couverture par frame** pour éviter une file de noms périmés non bornée. Ces changements ne prouvent pas la disparition des ralentissements sur firmware 13.60.

Trois lignes séparées indiquent également `glyphs: In-game button art: Nintendo original (rule=unsupported)`. Il ne s'agit pas d'une régression du mapping DualSense : **aucun atlas PlayStation qualifié pour FC27 n'était installé**.

## Nouvelle instrumentation hors console

`tools/analyze-ps5-logs.py` accepte des journaux locaux, déduplique les contenus par SHA-256 avant de compter les événements, distingue les fenêtres Vulkan, les ralentissements du launcher, les oscillations du mapping, l'admission JIT, les avertissements GPU et l'OOM. Un fixture source `tools/check-ps5-log-analysis.py` est présent mais pas exécuté pendant la consigne d'arrêt des runs.

## Ce qu'il reste réellement à démontrer

1. FC27 dense quarter-pool vs JIT sparse : même scène de match, FW13.60, deux lancements, allocation physique/fragmentation et durées de frame, sans inférer d'amélioration d'un autre build.
2. Mesures réelles du CPU/GPU et de la file Vulkan, plutôt que la chaleur perçue ou le compteur nominal 30 FPS.
3. Validation du nouveau décodage/reclaim des couvertures et de la limite de file de requêtes de 24 par image sur la navigation maintenue.
4. Comportement PlayStation Auto en menu, match, pause, popup et retour réel au menu.
5. PRMT Index et Fermi2D sur firmware, et glyphes graphiques PS5 réellement visibles dans FC27 (et un deuxième jeu).

**État : corrections source enregistrées, zéro preuve matérielle nouvelle. Issues #7 et #8 toujours ouvertes. Aucune branche de livraison/UI approuvée modifiée.**
