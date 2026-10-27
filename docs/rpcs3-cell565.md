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

## 3. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell565-host-linux.json`](evidence/rpcs3-cell565-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152` vierge, avec toutes
  les empreintes vérifiées. La fixture reconstruit exactement les préimages 563.
  `RSXZCULL.cpp`, jusqu'ici amont, est comparé à l'amont.
- Les corps de production sont exécutés sous ASan/UBSan, TSan et ARM64 (qemu) :
  - 162 cas de politique (titres × trois réglages × trois modes d'attente FIFO) ;
  - 10 cas de protocole `PUTLLC` ;
  - un modèle à trois SPU qui interrogent la ligne pendant qu'un quatrième
    l'incrémente : **0 échec** du `PUTLLC` qui change la donnée avec 565,
    contre 17 (ASan), 95 (TSan), 4 (ARM64) et 32 728 (build optimisé,
    200 000 incréments) avec l'ancien chemin ; aucune mise à jour perdue ;
  - le repos RSX : 200 réveils sur 200 ; un waiter avec un délai de 5 s
    revient dès `wake()` ; une attente de 60 ms consomme 13,3 ms CPU sur cette
    machine Linux, contre 60 ms en `yield` ; réveil médian 29 µs.
  - six mutations du comportement (temps avancé, comparaison omise, sans
    délai de grâce, sans notification, mauvais titre, réveil retiré de la
    faute) : toutes détectées.
- La vérification syntaxique ARM64 iOS des huit unités modifiées ne donne
  aucune erreur et aucun avertissement nouveau.
- Les neuf tests source du script de build et le test d'épinglage
  (`--source-only`) passent.

Ces chiffres valent pour l'hôte et le modèle, pas pour l'iPhone.

## 4. À relever sur iPhone

- DBZ : `putllc_fail` (`SPUWAIT551`) en forte baisse ; `rsx_thread_cpu` /
  `top=rsx__thread` en baisse ; FPS, p95/p99 et `fault_read` ms/image dans les
  mêmes scènes de combat que le 564.
- God of War III : FPS et `rsx_thread_cpu` (repos RSX seulement).
- Journal de démarrage : `noop_putllc=1 rsx_idle_park=1`.
