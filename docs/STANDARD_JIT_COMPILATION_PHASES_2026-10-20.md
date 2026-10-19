# Eden Encore — Standard A64 JIT compilation phase witness

Branch: dev/ps5-sparse-jit. Host-only implementation and regression.

## Evidence

Historical FC27 telemetry showed long presentation intervals correlated with
A64 compilation bursts, without identifying what fraction of the compiler
cost came from translation, optimization or native emission. The previous
DEV hook `eden_jit_phases` ran only for experimental bounded batch/shared
modes, not the normal per-core, non-batch Dynarmic compiler. Consequently,
`jit_dups=on` could not count repeat compilation in the standard path.

## Change

The complete active `a64_interface_standard.cpp` now samples clocks
around `Translate`, `Optimize` and `Emit` in its default non-batch
branch **only** when compiled with `EDEN_JIT_A64_DEV_PROFILE` and
detailed logging is enabled. It uses the already-declared weak
`eden_jit_phases` callback and passes the actual location descriptor.
With `jit_dups=off` phase totals can still be observed; duplicate
map recording requires the existing explicit opt-in and its associated
memory/lock overhead. No clock reads or callbacks are introduced in
release and quiet-DEV execution, and no changes affect guest code,
cache invalidation, JIT allocation, scheduling or GPUs.

The host fixture compiles the extracted real default non-batch code
in release and DEV configurations under ASan/UBSan and verifies
both silent runs and one detailed compile report. All other CMake
selection modes and the shared/batch behavior remain unchanged.

## Limits

These are **aggregated per-core compile phases**, not a one-to-one
guest-frame critical path. Historical 15 October logs predate this
hook. The user still needs an identified native PS5 diagnostic build
and same-scene frametime/guest-progress evidence before claiming that
repeat compiles cause a freeze or that FPS improved. Do not activate
shared or batch JIT just to collect diagnostics.

## 20 octobre — diagnostic mémoire borné au lancement

Le suivi de recompilation `jit_dups=on` réservait initialement
`2^21` buckets d'une table de hachage, environ **16 MiB pour le seul
tableau de buckets** sur une implémentation 64 bits classique, avant
d'enregistrer le premier bloc. Il réserve désormais `2^14` buckets au
premier enregistrement (~128 KiB de tableau), puis grandit normalement
si une session de diagnostic collecte beaucoup de blocs. Après arrêt
des workers, la remise à zéro du titre détruit la table et sa capacité
au lieu de conserver les buckets du plus gros jeu précédent.

Le test hôte compile la classe C++ effective avec ASan/UBSan, vérifie
les premiers buckets, la croissance sur 50 000 localisations, la libération
des buckets entre jeux et la classification multithread des doublons.
Le code fonctionne seulement sous profil développeur et seulement lorsque
`jit_dups` est activé : ce gain mémoire du **diagnostic** ne saurait être
présenté comme une amélioration des FPS en mode release.

## 20 octobre — vidanges JIT réellement appliquées (standard A64)

La voie A64 standard distingue désormais les vidanges **effectives** :
`EDEN_PERF_JIT_CACHE core=N flush_all=X flush_ranges=Y
scope=standard_a64_applied` sous profil DEV. L'instrumentation
n'incrémente le compteur qu'après le traitement du cache, lorsqu'une
invalidation non vide a été appliquée : l'absence de doublons dans
`jit_dups` n'était auparavant pas une mesure de cohérence du cache.
Les requêtes fusionnées peuvent donner une seule invalidation de plages.
Les vidanges complètes incluent la pression code-cache et les effacements
explicites ; ces compteurs **ne déduisent pas** l'origine exacte du flush.

Le hook est compilé uniquement en profil développeur A64 standard, et
l'appel n'est réalisé que lorsque la journalisation détaillée est active.
Les compteurs sont remis à zéro à la frontière de session après arrêt
des workers précédents. Un test hôte compile la méthode C++ exacte sous
ASan/UBSan dans ses variantes release/DEV et couvre les invalidations
vides, totales, par plage, combinées et le mode silencieux. Ni le JIT
partagé, ni les mutex, ni les caches GPU, ni le chemin release ne changent.
Aucune preuve d'amélioration en jeu sans capture native instrumentée.
