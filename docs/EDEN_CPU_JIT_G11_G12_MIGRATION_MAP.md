# Eden Encore — migration coordonnée CPU/JIT G11–G12 et X06/X07

**Actualisation au 19 octobre 2026 : migration de source effectuée ; plan
ci-dessous conservé comme historique, et non comme travaux à recommencer.**
Le sélecteur actif `headless/CMakeLists.txt` utilise désormais des unités
entières et exclusives `vendor/encore-active/eden-core/src/core/arm/dynarmic/g11/`
pour A32/A64 × hôte/natif × DEV/normal (8 fichiers, 16 combinaisons
avec l'option inline OFF/ON), au lieu de construire leurs fonctions
par `write_derived`. Le contrôle `tools/check-g11-jit-profile-matrix-host.py`
rejoue la sélection et compare les variantes à l'ancien générateur.
La compilation G12 sélectionne
`vendor/encore-active/eden-core/src/core/hle/kernel/physical_core_{dev,standard}.cpp`
par copie sans transformation C++, avec l'atomicité X07 incluse aux
sources maintenues. Les anciennes recettes X06/X07 ne sont plus incluses
en tant que générateurs de fonctions.

**La prochaine étape n'est pas une migration supplémentaire de G11/G12 :
c'est l'analyse des compilations, invalidations, prises de verrous et
attentes constatées en exécution.** Les tests hôte et la sélection CMake
ne qualifient ni les FPS ni la progression de FC27 sur console.


**État au 18 octobre 2026 :** cartographie de la prochaine frontière ; sources
G11, G12 et substitutions indirectes X06/X07 **non migrées**. G10 (interface
native A32) a été déplacée dans `encore-active` et possède son contrôle de
parité propre. Le présent périmètre n'inclut ni le launcher ni ses ressources.

## Périmètre réel et interfaces

| Site restant | Source épinglée / module | Propriétaire futur | Variantes obligatoires |
| --- | --- | --- | --- |
| G11 | `src/core/arm/dynarmic/arm_dynarmic_{32,64}.cpp` et `headless/CMakeLists.txt` | Unités complètes `vendor/encore-active/eden-core/src/core/arm/dynarmic/` | A32/A64, hôte/natif, DEV/release, exclusifs désactivés/expérimentaux |
| X06 | `headless/native_jit_memory_read_guard.cmake` | Méthodes de callback mémoire des mêmes unités G11 | Aborts/refus de lecture, page-table, callback de suivi guest, absence de lecture après refus |
| G12 | `src/core/hle/kernel/physical_core.cpp` et `headless/CMakeLists.txt` | Unité complète de `vendor/encore-active/eden-core/src/core/hle/kernel/` | Idle normal, profilage DEV, host/native, préfetch abort |
| X07 | `headless/physical_core_interrupt_atomic.cmake` | Synchronisation de `m_is_interrupted` dans l'unité G12 | `IsInterrupted`, `Idle`, `Interrupt`, `ClearInterrupt`, stores/loads atomiques, DEV |

## G11 — contrôles couplés à conserver

La boucle CMake dérive les deux wrappers de Dynarmic. Elle applique
notamment : politique de code-cache A32/A64 avec capacité initiale,
`std::countl_zero(PageTable::ATTRIBUTE_MASK)`, fastmem exclusifs
(option `EDEN_INLINE_EXCLUSIVES` **OFF** par défaut), profilage de
callbacks DEV, diagnostics des accès invités, `Eden::Watch` et
`Eden::CrashSite` pour A64, rappel de `JitStartup::ConstructWithCapacityFallback`
sur allocations contiguës échouées, et le module X06.

**Couplage non négociable :** la source complete du wrapper A32 et celle
du wrapper A64 doivent recevoir les mêmes changements de capacité et les
mêmes signatures de callback prévues pour leur ISA. Les chemins `watch`,
`crash_site` et les compteurs n'entrent pas dans le hot path normal
lorsque les diagnostics sont désactivés. Ne pas activer l'inline
exclusive pour « améliorer » les chiffres sans preuve matérielle :
l'ancien commentaire de production documente un risque de soft hang.

Les bascules DEV, native et inline-exclusives doivent passer en
**gardes C++ explicites** ; CMake sélectionne ou copie l'unité complète,
mais ne reconstruit plus de corps de fonction par `string(REPLACE)`.

## G12/X07 — atomicité et arrêt sur faute

`physical_core.cpp` garde le chemin condition-variable original en
shipping. En DEV, l'échantillonnage Idle ne prend l'horloge que lorsque
la télémétrie détaillée est active. X07 transforme **toutes** les lectures
et écritures du booléen `m_is_interrupted` avec `std::atomic_ref` ;
une seule écriture ordinaire subsistante serait une data race.

L'arrêt après `PrefetchAbort` conserve le dump borné des registres
invités, la recherche de mapping LR et `RecordGuestFault` sur la seule
voie fatale. Aucun suivi par frame ni déréférencement d'adresse invitée
non fiable ne doit être introduit.

**Migration atomique :** produire les corps complets normal/DEV et intégrer
X07 **avant** de retirer simultanément G12 et
`physical_core_interrupt_atomic.cmake`. Ne pas laisser deux mécanismes
d'atomicité concurrents actifs.

## Preuves requises avant statut HOST / retrait des compteurs

1. Comparer chaque source maintenue à la source épinglée et aux
   transformations historiques, y compris les profils DEV et natif.
   Verrouiller les ancres de fonctions et la sélection CMake.
2. Exécuter `tools/check-native-physical-core-atomic-host.py`,
   `tools/check-native-physical-core-interrupt-ack-host.py`,
   `tools/check-ps5-guest-fault-recovery.py` pour G12/X07.
3. Exécuter `tools/check-native-jit-memory-read-guard-host.py`,
   `tools/check-ps5-architecture.py`, les tests de cache JIT et
   de callback pour G11/X06 ; comparer les chemins A32/A64.
4. Exécuter l'inventaire exact des modules et générateurs par
   `tools/check-vendor-consolidation-debt.py` et les catalogues de
   sources/graphes ; supprimer X06/X07 seulement avec leurs transformations.
5. Valider par préflight hôte ; qualifier séparément la compilation native
   et la console. Un test textuel ou CMake vert ne prouve ni le timing
   guest ni l'absence de soft hang.

**Contrat de reprise :** commencer par G12/X07 (un propriétaire commun
avec mode DEV), puis traiter G11/X06 comme un ensemble A32/A64. Les
générateurs G13 et suivants restent hors de ce périmètre.
