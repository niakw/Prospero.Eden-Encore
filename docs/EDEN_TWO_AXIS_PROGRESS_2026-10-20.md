# Eden Encore — tableau de bord à deux axes

**Instantané :** 20 octobre 2026 · HEAD `9d3588989f00ea13527db1ba3b2c9a88c8f1f72f`
· branche `dev/ps5-sparse-jit`.

## Deux compteurs qu'il ne faut plus confondre

- **Développement :** chemins réellement modifiés, nature des corrections et
  problème précis traité. Un diff ne prouve pas une optimisation.
- **Qualification :** preuve de source, témoin C++/ASan, prévalidation CI,
  compilation/paquet natif **au SHA du correctif**, puis exécution/mesures PS5.
  Chaque niveau reste indépendant.

Le registre comporte **478 contrats / 455 fichiers distincts**.
Les **397 fichiers SOURCE+OPEN**, dont **95 P0**, regroupant **408 contrats**
désignent une *dette de qualification*, pas 397 fichiers restant à optimiser.
Le nombre de fichiers exigeant encore un **changement de code** est **inconnu** :
on ne peut l'établir qu'à partir d'anomalies reproduites et de diagnostics.

## Axe 1 — modification du code, comparaison GitHub

Base de cette reprise : `82c531d08641d8b28124bd2cebf37fcf85674179`.

| Catégorie | Fichiers |
| --- | ---: |
| Sources C/C++/headers modifiés depuis cette base | **20** |
| Parmi eux, présents dans le graphe à 455 fichiers | **19** |
| Modifiés depuis la base et restant SOURCE/OPEN | **16** |
| Non modifiés depuis la base et restant SOURCE/OPEN | **381** |
| Modifiés depuis la base, mais uniquement contrats HOST | **3** |
| Modifié depuis la base, hors graphe connu (`src/host_memory.cpp`) | **1** |

L'absence de changement **depuis cette base** ne veut pas dire absence
d'optimisation antérieure. La présence d'un changement ne prouve pas que
le comportement corrigé fonctionne sur le matériel.

Dernier paquet natif **localement documenté** :
`7ab02797110aeb260b547d299452680fb7a56bca`.
Trois sources ont changé **après** ce paquet :

| Source | Contrats | État précis |
| --- | --- | --- |
| `vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.cpp` | H03 OPEN, H19 SOURCE | Témoins hôte ciblés, progression guest/JIT inconnue |
| `vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp` | R03 OPEN | Tick GPU hôte ciblé, contention native inconnue |
| `vendor/encore-active/eden-vulkan/vk_fence_manager_cost.cpp` | V16 HOST | Gestion des fences hôte qualifiée, GPU PS5 non mesuré |

Le paquet ancien ne vaut donc **pas compilation du HEAD actuel**.
Les actions GitHub natives `skipped` ne signifient pas `success`.

## Axe 2 — provenance des preuves des 397 chemins encore ouverts

| Références associées à leurs contrats SOURCE/OPEN | Chemins |
| --- | ---: |
| Au moins un script Python référencé et invoqué en prévalidation CI | **309** |
| Seulement un script Python non invoqué directement en CI | **16** |
| Uniquement documents, CMake, patch ou référence non exécutable | **72** |
| **Total** | **397** |

Ces groupes sont **exclusifs par chemin** ; les 11 contrats supplémentaires
sur certains chemins ne sont pas comptés deux fois. Un script invoqué en CI
peut être un vérificateur statique, non un test du comportement C++ réel.
Les **62 contrats HOST** sont des propriétés hôte limitées, **pas** des
certifications par fichier et **pas** des preuves de performance PS5.
Zéro gain FPS/gel corrigé sur console est certifié par ce registre.

## Contrat anti-boucle applicable à toutes les reprises

1. Avant un patch, consigner **l'anomalie**, la preuve/reproduction,
   le symbole et le propriétaire source réellement sélectionné. Un compteur
   SOURCE ou un gain supposé n'est pas un motif de modification.
2. Après le patch, consigner **le commit**, la propriété corrigée, le témoin
   de l'ancien défaut, le résultat hôte, le CI, la compilation native au même
   SHA et, séparément, la mesure console. Écrire `non vérifié` lorsque
   l'un de ces niveaux manque.
3. Ne pas retoucher une source récemment modifiée pour une nouvelle
   optimisation spéculative : une nouvelle défaillance reproductible,
   un échec de test ou un problème de sécurité distinct est nécessaire.
   La simple absence de mesure FPS **n'autorise pas** une nouvelle réécriture.
4. Ne jamais diminuer la dette SOURCE/OPEN pour un diff. Seule une nouvelle
   preuve répondant aux critères **limités du contrat** permet SOURCE → HOST ;
   HOST ne signifie pas clôture console.
5. Recalculer **deux axes** avant chaque bilan : code modifié depuis la base,
   code modifié depuis le dernier build natif, SOURCE/OPEN avec témoin CI,
   sans témoin direct, et validation sur matériel. Ne pas réutiliser les
   chiffres de cet instantané si le HEAD change.
6. Respecter les tests PS5 **regroupés à la fin** souhaités par le projet.
   En attendant, ne pas empiler de correctifs HLE/JIT/GPU sans preuve nouvelle ;
   rechercher d'abord la vraie cause des freezes. Ne pas désactiver
   synchronisation, fence, verrous ou JIT conservateur pour obtenir une
   simple amélioration apparente.

## Point de contrôle

Le fast gate du SHA `9d35889` était vert au dernier relevé ;
prévalidation complète et sécurité étaient encore en cours.
L'état **hardware et FPS de ce SHA** reste inconnu.
Le prochain travail substantiel n'est pas un autre compteur artificiellement
diminué, mais la **qualification native du lot courant**, puis la validation
de progression invitée → nouveau rendu → présentation, au protocole décidé.

## Lot P0 — inspection de la chaîne IPC/GPU (10 sources)

Voir [EDEN_P0_SOURCE_REVIEW_2026-10-20.md](EDEN_P0_SOURCE_REVIEW_2026-10-20.md).
Dix sources P0 ont été examinées et consignées, sans modification spéculative du moteur.
Le nouveau témoin C++ d'envoi IPC / sortie de file d'attente qualifie
uniquement des transitions hôte ciblées, pas la reprise d'exécution invitée.
Les compteurs SOURCE+OPEN restent inchangés.

## Deuxième lot P0 — Vulkan, présentation et cache textures (10 chemins)

Voir [EDEN_P0_VULKAN_REVIEW_2026-10-20.md](EDEN_P0_VULKAN_REVIEW_2026-10-20.md).
Désormais **20 chemins P0 distincts sont inscrits comme examinés dans ces
lots de revue**, sans suppression artificielle de dette de qualification.
Le triage n'a pas établi de nouvelle correction moteur sûre sans preuve native.
