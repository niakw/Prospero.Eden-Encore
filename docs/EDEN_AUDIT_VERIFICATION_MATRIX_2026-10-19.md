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

## État initial vérifié

| État | Contrats | Preuve acquise |
|---|---:|---|
| HOST | 45 | Invariant précis sur hôte ; **pas** de jeu sur console |
| SOURCE | 410 | Source étudiée, comportement natif non qualifié |
| OPEN | 15 | Question de comportement/propriété non résolue |
| PARKED | 8 | Expérimentation suspendue, ne pas activer |
| **Total** | **478** | **0 certification de gain de FPS par ce registre** |

**411 chemins distincts SOURCE + OPEN** (dont **109 chemins P0** et
**291 dans `vendor/encore-active`**) correspondent à **425 critères SOURCE + OPEN**, dont **115 P0**, ont encore besoin
d'une qualification supplémentaire. Leur présence n'invalide pas les
corrections hôte : elle interdit seulement d'affirmer que leurs
performances ou leur effet sur les freezes sont démontrés.

Sur les **391 références à un script Python** parmi les preuves des
contrats, **374 sont appelées directement** par la prévalidation et
**17 ne le sont pas directement** (16 SOURCE et 1 OPEN). Les 17
références correspondent à cinq chemins distincts :

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
- `tools/check-gpu-producer-stop.py` : **1** référence au
  producteur GPU généré, avec la même contrainte de staging.
- `tools/check-ps5-sparse-jit-va-lifetime.py` : **1** référence
  à un témoin de politique JIT expérimental. Son en-tête le
  désigne comme *staged only*, non comme une validation native ;
  ne pas confondre sa réussite éventuelle avec une preuve de
  mémoire physique disponible ou de fluidité.

Le témoin de provenance `tools/install-vendored-surface-lifecycle.py
--check` est désormais directement exécuté et a réussi sur la CI
[39316703898](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39316703898).

Les **87 autres références** pointent vers des documents, recettes
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
