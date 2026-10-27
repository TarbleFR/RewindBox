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
  place **avant** de poser son bit, au plus ~0,5 ms.
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
- **Modèle** (en-tête de production, temps d'attente de `vm.cpp`) : trois
  écrivains en rafale, un thread passif, 2 000 reprises. Build optimisé sur
  l'hôte Linux, 4 cœurs :

| | Sans | Avec |
|---|---|---|
| Plus longue attente | 15,9 ms | 0,9 ms |
| Attente totale | 1 783 ms | 305 ms |
| Débit des écrivains | 585 / ms | 545 / ms (−7 %) |

  Sous ASan/UBSan et TSan, aucune reprise ne reste bloquée.

Ce sont des chiffres de modèle sur l'hôte, pas des FPS sur iPhone.

## 5. À relever sur iPhone (DBZ, combat)

- `WAITPROF527 vm_range_episode` et `RANGELOCKPROF` : total et maximum en forte
  baisse.
- `FRAMEPROF527` : p99 et max en baisse ; médiane ~16,7 ms.
- `RANGELOCKPROF wl_putllc` (temps d'acquisition) : légère hausse possible.
- Journal de démarrage : `passive_fairness=1`.
- Si une régression apparaît : *Passive lock fairness* sur Désactivé rend
  l'ordre 569.
