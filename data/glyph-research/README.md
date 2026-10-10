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
| `catalog/scope-audit.json` | Contrôle du périmètre Switch 1, volume d'IDs candidats, doublons de noms et démos/cloud suspectées | Rapport indépendant, commité sur la branche |

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

## Périmètre matériel vérifié

Seuls les **jeux et logiciels ayant réellement une version Nintendo Switch 1**
entrent dans le catalogue. Les versions qui existent **sur Switch 1 et Switch 2**
restent présentes via leurs IDs Switch 1 `0100…` (par exemple Zelda BOTW).
Les exclusivités Switch 2 `0400…` (par exemple Mario Kart World) sont
exclues. La compatibilité rétroactive sur Switch 2 ne convertit pas un jeu
Switch 2 exclusif en jeu Switch 1.

Le total `24 205` initial représente **des IDs d'applications candidates**
collectés dans plusieurs régions, pas 24 205 jeux commerciaux uniques.
L'audit `scope-audit.json` explique les doublons de noms et les indices
de démos/versions cloud, sans exclure à tort des jeux Switch 1.


## Switch 1 uniquement : vérification du catalogue (10 octobre 2026)

**Ne pas interpréter le catalogue TitleDB comme une liste vérifiée de jeux
officiels.** L'audit indépendant GitHub Actions
[`#38008270773`](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38008270773)
a traité 24 205 identifiants au format application Switch 1 et retenu
**23 997 candidats non officiellement confirmés** après exclusion de
153 démos clairement nommées, 17 versions cloud et 38 titres à sortie
future. Les 95 occurrences de Title IDs Switch 2 seuls `0400…` ont
également été rejetées au moment de la lecture des sources régionales.

Cette correction est un **premier filtre de métadonnées**, pas la preuve
que 23 997 jeux Switch 1 existent : un second recoupement avec des
sources indépendantes reste nécessaire. Les estimations d'inventaires
diffèrent selon les critères de comptage (édition, régions, jeux
numériques/physiques, périodes). **Aucune limite arbitraire** n'est
utilisée.

Règle constante : un jeu ayant une édition réellement jouable sur
**Switch 1** reste inclus même s'il possède aussi une édition Switch 2 ;
les jeux **exclusivement Switch 2** ne font jamais partie du catalogue
destiné à l'émulation Switch 1. Un ancien catalogue non filtré ne
doit pas déclencher un nouveau long balayage.
