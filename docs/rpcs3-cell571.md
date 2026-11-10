# RPCS3 iOS 571 — équité du verrou passif (saccades de DBZ en combat)

27 octobre 2026. Ce Core part des journaux du **build 567** de Dragon Ball Z
Budokai HD Collection (`BLES01658`), en combat (~195 dessins par image).
**Aucun gain 571 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux

| Combat, par fenêtre de 5 s | Build 564 | Build 567 |
|---|---|---|
| Image médiane | 21–23 ms | 16,7–17,4 ms |
| PUTLLC réussis / échoués | ~16 M / ~10 M | ~3 M / ~30 000 |
| PUTLLC lourds (verrou d'écriture) | ~105 000 | ~120 000 |
| Temps d'acquisition de ces verrous | ~12,8 ms | ~103 ms |
| Attentes du verrou passif | 140–230, 3–10 ms au total | 520–720, 90–200 ms au total |
| Plus longue attente du verrou passif | 0,1–2 ms | ~10 ms |
| Pires images | < 40 ms | 130–150 ms |

Le PUTLLC sans effet de la 565 a supprimé la boucle d'échecs des SPU : DBZ
passe de ~45 à ~60 FPS en combat. Mais les SPU avancent désormais plus vite et
prennent leurs verrous d'écriture en rafales.

## 2. Le mécanisme

- Un PUTLLC qui change la donnée prend un verrou d'écriture
  (`vm::writer_lock`). Il pose un bit dans un mot exclusif et attend que chaque
  thread PPU se soit arrêté.
- Un thread qui reprend l'accès à la mémoire du jeu (`vm::passive_lock`, à
  chaque reprise après une attente ou un verrou d'écriture) attend que ce mot
  soit **entièrement** vide.
- Le mot n'est notifié que lorsqu'il redevient vide. Quand plusieurs SPU
  enchaînent leurs verrous, le thread qui attend, réveillé à chaque fois, trouve
  à chaque fois un nouveau bit posé. C'est une famine : jusqu'à 10 ms.

## 3. Le changement (`CELL571_PASSIVE_LOCK_FAIRNESS`, `ios/IOSPassiveLockGate.h`)

- Un thread qui a déjà fait deux attentes chronométrées (50 µs chacune) dans
  `passive_lock` se déclare « affamé ».
- Tant qu'un thread est affamé, un nouveau preneur de verrou d'écriture
  (PUTLLC lourd, STORE128, `stwcx` PPU, opération de réservation) cède la
  place **avant** de poser son bit, au plus ~0,5 ms. Il patiente par une
  attente active avec l'instruction `yield` du processeur : sous Darwin,
  `sched_yield()` abaisse le thread pendant tout un quantum (~10 ms).
- Les verrous déjà pris se libèrent, le mot se vide, le thread passe, puis les
  écrivains reprennent.
- Aucun verrou n'est sauté ni affaibli : le thread attend toujours le mot vide,
  l'écrivain prend toujours son verrou.
- Réglage *Experimental → FPS Experiments → Passive lock fairness*
  (`experimental.passive_lock_fairness`). Automatique : tous les titres.
  Désactivé : ordre 569 exact.
- Journal de démarrage : `passive_fairness=1`.
- Les identités de codegen sont inchangées : aucune recompilation à froid.

## 4. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell571-host-linux.json`](evidence/rpcs3-cell571-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152`. La fixture
  reconstruit exactement les préimages 569.
- Le contrat de placement vérifie :
  - l'emplacement des deux insertions dans `vm.cpp` ;
  - le reste de `vm.cpp` identique au 569 ;
  - le réglage, la politique et le champ de journal.
- Le bloc de politique est exécuté pour les trois modes.
- La vérification syntaxique iOS ARM64 de `vm.cpp`, de la politique et des
  réglages ne donne aucune erreur et aucun avertissement nouveau.
- **Modèle** (en-tête de production, temps d'attente de `vm.cpp`) : des
  écrivains en rafale (3, ou 2 si l'hôte a moins de 4 cœurs, pour laisser un
  cœur au thread passif, comme dans DBZ qui occupe ~2,4 cœurs sur 6), un thread
  passif, 2 000 reprises. Build optimisé sur l'hôte Linux, 4 cœurs :

| | Sans | Avec |
|---|---|---|
| Plus longue attente | 13,1 ms | 3,9 ms |
| Attente totale | 2 545 ms | 252 ms |
| Débit des écrivains | 619 / ms | 585 / ms (−6 %) |

  - Sur plusieurs exécutions, le débit des écrivains varie de −20 % à +8 % : ce
    modèle écrit sans arrêt, ce qui est le pire cas pour lui.
  - Avec 3 cœurs émulés et 2 écrivains, l'attente totale est divisée par 2 à
    3,6.
  - Le test vérifie dans tous les builds (ASan/UBSan, TSan, optimisé)
    qu'aucune reprise n'atteint 20 ms. Les latences sont rapportées sans borne
    plus serrée.

**Deux runs Core échoués avant celui-ci.**
- `40568663915` : une borne de 10 ms sous TSan était trop serrée (10,8 ms).
- `40569244176` : sur le Mac de la CI (3 cœurs), sans le correctif le thread
  passif restait bloqué jusqu'à 24 ms. Avec la première version, une reprise a
  duré 127 ms, et un écrivain a cédé la main jusqu'à 11 ms : `sched_yield()`
  sous Darwin. D'où l'attente active bornée et le modèle qui laisse un cœur au
  thread passif.

Ce sont des chiffres de modèle sur l'hôte, pas des FPS sur iPhone.

**Run Core sur Mac Apple Silicon (`40570081835`, `0522f593`).**
Reçu : [`evidence/rpcs3-cell571-macos.json`](evidence/rpcs3-cell571-macos.json).
- Build optimisé, 3 cœurs, 2 écrivains, 2 000 reprises :

| | Sans le correctif | Avec |
| --- | --- | --- |
| Reprises au plafond de 20 ms | 2 | 0 |
| Attente maximale | 26,4 ms | 12,1 ms |
| Attente totale | 786 ms | 211 ms |
| Débit des écrivains | 428 / ms | 351 / ms (−18 %) |

- ASan/UBSan et TSan : aucune reprise au plafond avec le correctif.
- Le Core iPhone est compilé : SHA-256 `4f13dda2…`, 88 exports, identités
  PPU/SPU inchangées, aucune recompilation à froid.

## 5. À relever sur iPhone (DBZ, combat)

- `WAITPROF527 vm_range_episode` et `RANGELOCKPROF` : total et maximum en forte
  baisse.
- `FRAMEPROF527` : p99 et max en baisse ; médiane ~16,7 ms.
- `RANGELOCKPROF wl_putllc` (temps d'acquisition) : légère hausse possible.
- Journal de démarrage : `passive_fairness=1`.
- Si une régression apparaît : *Passive lock fairness* sur Désactivé rend
  l'ordre 569.
