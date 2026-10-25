# Eden Encore — reste à faire pour FC27 (critères de sortie)


## État officiel — F05 clôturé techniquement, 5/6 (25 octobre 2026)

**Révision de référence du code : [771afa2](https://github.com/niakw/Prospero.Eden-Encore/commit/771afa2fa535bed0e436f333cafba3c092735fac)**,
branche unique **dev/ps5-sparse-jit**. Les quatre workflows du SHA sont réussis :

- [Fast gate #40229853881](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40229853881) : **SUCCESS**.
- [Prévalidation #40229853920](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40229853920) : **SUCCESS**, checkpoint : **f01_to_f06_closed=5**, **host_subpaths_passed=35/35** et **F05-guest-progress=true**.
- [Build/package natif PS5 #40229853892](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40229853892) : **SUCCESS**.
- [CodeQL #40229853921](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40229853921) : **SUCCESS**.

**F05 clos pour le contrat technique pré-console, pas pour la progression du jeu réel.**
Le nouveau test intégré construit et lie cinq unités de translation C++.
Avant chaque transfert Binder → BufferQueue → HardwareComposer → NvDisp →
Host1x → PresentManager, il impose une libération de buffer valide suivie
de la chaîne native sélectionnée ProducerReleaseWake → KEvent →
KThread::NotifyAvailable → KThreadQueue::EndWait. Une libération périmée
ou répétée ne doit pas réveiller un thread supplémentaire.

Le témoin **F05_NATIVE_RELEASE_KTHREAD_TO_PRESENT_BOUNDARY_PASS**
a validé **260 libérations**, **520 reprises simulées** et **260 images
transmises dans l'ordre** sous **-O0** et **-O2**. Les **14 sous-chemins
hôte F05** et les **35 sous-tests globaux** sont tous réussis.

**Limites :** l'ordonnanceur invité, les paquets HIPC du jeu, la CPU invitée,
le GPU/Vulkan réel et l'affichage PS5 sont simulés ou exclus du scénario.
Ce résultat ne démontre ni un gain de FPS, ni l'absence de freeze sur FC27.
Les mesures PS5 appartiennent au critère de qualification matérielle **F07**.

**Compteur : F01 validé · F02 validé · F03 validé · F04 validé · F05 validé ·
F06 ouvert = 5/6.** F06 reste intact (commandes non modifiées), suivant
les retours de la console ; les preuves de son critère technique complet
restent distinctes. Aucun nouveau test console n'est demandé à cette étape.

**Historique :** les sections suivantes sont les journaux des anciens
jalons et de l'ancien compteur **4/6**. Le checkpoint du SHA **771afa2**
fait foi pour le statut actuel.

---


## F05 — dernier témoin d'intégration (25 octobre 2026)

**Base technique confirmée :** `3347144` a réussi le fast gate
[#40222417431](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40222417431),
la prévalidation
[#40222417439](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40222417439),
le build PS5
[#40222417453](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40222417453)
et CodeQL
[#40222417560](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40222417560).

**Lot ajouté, CI en cours :** les révisions `8a7bbec`, `2023ce3`
et `451d4c8` étendent `check-fc27-f05-native-kthread-endwait-host.py`
avec une exécution C++ continue de
`BufferQueueConsumer::ReleaseBuffer` →
`ProducerReleaseWake::OnBufferReleased` →
`KEvent::Signal` → `KReadableEvent::Signal` →
`KThread::NotifyAvailable` → `KThreadQueue::EndWait`.
Le scénario rejoue 260 libérations réelles dans un noyau **mocké**,
rejette les frames périmées et les libérations répétées sans réveil
supplémentaire, vérifie 520 reprises simulées, 260 signaux de la condition
hôte et le retour des deux attentes à l'état exécutable.
Le checkpoint F01–F06 exige explicitement les sorties
`F05_NATIVE_RELEASE_TO_KTHREAD_PASS` sous `-O0` et `-O2` ;
cette preuve est **non acquise tant que la nouvelle CI n'est pas verte**.

**Limite :** un rejeu natif source-extrait avec noyau simulé ne prouve
ni le véritable décodage HIPC invité, ni la progression des threads PS5,
ni la disparition du gel de FC27. Le compteur **reste à 4/6**,
F05 ouvert, F06 préservé selon les essais console déjà communiqués.

---


## F05 — verrouillage producteur / noyau invité (25 octobre, nouveau lot)

**Correctif moteur à qualifier par la CI du HEAD :** tous les huit sites
`buffer_wait_event->Signal(service_context.kernel)` dans
`BufferQueueProducer` sont désormais émis **après** la sortie de
`core->mutex`. Les mutations de slots et le réveil hôte
`SignalDequeueCondition` restent dans la section critique, tandis que
`KEvent::Signal`, susceptible de prendre le verrou de l'ordonnanceur invité,
n'y entre plus. Le cas zéro de `SetBufferCount` utilise un déverrouillage
explicite avant retour ; `Disconnect` ne publie l'événement qu'après une
déconnexion réussie.

- Sources : `66be480` (remplacement de frame), `ae4b068` (tous les autres
  chemins de transition).
- Provenance : `dff582d`, parité exacte du producteur maintenu avec les
  ajouts F05 contrôlés.
- Tests : `c96b555` (rejeu remplacement), `4deadd0` (verrouillage pour
  tous les chemins), `d4fe63c` (assertion mise à jour).
- Témoin de verrouillage natif renforcé : `8268dfd` vérifie l'accès au
  mutex depuis un second thread lors du signal Binder des détachements et
  des changements du nombre de buffers ; `9a36bf2` exécute aussi
  `CancelBuffer`. `3347144` autorise la fin d'un autre dequeuer qui
  reprend légitimement le mutex, pour ne pas interpréter cette concurrence
  normale comme une inversion des verrous. Les méthodes exécutées restent
  celles du code C++ maintenu, avec état de noyau simulé.
- Révision complète de référence : `d4fe63c`, **les quatre workflows
  réussis**, dont le build PS5. Dernier test ajouté : `3347144`,
  **nouvelle CI en cours** (fast gate #40222417431,
  prévalidation #40222417439, build PS5 #40222417453,
  CodeQL #40222417560).
- CI à confirmer : fast gate [#40212403986](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40212403986),
  prévalidation [#40212403950](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40212403950),
  build PS5 [#40212403951](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40212403951),
  CodeQL [#40212403982](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40212403982).

**Compteur F01–F06 : 4/6** (F01–F04 clos techniquement ; F05 et F06
ouverts). Le fonctionnement F06 ayant été jugé satisfaisant en console,
aucun changement du chemin des commandes. La disparition des gel/ralentissements
de FC27 n'est pas démontrée par ces tests de source, même avec un build vert.

---


## Dernier état contrôlé — F05

**Base techniquement verte :** `e2eecc6` a réussi le fast gate
[#40165760771](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40165760771),
la prévalidation hôte complète
[#40165760815](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40165760815)
(34 sous-chemins sur 34), le build PS5
[#40165760784](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40165760784)
(`eboot.elf` produit, paquet contrôlé), et CodeQL
[#40165760785](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40165760785).
Ces validations confirment le code compilé et ses témoins hôtes,
**pas la fluidité du jeu ou la reprise de son compteur d'instructions**.

**Nouvelle attribution d'un blocage durable (CI encore à valider) :**
les compteurs `guest_dequeue_wait` sont mis à jour lorsque `DequeueBuffer`
revient ; si le producteur attend pour toujours dans
`BufferQueueCore::WaitForDequeueCondition`, ils ne permettent pas d'attribuer
le gel. Avec les commits `04946f1`, `ae465e5`, `71acf98d`, le mode de
profilage **détaillé seulement** expose `dequeue_blocked` dans
`EDEN_DEV_GUEST` et dans `EDEN_GPU_REPORT_STALLED`. C'est le nombre
d'attentes hôtes de slots **actuellement en cours**, mesuré par un scope
RAII autour de l'attente et décrémenté aussi sur sortie anticipée.
Pas de polling, timeout, allocation, log supplémentaire par frame ou
modification du prédicat de réveil ; profilage désactivé, ce compteur
n'entraîne aucune écriture atomique sur le chemin d'attente.
L'oracle de provenance maintenu et le test compilé sous UBSan `-O0`/`-O2`
vérifient le scope et huit attentes concurrentes. Le témoin supplémentaire
`check-native-nvnflinger-dequeue-profile-host.py` exécute désormais aussi
les méthodes natives `BufferQueueCore::{WaitForDequeueCondition,SignalDequeueCondition}`
avec le bloc d'attente réellement sélectionné dans `WaitForFreeSlotThenRelock`.
Il rejoue huit producteurs sous quatre variantes (`-O0`/`-O2`, profilage
actif/absent), et exige la suppression du compteur à la reprise. Ce témoin
est raccordé au checkpoint `check-fc27-six-gates-host.py` depuis `2819a4a`.
Son premier essai CI a révélé une divergence **de nom du verrou dans le mock**,
corrigée en `e762f2b` ; la validation complète du nouveau HEAD reste en cours.
Une valeur non nulle **n'est pas** la preuve que l'IPC ou le PC invité est
bloqué ; les deux observations doivent rester indépendantes.

**Inventaire séparé :** `EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS` sur la
prévalidation verte relève `owned_code=506`, `handled=443`,
`remaining_emulator_to_optimize_review=0` et `launcher_ui_pending_separate=63`.
Les 63 chemins restants sont dans le volet launcher/UI et non 63 correctifs
moteur manquants ; ce compteur n'implique ni accélération ni validation FC27.

**Critères pré-console : F01–F04 validés techniquement, F05 et F06
encore ouverts (4/6).** F06 est jugé fonctionnel par l'utilisateur et
reste hors du chantier sauf régression reproduite. Aucun nouveau test console
demandé tant que le lot F05 n'est pas qualifié.

---

## Tableau de bord courant — 25 octobre 2026 (référence technique, 4/6)

**Source de vérité automatique :** `tools/check-fc27-six-gates-host.py`, exécuté par le workflow
`encore-core-preflight.yml`. Sa sortie `FC27_SIX_GATES_HOST_CHECKPOINT` contient
`preconsole_exit_status`, `f01_to_f06_closed` et les preuves par test. Ne pas déduire
le compteur d'un ancien tableau, des seuls commits ou du succès général d'un autre workflow.

| ID | État de clôture pré-console | Preuve ciblée | État PS5 |
| --- | --- | --- | --- |
| **F01** contention/cache GPU-CPU | **VALIDÉ techniquement** | `3fb2986`, `d5cb865`, `a43af9c` : mesure avant/après des appels samplers, section critique avec concurrent et source native sélectionnée ; fast gate vert sur `c03a47c` | Non mesuré ; F07 |
| **F02** JIT A32/A64 | **VALIDÉ techniquement** | `2579482`, `c03a47c` : méthodes natives épinglées/maintenues, 96 invalidations, compilation froide/chaude, recompilation et isolation des caches par cœur ; fast gate vert sur `c03a47c` | Non mesuré ; F07 |
| **F03** HUD/fraîcheur | **VALIDÉ techniquement** | Préflight [40149972349](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40149972349) vert : `FC27_SIX_GATES_HOST_CHECKPOINT` déclare `F03-hud-freshness=true`, 241 révisions HUD, 2 remaps, 1 perte/récupération, 12 ticks pause, O0/O2 | Non mesuré ; F07 |
| **F04** textures/contenu GPU | **VALIDÉ techniquement** | [prévalidation #40152839640](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40152839640), SHA `c757d02` : `F04-texture-integrity=true`, 6/6 sous-tests F04. Rejeu compilé `-O0`/`-O2` : 3 copies DMA, 2 alias, 1 unmap/remap simulé, 3 révisions d’upload et 3 barrières ; tests des barrières Vulkan et de la parité des sources également verts. | GPU réel/pixels FC27 non mesurés ; F07 |
| **F05** progression HLE | **EN QUALIFICATION — Binder, buffers/fences vérifiés** | [fast gate #40155675552](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40155675552) vert : 260 transactions `IHOSBinderDriver`, 260 acquisitions jeu + HUD, compositions et copies Vulkan dans une chaîne C++ liée à quatre unités, `-O0`/`-O2`. Le marshaling HIPC réel et la progression CPU du jeu restent non démontrés. | HID/IPC invités et jeu réel non mesurés ; F07 |
| **F06** commandes/gel | **EN QUALIFICATION — transitions DualSense et handoff Npad source vérifiés** | Rejeu C++ `Pad::Consume` + `PadEngine::SetButtonState` (`a7738bd`) ; nouveau rejeu source-extrait `EmulatedController::GetNpadButtons` + `NPad::RequestPadStateUpdate` (`ec24e9e`) : Plus, relâchement, filtrage, déconnexion/reconnexion, Joy-Con droit sous `-O0`/`-O2`. Le nouveau témoin OnUpdate→LIFO hôte (`0385a6b`) ajoute la publication Fullkey/system_ext. La lecture HIPC réelle, le mapping interne FC27 et la progression du match restent non prouvés. | Jeu réel non mesuré ; F07 |

**Jalon certifié le 25 octobre : 4/6 pré-console (F01, F02, F03, F04).**
[Prévalidation entière verte #40152839640](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40152839640)
au commit `c757d02` : `FC27_SIX_GATES_HOST_CHECKPOINT` a émis
`f01_to_f06_closed=4`, `host_subpaths_passed=23`,
`host_subpaths_total=23`, et
`preconsole_exit_status.F04-texture-integrity=true`.
F04 est **clôturé techniquement pré-console**, comme F01–F03.
Le mock d'adressage et de GPU ne permet **ni d'affirmer les pixels
réels ni les FPS du jeu** ; cela reste F07.

**F06, 25 octobre — DualSense vers l'entrée virtuelle, preuve source supplémentaire :**
Le test `tools/check-fc27-f06-native-pad-transition-host.py` compile les méthodes
C++ sélectionnées `Pad::Consume` et `PadEngine::SetButtonState` sous UBSan à
`-O0` et `-O2`. Il rejoue cinq étapes synthétiques du match avec une
configuration de touches par titre figée, des pressions Options→Plus, une
perte de connexion, le chord Home et les raccourcis. Son fixture utilise
la vraie structure d'entrée DualSense `third_party/ps5_pad.hpp`, mais un
récepteur virtuel simulé ; les cinq *phases* sont des étiquettes de test,
**pas des transitions FC27 exécutées**. Le contrôle est appelé depuis le
fast gate, la prévalidation et le tableau des six critères au commit
[`a7738bd`](https://github.com/niakw/Prospero.Eden-Encore/commit/a7738bdfc67bddf064539de79b6b33e89fde8e92).
La CI complète et la clôture F06 sont distinctes : **4/6 reste inchangé**,
aucun nouveau test sur PS5 demandé.

**F05, 25 octobre — vérification de l'événement Binder jusqu'à la notification d'attente :**
Le contrôle `tools/check-fc27-f05-native-kernel-wait-publication-host.py`
extrait les méthodes C++ de production `KEvent::Signal`,
`KReadableEvent::{IsSignaled,Signal,Reset}`,
`KSynchronizationObject::NotifyAvailable` et le relais
`ProducerReleaseWake::OnBufferReleased`. Il fait évoluer deux threads
hôtes **simulant les attentes d'un jeu**, sur 260 cycles, en contrôlant
le caractère *level-triggered* de l'événement (un signal supplémentaire
avant `Reset` n'est pas un nouveau réveil), puis son réarmement.
Les endpoints `IHOSBinderDriver::GetNativeHandle`,
`BufferQueueProducer::GetNativeHandle` et
`Svc::WaitSynchronization` sont référencés par les assertions de source.
Le test natif a été ajouté au fast gate, à la prévalidation et au checkpoint
au commit [c28436f](https://github.com/niakw/Prospero.Eden-Encore/commit/c28436fa8139d38320f9f70f9eacafd75b6f5999).
**Statut : CI en cours**, ce n'est pas encore une preuve d'exécution du
véritable `KThread::EndWait`, de son ordonnanceur PS5 ni d'une transition
pause/mi-temps/fin de match dans FC27. F05 reste ouvert.

**CI réparée :** après le recyclage `QueueBuffer`, les deux simulations
du compositeur (`check-native-hardware-composer-liveness-host.py` et
`check-fc27-f05-native-nvdisp-vulkan-present-chain-host.py`) devaient
recevoir les nouveaux paramètres de l'événement invité. Corrections
[4ef9ec4](https://github.com/niakw/Prospero.Eden-Encore/commit/4ef9ec45bec721f3e13adfbe5ee962bdb2c02b66)
et [8d04691](https://github.com/niakw/Prospero.Eden-Encore/commit/8d0469132caa0be5095a6265b000c46b945abd8d).
Les succès du moteur, des hôtes et de la CI doivent être qualifiés
séparément. Aucun passage à 5/6 tant que la progression invitée n'est
pas démontrée.

**F05, 25 octobre — recyclage des images et réveil de l'invité :**
Le moteur conservait deux chemins de recyclage ne notifiant pas le handle
Binder du producteur : `BufferQueueConsumer::AcquireBuffer` lorsqu'il écarte
des images en retard, et `BufferQueueProducer::QueueBuffer` lorsqu'une frame
remplace une frame `droppable` déjà suivie. Les corrections
[1890067](https://github.com/niakw/Prospero.Eden-Encore/commit/1890067b9c37ff5342d152a471f7c04cac451c81)
et [a9ba080](https://github.com/niakw/Prospero.Eden-Encore/commit/a9ba080d1ee5b054177b3ddc79a4f4bd4c55af10)
publient l'événement invité uniquement lors de ces transitions ; le chemin
de l'acquisition conserve un callback hors du mutex `core->mutex`.
Les nouveaux tests `check-fc27-f05-native-acquire-drop-wake-host.py`
(260 acquisitions, 520 suppressions simulées) et
`check-fc27-f05-native-queue-replace-wake-host.py` (260 remplacements)
rejouent les branches natives sous `-O0`/`-O2`, sans transformer
ces résultats en preuve de gameplay FC27.
Les contrôles de parité vendor, le fast gate, la prévalidation et
`check-fc27-six-gates-host.py` ont été actualisés. **Nouvelle CI en cours** ;
F05 reste non clôturé jusqu'à la preuve de progression HLE/IPC invitée.

**Inventaire moteur, 25 octobre :** le contrôle CI sur `c403948`
échouait parce que `owned_code_count_at_snapshot=504` et
`post_snapshot_owned_additions` ne comptait qu'une des deux sources ajoutées.
Le commit [54caa67](https://github.com/niakw/Prospero.Eden-Encore/commit/54caa67d6a67f85b4cf56ae8b36be3ccf089a03d)
enregistre `buffer_queue_consumer.cpp` comme source native maintenue,
avec sa preuve F05. L'inventaire suivi atteint **506 sources C/C++**
(504 à la référence et 2 nouvelles), sans affirmer que 506 fichiers
ont été optimisés ou validés sur PS5.

**F05, 25 octobre — fermeture consommateur sans attente invitée persistante :**
Le chemin épinglé `BufferQueueConsumer::Disconnect` abandonnait la file et
réveillait `SignalDequeueCondition` (condition hôte), sans notification
du handle Binder de la tâche invitée. Une implémentation maintenue distincte
est maintenant sélectionnée par `headless/CMakeLists.txt` pour libérer la file
et transmettre un dernier `OnBufferReleased` au relais de réveil du producteur.
Le callback intervient après libération de `core->mutex` pour empêcher un
réentrance/deadlock. Sources et points de contrôle :
[ca32b64](https://github.com/niakw/Prospero.Eden-Encore/commit/ca32b64c484a69b34014e8f17b82bdb8f55ad3c0)
(correctif),
[37eef47](https://github.com/niakw/Prospero.Eden-Encore/commit/37eef4781d72ed2d506f631cb9620d85a68a3c39)
(sélection CMake),
`tools/check-fc27-f05-native-consumer-disconnect-host.py`
(source extraite, deux attentes hôtes, événement invité simulé, callback
hors mutex, chemin erreur, arrêt sécurisé, compilations O0/O2).
L'oracle `check-vendor-consolidation-debt.py` vérifie la parité avec la
source épinglée et ce seul delta de production. Test ajouté au fast gate,
à la prévalidation et au tableau des six critères. **Ce test ne couvre
pas l'ordonnancement réel des threads invités ni la progression FC27 :
F05 reste en qualification et le total reste à 4/6.**

**Réorientation du 25 octobre — retour fonctionnel utilisateur sur F06 :**
L'utilisateur jugeait les commandes F06 déjà satisfaisantes dans ses essais.
Ne pas ouvrir de nouvelle refonte du pad ou de ses raccourcis en l'absence
d'une régression reproduite. Conserver les tests existants et les protections
de non-régression. F06 reste administrativement en attente de clôture
technique de bout en bout, mais **n'est plus le chantier prioritaire**.
Priorité F05 : attente HLE/IPC, synchronisation des slots et progression invitée.


**F05, 25 octobre — notifications manquantes du handle Binder :**
Le code maintenu réveillait la condition du producteur, mais ne signalait
pas l'événement noyau consommé par l'invité dans trois transitions :
`SetBufferCount(0)`, `DetachBuffer`, `DetachNextBuffer`. Le commit
[cb94cd1](https://github.com/niakw/Prospero.Eden-Encore/commit/cb94cd16325c8edf494a1a1219509809af5e44a1)
ajoute les trois notifications, sans intervenir dans `QueueBuffer` ni dans
le routage F06. `tools/check-vendor-consolidation-debt.py` conserve la parité
avec la source historique en projetant explicitement ces trois deltas.
`tools/check-native-nvnflinger-detach-wake-host.py` extrait et exécute
maintenant les deux méthodes `DetachBuffer` et `DetachNextBuffer`, ainsi
que `SetBufferCount`, et vérifie signaux hôtes/événements invités
sur succès et absence de réveils sur erreur avec compilation UBSan O0/O2.
La réussite complète de la CI et la progression réelle FC27 restent
à établir. **Ces réveils ne clôturent pas F05 à eux seuls.**

**F06, 25 octobre — publication du contrôleur vers le LIFO invité simulé :**
Le test `tools/check-fc27-f06-native-npad-lifo-host.py` exécute dans un
même programme C++ les trois méthodes natives maintenues
`EmulatedController::GetNpadButtons`, `NPad::RequestPadStateUpdate` et
`NPad::OnUpdate`. Il teste les publications `fullkey_lifo` et
`system_ext_lifo`, la numérotation croissante des échantillons, le passage
Options→Plus, le relâchement à zéro, les gates input/style/activation,
la reconnexion et le masque du Joy-Con droit. Rejeu local de référence
compilé sous UBSan en `-O0`/`-O2`; le script source-extrait est ajouté
au fast gate, à la prévalidation et au checkpoint F01–F06 au commit
[5b930dc](https://github.com/niakw/Prospero.Eden-Encore/commit/5b930dc13494324685aabe3e2bc673bf12382241).
La validation CI complète de ce témoin reste indépendante.
**La mémoire partagée et le noyau hôte sont simulés : ce résultat ne prouve
ni la lecture HIPC réelle par le jeu ni les actions FC27 en match. F06 reste
ouvert ; total 4/6.**

**F06, 25 octobre — transfert natif contrôleur vers Npad (nouveau témoin) :**
`tools/check-fc27-f06-native-npad-handoff-host.py` compile les fonctions
maintenues `EmulatedController::GetNpadButtons` et `NPad::RequestPadStateUpdate`
avec un contrôleur et un noyau simulés, en `-O0` et `-O2` sous UBSan.
Le transfert d'Options/Plus, sa libération, le filtrage pendant configuration,
les masques de boutons et une déconnexion/reconnexion sont vérifiés dans le
même exécutable hôte. Les correspondances de boutons et l'écriture Npad en
mémoire partagée sont contrôlées dans la source ; **le callback virtuel réel,
l'écriture dans le LIFO invité et les phases de FC27 ne sont pas rejoués**.
Le test est inscrit dans le fast gate, la prévalidation et le tableau des six
critères. La CI GitHub du SHA récent n'est pas encore confirmée.
**F06 reste ouvert ; total inchangé à 4/6.**


**F05, 25 octobre — cohérence de l'oracle vendor :**
Le contrôle `tools/check-vendor-consolidation-debt.py` attendait encore
l'ancien fichier C++ malgré l'ajout du relais de réveil. Le correctif
[253efd9](https://github.com/niakw/Prospero.Eden-Encore/commit/253efd927a62ee2889fb4b2b3c6ecdcec6a379c6)
projette seulement le nouveau bloc F05 hors de la parité historique,
vérifie son empreinte et conserve la comparaison de toutes les anciennes
optimisations. Aucune nouvelle clôture F05 n'est déduite de cette mise à jour.

**F05, 25 octobre — réveil de producteur après libération de buffer :**
Le producteur ignorait le callback de `BufferQueueConsumer::ReleaseBuffer`
lorsqu'une connexion HOS n'apportait aucun `IProducerListener`. Le consommateur
réveillait la condition hôte, mais pas l'événement noyau renvoyé par
`BufferQueueProducer::GetNativeHandle`. Le commit
[6ae418e](https://github.com/niakw/Prospero.Eden-Encore/commit/6ae418e67143c44dcba2b5cebd4cf318658fffaf)
installe un relais à chaque connexion, transmet éventuellement la notification
d'origine et le désactive avant `CloseEvent` pour gérer le callback différé.
`tools/check-fc27-f05-producer-release-wake-host.py` rejoue 260 notifications,
le callback délégué, une concurrence libération/destruction et l'absence de
signal après fermeture. Le test source-extrait est branché dans le fast gate,
la prévalidation et le suivi F01–F06, sous `-O0` et `-O2`.
**C'est un événement noyau simulé, pas le réveil de la vraie tâche invitée ;
F05 reste en qualification tant que HIPC, ordonnancement invité et progression
CPU ne sont pas prouvés.**

**F05, 25 octobre — BufferQueue jusqu'à Vulkan, sous GPU simulé :**
[Fast gate #40155140352 vert](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40155140352)
sur `bfee35e`. Les deux compilations `-O0`/`-O2` exécutent
les méthodes natives de `BufferQueueProducer`/`BufferQueueConsumer`,
`HardwareComposer`, `nvdisp`, GPU/Host1x, `RendererVulkan`
et `PresentManager` en trois unités C++ liées. Les traces affichent
`queued=260 acquired_game=260 acquired_hud=260 composite=260
callback_frames=260` et `requests=260 copies=260`. Le module
`IHOSBinderDriver` est en cours d'intégration au témoin ; il ne
reproduit ni le vrai marshaling HIPC ni le thread invité.
**F05 n'est pas clôturé** ; aucun test console demandé.

**F05 en cours :** le nouvel essai natif relié dans
`tools/check-fc27-f05-native-nvdisp-vulkan-present-chain-host.py`
assemble les chemins nvdisp → GPU → Host1x → rendu Vulkan →
présentateur asynchrone sur 260 requêtes fences dans un même exécutable.
Sa CI sur la branche doit encore être prouvée après intégration. F05
reste ouvert faute de preuve HID/HLE/IPC → buffer queue complète ;
F06 reste ouvert faute de transitions de commandes de match.

**Entrées F04 plus anciennes ci-dessous : historiques uniquement.**
Elles documentent la progression avant ce jalon et ne remettent pas le
compteur à 2/6 ou 3/6.

**F04, 25 octobre — preuve hôte supplémentaire, non clôturante :**
[fast gate vert #40150112743](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40150112743)
sur `f96f3cb`. Le test `tools/check-fc27-f04-native-dma-alias-bytes-host.py`
compile des fragments C++ réellement sélectionnés de `MaxwellDMA`,
`TextureCache::SynchronizeAliases` et `TextureCache::WriteMemory`
sous UBSan avec `-O0` et `-O2`. Les deux modes passent : copies DMA
contiguës, à pitch disjoint ou à chevauchement, ordre des deux alias,
conservation de trois régions d'octets, actualisation d'un alias et
invalidation CPU idempotente. **Pas de Vulkan réel, ni pixels FC27, ni preuve
de upload/décodage complet** : F04 reste EN QUALIFICATION, et le compteur
des critères fermés reste 2/6. L'incident précédent sur le type
`GPUVAddr` du fixture a été corrigé avant ce fast gate vert.

**F04, 25 octobre — nouvel état vérifié sur `778fc2b` :**
[fast gate #40151841247 réussi](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40151841247).
Les logs prouvent `VENDORED_VULKAN_FORK_EQUIVALENT_OK files=41`,
`F04_NATIVE_DMA_ALIAS_CONTENT_PASS`,
`F04_NATIVE_TEXTURE_UPLOAD_REVISION_PASS`,
`F04_NATIVE_VULKAN_UPLOAD_BARRIER_PASS` en `-O0` et `-O2`,
puis `DEFERRED_COPY_OWNERSHIP_PASS sites=7` sous ASan/UBSan.
Le moteur Vulkan actif possède désormais les barrières d'écriture/lecture
transfer → shaders/attachements renforcées. La reconstruction de l'oracle
épingle les quatre deltas du correctif ; le témoin de propriété des copies
retire uniquement ces quatre deltas pour garder l'empreinte historique stricte.
**La prévalidation complète, CodeQL et la compilation native de `778fc2b`
ne sont pas encore confirmés verts dans ce relevé.** Les trois tests
vérifient des sous-chaînes hôte séparées, sans un vrai contenu GPU Vulkan
ni le remap→DMA→upload complet. F04 reste donc ouvert ; F01–F03 restent
validés pré-console, soit **3/6**, et F07 reste le test matériel final.

**Ancien jalon établi : 3/6 (F01 + F02 + F03), dépassé par le résultat 4/6 ci-dessus.** La prévalidation [40149972349](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40149972349), SHA `ba308547`, a terminé avec succès et émis `FC27_SIX_GATES_HOST_CHECKPOINT` : `f01_to_f06_closed=3`, `host_subpaths_passed=20/20`, F01/F02/F03 `true`, F04/F05/F06 `false`. Une correction limitée à F04 ne remet pas les trois sorties techniques à zéro : seule une régression constatée de leurs preuves ou des sources correspondantes le justifie. C'est une **clôture pré-console avec GPU simulé**, pas une mesure des pixels ou des FPS de FC27.

Le test supplémentaire `tools/check-fc27-f04-native-upload-revision-host.py` (commit `422ff11`) est branché sur fast gate et prévalidation. Il extrait `TextureCache::RefreshContents` et `UploadImageContents`, vérifie que les révisions CPU atteignent le stockage d'image simulé avant la barrière, y compris conversion, accélération, décodage asynchrone et MSAA non pris en charge. **Sa CI est à confirmer, et F04 reste ouvert** : pas de vrai GPU Vulkan ni de décodeur de formats testé.

**F07 est distinct et reste ouvert :** ni ces validations techniques hôte
ni des builds natifs verts ne démontrent les FPS, l'image ou les commandes
réels dans FC27 sur la PS5. On ne demande pas de test console intermédiaire.

**Vérifications GitHub :** [fast gate F01/F02 vert au commit c03a47c](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40146542127) ;
[fast gate F03 précédent vert au commit 7976a38](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40148166205) ;
[nouveau fast gate après remap 77b5ee2](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40148940424).
Une CI annulée par un push ultérieur n'est pas un test échoué. L'état CI
des commits changeants doit être relu avant d'affirmer une nouvelle clôture.

---

## Archives : tableau de bord du 22 octobre, état après `da6d57c`

> **Archive historique uniquement.** Les états ci-dessous (dont le 0/6) sont antérieurs aux validations F01/F02 et ne doivent pas servir de tableau courant.

**Il reste six critères techniques ouverts (F01–F06), puis la qualification console F07.** Les correctifs et les contrôles hôte réussis font avancer des sous-chemins précis, **mais aucun critère technique complet n'a encore satisfait tous ses critères de clôture**.

**Ne pas confondre trois décomptes :**

- **Revue initiale des sources d'émulation : 0 fichier restant** (registre vérifié par `tools/check-eden-optimization-coverage.py`, fast/preflight `EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS`).
- **Revue source de tous les composants : 62 fichiers restants**, exclusivement dans `headless/prosperoeden/` et séparés de l'audit moteur. Le fichier commun `runtime_shims.cpp` a déjà été classé avec le moteur.
- **Nombre de fichiers exigeant encore un changement d'optimisation/correction : inconnu**. Un fichier déjà revu peut contenir un défaut découvert lors d'un rejeu ; ni « 0 » ni « 62 » ne mesure les corrections restantes.

| Critère | État technique | Dernier progrès démontrable | Travail empêchant la clôture |
| --- | --- | --- | --- |
| F01 — contention et saccades GPU/CPU | **INVESTIGATION** | Mémoire paginée, préflight GPU et déduplication de samplers par draw (`abbf9c5`, `da6d57c`), tests de sources en CI | Identifier et diminuer la section *réellement* responsable des attentes cache ; test de concurrence/benchmark avant-après et compilation native validés |
| F02 — pics de compilation JIT | **INVESTIGATION** | Invalidation et limites de cache précédemment gardées | Rejeu par cœur de la compilation et des invalidations avec compteurs et comportement pré/post correctif |
| F03 — HUD actualisé | **À QUALIFIER** | Récupération des mappings TIC/TSC, test hôte existant | Tests de fraîcheur TIC → vue → descripteur → barrières → présent, y compris alias et retour de NULL |
| F04 — maillots et terrain corrects | **À QUALIFIER** | Sécurités DMA, tailles d'index et transferts déjà intégrées | Rejeu de contenu des alias/remaps, upload et invalidations sans perte de données |
| F05 — simulation HLE qui avance | **INVESTIGATION** | Notifications producteur et horodatage conditionnel validés en hôte | Rejeu déterministe complet HID/HLE/IPC → queue → fence → present ; prouver les réveils et l'absence de frame périmée |
| F06 — commandes et match sans gel | **À QUALIFIER** | Parcours contrôleur et symptômes de pause documentés | Rejeu Npad/HID et commandes modifiées, transitions pause/mi-temps/fin |
| F07 — qualification console | **OUVERT** | Aucune comparaison A/B sur le même binaire récent | Une campagne finale, seulement lorsque F01–F06 disposent de preuves suffisantes |

**Contrats :** les six premiers se closent par preuve source + hôte + CI + compilation native ; **F07 est le seul critère nécessitant la console**. Les anciennes traces ne prouvent pas encore une amélioration de FPS ou la disparition des gels.

**Sélection de fichiers encore actifs sur les problèmes, déjà revus dans l'inventaire :**
`vulkan_rasterizer.cpp` (`OnCPUWrite`/`PrepareDraw`),
`vk_graphics_pipeline_cost.cpp` (`ConfigureImpl`),
`video_core/buffer_cache/buffer_cache.h`,
`texture_cache/texture_cache.h`,
`video_core/texture_cache/util.cpp`,
`video_core/memory_manager.cpp`,
`buffer_queue_producer.cpp`,
`buffer_queue_core.cpp` et `surface_flinger.cpp`.
Il ne s'agit **pas** d'une liste exhaustive des fichiers qui devront être modifiés.

**Temps de clôture : non estimable de manière fiable**, tant que les reproductions F01/F02 et les replays F03–F06 n'ont pas identifié l'effort exact. Remplacer ce constat par un nombre d'heures arbitraire serait une fausse visibilité. Le suivi porte sur les preuves manquantes, pas sur un calendrier inventé.

**Référence actuelle :** HEAD `da6d57c` (mémorisation de sampler par draw et test de génération), fast gate, prévalidation, CodeQL C++ et compilation native déclenchés mais non définitifs au moment de cette entrée. [Build natif](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39849801544), [Fast gate](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39849801419).

---

**État établi le 22 octobre 2026.** Branche unique :
`dev/ps5-sparse-jit`. Base native vérifiée :
[`69fdf79`](https://github.com/niakw/Prospero.Eden-Encore/commit/69fdf7912de4cb0264d95bcbfcf61ad49d20d95c).

> **Indicateurs séparés : 0 / 6 chantiers techniques clôturés sur code + tests,
> et F07 = qualification matérielle distincte.**
> Les six premiers chantiers **ne requièrent aucune nouvelle preuve sur console**.
> Une correction peut satisfaire plusieurs critères, ou aucun si les tests ne
> couvrent pas la cause identifiée. Une CI verte seule n'est pas une preuve
> que tous les chemins du sous-système sont couverts. Les `430/492` sources examinées et les `409`
> contrats SOURCE/OPEN sont des indicateurs historiques d'inventaire et de
> qualification, **pas des compteurs d'optimisations restantes**.

## Socle CI — terminé pour le SHA de référence

| Preuve | État | Exécution |
| --- | --- | --- |
| Fast gate et régressions hôte C++ | **VERT** | [39775426169](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426169) |
| Prévalidation de toutes les sources | **VERT** | [39775425826](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775425826) |
| Build/package natif PS5 | **VERT** | [39775426085](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426085) |
| Analyse sécurité CodeQL | **VERT** | [39775426078](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39775426078) |
| **Résultat FC27 sur matériel pour ce SHA (F07 uniquement)** | **NON MESURÉ** | Aucun test console du SHA de référence |

Cette base inclut déjà les gardes TIC/TSC, les limites des buffers
indirects / SSBO / TBO / CBUF, les liaisons compute périmées, la
mise à jour des plages d'indices, le coût des samplers et le
correctif du registre AMD. Leur réussite en CI n'est pas une
qualification de performance, de HUD ou de fidélité des textures.

## Tableau des sept critères de sortie

Les états ont un sens strict : **OUVERT** = une lacune de code, de reproduction ou
 de couverture de tests subsiste ; **INVESTIGATION** = les chemins propriétaires sont
repérés, la cause n'est pas totalement démontrée ; **À QUALIFIER** = un correctif
existe, mais il manque un test de non-régression ou une preuve de sélection native.
**F01–F06 se clôturent exclusivement avec preuves source, tests hôte, replay
et CI/native**, indépendamment d'un test console. **F07 seul** mesure le résultat
observable par l'utilisateur ; son état ne bloque pas la clôture des six premiers.

| ID | Priorité | Résultat attendu | Situation vérifiée | Prochaine intervention ciblée | Clôture requise |
| --- | --- | --- | --- | --- | --- |
| **F01** | P0 | **Plus de saccades CPU/GPU liées aux buffers** | **INVESTIGATION.** 1 005 680 attentes du mutex buffers, 9,311 s cumulées dans la trace détaillée. Réductions partielles déjà intégrées : pages jamais possédées, préallocation des descripteurs, samplers consécutifs. | Isoler les sections réellement longues entre `RasterizerVulkan::OnCPUWrite`, `PrepareDraw` et `GraphicsPipeline::ConfigureImpl`. Réduire le travail immuable sous le verrou sans perdre une invalidation. | Test source-extrait concurrents/ownership buffer+texture prouvant l'ordre des invalidations et absence de régression, plus microbenchmark hôte du chemin ciblé et build natif vert. Le gain FPS sur console reste F07. |
| **F02** | P0 | **Supprimer les très gros pics de compilation JIT** | **INVESTIGATION.** Les traces comportent des images de plusieurs centaines de ms à plus d'une seconde et de fortes compilations JIT cumulées. Le sparse JIT expérimental est OFF en release ; l'ancienne session sparse utilisait un **autre SHA**. | Isoler par cœur les compilations froides/répétées, invalidations de blocs et limites du cache ; privilégier une correction ciblée plutôt que monter les tailles et les threads au hasard. | Reproduction hôte des invalidations/compilations répétées par cœur avec compteur avant/après, tests JIT O0/O2, absence de corruption mémoire sous sanitizers et build natif vert. Aucun A/B console nécessaire pour cette clôture technique. |
| **F03** | P0 | **HUD présent et actualisé en continu** | **À QUALIFIER.** Gardes TIC/TSC et récupération de mappings manquants intégrés, mais la dernière console montrait encore des éléments de HUD figés/disparus. Zéro `EDEN_GPU_DRAW_DROP` observé dans l'ancienne trace ne prouve pas la fraîcheur des pixels. | Tracer le parcours TIC/TSC → image view → descripteur graphique → barrières/feedback → présentation, avec la durée de validité et les écritures CPU/GPU. | Tests déterministes TIC/TSC, vues NULL, réutilisation après remap et barrières/feedback couvrant le chemin sélectionné ; assertions de fraîcheur/invalidations et CI/native verts. L'aspect visuel sur console relève seulement de F07. |
| **F04** | P0 | **Maillots, terrain et autres textures sans trous ni corruption** | **À QUALIFIER.** Limites DMA, vertex/index, slots SSBO/TBO et mappings textures corrigées côté source, sans preuve d'une restitution correcte de FC27. `memory_short=0` dans l'ancien relevé. | Vérifier alias/remap, invalidations de textures, vues périmées et échelles/régions d'upload ; distinguer géométrie absente et texture invalide. | Tests host source-extraits couvrant les alias/remaps, régions DMA, vertex/index, uploads et formats pertinents, avec vérification du contenu et absence de dépassement ; sélection native verte. Fidélité réelle en match à vérifier dans F07. |
| **F05** | P1 | **Image affichée = simulation du jeu qui avance** | **INVESTIGATION.** ~30 FPS Vulkan peuvent masquer une scène bloquée. L'ancien gel de pause/fin de match avait GPU et compositor actifs. Le service `IHOSBinderDriver` concentre des attentes IPC mais elles ne sont pas toutes des coûts évitables. | Corréler progression du jeu/HLE, transactions `TransactParcelAuto`, dequeue/queue de buffers, fences et horodatages de présentation. Ne pas forcer la cadence ni sauter un fence. | Rejeu déterministe de la chaîne HID/HLE/IPC buffer queue → fence → present, invariants de progression, anti-double-present/notification perdue et tests de blocages ; CI/native verts. Réactivité ressentie en jeu uniquement F07. |
| **F06** | P1 | **Match complet : contrôles cohérents, pas de gel ni crash** | **À QUALIFIER.** La session console récente ne semblait plus planter/geler mais de forts lags persistaient ; les anciens gels pause/mi-temps/fin de match et paramètres de commandes non appliqués n'ont pas été clos sur la révision actuelle. | Vérifier le passage DualSense → HID/Npad → actions du jeu, les états de commande personnalisés et la progression HLE des menus/écrans de fin. Ne pas forcer de mapping global pendant le match. | Tests de bout en bout côté hôte pour transitions pause/mi-temps/fin, style HID/Npad, persistance et mapping de commande, plus analyses des attentes/signalements d'erreurs ; CI/native verts. Essai de match complet uniquement F07. |
| **F07** | P0, final | **Qualification reproductible sur PS5 FW 13.60** | **OUVERT** : CI verte ≠ résultat sur console. Les deux traces historiques les plus récentes ont des SHAs et des états sparse différents, non comparables comme A/B. | Quand des correctifs ciblés F01–F06 auront un candidat CI vert, figer une seule révision/paramétrage, lancer scénario froid **puis** scénario cache chaud, sans mélange des profils ni changements simultanés. | Relever `late50`, `late100`, intervalle maximal, p95/p99, progression du jeu, HUD, maillots, freeze et commandes. Comparaison contrôlée, effet attribuable, validation explicite. |

### Ce qui n'est **pas** une tâche restante

- Migrer d'autres centaines de fichiers **sans défaut précis**.
- Revalider comme « optimisation » un backport seulement parce qu'il est
  référencé par le graphe d'architecture.
- Agrandir d'office la queue GPU : `gpu_full_ms=0` dans les anciens relevés.
- Déverrouiller le cache pendant des invalidations CPU/GPU ou supprimer les
  fences sous prétexte que les FPS affichés restent proches de 30.
- Activer par défaut les variantes sparse/shared JIT, CPU→GPU différé, ou
  toute expérimentation DEV non qualifiée.
- Faire tester une nouvelle image uniquement pour valider des sources qui
  ne sont pas encore des candidates mesurables.

### Ordre d'exécution et journal de décision

1. **F01** et **F03/F04** d'abord, dans les fonctions effectivement
   responsables des acquisitions CPU/GPU et de la cohérence des descripteurs.
   Les correctifs successifs de sûreté SSBO sont terminés **au niveau CI**
   sur `69fdf79` ; ils ne ferment pas ces objectifs.
2. **F02** séparément : compilation et réutilisation des blocs par cœur ;
   ne pas confondre somme du travail JIT multi-cœur et temps perdu par image.
3. **F05/F06** : confirmer progression HLE, buffers de présentation et
   contrôle de jeu, plutôt que conclure d'après les FPS du compositor.
4. **F07** reste distinct : une seule éventuelle campagne de qualification
   matérielle finale. **Aucune preuve console n'est demandée pour fermer F01–F06**.
   Les tests hôte démontreront la correction technique, sans prétendre prédire
   précisément les images/sec ni l'aspect final en match.

Après chaque lot : noter **le ou les IDs techniques affectés**, le commit,
le test source-extrait/rejeu/benchmark, les résultats CI et le SHA de
sélection native. Fermer **F01–F06 sans passage sur console** dès que les
invariants correspondants sont établis. Garder F07 indépendant. Une baisse du nombre de sources restantes
n'est plus une métrique de progression ici.

**Sources de mesures :**
[FC27_GPU_SOURCE_TARGETS_2026-10-21.md](FC27_GPU_SOURCE_TARGETS_2026-10-21.md),
[FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md](FC27_NATIVE_FRAME_PROGRESS_TRIAGE_2026-10-17.md),
[FC27_PAUSE_FREEZE_R435.md](FC27_PAUSE_FREEZE_R435.md),
[FC27_TIC_TSC_MISSING_CHANNEL_MAPPING_2026-10-22.md](FC27_TIC_TSC_MISSING_CHANNEL_MAPPING_2026-10-22.md),
[EDEN_SINGLE_FINAL_RUNTIME_DECISIONS_2026-10-21.md](EDEN_SINGLE_FINAL_RUNTIME_DECISIONS_2026-10-21.md).

**Périmètre séparé :** travaux launcher/UI, couvertures 3D, avatar, jaquettes,
glyphes et traductions. Ne pas les mélanger à la mesure de stabilité du moteur.


## F05 — 22 octobre : réveil producteur après détachement du plus ancien tampon libre

**Source ciblée :** `eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`
(`BufferQueueProducer::DetachNextBuffer`, sélectionné directement par CMake).
Le chemin `DetachBuffer` publiait déjà `SignalDequeueCondition` après
`FreeBufferLocked`, mais `DetachNextBuffer` ne le faisait pas. Une
transition de la file pouvait donc passer inaperçue pour un producteur
attendant la génération suivante. Le chemin normal conserve l'ordre de
sélection du tampon le plus ancien, la propriété du buffer transféré et
les fences ; seule la notification est ajoutée, sous `core->mutex`.

**Preuve technique :** `tools/check-native-nvnflinger-detach-wake-host.py`
compile le corps C++ sélectionné à -O0/-O2 sous UBSan, vérifie
les refus sans signal, le choix du plus ancien tampon libre,
les transferts de fence et exactement un réveil après chaque détachement
réussi. La parité reproduit le changement depuis la source épinglée.
**F05 reste ouvert** : ce test ferme le sous-chemin « détachement sans réveil »,
pas toute la progression HLE/IPC / présentation.

## F05 — 22 octobre : conserver la frame réelle jusqu'à la notification

**Source native :** `vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`.
`QueueBuffer` construisait une `BufferItem` complète, mais vidait son
`graphic_buffer` et remplaçait son `slot` par `INVALID_BUFFER_SLOT` juste avant
d'appeler `OnFrameAvailable` ou `OnFrameReplaced`. Cela rompait le contrat de
notification avec tout consommateur utilisant les champs du paramètre.
Le consommateur `ConsumerBase` actuellement retenu ignore ces champs dans
ses callbacks : **aucun gain de FPS ou déblocage FC27 n'est donc prétendu**.

La correction conserve la frame et sa référence au buffer jusqu'à la fin
de la notification **hors verrou**, sans supprimer de fence ni modifier la
politique de remplacement des frames. Un test C++ extrait le dispatch
de la méthode réellement sélectionnée, compile à O0/O2 sous UBSan et
vérifie les callbacks « available » et « replaced », l'identité de la
frame/buffer/slot et l'absence de double notification. La parité
`check-vendor-consolidation-debt.py` est mise à jour ; fast gate et
prévalidation doivent rester verts. **F05 reste ouvert** jusqu'à la preuve
de progression de bout en bout.

## F01/F05 — 22 octobre : limiter les logs d'attente normale de NVNflinger

Dans `BufferQueueProducer::WaitForFreeSlotThenRelock`, le cas `queue.size() > max_buffer_count` représente une attente de retour de capacité, pas une erreur de service. Sa journalisation `LOG_ERROR` se produisait à chaque itération de la boucle et pouvait créer des écritures de log en rafale lorsque le consommateur était en retard, même sans diagnostic détaillé. Elle passe à `LOG_DEBUG`, tout en conservant la condition d'attente, les réveils, l'ordre des frames et les fences à l'identique. L'oracle de parité maintenue vérifie la substitution exacte depuis la source épinglée. **Amélioration préventive du coût CPU/log ; aucun gain FC27 ni correction de freeze n'est encore revendiqué.**

## F05 — 22 octobre : lecture des numéros de frame sous verrou

Le diagnostic de `DequeueBuffer` relisait `slots[*out_slot].frame_number` après la sortie de `core->mutex`, pendant qu'un autre producteur ou consommateur pouvait modifier les métadonnées du slot. Le numéro est maintenant capturé sous verrou à la sélection, puis actualisé dans le chemin de réallocation sous le même mutex. Seule cette copie est utilisée par `LOG_DEBUG`. Cela évite une lecture concurrente indéfinie et un diagnostic de frame incohérent, sans changer la propriété des buffers, les fences, la sélection du slot ni la synchronisation du jeu. L'oracle des sources maintenues reproduit chaque remplacement exactement depuis la version épinglée. **F05 demeure ouvert ; ce garde ne prouve pas un déblocage FC27.**

## F05 — producteur unifié en release et DEV

La sélection précédente du producteur épinglé en release omettait les correctifs NVNflinger retenus en DEV. L'introduction d'une seconde unité standard avait réparé la livraison, mais doublonnait le code et rendait l'inventaire architectural obsolète. Désormais **une seule source maintenue** (`vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`) est sélectionnée par CMake dans les deux profils. Le bloc `EDEN_NVNF_DEQUEUE_PROFILE` n'est compilé qu'en DEV et protège uniquement le chronométrage de dequeue ; les notifications, la préservation des métadonnées des frames et les gardes mémoire sont communs. Le fichier standard redondant est retiré, sans toucher à la source épinglée. Le catalogue d'architecture conserve ainsi sa cardinalité historique.

La parité exacte des sources et les tests hôte vérifient l'intégration. **F05 reste ouvert** : sélection native et compilation CI ne prouvent pas encore la progression de la simulation sur console.

## F01/F05 — 22 octobre : horloge de buffer uniquement lorsque l'historique est actif

Le chemin `BufferQueueProducer::QueueBuffer` du moteur sélectionné demandait `Common::g_wall_clock.GetTimeNS()` à chaque queue de frame, bien que `enable_buffer_history` soit désactivé par défaut. La correction lit le paramètre une seule fois sous le mutex existant et n'échantillonne l'horloge que si l'historique est actif. Le numéro de frame, le `queue_time`, les fences, les callbacks et les changements d'état restent inchangés. Un témoin hôte compile le fragment réel et exécute les deux configurations (`-O0`, `-O2`, UBSan), ajouté à la prévalidation et au fast gate. **Objectif : supprimer un coût inutile du chemin chaud ; aucun gain FPS PS5 ou déblocage FC27 n'est déduit de ce contrôle.**

## F01 — 22 octobre : réutilisation bornée des samplers par draw

`GraphicsPipeline::ConfigureImpl` invalidait sa petite mémorisation dès qu'un handle de sampler différent intervenait, puis la recréait à chaque étage shader. Or l'identité du sampler ne peut changer pendant cette configuration sous les deux mutex invités. Une table directe de 16 entrées sur la pile réutilise maintenant les identifiants correspondant à des handles non consécutifs et entre les étages **du même draw**, sans allocation ni identité rémanente entre draws. Les collisions ne compromettent rien : elles entraînent seulement une nouvelle recherche `GetSamplerId`. L'ordre des vues, les samplers dans les descripteurs, les invalidations et les locks restent identiques. Le test hôte exécute la logique C++ sélectionnée (table vide, A/B/A, passage d'étage, collisions, nouveau draw, même vue avec samplers différents) en `-O0` et `-O2`, avec UBSan. **F01 reste ouvert : économie de recherches démontrable, baisse de latence/FPS sur console non mesurée.**

## F05 — 22 octobre : insertion idempotente dans la pile de composition

Le chemin sélectionné `SurfaceFlinger::AddLayerToDisplayStack` permettait plusieurs insertions d'une même couche (`consumer_binder_id`) sur un même affichage. Le compositeur parcourt la pile à chaque frame, de sorte qu'une seconde insertion double inutilement le parcours et la composition de la même image. La source `vendor/encore-active/eden-surface-lifecycle/src/core/hle/service/nvnflinger/surface_flinger.cpp` refuse désormais une insertion si cet identifiant existe déjà **dans cet affichage uniquement**. L'ordre des autres couches et la possibilité d'une couche sur plusieurs affichages restent intacts. L'installateur de source active vérifie l'ordre de cette garde, et `tools/check-surface-lifecycle.py` compile et exécute les méthodes réelles : doublons, deux affichages, binder invalide, détachement et fences sans double libération.

**F05 reste ouvert :** correction d'une anomalie réelle de gestion des couches, mais rien dans les anciennes traces ne prouve que FC27 envoyait une commande d'attachement dupliquée. Il reste à démontrer la progression HLE/IPC→présentation de bout en bout.

## F02 — 22 octobre : invalidations de blocs JIT hors du verrou de publication

Les méthodes de JIT **A32** et **A64 standard** maintenues tenaient `invalidation_mutex` pendant `emitter.InvalidateCacheRanges` ou le vidage complet (`block_of_code.ClearCache` et `emitter.ClearCache`). Ce verrou protège en réalité l'arrivée des demandes depuis les autres threads. Le JIT partagé expérimental effectuait déjà un instantané des demandes, puis exécutait les invalidations après avoir rendu le verrou.

Les deux modes de release utilisent désormais **la même séparation** : sous verrou, effacement du bit de halt, capture et retrait atomique du flag de vidage complet et des plages (par `ranges.swap`) ; hors verrou, invalidation effective et restauration RSB. Les demandes arrivées durant l'exécution restent dans la file pour la prochaine itération au lieu d'être effacées à la fin de l'ancienne invalidation. Les compteurs DEV sont associés au snapshot réellement traité.

Le nouveau test `tools/check-native-jit-invalidation-snapshot-host.py` compile les corps des trois méthodes depuis les sources réelles A32/A64, en `-O0`/`-O2`, release et profil DEV. Il déclenche une invalidation **réentrante pendant le traitement**, puis vérifie que le mutex est libre, que les demandes suivantes survivent, que la plage exacte est appliquée et que le vidage complet n'efface pas les nouvelles demandes. Tests ajoutés au fast gate et à la prévalidation. **F02 reste ouvert : réduction du temps passé sous verrou démontrable, mais effet réel sur les pics de compilation et FPS non mesuré sur console.**


## État de qualification technique — 22 octobre, après correctif F02

- **HEAD moteur vérifié :** `e96d474` (les commits `b907007` à `e96d474` réparent uniquement les oracles/test fixtures, sans autre changement A32/A64 depuis `a607654`).
- **Fast gate : réussi** [39860743923](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39860743923). Source-extracted A32 et A64 : cas de vidage complet et de nouvelle invalidation pendant l'ancien traitement, `-O0` et `-O2`, release et DEV.
- **Prévalidation complète : réussie** [39860743911](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39860743911).
- **Build PS5 source moteur `a607654` : réussi** [39858896077](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39858896077). Une recompilation explicite de la source courante est demandée séparément, et son résultat n'est pas anticipé.
- **CodeQL C++ : en cours** [39860743939](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39860743939), alors que Python et Actions sont réussis. Ne pas annoncer CodeQL entièrement vert avant la fin.
- **F02** : sous-mécanisme d'invalidation concurrente corrigé et testé. Les durées globales de compilation JIT et l'effet sur les saccades restent non mesurés.
- **F01** : dans `PrepareDraw`, la section sous mutex inclut `ConfigureImpl` **mais aussi** les états dynamiques et l'enregistrement des draws. Elle ne doit pas être libérée prématurément : `DrawIndirect` accède à `buffer_cache`, et la durée de vie des vues/descripteurs d'un draw direct dépend de l'ordre de publication des commandes. Les anciennes mesures désignent la contention sur `buffer_cache.mutex`, mais ne prouvent pas qu'un déplacement de ces opérations hors verrou serait correct. Tant qu'une extraction sûre des données et des barrières n'est pas démontrée, **aucun unlock spéculatif**.
- **F03–F06** : restent ouverts. Aucun correctif de texture ni contrôle de match ne peut être considéré comme complet sur la seule base d'une compilation.

**Décision avant F07 :** continuer les preuves F01–F06 sans nouvelle session PS5, et conserver les tests de fidélité des caches, du HUD et des commandes. Les résultats de CI n'établissent ni une cadence stable des frames invitées ni un HUD correct.

## F04 — 22 octobre : bounds de la page-table BufferCache en cas d'adresse invalide

Le chemin maintenu `BufferCache::IsRegionRegistered` parcourait une table limitée à 16 Gio tout en calculant `addr + size` sans garde supérieure. Sur une adresse malformée, une plage débordante ou dépassant cette limite pouvait mener à un index hors de la table. Une garde rejette désormais les plages vides, hors domaine et non représentables avant tout calcul de borne haute ou accès `page_table[]`, sans changer le parcours des plages valides. Le test source-extrait `check-ps5-buffer-region-multipage-host.py` vérifie les plages valides multipages, les plages croisées au-delà de 16 Gio, les adresses proches de `UINT64_MAX` et zéro octet en `-O0` et `-O2` (UBSan). Les deux oracles de reproductibilité recomposent exactement la nouvelle source à partir du backport épinglé. **F04 reste ouvert :** cela prévient un accès hors limites, mais n'établit pas une correction visible des maillots ou du terrain FC27.

## F03/F05 — 23 octobre : ne jamais recomposer un buffer déjà libéré

`HardwareComposer::CacheFramebufferLocked` (source originale épinglée) renvoyait `CachedBufferReused` après l'échec d'acquisition d'un **ancien** buffer déjà libéré. Lorsque une autre couche présentait une image récente, la composition pouvait inclure ce buffer périmé, désormais disponible pour l'écriture du producteur. La nouvelle source maintenue `eden-surface-lifecycle/src/core/hle/service/nvnflinger/hardware_composer.cpp` renvoie `NoBufferAvailable` uniquement dans ce cas, conservant le cache encore acquis, la nouvelle acquisition et le traitement normal des couches indépendantes. `ComposeLocked` saute déjà explicitement les résultats `NoBufferAvailable` avant la lecture du pointeur de buffer.

L'installateur applique **les deux unités complètes** `SurfaceFlinger` et `HardwareComposer` dans l'arbre Eden temporaire ; il vérifie la source originale épinglée par empreinte Git, reconstruit les octets attendus du compositeur, contrôle les deux entrées avant toute écriture et rejette toute modification extérieure. Le test hôte `check-surface-lifecycle.py` exécute la méthode C++ extraite, avec premier manque, réutilisation pendant acquisition, libération puis nouvel échec, nouvelle image et couche indépendante, en `-O0` / `-O2` (UBSan).

**F03 et F05 restent ouverts** : le chemin de référence périmée est corrigé au niveau source, mais la preuve complète HUD et la progression IPC→présentation doivent encore être établies ; ce défaut n'est pas formellement relié aux anciennes traces FC27.


## Cartographie et build du correctif compositeur — 23 octobre

La nouvelle unité native `hardware_composer.cpp` est enregistrée sous le contrat **N23** dans `docs/EDEN_CORE_AUDIT_DEPENDENCIES.md` et `docs/EDEN_ACTIVE_SOURCE_CATALOG.md`. L'inventaire de revue source passe à **493 fichiers, dont 431 traités et 62 sources du lanceur à examiner séparément**. Le nombre de sources moteur restant à parcourir systématiquement reste zéro ; le nombre de corrections encore nécessaires reste inconnu.

La validation complète du correctif de buffer libéré nécessite un **build natif sur le HEAD contenant aussi l'installateur corrigé**, et non sur `ac04f33` (script initial) ou `d1358ab` (premier inventaire). Les anciens résultats ne doivent pas être attribués au nouveau HEAD. F03/F05 restent ouverts tant que l'intégration native et le rejeu global n'ont pas réussi.

## Reprise N23 — contrôle hôte réussi, build final réémis

Le fast gate du code `642f80f` est **vert** ([exécution 39865536857](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/39865536857)). Le test compilant `HardwareComposer::CacheFramebufferLocked` depuis la source maintenue et la migration des deux TU passent ; le graphe d'architecture et l'inventaire passent le contrôle initial de prévalidation. Le tableau quantifié du graphe a été recalculé séparément : **480 contrats recensés, 410 SOURCE/OPEN** ; ceci ne correspond pas à des fichiers restant à optimiser.

La compilation native de `157e7e0` a été lancée **avant** la dernière rectification du tableau de graphe. Un build complet est donc redemandé sur cette version cohérente. Ne pas considérer la qualification native F03/F05 comme obtenue avant la fin de ce nouveau build.

## F03/F05 — 23 octobre : rejeu réel des couches composées

Le témoin `tools/check-native-hardware-composer-liveness-host.py` compile **les quatre méthodes C++ du HardwareComposer effectivement installées**, plus la fonction de cadence, en `-O0` et `-O2` sous UBSan. Seuls les objets périphériques (buffers entrants, display GPU et deux consommateurs) sont simulés. Le scénario alterne une couche jeu à cadence double, un HUD indépendant, le maintien d'un buffer encore acquis, sa libération, une acquisition manquante, un nouveau HUD et un nouveau jeu. Les identifiants des images réellement présentées sont comparés pour exclure la réintroduction d'une image libérée. Le test est appelé par le fast gate et la prévalidation via `check-surface-lifecycle.py`.

**Portée :** une preuve de non-régression du compositeur sur ce scénario HLE, non une preuve du comportement du jeu FC27, de l'IPC complet ou de la synchronisation effective de la console. F03/F05 restent ouverts.


## F03/F05 — 23 octobre : borne extrême de cadence du compositeur

Dans `NormalizeSwapInterval`, l'extension des intervalles négatifs évaluait `1 - swap_interval` en entier signé **avant** conversion flottante. Pour `INT32_MIN`, cela débordait en C++ (UBSan). La conversion a été déplacée avant la soustraction, sans changer le comportement des intervalles usuels ; la transformation est désormais contrôlée octet par octet depuis la source épinglée. Le rejeu natif teste `INT32_MIN`, `-1` et `0` en `-O0`/`-O2`, et doit faire échouer l'ancienne fonction sous UBSan. L'installateur accepte exactement la version maintenue précédente pour mettre à jour les staging temporaires, sans accepter de variante inconnue. **Il s'agit d'une correction de sûreté du calendrier de présentation, pas d'une preuve de gain de FPS ni d'une clôture F03/F05.**


## F05 — 23 octobre : un seul affichage par identifiant

`SurfaceFlinger::AddDisplay` créait auparavant une nouvelle pile à chaque appel,
même pour un `display_id` déjà présent. Or `FindDisplay` retourne la première
pile, tandis que `RemoveDisplay` efface toutes celles portant cet identifiant
après n'avoir libéré que les buffers de la première. Cela pouvait produire un
état de propriété incohérent en cas de création en double.

La source maintenue refuse désormais une création répétée avant
`emplace_back`, en conservant l'ordre et le comportement des identifiants
distincts. L'oracle `install-vendored-surface-lifecycle.py` vérifie le
nouveau garde-fou et n'autorise que les empreintes exactes des versions
maintenues précédentes lors d'un staging. Le test hôte
`check-surface-lifecycle.py` exerce deux créations identiques, l'attachement
d'une couche, son unique libération et la création d'autres affichages.

**Commits de ce sous-chemin :** `4cb3fcf` (source), `c955eea` et
`74229dc` (oracles/tests), `767a5d5`, `1475299` et
`8d45284` (migration et corrections de témoin). Un témoin C++ local
couvrant le scénario de doublon a réussi sous UBSan en `-O0`/`-O2`.
La validation complète du test source-extrait, la prévalidation et le
build natif doivent encore être vérifiés pour le dernier HEAD ; ne pas
confondre le témoin local avec une preuve CI.

**Portée :** sûreté d'un cas de duplication des piles d'affichage ;
aucune trace historique FC27 n'établit que cette duplication se produisait.
Aucun gain de FPS, de fraîcheur du HUD ou de déblocage du match n'est
revendiqué. **F05 reste ouvert** jusqu'au rejeu IPC→buffers→fences→présentation.


**Validation native demandée pour ce lot :** le workflow de build sur la branche
`dev/ps5-sparse-jit` est déclenché par un commit portant `[full-build]`.
Cette demande ne préjuge pas du résultat du fast gate, de la prévalidation,
de CodeQL ou du package natif. Aucun test console F07 n'est demandé.


## F04 — 23 octobre : scissor Vulkan, bornes de coordonnées invitées

La source maintenue réellement sélectionnée `vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp`
contenait des soustractions 32 bits `src.max_x - src.min_x` et
`clip_height - src.max_y` susceptibles de déborder en cas de valeurs de
registres invitées extrêmes. Le décalage dépendait également d'un compteur
`down_shift` sans borne. Un rectangle incorrect peut clipper un draw et
faire apparaître une portion de géométrie manquante, sans qu'une perte
de descripteur ou un draw rejeté soit nécessaire.

Le correctif `60a6661` calcule les différences en 64 bits et borne la
conversion au domaine `s32`. Pour les produits ordinaires représentables et
les décalages valides, il conserve les règles 32 bits originales, y compris
le traitement existant des coordonnées négatives ; la voie large ne couvre
que les valeurs hors plage ou les décalages excessifs.

Le témoin `tools/check-ps5-scissor-extremes-host.py` extrait la fonction
active et l'ancienne fonction épinglée, exige leur identité de résultat sur
un ensemble de rectangles ordinaires, et vérifie sous UBSan que la source
antérieure échoue sur `INT32_MIN`/`INT32_MAX`, quand la version maintenue
ne déborde pas. Les variantes `-O0` et `-O2` sont intégrées à la
prévalidation. Un témoin local de même logique a réussi avant intégration ;
l'exécution CI source-extraite et le package natif restent à vérifier.

**Effet performance non revendiqué :** dans un microbenchmark hôte
non représentatif du GPU PS5, la voie sécurisée a été environ 3–4 ns
plus coûteuse par appel que la voie historique sur l'échantillon ordinaire.
Le gain de sûreté ne clôt donc ni les saccades F01, ni la fidélité FC27 F04.
Aucun test console demandé avant F07.


## F01/F05 — 23 octobre : notification de construction Vulkan sans fuite

**Source native sélectionnée :** `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp`
(`GraphicsPipeline::GraphicsPipeline`). Avant ce lot, `MarkShaderBuilding`
était exécuté au début du constructeur, tandis que le seul
`MarkShaderComplete` garanti était dans la fonction de compilation,
créée après la préparation des métadonnées shader, des layouts,
des allocations de descripteurs et autres opérations pouvant lever
une exception. Un échec pendant cette préparation ou pendant
`QueueWork` pouvait laisser une construction comptabilisée
sans notification de fin.

La correction `c5652a3` ajoute une garde RAII au constructeur :
tant que la construction n'a pas été confiée à la fonction synchrone
ou au worker, toute sortie exceptionnelle appelle
`MarkShaderComplete`. Le constructeur achève maintenant
`ConfigureFunc(spv_modules, stage_infos)` **avant**
`worker_thread->QueueWork`, évitant qu'un worker lancé tôt
voie cette fonction de configuration incomplète. Une fois la mise en
file réussie, le worker conserve son `SCOPE_EXIT` original pour
publier `is_built`, réveiller `build_condvar` et notifier la fin
même en cas d'échec de validation ou de compilation.

**Preuve :** `tools/check-ps5-pipeline-build-handoff-host.py` extrait
la garde réelle et vérifie les invariants d'ordre du constructeur
natif. Son témoin C++ simule les échecs de préparation et de
queue, la compilation synchrone/asynchrone, un worker en échec
et l'absence de notificateur ; son témoin négatif démontre la fuite
de notification de l'ancien comportement. Les cas simulés ont
réussi localement sous GCC/Clang, `-O0`/`-O2` et UBSan. Ce
témoin ne compile pas la totalité de `GraphicsPipeline` ni Vulkan :
la prévalidation et le build natif doivent encore être confirmés.

**Portée limitée :** correction d'un risque démontrable d'attente
prolongée sur notification absente et d'initialisation asynchrone
incomplète. Aucun ancien log FC27 ne prouve que la création
d'un pipeline lançait l'une de ces exceptions. Cette correction
ne valide ni un gain de FPS, ni l'absence de freeze en match.
**F01/F05 restent ouverts**, ainsi que F02–F04/F06.


## F04 — 23 octobre : contrôle strict de parité des coordonnées négatives

Un audit supplémentaire du chemin `GetScissorState` a confirmé un point
subtil des promotions entières en C++ : l'opérande `up_scale` est
`u32`, donc l'expression historique `value * up_scale` suivie du
décalage se comporte en **non signé**, y compris lorsque `value < 0`.
Remplacer ce décalage par un décalage arithmétique signé changerait
la géométrie d'un titre valide. Cette variante a été rejetée puis le
comportement épinglé a été restauré, au lieu de faire passer une
rupture visuelle pour une optimisation.

Les commits `5a8a26f` et `aff4105` maintiennent donc le décalage
historique et ajoutent un témoin explicite : pour un offset
`-96`, `up_scale=1` et `down_shift=1`, le rectangle épinglé
et maintenu renvoient tous deux `-1` après la borne historique.
Une reproduction locale des deux méthodes C++ a été compilée et
exécutée sous **Clang et GCC**, `-O0`/`-O2`, UBSan : **3516**
configurations de rectangles ordinaires/extrêmes validées pour chacune
des quatre combinaisons. Ce test indépendant n'est pas une exécution
de la suite CI complète ni une mesure de performance réelle.

La protection contre les soustractions 32 bits overflow et le
décalage hors plage est conservée. **F04 reste ouvert** tant que la
fidélité du rendu invité n'est pas démontrée. Ne pas annoncer de
résolution du HUD, des maillots ou du terrain de FC27.


## F02 — 23 octobre : purge JIT sous verrou, y compris en pression mémoire

Les interfaces maintenues `a64_interface_standard.cpp` et
`a32_interface_native.cpp` utilisaient `invalidation_mutex` pour les
demandes de vidage provenant d'autres threads, mais **deux chemins
internes chacun** modifiaient directement le booléen partagé
`invalidate_entire_cache` : moins de 1 Mio de code disponible,
et nouvel essai après `std::bad_alloc` de `EnsureMemoryCommitted`.
Ces quatre écritures hors mutex pouvaient se produire en parallèle
avec `InvalidateCacheRange` / `ClearCache` et constituaient une
course de données (undefined behavior en C++).

**Correction appliquée :** les quatre chemins passent désormais par
`ClearCache()`, qui détient le mutex pour déclarer le vidage complet
et publier le signal `CacheInvalidation`, puis exécutent la méthode
`PerformRequestedCacheInvalidation` existante. La remise à zéro
des plages, le snapshot hors verrou, la taille limite d'1 Mio et le
profil standard par cœur restent inchangés. Aucun réglage du cache
JIT ou mode expérimental n'est activé.

**Contrôles :** `tools/check-native-jit-invalidation-snapshot-host.py`
recherche désormais exactement les **deux chemins** de purge de
chaque source A32/A64, sans écritures directes dans l'état de vidage.
Son témoin C++ utilise les méthodes d'invalidation extraites des
sources, vérifie la publication sous un mutex instrumenté,
rejoue une écriture invitée provenant d'un autre thread pendant
`emitter.ClearCache()` et rejette l'ancienne affectation sans verrou
par un contre-test négatif. Le contrat de reproduction octet à octet
du code A32 épinglé dans
`tools/check-maintained-a32-native-interface.py` a été actualisé
afin de garantir que la source réellement compilée intègre le
correctif sans modifications non revues.

**Statut :** source et tests poussés ; exécution de la suite CI,
ASan/UBSan du build complet et qualification native restent à
confirmer. Ce correctif supprime une course de données à
l'invalidation et **ne démontre pas** qu'il supprimera les
pics de recompilation FC27. F02 reste ouvert.



## F01 — 23 octobre : allocations de snapshots GPU hors verrou partagé

**Source active :** `vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp`.
`GraphicsPipeline::ConfigureDraw` mémorise la charge utile des descripteurs
Vulkan dans `last_descriptor_payload`. Son premier `assign` pouvait
réserver de la mémoire alors que `PrepareDraw` détenait simultanément
`buffer_cache.mutex` et `texture_cache.mutex`, contribuant à la durée
de détention du verrou lors de la première utilisation d'un pipeline.

Le correctif `e633f3d` déplace **uniquement la réservation de capacité**
dans `GraphicsPipeline::PreflightDescriptorScratch`, déjà exécuté
par le propriétaire GPU **avant** les deux mutex. La réservation est
limitée au nombre immuable `num_descriptor_entries` et seulement aux
pipelines qui conservent réellement un snapshot (buffer de descripteurs
ou ensembles classiques, hors mode push-only). Les vues TIC/TSC,
les lectures mémoire invitées, les uploads et le contenu du payload ne
sont pas lus ou copiés hors du verrou. La branche de repli imbriquée
conserve ses gardes de réentrance.

Le générateur `tools/prepare-vulkan-port.py` et la déclaration C++
native générée ont été mis en cohérence (`4454bbf`), de sorte
qu'un staging natif ne réintroduise pas l'ancienne signature `const`.
Le test `tools/check-ps5-graphics-payload-preflight-host.py`
(`72265ac`, renforcé par `a9743ef`) extrait la vraie méthode
maintenue, vérifie l'identité octet à octet du corps dans le générateur,
et compile sa logique avec un allocateur instrumenté qui refuse une
allocation sous le double verrou. Il contrôle l'ensemble classique,
le buffer de descripteurs, le push-only, le pipeline vide et le
scratch imbriqué ; l'ancien code provoque le refus attendu.

Une **reproduction locale** de la méthode et de son allocateur a
réussi sous Clang et GCC, `-O0` et `-O2`, UBSan. Le script
source-extrait est intégré à la prévalidation ; il attend encore
une preuve CI sur le dernier HEAD. Ce changement retire une allocation
de la section critique lors de certaines premières utilisations,
mais **aucun gain de FPS, de `pair_held` ou de `late50` sur console
n'est encore démontré**. F01 reste ouvert.


## F01/F04 — 23 octobre : suppression de la décision feedback pour les draws sans texture

La source native sélectionnée `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h`
contient désormais un chemin direct lorsque `CheckFeedbackLoop` reçoit une liste
`views` vide. Aucun échantillon ne pouvant référencer un attachement,
il n'est pas nécessaire de comparer la clé des vues précédentes, de
réévaluer les rendertargets ou de construire un nouveau snapshot.
Le cache de décision et les numéros de série sont remis dans l'état
`false` existant, afin que **le draw texturé suivant** recalcule
obligatoirement la décision de barrière.

Le changement est présent dans la source maintenue (`92150c6`) et dans
son backport épinglé (`2fd4743`), pour éviter un écart entre le build
natif et l'arbre de développement. L'oracle du patch source est renforcé
(`69941db`), et `tools/check-ps5-feedback-loop-empty-fastpath-host.py`
(`7f75349`) compile la fonction réellement maintenue et rejoue
un ensemble de transitions `depth→other→depth→empty→depth→color-only→depth`
avec et sans `PS5_NATIVE`, `-O0`/`-O2` sous UBSan.

Une reproduction locale indépendante de ces transitions, compilée sous
Clang et GCC, a passé **huit combinaisons** (compilateur × niveau
d'optimisation × mode natif/amont). La suite native complète et le rejeu
du patch sur la totalité des fichiers épinglés restent à confirmer.

**Impact limité :** suppression d'un travail non nécessaire sur les draws
sans image ; aucune donnée de scène FC27 ne permet encore de quantifier
un gain de `pair_held`, `late50` ou FPS. Ce n'est pas une preuve de
correction des textures de maillots ou du HUD. F01, F03 et F04 restent ouverts.


## F01 — 23 octobre : hypothèse des prévalidations 1024 rejetée

La revue de `GuestDescriptorQueue::PreflightLargeGuestDraw` révèle un retour immédiat lorsque `entries <= 0x400`. `DescriptorEntryReservation()` renvoie précisément `0x400` pour un shader sans descripteur. Les six précontrôles supplémentaires ne pouvaient donc pas provoquer le `WaitWorker` soupçonné. Les changements d'optimisation correspondants ont été **annulés** après cette contre-vérification, et le témoin reposant sur cette fausse hypothèse retiré de CI. Aucun gain de FPS ni de contention n'est revendiqué sur cette piste ; F01 reste ouvert.


## F01 — 23 octobre : précontrôle exact des petits descripteurs après resélection

**Défaut établi dans la logique du code :** `UpdateDescriptorQueue::Acquire`
attend le worker lorsque `used + required_entries >= frame_payload_size`.
Cependant, `PreflightLargeGuestDraw` ignorait toute réservation
`entries <= 0x400`, même lorsqu'une attente était nécessaire. Cela
pouvait laisser un nouveau shader à petits descripteurs découvert
**après un premier drain et une resélection de pipeline** arriver à
`Acquire` sous le double verrou GPU et y déclencher `WaitWorker`.

Une première hypothèse, selon laquelle les shaders sans descripteurs
attendaient inutilement, a été réfutée : leur nombre de secours
`0x400` était explicitement ignoré par le précontrôle d'origine.
Cette modification a été annulée, avec retrait de son test invalide.

Le correctif retenu est différent : `PreflightExactGuestDraw`
reproduit maintenant la condition exacte d'`Acquire` pour **tout
nombre positif** d'entrées inférieur à la taille de la file. Il est
appelé sur trois sites graphiques et trois sites compute,
**uniquement si `HasDescriptorEntries()` est vrai**, avant de prendre
les mutex des caches. Les changements sont synchronisés dans
`vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp` et
`tools/prepare-vulkan-port.py` ; le test de provenance du générateur
doit empêcher le staging d'une ancienne implémentation.

**Témoin :** `tools/check-ps5-exact-descriptor-preflight-host.py`
extrait la méthode exacte issue du générateur et les six conditions
C++ maintenues. Il vérifie le seuil `Acquire` sur une petite file,
le contre-exemple historique (`4095/4096` entrées utilisées +
`1` entrée demandée), et les resélections vers un shader vide
ou de grande taille. Il est inscrit au fast gate hôte.
**Résultat d'exécution CI/native non confirmé** au moment de cette
mise à jour. Le cas reproduit est une possibilité de synchronisation
sous verrou ; les anciennes traces de FC27 ne permettent pas
d'attribuer un pic précis à ce chemin. **F01 reste ouvert.**


### F01 — ajustement final du seuil initial, source/en-tête natif vérifiés

La prévalidation initiale `PreflightGuestDraw` anticipait une réservation
fixe de **1 024 entrées**, même lorsqu'un pipeline graphique/compute
utilisait quelques descripteurs. Elle reçoit désormais
`pipeline->DescriptorEntryReservation()` et applique le seuil exact
`used + reserve >= frame_payload_size` de l'`Acquire` réel.
La valeur `0x400` reste disponible par défaut pour les autres appels
non revus. Les méthodes initiale et de resélection sont présentes
**à l'identique** dans `tools/prepare-vulkan-port.py` et dans
l'en-tête maintenu sélectionné
`vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h`.
Les deux sites initiaux et six sites de resélection sont présents
dans le rasterizer maintenu.

`tools/check-ps5-graphics-pipeline-aware-preflight-host.py`
a été adapté au paramètre supplémentaire ;
`tools/check-ps5-exact-descriptor-preflight-host.py` exige maintenant
la parité des deux méthodes dans l'en-tête et le générateur et vérifie
le précontrôle initial à la frontière de la file.

Une reproduction locale séparée du calcul a réussi sous GCC et
Clang, `-O0`/`-O2`, UBSan : **110 couples** remplissage/réservation
pour chaque configuration, contre-exemple historique inclus.
Ce n'est pas la suite source-extraite du dépôt, dont l'exécution
reste à confirmer. **Aucun gain en FPS n'est quantifié**, et les
attentes F01 autres que celles-ci restent ouvertes. La compilation
PS5 complète doit valider la cohérence des sources et du build
avant F07.


## 23 octobre — reprise F01–F06 sans nouveau test console

La dernière revue initiale recense **0 chemin moteur à parcourir de nouveau** ;
ce chiffre n'est toujours ni un compte de correctifs restant à écrire ni
une preuve d'optimisation FPS. Les **62 sources du lanceur** sont traitées
dans leur propre chantier. Les **six sorties F01–F06 restent ouvertes** tant
que les invariants complets du tableau initial ne sont pas démontrés.

Pour rendre les reprises diagnostiquables sans attendre le succès de tous les
contrôles génériques, `tools/check-fc27-six-gates-host.py` exécute maintenant
**douze témoins C++ source-extraits** indépendamment :

- **F01 :** réservation du payload avant mutex buffer/texture et déduplication
  de samplers ;
- **F02 :** invalidations JIT réentrantes A32/A64 et bornes du code JIT ;
- **F03 :** remappage TIC/TSC sans entrée et réutilisation correcte des couches
  HardwareComposer ;
- **F04 :** coordonnées scissor extrêmes et plages BufferCache multipages ;
- **F05 :** gestion des affichages SurfaceFlinger et réveil de producteur après
  détachement de buffer ;
- **F06 :** persistance de la conversion physique→guest au lancement et
  cadence HID du runtime.

Ce point de contrôle est exécuté dans la prévalidation hôte avec
`if: always()` : un échec indépendant de cartographie ou de reproduction de
source ne masque plus le résultat de chaque critère. **Il reste bloquant en
cas d'échec de l'un des douze témoins** et inscrit le résultat détaillé dans
le résumé du workflow. Un `HOST_SUBPATH_PASS` est un progrès de preuve
partielle, **pas une clôture de F01–F06**, ni un résultat PS5.

Le contrôle strict d'empreinte U13 a été remis à jour **après inspection des
six modifications** de `metadata_bridge.cpp` liées à la classification des
conteneurs. Le chemin CPU/GPU/JIT n'est pas modifié par cette revue et son
empreinte restera verrouillée. En parallèle, le fast gate de reproduction
Vulkan a signalé un écart entre le générateur et quatre sources maintenues
(`vk_graphics_pipeline.h`, `vk_graphics_pipeline_cost.cpp`,
`texture_cache.h`, `vulkan_rasterizer.cpp`) : **ne pas certifier la
parité/native de F01, F03 ou F04 sans résolution de cet écart**. Ne jamais
modifier l'oracle pour simplement ignorer la différence.

Le profil de livraison conserve le JIT normal, les verrous nécessaires, les
fences et les invalidations GPU. Aucun changement automatique de fréquence,
affinité, résolution, taille des caches ou file Vulkan. Une seule validation
matérielle finale demeure réservée à F07.


## 23 octobre — intégration des formats et compteur moteur restauré

Après la prise en charge des formats NSZ/XCZ, des modules directs et de
l'ExeFS, le registre d'audit historique à 493 fichiers n'était plus à jour.
Une comparaison exacte avec les objets de l'arbre Git de la branche a révélé
**11 nouvelles sources de code** : dix sont des unités de lecture, décompression
ou routage de formats ; la dernière est
`headless/prosperoeden/pe/ui/case_media_selection.hpp`, suivie dans le
périmètre UI. Aucun de ces onze fichiers ne constitue en lui-même un
correctif de saccades, de HUD ou de commandes FC27.

Au commit `540f4bb`, le nouveau registre distingue :

| Compteur de la première revue de code | Valeur |
| --- | ---: |
| Fichiers C/C++/headers détenus par Encore | **504** |
| Sources traitées, revues ou intégrées avec référence | **441** |
| Dont nouveaux propriétaires de formats, hors optimisations FPS | **10** |
| Première revue moteur restant à traiter | **0** |
| Première revue UI/launcher restant à traiter séparément | **63** |
| Nombre de correctifs moteur réellement encore nécessaires | **inconnu** |
| Critères FC27 F01–F06 techniquement clos | **0/6** |

La source et le test `tools/check-eden-optimization-coverage.py`
contrôlent désormais les dix nouveaux chemins par **empreinte Git exacte**,
preuve de sélection, référence à la prévalidation et distinction
native/hôte/en-tête. Voir
[la revue indépendante des formats](EDEN_FORMAT_SOURCE_REVIEW_2026-10-23.md).
Les **12 témoins hôte F01–F06** précédemment exécutés ont tous réussi,
mais la suite CI complète du dernier SHA demeure une qualification
indépendante. La reproduction Vulkan générateur/sources est passée dans
le fast gate de `d612c8c` ; des témoins de contrôle de préflight
compute ont été réalignés ensuite, sans modifier les fences ni désactiver
les verrous.

**Ne pas interpréter « 0 source moteur à revoir » comme « F01–F06
terminés ».** Les six critères restent à prouver au niveau bout-en-bout ;
F07 reste la seule validation physique sur PS5.


## 23 octobre — demande de qualification native du lot F01–F06

Le sous-contrôle source F01–F06 a donné **12/12 témoins hôte réussis**
sur la dernière base inspectée, et le registre exact a passé
`EDEN_OPTIMIZATION_REVIEW_BACKLOG_PASS` à 504/441.
La prévalidation complète et le fast gate demeurent des contrôles
**indépendants**. L'empreinte de la source A64 standard a été
réexaminée dans `tools/ci/check-final-engine-owner-contracts.py`
après l'introduction de deux purges via `ClearCache()` sous mutex.

La demande de compilation `[full-build]` est volontaire et porte
exclusivement sur la branche unique `dev/ps5-sparse-jit`.
Elle ne demande **aucun test physique de FC27 ni aucun essai sur PS5**.
Un artefact compilé prouverait la sélection du code native pour ce SHA,
**pas** une suppression des gels, du lag ou de la corruption visuelle.
F01–F06 restent ouverts et F07 demeure entièrement séparé.


## 23 octobre — reprise de la compilation native après validation des prérequis

Le [premier build natif déclenché au SHA `98291a0`](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/40027498597)
a exécuté les contrôles C++ JIT, paquets, formats NCZ, SDK et validation de
l'interface, mais a **échoué avant de lancer la compilation native**.
Trois contrats de source incompatibles avec le nouveau code ont été trouvés :

1. `tools/check-nlib-ui-recovery.py` cherchait l'ancienne fonction
   `fit_fallback_art` et interdisait `cover_crop`, alors que le front
   reconstruit est désormais imprimé en plein format dans les deux vues.
   Ce contrôle impose désormais le plein format et le même compositeur
   Library/launcher.
2. `tools/check-ps5-vulkan-cache-phases.py` attendait la déclaration
   `PreflightDescriptorScratch() const`. Le passage en méthode mutable
   est intentionnel : elle préalloue les vecteurs avant les deux mutex.
   Le test vérifie la signature courante sans relâcher l'invariant
   préallocation-avant-verrou.
3. La politique de noms d'étapes CI refusait la mention d'une bibliothèque
   tierce dans un workflow de capture du README. Le libellé est neutralisé
   et la prévalidation se déclenche désormais lorsque ce workflow change.

**Nouvelle compilation demandée volontairement** avec `[full-build]` afin
de vérifier l'intégration PS5 de tous ces changements. Elle ne remplace pas
F07 : aucun test console ni promesse de gain de FPS ne découle de la
réussite éventuelle du build. L'ajout du témoin F03 de vues NULL transitoires
sous deux slots TIC protège la sélection texture quand le GPU cache vient
à peine de recréer une vue valide.


## 23 octobre — correctifs de prévalidation et reprise du build PS5

La qualification native lancée sur `10991c3` a été bloquée **avant** le
compilateur PS5 par quatre assertions restées sur des contrats abandonnés :
la silhouette de jaquette à largeur variable, le test XCI-only de glyphes,
`PreflightLargeGuestDraw` après l'introduction du contrôle exact, et
la vérification de l'attente du ring descripteur. Les vérifications ont été
réalignées sur les **sources actives** sans suppression des verrous, des
synchronisations de textures ou du repli de taille historique.

La prévalidation a également identifié un défaut réel de reproductibilité
M07 : la variante DEV CPU→GPU différée n'avait pas hérité des protections
de clipping GPU du rasterizer natif. Elle est maintenant reconstruite à
partir de celui-ci en ne conservant que ses deux modifications de pont.
Cette variante **reste désactivée** sur les builds normaux.

Enfin, `eden-ps5-feedback-loop-no-depth-fastpath.patch` (modifié le
23 octobre) et l'unité maintenue `eden-backports/src/video_core/texture_cache/texture_cache.h`
(dernière matérialisation datant d'octobre 11) divergeaient : le patch
ajoutait le cas `views.empty()`, absent de la source possédée.
Le bloc est maintenant intégré, et `manifest.json` verrouille ses
nouvelles empreintes **SHA-256 source + patch**, sans désactiver le
rejeu octet à octet de `install-vendored-eden-backports.py --replay`.

**Build [full-build] demandé à nouveau** avec cette base corrigée. La
preuve attendue est la compilation/link native de ce SHA et la sélection
des sources actualisées, pas un nouveau test de FC27 sur matériel.
**F01–F06 demeurent ouverts (0/6)** et F07 demeure séparé.

## 24 octobre 2026 — F01 : masques uniformes identiques sous verrou

Le chemin natif `BufferCache::SetUniformBuffersState`, appelé par
`GraphicsPipeline::ConfigureImpl` pendant la possession conjointe des
mutex buffer/texture, réécrivait `enabled_uniform_buffer_masks` même
lorsqu'il était identique à la configuration précédente.

Le commit `04d7821` évite cette affectation lors des rebinding sans
changement, **sans** supprimer la mise à jour inconditionnelle du pointeur
`uniform_buffer_sizes` et **sans** toucher aux invalidations lors d'une
transition effective. La reconstruction de la source native depuis le
backport et le rejeu du code original sont vérifiés respectivement par
`check-vendor-consolidation-debt.py` et
`check-native-uniform-mask-rebind-host.py`.

**Preuve attendue du test source-extrait :** quatre appels, deux changements
de masques, donc quatre affectations dans la source d'origine et deux dans
la source maintenue, en profils avec et sans cache uniforme persistant et
sous O0/O2/UBSan. Cette réduction de deux affectations ne mesure ni le
temps de verrou, ni les FPS, ni les freezes sur la console.

L'analyseur `analyze-fc27-stutter.py` expose aussi la part
`pipeline_configure / pair_held` *uniquement* pour des fenêtres dont les
échantillons GPU sont appariés. Les relevés incomplets restent inconnus.
**F01 demeure ouvert** : aucun gain de contention FC27 après ce changement
n'a été constaté. Cette révision demande seulement la vérification CI et
la compilation native, pas de test utilisateur sur PS5.


## 24 octobre — papier unifié et rôles LaunchBox du dos manquant

Le dos reconstitué utilise les vrais médias distincts du catalogue embarqué :
`Fanart - Background` (fond de la partie haute), `Screenshot - Game Title`
(illustration de titre) et `Screenshot - Gameplay` (scène inférieure).
Aucun n'est substitué par la jaquette avant ou par une case noire. Les
catégories absentes laissent voir **un seul papier opaque** commun à la
bibliothèque et à la texture 3D. Le front utilise un crop UV `cover`
uniforme sans écrasement indépendant de sa largeur.

Le dos en bibliothèque atteint le pli droit sans bande plastique rajoutée ;
son ouverture reste à gauche. Les impressions officielles front/back restent
prioritaires sur la reconstruction. Le catalogue LaunchBox v6 est généré lors
du build natif et journalise séparément ses trois taux de couverture.
La composition est vérifiée par le rendu OpenGL réel et les tests hôte du
sélecteur, mais l'arrivée des images sur console n'est pas prouvée par la CI.

**Ne pas comptabiliser ces correctifs graphiques du launcher comme une
clôture des critères moteur F01–F06.**

## 24 octobre — contrôle du fallback de jaquettes et de sa texture GPU

Les corrections de la bibliothèque et du rendu 3D ont été mises à jour sur
`dev/ps5-sparse-jit` : une jaquette officielle référencée mais devenue
illisible cède la place à la reconstruction au lieu de montrer seulement le
papier uni. Si le fichier officiel devient disponible plus tard, il reprend
la priorité. Une page GPU provisoire, construite avant que toutes les scènes
locales soient décodées, peut maintenant être réimprimée **sur le même ID de
texture** après leur arrivée, sans dépasser deux pages pour le titre.

Le contrôle hôte `check-encore-case-media-selection-host.py` couvre la
politique de rafraîchissement (délai, réussite tardive, absence de boucle
incomplète), et vérifie les invariants de source de réutilisation du GPU.
La commande compile les tests C++ hôtes ; **elle ne valide pas, à elle seule,
le pilote GL PS5 ni les textures observées en jeu**.

Ces changements traitent la présentation des jaquettes du lanceur, **pas**
les objectifs d'émulation F01–F06, qui restent ouverts. Aucun chiffre de
fichiers « restant à optimiser » n'est inféré de cette intervention.


## 24 octobre — F01, chemin CPU propre du cache de buffers

**Sous-chemin corrigé (F01 reste INVESTIGATION).** Dans la source Eden
maintenue, `BufferCache<P>::SynchronizeBuffer` retourne directement un succès
de cache **sur PS5 uniquement** lorsque
`memory_tracker.IsRegionCpuModified(device_addr, size)` est faux. Le parcours coûteux des plages `ForEachUploadRange` et la construction
des copies sont alors évités. Pour une plage modifiée, le chemin antérieur
reste intact, y compris l'exclusion des octets possédés par le GPU, la
consommation des marques CPU et l'appel éventuel à `UploadMemory`.

- Source livrée à la compilation PS5 : `vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h`, copie CMake de la source maintenue.
- Source du rejeu : `vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h`.
  Les deux méthodes `SynchronizeBuffer` sont identiques ; l'ancienne version
  complète de chacune est retrouvée en retirant seulement la même garde F01.
- Rejeu natif : `headless/backports/eden-ps5-buffer-clean-upload-fastpath.patch`,
  intégré à `tools/apply-eden-backports.sh` et inscrit dans le manifeste avec
  la taille, l'empreinte du source actif et le hash du patch.
- Test source-extrait : `tools/check-ps5-buffer-clean-upload-host.py`, appelé
  par la prévalidation et le workflow de compilation native. Il vérifie les
  chemins CPU propres/modifiés, le chevauchement GPU et la plage nulle.
- Le harnais C++ source-extrait est programmé en O0/O2 avec UBSan dans
  les deux modes (PS5 et amont), et extrait maintenant la méthode de la
  **source réellement sélectionnée par CMake**. **Son exécution et son résultat
  ne sont pas vérifiés dans cette intervention**, tout comme le résultat des workflows
  GitHub, le build natif et l'effet réel sur les attentes `buffer mutex` de FC27.

**Ne pas clôturer F01** sur ce seul raccourci : les durées de contention
relevées en jeu exigent toujours un benchmark avant/après avec le même profil,
un rejeu concurrent des invalidations et la compilation native confirmée.
Les critères F02–F06 ne changent pas d'état et F07 reste la qualification PS5.


## 24 octobre — F01, capacité compute hors verrous GPU

Le chemin `RasterizerVulkan::DispatchCompute` réalisait encore la création et
l'agrandissement éventuel de deux `small_vector` de descripteurs au cours de
`ComputePipeline::Configure`, sous les verrous conjoints du cache de buffers
et du cache de textures. L'intervention conserve le traitement de ces
descripteurs **sous les mêmes verrous**, mais déplace la réservation des
capacités avant leur acquisition.

- `vk_compute_pipeline_cost.cpp` : compteurs de descripteurs immuables
  calculés lors de la construction du shader compute, stockage
  `thread_local` réutilisé et bail RAII indépendant pour chaque appel imbriqué.
  Une troisième imbrication utilise un stockage privé pour éviter toute
  corruption des listes parentes.
- `include/video_core/renderer_vulkan/vk_compute_pipeline.h` :
  `PreflightDescriptorScratch()` et tailles ajoutées uniquement sur PS5.
- `vulkan_rasterizer.cpp` : préallocation exécutée après les éventuelles
  attentes du worker et la dernière sélection du pipeline, **avant**
  `std::scoped_lock(texture_cache.mutex, buffer_cache.mutex)`.
- `tools/prepare-vulkan-port.py` : reconstruction stricte des mêmes deltas
  depuis la source épinglée ; aucun remplacement silencieux du générateur
  par les sources maintenues.
- `tools/check-ps5-compute-descriptor-scratch-host.py` : test extrait des
  sources, intégré aux prévalidations et au build natif, couvrant
  réentrance, conservation de capacité et isolation entre threads.

Un harnais C++ isolé reproduisant la classe et les scénarios de ce test est
passé avec Clang/GCC, O0/O2 et UBSan (quatre combinaisons). La parité
textuelle entre blocs sélectionnés et blocs du générateur a été vérifiée.
La prévalidation complète, le rejeu complet de `prepare-vulkan-port.py`,
la compilation PS5 et le gain mesuré sur FC27 ne sont **pas** encore
confirmés. F01 demeure ouvert ; les autres objectifs F02–F06 ne sont pas
clôturés par cette intervention.


## 24 octobre — F01, sampler compute à portée strictement locale

Le pipeline compute effectuait un `GetSamplerId(handle, true)` par
occurrence de sampler, même lorsque plusieurs textures utilisaient
le même index TSC dans un dispatch. Une table directe à 16 entrées,
initialisée à chaque `ComputePipeline::Configure`, évite les lectures
répétées. Chaque collision vérifie la clé entière, et aucun ID n'est
conservé entre dispatchs : la synchronisation de la table de samplers,
les changements de canal et les remappages sont donc respectés.

- `vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp` :
  cache local de samplers sous verrou, limité à `PS5_NATIVE` ;
  chemin non-PS5 inchangé.
- `tools/prepare-vulkan-port.py` : reconstruction depuis la source
  amont épinglée via ancres exactes, avec refus des divergences.
- `tools/check-ps5-compute-sampler-memo-host.py` :
  test source-extrait inscrit dans les deux workflows ; clés
  répétées, collisions modulo 16, nouvelle époque de descripteurs
  entre dispatchs et dispatch sans sampler.
- Harnais C++ isolé : Clang/GCC, O0/O2, UBSan : 4/4 réussis.
  Les dix contrôles de cohérence source/générateur passaient
  également lors de l'intégration.

**Non vérifiés :** l'intégralité du workflow GitHub, le rejeu complet
du générateur, le build natif PS5, le profilage sur FC27 et les
gains de latence. Aucun des critères de sortie F01–F06 n'est clos.


## 24 octobre — parcours des pages textures CPU/GPU bornés

**Correctif réel, sous-chemin F01/F03/F04 (critères encore ouverts).**
Le cache de textures Eden itérait les pages d'une région en calculant
`(addr + size - 1) >> YUZU_PAGEBITS`. Avec `addr=0, size=0`,
le calcul sous-débordait et pouvait entraîner un parcours démesuré.
Les régions dont la dernière adresse dépasse `UINT64_MAX` étaient également
susceptibles de revenir artificiellement au début de l'espace mémoire.

Un deuxième défaut se trouvait dans le même bloc : la branche destinée
aux callbacks `bool` utilisait `std::invoke_result<Func, u64>`
(type du *trait*), et non `std::invoke_result_t<Func, u64>`
(type de retour). La sortie anticipée sur première correspondance
était donc désactivée et le parcours continuait inutilement.

**Modifications PS5 seulement :**

- `vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache_base.h` :
  les parcours CPU et GPU rejettent les régions de taille nulle ou
  dont la dernière adresse déborde, et honorent à nouveau la sortie
  anticipée des callbacks booléens.
- `headless/backports/eden-ps5-texture-page-range-guards.patch` :
  reproduction du correctif sur le snapshot Eden épinglé,
  avec validateur dans `tools/apply-eden-backports.sh`.
- `tools/check-ps5-texture-page-range-host.py` :
  compilation des deux méthodes natives extraites, test des régions
  valides, des traversées entre pages, de l'arrêt anticipé et des
  plages nulles/débordantes ; vérification du patch Git sur la source
  épinglée. Appelé par la prévalidation et le workflow de build.
- Manifeste shipping et inventaire : empreintes et tailles mises à jour,
  sans modifier les sources upstream immuables.

Une reproduction locale de ces deux méthodes a réussi pour
**8 configurations** Clang/GCC x O0/O2 x PS5/non-PS5 avec UBSan.
La CI complète, le rejeu de tous les backports et le build
PS5 restent à confirmer. Il n'existe pas de trace attestant que
FC27 déclenche précisément la région nulle ou le bool-break path :
**ne pas clôturer F01/F03/F04 sans les validations du moteur et du jeu.**


## 24 octobre — F04, vues TIC et décalages de couche

Le chemin `TextureCache<P>::CreateImageView` reconstruisait le début
d'une texture à partir de `BaseLayer * layer_stride`, calculé en `u32`.
La multiplication pouvait donc tronquer un décalage de couche supérieur
à 4 Gio et la soustraction pouvait produire une adresse GPU sous-débordée.
Un `TryFindBase(...).value()` sans présence garantie pouvait également
interrompre la création d'une texture incomplètement mappée.

Sur **PS5 uniquement**, le décalage est désormais calculé en `u64`
et une adresse GPU inférieure au décalage est rejetée avant recherche
ou insertion d'image. Lorsque le sous-ensemble demandé n'existe pas,
`CreateImageView` retourne `NULL_IMAGE_VIEW_ID` : le chemin existant
de reprise des vues NULL peut retenter la création après remappage.
La création normale des vues et le comportement non-PS5 restent inchangés.

- Sources maintenues : `eden-backports/src/video_core/texture_cache/texture_cache.h`
  et `eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h`.
- `headless/backports/eden-ps5-texture-tic-layer-bounds.patch` :
  rejeu explicite contre la source Eden épinglée et validateur
  `validate_ps5_texture_tic_layer_bounds`.
- `tools/prepare-vulkan-port.py` :
  reconstitution stricte de la même méthode pour l'overlay Vulkan natif.
- `tools/check-ps5-texture-tic-layer-host.py` :
  test de la méthode source-extrait pour couches valides, décalage 4 Gio,
  adresse incorrecte et sous-ensemble manquant, avec patch `git apply --check`
  puis comparaison des versions shipping/native.
- Manifeste et inventaire : empreintes source/patch, bytes et preuve du
  chemin réellement modifié mis à jour.

Une reproduction C++ locale de la méthode et de ses cas a réussi sous
Clang/GCC en O0/O2, avec et sans `PS5_NATIVE`, UBSan activé
(8 combinaisons). Ce test **ne prouve pas** la compilation complète du
moteur, ni le retour du HUD en jeu. La CI globale, le rejeu intégral,
le build PS5 et la qualification FC27 restent requis. F04 reste ouvert.


## 24 octobre — F03/F04, invalidation des vues remappées

**Anomalie de cache vérifiée dans les sources, qualification PS5 ouverte.**
Après `TextureCache::UnmapGPUMemory`, l'ancienne image peut porter
`ImageFlagBits::Remapped` alors que les octets de sa table TIC n'ont pas
changé. `VisitImageView` conservait alors une vue déjà résolue sur cette
image et appelait `PrepareImageView` dessus. Ce chemin ne vérifiait pas
le drapeau `Remapped`, même si la recherche de nouvelles images sait
explicitement ignorer les images remappées.

La réparation **sur PS5 seulement** contrôle ce drapeau avant de
réutiliser une vue mise en cache. Elle recrée une vue si le backing
guest est de nouveau résident ; sinon elle enregistre une vue nulle et
invalide le cache de décision de synchronisation associé. Les vues
de type buffer ne passent pas par ce contrôle d'image, et les vues
normales non remappées ne sont pas recréées.

- Sources : `vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache.h`
  et `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h`.
- Rejeu : `headless/backports/eden-ps5-texture-remapped-view-rebind.patch`
  après les autres patches de texture, avec validateur dans
  `tools/apply-eden-backports.sh`.
- Générateur : transformation stricte de la version shipping en version
  Vulkan, en conservant le cas supplémentaire des associations
  de canal absentes, déjà géré par ce backend.
- Régression : `tools/check-ps5-remapped-texture-view-host.py`,
  inscrite en prévalidation et au workflow de build ; compile la
  méthode Vulkan extraite et vérifie vue normale, remap résident,
  remap indisponible puis rétabli, table TIC relue, mapping absent,
  vues buffer, et branche non-PS5.
- Empreintes source/patch et inventaire mis à jour.

La correspondance textuelle de la transformation shipping → Vulkan
a été vérifiée. **La nouvelle régression n'a pas encore de résultat
CI confirmé**, pas plus que la compilation native du moteur ou un
test du HUD FC27. F03 et F04 demeurent ouverts, sans déclaration de
résolution des textures observées en jeu.


## 24 octobre — F03/F04, remappage des cibles framebuffer

**Deuxième sous-chemin corrigé de la récupération après remappage GPU.**
La reprise d'une vue TIC ne couvre pas les vues de cibles de rendu :
`TextureCache::UpdateRenderTargets` peut suivre son chemin rapide si
`Dirty::RenderTargets` reste faux. Or `UnmapGPUMemory` marquait une
ancienne image `Remapped` sans marquer les attaches du framebuffer.

Le correctif PS5 inspecte, **uniquement lors du remappage**, les
`image_view_ids` de l'image concernée. Si une vue apparaît parmi les
attaches couleur actuellement actives, elle marque précisément
`Dirty::ColorBuffer0 + rt`. S'il s'agit de l'attache profondeur, elle
marque `Dirty::ZetaBuffer`. `Dirty::RenderTargets` n'est activé que
si une de ces attaches est effectivement touchée. Il n'y a donc
aucune reconstruction obligatoire de framebuffer pour une image
non attachée, ni pour les vues NULL. La prochaine mise à jour normale
doit alors retrouver le backing actuel au lieu de préparer l'ancien.

- `vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache.h`
  et `vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h`
  contiennent exactement la même méthode `UnmapGPUMemory`.
- Rejeu natif :
  `headless/backports/eden-ps5-texture-remap-target-invalidation.patch`,
  avec vérification dans `tools/apply-eden-backports.sh`.
- `tools/prepare-vulkan-port.py` conserve explicitement cette
  transformation, qu'elle soit déjà présente dans la source shipping
  ou appliquée à une source plus ancienne.
- `tools/check-ps5-remapped-render-target-host.py` vérifie
  le rejeu inverse puis direct du patch, et compile le corps réel de
  `UnmapGPUMemory` sur hôte pour les cas couleur, profondeur,
  vue absente, et image sans attache. Il est ajouté aux deux
  workflows CI.
- Les empreintes source et patch, ainsi que l'inventaire, sont actualisés.

Contrôles statiques effectués : 13/13, notamment méthode
shipping/Vulkan identique, patch exact et branche non-PS5 identique
à la version précédente. **Les résultats effectifs des workflows,
de la compilation PS5 et du rendu FC27 ne sont pas encore vérifiés.**
F03 et F04 restent ouverts.


## 24 octobre — F03/F04, association TIC absente du cache de canal

Le nouveau test de récupération des vues a mis en évidence une divergence
résiduelle entre les deux propriétaires des textures. Dans la source
shipping, `VisitImageView` pouvait appeler `is_remapped_view(it->second)`
alors que `it == channel_state->image_view_ids.end()`, si une association
de canal avait été supprimée sans changer le descripteur TIC.
Le backend Vulkan comportait déjà un garde-fou supplémentaire.

Le code PS5 shipping vérifie désormais la présence de l'entrée avant
tout accès et suit la même politique que Vulkan : reconstitution de
l'association si elle est valide, ou création d'un emplacement NULL.
Une entrée absente n'invalide pas fictivement un cache de feedback
contenant déjà une vue NULL. Le chemin non-PS5 reste inchangé.

- `headless/backports/eden-ps5-texture-missing-channel-slot-guard.patch`
  est appliqué **après** la réparation des vues remappées et des
  cibles framebuffer ; la chaîne shipping enregistre son empreinte.
- `tools/prepare-vulkan-port.py` transforme désormais la source shipping
  actualisée en la méthode native préexistante, sans dérive d'octets.
- `tools/check-ps5-remapped-texture-view-host.py` compile **les deux**
  méthodes, shipping et Vulkan, en O0/O2 et PS5/non-PS5 ; il retire
  les deux patches de vues dans l'ordre inverse avant de les rejouer.
- Vérification de cohérence shipping → Vulkan : 9/9 points satisfaits.

Les reproductions hôte isolées de la méthode native et du remappage des
cibles framebuffer sont réussies (Clang/GCC, O0/O2, les deux modes,
UBSan). Les tests du dépôt complet et son rejeu intégral ne sont
pas encore confirmés par CI, et aucun résultat PS5/FC27 n'est acquis.
**F03/F04 restent ouverts.**


## 24 octobre — F03/F04, contrôle de l'ordre complet des vues textures

L'empilement de quatre patches successifs sur
`src/video_core/texture_cache/texture_cache.h` était vérifié auparavant
essentiellement patch par patch. Un patch isolément correct peut néanmoins
devenir incompatible avec un patch suivant.

Un contrôle de correspondance textuelle des hunks a maintenant validé,
depuis la source shipping, **la suppression en ordre inverse des
quatre patches et leur réapplication en ordre normal** :
`tic-layer-bounds` → `remapped-view-rebind` →
`remap-target-invalidation` → `missing-channel-slot-guard`.
Le résultat obtenu reproduit le contenu final octet pour octet.
Le préfixe retrouvé est la source maintenue avant F04,
`117051` octets, SHA-256
`3c129bb7ecf389d6f95c852ac9afbf1956fcc6e31d19bbeccaef757228af450a`.

`tools/check-ps5-texture-ordered-backports-host.py` exécute la version
Git de cette validation : digest/bytes de source, SHA-256 des reçus,
ordre exact du script d'installation, `git apply --reverse --check`
puis `git apply --check`, et retour exact au blob maintenu.
Ce contrôle est ajouté à la prévalidation hôte et au workflow natif.

**Limites :** le contrôle textuel hors CI a réussi ; l'exécution
de ce nouveau script dans GitHub Actions, le rejeu intégral de tous
les backports et le build PS5 complet ne sont pas encore confirmés.
Aucun effet réel sur les textures FC27 n'est proclamé. F03/F04 ouverts.
