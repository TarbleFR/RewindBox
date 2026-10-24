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

Le test extrait la déclaration HLE et les trois méthodes d'admission exercées
des sources réelles.
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

Le Core iPhone a compilé depuis `a7a109b955d2e60de005fd663eb4391f6c93e88d`,
[Actions 40110663507](https://github.com/TarbleFR/RewindBox/actions/runs/40110663507).
Le contrôle Apple natif passe avant la compilation complète. Les artefacts
ont été téléchargés et vérifiés indépendamment : SHA-256 du Core
`382bd3e2b27eb186c059fde7b5294de33f1334117ee2f593957b76658625fff0`, ABI 30, 88 exports exacts et 42 unités SDK.
Les identités PPU/SPU restent `9013390836efe46e` / `a601a98f20f30c80`.
Le contrôle négatif et les 20 cas passent avec les méthodes HLE réelles,
le moteur d'attente RPCS3 et `os_sync_wait_on_address` sur ARM64 macOS.
Cela ne constitue pas un essai de sauvegarde ou de gameplay sur iPhone. Le premier passage `40110380865` a
échoué à la compilation de la méthode `lock()` inutilisée dans le test avec
Xcode 16.4 ; cette définition a été retirée de l'extraction. Les trois méthodes
d'admission exercées et toutes les assertions restent celles du moteur réel.
Le correctif moteur n'a pas changé et ce premier passage n'a produit aucun Core.

L'assemblage privé 524 réutilise le cache chiffré et authentifié de l'application
523, source `c1f550f8`, run `40104064265`. Une empreinte de la véritable IPA 523
identifie les **87 images ARM64**, leurs entitlements et **4410 ressources**
conservées. Les numéros de build de l'application et de ses extensions, les
signatures et les métadonnées natives/source listées sont les seules exceptions.
Le code des autres moteurs, du frontend et du pont natif doit rester identique.
Les trois images universelles sont comparées sur leur tranche ARM64 utilisable.
Le test sur l'IPA réelle accepte le changement de numéro et refuse un identifiant
ou une instruction de l'application modifiés. Aucun binaire d'IPA externe n'est utilisé.

L'IPA 524 reste **en attente d'assemblage et vérification**. La préparation conserve
les notices originales et ajoute le delta canonique, son manifeste et la recette
native au paquet de sources. Elle resigne le paquet avec le cœur source compilé ;
aucune nouvelle campagne Flutter n'est lancée.

Le premier assemblage `40111780603` a validé la reprise exacte du binaire et
des ressources, puis a refusé la perte d'un ancien relevé SDK/plugin pendant
la régénération des notices. Le générateur recrée son dossier ; l'assemblage
conserve désormais toutes les anciennes notices et références avant cette
opération, puis refuse toute différence hors des métadonnées explicitement
actualisées. Aucune IPA de ce premier assemblage n'est livrée. Le Core compilé
reste identique et n'est pas recompilé pour cette correction d'empaquetage.
