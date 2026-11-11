# RPCS3 Core 928 — la protection GPU se ferme dès la désactivation de l'application

11 novembre 2026. Core 928 = Core 927 + un seul changement : le moment où le rendu cesse d'envoyer du travail au GPU
quand on quitte l'application.

**Rien n'a été mesuré sur iPhone avec ce Core.** Ce qui suit vient des journaux d'appareil des builds précédents, de la
documentation d'Apple et de tests sur ordinateur. Aucun gain d'images par seconde n'est revendiqué.

## 1. Le défaut du Core 927

Le Core 927 ferme sa protection quand l'application reçoit la notification « entrée en arrière-plan »
(`UIApplicationDidEnterBackgroundNotification`). En relisant le journal de la seule perte de périphérique connue
(IPA 650, Assassin's Creed, PID 8767) :

| Instant | Événement |
|---|---|
| 1793814730,525 | le fil RSX reçoit `Device lost` (un tampon de commandes a déjà été refusé par iOS avant cet instant) |
| 1793814730,555 | l'observateur de l'hôte traite la notification d'arrière-plan (`HOST_STATE app=background`) |

iOS avait donc retiré l'accès au GPU **au moins 30 ms avant** que l'application traite cette notification. Une protection
fermée à ce moment-là n'aurait pas empêché cette perte : le correctif du Core 927 était posé un cran trop tard.

## 2. La règle d'Apple

Documentation Metal d'Apple, « Preparing your Metal app to run in the background » :

- à la **désactivation** de l'application, cesser d'envoyer du travail à Metal — « you've some time before the system
  restricts your app from using Metal » ;
- à l'**entrée en arrière-plan**, s'assurer que tout ce qui a été soumis est planifié avant de rendre la main ;
- ne reprendre qu'une fois l'application **réactivée**.

Le système applique donc sa restriction de son côté, un certain temps après la désactivation ; il n'attend pas que
l'application ait fini de traiter la notification d'arrière-plan. C'est cohérent avec le journal ci-dessus.

## 3. Ce que fait le Core 928

| Notification | Core 927 | Core 928 |
|---|---|---|
| `UIApplicationWillResignActiveNotification` (désactivation) | rien | ferme la protection, attend les appels en cours (500 ms au plus), puis la fin du travail en file (1 s au plus) |
| `UIApplicationDidEnterBackgroundNotification` | ferme et vide les files | termine seulement ce qui reste : rien si le vidage a abouti ; une attente **sans aucun nouvel envoi** s'il avait dépassé son délai ; la procédure complète si un appel était encore en cours à la désactivation |
| `UIApplicationDidBecomeActiveNotification` | rouvre | rouvre |

Autres points :

- un moteur de rendu créé alors que l'application n'est déjà plus active (jeu lancé juste avant de quitter) ferme la
  protection aussitôt (`found_not_active`) ;
- le détecteur de gel compte le temps de protection fermée comme une pause, pas comme un gel du jeu ;
- la ligne de journal devient `COREPROF GPUGATE928` (désactivations, arrière-plans, fermetures, appels mis en attente,
  vidages, reprises d'attente) ;
- rien n'est supprimé ni réordonné : les appels attendent et reprennent dans leur ordre ; un émulateur en cours d'arrêt
  ne patiente pas.

**Conséquence visible, voulue :** tant que l'application est inactive (Centre de contrôle, Centre de notifications,
sélecteur d'applications, alerte système), l'image se fige et le jeu attend son rendu ; il reprend au retour. Avant, le
jeu continuait de tourner sans qu'on puisse le commander.

## 4. Tests (ordinateur)

`test/rpcs3_gpu_gate928_test.py` : contrôle du source, puis deux modèles compilés contre le **vrai** code (g++ : normal,
ASan/UBSan, TSan ; clang : normal).

| Scénario | Règle du Core 927 (témoin) | Core 928 |
|---|---|---|
| Trois fils soumettent ; désactivation, puis restriction par le système, puis notification d'arrière-plan | des trames sont refusées entre la restriction et la notification (environ 200 sur cette machine) | 0 refusée, appels repris au retour, aucun perdu |
| 30 soumissions en file à la désactivation | 30 refusées sans vidage | 0 : la file est vidée pendant la désactivation |
| Notification d'arrière-plan après un vidage abouti | — | aucun nouvel envoi |
| Vidage qui dépasse son délai, puis arrière-plan | — | reprise : attente des barrières laissées, **aucun nouvel envoi** |
| Appel encore en cours à la désactivation | — | pas de vidage tant que les files sont utilisées ; vidage complet à l'arrière-plan |
| Désactivation puis retour sans arrière-plan (Centre de contrôle) | — | rouvre ; la désactivation suivante vide à nouveau |
| Changement de moteur de rendu pendant la fermeture, arrêt de l'émulateur, reprise de la fonction pendant un vidage | — | états remis à zéro, pas d'attente à l'arrêt, attente de la fin du vidage |

Le second modèle (`test/native/rpcs3_gpu_settle928_model.cpp`) exécute **le texte réel** de `vk::ios_settle_queues`,
copié du source par le test, contre un modèle des six appels Vulkan qu'il fait : six vidages complets de deux files
(12 envois, 12 barrières créées et détruites), et aucun envoi par une reprise d'attente.

Aucun scénario ne dépend d'une durée d'ordonnancement (verrous explicites et compteurs du Core). Épreuve sous charge :
les trois modèles, trois variantes, quatre passages sur un cœur partagé avec six boucles occupées : 36 sur 36.

`test/rpcs3_mvk_async927_test.py` garde tout ce qui concerne les soumissions asynchrones ; sur un source 928 la partie
« protection » est celle du test 928. `test/rpcs3_core_marker_rule927_test.py` : le vérificateur de livraison exige une
seule ligne de protection, `GPUGATE927` ou `GPUGATE928`. Identités du code généré inchangées (PPU a987639e, SPU
477a3fa4) : les caches PPU/SPU des joueurs sont conservés.

## 5. Bilan selon la grille de la mission

- **Coût supprimé** : aucun coût de calcul ; c'est une correction de sûreté (perte du périphérique en quittant
  l'application).
- **Coût restant** : inchangé par rapport au Core 927 (encodage sur le fil de MoltenVK, attente ZCULL, stationnement
  des fils PPU à chaque PUTLLC exact).
- **Chemin critique** : aucun changement en jeu ; à la désactivation, le fil principal attend au plus 1,5 s (en
  pratique une trame de GPU).
- **Mémoire** : aucune allocation par image ; une barrière temporaire par file à chaque fermeture.
- **Risques** : (a) l'image figée pendant l'inactivité est un changement de comportement visible ; (b) si le fil
  principal est lui-même bloqué longtemps (mémoire saturée), la désactivation peut être traitée trop tard — c'est la
  limite de toute protection côté application ; (c) à confirmer sur l'appareil.

## 6. À vérifier sur l'iPhone

1. En jeu, ouvrir le Centre de contrôle puis revenir : l'image se fige puis reprend ; `GPUGATE928 deactivations>=1
   closes>=1 opens>=1`, pas de `FREEZE_EPISODE` pendant la fermeture.
2. Quitter l'application quelques secondes et revenir : le jeu reprend, pas de `Device lost` ; `backgrounds>=1`,
   `settle_timeouts=0`.
3. Mêmes essais sur Black Ops II, God of War III et Assassin's Creed (`mvk_async=1`).

Le Core 927 reste épinglé dans l'historique comme repli (commit `6669475f`).
