# Eden Encore — une seule version livrable (26 octobre 2026)

## Règle de développement

**Une seule branche de travail et un seul paquet PS5 à qualifier :** le
profil natif final (`tools/build-package.sh release` /
`release-stage`), application `PPSA99008`. Le nom historique de la branche
`dev/ps5-sparse-jit` n'implique pas qu'un profil DEV soit livré.

- Aucun chantier d'amélioration des profils `EDEN_DEV_PROFILE`,
  `EDEN_SPARSE_JIT_DEV`, `EDEN_SHARED_JIT`,
  `EDEN_JIT_COMPILE_BATCH`, ou `fast_first_pipelines`. Ces variantes
  restent désactivées dans l'unique paquet final. Les oracles et composants
  historiques peuvent demeurer dans les sources tant qu'ils ne sont pas
  compilés/activés dans l'exécutable final ; ils ne font plus partie du suivi
  d'optimisation ou des demandes de tests.
- Un correctif est accepté seulement si le **chemin effectivement sélectionné
  en production** est démontré, avec son test source/hôte, une vérification de
  régression fonctionnelle et le paquet natif compilé sur le même SHA.
- Une source lue ou un contrat marqué SOURCE n'est pas un fichier à modifier
  automatiquement. Préserver les verrous, barrières Vulkan, invalidations
  TIC/TSC, durée de vie GPU et cohérence JIT avant tout gain hypothétique.
- **F07 FC27** reste la priorité moteur : distinguer pauses JIT, temps sous
  mutex buffer/texture, cadence des présentations, contenu nouveau, HUD et
  latence de commande. Ne pas extrapoler de gain depuis les tests hôte.
- Le ZIP FTP validé doit contenir `PPSA99008/eboot.bin` et
  `PPSA99008/sce_sys/param.json`. Pas de dossier ZIP imbriqué.

## Audit des fonctions restantes

La dernière revue exhaustive du périmètre initial de **491 chemins** classe
**429 propriétaires dont les sources moteur sont toutes examinées**, et
**62 unités du lanceur suivies séparément**. Les additions postérieures font
partie d'un inventaire plus large : il faut recalculer exactement les
différences, plutôt qu'appeler `SOURCE + OPEN` des optimisations manquantes.

Une validation de toutes les fonctions demanderait une preuve de comportement
de chaque chemin : les comptes documentaires, les gardes source et les
analyses statiques ne remplacent pas cette qualification.

Le correctif HUD `DrawTexture` est conservé dans le profil final.
La modification `97031b0` du pipeline optimisé en arrière-plan est retirée :
elle ciblait seulement le mode expérimental et a cassé la reproduction
complète de la source Vulkan.
