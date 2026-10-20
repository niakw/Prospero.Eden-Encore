# Eden Encore — dix propriétaires du runtime natif examinés

**21 octobre 2026 · branche `dev/ps5-sparse-jit`**

Objectif : éliminer rapidement les reprises de code inutiles sur des
sous-systèmes déjà instrumentés ou optimisés. Le statut **examiné**
signifie lecture de la source actuelle et décision explicite ;
il ne signifie ni gain de FPS ni validation PS5.

| Fichier source | Fonction / zone | Constat et décision |
| --- | --- | --- |
| `headless/heap_pages.cpp` | Mémoire directe et heap (`U02`) | Heap C bridge already delegates allocation, reservation and rollback to its single owned backend; initial direct-memory provenance is startup-only, no redundant per-allocation lookup found. |
| `headless/pad.cpp` | Manette et vibration (`U03`) | Controller input and rumble path has release/acquire pending hint before mutex; no hotpath locking on silent polls, preserve paired publication. |
| `headless/audio.cpp` | Audio 48 kHz (`U04`) | Audio worker is stop-aware, output is paced by 256-frame device calls, mutex protects PCM publish; do not disrupt device cadence. |
| `headless/network_audit.c` | Audit réseau local (`U05`) | Network audit disabled path returns after atomic acquire; duplicate DNS denies suppressed before file lock and writes batched, so quiet-mode bottleneck not evident. |
| `headless/network_audit_sockets.c` | Sockets instrumentées (`U06`) | POSIX socket wrappers preserve errno and call target formatting, getpeername and file audit only when diagnostics active; no unconditional socket peer query. |
| `headless/network_domain_rules.c` | Filtre de domaines (`U07`) | Guest domain policy is immutable after release-ready publication and no heap/socket work in lookup; linear scan is bounded but needs DNS workload measurements to justify indexing. |
| `headless/ps5_net_compat.c` | Compatibilité DNS PS5 (`U08`) | Native resolver and fcntl compatibility wrappers preserve special console ABI; resolver setup could be profiled but blind caching could change lifecycle and errno. |
| `headless/vulkan_surface.cpp` | Surface Vulkan PS5 (`U09`) | Vulkan surface enumerates display modes once at initialization and chooses 60/120 mode; loop and vector allocations are not a per-frame rendering bottleneck. |
| `headless/vulkan_allocator.cpp` | Traduction VMA (`U10`) | Single VMA_IMPLEMENTATION ownership TU contains no hotpath logic to optimize; verify no double implementation rather than replacing allocator source. |
| `headless/crash_report.cpp` | Rapport de crash (`U11`) | Crash reporter keeps signal path separate from helper threads, uses fixed buffer and atomics; startup/report failure handling isn't a per-frame cost, do not simplify signal safety without fault trace. |

**Décision du lot : 10 fichiers réellement lus, 0 nouveau patch C++.**
Les attentes GPU/HLE liées aux freezes FC27 ne sont pas « résolues »
par cette revue. Conserver le comportement de l'audio, des signaux de
crash et des politiques réseau est préférable à une micro-optimisation
non mesurée qui risquerait la stabilité.

Le suivi de l'optimisation de code passe de **279/491** à **289/491**
chemins examinés ou déjà corrigés, soit **202 fichiers restant à
traiter** dans cette passe. Ce chiffre est une file de tri, pas 202
correctifs prouvés nécessaires. Les preuves des contrats de test et la
compilation native sont suivies indépendamment.
