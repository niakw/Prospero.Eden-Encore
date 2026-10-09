# Eden Encore — Clôture complète PS5, FC27, JIT sparse, GPU et glyphes

**État au 9 octobre 2026 : NON TERMINÉ.** Développement : \`dev/ps5-sparse-jit\`; livraison protégée : \`fix/0.40-zbic-13.60\`. Maquette violette approuvée à préserver. Après accord explicite de l'utilisateur pour un **run de test toutes fonctions activées**, un build isolé sur `dev/ps5-sparse-jit` est permis, sans publication ni modification de la branche de livraison. Cela ne constitue pas une qualification matérielle.

Cette page et [PS5_CLOSURE_MATRIX.json](PS5_CLOSURE_MATRIX.json) couvrent **26 preuves nécessaires réparties en cinq axes**. Le contrôle local \`python3 tools/check-ps5-closure.py --require-ready\` **doit refuser la clôture** tant que des éléments manquent. Ce vérificateur ne lance aucune tâche GitHub et ne valide pas lui-même l'authenticité d'une preuve matérielle : une revue humaine des captures/logs, droits et conditions est obligatoire.

## 1. FC27 et navigation de la bibliothèque (issue #8)

**Fait :** de vraies mesures de 5 s ont présenté 18–27 FPS et des frames retardées de ~100–496 ms, malgré un compteur fixe perçu de 30 FPS. Deuxième lancement avec cache similaire. Navigation maintenue vers le bas : hitches d'UI observés à 122 et 175 ms. La console ne chauffant pas beaucoup ne prouve ni sous-exploitation CPU/GPU ni absence de limites. Anciens marqueurs de topologie CPU « non confirmée » n'indiquent pas cinq workers sur un seul cœur.

**Source déjà modifiée :** décompression/réduction des couvertures Nlib sur worker, maintien de l'upload GL sur le thread principal ; contexte PlayStation Auto collant après passage en match pour empêcher D-pad, Options ou popup de renverser la disposition pendant le match. Le retour réel au menu principal du jeu ne peut pas être détecté universellement à partir des touches.

**Clôture :** démarrage/reprise répétée de FC27 sur FW13.60, première et deuxième sessions du même match, distribution des frame times (dont p95/p99), CPU/GPU/VRAM et shaders/chargements, absence de crash \`std::bad_alloc\` après plusieurs minutes et pression mémoire, vérification du défilement bibliothèque/Home, test de la manette entre match, pause, overlays et véritable menu. Aucun gain de FPS imaginé sans comparaisons mesurées.

## 2. JIT sparse + Dynarmic A64/A32, quatre cœurs invités (issue #8)

**Fait :** banc hôte/CI a démontré 64 Mio réservés virtuellement, 4 Mio physiques engagés au démarrage, croissance à 10 Mio puis désallocation. Le dernier build distribué pour essai utilisait **dense quarter-pool** (allocation physique initiale réduite), **PAS** sparse en livraison.

**Clôture :** vrai build SDK PS5 avec \`EDEN_SPARSE_JIT_DEV\` en configuration strictement expérimentale, vérification firmware 13.60 des alias RX/RW, protections exécutables et flush de code ; bootstrap par quatre cœurs/A64/A32, commit 2 Mio à la demande, fragmentation/rollback/unmap, comparaison de consommation physique avant/après plusieurs jeux. Ne pas activer sparse par défaut ni perturber le fallback tant qu'il n'est pas qualifié.

## 3. GPU Vulkan et compatibilités (issue #8)

**Fait :** le patch natif \`headless/gpu_native_observability.cmake\` contient le traitement de PRMT immediate/register en mode Index, et certains chemins software Fermi2D profondeur z=0/pitch-linear. Les autres modes PRMT, certaines couches 3D/block-linear et les risques de synchronisation pipeline restent hors qualification.

**Clôture :** compiler/lier le code GPU généré au SDK exact, comparer les pixels de shaders PRMT à une référence, contrôler les copies Fermi2D par formats/profondeurs/couches et leurs limites, préserver le comportement d'erreur/soft assert lorsque l'instruction n'est pas implémentée, mesurer files d'attente/sync et frame times sur FC27 + un autre jeu. Aucun masquage des logs pour faire disparaître un défaut de rendu.

## 4. Glyphes PlayStation **dans les jeux** (issue #7)

**Fait :** le mapping d'entrée DualSense n'est pas le dessin des glyphes Nintendo. \`headless/glyph_overrides_generated.h\` contient actuellement **zéro règle qualifiée** ; FC27 logge \`Nintendo original (rule=unsupported)\`. Recherche : 28 jeux Switch 1, 26 références de mods Switch pour 18 titres et 22 sources multiplateformes pour 16 titres ; les 34 coordonnées publiques DST sont des **positions de libellés d'UI Lua**, pas les XYWH des textures Nintendo.

**Clôture :** obtenir légalement les vrais fichiers d'atlas d'au moins FC27 et un second jeu, valider les Title IDs/versions actives + SHA-256 du vrai RomFS après updates, formats BNTX/BLARC/Unity/CPK si nécessaires, édition/réimport réversible, droits de distribution, visuels Croix/Rond/Carré/Triangle selon le menu/match/HUD/tuto, vérification de livraison de packs versionnés avec authenticité et repli sans écraser les mods du joueur. **Ne pas déclarer universel** un mécanisme graphique dépendant du jeu.

## 5. Native/release/UX intégrité

**Dernière native identifiée :** [#37853342541](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/37853342541) — compilation achevée mais **échec au contrôle \`Validate freshly built staged app\`** pour une ancienne attente de log \`EDEN_PAD_CONTEXT mode=ui\` ; le checker source a été modifié ensuite. **Aucun nouveau build natif ne valide ce changement.**

La compilation du vrai SDK et le redémarrage/fermeture/re-lancement sur firmware 13.60, régression Home/Library et contrôles légaux ne doivent être entrepris **qu'après feu vert explicite**. Garder intacte la branche \`fix/0.40-zbic-13.60\` pendant les essais et conserver le design adopté.

## Règle de fermeture

Les issues [#7](https://github.com/niakw/Prospero.Eden-Encore/issues/7) et [#8](https://github.com/niakw/Prospero.Eden-Encore/issues/8) doivent rester **ouvertes** jusqu'à ce que les 26 vérifications aient de véritables preuves examinées et que la nouvelle version passe le firmware et des jeux réels. Des tests source/CI verts n'équivalent pas à une preuve PS5. Le lien d'un ancien run et l'existence de fichiers de mod ne suffisent pas. Ne jamais fermer administrativement pour satisfaire une demande de suivi sans corriger et qualifier le problème.

## Mise à jour : test unifié tout activé

Le profil de test est décrit dans [PS5_ALL_ON_TEST_BUILD.md](PS5_ALL_ON_TEST_BUILD.md). Le build dev active automatiquement JIT sparse (sous probe RW/RX), placement CPU logique et trace Vulkan sans bascule expérimentale dans les paramètres. Il ignore l'ancien `experiments.json` ; Safe Launch et les protections contre les GPU/JIT non pris en charge restent en place. Les 26 critères physiques sont toujours nécessaires avant de considérer FC27, GPU, JIT sparse et glyphes PlayStation comme terminés.
