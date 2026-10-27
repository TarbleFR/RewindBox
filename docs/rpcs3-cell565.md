# RPCS3 iOS 565 — soumission anticipée permanente, PUTLLC sans effet et repos du thread RSX

27 octobre 2026. Ce Core part des journaux du **build 564** (Core 563) de
Dragon Ball Z Budokai HD Collection (`BLES01658`, iPhone A18 Pro : deux cœurs
performance, quatre cœurs efficacité). **Aucun gain 565 n'est mesuré sur
iPhone.**

## 1. Ce que montrent les journaux 564 (combat, session 2)

- Une relecture CPU d'une surface 1280×720×4 par image (`fault_read`), avec
  3,7 à 6,5 ms d'attente par image ; elle suit le temps GPU de l'image.
- **SPU** : environ 120 000 `PUTLLC` réussis et 75 000 échoués par image, pour
  environ 500 qui changent la donnée (`putllc_heavy`). Le titre tourne avec
  « Accurate SPU Reservations » (`accurate_res=true`). Dans ce mode, un `PUTLLC`
  qui réécrit la donnée inchangée avance quand même l'horodatage de la
  réservation (`rtime + 128`). Il invalide donc les réservations des autres SPU
  qui interrogent la même ligne, et leurs `PUTLLC`, y compris ceux qui changent
  la donnée, échouent puis recommencent.
- **RSX** : le thread RSX occupe 0,90 cœur alors que la FIFO n'est occupée que
  33 à 43 % du temps. Il y a une période d'attente d'environ 12 ms par image,
  passée en `yield` (« RSX FIFO Idle Wait » = Yield).
- L'A/B 563 (12 paires sur 12) a mesuré +1,8 FPS en combat avec la soumission
  anticipée 561.

## 2. Les changements 565

**A. Soumission anticipée permanente sur DBZ.** L'alternance par fenêtre du
563 est retirée. `IOSEarlySubmit.h` et `RPCS3IOSPerformance.cpp` redeviennent
exactement ceux du 561. Le réglage « Early Command Buffer Submission » reste en
Automatique, actif sur `BLES01658` pendant toute la session.

**B. `PUTLLC` sans effet qui garde les réservations (`CELL565_NOOP_PUTLLC`).**
- Dans `spu_thread::do_putllc`, mode précis, donnée à écrire égale à
  l'instantané `GETLLAR`.
- Le `PUTLLC` réussit si la ligne est inchangée et si l'horodatage vaut toujours
  `rtime`, vérifié des deux côtés de la comparaison. Il n'avance plus
  l'horodatage.
- Les autres réservations de la ligne restent valides. Aucun waiter n'est
  notifié, comme avant.
- Une ligne changée, une réservation verrouillée ou un horodatage avancé font
  toujours échouer le `PUTLLC`.
- Écart avec le matériel : sur PS3, une écriture conditionnelle réussie, même
  identique, annule les autres réservations. Le mode relâché de RPCS3
  (`Accurate SPU Reservations: false`, déjà utilisé par God of War III) ne
  l'émule pas non plus.
- Réglage *Experimental → FPS Experiments → No-op PUTLLC keeps reservations*
  (`experimental.noop_putllc_keeps_reservations`). Automatique : DBZ seulement.
  Désactivé : comportement 563 exact.
- Code hôte appelé par les objets SPU, pas contenu dans ces objets : l'alias
  existant de `SPUThread.cpp` dans `JITCacheCompatibility.cmake` passe au nouvel
  instantané. Les identités de codegen restent PPU `a987639e9f838d1c` et SPU
  `d070cb361bdef607`, donc aucune recompilation à froid.

**C. Repos du thread RSX (`CELL565_RSX_IDLE_PARK`, `ios/IOSRsxIdlePark.h`).**
- Quand la FIFO est restée vide pendant 1 ms, `FIFO_control::idle_wait` dort
  par tranches de 50 µs au lieu de faire `yield`.
- Une courte attente à l'intérieur d'une image garde la boucle d'origine.
- La reprise de la FIFO termine la période d'attente.
- Ces demandes d'autres threads le réveillent aussitôt :
  - la demande de vidage d'une faute CPU (`on_access_violation`, sur le chemin
    critique de la relecture DBZ) ;
  - la demande du déchargeur ;
  - la demande de flip du PPU ;
  - le vidage ZCULL.
- Le prochain `PUT` du jeu est vu au plus tard à la fin de la tranche.
- Réglage *RSX idle park* (`experimental.rsx_idle_park`). Automatique : DBZ et
  God of War III, seulement si « RSX FIFO Idle Wait » vaut Yield.
- But : rendre le cœur aux threads SPU et PPU sur un appareil qui n'a que deux
  cœurs performance.

Hors iOS, chaque fichier modifié est identique au 563.

**D. God of War III sans limite à 30 FPS (application, `c5ba917`).**
- **D'où venait la limite.**
  - Le profil God of War III de RewindBox
    (`lib/services/rpcs3_game_profile_service.dart`, build 412) réglait le
    limiteur de RPCS3 sur 30 (`gpu.frame_limit: '30'`), comme cible mesurée de
    l'époque.
  - Rien d'autre ne plafonne ce jeu à 30 : le Core n'a aucune limite propre à
    God of War III. Le limiteur de RPCS3 ne prend que les valeurs du réglage
    « Frame limit » (`RSXThread.cpp`) ; la présentation MoltenVK suit
    l'écran.
  - Les correctifs de jeu fournis pour ce titre ne contiennent que des triches.
- **Ce qui vient du jeu.** Sur PS3, God of War III n'est pas verrouillé à
  30 FPS : sa cadence varie, synchronisée sur le vblank à 60 Hz, et il anime
  avec son propre temps. Aucun correctif du moteur n'est donc nécessaire pour
  dépasser 30.
- **Le changement.**
  - Le profil règle « Frame limit » sur `Auto`, la valeur par défaut du Core
    et celle des autres titres : limite au vblank de 60 Hz. La vitesse du jeu,
    la physique, les animations, les cinématiques et l'audio suivent donc son
    propre temps, comme sur PS3.
  - La valeur est explicite : une entrée GameDB publiée ne peut pas ramener
    une limite plus basse.
  - Un choix par jeu de l'utilisateur reste appliqué en dernier.
  - Sur un appareil qui garde un ancien `config_BCES00510.yml` complet, la
    couche d'héritage applique la valeur du profil quand le fichier avait laissé
    la valeur globale (`kept=0` aux démarrages 553).
- **Au-delà de 60.**
  - Il faudrait relever la fréquence du vblank (réglage par jeu « VBlank
    Frequency », par exemple 120 Hz, avec « Frame limit » sur 120 ou Display
    rate).
  - Ce réglage peut modifier la vitesse du jeu et la cadence de ses
    événements. Il n'est pas activé, et rien n'a été testé.
- **Coût.** Le limiteur à 30 laissait du temps CPU libre dans les scènes
  légères. Sans lui, le jeu travaille plus et chauffe davantage.

## 3. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell565-host-linux.json`](evidence/rpcs3-cell565-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152` vierge, avec toutes
  les empreintes vérifiées. La fixture reconstruit exactement les préimages 563.
  `RSXZCULL.cpp`, jusqu'ici amont, est comparé à l'amont.
- Les corps de production sont exécutés sous ASan/UBSan, TSan et ARM64 (qemu) :
  - 162 cas de politique (titres × trois réglages × trois modes d'attente FIFO) ;
  - 10 cas de protocole `PUTLLC` ;
  - un modèle à trois SPU qui interrogent la ligne pendant qu'un quatrième
    l'incrémente : **0 échec** du `PUTLLC` qui change la donnée avec 565 ;
    avec l'ancien chemin, de 0 à plusieurs dizaines de milliers selon le
    build et l'exécution (37 392 sur 200 000 incréments dans le build
    optimisé) ; aucune mise à jour perdue ;
  - le repos RSX : 200 réveils sur 200 ; un waiter avec un délai de 5 s
    revient dès `wake()` ; une attente de 60 ms consomme 14 ms CPU sur cette
    machine Linux, contre 60 ms en `yield` ; réveil médian 20 µs.
  - six mutations du comportement (temps avancé, comparaison omise, sans
    délai de grâce, sans notification, mauvais titre, réveil retiré de la
    faute) : toutes détectées.
- La vérification syntaxique ARM64 iOS des huit unités modifiées ne donne
  aucune erreur et aucun avertissement nouveau.
- Les neuf tests source du script de build et le test d'épinglage
  (`--source-only`) passent.

Ces chiffres valent pour l'hôte et le modèle, pas pour l'iPhone.

**Run Core sur Mac Apple Silicon (`40533429692`, `07e416c`).**
Reçu : [`evidence/rpcs3-cell565-macos.json`](evidence/rpcs3-cell565-macos.json).
- Les mêmes tests passent sur le Mac ARM64 de la CI (ASan/UBSan, TSan, build
  optimisé).
- Le Core iPhone est compilé : SHA-256 `428b11e6…`, 88 exports, identités
  PPU/SPU inchangées, aucune recompilation à froid.
- Modèle à trois SPU, build optimisé, 200 000 incréments : **0 échec** avec
  565, contre **637 736 échecs** avec l'ancien chemin, soit plus de trois
  échecs par mise à jour réussie.
- Repos RSX : 1,7 ms CPU pour 60 ms d'attente, contre 56,4 ms en `yield` ;
  réveil médian 2 µs, maximum 15 µs.
- Ce sont des mesures de modèle sur Mac, pas des FPS sur iPhone.

Le premier run Core (`40532040733`, `36ff40f`) a échoué dans le test natif sur
le Mac : le harnais chronométrait le premier repos à partir d'une lecture
d'horloge antérieure au bloc de repos (999 µs contre 1 000 µs de grâce). Il le
mesure maintenant depuis le début d'attente utilisé par le bloc. Aucune source
de production ne change.

## 4. À relever sur iPhone

- DBZ : `putllc_fail` (`SPUWAIT551`) en forte baisse ; `rsx_thread_cpu` /
  `top=rsx__thread` en baisse ; FPS, p95/p99 et `fault_read` ms/image dans les
  mêmes scènes de combat que le 564.
- God of War III : `frame_limit=Auto` dans `CONFIG_LAYERS` ; FPS, temps
  d'image et p95/p99 sans la limite à 30 ; `rsx_thread_cpu` (repos RSX). Aucune
  mesure God of War III n'existe depuis le build 551 : aucun gain n'est annoncé.
- Journal de démarrage : `noop_putllc=1 rsx_idle_park=1`.
