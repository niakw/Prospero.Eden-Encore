# Eden Encore — audit de 10 sources P0 : IPC, réveil, exécution et GPU

**20 octobre 2026 · base de revue** `ef714b02f92ae586166aad34b9110c7352aec699`
sur `dev/ps5-sparse-jit`.

## Distinguer inspection et qualification

Cette passe lit **10 fichiers distincts P0** non modifiés depuis
`82c531d`. L'état « inspecté » ci-dessous signifie *lecture ciblée du code
source et décision technique*, **pas** fermeture de contrat ni preuve de
comportement sur PS5. Aucun fichier n'est déclaré « optimisé » simplement
parce qu'un symbole a été trouvé. Un nouveau témoin C++ couvre
`KServerSession::OnRequest` et `KThreadQueue::{EndWait,CancelWait}`
en plus d'assertions statiques sur les deux chemins clients IPC.
Il compare des décisions de flux, pas les fibres natives.

| Contrat(s) | Fichier inspecté | Constat / décision | Preuve restant à obtenir |
| --- | --- | --- | --- |
| H25 | `vendor/sources/eden/src/core/hle/kernel/k_client_session.cpp` | Sync/async initialisent la requête, `SCOPE_EXIT` ferme la référence cliente, `OnRequest` assure le transfert ; ne pas changer le refcount sans un échec réel | Ownership/lifetime du côté serveur en conditions réelles ; ordonnanceur invité |
| H26,H27 | `vendor/sources/eden/src/core/hle/kernel/k_server_session.cpp` | `OnRequest` notifie l'arrivée, puis attend seulement pour sync ; `SendReply` et `CleanupRequests` réveillent le client ou signalent son événement ; témoin C++ ciblé ajouté pour `OnRequest` | `SendReply` complet et reprise effective après `EndWait` ; contrôles native/PS5 |
| H06 | `vendor/sources/eden/src/core/hle/kernel/k_thread_queue.cpp` | `EndWait` et `CancelWait` conservent résultat → Runnable → remise à zéro de la file → timer ; témoin ASan/UBSan ciblé ajouté | Planification et avancement de l'instruction invitée après réveil |
| H05 | `vendor/sources/eden/src/core/hle/kernel/k_synchronization_object.cpp` | `Wait` examine signal, annulation, timeout et liens ; `NotifyAvailable` visite les waiters. Témoin unlink hôte déjà présent, pas de nouvelle modification | Correlation notification → fiber/JIT sur console |
| H23 | `vendor/sources/eden/src/core/hle/kernel/k_readable_event.cpp` | `Signal` publie et notifie sous le verrou scheduler, `Reset` exige signal ; pas de changement source sans bug démontré | Réveil du client consommateur en conditions réelles |
| Q06 | `vendor/encore-active/eden-gpu/gpu_thread_quiet.cpp` | File GPU, stop token, propagation d'erreur et purge après join existent ; ne pas court-circuiter les attentes pour masquer un gel | EOF, drain et absence de fences pendantes sur le worker natif |
| Q08 | `vendor/encore-active/eden-gpu/include/video_core/gpu_thread.h` | ABI de file SPSC 256, fence monotone, mutex/CV partagé : header effectivement lié au worker | Compatibilité native quiet/DEV et durée de vie des producteurs |
| H07 | `vendor/encore-active/eden-threading/src/core/hle/kernel/k_address_arbiter.cpp` | `Signal` et les chemins wait passent par `EndWait` ; des témoins dédiés de réveil/overflow existent déjà | Corrélation native d'adresse et progression du guest |
| J04,J14 | `vendor/sources/eden/src/core/cpu_manager.cpp` | Le worker invité passe par `PhysicalCore::RunThread` et boucle en cas d'interruption ; aucun indice isolé justifiant une réécriture | Échantillon PC/JIT après sélection du thread |
| J15 | `vendor/sources/eden/src/core/hle/kernel/physical_core.cpp` | RunThread verrouille et recharge le contexte ARM ; interruptions et sauvegardes restent liées | Traces du PC et du contexte de reprise sur matériel |

## Nouveau contrôle hôte

`tools/check-native-ipc-wake-chain-host.py` :

- Extrait les **vraies méthodes** `KServerSession::OnRequest`,
  `KThreadQueue::EndWait` et `KThreadQueue::CancelWait`.
- Sur le client, vérifie l'ordre création → initialisation → transfert
  et la libération de référence des méthodes sync/async.
- Exécute les branches sync, async, file non vide, serveur fermé,
  thread en terminaison, réveil avec timer et annulation avec/sans timer
  dans un banc C++20 instrumenté ASan/UBSan (**192 cas**).
- L'effet du remplacement simulé d'une attente par un retour immédiat
  n'est **pas** une preuve de scheduling/fiber, de durée de vie
  inter-thread ou de résolution de gel sur PS5.

**Bilan : 10 chemins P0 inspectés et consignés ; 0 modification de source
moteur ; 0 contrat HOST ajouté ; 397 chemins et 408 contrats SOURCE+OPEN
restent à qualifier, dont 95 chemins P0.** L'objectif de cette passe est
de prévenir les patches en boucle et de mettre sous test les véritables
points de passage avant toute modification.
