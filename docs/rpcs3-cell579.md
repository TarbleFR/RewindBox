# RPCS3 iOS 579 — plantage SPURS de God of War III, attente des écrivains, attentes PPU, cession sans dépression

28 octobre 2026. Ce Core part des journaux du **build 575** (God of War III
`BCES00510`, Call of Duty: Black Ops II `BLES01717`, Dragon Ball Z Budokai HD
Collection `BLES01658`) et des analyses du Core 575. **Aucun gain 579 n'est
mesuré sur iPhone.**

## 1. Ce que montrent les journaux

| Build 575 | Constat |
|---|---|
| God of War III, premier lancement du processus | 2 lancements sur 2 (builds 567 et 575) s'arrêtent sur « vm::writer_lock is being used without cpu_flag::wait set by the caller! » dans `cellSpursRemoveWorkload` (PPU `0x1000000`, HLE). Le second lancement passe. |
| Black Ops II, verrous d'écriture SPU | 116–197 µs par verrou (DBZ : 0,3–0,6 µs). Les PPU en attente font 25 à 31 attentes temporisées par épisode : la porte d'équité 571 est presque toujours active, et chaque PUTLLC lourd attend en tournant jusqu'à 500 µs avant de publier son bit. Dans les fenêtres de tempête PUTLLC, environ 5 s par fenêtre de 5 s passent avant la publication, avec jusqu'à cinq threads SPU qui tournent sur les cœurs dont le PPU affamé a besoin. |
| Tous les jeux, iPhone A18 Pro | Chaque lancement écrit `cntfrq=1000000000 timer_scale=1` : le compteur tourne à 1 GHz, et `busy_wait(n)` dure n/100 ns, 33 fois moins que la durée prévue en amont (3 GHz). Les boucles d'attente PPU abandonnent leur attente active au bout d'environ 1 µs et s'endorment. |
| Dragon Ball Z | 825 épisodes de verrou passif de 38 µs en moyenne par fenêtre de 5 s, alors que les écrivains tiennent le verrou 0,3–0,6 µs. |

## 2. Les changements

**`CELL579_RESERVATION_OP_WAIT` — plantage SPURS (God of War III).**
`vm::reservation_op`, appelé par les fonctions HLE de SPURS sur un thread PPU,
prend le verrou d'écriture complet alors que ce thread tient son verrou passif
sans `cpu_flag::wait`. Le constructeur de `vm::writer_lock` refuse ce cas.
579 pose le drapeau autour du verrou et sort par `test_stopped()`, comme le
fait déjà `ppu_store_reservation` (stwcx PPU). Il ne le pose que dans le cas
refusé (thread PPU, verrou passif tenu, pas de `wait`). Les huit appels HLE de
`cellSpurs.cpp` (charges, drapeaux d'événement, signaux de tâches, job guard,
job chain) en profitent ; les appelants SPU ne changent pas.

**`CELL579_GATE_SLEEP` — attente des écrivains (Black Ops II, God of War III).**
La porte 571 garde son déclencheur (deux attentes temporisées) et sa borne de
500 µs. L'écrivain qui la respecte tourne au plus **50 µs**, puis **dort**
pour le reste : `os_sync_wait_on_address` sur iOS 17.4 et plus (attente
active comme en 575 sinon), futex sous Linux. Le dernier PPU affamé qui
repart réveille un seul écrivain endormi, et chaque écrivain réveillé
réveille le suivant : le PPU ne paie qu'un réveil. Les attentes de moins de
50 µs (cas de DBZ, qui a des cœurs libres) sont inchangées. Ce que l'écrivain
et le PPU attendent ne change pas.

**`CELL579_WRITER_YIELD` — l'écrivain cède son cœur sans perdre sa priorité
(Black Ops II, God of War III).** Après avoir publié son bit exclusif, qui
immobilise tous les PPU, l'écrivain attend en tournant, puis cède son cœur une
fois sur 32 au-delà de 128 tours. Sur Darwin, `sched_yield()` vaut
`swtch_pri(0)` : dès qu'un autre thread est prêt, l'écrivain descend à la
priorité 0 jusqu'à sa prochaine exécution, au plus un quantum de 10 ms, et il
garde son bit pendant ce temps. Avec le nouveau réglage *Writer lock yield
without depression* (Automatique : tous les jeux), la cession devient
`thread_switch(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0)` : le `sched_yield` de
libpthread lui-même avec `PTHREAD_YIELD_TO_ZERO=0`, la même cession mais
sans la dépression. Le rythme des cessions, la cession de la boucle de
publication et toutes les conditions d'attente sont ceux du 575. Désactivé
rend exactement le comportement 575.

**`CELL579_SPIN_NS` — attentes PPU à la bonne durée (tous les jeux, DBZ).**
`utils::spin_ns()` attend une durée réelle sur le compteur de l'appareil, en
arrondissant au tick supérieur. Il remplace `busy_wait` dans :
- l'attente active de `vm::passive_lock` avant sa première attente
  temporisée : 6,7 µs à 1 GHz ;
- les boucles « signal rapide » de sept primitives lv2 (`sys_semaphore`,
  `sys_lwmutex`, `sys_event_queue_receive`, `sys_cond`, `sys_lwcond`,
  `sys_event_flag`, `sys_mutex`) : 8,3 µs à 1 GHz, 6,7 µs pour
  `sys_mutex`, plus sa boucle d'essai.

Sur un compteur à 24 MHz, les ticks sont exactement ceux d'aujourd'hui (2, 3
et 5). Le verrou générique `shared_mutex` n'est pas modifié.

**`CELL579_IDLE_PARK_ALL` — RSX idle park pour tous les jeux.** Règle des
leviers d'`AGENTS.md` (« RSX idle park global next ») : actif depuis 565 sur
DBZ et God of War III, depuis 575 sur Bladestorm. La mise en veille ne
commence qu'après 1 ms de FIFO vide, avec l'attente FIFO *Yield*.

Tous ces changements sont réservés à iOS : hors iOS, chaque fichier touché
est celui du 575. Aucun fichier source PPU/SPU de l'identité de codegen n'est
touché : **pas de recompilation à froid**, les caches 575 restent valides.

## 3. Ce que 579 ne change pas, et pourquoi

- **Priorité de l'Offloader RSX et copies en ligne (God of War III).**
  Implémentées puis retirées. En 565, RSX, Offloader, SPU et PPU tournaient
  tous au même niveau, et l'écart RSX de God of War III (thread occupé mais
  hors CPU) était déjà le même. L'inversion de priorité n'en est donc pas la
  cause. Les copies en ligne auraient déplacé du travail vers le thread RSX,
  goulot de God of War III.
- **Relecture anticipée des cibles de rendu (DBZ).** Réfutée. Les octets
  attendraient dans le pool DMA partagé, qui peut être réenchaîné avant la
  faute : risque d'octets périmés. Gain estimé de 0 à 0,5 ms.
- **DBZ, la relecture GPU (5,3 ms par image).** C'est le GPU qui finit le
  travail dont dépend la surface lue par le SPU. Aucun patch de jeu n'existe
  dans la base officielle RPCS3 pour ce titre. Les soumissions asynchrones
  MoltenVK restent désactivées depuis le plantage au lancement de la 551.
- **Mémoire de God of War III (346 à 549 Mo de blocs VMA inutilisés).** Une
  allocation Vulkan dédiée par image rendrait cette mémoire au système. Mais
  elle change la façon dont MoltenVK rend les textures résidentes pour tous
  les jeux, et son coût en FPS ne peut pas être mesuré hors iPhone. Elle est
  reportée.
- **Boucle PUTLLC sans effet de Black Ops II (4,6 cœurs SPU).** Réfutée à la
  vérification : la session 4 de Black Ops II est le menu (10 dessins par
  image), le détecteur ne s'enclencherait pas (lignes alternées), et la
  correction touche `SPUThread.cpp`, qui fait partie de l'identité de codegen
  SPU : elle imposerait une recompilation à froid de tous les caches SPU.
- **Passage de la main au PPU qui n'a pas répondu (`thread_switch` vers son
  port Mach).** Seule la cession sans dépression est retenue ; le passage de
  main ciblé reste une piste.

## 4. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell579-host-linux.json`](evidence/rpcs3-cell579-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152`. La fixture
  reconstruit exactement les préimages 575, dont six fichiers lv2 modifiés
  pour la première fois, authentifiés contre la source XITRIX.
- Identités de codegen PPU `a987639e9f838d1c` et SPU `d070cb361bdef607`,
  inchangées depuis 575.
- `reservation_op` : le vrai corps de la fonction et la vraie vérification
  du constructeur de `writer_lock` sont compilés dans un modèle (36 cas :
  PPU avec ou sans verrou passif, avec ou sans `wait`, SPU, thread hors CPU,
  verrou partagé contesté ou non, opérations sans retour et booléennes).
  - Avec le texte 575, le modèle reproduit **15** erreurs fatales.
  - Avec le 579, **0**. L'opération est appliquée et l'état du thread est
    rendu tel que le verrou partagé l'a laissé.
  - Contrôlé sous ASan/UBSan et TSan.
- Porte 571 : les en-têtes 575 et 579, compilés dans le même modèle à vrais
  threads (Linux, 4 cœurs) :

  | Mesure | 575 | 579 |
  |---|---:|---:|
  | CPU d'un écrivain pour une temporisation complète de 500 µs | 503 µs | 75 µs |
  | Retour quand le PPU affamé repart après 200 µs | 229 µs | 256 µs |
  | Part CPU de six écrivains sur quatre cœurs | 0,57 | 0,33 |

  Aucun épisode affamé. TSan réussi.
- Cession sans dépression : le corps de `reservation_lock_yield()` est
  compilé tel quel. Sous Linux, une imitation de `thread_switch` reçoit
  exactement `(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0)` quand le réglage est
  actif, et rien sinon. Le rythme des cessions (`reservation_lock_should_yield`)
  et la cession de la boucle de publication sont identiques au 575. Sur le Mac
  de la CI, les vrais en-têtes Mach sont compilés et les durées de
  `sched_yield` et de `thread_switch` sous charge sont rapportées.
- `spin_ns` : les conversions sont vérifiées à la compilation pour 24 MHz,
  19,2 MHz et 1 GHz. Les neuf sites sont des branches iOS dont le `#else`
  est le `busy_wait` du 575.
- Vérification syntaxique ARM64 iOS des unités touchées (`vm.cpp`, les
  sept primitives lv2, `cellSpurs.cpp`, `cellSpursSpu.cpp`, la politique, les
  réglages, `system_config.cpp`) : mêmes diagnostics que le Core 575.
  `RPCS3IOSPlatform.mm` (Objective-C++) n'est compilé que par la CI macOS.

Ce sont des vérifications sur l'hôte, pas des mesures sur iPhone.

## 5. À relever sur iPhone

- God of War III, premier lancement après l'installation : il ne doit plus
  s'arrêter dans `cellSpursRemoveWorkload`.
- Black Ops II et God of War III :
  - `RANGELOCKPROF wl_putllc`, temps d'acquisition par verrou ;
  - `COREPROF range_wait_ms` ;
  - `WAITPROF527 vm_range_episode` ;
  - `RANGELOCKPROF max_ms` : le groupe autour de 10 ms doit disparaître ;
  - `spu_cores` et FPS.
- DBZ :
  - `vm_range_episode`, nombre et durée totale en baisse ;
  - verrous d'écriture toujours à 0,3–0,6 µs ;
  - FPS et p99.
- En cas de régression :
  - *Writer lock yield without depression* sur Désactivé rend la cession 575 ;
  - *Passive lock fairness* sur Désactivé rend l'ordre des verrous d'avant 571 ;
  - *RSX idle park* sur Désactivé rend l'attente active.
  L'attente PPU et la correction SPURS n'ont pas de réglage.
