# RPCS3 Core 918 — la durée des attentes actives sur l'iPhone à compteur 1 GHz

Suite de la mission du 10 novembre (Black Ops II et God of War III doivent tourner plus vite).
Core 918 = Core 917 + ce document. **Aucune mesure iPhone n'a été faite avec ce Core.** Ce qui suit vient des
journaux applicatifs de la build 718, du code et d'exécutions sur hôte ; la section 6 dit ce que l'export suivant
doit montrer, et il le montrera sans rien demander au joueur.

## 1. Symptôme chiffré

Journaux de la build 718, les seize démarrages (tous les titres) :

```
Resolved boot policy: … spin_timing=reference … cntfrq=1000000000 timer_scale=1 getllar_ticks=1000/5000/400000
```

Les attentes actives courtes de l'émulateur sont `utils::busy_wait(n)` (`rpcs3/util/asm.hpp`) : `(n / 100) × échelle`
ticks du compteur système. L'échelle 1 a été validée sur des iPhone dont le compteur tourne à 24 MHz ; celui de cet
appareil tourne à 1 GHz.

| Appel | Compteur 24 MHz (référence) | Compteur 1 GHz, échelle 1 (build 718) | Compteur 1 GHz, Core 918 |
|---|---|---|---|
| `busy_wait(200)` | 83 ns | 2 ns | 84 ns |
| `busy_wait(300)` | 125 ns | 3 ns | 126 ns |
| `busy_wait(500)` | 208 ns | 5 ns | 210 ns |
| `busy_wait()` (3000) | 1,25 µs | 30 ns | 1,26 µs |

Quarante-deux fois moins, sur les 66 appels du moteur.

## 2. Chemin de production

- **Lecture GETLLAR d'un SPU sur une ligne qu'un PUTLLC tient** (`SPUThread.cpp`) : 24 fois `busy_wait(300)`, puis
  `std::this_thread::yield()` à chaque tour. Sur cet appareil les 24 tours durent moins d'une microseconde ; un
  PUTLLC lourd de Black Ops II tient sa ligne 1,25 à 2,3 µs (builds 694 et 676, 213 000 par seconde). Le SPU qui
  attend passe donc presque toujours à `yield`, c'est-à-dire `swtch_pri` : sur Darwin, la priorité du thread tombe
  jusqu'à un quantum (constat déjà fait deux fois dans ce dépôt, `IOSPassiveLockGate.h` et
  `IOSReservationLockPolicy.h`, et corrigé alors pour l'écrivain seulement).
- Même forme pour les transferts DMA, PUTLLUC, les verrous de réservation de `vm.cpp` et le verrou d'écriture.
- **Tous les mutex du moteur** (`Utilities/mutex.cpp`, `sema.cpp`) : dix `busy_wait()` puis attente noyau. Dix
  fois 30 ns au lieu de dix fois 1,25 µs : la moindre contention part en appel système.

Ce que montre la fenêtre 12 de Black Ops II (build 676, 20,5 images/s) : six threads SPU à 0,53 cœur chacun alors
qu'ils n'attendent un événement que 407 fois (119 ms) en 5 s ; les attentes connues (verrou d'écriture, report
d'écrivains) n'expliquent pas un quart du temps qu'ils passent hors d'un cœur.

## 3. Modification

`REWINDBOX_BUSY_WAIT_REFERENCE_918` : avec « SPU Spin Timing = Reference » (le réglage par défaut), l'échelle est
la fréquence du compteur divisée par 24 MHz, arrondie — 1 sur le compteur de référence, 42 à 1 GHz. Chaque durée
redevient celle de l'appareil de référence, à 2 % près.

- `rpcs3/ios/RPCS3IOSLeverHelpers.h` : `reference_arm_timer_scale` ;
- `rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp` (`resolve_spu_spin_timing`) : installe l'échelle ; « Calibrated » garde
  l'échelle amont (33) ; les trois seuils GETLLAR en ticks ne sont pas touchés ;
- `rpcs3/util/asm.hpp` : l'échelle est un atomique sur iOS (lue par chaque attente, écrite par la politique et par
  le rapport) ; `busy_wait` calcule et attend comme avant ;
- réglage « Busy wait reference duration » (Expérimental → FPS Experiments) : Automatique = tous les titres,
  Désactivé = l'échelle 1 d'avant.

Aucune condition d'attente ne change, aucun verrou, aucun réglage de titre, aucun nombre ni priorité de SPU. Aucun
fichier d'entrée des identités de code généré n'est modifié : les caches restent valides.

## 4. Mesure dans la même scène

`COREPROF SCHED918` : par fenêtre de 5 s, ce que le noyau a compté pour le processus — changements de contexte,
appels Mach (un `yield` en est un), appels système BSD — avec l'échelle de la fenêtre.

La comparaison du Core 917 est étendue. Sur les fenêtres en cours de jeu qui affichent des images, pour tous les
titres, tant que les deux réglages sont sur Automatique :

| Fenêtres comptées du démarrage | Leviers |
|---|---|
| 1 à 6 | tous actifs (les captures demandées par le rapport s'y déroulent) |
| 7 à 22 | par paires : (rotation de l'écrivain inactive, échelle active), (active, échelle 1), (les deux inactifs), (les deux actifs), deux fois |
| 23 à 44 | tous actifs |
| 45 à 60, puis 83 à 98 | deux autres passes identiques |
| ensuite | tous actifs |

Trois passes pour qu'au moins une tombe en jeu quel que soit le temps passé dans les menus. La rotation de
l'écrivain (levier 917) n'alterne que dans une fenêtre qui compte au moins 100 000 PUTLLC lourds ; ailleurs elle
ne fait rien et reste active. Sur Activé ou Désactivé, un levier n'alterne jamais.
`tools/rpcs3/capture_analyzer.py` imprime, passe par passe, les médianes de chaque combinaison : images/s, cœurs SPU
et PPU, PUTLLC terminés, temps par verrou, appels Mach, changements de contexte, appels système.

**Conséquence visible** : pendant ces passes (trois fois 80 s dans les dix premières minutes d'un démarrage), la
cadence peut varier d'une paire de fenêtres à l'autre. Pour jouer sans alternance, mettre les deux réglages sur
Activé.

## 5. Test discriminant (hôte)

`test/rpcs3_busy_wait918_test.py`, 18 vérifications sur les en-têtes réels :

- l'échelle (24 MHz et 19,2 MHz : 1 ; 1 GHz : 42 ; inconnue : 1) et les durées du tableau ; contrôle : à 1 GHz avec
  l'échelle 1, 3 ns, 5 ns et 30 ns ; les 24 tours finissent avant la plus courte tenue mesurée avec l'échelle 1 et
  dépassent la plus longue avec l'échelle de référence ;
- la boucle d'attente du GETLLAR sur deux vrais threads, dans les proportions de l'appareil (un tour d'avant vaut un
  passage de boucle, un tour de référence en vaut 42 ; l'autre thread tient la ligne 2 à 6 fois les 24 tours d'avant
  et ne dort jamais) :

| 20 000 tenues, neuf exécutions (g++ et clang++, machine chargée) | Durée d'avant (contrôle) | Durée de référence |
|---|---|---|
| Tenues où le thread en attente a cédé son cœur | 19 919 à 19 957 | 1 à 24 |
| Cessions au total | 482 865 à 535 000 | 122 à 13 226 |

- une ligne tenue 6 à 8 fois plus longtemps que toute la rotation (son détenteur n'est pas sur un cœur) : 200 sur
  200 arrivent encore à la cession ;
- la comparaison : les quatre combinaisons, quatre fenêtres chacune, par paires ; une fenêtre sous la borne garde la
  rotation de l'écrivain active pendant que l'échelle alterne (God of War III) ; une fenêtre arrêtée ou sans image
  n'est pas comptée.

Ces chiffres montrent le mécanisme sur un PC Linux ; ils ne mesurent pas l'iPhone, où le coût d'une cession
(`swtch_pri`) est celui que les passes de la section 4 mesureront.

Revue indépendante (lecture seule, partielle) : aucun défaut dans l'échelle atomique ni dans la politique ; sa
remarque (`<atomic>` n'était inclus que par transitivité dans `asm.hpp`) est appliquée. Elle relève deux attentes
faites sous un verrou, qui durent maintenant ce qu'elles durent sur l'appareil de référence : la lecture GETLLAR
sous `rsx::reservation_lock` (environ 3 µs) et le cas rare de synchronisation ZCULL forcée de `VKGSRender.cpp`
(1,25 µs). L'arithmétique des passes et le bloc du rapport sont couverts par les tests exécutés.

## 6. Ce que l'export suivant décidera

- **Le levier agit** si, à échelle 42, les appels Mach par fenêtre chutent, les cœurs SPU et les images/s montent.
- **Il n'agit pas ou coûte** si les images/s baissent à échelle 42 (rotation plus longue sur des cœurs déjà pris) :
  le réglage Désactivé rétablit l'échelle 1, et le correctif suivant vise alors la cession elle-même.
- S'il reste beaucoup d'appels Mach à échelle 42 : la cession des boucles d'attente SPU (`SPUThread.cpp`, entrée
  d'identité : alias exact et audit, comme pour les Cores 911 et 916) doit passer à la cession sans dépression.

## 7. Limites

- Aucun gain n'est connu. Les durées restaurées sont celles de l'appareil de référence ; rien ne dit qu'elles sont
  les meilleures sur celui-ci.
- Les compteurs du noyau sont ceux du processus entier, pas ceux des seuls threads SPU.
- Les trois seuils GETLLAR en ticks (1 000 / 5 000 / 400 000) valent 1 µs / 5 µs / 400 µs ici contre 41,7 µs /
  208 µs / 16,7 ms sur le compteur de référence (et 0,33 µs / 1,67 µs / 133 µs dans l'intention amont). Ils ne
  sont pas modifiés, et les journaux existants les écartent comme levier :
  - Black Ops II (export de la build 694, 50 fenêtres de jeu à 230 000 PUTLLC lourds par seconde) : 0 sondage
    GETLLAR et 0 sommeil GETLLAR. Le deuxième et le troisième seuil ne règlent que ce chemin ; le premier ne
    concerne que les PUTLLC échoués, 2,9 % des PUTLLC réussis. Les SPU de ce jeu enchaînent GETLLAR puis PUTLLC
    (2,4 millions de PUTLLC réussis par fenêtre) et n'attendent un événement que 351 fois par fenêtre ;
  - God of War III (build 718, fenêtre 16) : 95 736 sondages (13,9 ms) et 3 094 sommeils (197 ms) sur l'ensemble
    des threads SPU en 5 s, soit 0,04 cœur.

## 8. Protocole iPhone

Rien à régler. Un export par jeu : le journal de performance garde deux générations de 2 Mio (`RPCS3-performance.log`
et son fichier `.1`), soit une dizaine de minutes de fenêtres (32 à 35 Ko par fenêtre de 5 s mesurés sur les exports
694 et 718). Une seconde partie jouée avant l'export efface la première ; l'export de la 718 ne contenait plus que
les quatre dernières minutes de God of War III et aucune fenêtre de Black Ops II.

1. Black Ops II : lancer le jeu, aller dans la scène lente et y rester jusqu'à neuf minutes après le lancement
   (les passes de comparaison occupent les fenêtres 7 à 22, 45 à 60 et 83 à 98 comptées depuis le démarrage, menus
   compris : de 0 min 30 à 1 min 50, de 3 min 40 à 5 min, de 6 min 50 à 8 min 10). Quitter le jeu et exporter
   aussitôt les journaux **avec les fichiers `.1`**.
2. God of War III : **démarrer le jeu normalement, sans état de sauvegarde** (« Continuer » dans le menu du jeu),
   jouer jusqu'à neuf minutes après le lancement dans la même zone, recréer ensuite un état de sauvegarde, quitter
   et exporter aussitôt avec les fichiers `.1`. Un état créé avant le Core 916 garde la mémoire du démarrage sans le
   contournement MLAA.
3. Pendant une passe, rester dans la même zone : la comparaison se fait entre paires de fenêtres voisines de 5 s.

## 9. Compilation et épinglage

| Élément | Valeur |
|---|---|
| Moteur | `cf850a8`, `d7695af`, `6d15a9a` sur le Core 917 (`921dbb5`) ; canonique `0f428497` (455 fichiers), delta `026f6841` |
| Demande | `02b9bf22` (`[rpcs3-core-build]`), run `42776454670`, verte au premier essai |
| Job Core | 129695964275 ; artefact 13745436352, 30 502 186 octets, empreinte API `f5478c38…80f4` |
| Job hôte Apple | 129695963848 ; 15 commandes dont `core918` ; artefact 13745530407 |
| Bibliothèque | `libRPCS3Core.dylib` 80 937 424 octets, SHA-256 `97b083c2…cb6f`, empreinte de charge `78f2defd…f9d3` |
| Identités | type `rpcs3-ios-core918`, PPU `a987639e9f838d1c`, SPU `477a3fa442d27917` (inchangées) |
| Pin | `3d8ec315…` ; vérificateur du dépôt : `verified`, aucune erreur, marqueurs présents |

Le pilote local complet a échoué une fois dans `zcull630_plain` (banc chronométré de l'étape Core 630 sur l'arbre
ramené en arrière, ligne 765) pendant que d'autres compilations chargeaient la machine ; le même pilote est vert dans
le job hôte Apple de ce run et dans un rejeu local sans autre charge.
