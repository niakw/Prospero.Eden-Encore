# Eden Encore — provenance des sous-dépendances et vérification du vault

**20 octobre 2026 · branche dev/ps5-sparse-jit.**

Le code directement maintenu compte **491 fichiers C/C++**, dont les sources
`vendor/encore-active` (catalogue exact de **319 unités/en-têtes**). Les
sources amont originales sous `vendor/sources` et les archives découpées
dans `vendor/objects` restent volontairement distinctes des correctifs
Encore. Le graphe répertorie aussi **36 sources Eden épinglées**, dont
certaines servent uniquement à comparer les implémentations maintenues.

`tools/deps.json` référence **22 entrées épinglées** :
**15 dépôts Git**, **6 archives** et **1 lot de fichiers individuels**.
En complément, `tools/vendor-eden-cpm.py` conserve les **22 paquets CPM**
avec leurs empreintes ; le constructeur RADV relie son archive aux
empreintes des **12 unités compilées** de `vendor/encore-active/ps5-mesa`.
`tools/check-vendor-consolidation-debt.py` interdit toute réintroduction
d'un générateur de transformations C++ non documenté dans le CMake
principal ; le seul `write_derived` maintenu vise une ressource GLSL.

## Renforcement vérifiable

Les archives du vault étaient contrôlées contre leurs chunks et la
somme SHA256 inscrite dans le même vault. Le vérificateur contrôle
maintenant en supplément le **hash indépendant de `tools/deps.json`**,
pour les cinq archives SHA256 et pour FFmpeg, épinglé en SHA512.
Un contenu et un `chunks.json` qui sont cohérents entre eux, mais
diffèrent du manifeste des dépendances, ne sont plus acceptés.

`tools/check-vendor-archive-pin-contract-host.py` exécute
`assert_blob` extrait du vrai vérificateur sur des témoins artificiels
(archive correcte, mauvais SHA256, mauvais SHA512, vault
autocohérent falsifié, chunk corrompu). Le contrôle rapide prouve ce
protocole sans reconstruire les centaines de Mio du vault.
La prévalidation complète vérifie indépendamment les vraies archives,
les Git bundles et la réhydratation hors réseau.

**Attention :** contrôle de provenance, pas gain CPU/GPU ni preuve que
toute sous-dépendance est *copiée* dans `encore-active`.
Il reste **389 fichiers de code à traiter pour l'optimisation**
sur 491, distinctement des validations encore dues.
