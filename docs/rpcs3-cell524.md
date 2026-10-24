# RPCS3 524 — réveil HLE après refus de création d'une sauvegarde

Reprise sur `Claude` depuis le rapport Build 523, `1f850395`, sans nouveau
journal appareil ni changement distant. La Build 523 privée reste la dernière
IPA validée tant que la compilation et la livraison décrites ici ne sont pas
terminées. Aucun changement de `main`, tag ou release n'est autorisé.

## Défaut démontré dans le code

`System.cpp`, préparation d'une savestate, suspend les SPU puis appelle
`hle_locks_t::try_finalize`. Ce dernier effectue un premier contrôle, change
l'admission HLE de `0` à `waiting_for_evaluation` (`-1`), puis recontrôle les
conditions de sécurité. Si une vidéo HLE ou un callback sysutil apparaît entre
les deux contrôles, il refuse la sauvegarde et remet le verrou à `0`.

Les appels concurrents de `cellAdec`, `cellDmux`, `cellVdec`, `cellSaveData` ou
`cellSysmodule` passent par `hle_locks_t::try_lock`. Lorsqu'ils voient `-1`,
ils attendent avec le véritable `atomic_t<s64>::wait`, sans timeout par défaut.
Le chemin de refus remettait la valeur à zéro **sans notification**. Des threads
déjà parqués pouvaient donc rester endormis alors que la sauvegarde était refusée
et que l'émulation devait reprendre. Le chemin accepté notifie déjà ses attentes.

Le correctif ajoute `notify_all()` uniquement après le retour à zéro, sous
`RPCS3_IOS`. Il ne modifie ni CAS, ordre mémoire, délai, condition d'acceptation,
format de sauvegarde, précision numérique, réservation CELL ou barrière RSX.
Les sauvegardes originales ne sont ni migrées ni réécrites par ce correctif.

Ce défaut concerne une **création refusée**. Il n'est pas présenté comme la cause
de l'arrêt PPU du Build 522, survenu pendant le **chargement** d'une sauvegarde.
Les nouveaux jalons du Build 523 restent nécessaires pour localiser cet arrêt
sur appareil. Aucun nouveau test de God of War III n'est revendiqué ici.

## Preuve avant/après

Le test extrait la déclaration HLE et ses quatre méthodes des sources réelles.
Il compile `rpcs3/util/atomic.cpp`, `atomic.hpp` et `Utilities/sync.h` ; aucun
double ne remplace le verrou ou son moteur d'attente. Le rappel de test natif
annonce les attentes après leur enregistrement et leur contrôle de valeur,
avant le parcage, afin de reproduire le même entrelacement.

La méthode du Core 523 est reconstruite et authentifiée par SHA-256 :
`05aeb95ee311c7f51d8607fdbe83282cc60c2da829b8a154c49e10cde1faf1f5`.
Son contrôle négatif laisse huit attentes enregistrées inachevées après le refus.
Le test observe cet échec pendant sa borne d'une seconde, puis émet lui-même
une notification de secours pour joindre les threads proprement. Cette borne
appartient au test ; aucun timeout n'est ajouté au moteur.

Le candidat passe **20 cas ASan/UBSan** : réveil de tous les threads après
annulation, une puis huit attentes, répétitions, nouvelle finalisation réussie,
refus des acquisitions après finalisation, verrou déjà occupé et premier contrôle
refusé. Le test Linux utilise le vrai chemin de parcage RPCS3 par futex haché,
sélectionné par `-DANDROID` avec des adaptateurs d'identifiant de thread et de
formatage propres au test. Cela ne constitue pas un essai Apple ou iPhone.

Le [reçu détaillé](evidence/rpcs3-cell524-validation.json) conserve les sources,
résultats et limites. L'essai du backend natif Apple `os_sync_wait_on_address`
doit passer dans la compilation dédiée avant toute livraison.

## Sources, périmètre et validation

Base XITRIX `22f1152783cef1f7e04af7b1c895173e28fd5b03`, delta local dérivé
du Core 523 `e8437623`. La provenance est conservée dans `canonical-source.json`,
section `cell524`. Licence et attribution RPCS3 conservées ; adaptateurs de test MIT.
Un seul fichier moteur change : `rpcs3/Emu/savestate_utils.cpp`. Une fixture inverse
prouve la reconstruction exacte de ce fichier dans le Core 523 ; les 249 autres
postimages canoniques sont inchangées. Le delta complet a été rematérialisé sur
une copie propre de la base et toutes les empreintes ont été contrôlées.

Les preuves du Core 523 inchangées sont réutilisées après authentification de
leur run, de leur archive et de toutes leurs entrées. Seul le nouveau chemin HLE
est rejoué. Les 42 unités du contrôle SDK restent dans la compilation réelle.
ABI 30, garde ARMv8.4-A, caches PPU/SPU, NeoSwap, contrôleurs et choix JIT sont
conservés. Aucun changement du pont Flutter, des autres émulateurs ou de l'interface.

Cette intervention corrige un réveil manquant ; elle ne démontre aucun gain de
FPS, de chargement ou de RAM physique. Aucun appareil iPhone ou contenu légal
du jeu n'est accessible. Une future comparaison sur appareil devra conserver
le même jeu/update, état, scène, réglages, température et caches froids puis chauds.
Créer une copie des sauvegardes originales pour les essais.

Compilation du Core Apple et IPA privée : **en attente**. La livraison doit
réutiliser l'application 523 inchangée et reconstruire/signaturer son paquet
avec le nouveau cœur réellement compilé ; aucune nouvelle campagne Flutter
n'est nécessaire pour cette modification exclusivement native.
