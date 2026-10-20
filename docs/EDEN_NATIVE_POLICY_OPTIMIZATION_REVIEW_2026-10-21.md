# Encore — optimisation : revue de 16 composants natifs hors boucle de rendu

**21 octobre 2026 · branche `dev/ps5-sparse-jit` · référence `3d214ca46`.**

## Méthode

Seize fichiers du programme natif ont été **lus directement**, puis
rapprochés d'un contrat `SOURCE` unique et de leur témoin CI exécuté.
Ce lot vise à **éliminer le retraitement des fonctions déjà conçues
hors chemin chaud**, sans prétendre qu'un test hôte vaut mesure PS5.
Le code du lanceur n'est pas modifié.

| Chemin (source examinée) | Contrat | Constat de décision d'optimisation |
| --- | --- | --- |
| `headless/assets_dir.h` | U46 | Cold storage-root selection is computed once per process; no per-frame filesystem probing. |
| `headless/audio_out_init.h` | U47 | Shared sceAudioOutInit is protected by call_once; no repeated device initialization on audio streams. |
| `headless/boot_trace.h` | U34 | Early boot/fatal trace only; not enabled as a per-draw hotpath. |
| `headless/button_mapping.h` | U66 | Static/constexpr translation and bounded uniqueness validation; no additional hotpath allocation identified. |
| `headless/controller_applet.h` | U58 | Controller reconfiguration is event-triggered; does not participate in per-frame GPU stalls. |
| `headless/crash_report.h` | U48 | Crash lifecycle and atomic diagnostic counters are already separated; no performance defect localized. |
| `headless/crash_site.h` | U27 | DEV-only failure dump, not shipping frame handling. |
| `headless/crash_trigger.h` | U49 | Manual development crash trigger, not an automatic production poll. |
| `headless/dev_launch_policy.h` | U50 | Constexpr launch/previous-crash intent, not gameplay processing. |
| `headless/dev_replay_policy.h` | U45 | Constexpr title-qualified developer replay policy; opt-in, not per-frame workload. |
| `headless/error_applet.h` | U60 | Guest error completion is event-based and bounded; relevant to UI correctness not normal GPU performance. |
| `headless/filesystem_probe.h` | U35 | Writable-root capability probe on startup only; no frame-time filesystem check. |
| `headless/glyph_sha256.h` | U68 | Artwork integrity hashing occurs off the frame hotpath; bounded implementation maintained. |
| `headless/glyph_version.h` | U69 | Title display-version extraction is metadata work, not runtime shader input. |
| `headless/title_id_fallback.h` | U40 | Constexpr title identity fallback on filename, not draw command processing. |
| `headless/storage_paths.h` | U76 | Static directory resolution and sandbox fallback; no per-frame path discovery. |

Aucune intervention sur le CPU, le GPU, le shader/JIT ou les files HLE
n'est motivée par ces sources sur la seule base des symptômes FC27.
Le traitement de bugs fonctionnels (glyphes/contrôleur/applet) et la
validation native demeurent indépendants. On n'infère aucune amélioration
FPS ni correction de crash du statut « trié ».

## Deux périmètres séparés, sans altérer le total

La cartographie d'optimisation du fork contient **491 chemins maintenus**.
Le suivi était à **308 traités / 183 encore ouverts** avant cette revue.

Après ces 16 inspections : **324 fichiers traités ou examinés sur 491,
167 fichiers encore ouverts**.

Parmi ces 167 restants, **63 appartiennent au préfixe
`headless/prosperoeden/`**, correspondant au lanceur, au frontend
et à ses composants visuels/plateforme. Ils sont **toujours dans le
registre complet**, mais exclus de la file de travail prioritaire des
optimisations d'émulation en jeu conformément à l'architecture
précédemment fixée. Cela laisse **104 sources non-lanceur
à traiter prioritairement**, sans prouver que chacune demande un patch.

C'est une séparation de priorité, pas une soustraction frauduleuse :
`167 = 104 non-lanceur + 63 lanceur`. Les 63 resteront auditables
lorsque l'optimisation du lanceur sera un chantier séparé.
