# G06–G07 — frontières de migration des émetteurs mémoire Dynarmic

Date : 2026-10-18. Statut : **cartographié, migration des deux corps G06/G07 encore ouverte**.

## But et sources d'autorité

L'adaptation du code ne doit avoir **qu'un seul propriétaire physique**, sous
`vendor/encore-active/eden-core/src/dynarmic/backend/x64/`. Les sources
`vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/` restent épinglées.
CMake doit seulement choisir/copier des unités complètes dans les chemins de
build existants ; aucun `string(REPLACE)` de code C++ ne doit rester.

- **G06** : `emit_x64_memory.cpp.inc` — corps de méthodes mémoire inclus par
  A32 et A64. Il ne s'agit **pas** d'une unité de traduction autonome.
- **G07** : `emit_x64_memory.h` — décodage d'adresses, fallback et accès
  exclusifs, inclus par les mêmes unités.
- **G08 [source déplacée, validation ouverte]** :
  `a32_emit_x64_memory.cpp` et `a64_emit_x64_memory.cpp` sont deux sources
  complètes maintenues sous `encore-active`. Les macros de monitor/config
  shared sont conditionnées par `EDEN_SHARED_JIT_LAYOUT` et la sélection
  CMake est une copie. Preuves : `tools/check-maintained-memory-units.py`.

## Propriétaires des transformations à absorber

| Composant de production | Origine actuelle de la transformation | Contrats à ne pas perdre |
| --- | --- | --- |
| `EmitVAddrLookup<A32EmitContext>` / `<A64EmitContext>` | G07, `headless/CMakeLists.txt` | Indexation à échelle x86, page-table stride 0–3 et au-delà, masque packed `0x00fffffffffff000`, extension de signe et registres scratch |
| `EmitExclusiveVAddrLookup` | G07, bloc CMake `exclusive_lookup` | Alignement naturel, fallback page-table si fastmem indisponible, aucune allocation conditionnelle de registre au milieu des branches |
| `EmitCheckedFastmemTest` / `EmitCheckedFallbackLookup` | `headless/checked-fastmem.cmake` dans G07 | Fenêtre de vérification A32 ; bits lecture/écriture ; transition directe vers fallback et gestion de pages contiguës |
| `EmitMemoryRead` / `EmitMemoryWrite` | `headless/scalar-memory.cmake`, `scalar-memory-{read,write}.inc`, `checked-fastmem.cmake` dans G06 | VLDR/VSTR scalaires en XMM, fallback ordonné, conservation de l'adresse de patch, accès 32/64 et SIMD |
| `EmitExclusiveReadMemoryInline` / `EmitExclusiveWriteMemoryInline` | Bloc `memory_exclusive` de G06 ; `checked-fastmem.cmake` | Global monitor, vérification d'alignement, CMPXCHG16B, A32 page-table fallback et règles de déclenchement des recompilations |
| `EDEN_EXCLUSIVE_ADDRESS` / `VALUE` / `CONF_ARG` | `headless/dynarmic/shared-jit.cmake`, G06 + G08 | Adressage du monitor et de la configuration par l'état JIT A64 partagé ; adresse locale A32 en mode normal |
| Nettoyage des réservations exclusives | `eden_shared_jit_memory_header`, G07 | Suppression des réservations de tous les cœurs pour l'état partagé, sans changer les règles A32 ordinaires |

Les fragments `scalar-memory-*.inc` sont actuellement des **oracles
historiques** conservés dans `vendor/encore-active/eden-core/dynarmic/scalar/`.
Le futur corps maintenu de G06 doit intégrer leur logique entière, mais ne
doit pas en fabriquer un second exemplaire compilé.

## Matrice de profils à préserver

| Dimension | Modes à vérifier |
| --- | --- |
| Architecture | A32, A64 — un même fragment G06 est inclus depuis deux TU |
| Mémoire | Direct fastmem, page-table, checked A32, fallback exception-handler |
| Exclusifs | Lecture/écriture, alignement, 8/16/32/64/128 bits |
| JIT | Standard, `EDEN_SHARED_JIT` expérimental |
| Runtime | Hôte Linux, `PS5_NATIVE` |
| Diagnostics | DEV / normal, sans imposer de mesure permanente dans le chemin shipping |

## Ordre de migration sans duplication

1. Construire les deux **fichiers complets maintenus** `emit_x64_memory.h`
   et `emit_x64_memory.cpp.inc` en conservant les séparations de variantes
   nécessaires dans le C++, pas par substitutions dans CMake. Le fragment
   `.cpp.inc` demeure un include C++ réel partagé, pas un patch CMake.
2. Contrôler chaque bloc source contre les transformations épinglées par
   les points de vérification ci-dessus ; refuser les divergences et ne
   supprimer aucun garde A32/A64 non prouvé.
3. Remplacer G06/G07 par des `configure_file(... COPYONLY)` aux mêmes
   chemins dérivés ; retirer **ensemble** les producteurs C++ de
   `scalar-memory.cmake`, `checked-fastmem.cmake` et les macros mémoire
   de `shared-jit.cmake`, en préservant leurs autres sélections légitimes.
4. Vérifier les chemins sélectionnés **et** leurs consommateurs : tests
   mémoire JIT, exclusifs, scalaire SIMD, fastmem vérifié, regressions
   de compilation hôte/asan, puis build natif réel. Le succès d'une
   parité textuelle **ne constitue pas** une preuve console.
5. N'enregistrer G06/G07 comme migrés qu'après la sélection et les
   contrôles ; synchroniser immédiatement les catalogues
   `EDEN_ACTIVE_SOURCE_CATALOG.md`, `EDEN_CORE_AUDIT_DEPENDENCIES.md`
   et `EDEN_OVERRIDE_MIGRATION_INVENTORY.md`.

## Points de preuve déjà existants

`tools/check-maintained-memory-units.py` vérifie G08 ;
`tools/check-exclusive-monitor.py`,
`tools/check-jit-memory-policy.py`,
`tools/check-native-jit-memory-read-guard-host.py` et
`tools/check-maintained-scalar-emitters.py` couvrent des
propriétés voisines. Ces tests devront être complétés par
des preuves spécifiques à G06/G07 et par un build natif.

**Ne pas déclarer G06/G07 terminés tant que les deux sources maintenues
ne remplacent pas effectivement les transformations de code.**
