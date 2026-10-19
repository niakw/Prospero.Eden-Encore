# Eden Encore — FC27: triage CPU/JIT, caches, GPU et gel visuel

Date : 19 octobre 2026 · Branche : `dev/ps5-sparse-jit`

## État des preuves

La cartographie physique des sources permet de commencer les revues
fonctionnelles. Elle **n'est pas** une preuve que les 476 contrats
dépendance/fonction ont tous été exécutés et validés sur PS5.
Ne jamais confondre succès du préflight hôte, compilation, stabilité console
et fluidité perçue. Le launcher et ses thèmes restent hors périmètre.

La capture historisée `tools/fixtures/fc27-2efd8b3c-stutter-windows.json`
contient **415 fenêtres de télémétrie de cinq secondes**, source
`2efd8b3c96608667a2b22f1751eed1a475091cce`. Ce n'est **pas**
un benchmark des correctifs d'octobre 2026. Elle n'autorise pas de
comparaison de FPS « avant/après » avec le HEAD courant.

## Résultats reproductibles et séparation des domaines

Exécuter `python3 -B tools/check-fc27-stutter-regimes.py --self-test --json`
pour reproduire les calculs et invariants. Le champ
`bottleneck_signals` explicite les populations, sans inférence causale.

| Signal de la capture | Valeur | Interprétation acceptable |
|---|---:|---|
| Présentations de plus de 50 ms | 858 | Vraies irrégularités visibles possibles |
| Présentations de plus de 500 ms | 10 | Queues extrêmes à réduire sans casser la correction GPU |
| Plus longue présentation | 1 288,129 ms | Incident individuel, pas le framerate moyen |
| Fenêtres à ≥29,9 FPS | 341/415 | Une bonne moyenne n'atteste pas de la progression du jeu |
| Intervalles >50 ms dans ces fenêtres | 5 | Le gel d'image peut exister malgré l'affichage régulier |
| Fenêtres à moins de 25 FPS | 28/415 | Contiennent 668 des 858 intervalles >50 ms |
| Fenêtres JIT ≥500 ms cumulées | 25/415 | Compilation coûteuse, souvent au démarrage |
| Fenêtres cache-wait ≥100 ms cumulées | 17/415 | Contention distincte, surtout en jeu |
| Longues fenêtres ≥500 ms avec JIT ≥500 ms | 8/10 | Association forte, causalité par frame NON prouvée |
| Longues fenêtres ≥500 ms sans JIT ≥500 ms | 2/10 | Le JIT ne peut pas expliquer seul toute la queue |
| Fenêtres de saturation de file GPU mesurée | 0/415 | Aucune raison de gonfler la file pour **cette** capture |

Par phase : démarrage 42 fenêtres et 109 `late50` ;
gameplay 180 fenêtres et 679 `late50` ;
fin de session 193 fenêtres et 70 `late50`.
Les trois phases regroupent **la même capture**, pas trois benchmarks.
L'âge ou la fraîcheur des pixels n'est pas mesuré dans ce fichier.

## Ordre d'audit source recommandé

1. **P0 — JIT A32/A64 et temps de compilation initiale** :
   reconstituer le chemin réellement sélectionné pour les variantes
   native/release/DEV, distinguer re-traduction, invalidation, création
   de blocs et compilation simultanée. Le sélecteur source G11/X06
   est déjà migré et son tableau de variantes possède un témoin CMake ;
   restent à qualifier les invalidations effectives et les attentes
   JIT en exécution. Le compteur de
   compilation cumule plusieurs cœurs ; un pic ne prouve pas que le
   compositeur attendait un bloc donné. Priorité : trouver pourquoi
   8 des 10 grandes interruptions partagent de fortes compilations.
2. **P0 — Véritable progression du jeu durant le gel** :
   départager nouveau rendu du guest, réutilisation de buffer, callback
   de présentation et état des threads/HLE. La session R384 présentait
   encore des milliers de draws pendant un gel rapporté ; ni queue GPU
   ni FPS 30 ne prouvent que la scène progresse.
3. **P1 — Contention cache tampon/texture en gameplay** :
   identifier le détenteur du verrou et **sa durée de possession**,
   pas seulement le temps d'attente cumulé d'autres threads. Tracer
   les dépendances aux barrières, dirty invalidations et fences avant
   toute modification de portée d'un mutex.
4. **P1 — Intégrité HUD / textures / aliasing et copy sources** :
   tester les invalidations de descripteurs, frontières de durée de vie
   et ordre DMA → cache → draw → present. Préserver la correction du
   Fermi2D maintenu (#55/#56), dont l'élargissement de l'offset
   est un correctif sécurité et **pas un gain de FPS mesuré**.
5. **P2 — Affinité, capacité des workers, cache et mémoire** :
   garder l'affinité système comme témoin de référence, sans
   supposer la topologie SMT à partir d'identifiants logiques.
   Ne pas augmenter d'office les files, caches ou le JIT, ne pas
   libérer de mémoire sans propriétaires prouvés.

## Conditions avant modification des chemins chauds

- Associer une anomalie reproductible à la **fonction active** et à son
  graphe d'appel, puis prouver la sélection du fichier dans la
  compilation native (pas simplement sa présence sous `encore-active`).
- Ajouter un témoin hôte C++ du comportement précédent et du
  comportement corrigé, y compris les cas limites, les erreurs,
  le shutdown et les invariants d'ordre GPU/HLE/JIT.
- Garder les options expérimentales OFF et ne pas désactiver un mutex,
  un flush, un synchroniseur invité, une barrière ou un drain de GPU
  sur une simple corrélation.
- Prévalidation complète, analyse C/C++ et build PS5 identifié par SHA.
  Ensuite seulement comparer sur console **même scène/même réglages**
  p50/p95/p99 en frametime, incidents >50/>100/>500 ms,
  entrée-vers-image, HUD, mémoire physique et fermeture du jeu.

**Aucun gain FPS, réparation de freeze ou suppression de corruption
graphique n'est revendiqué par ce relevé.** Son utilité est de
prioriser les changements les moins spéculatifs et de prévenir
les « optimisations » qui masqueraient la véritable cause.


## Premier correctif moteur candidat : écriture CPU sans texture enregistrée

**Changement de code maintenu** :
`vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`,
`RasterizerVulkan::OnCPUWrite`.

La voie CPU-write native avait déjà une preuve monotone des pages
tampon jamais enregistrées, mais prenait systématiquement le mutex du
cache texture, même si la plage n'avait jamais appartenu à une image.
`ImagePages::NeverHeld(addr,size)` existait déjà pour la lecture
`GetFlushArea`. `TextureCache::RegisterImage` publie
`ImagePages::Mark` **avant** de remplir `slot_map_views`, y compris
pour les images clairsemées. `TextureCache::WriteMemory` ne visite que
les images actuellement enregistrées dans ce mapping.

`OnCPUWrite` évite désormais le mutex et la recherche texture pour
une écriture jamais vue dans une image, bornée à 256 KiB et dans l'espace
suivi. Dès qu'une page a été enregistrée, que la plage est inconnue,
hors bornes ou trop grande, le chemin verrouillé original est utilisé.
Les invalidations de shaders restent **toujours exécutées** lorsque
le buffer cache ne retourne pas la condition de sortie historique.
Aucun changement aux fences, barrières GPU, identités de textures,
allocations, paramètres du jeu ou cadence de présentation.

Tests : `check-ps5-image-pages-r433.py` valide l'ordre de publication,
les limites et la monotonie du témoin ; le nouveau
`check-ps5-guest-texture-write-elision-host.py` compile le corps C++
**extrait de la véritable méthode**, sous ASan/UBSan, et compare les
effets sur les caches tampon/texture/shader pour petites pages inconnues,
pages enregistrées, plages trop grandes et sortie anticipée.

Cette optimisation élimine une acquisition de mutex sur les écritures
dont l'absence de texture est prouvée. Un **gain mesuré de frametime,
FPS ou correction du freeze n'est PAS encore démontré sur console**.
Comparer le même jeu et le même profil avec un package identifié,
sans attribuer à ce seul changement un éventuel résultat mélangé.
