# Eden Encore — vérification systématique des contrats cartographiés

**Date :** 19 octobre 2026 · **Branche :** `dev/ps5-sparse-jit`

## Objectif et limite vérifiable

La cartographie actuelle compte **478 contrats**, **455 chemins de
sources distincts**, **959 ancres de symbole**. Chacun est contrôlé par
`tools/check-eden-audit-register.py` et
`tools/check-eden-audit-verification-matrix.py`. Le premier vérifie
l'existence et les ancres de fonctions, les dépendances et l'absence de
cycles. Le second produit une **fiche explicite pour chaque contrat**
avec propriétaire, priorité, état, lien de preuve, exécution directe en
CI, dépendances suspendues et absence de qualification matérielle.

**Exporter les 478 fiches :**

```bash
python3 -B tools/check-eden-audit-verification-matrix.py --json > /tmp/encore-audit-verification.json
```

L'export est généré à partir du registre : aucune seconde liste
d'améliorations « terminées » n'est maintenue manuellement. Le
contrôle échoue si un fichier, symbole, lien de catalogue actif ou
preuve `HOST` invoquée en CI disparaît.

## État courant vérifié (20 octobre 2026)

| État | Contrats | Preuve acquise |
|---|---:|---|
| HOST | 59 | Invariant précis sur hôte ; **pas** de jeu sur console |
| SOURCE | 396 | Source étudiée, comportement natif non qualifié |
| OPEN | 15 | Question de comportement/propriété non résolue |
| PARKED | 8 | Expérimentation suspendue, ne pas activer |
| **Total** | **478** | **0 certification de gain de FPS par ce registre** |

**400 chemins distincts SOURCE + OPEN** (dont **98 chemins P0** et
**281 dans `vendor/encore-active`**) correspondent à **411 critères SOURCE + OPEN**, dont **103 P0**, ont encore besoin
d'une qualification supplémentaire. Leur présence n'invalide pas les
corrections hôte : elle interdit seulement d'affirmer que leurs
performances ou leur effet sur les freezes sont démontrés.

Sur les **399 références à un script Python** parmi les preuves des
contrats, **383 sont appelées directement** par la prévalidation et
**16 ne le sont pas directement** (15 SOURCE et 1 OPEN). Les 16
références correspondent à quatre chemins distincts :

- `tools/install-vendored-radv.py` : **12** références à un
  *installateur d'entrées compilateur*, contrôlé séparément par les
  empreintes RADV et son vérificateur de fork. **Ne pas exécuter sans
  destination Meson jetable.**
- `tools/check-jit-protection.py` : **2** références à un
  banc fondé sur les fichiers générés dans
  `.local/headless-cache`, absents d'une prévalidation hôte
  vierge. Nécessite un build de préparation identifié.
- `tools/check-jit-allocator.py` : **1** référence, avec
  même dépendance à l'arbre de compilation généré et tests
  d'alias mémoire.
- `tools/check-ps5-sparse-jit-va-lifetime.py` : **1** référence
  à un témoin de politique JIT expérimental. Son en-tête le
  désigne comme *staged only*, non comme une validation native ;
  ne pas confondre sa réussite éventuelle avec une preuve de
  mémoire physique disponible ou de fluidité.

Le témoin de provenance `tools/install-vendored-surface-lifecycle.py
--check` est désormais directement exécuté et a réussi sur la CI
[39316703898](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39316703898).

Les **79 autres références** pointent vers des documents, recettes
CMake, patches ou autres fichiers non exécutables : existence et
ancres documentaires ne constituent **pas** un benchmark.

## Fermeture des chemins de performance

Le pipeline doit rester réparti entre les familles **J** (JIT/CPU),
**H** (HLE/scheduler), **M** (mémoire invitée), **V** (Vulkan),
**R** (pilote RADV), **N** (GPU/NVDRV), **S** (progrès jeu/frames),
**A** (audio), **F** (fichiers/IPC), **Q** (durée de vie/arrêt),
ainsi que construction, ressources, réseau et entêtes applicatifs.

Chaque contrat P0 encore SOURCE ou OPEN représente une qualification
en attente, pas automatiquement un défaut à corriger. Un changement
dans une fonction partagée est acceptable si :

1. Le **chemin C++ réellement sélectionné** et ses propriétaires
   sont prouvés pour le profil natif concerné.
2. Le symptôme est relié à une observation précise, et une
   hypothèse de contention, de mémoire, de JIT ou de progression
   n'est pas présentée comme une causalité prouvée.
3. Un témoin du *comportement original* et un test ciblé de la
   correction existent (ASan/UBSan et cas de défaut si utile).
4. Le contrôle hôte entier, la sécurité C/C++ et un paquet natif
   au **même SHA** sont contrôlés. Le build n'est jamais déduit
   d'une simple copie vers `encore-active`.
5. La PS5 démontre dans une scène identique la progression des
   threads/du contenu et le p50/p95/p99 en temps de frame,
   les intervalles >50/>100/>500 ms, l'absence de gel et
   l'intégrité HUD/textures. Un affichage stable à 30 FPS ne
   prouve pas que le match progresse.

L'audit de complétude automatisé **ne peut pas prouver** qu'il
n'existe aucune optimisation possible, ni que tous les codes
C++ externes hors du périmètre inventorié sont couverts.
Il garantit que **chaque contrat déjà cartographié reste traçable,
que ses inconnues sont visibles, et qu'aucune preuve source ne
peut être convertie implicitement en preuve matérielle**.

Les branches de thèmes/launcher et les fonctions de rendu UX sont
hors modifications de cette passe ; les options post-store
différées, affinités SMT non vérifiées et JIT expérimental
restent désactivées.

## 20 octobre — clôture des propriétés d'intégration hôte

12 contrats P1 des sources maintenues (heap, JIT W^X, émetteurs A32/A64 et unités de mémoire) passent de SOURCE à HOST avec leurs tests déjà sélectionnés dans la CI. Le statut qualifie uniquement parité/compilation/staging. Le compteur de sources à qualifier devient **411** (auparavant 423), et les **109 P0** sont inchangés. Aucun contrat n'est requalifié comme amélioration FPS ni preuve de runtime console.

## 20 octobre — qualification ciblée des attentes GPU (deux P0)

Les contrats `Q07` (file SPSC/stop token) et `V02` (présentation
Vulkan) ont des témoins hôte directement invoqués par la CI et des
critères limités à leurs mécanismes vérifiés. `V02` contrôle désormais
le source maintenu natif, et non seulement le générateur, en supprimant
une assertion toujours vraie. Le passage SOURCE → HOST concerne la
relecture/recyclage de slots et le déverrouillage/protocole d'attente ;
l'effet sur les blocages du jeu et le temps de frame PS5 reste inconnu.
Les décomptes courants sont 410 fichiers encore à qualifier, dont 108
en priorité P0. Le total de chemins reste à 455 et celui des contrats
à 478 : aucun chemin n'a été effacé du graphe.

## 20 octobre — dossier SPSC qualifié

Les deux contrats `Q02` et `V72`, auparavant SOURCE, sont désormais
HOST pour la propriété de file et de réveil déjà démontrée dans
`check-native-gpu-queue-stop-fastpath-host.py`. Le registre contient
**421 critères SOURCE + OPEN sur 409 fichiers, dont 107 P0**.
La validation console et les gains de FPS restent à produire.

## 20 octobre — lot unique Vulkan

`V01` devient HOST pour la propriété hôte de drain/échec du
worker. Le registre compte désormais **408 fichiers restants,
dont 106 P0**. Dans une autre unité Vulkan, les tailles et offsets
de binding mémoire multi-plages sont contrôlés avant création des
objets Vulkan, avec test ASan/UBSan et génération reproductible.
Pas de gain FPS sur PS5 revendiqué.

## 20 octobre — JIT sparse et preuve d'allocation hôte

Le contrat `J05` passe à HOST pour la propriété de dimensionnement de
`PlanSparseCommit` exécutée dans le mock natif complet. Les compteurs
passent à **407 chemins restant à qualifier**, dont **106 P0**,
et **419 contrats SOURCE + OPEN**. La preuve ne certifie ni
les FPS ni le comportement physique console.

## 20 octobre — sparse decommit qualifié sur hôte

La source `J34` possède maintenant deux témoins C++ réellement exécutés
dans le fast gate pour les bornes et la libération de slot, et le contrôle
de parité en prévalidation. `J34` passe HOST pour cette propriété, pas
pour l'exécution réelle sur PS5. Restent **406 fichiers à qualifier
dont 105 P0**, soit **418 contrats SOURCE + OPEN**.
Le scan par mots limite les chargements de bitmap ; aucun chiffre de FPS
n'a été mesuré sur console.

## 20 octobre — validation ciblée JIT A32/A64

J19 et J20 sont HOST pour la méthode native de demande d'invalidation,
extraite et compilée avec ASan/UBSan. Restent **404 fichiers**
(dont **103 P0**) et **416 contrats** : aucun gain console certifié.

## 20 octobre — qualification ciblée J16

La diffusion hôte des invalidations I-cache entre interfaces CPU est
prouvée par `tools/check-native-jit-icache-broadcast-host.py`; **404 fichiers** restent à
qualifier dont **102 P0**, représentant **415 contrats**.

## 20 octobre — condition de compilation partagée V40

V40 dispose désormais d'un témoin source-extrait C++ hôte pour
les conditions partagées. **403 fichiers** restent à
qualifier (dont **101 P0**) sur **414 contrats**.

## Qualification P0 du ring de descripteurs (20 octobre)

`V17` et `V33` réutilisent deux témoins C++ ASan/UBSan déjà exécutés
par la prévalidation, sans compiler un autre modèle. Ils qualifient
la prévalidation et les générations du ring ; le repli `Finish` sous
verrous subsiste. Aucune amélioration FPS sur PS5 démontrée.

**401 fichiers** encore à qualifier, dont **99 P0**
(**412 contrats**).

## 20 octobre — retrait des buffers Vulkan multi-plages

`V20` est qualifié HOST pour la possession des buffers gathered/sparse,
l'invalidation des entrées dont l'entrée propriétaire disparaît et la
libération différée en fonction du tick achevé. Le test
`tools/check-vulkan-multirange-owner-lifetime-host.py` compile `RetireEntry`, `DrainRetired`,
`DropOwner` et `Invalidate` réels sous ASan/UBSan, y compris
le repli gathered et 300 cycles avec capacité MAX_RETIRED=256.
**Les attentes réelles du GPU ne sont pas mesurées sur PS5.**
Restent 400 fichiers, dont 98 P0, et 411 contrats.
