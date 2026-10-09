# Eden Encore · Recherche de glyphes PlayStation par jeu Switch 1

**Stockage persistant : dépôt GitHub `niakw/Prospero.Eden-Encore`, branche
`dev/ps5-sparse-jit`.** Ce dossier contient uniquement des métadonnées,
liens et preuves de correspondance. Ne pas y ajouter de ROM, clés, textures
Nintendo ni archives de mods redistribuables sans licence.

## Organisation

| Emplacement | Contenu | Persistance |
| --- | --- | --- |
| `games/01007EF00011E000.json` | BOTW : mods Switch/Wii U, scènes, mapping A=Cross et preuves manquantes | Commit Git |
| `games/<TITLE_ID>.json` | Futurs dossiers par jeu, lorsque les données sont qualifiées | Commit Git |
| `discovery/leads.json` | Liens GameBanana/ModDB/Nexus/GitHub repérés, provenance, requêtes Switch/PC | Régénéré puis commité sur cette branche par GitHub Actions |
| `discovery/progress.json` | Curseurs de recherche par Title ID, moteur et variante | Régénéré puis commité sur cette branche par GitHub Actions |
| `catalog/switch1-titles.json.gz` | Catalogue régional Switch 1 consolidé | Export gzip GitHub Actions et commit Git |
| `catalog/source-queries.json.gz` | Requêtes publiques préconstruites (Switch/PC/GameBanana/ru) | Export gzip GitHub Actions et commit Git |

Les fichiers `discovery` et `catalog` apparaissent au **premier run dont le
commit a été autorisé**. Si le jeton Actions n'a pas le droit d'écrire, si la
branche a bougé, ou si le serveur refuse les requêtes, un avertissement est
émis et les résultats restent en artefacts GitHub Actions, qui ne sont
**pas** un stockage définitif. Ne jamais annoncer un commit sans le vérifier.

## Différence entre candidat et jeu fonctionnel

Un lien de mod et les positions d'interface d'une édition PC/Wii U ne
constituent pas un atlas Switch activable. Les données de ressources vérifiées
incluent `original SHA-256`, `game update`, `romfs_path`,
`texture_name`, `slot rect_xywh`, `guest action vs spatial button`.
Les champs `null` du fichier BOTW indiquent exactement les preuves non
encore produites.

Les scripts `tools/ps-glyph-*` exécutent les adaptations techniques ;
`docs/PS_GLYPH_SOURCE_INDEX.json` et
`docs/PS_GLYPH_CROSS_PLATFORM_INDEX.json` restent les indices de sources
historiques. L'approbation des données n'active aucun pack dans l'émulateur.

## Recherches publiques HTTP vs vrai navigateur

`curl` avec User-Agent Firefox est le chemin léger par défaut, mais ne
devient pas pour autant un navigateur Firefox. Playwright Firefox peut être
choisi explicitement lorsqu'une page exige un rendu JavaScript. Aucun de ces
clients ne contourne CAPTCHA, authentification, 403 ou limitation de débit.
Yandex via ses pages de recherche publiques ne nécessite pas une API payante ;
l'API Search officielle est une voie **distincte** et uniquement sur
activation avec ses clés et sa facturation éventuelle.
