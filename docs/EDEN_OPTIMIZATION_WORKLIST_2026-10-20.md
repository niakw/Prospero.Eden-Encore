# Eden Encore — compteurs d'optimisations (≠ validation)

**20 octobre 2026 — premier lot d'optimisation dédié.**

Le registre existant recense **538 chemins inventoriés** (491 fichiers de code directement maintenus, plus 47 chemins épinglés hors du périmètre des corrections directes ; 83 des fichiers maintenus sont hors du graphe central). Ces nombres ne correspondent ni à
491 fichiers à optimiser, ni à 397 fichiers « restants à optimiser ».
Les 397 en attente sont une *dette de preuve*.

## Comptage explicite des corrections de code

Ne compter comme **reste à optimiser identifié** que les fichiers pour
lesquels un **coût évitable réel a été localisé dans le code** et pour lesquels
un changement précis est possible. La preuve hôte est conservée à part.
Un défaut de gameplay dont le propriétaire exact est inconnu
n'autorise **pas** de multiplier arbitrairement le nombre de fichiers.

| Lot | Chemins identifiés à modifier | Chemins corrigés par ce lot | Restants dans ce lot |
| --- | ---: | ---: | ---: |
| Publication du fence du worker GPU (deux variantes natives) | **2** | **2** | **0** |

### Les deux corrections

- `vendor/encore-active/eden-gpu/gpu_thread_quiet.cpp`
- `vendor/encore-active/eden-gpu/gpu_thread_dev.cpp`

Dans `ThreadManager::RunWorker`, chaque commande GPU terminée écrivait
son numéro de fence au moyen d'un `atomic::store` implicite
`memory_order_seq_cst`. Or les consommateurs existants lisent le numéro
avec `memory_order_acquire`. Un store `memory_order_release`
assure la publication de tous les effets de commande antérieurs
vers ces lectures sans imposer l'ordre global `seq_cst` :
sur une architecture x86, cela peut éviter une opération de
synchronisation globale coûteuse sur le chemin fréquent des commandes.

Le worker ne change ni l'ordre FIFO, ni le numéro de fence, ni les waits,
ni les notifications `condition_variable_any`, ni le stop/restart.
**Ce n'est pas** une démonstration d'augmentation FPS ou de guérison du gel.

`tools/check-native-gpu-fence-release-publication-host.py` compile les
fragments C++ réels de publication des deux variantes plus la
publication upstream en contrôle. 32 768 commandes sont consommées par
un thread indépendant sous ASan/UBSan, en vérifiant l'ordre et
la visibilité des écritures associées au numéro publié.
La comparaison historique `tools/check-native-gpu-thread.py` est
normalisée spécifiquement pour cette amélioration, sans réduire ses
autres assertions de parité.

**À ne pas tromper :** le nombre *global* de fichiers où une future
optimisation s'avérera nécessaire est **encore inconnu** sans examen
effectif de l'ensemble de la cartographie (491 chemins maintenus ; 538 avec les chemins épinglés). Ce document
présente un chiffre exact et vérifiable **pour les besoins identifiés**,
et non un faux « reste = total des fichiers non validés ».

## Couverture d'optimisation de code — compteur principal de traitement

Au HEAD `05846723c` (optimisation GPU `db6b6a6` et réparation CI `0584672`), l'inventaire versionné `tools/audit-cloud-worklist.py` recense **491 sources/en-têtes maintenus** (et 47 chemins épinglés additionnels, soit 538 inventoriés) sous `headless/`, `src/`, `vendor/encore-active/`. Par comparaison GitHub avec `82c531d08` : **23 chemins de code réellement modifiés**, sans prétendre qu'ils sont tous des gains de performance. Les revues P0 antérieures ajoutent **12 chemins actifs examinés sans modification** (13 chemins recensés, dont un recouvert par les 23), et la nouvelle [revue de six chemins GPU/Mesa](EDEN_OPTIMIZATION_REVIEW_MESA_VULKAN_2026-10-20.md) ajoute **6 chemins sans nouveau correctif**.

**Couverture effective : 41 fichiers de code traités/examinés ; reste à traiter dans le chantier d'optimisation : 450 fichiers (491 − 41).**

Cette mesure est un **compteur de travail d'optimisation**, pas de validation. Chaque nouveau fichier analysé pour ses points chauds ou corrigé une seule fois doit être ajouté au [manifeste des propriétaires](EDEN_OPTIMIZATION_COVERAGE_2026-10-20.json) : il fait alors baisser le compteur même s'il ne nécessite pas de patch. Cela évite de fabriquer des optimisations inutiles simplement pour faire diminuer un chiffre. Le nombre de fichiers qui **nécessitent impérativement un changement C++** reste inconnu jusqu'à leur diagnostic. Contrôle CI : `python3 -B tools/check-eden-optimization-coverage.py`.

## Accélération — sources déjà couvertes par des travaux antérieurs

**Lot du 20 octobre — sans nouveau patch moteur.** L'inventaire a recoupé
le manifeste de 41 chemins avec le registre central. **61 chemins distincts**
supplémentaires de `vendor/encore-active` disposent d'une attribution
historique explicite : **35** contrats `HOST` ciblés (tests/parité
ou propriétés précises) et **26** unités sources complètes déjà
maintenues, backportées ou sélectionnées (`SOURCE`; niveau de preuve
hôte et console non nécessairement atteint).

Ces 61 chemins n'ont **pas** été déclarés « FPS optimisé ».
Ils ont été retirés de la **première analyse de code à refaire**,
parce que leur propriétaire, leur intervention passée et une référence
de preuve sont déjà consignés. Tout nouveau défaut documenté rouvrira
le chemin pertinent sans cacher le problème.

| Comptage optimisation de code | Précédent | Maintenant |
| --- | ---: | ---: |
| Sources/en-têtes maintenus directement par Encore | 491 | 491 |
| Déjà modifiés ou examinés dans la passe récente | 41 | 41 |
| Revus par réception hôte existante | 0 | **35** |
| Revus par source déjà intégrée avec justificatif | 0 | **26** |
| **Restent à traiter dans la passe** | **450** | **389** |

**Ce nombre 389 n'est pas le nombre de correctifs nouveaux prouvés
nécessaires.** Le registre de qualification SOURCE/OPEN n'a pas changé.
Le contrôle CI exige que chacun de ces 61 chemins conserve son ID,
son statut et sa référence de preuve historique dans
`docs/EDEN_CORE_AUDIT_DEPENDENCIES.md`.
Le nombre de nouvelles modifications de code obligatoires demeure
inconnu avant diagnostic des sources non traitées.
