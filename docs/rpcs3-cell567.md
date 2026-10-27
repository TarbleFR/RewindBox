# RPCS3 iOS 567 — priorité du thread RSX et remise à zéro des workers

27 octobre 2026. Ce Core part des journaux du **build 565** (Core 565) de
Dragon Ball Z Budokai HD Collection (`BLES01658`) et de God of War III
(`BCES00510`), sur iPhone A18 Pro (deux cœurs performance, quatre cœurs
efficacité). **Aucun gain 567 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux 565

- **God of War III**, sans limite à 30 : 13 à 17 FPS en jeu. La FIFO RSX est
  occupée 85 à 90 % du temps, mais le thread RSX n'obtient que 0,57 cœur. Les
  SPU en prennent environ 3,4.
- **DBZ** : 51 à 60 FPS en combat. Le thread RSX descend à 0,28–0,6 cœur
  grâce au repos 565.

## 2. Ce qui ne va pas dans le Core 565

**A. Les priorités voulues par RPCS3 sont aplaties sur iOS.**
- Sur PC, RPCS3 place le thread RSX, `cellAudio` et `rsxaudio` au-dessus des
  autres threads (`thread_ctrl::scoped_priority(+1)`).
- Sur iOS, `set_native_priority` met tous les threads qui ne demandent rien,
  dont les PPU et SPU, dans la même classe QoS *user-interactive* que le RSX.
  La demande `+1` ne change rien.
- Avec deux cœurs performance, le thread RSX est donc en concurrence à égalité
  avec quatre threads SPU.

**B. Fuite de priorité dans les workers réutilisés.**
- Sur iOS, les threads natifs sont des workers réutilisés
  (`ios_thread_worker`).
- L'écrivain du cache de shaders se met en *utility* (`set_native_priority(-1)`,
  `rsx_cache.h`) et ne revient jamais en arrière.
- Le travail suivant sur ce worker, par exemple un thread SPU ou PPU, garde la
  classe *utility* et peut être relégué sur les cœurs efficacité.

## 3. Les changements 567 (`CELL567_THREAD_QOS`)

- Nouveau `ios/IOSThreadQoS.h` : une seule correspondance entre priorité RPCS3
  et QoS iOS.
  - `+1` (RSX, audio) : *user-interactive*, priorité relative 0.
  - `0` (PPU, SPU et les autres) : *user-interactive*, priorité relative −2.
  - `−1` (compilateurs, journaux, cache de shaders) : *utility*, comme avant.
- `ios_thread_worker::run` remet le niveau par défaut au début de chaque
  travail. Un travail ne peut plus hériter de la classe d'un précédent.
- Réglage *Experimental → FPS Experiments → RSX thread priority*
  (`experimental.rsx_thread_priority`). Automatique : tous les titres.
  Désactivé : priorité relative 0 pour tous, comme en 565. La remise à zéro
  des workers reste active dans les deux cas.
- Journal de démarrage : `rsx_thread_priority=1`.
- Les classes QoS restent les mêmes : seul l'ordre à l'intérieur de
  *user-interactive* change. La vitesse du jeu, l'audio et les horloges ne
  dépendent pas de ce réglage.
- `Utilities/Thread.cpp` n'est pas une entrée des identités de codegen : PPU
  `a987639e9f838d1c` et SPU `d070cb361bdef607` inchangés, donc aucune
  recompilation à froid.
- Hors iOS, chaque fichier modifié est identique au 565.

## 4. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell567-host-linux.json`](evidence/rpcs3-cell567-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152` vierge, avec
  toutes les empreintes vérifiées. La fixture reconstruit exactement les
  préimages 565.
- Le bloc de politique de production est exécuté sous ASan/UBSan et TSan pour
  les trois modes :
  - correspondance des priorités ;
  - un worker laissé en *utility* qui démarre son travail suivant au niveau
    par défaut.
- Sur un Mac (CI), le test appelle aussi les vraies fonctions
  `pthread_set_qos_class_self_np` / `pthread_get_qos_class_np`.
- Le contrat de placement vérifie trois points :
  - la remise à zéro précède chaque travail ;
  - les demandes `+1` et `−1` des appelants sont inchangées ;
  - le reste de `Thread.cpp` est identique au 565.
- La vérification syntaxique de `Thread.cpp` (iOS ARM64, avec les
  déclarations QoS d'Apple) ne donne aucune erreur et aucun avertissement
  nouveau.

Ces résultats valent pour l'hôte, pas pour l'iPhone.

**Run Core sur Mac Apple Silicon (`40547296252`, `67dd222`).**
Reçu : [`evidence/rpcs3-cell567-macos.json`](evidence/rpcs3-cell567-macos.json).
- Les mêmes tests passent sur le Mac ARM64 de la CI (ASan/UBSan, TSan).
- Les vrais appels QoS de Darwin confirment les trois modes, sous ASan/UBSan
  comme sous TSan :
  - un thread abaissé lit la classe *utility* ;
  - remis à zéro, il lit *user-interactive* avec la priorité relative
    attendue (−2 en Automatique et Activé, 0 en Désactivé) ;
  - relevé, il lit *user-interactive*, priorité relative 0.
- Ce sont des vérifications sur Mac, pas des FPS sur iPhone.

## 5. IPA privée 567

- Elle reprend le produit 566 livré :
  - moteur MeloNX `86c2b4d`, clavier, L3/R3 ;
  - God of War III sans la limite à 30 FPS.
- Seul le Core RPCS3 change : 565 devient 567.
- Elle s'installe par-dessus la 566 (même application, build 567).
- Recette : `rpcs3cell567_tree.py`, `rpcs3cell567_delivery.py`,
  `rpcs3-cell567-delivery.yml`, `validate_*567_ipa.py`.
- La recette 566 tourne inchangée sur l'arbre 566 livré (`as_566()`).
- La vérification des clés MeloNX attend le moteur réellement embarqué,
  `86c2b4d` (run `40535449055`).

## 6. À relever sur iPhone

- God of War III : FPS, temps d'image, p95/p99 ; `rsx_thread_cpu` (attendu en
  hausse) ; occupation de la FIFO.
- DBZ : FPS en combat, sans régression par rapport au 565.
- Audio : aucun craquement (`cellAudio` reste au-dessus des SPU).
- Si une régression apparaît : *RSX thread priority* sur Désactivé rend la
  répartition 565.
