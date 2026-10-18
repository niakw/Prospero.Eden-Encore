# Eden Encore — source de vérité unique des overrides

**Règle impérative :** tout correctif ou variante de source d'une
dépendance doit vivre dans **`vendor/encore-active/`**, sous forme
de source complète, d'en-tête complet ou de donnée maintenue. Le compilateur
ne doit sélectionner qu'un propriétaire de code. Les sources originales
sous `vendor/sources/` restent immuables.

Le rôle de `headless/CMakeLists.txt`, `headless/*.cmake`, `tools/`,
`Makefile` et `.github/workflows/` est d'assembler, sélectionner,
installer et **vérifier** — pas de conserver la correction C++ concurrente.
Les scripts de replay de patches sont des oracles historiques, pas
une autre source de vérité. Les scripts d'installation peuvent copier les
fichiers maintenus et refuser toute dérive SHA, mais pas inventer de
nouveaux corps C++ destinés à la console.

## État concret au 18 octobre 2026

- `vendor/encore-active` : **232 sources et en-têtes suivis**, tous avec
  un propriétaire de chemin dans le graphe. Couverture documentaire,
  **pas** validation console.
- `headless/CMakeLists.txt` : **31 générateurs** `write_derived`.
- Six modules CMake supplémentaires totalisent **21 générateurs**
  `write_derived`, soit **52 sites** au total.
- Quatre modules CMake procèdent encore à des substitutions **indirectes**
  dans des variables source. **Dette restante**, non cachée par le
  nombre 54.
- `headless/` contient **8 fragments `.inc`**. Plusieurs contribuent
  aux sources dérivées JIT/GPU/mémoire. Les autres doivent être classés
  selon qu'il s'agit d'un runtime natif autonome ou d'un override de
  dépendance. **Leur présence dans `headless` ne vaut pas conformité
  à la règle de centralisation.**
- Les fichiers `src/`, `third_party/`, `assets/`, `data/`,
  `fixtures/` et `sce_sys/` sont distincts : code natif original,
  contrats ABI, ressources ou tests. Ils ne sont pas automatiquement
  des corrections aux dépendances. Toute future transformation de source
  découverte dans ces répertoires doit rejoindre `encore-active`.
- `tools/build-headless-host.sh` (FFmpeg hôte),
  `tools/materialize-openssl-cert.py` (certificats),
  `tools/build-radv-dependencies.sh` (ccache Meson temporaire) et
  `tools/build-opengl-sdk.sh` (test hôte provisoire) restent des
  transformations de **build/ressource**, à qualifier séparément des
  overrides C++ ; elles sont documentées dans
  `EDEN_OVERRIDE_MIGRATION_INVENTORY.md`.

## Recensement des modules CMake hors CMake principal

<!-- SINGLE_SOURCE_CMAKE_START -->
| Fichier | Nature | Position |
| --- | --- | --- |
| `headless/checked-fastmem.cmake` | Réécriture indirecte de code, à déplacer | Dette de migration |
| `headless/dynarmic/reg_alloc.cmake` | Générateur de source dérivée, à déplacer | Dette de migration |
| `headless/dynarmic/shared-jit.cmake` | Générateur de source dérivée, à déplacer | Dette de migration |
| `headless/gpu_native_observability.cmake` | Générateur de source dérivée, à déplacer | Dette de migration |
| `headless/guest_write_deferred_bridge.cmake` | Générateur de source dérivée, à déplacer | Dette de migration |
| `headless/inject.cmake` | Orchestration ou toolchain | Sélecteur / configuration |
| `headless/jit-alias.cmake` | Générateur de source dérivée, à déplacer | Dette de migration |
| `headless/native_guest_range_overflow.cmake` | Réécriture indirecte de code, à déplacer | Dette de migration |
| `headless/native_jit_memory_read_guard.cmake` | Réécriture indirecte de code, à déplacer | Dette de migration |
| `headless/physical_core_interrupt_atomic.cmake` | Réécriture indirecte de code, à déplacer | Dette de migration |
| `headless/ps5.cmake` | Orchestration ou toolchain | Sélecteur / configuration |
| `headless/scalar-memory.cmake` | Générateur de source dérivée, à déplacer | Dette de migration |
| `headless/vulkan.cmake` | Sélection/copie de sources Encore maintenues | Sélecteur / configuration |
<!-- SINGLE_SOURCE_CMAKE_END -->

## Cache GPU R437 maintenu

Le header natif `video_core/buffer_cache/buffer_cache.h`, initialement créé
par substitutions dans CMake, est maintenant la version complète suivie dans
`vendor/encore-active/eden-core/src/video_core/buffer_cache/`. La compilation
PS5 sélectionne une copie identique de ce header ; la comparaison avec
`eden-backports` et le témoin R437 empêchent le retour de l'ancien générateur.
Le helper applicatif `headless/buffer_pages.h` reste un composant distinct.

## Runtime RADV maintenu

Le fichier de démarrage natif `app_crt_radv.cpp` est maintenu
dans `vendor/encore-active/eden-build/tooling/native/` et choisi
explicitement par le profil RADV ; la branche CMake ne transforme plus
le boilerplate en C++.

## Fragments inclus ou injectés : vérifier leur propriétaire réel

Les entrées techniques qui fabriquent un correctif pour une dépendance
doivent finir dans `encore-active`. Ne pas transférer à l'aveugle les
fragments de l'application native qui ne remplacent aucune source upstream.

<!-- SINGLE_SOURCE_FRAGMENTS_START -->
| Chemin | Hypothèse de rôle | Qualification |
| --- | --- | --- |
| `headless/dev_render_passes.inc` | Fragment local, sélectionner/qualifier | À vérifier dans les consommateurs / CMake |
| `headless/gpu_native_probe.inc` | Fragment technique, tracer l'inclusion | À vérifier dans les consommateurs / CMake |
| `headless/gpu_probe.inc` | Fragment technique, tracer l'inclusion | À vérifier dans les consommateurs / CMake |
| `headless/heap_arenas.inc` | Runtime natif (non nécessairement override) | À vérifier dans les consommateurs / CMake |
| `headless/jit-compile-batch.inc` | Fragment technique, tracer l'inclusion | À vérifier dans les consommateurs / CMake |
| `headless/jit-permissions.inc` | Fragment technique, tracer l'inclusion | À vérifier dans les consommateurs / CMake |
| `headless/jit_assert.inc` | Fragment local, sélectionner/qualifier | À vérifier dans les consommateurs / CMake |
| `headless/native_gpu_thread.inc` | Fragment technique, tracer l'inclusion | À vérifier dans les consommateurs / CMake |
<!-- SINGLE_SOURCE_FRAGMENTS_END -->

## Groupe JIT partagé centralisé

Les cinq fragments `jit_*.inc` et `jit_group.h` ont été déplacés à
blobs Git identiques dans `vendor/encore-active/eden-core/dynarmic/shared-jit/`.
Le sélecteur de `headless/dynarmic/shared-jit.cmake` lit les fichiers
maintenus. **Ce module CMake conserve encore des transformations upstream
à migrer** ; la relocalisation des données d'injection ne supprime pas les
21 générateurs de modules. Le mode JIT partagé reste OFF par défaut.

## Fragments scalaires centralisés

Les injections Dynarmic `scalar-fold.inc`,
`scalar-memory-read.inc` et `scalar-memory-write.inc` sont désormais
maintenues uniquement sous `vendor/encore-active/eden-core/dynarmic/scalar/`.
CMake charge ces contenus, mais garde encore les règles d'injection et
les générateurs C++ correspondants : **centralisation des données ne signifie
pas encore suppression des générateurs**.

## Oracles Vulkan historiques

Les cinq anciens fragments Vulkan ont été déplacés **sans modifier leurs blobs
Git** vers `vendor/encore-active/eden-vulkan-oracles/`. Ils ne constituent
pas une seconde version compilée de Vulkan : `tools/prepare-vulkan-port.py`
ne les charge que pour reconstituer les sorties historiques, tandis que
le binaire choisit exclusivement `vendor/encore-active/eden-vulkan/`.
`headless/vulkan.cmake` ne les surveille plus inutilement comme dépendances
de configuration. Leur conservation sert la preuve de parité, pas la
construction du moteur.

## Correction GPU réellement centralisée

`video_core/memory_manager.cpp` est désormais maintenu dans
`vendor/encore-active/eden-core/src/video_core/`, avec les huit sites
de correction de plages, débordements et pages GPU. `PS5_NATIVE` sélectionne
directement cette source. Le module `native_gpu_granular_bounds.cmake`
et la génération `memory-manager-native.cpp` sont supprimés.
Les vérifications hôtes contrôlent les fonctions maintenues et leur parité
avec les anciennes transformations ; aucun gain FPS ni résultat console
n'est inféré.

## Variantes HID exclusives

Le témoin R435 ne génère plus `npad_pause_diag.cpp` dans CMake.
`hid_core` compile une seule variante : le `npad.cpp` maintenu
ordinaire, ou `npad_pause_diag.cpp` lorsque `PS5_NATIVE` et
`EDEN_DEV_PROFILE` sont tous deux activés. La variante de diagnostic
conserve les deux gardes de pointeurs de la version normale et ne modifie
ni le mapping ni les commandes. Le contrôle hôte compare le code
extérieur au témoin Fullkey et vérifie la sélection exclusive.

## Injections GPU centralisées

Les deux fragments `gpu_queue_stop_wait.inc` et `gpu_sync_failure_wait.inc`
sont des entrées de code maintenues exclusivement dans
`vendor/encore-active/eden-core/gpu-injections/`. Leur contenu reste
bit-à-bit identique aux blobs Git déplacés. CMake charge ces fichiers
comme données d'injection en attendant la migration des unités C++ dérivées,
avec dépendances explicites pour toute modification.

## Verrou natif Dynarmic centralisé

Le fragment historique `headless/spin-lock.inc` est supprimé. Les fonctions
`SpinLock::Lock()` et `SpinLock::Unlock()` résident dans l'unique source
`vendor/encore-active/eden-core/src/dynarmic/common/spin_lock_x64.cpp`.
Le build natif sélectionne cette source directement et n'assemble plus
le corps C++ dans CMake. La vérification de provenance protège son
identité Git ; le comportement console reste à confirmer.

## Correction de cache de shaders centralisée

Le chargement d'un cache tronqué ou corrompu est compilé depuis
`eden-core/src/video_core/shader_environment.cpp` qui inclut
`shader_cache_reader.inc` depuis son propre dossier Encore.
Le générateur CMake et le doublon `headless/` sont supprimés.
Le contrôle de parité reconstruit l'ancien résultat du CMake épinglé ;
cela ne constitue pas une preuve de comportement sur console.

## Conditions de sortie de la dette

1. Aucun générateur CMake ne reconstruit du C++ corrigé à partir d'une
   source épinglée. Les ressources GLSL et sorties de configuration ne
   sont pas automatiquement du C++ : les classer par usage.
2. Aucun module indirect ne transforme un corps ou un en-tête upstream ;
   toute modification est une source suivie dans `encore-active`.
3. Les scripts `tools/` encore autorisés pour la production se limitent
   à sélectionner, copier, configurer ou contrôler. Les différences hôtes,
   certificats et packaging ont chacune une origine versionnée explicite.
4. Les `.inc` qui injectent une modification upstream sont migrés dans
   `encore-active`, avec mise à jour des include paths ou du sélecteur.
5. Chaque transfert possède un test de **parité exacte** avec la source
   anciennement générée, un rattachement de fonctions, et une prévalidation
   CI. La validation du comportement console est distincte.
6. `headless/prosperoeden/` reste le code du launcher dans son chantier
   indépendant ; la centralisation des overrides ne justifie pas de toucher
   au thème ni aux mappings de commandes.

Ce registre est un **périmètre de migration**, pas un certificat
d'achèvement. L'énumération de modules et fragments est vérifiée par CI :
un nouveau fichier doit être explicitement qualifié plutôt que devenir
un override invisible.
