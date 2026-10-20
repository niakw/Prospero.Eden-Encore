# Encore — examen ciblé des politiques GPU et mémoire déjà optimisées

**21 octobre 2026 · HEAD de référence `4c62c5f4c` · branche `dev/ps5-sparse-jit`.**

Ce lot porte sur **8 chemins de production natifs** et leurs contrats
et témoins directement exécutés par la prévalidation CI. Le code a été
inspecté pour éviter de répéter les améliorations déjà appliquées
à la gestion mémoire et à la répartition des écritures GPU.

| Source inspectée | Contrat | Protection/fast path déjà maintenu |
| --- | --- | --- |
| `headless/direct_pool_probe_policy.h` | U43 | Bounded policy: 100 ms polls under pressure; 250 ms only with a prior valid >=4 GiB free observation, avoiding frequent driver syscalls. |
| `headless/direct_pool_region_scan.h` | U44 | Checks monotone interval coverage with overflow-safe extent bounds; conservatively reports only an upper free bound. |
| `headless/direct_pool_accounting.h` | U32 | Checks physical-ownership accounting without overflowing start + allocation span; virtual reservations are excluded. |
| `headless/vulkan_gc_budget.h` | U77 | Saturating arithmetic prevents unsigned wrap on projected reclaim and frame-age eviction tests. |
| `headless/vulkan_pool_capacity.h` | U78 | One-time atomic latch of first valid device-free estimate; repeated probes are driven elsewhere by existing throttle. |
| `headless/cache_budget.h` | U28 | Shader cache trims only at session boundary and only when verified free disk space drops below reserve. |
| `headless/buffer_write_ahead.h` | R06 | Bounded write-ahead of 64 pages, rejects unregistered pages and overflow before marking dirty. |
| `headless/gpu_dirty_region_split.h` | R04 | 32-bit dirty mask split into 2 KiB regions with overflow check before any callback; preserves per-region order. |

**Décision :** aucun diff C/C++ nouveau, car ces fonctions disposent
déjà des protections d'adresse/overflow, des chemins non allocants et
des cadences conservatrices recherchés. Les tests ne démontrent ni
le budget libre exact de la PS5, ni une amélioration FPS en jeu. Les
éventuels dépassements ou attentes de textures doivent être reliés
à un défaut reproduit avant tout autre patch.

**Bilan d'optimisation de code :** 332 fichiers traités ou examinés
sur 491, **159 encore à traiter**. Parmi les 159 restants,
**62 sont dans le chantier du lanceur** ; **97** sont des chemins
moteur ou infrastructure native prioritaires (dont les shims globaux
`runtime_shims.cpp`). Le registre de qualification HOST/SOURCE
demeure séparé.
