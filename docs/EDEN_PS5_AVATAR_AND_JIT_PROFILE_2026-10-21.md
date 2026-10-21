# Eden Encore — avatar local et sélection CPU/JIT (21 octobre 2026)

## Avatar du compte actif

L'interface savait déjà afficher le profil, mais `profile_avatar()` n'essayait que
`avatar.png` sous un identifiant `0x%08x`. Les caches locaux peuvent exposer
seulement les variantes DDS. Le chemin reste **strictement dérivé de
`sceUserServiceGetForegroundUser`**, sans lecture d'autres profils, sans
modification de cache, sans téléchargement et sans dépendance réseau.

La recherche privilégie le PNG et essaie ensuite les variantes DDS 128, 260,
64 et 440 px. Un décodeur borné (fichier <= 4 MiB, côtés <= 512 px)
gère BC1/BC2/BC3 et RGBA/BGRA 32 bits, y compris les en-têtes DX10
correspondants. Les formats non pris en charge, les fichiers tronqués et
les erreurs de lecture conservent la silhouette neutre. Lecture et
décodage restent dans le worker existant, hors rendu/entrée de l'UI.

Le test hôte compile le vrai décodeur et vérifie quatre échantillons plus
les refus tronqué/surdimensionné. **Affichage sur PS5 non encore validé**.

## JIT sparse : audit de sélection, sans modification de comportement

- **Release actuel** : `EDEN_FINAL_RELEASE_PROFILE=ON`,
  `EDEN_SPARSE_JIT_DEV=OFF`. Dynarmic emploie des caches denses
  réservés physiquement au démarrage, suivant
  `ChooseJitMemoryPlan` et un budget limité à un quart de l'espace
  direct contigu disponible après réserve hôte.
- **DEV explicite** : `EDEN_SPARSE_JIT_DEV=ON` peut réserver une
  adresse virtuelle plus large et engager des pages au besoin.
  Le chemin teste l'alias RW/RX avant activation et accepte les
  échecs d'engagement via son traitement de défaillance.
- **Risque restant** : l'autorisation de démarrer en sparse ne
  prouve pas la sûreté de toutes les transitions de droits, de
  l'invalidation inter-cœurs et de la pression mémoire du GPU
  durant de longues sessions. Les anciennes traces de stabilité
  ne constituent pas une comparaison A/B de frametimes
  à configuration identique.
- **Décision** : ne pas basculer silencieusement le nouveau
  build release vers sparse. Garder le mode accessible par
  profil DEV séparé ; comparer percentiles 95/99,
  >50 ms, attentes fences, évacuations JIT et mémoire engagée
  avant une éventuelle promotion. Pas de nouveau fichier moteur
  à optimiser comptabilisé par ce correctif UI.

Autres options non requalifiées pour une activation globale :
placement logique des travailleurs sans topologie CPU physique
fiable, sondage de frames DEV, compilation JIT partagée,
relecture différée des écritures GPU et précompilation.
La stabilité observée lors du test `c3ac33a` (aucun crash signalé)
et les fortes saccades restent deux métriques distinctes.
