# Eden Encore — Build PS5 de test unifié, fonctions activées

**9 octobre 2026 — configuration source prête pour un essai de compilation, non encore qualifiée sur PS5.**

## Règle fondamentale

- **AUCUNE option « Expérimental » à activer dans Paramètres.** Pour le profil de test PS5, les fonctions implémentées de correction/réduction mémoire JIT sparse, placement CPU logique et télémétrie frame time sont activées directement à la compilation et au lancement, sous réserve du contrôle physique d'alias mémoire.
- Le rendu RADV/Vulkan, les patches PRMT Index/Fermi2D pris en charge, les protections mémoire, la gestion des couvertures Nlib et le mapping PlayStation Auto font partie du même binaire de test.
- Si les alias RW/RX ne passent pas le probe du firmware 13.60, le JIT sparse est désactivé avec un diagnostic et le lancement se poursuit en mode dense. **Safe Launch** contourne également les fonctions de test.
- Les anciens fichiers `experiments.json` ne sont plus consultés par le profil de test et ne peuvent pas lui désactiver les fonctions à ton insu.
- Des glyphes PlayStation **dans les jeux** exigent des textures/ROMFS originales et des packs individuels réellement qualifiés : actuellement **zéro règle graphique**. Les touches DualSense correctement mappées ne sont pas l'art dans le jeu.
- Les modes GPU non encore implémentés, le frame generation IA inexistant et les chemins JIT cross-core/compile batching indépendants non qualifiés ne deviennent pas corrects par une simple case à cocher. Ils ne sont donc pas présentés comme des capacités prêtes.

## Lancement GitHub — test natif uniquement

Workflow existant : [Build and release Prospero.Eden Encore](https://github.com/niakw/Prospero.Eden-Encore/actions/workflows/build-040-zbic.yml). Sur `dev/ps5-sparse-jit`, `workflow_dispatch` accepte :

- `test_all_on = true` : construit `tools/build-package.sh dev`, avec `EDEN_DEV_PROFILE=ON`, `EDEN_SPARSE_JIT_DEV=ON`, `EDEN_DEV_VULKAN=ON`, renderer RADV et source preflights ; produit **Prospero.Eden-Encore-PS5-all-on-test** uniquement après validation du staged app.
- `test_title_id = 0100C49025D3E000` : FC27 est l'identifiant de développement/diagnostic, **pas un autoboot implicite**. Le build de test ouvre le launcher avec le DualSense réel ; lancer FC27 ou Zelda manuellement depuis la bibliothèque. Seul `dev-settings.txt autoboot=on` demande explicitement un démarrage automatique unique. Un autre identifiant Switch 1 vérifié peut servir aux diagnostics du build suivant.
- `build_only = false` : ne jamais sauter les gates pré-compilation après modifications récentes.
- `publish = false`, `resume_run_id` vide. Le flux de test refuse toute invocation sur `fix/0.40-zbic-13.60` et n'entre jamais dans `make-dist.py` ou la publication GitHub Release.

Une alternative automatique, utilisée uniquement sur la branche de développement, est un commit déclencheur portant à la fois `[full-build]` et `[test-all-on]`. Les commits normaux `[skip ci]` ne lancent aucune compilation native. Ne pousser aucun autre commit sur la branche dev **pendant ce run**, car son groupe GitHub Actions utilise `cancel-in-progress: true`.

## Contrôles ajoutés

- `tools/check-ps5-all-on-contract.py` : refuse de laisser une configuration de test basculer silencieusement vers la release ou le dense standard ; lancé dans la validation des sources avant compilation.
- `tools/ci/check-all-on-test-binary.py` : après compilation, inspecte le CMakeCache réel, le frontend.json, le binaire de PS5, l'identifiant FC27 et l'activation effective des indicateurs de compilation. Ces données ne prouvent **pas** que l'exécutable sait utiliser les mappings du firmware.
- Nlib navigation, analyse dédupliquée des logs FC27, architecture PS5, GPU, jeux de glyphes, JIT mémoire et règle de livraison sont vérifiés par les tests hôtes préparatoires.

## Ce qu'un run vert ne prouve pas

Il reste à installer l'artefact sur PS5 FW13.60, comparer FC27 premier/deuxième lancement sans purger les caches, contrôler l'absence de `std::bad_alloc`, les mesures de frame time et Home/Library, la bonne activation sparse (probe et commit physique), les rendus PRMT/Fermi2D et les glyphes graphiques effectivement affichés. Les issues #7 et #8 ainsi que les 26 preuves de clôture matérielle restent ouverts jusqu'à ces tests.
