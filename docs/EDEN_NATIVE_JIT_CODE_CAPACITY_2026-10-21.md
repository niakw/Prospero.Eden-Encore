# Eden Encore — native JIT code allocation overflow guard

`BlockOfCode::AllocateFromCodeSpace` in the active native Dynarmic implementation previously compared `size_ + alloc_size >= maxSize_`. The input `alloc_size` can be large, and unsigned arithmetic can wrap before the comparison, letting an invalid request reach `EnsureMemoryCommitted`, `getCurr` and `memset`. This is a correctness boundary, not a proven in-game occurrence.

The guard now checks `size_ >= maxSize_ || alloc_size >= maxSize_ - size_` without adding. The same strict policy rejects exact-capacity allocations; permitted requests continue to commit, advance cursor and zero memory unchanged. No alternate JIT profile, sparse backend, signal handler or W^X permission transitions are altered.

`tools/check-native-jit-code-space-bounds-host.py` extracts the actual allocator method into a source-derived C++20 ASan/UBSan fixture and exercises normal, exact-fit and overflow requests, including `SIZE_MAX` corner cases. The checks run under the fast gate and complete preflight. **426/491 handled; 3 core engine sources outstanding; launcher UI 62 separately.** No PS5 FPS, JIT throughput or title stability result is inferred.

## Sélection de compilation du JIT sparse

Le premier garde-fou concernait la capacité d'allocation. Un second contrôle supprime de **toute compilation release** la lecture atomique de `Eden::Experimental::sparse_jit_cache` dans `EnsureMemoryCommitted`. L'ancienne condition `#ifdef PS5_NATIVE` compilait ce branchement même lorsque l'option sparse de CMake était OFF. L'implémentation est désormais sous `#if defined(PS5_NATIVE) && defined(EDEN_SPARSE_JIT_DEV)`; le CMake transmet explicitement cette définition à `dynarmic` seulement avec l'option DEV.

La sélection est vérifiée par `tools/check-native-sparse-jit-release-selector-host.py`, qui compile la méthode réelle en deux profils (ASan/UBSan), vérifie qu'aucun appel sparse ne se produit ni symbole diagnostic ne demeure dans le binaire release, et que l'option DEV fonctionne toujours. Le code du pont CPU→GPU et la permission W^X sont inchangés. Le compteur de fichiers ne diminue pas : ce chemin Dynarmic était déjà pris en charge.
