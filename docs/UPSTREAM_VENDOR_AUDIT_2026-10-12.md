# Eden Encore — audit des vendors du 12 octobre 2026

**Intégration sur une seule branche : `dev/ps5-sparse-jit`.** Les correctifs upstream ne sont pas automatiquement compatibles avec nos forks Vulkan, RADV et nos 83 backports : aucun SHA vendor n'est modifié dans cet audit.

## Sources et versions

| Composant | SHA actuellement figé dans `tools/deps.json` | `main` / `master` contrôlé | Différence Git |
|---|---|---|---|
| [Eden officiel](https://github.com/eden-emulator/mirror) | `5f142c7926d0` | `9580e54f2f47` | +80 commits |
| [PS5_Vulkan](https://github.com/mihawk-99/PS5_Vulkan) | `3f3ee6960701` | `252bf912a745` | +18 commits |
| [PS5_Mesa](https://github.com/mihawk-99/PS5_Mesa) | `0b2d6d1a61d9` | `47e9eb61ee7e` | **divergent : +110/−103 commits**, 110 fichiers changés |
| [PS5 native boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate) | `dd44bbdc7543` | `b8dc4a3fe2e0` | +43 commits |
| [Encore overrides](https://github.com/niakw/encore-overrides) | `4fdb329e732a` | `4fdb329e732a` | à jour |

ProsperoEden upstream n'est pas lui-même le pin du moteur de base : les sources compilées sont dérivées de `eden-emulator/mirror`, puis de nos modifications complètes vendorizées. Ne pas assimiler les arbres ni appliquer un `git pull` général.

## Correctifs à examiner en priorité

**P0 — Fidélité GPU, textures/HUD.** [Eden #4473/#4477](https://github.com/eden-emulator/mirror/commit/dbeb73ee01) sont **déjà intégrés** à Encore dans `headless/backports/eden-4473-4477.patch` et les fichiers complets de `vendor/encore-active/eden-backports` (vérifié le 12/10). Pas de nouveau port ni de correction de textures à leur attribuer. [Eden #4499](https://github.com/eden-emulator/mirror/commit/6352612425) **absent de notre fork avant R392** : R392 supprime strictement l'actualisation des buffers dans `FlushEndTFB()` mais la conserve dans `FlushBeginTFB()`. Vérifier le rendu sur console, sans gain FC27 présumé.

**P0 — HID/état des applets.** [Eden #4442](https://github.com/eden-emulator/mirror/commit/07f40d5cac) était **déjà intégré aux backports actifs** : le compteur Npad est lu dans `.state`, les notifications/focus des applets et le stub HID ont été portés. Il faut instrumenter le dernier maillon de publication Npad de notre nouveau mapping HOME/Capture R390, pas réappliquer #4442. Le freeze actif de FC27 ne lui est pas attribué.

**P1 — Saccades de collecte des textures.** [ProsperoEden 002c40c](https://github.com/blackbearreloaded/ProsperoEden/commit/002c40cb794c) précharge aussi les images mises à l'échelle avant leur éviction, avec des lots de 64 images/64 Mio plutôt que des attentes GPU par image. Notre `headless/vulkan_gc_downloads.inc` a déjà un préchargement 40 images/32 Mio, **mais exclut explicitement `image.HasScaled()`** : écart confirmé. Un port ciblé est pertinent, mais exige une vérification de la copie scaled→guest, durée de vie des staging buffers et budget RAM unifiée; ne pas élargir la limite sans qualification.

**P1 — Diagnostiquer le gel de simulation.** [ProsperoEden b59cef8](https://github.com/blackbearreloaded/ProsperoEden/commit/b59cef86fd85) mesure le délai entre réveil et reprise réelle des threads invités; [6cab789](https://github.com/blackbearreloaded/ProsperoEden/commit/6cab7898c05d) identifie le thread dans `SendSyncRequest`; [8b35097](https://github.com/blackbearreloaded/ProsperoEden/commit/8b350979303c) échantillonne ses appelants. À importer uniquement en diagnostic borné, pour distinguer boucle guest/condition variable/attente IPC sans se fonder seulement sur les FPS.

**P1 — CPU/JIT.** [ProsperoEden 376f75c](https://github.com/blackbearreloaded/ProsperoEden/commit/376f75c9dc45) préserve les accès exclusifs inlinés en mode Unsafe/Faster CPU alors que le pointeur fastmem est désactivé. Gain rapporté par upstream sur Pokémon Violet, **non transférable directement à FC27** : vérifier le mode CPU réellement utilisé et les chemins A32/A64 avant port.

**P1 — Réduire le coût de profilage.** [ProsperoEden 2e59218](https://github.com/blackbearreloaded/ProsperoEden/commit/2e59218ae21b) réserve les mesures de phases par draw aux builds de développement. À comparer aux sondes R377 et R382 déjà corrigées pour éviter d'ajouter des coûts par draw dans les builds normaux.

## Changements à ne pas importer aveuglément

- [PS5_Mesa 47e9eb6](https://github.com/mihawk-99/PS5_Mesa/commit/47e9eb61ee7e1112194557e1e047178562827bc6) et [PS5_Vulkan 252bf91](https://github.com/mihawk-99/PS5_Vulkan/commit/252bf912a745e3566a93b69b098bdc8ec4048837) rendent la détection du mode 119,88 Hz fidèle à la négociation réelle et au vblank. C'est utile pour un affichage 120 Hz compatible, **pas un déverrouillage du FPS de FC27 ni une solution automatique aux saccades à 30 FPS**. Notre PS5_Mesa diverge lourdement; pas de repin global.
- [Boilerplate b8dc4a3](https://github.com/blackbearreloaded/ps5-native-app-boilerplate/commit/b8dc4a3fe2e05e826b037bd68824751c7468a6d7) corrige la durée de vie du helper Lapy optionnel (SDK v0.42), hors chemin de rendu. À regarder si Eden utilise ce helper, pas comme correctif du match.
- [ProsperoEden 487fa34](https://github.com/blackbearreloaded/ProsperoEden/commit/487fa348265bf05e3eabc5f659efd3ba71787336) apporte la configuration de graine RNG par jeu et sa validation ; fonctionnelle, mais sans rapport direct avec FC27.
- [Eden c95ad02](https://github.com/eden-emulator/mirror/commit/c95ad020fb) corrige un hang de thread GPU **au shutdown/reset**. Ne pas confondre avec R384, où le GPU continue de rendre pendant la séquence répétitive.

## Contrat d'intégration

1. Rester exclusivement sur `dev/ps5-sparse-jit` ; commits atomiques, sans branche de travail.
2. Comparer chacun de ces correctifs avec le pinned `vendor/sources/eden`, les 83 fichiers backport et le fork `vendor/encore-active` effectivement compilé.
3. Ne modifier ni `tools/deps.json` ni l'archive immuable de vendor tant qu'un port ne reproduit pas ses tests source et ses signatures.
4. Ajouter tests hôte, équivalence générateur/fork et métriques de logs avant **un seul** build/test PS5 combiné.
5. Ne pas attribuer à un commit upstream la résolution des freezes, textures ou saccades sans essai console.

Cet audit ne lance pas de compilation PS5 et ne change aucun pin.
