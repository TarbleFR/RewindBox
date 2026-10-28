# RPCS3 Core 587 — soumissions MoltenVK asynchrones sans le plantage de la 551 (28 octobre 2026)

Le mainteneur confirme que le plantage au lancement de la 551 venait des
soumissions MoltenVK asynchrones (`docs/rpcs3-crash552.md`) et demande les
correctifs. Le Core 587 les apporte. Il est embarqué par la livraison privée
586 de la session MeloNX (consigne du mainteneur : « la session 586 avec
l'autre chat va embarquer tes correctifs »), à la place du Core 585.

## 1. Ce que fait MoltenVK 1.4.2 en mode asynchrone (source lue)

* `MVKQueue::submit` (`MVKQueue.mm:87`) : avec
  `MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS=0`, `vkQueueSubmit` et
  `vkQueuePresentKHR` placent la soumission sur une file GCD série
  (`MVKQueue::initExecQueue`, `MVKQueue.mm:324`) et rendent la main. Les
  commandes Metal sont encodées plus tard, sur cette file.
* `MVKPresentableSwapchainImage::acquireAndSignalWhenAvailable`
  (`MVKImage.mm:1565`) : `vkAcquireNextImageKHR` **libère le drawable** de
  l'image qu'il rend (`releaseMetalDrawable`), sans verrou. Si aucune image
  n'est disponible, il rend la moins récemment acquise, même si sa
  présentation n'a pas encore été encodée.
* `getCAMetalDrawable` (`MVKImage.mm:1608`) : le rendu dans cette image et sa
  présentation vont chercher le drawable au moment où la file les encode.

En mode synchrone, RPCS3 n'acquiert jamais avant l'encodage : il est fait
dans `vkQueueSubmit`, et `present()` attend que l'offloader RSX ait soumis.
En mode asynchrone, une acquisition peut dépasser une présentation encore en
file. Elle libère alors le drawable qui porte l'image : la présentation prend
un drawable neuf, et le rendu suivant de l'image dessine dans un drawable
déjà présenté. Ou bien elle entre en course avec la file sur le même
pointeur. La boîte de dialogue du cache de shaders enchaîne les images sans
travail entre elles : la fenêtre est la plus large dans la première seconde
d'un démarrage, là où toutes les 551 se sont arrêtées. C'est la cause la plus
probable ; aucune pile d'appel de la 551 ne la prouve.

Autres points audités, sans défaut en mode asynchrone : cycle de vie des
command buffers, descripteurs, tas de données, événements DMA et objets
libérés (tous attendent la fence, qui ne signale qu'après l'exécution GPU) ;
une seule file Vulkan sur MoltenVK, donc pas d'encodage concurrent ;
`vkDeviceWaitIdle` vide la file d'encodage avant toute reconstruction de la
swapchain. Défaut trouvé à part : MetalFX valide son propre command buffer
sur la même `MTLCommandQueue` juste après la soumission du blit d'entrée, que
l'offloader RSX peut encore tenir, déjà en mode synchrone.

## 2. Modifications

| Marqueur | Fichiers | Effet |
| --- | --- | --- |
| `CELL587_MVK_ENCODE_BARRIER` | `ios/IOSMoltenVKExec.h`, `ios/IOSMoltenVKExecQueue.h` (nouveaux), `RPCS3IOSPlatform.mm`, `VKPresent.cpp`, `VKGSRender.h`, `vkutils/device.cpp`, `RPCS3IOSPerformance.cpp` | Le build renomme l'unique référence de l'archive MoltenVK à `dispatch_queue_create` en `rbx_mvk_exec_q_create` (`build-utils/rpcs3/patch_moltenvk_exec_queue.py`, après le patch QoS de la 551 ; empreintes figées `b91a46f7…` → `0ee6ae96…`). La fonction crée la file à l'identique et la retient. Après chaque présentation, un marqueur est mis en file derrière elle ; avant chaque `vkAcquireNextImageKHR`, le thread RSX attend le marqueur de la dernière présentation (2 s au plus). Les soumissions faites depuis continuent d'être encodées pendant que le RSX enregistre. MetalFX : attente de l'offloader puis vidage de la file d'encodage avant son commit. En mode synchrone, aucune file n'est créée et rien n'attend. |
| `CELL587_MVK_ASYNC_CANARY` | `ios/IOSMoltenVKAsyncCanary.h` (nouveau), `RPCS3IOSExperimentalPolicy.cpp/.h`, `vkutils/instance.cpp`, `VKPresent.cpp`, `VKGSRender.cpp`, `IOSTitleLevers.h` | Automatique = God of War III. À la création de l'instance Vulkan, le titre est inscrit « armed » de façon durable (écriture, `fsync`, renommage). Il passe « ok » après 900 flips du jeu ou à l'arrêt propre du renderer. Un démarrage qui trouve son titre encore « armed » le note « failed » : soumissions synchrones pour ce titre ensuite. Fichier `rewindbox-mvk-async-587.txt` du dossier de configuration ; un Core suivant réessaie une fois. Sans écriture possible, le démarrage reste synchrone. |

Profil de l'application (commit séparé, hors Core) :
* God of War III : `experimental.moltenvk_async_submits` passe de `Disabled`
  (552) à `Automatic`, c'est-à-dire la décision du Core ci-dessus.
* Black Ops II (`BLES01717`) : `advanced.accurate_spu_reservations: false`.
  Journaux 583 : jeu limité par les SPU (3,6–4,3 cœurs, RSX 0,15–0,18) ;
  1,1 à 6,3 millions de PUTLLC modifiant les données par fenêtre de 5 s, chacun
  sous le verrou d'écriture exclusif qui arrête tous les threads PPU :
  0,74–2,9 s d'acquisition de ce verrou par fenêtre côté SPU, 4 000–9 500
  attentes PPU pour 0,3–0,9 s (`RANGELOCKPROF wl_putllc`,
  `WAITPROF527 vm_range_episode`). Les FPS suivent : 47–61 sous 0,4 million,
  24–29 vers 1,2 million, 6–22 au-delà de 2,4 millions. Le mode relâché garde
  le protocole de réservation ; un changement limité à 16 octets est un
  compare-and-swap sous verrou de plage, sans verrou d'écriture. Même choix
  que God of War III depuis la build 412 ; l'entrée officielle RPCS3 du titre
  (SPU Block Size Safe, ZCULL) n'impose pas les réservations exactes.

Rien ne change pour Dragon Ball Z (soumissions synchrones, profil global).
Les identités PPU/SPU sont inchangées (pas de recompilation à froid). Le
texte vu par un compilateur non-iOS des cinq fichiers partagés est celui de
la 585.

## 3. Vérifications (sans iPhone)

* `test/rpcs3_cell587_test.py` sur la source matérialisée : préimages 585
  authentifiées, contrat de source, texte hors iOS, outil de patch et étape de
  build. `test/native/rpcs3_cell587_mvk_exec_test.cpp`, en simple, ASan+UBSan
  et TSan :
  * logique des en-têtes : étiquette de file, suivi des tickets, états du
    canari ;
  * modèle des règles de swapchain de MoltenVK sur un thread série, avec le
    rythme de RPCS3 (trois contextes d'image), le dialogue des shaders et un
    thread d'encodage préempté une image sur huit : 309 à 373 libérations de
    drawable encore attendu sans barrière, **0 avec**. Preuve :
    `docs/evidence/rpcs3-cell587-host-linux.json`.
* Sur le Mac de la CI : `rpcs3_cell587_mvk_gcd_test.cpp` fait tourner le
  registre GCD réel (`IOSMoltenVKExecQueue.h`) contre la vraie libdispatch,
  avec une file créée comme celle de MoltenVK (le test échoue s'il ne tourne
  pas). Le build vérifie l'archive patchée (empreinte) et que le hook est
  résolu dans `libRPCS3Core.dylib`.
* Analyse syntaxique ARM64 locale des six unités C++ modifiées : 0 erreur, les
  mêmes avertissements qu'en 585.

Rien n'a tourné sur iPhone. Aucun gain d'images/s, aucune absence de
plantage n'est revendiquée.

## 4. À lire dans les journaux de la 586

* God of War III : ligne `COREPROF OPT587` avec `mvk_async=1`,
  `canary=armed`, puis `confirmed=1`, `exec_queues=1`, `barrier_missing=0`,
  `acquire_waits` et `marker_lag_ms`. Sous `RSXSYNC551`, `submit=` ne mesure
  plus que la mise en file ; comparer les images/s aux mêmes scènes que la 583.
  Si le jeu plante au démarrage, le lancement suivant reste synchrone
  (`canary=previous_boot_failed`) : envoyer le journal de diagnostic et le
  rapport iOS.
* Black Ops II : `RANGELOCKPROF wl_putllc` et `WAITPROF527 vm_range_episode`
  doivent chuter, les images/s des scènes chargées monter. Signaler tout gel
  ou défaut de jeu.
