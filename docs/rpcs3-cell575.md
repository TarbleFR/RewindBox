# RPCS3 iOS 575 — Black Ops II et Bladestorm

27 octobre 2026. Ce Core part des journaux du **build 567** de Call of Duty:
Black Ops II (`BLES01717`) et de Bladestorm: The Hundred Years' War
(`BLES00113`). **Aucun gain 575 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux

| Build 567 | Black Ops II | Bladestorm |
|---|---|---|
| Images par seconde | 13–20 en jeu, gels jusqu'à 70 s | 30,00 constant |
| Ce qui limite | SPU (6 threads à 0,63–0,94 cœur) et RSX (FIFO occupée 83–99 %) | Thread PPU principal : 18,8 ms par image (0,567 cœur) |
| PUTLLC SPU réussis / échoués par fenêtre de 5 s | 27 M / 5,3 M (réservations exactes actives) | 0,4 M / 0,04 M |
| Préparation des textures | 9–16 ms par image, ~5 270 dessins | 7,4 ms par image |
| Thread RSX | Occupé | 0,66 cœur pour une FIFO occupée 31 % |
| Textures en cache | 63–147 Mo | 85 Mo |

**Les échecs de PUTLLC.** Dragon Ball Z avait la même signature avant 565 :
14–22 M PUTLLC réussis et 8–14 M échoués par fenêtre (builds 560 à 564).
Avec *No-op PUTLLC keeps reservations* (build 567) : 2,4 M et 0,03 M. Black
Ops II, qui n'a pas ce réglage, garde 27 M et 5,3 M.

## 2. Le changement (`CELL575_TITLE_LEVERS`, `ios/IOSTitleLevers.h`)

**Aucun nouveau mécanisme.** Le mode Automatique de quatre leviers existants
inclut désormais ces jeux :

| Réglage | Automatique avant | Ajouté |
|---|---|---|
| *No-op PUTLLC keeps reservations* (565) | DBZ | Black Ops II |
| *Texture validation per FIFO batch* (559) | GoW3 | Black Ops II, Bladestorm |
| *Scoped texture revalidation* (573) | GoW3 | Black Ops II, Bladestorm |
| *RSX idle park* (565) | DBZ, GoW3 | Bladestorm |

- Séries : `BLES01717` (Black Ops II) ; `BLES00113` et `BLUS30070`
  (Bladestorm). Les autres régions restent sur l'ancien réglage ; on peut
  forcer chaque levier sur Activé.
- Activé et Désactivé sont inchangés. Désactivé rend le comportement 573.
- Identités de codegen inchangées : aucune recompilation à froid.

## 3. Ce que 575 ne change pas, et pourquoi

**Black Ops II, gels (session 4 du build 567).** C'est le premier lancement
d'un exécutable jamais lancé auparavant : 85 modules PPU compilés au démarrage
(111 s), 0 objet SPU trouvé en cache pour ≈11 000 compilés, 389 pipelines
nouveaux. Le gel le plus long (≈70 s sans image) a deux phases :
1. ≈26 s de compilation SPU (≈7 000 programmes) ;
2. ≈55 s où le thread RSX compile des pipelines sans interruption : 10 à 14
   par fenêtre de 5 s, 0,35–0,48 s chacun dans le compilateur Metal (même coût
   pour God of War III).

Les trois caches ont été écrits. God of War III, cache chaud, n'a que 1 à 4
compilations de pipeline par session. Les identités de codegen n'ont pas
changé depuis 536 : les objets SPU de cette session servent aux builds 573 et
575. Supprimer aussi le gel du premier lancement demande un mode exclu à ce
jour :
- *Async with shader interpreter* : aucun dessin sauté, mais le rendu de
  l'interpréteur n'est pas vérifié sur iPhone ;
- la compilation SPU différée : désactivée en 436 après le gel de God of War
  III et l'arrêt de Bladestorm.

**Black Ops II, mémoire (4,1–4,8 Go).** Elle monte pendant cette même session
de compilation : 2,5 Go en début de partie, 4,7 Go 200 s plus tard. Toute la
hausse est de la mémoire compressée par iOS : la mémoire résidente reste vers
2,8 Go.
- Mémoire Vulkan : 392 → 968 Mo (cibles de rendu 167 Mo, textures 147 Mo).
- Le reste suit les compilations SPU et de pipelines.
- Session 559, en partie en cache : 3,05 Go au plus.
- Marge restante : ≥ 1,75 Go sous la limite estimée de 6,98 Go.

Bladestorm, cache chaud, reste plat (2 106 → 2 098 Mo sur 25 fenêtres) : pas
de fuite générale.

**Bladestorm, 30 FPS.** Aucune correction 60 FPS n'existe pour ce jeu dans la
base officielle de patchs RPCS3 (914 jeux, téléchargée le 27 octobre 2026).
Les journaux ne permettent pas de trancher entre deux causes :
- le jeu est conçu à 30 ;
- le jeu vise 60 avec synchronisation verticale, mais le thread PPU principal
  prend 18,8 ms par image, plus que les 16,7 ms d'une image à 60.

575 retire au thread RSX ≈0,6 cœur d'attente active sur les deux cœurs
performance. Si le PPU principal descend sous 16,7 ms et que le jeu reste à 30,
le jeu est conçu à 30.

## 4. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell575-host-linux.json`](evidence/rpcs3-cell575-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152` ; la fixture
  reconstruit exactement les préimages 573 ; les 9 tests statiques passent.
- Le fichier de politique, avec les quatre blocs 573 remis en place, est
  identique octet pour octet au 573. Seules les quatre phrases « Automatique »
  des réglages changent.
- Les quatre blocs de politique, copiés tels quels, sont compilés et exécutés
  pour 7 jeux × 2 modes d'attente FIFO × 3 modes (42 cas). L'idle park ne
  s'applique toujours qu'en mode d'attente *Yield*.

Ce sont des vérifications sur l'hôte, pas des mesures sur iPhone.

**Run Core sur Mac Apple Silicon (`40589313705`, `ddf73420`).**
Reçu : [`evidence/rpcs3-cell575-macos.json`](evidence/rpcs3-cell575-macos.json).
- Mêmes 42 cas de politique réussis que sous Linux.
- Le Core iPhone est compilé : SHA-256 `90275c29…`, 88 exports, 137 entrées
  enregistrées, identités PPU/SPU inchangées (aucune recompilation à froid).
- Les trois textes « Automatique » du 575 sont dans le binaire.

## 5. À relever sur iPhone

- Black Ops II :
  - `SPUWAIT551 putllc_fail` en forte baisse ;
  - `RSXFRAME551 texture_ms` en baisse ;
  - `OPT559 epoch_skips` non nuls ;
  - FPS moyen et p99.
- Black Ops II, relancer le même mode : `SPUPROF obj_hits` élevé,
  `obj_misses` proche de 0 ; peu d'événements `SHADERSTALL538_EVENT`.
- Bladestorm : `rsx_thread_cpu` en baisse. Part du thread `PPU[0x1000000]`
  dans `top=` : sous 0,5 cœur avec toujours 30 FPS, le jeu est conçu à 30.
- Si une régression apparaît : remettre le réglage concerné sur Désactivé.
