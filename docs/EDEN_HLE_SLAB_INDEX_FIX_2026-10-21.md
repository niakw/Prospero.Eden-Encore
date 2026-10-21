# Eden Encore — correction des helpers d'index HLE slab

**21 octobre 2026**, branche `dev/ps5-sparse-jit`.

`vendor/encore-active/eden-threading/src/core/hle/kernel/slab_helpers.h` exposait trois chemins `GetSlabIndex` incohérents : un appel `GetIndex` absent du heap maintenu, et deux résolutions de `SlabHeap<Derived>(kernel)` non cohérentes avec les autres méthodes. La vraie API du `KSlabHeap` maintenu est `kernel.SlabHeap<Derived>().GetObjectIndex(...)`.

Les trois helpers utilisent maintenant ce chemin. Cette correction vise à éviter les échecs d'instanciation et les incohérences de l'accès HLE, sans changer le comportement des allocations ou les locks.

Le témoin hôte `tools/check-native-slab-index-host.py` compile sous ASan/UBSan une instanciation des trois méthodes du header actif avec des substituts d'interface minimale. Ni FPS console ni résolution du freeze FC27 ne sont revendiqués.

**Couverture : 413/491**, **16 moteur/runtime à examiner**, **62 UI séparés**, **78 globalement**.
