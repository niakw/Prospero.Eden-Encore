# Eden Encore — optimisation verrou de slab HLE et revue runtime

**21 octobre 2026.** Les 62 sources du frontend restent isolées du compteur prioritaire. `runtime_shims.cpp` est conservé du côté moteur car ses symboles C sont globaux.

## Correctif HLE réellement modifié

`vendor/encore-active/eden-threading/src/core/hle/kernel/k_slab_heap.h` : `KSlabHeapImpl` utilise déjà `m_lock` pour sérialiser toutes ses opérations `Allocate` et `Free` sur la liste libre. Ses deux lectures et deux écritures atomiques étaient implicitement séquentiellement cohérentes. Elles sont maintenant explicitement `std::memory_order_relaxed`, tout en conservant le mutex existant et les instructions qui suivent. Cela évite des barrières atomiques redondantes en cas d'utilisation intensive de l'allocateur de threads/objets du noyau.

`tools/check-native-kernel-slab-mutex-host.py` compile le véritable en-tête maintenu avec faux en-têtes d'API minimalistes et teste l'unicité des objets alloués entre 4 threads, le retour des éléments, l'épuisement de la liste et sa restauration sous ASan/UBSan. La prévalidation hôte appelle ce test. Aucun gain FPS PS5 n'est revendiqué.

## Quatre fichiers examinés et classés sans retouche C++

| Source | Contrat | Motif |
| --- | --- | --- |
| `src/fastmem.h` | `F12` | Thin ABI header for direct fastmem access and PC/RSP slots on PS5/Linux. Runtime functions are declarations or one offset-based register access in a signal handler; no scan/allocation/polling to optimize. Firmware ABI offsets intentionally unchanged; do not change absent oracle proof. Blob `32dd49e4d6d05b0b32b90d8cfb2404b33bbef5f4` |
| `headless/prosperoeden/runtime_shims.cpp` | `U87` | This is the global C runtime owner linked with the emulator as well as launcher, not one of 62 UI sources. pthread_once spins with sceKernelUsleep only while library static initialization is in progress; strtof/fseek/ftell/strcasestr are small libc compatibility wrappers outside the game CPU/GPU draw loops. Do not invent micro-optimizations to libc behavior. Blob `6ce11f021f49f0ed8125f4cec571b391c254ef3c` |
| `vendor/encore-active/eden-core/src/core/hle/service/audio/audio_controller.cpp` | `A10` | HLE service requests for volume/output targets/mute, not PCM mixing. GetSetSys uses call_once and reuses a service pointer; SetTargetVolume/SetTargetMute perform work only on explicit IPC controls. Keep source behavior to avoid reintroducing audio service deadlock or sink mismatch. Blob `2408420253c568a63b56713313be8290f3e4e9ec` |
| `vendor/encore-active/eden-core/src/core/hle/service/am/service/application_functions.cpp` | `H32` | Application-management IPC for save-data setup, title/version metadata and lifecycle/event requests, not guest-JIT execution or frame-time synchronization. Handle-title operations are on-demand and no repeatedly taken critical renderer lock. Retain metadata fallback and notification semantics. Blob `6f80d50d4c732004bef6ff387dbbc68e0778d1e3` |

**Bilan : 412/491 sources prises en charge, 17 moteur/runtime restant à examiner, 62 UI du lanceur séparées, 79 globalement.** Une source C++ modifiée et quatre sources étudiées sans patch ; la qualification matérielle demeure distincte.
