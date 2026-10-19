# HLE IPC — correction de délai d'attente ReplyAndReceive

Révision du 19 octobre 2026 · Branche `dev/ps5-sparse-jit`.

## Défaut constaté dans les sources

Le `ReplyAndReceiveImpl` épinglé construisait l'échéance absolue en
additionnant le tick courant, un délai positif et deux ticks dans un
entier signé de 64 bits, puis vérifiait `timeout <= 0`.
Cette vérification se produit **après** l'éventuel débordement signé,
qui constitue un comportement indéfini en C++. Les chemins
`WaitProcessWideKeyAtomic`, `WaitForAddress`,
`WaitSynchronization` et `SleepThread` possédaient déjà un calcul
d'échéance saturant ; le chemin IPC manquait encore ce garde.

## Correction maintenue

- En mode normal, CMake sélectionne la traduction complète
  `vendor/encore-active/eden-core/src/core/hle/kernel/svc/svc_ipc_standard.cpp`,
  identique à l'unité épinglée sauf la conversion vérifiée.
- En mode de diagnostic, `svc_ipc.cpp` conserve l'attribution des
  requêtes IPC aux threads et ajoute le **même** contrôle de débordement.
- Les deux additions sont effectuées avec `__builtin_add_overflow`
  et les délais impossibles saturent à `INT64_MAX`, en conservant le
  traitement des délais nuls/négatifs et les boucles d'attente HLE.
- La source dans `vendor/sources/eden` est inchangée ; les deux
  traductions complètes appartiennent exclusivement à
  `vendor/encore-active`. Aucune édition de corps de fonction en CMake.

## Témoins et limites

`tools/verify/hle/check-native-hle-ipc-timeout-host.py` compile les
calculs extraits des vrais fichiers C++ sous UBSan. Deux configurations
de dépassement doivent échouer sur l'original ; les variantes normales
et DEV doivent les gérer sans débordement, tout en respectant les valeurs
usuelles et limites. Le contrôle `check-vendor-consolidation-debt.py`
vérifie en parallèle la parité des traductions complètes.

**Ce correctif élimine un risque démontrable de comportement indéfini
dans le noyau HLE.** Il ne démontre pas que les gels observés à 30 FPS
étaient causés par ces délais extrêmes, ni une amélioration de FPS.
Les tests hôte ne remplacent ni compilation native ni vérification
console, et aucune option de synchronisation expérimentale n'est activée.
