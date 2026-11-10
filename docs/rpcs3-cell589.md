# RPCS3 Core 589 — Assassin's Creed et les leviers de validation de textures (28 octobre 2026)

Journaux iPhone du 28 octobre (`RPCS3-performance.log`, `RPCS3-timeline.1.log`,
`RPCS3-milestones.log`, `app.log`, `NeoSwap-v1.jsonl`). Toutes les sessions
portent `"build":"585"` : RewindBox 0.0.8 (585), Core 585 (`2b013636`, run
40700604912). Aucune ne porte le Core 587 : ses marqueurs (`COREPROF OPT587`,
canari) n'apparaissent nulle part ; la build 586 qui l'embarque a été livrée
après ces sessions (run 40774769488). Rien de ce qui suit ne mesure le 587.

## 1. Ce que disent les journaux (faits)

| pid | Jeu | Lancement | Couches de configuration |
| --- | --- | --- | --- |
| 44032 | Black Ops II (BLES01717) | deux démarrages frais (second exécutable) | base de données, `accurate_res=true` (profil 587 pas encore livré) |
| 44032 | God of War III (BCES00510) | frais, puis deux savestates | ancienne config personnalisée neutralisée : `inherited=19 kept=0`, WCB on, Mega, 75 %, réservations relâchées, MT RSX |
| 44754 | Bladestorm (BLES00113) | frais, 52 min, puis création de savestate | ancienne config personnalisée, pas d'entrée GameDB |
| 44952 | Dragon Ball Z (BLES01658) | menu puis jeu, 1 min | profil global |
| 45096 | Assassin's Creed (BLES00158), premier lancement | frais, 175 modules PPU compilés à froid | entrée officielle RPCS3 : MT RSX, streaming de textures asynchrone, ZCULL relâché |

* **Black Ops II** (585) : `FREEZE_DUMP no_frames` 4,5 s, 34,9 s puis 65,3 s
  après le second démarrage, 4,5–4,7 cœurs occupés. Les six SPU du noyau
  SPURS bouclent en GETLLAR/PUTLLC sur la même ligne (`0x2e20880`, bloc de
  contrôle SPURS). Le thread PPU principal attend un sémaphore depuis 65 s ;
  le seul thread PPU actif (`Secondary`) est trouvé suspendu par le verrou
  d'écriture (`state=0x204[w|mem]`). Le joueur a quitté le jeu.
* **Assassin's Creed**, scène de jeu stable (21:32:28–21:33:14, 12–29 fps) :
  * thread RSX 0,54–0,80 cœur, FIFO occupée 70–91 % ;
  * 1 040–2 170 draws par image ;
  * préparation des textures 14,5–28,2 ms par image (`RSXFRAME551 texture_ms`) ;
  * `OPT559 texture_epoch=0` : chaque recherche de texture re-hache la
    section ;
  * soumissions : 10–21 par image et 0,74–1,02 s par fenêtre de 5 s
    (synchrones) ;
  * 0,87–1,03 million de PUTLLC à données modifiées par fenêtre, sous le
    verrou d'écriture : `wl_putllc` 0,98–1,32 s ;
  * attentes PPU de 1,26–1,71 s (`vm_range_episode`, 19 500–32 100 épisodes).

  Plus tôt (21:31:30–21:32:22), à 1 900–3 300 draws, les textures coûtent
  20–45 ms par image. Sur toute la session de jeu, 268 compilations de
  pipelines Metal dépassent 50 ms (jusqu'à 0,7 s) : premier lancement, pas un
  cas de levier (AGENTS, règle 5). Le premier démarrage a passé 16,7 min à
  compiler les modules PPU (3 threads à environ 0,7 cœur) ; les deux suivants
  ont trouvé les 175 modules en cache (4 s). Fin par passage en arrière-plan
  (NeoSwap `application_background`), pas par un plantage.
* **Bladestorm** : 30 fps (plafond du jeu) pendant 45 min, p99 34–35 ms. Les
  textures coûtent 1,4–4,2 ms par image, contre 7,4 ms en 567, avant ses
  leviers 575 ; les scènes diffèrent, ce n'est pas une mesure du levier. Après
  la création de la savestate, 348 programmes SPU sont recompilés (225 + 123,
  absents du cache d'objets) : une fenêtre à 13,8 fps avec une image de
  593 ms. Empreinte mémoire de 3,0 à 3,4 Go en 45 min.
* **Dragon Ball Z** : une minute seulement : menu à 60 fps, intro à 53 fps,
  programmes SPU servis par le cache d'objets (804 chargés, 0 compilé). Aucune
  scène comparable aux mesures 563/565 ; la soumission anticipée n'est pas
  remise en cause.

## 2. Correctif du Core (CELL589_TITLE_LEVERS)

| Fichier | Changement |
| --- | --- |
| `rpcs3/ios/IOSTitleLevers.h` | `is_assassins_creed_title` : BLES00158, BLUS30089 (catalogue de cheats livré) |
| `rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp` | Assassin's Creed rejoint le mode Automatique de la validation de textures par lot FIFO (559) et de la revalidation ciblée (573) |
| `rpcs3/ios/RPCS3IOSSettings.cpp` | Les deux textes d'aide nomment Assassin's Creed |

C'est la règle 3 d'AGENTS : un titre rejoint ces deux leviers quand sa
préparation de textures atteint 5 ms par image. Black Ops II et Bladestorm
les ont rejoints en 575, God of War III les a depuis 559 et 573. Aucun
mécanisme ne change ; Enabled et Disabled restent identiques. La
pré-validation 581/583 reste réservée à God of War III : son coût de hachage
résiduel, après l'époque, n'est pas encore mesuré pour Assassin's Creed.
L'époque ne dépend pas du streaming de textures asynchrone : elle ne décide
que de re-hacher ou non la mémoire invitée, et les écritures du GPU en
mémoire invitée passent par `flush_set`, qui l'avance ou revalide la plage.

Identités de génération de code PPU/SPU inchangées, donc pas de
recompilation à froid. Les trois fichiers sont propres à iOS.

## 3. Profil de l'application (commit séparé)

Assassin's Creed (BLES00158, BLUS30089) :
`advanced.accurate_spu_reservations: false`, au-dessus de l'entrée officielle
RPCS3. C'est la signature de Black Ops II (profil 587) et le choix de God of
War III depuis la build 412. En mode relâché, un PUTLLC qui ne change qu'une
voie de 16 octets est un compare-and-swap sous verrou de plage, et un PUTLLC
sur le bloc de contrôle SPURS (`addr - spurs_addr <= 0x80`) un simple store :
ni l'un ni l'autre ne prend le verrou d'écriture. Le gel de Black Ops II
ci-dessus se produit précisément sur cette ligne SPURS : c'est ce que le
profil 587 (livré par la 586) doit faire disparaître. La clé du cache
d'objets SPU contient ce réglage : le premier lancement suivant recompile les
programmes SPU de ces deux titres une fois.

## 4. Vérifications (sans iPhone)

* `test/rpcs3_cell589_test.py` :
  * préimages 587 authentifiées par la fixture inverse ;
  * les deux blocs de politique compilés tels quels avec les vrais
    prédicats, en simple et sous ASan/UBSan, pour 11 serials × 3 modes : en
    Automatique, seuls BLES00158 et BLUS30089 changent (off avant, on après) ;
  * pré-validation inchangée ;
  * en remettant les blocs et lignes 587, la politique, les réglages et les
    leviers redeviennent ceux de la 587 à l'octet près.

  Preuve : `docs/evidence/rpcs3-cell589-host-linux.json`.
* Analyse syntaxique ARM64 des deux unités : 0 erreur, mêmes diagnostics qu'en
  587.
* `test/rpcs3_game_profile_service_test.dart` : le profil Assassin's Creed et
  la configuration publiée. Flutter est absent de ce conteneur : le test
  tourne dans la CI de livraison.

Rien n'a tourné sur iPhone. Aucun gain d'images/s n'est revendiqué.

## 5. À lire dans les prochains journaux

* Assassin's Creed (second lancement, mêmes scènes) :
  * `OPT559 texture_epoch=1`, `epoch_skips` ;
  * `RSXFRAME551 texture_ms` sous les 14–28 ms par image de la 585 ;
  * `RANGELOCKPROF wl_putllc` et `WAITPROF527 vm_range_episode` proches de
    zéro ;
  * `SHADERSTALL538_EVENT` en baisse (cache de pipelines écrit).
* Black Ops II (586, profil 587) : plus de `FREEZE_DUMP no_frames` sur la
  ligne SPURS ; `wl_putllc` en chute.
