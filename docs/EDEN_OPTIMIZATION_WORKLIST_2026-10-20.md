# Eden Encore — compteurs d'optimisations (≠ validation)

**20 octobre 2026 — premier lot d'optimisation dédié.**

Le registre existant recense **538 chemins C/C++ maintenus** (dont 83 hors
du graphe central à 455 chemins). Ces nombres ne correspondent ni à
538 fichiers à optimiser, ni à 397 fichiers « restants à optimiser ».
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
effectif de l'ensemble de la cartographie (538 chemins). Ce document
présente un chiffre exact et vérifiable **pour les besoins identifiés**,
et non un faux « reste = total des fichiers non validés ».
