# Eden Encore — JIT RX→RW alias et revue de quatre sources

**21 octobre 2026 — base `ac95ee5a4`.** Compteur de travail moteur ; la validation PS5 est indépendante.

## Optimisation du chemin JIT

`headless/jit-allocator.h` : le chemin `Xbyak::Allocator::writableAddress` cherchait une correspondance RX→RW connue en prenant systématiquement le mutex partagé et la table de mappings. Le cache direct-mapped de huit entrées **par thread** évite ce verrou lors de consultations répétées. Chaque insertion et suppression d'allocation publie une nouvelle génération atomique, invalidant toutes les mémorisations positives précédentes. Une adresse RX inconnue conserve le comportement sans alias du code d'origine.

Preuve hôte : `tools/check-native-jit-alias-lookup-host.py` compile l'en-tête réel, avec le contrat d'interface Xbyak minimal et des allocations `memfd` Linux RX/RW réelles sous ASan/UBSan. Les scénarios couvrent l'alternance de deux arènes, les recherches répétées, une autre thread, la libération d'une arène et son éventuelle réutilisation. Pas de preuve de FPS, d'absence de freeze ou d'allocation PS5 native.

## Sources vérifiées sans nouvelle édition

| Fichier | Contrat | Constat source |
| --- | --- | --- |
| `vendor/encore-active/eden-core/src/audio_core/sink/sink_details.cpp` | `A05` | Le choix des backends et des appareils audio est lié à l'initialisation ; tableau constexpr et sélection bornée, pas dans la synthèse PCM par échantillon. Aucune optimisation par frame justifiée. Blob `0704a78a108d385ecb1e40dea1cad802278e5703` |
| `vendor/encore-active/eden-core/src/common/assert.h` | `F18` | En-tête des assertions : chemin de succès inline sans log, chemin exceptionnel déjà noinline pour ne pas grossir l'IR. Ne pas retirer une garde de sûreté pour une optimisation hypothétique. Blob `af026e17732b284e46968b183feecc743d5c9dd7` |
| `vendor/encore-active/eden-core/src/core/loader/deconstructed_rom_directory.cpp` | `F16` | Les lectures NSO/NACP, allocations et correctifs sont faits durant le chargement d'un titre, non lors du rendu de chaque frame. Garder les vérifications des modules et rouvrir si un chargement réel échoue. Blob `b59aff296828492c5e9022ab1eab19244f001c4d` |
| `vendor/encore-active/eden-core/src/core/hle/service/audio/audio_controller.h` | `A11` | Interface de service de contrôle audio et singleton settings lazy avec std::once_flag. Ni mixage audio ni JIT sur ce chemin ; éviter de modifier l'ordre d'initialisation sans repro. Blob `e82e46ebba163b094559cf1e9c857d75dbbd5aa7` |

**Couverture :** 406/491 maintenus pris en charge ; 23 moteur/runtime encore à traiter (28 auparavant) ; 62 UI lanceur séparés ; 85 globalement. Un fichier optimisé (code modifié), quatre sources classées après lecture. Cette classification ne vaut pas validation matérielle.
