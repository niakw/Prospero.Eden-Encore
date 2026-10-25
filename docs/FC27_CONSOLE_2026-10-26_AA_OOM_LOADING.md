# Eden Encore — observations FC 27, crash GPU, loading et anti-aliasing (26 octobre 2026)

**Branche de production :** `dev/ps5-sparse-jit`. **Build testé :** `cd4857c8` (Oct 25 2026 21:06:16). Les modifications source postérieures n'étaient **pas encore** dans le paquet que l'utilisateur a testé. La branche `feat/graphics-network-achievements` est en pause.

## Données source de l'utilisateur

- `boot-trace.sandbox-prev(10).txt` et `boot-trace(20261025-232515).txt` : la demande de privilèges/accès aux fichiers réussit (`status=0`). Plusieurs jeux sont lancés depuis le même processus, puis l'interface rouverte.
- `stderr(20261025-232522).log` et `heap(20261025-232521).log` : sept lancements successifs, six avec fenêtres `EDEN_VULKAN_FRAME`. L'ordre des profils ci-dessous provient des entrées `launch: Resolution` de `stderr` et du nombre de sessions de `heap`.
- `crash-20261026-000340.txt` et `crash-20261026-000340-stderr.log` : arrêt le 26 octobre 2026 à 00:03:40, `VK_ERROR_OUT_OF_DEVICE_MEMORY`, au premier échec `CreateImage` (`vulkan_memory_allocator.cpp:224`, `VkResult=-2`). Paramètres déclarés par le rapport au crash : **4× interne, AMD FSR, sortie 2160p, 60 Hz, FC 27**. Plus gros bloc libre déclaré : **64 MiB** ; ne pas le confondre avec le budget total exact de VRAM. `watchdog suspected stalls=0`, `invalid guest-memory accesses=0`. Rien ne prouve que le bug HUD déclenche ce crash.
- `crash-20261026-000340-heap.log` : log de plusieurs sessions dont 1440p et 2160p ; les zéros de certaines colonnes de compteurs ne prouvent pas qu'il n'y a pas de travail si l'instrumentation correspondante est désactivée.
- `network-accepted(20261025-232521).log` : journal réseau cumulatif, des lignes remontent au 13 octobre ; aucune causalité de crash GPU démontrée.

## Comparaison non contrôlée, pas un benchmark identique

| Séance | Interne / filtre / AA | Fenêtres ~5s | FPS médian par fenêtre | FPS min par fenêtre | Pire intervalle | Frames > 100ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,5× / FSR / SMAA, sortie 2160p | 30 | 30,00 | 19,399 | 505,688 ms | 25 |
| 2 | 1× / Nearest / SMAA, sortie 2160p | 33 | 29,90 | 16,772 | 535,684 ms | 45 |
| 3 | 1× / Bicubic / SMAA, sortie 2160p | 31 | 29,80 | 14,751 | 587,822 ms | 49 |
| 4 | 0,25× / Bilinear / SMAA, sortie 2160p | 2 | 24,04 | 23,921 | 486,747 ms | 9 |
| 5 | 0,75× / Bilinear / SMAA, sortie 2160p | 23 | 29,10 | 11,683 | 578,107 ms | 43 |
| 6 | 2× / Bilinear / SMAA, sortie 2160p | 43 | 29,79 | 16,394 | 802,219 ms | 63 |
| 7 | 2× / Bilinear / FXAA, sortie 2160p | 0 | — | — | — | — |

Les jeux/scènes, la durée, l'état du cache et les changements de qualité ont pu varier. La conclusion défendable est limitée : **diminuer énormément la résolution n'élimine pas les saccades** ; le plateau proche de 30 FPS n'exclut pas des images ponctuellement très longues ; le test 0,25× est trop bref pour une moyenne robuste. Les attentes de cache à zéro dans le jeu de fichiers `heap(20261025-232521)` sont une **mesure absente / non activée**, pas une absence démontrée de contention.

## Corrections séparées du moteur FC 27

1. **Jaquettes Switch reconstituées** : correction des UV du **logo rouge frontal fixe** dans `pe/ui/library.cpp`, en miroir de celle du footer arrière. Les sources réelles `box-front/box-back` ne sont pas modifiées. Le FBO du 3D effectue toujours son retournement final ; il ne faut pas ajouter une nouvelle inversion sur la face entière.
2. **Double écran de chargement** : l'animation de boîte du launcher est l'unique chargement *graphique identifiable*. L'ancien shader GLSL de la page violette est **conservé à l'identique** car ses octets et le SPIR-V précompilé sont des artefacts reproductibles épinglés. Le code **effectivement compilé** dans `vendor/encore-active/eden-vulkan/vulkan_window_adapt_pass.cpp` bloque désormais l'appel de dessin de cet overlay pendant le chargement, mais continue de présenter un fond uniforme (0.024,0.035,0.039). Le fallback OpenGL `graphics.cpp` utilise ce même fond. **Conservé :** warmup/present Vulkan, présentation GL, progression GPU et point de transition à la première image invitée. Il existe toujours un intervalle sombre d'attente entre launcher et première image du jeu ; aucun transfert direct d'une image OpenGL vers Vulkan n'est revendiqué. Le test `tools/check-vendored-vulkan-fork.py` reproduit le correctif dans le générateur de référence **avec cinq ancres exactes**, puis compare les sources produites octet par octet ; pas de dérogation générale.
3. Régression de la priorité de chargement des illustrations front et de l'orientation du footer arrière : déjà corrigée sur la branche de production avant ces tests utilisateur. Le build testé `cd4857c8` **ne les contient pas**.

## Anti-aliasing : audit et décision

- `headless/main.cpp` raccorde seulement `None`, `FXAA`, `SMAA` à `Settings::values.anti_aliasing`.
- `vendor/encore-active/eden-vulkan/vulkan_present_layer.cpp` exécute vraiment `FXAA::Draw` ou `SMAA::Draw` sur les couches. Ce sont des méthodes spatiales ; elles ne résolvent pas les bugs de shaders/texte manquant ni le scintillement temporel de tous les titres.
- Le `AMD FSR` actuel est un filtre d'upscaling spatial, pas FSR 3 / Native AA. Le prototype `extras/graphics/framegen_capabilities.h` sur la branche expérimentale **ne fournit pas** de runtime AA.
- **Piste qualité** : FSR 3.1 Native AA ou TAA équivalent nécessiterait l'accès correct aux images invitées, à la profondeur, à l'historique, aux vecteurs de mouvement et aux masques réactifs/composites. Pour une couche HUD absente ou retardée, un traitement temporel naïf pourrait *aggraver* la rémanence. Ne pas exposer une option Native AA sans vrai chemin de données et preuve graphique.
- L'expérience FC 27 **4×** se termine par un épuisement mémoire ; ne pas proposer une résolution brute 3×/4× comme remplacement universel de l'AA. Ne pas désactiver les barrières/invalidations mémoire pour compenser.

## Qualification et suite technique

- **F01–F06** : 6/6 contrats de prévalidation **hôte** antérieurs au test utilisateur ; ce chiffre ne représente PAS la jouabilité.
- **F07 : ouvert** pour HUD/texte, input-to-image, pics de latence, stabilité OOM et comparaison du cache.
- Mode de référence utilisateur : **cache vidé, logs OFF, résolution 1×, sortie 1440p**. Les scénarios de mesure avec logs et configs multiples ne doivent pas écraser ce point de comparaison.
- Pour l'out-of-memory : auditer les allocations images par tailles/format et la fragmentation, la politique de rétention du cache GPU, la destruction inter-session, et un éventuel repli gracieux en cas d'allocation refusée. Le rapport seul ne prouve ni une fuite inter-session ni un bug de budget VRAM.
- Les corrections ci-dessus requièrent le fast gate, le rendu launcher et la compilation native PS5 **sur le même SHA** avant de solliciter un nouveau test console.
