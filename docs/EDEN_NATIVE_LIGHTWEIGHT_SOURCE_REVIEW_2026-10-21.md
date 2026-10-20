# Eden Encore — douze sources natives déjà examinées, hors boucle chaude

**21 octobre 2026 · référence** `986d042` · branche `dev/ps5-sparse-jit`.

Inspection directe de douze chemins C/C++ encore dans la file d’optimisation. Trois disposent d’un contrat SOURCE dans le registre moteur ; neuf relèvent de sources auxiliaires, de données générées ou d’exécutables de test séparés. Chaque SHA Git est verrouillé dans le manifeste et recontrôlé par la CI. Aucun de ces douze fichiers n’a nécessité une réécriture spéculative pour le chemin graphique/CPU actuel.

| Fichier | Contrat | Constat du code | Périmètre |
| --- | --- | --- | --- |
| `src/aligned_alloc.c` | Hors registre central | Native startup allocator shim; one posix_memalign call with alignment checks and diagnostic on failure. No per-frame loop; no safe redundant work to eliminate. | `startup-shim` |
| `src/lifecycle.c` | Hors registre central | Title termination/restart and fatal assertion fallbacks; sleeps only after exit is refused. Not a healthy gameplay hot path. | `shutdown-only` |
| `headless/encore_overrides_generated.h` | Hors registre central | Version-pinned constexpr title/video control profiles; one title override and bounded compile-time array lookup, no runtime parsing in this header. | `generated-configuration` |
| `headless/glyph_overrides_generated.h` | Hors registre central | Generated constexpr glyph-art rule array contains zero rules. No input mapping or dynamic asset scanning. | `generated-configuration` |
| `headless/zbic_compression.cpp` | `U17` | Selected native ZBIC implementation: checks input/output spans then dispatches one ZSTD_decompress without extra staging allocation/copy; future codec hotspots need measurements. | `bounded-codec-adapter` |
| `headless/zbic_compression.h` | `U18` | Two ZBIC declarations accepting bounded spans; no executing loop, allocation, or thread synchronization in header. | `interface` |
| `headless/romfs_check.cpp` | Hors registre central | Separate eden-romfs-check executable with isolated allocation-accounting and fiber ownership assertions; not the gameplay app target. | `host-only-test` |
| `headless/scalar_check.cpp` | Hors registre central | Separate eden-scalar-check executable exercising Dynarmic scalar IR folding. Does not execute within emulator frames. | `host-only-test` |
| `headless/shader_cache_check.cpp` | Hors registre central | Separate eden-shader-cache-check executable for damaged shader-cache recovery. Not linked into gameplay target. | `host-only-test` |
| `headless/elevation/elevation.hpp` | Hors registre central | Startup-only elevation request declaration, explicitly single-threaded before worker creation. No per-frame cost. | `startup-interface` |
| `headless/elevation/protocol.hpp` | Hors registre central | Fixed-width privilege-helper wire protocol, validation and bounded socket transfer for startup requests; not GPU/guest scheduling. | `startup-interface` |
| `vendor/encore-active/eden-core/overrides/core/hle/service/sockets/encore_guest_network_policy.h` | `N10` | Immutable guest-offline policy is constexpr true. No mutable airplane-mode consult or per-packet work in this header; DNS implementation remains separate. | `constant-policy` |

Les exécutables de test `eden-romfs-check`, `eden-scalar-check` et `eden-shader-cache-check` possèdent leurs propres cibles CMake : ils ne tournent pas dans la boucle de rendu du jeu. Les headers générés conservent leurs scripts de synchronisation et ne doivent pas être édités à la main. Le ZBIC est un véritable adaptateur natif ; il reste rouvrable si une mesure montre un coût excessif dans `ZSTD_decompress`.

**Avancement du périmètre moteur et infrastructure : 61 → 49 chemins restant à examiner.** Le lanceur demeure suivi séparément : 62 chemins. Le manifeste global atteint **380/491 pris en charge, 111 à examiner (49 hors lanceur + 62 lanceur)**. Ce n’est pas une baisse du nombre de défauts démontrés ni la certification d’une amélioration PS5.

Restent prioritaires sans raccourci documentaire : `src/memory_pages.cpp`, `headless/fastmem_handler.cpp`, `headless/performance.cpp`, `vendor/encore-active/eden-core/src/video_core/engines/maxwell_dma.cpp`, les propriétaires HLE/slab et `vk_pipeline_cache_cost.cpp`.
