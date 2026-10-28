# RPCS3 iOS 585 — soumission anticipée des commandes pour God of War III

28 octobre 2026. Ce Core part des **journaux iPhone du build 583** (God of
War III, Black Ops II, Dragon Ball Z, Bladestorm) et s'applique au Core 583
(`8ebca28`, run `40683438937`). **Aucun gain 585 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux 583

### God of War III (`BCES00510`), même sauvegarde qu'en 581

La première fenêtre a le même nombre de dessins par image (1 066,7 contre
1 066,5) : les deux sessions partent du même point.

| Fenêtres de 5 s | 581 | 583 |
|---|---:|---:|
| Scènes légères (~700 dessins/image) | 26-31 fps, médiane 32-38 ms | 29-33 fps, médiane 30-34 ms |
| Scènes chargées (~2 000 dessins/image) | 12-13 fps, médiane 77-80 ms | 16-19 fps, médiane 53-67 ms |
| Validations servies par le thread auxiliaire | 49-64 % | 54-66 % |
| Travail du thread auxiliaire perdu | 44-53 % | 39-51 % |

Le rythme du 583 change peu ses compteurs (`worker_passed` 60 à 400 par
fenêtre, `worker_refills` 400 à 720) : le gain d'images ne peut pas lui être
attribué avec certitude (trajet du joueur, état thermique).

**Chaque image, le jeu relit une cible de rendu 1280 × 720 × 4** :
`READBACK555 fault_read` en compte une par image (3,69 Mo), pour 2,1 à
6,7 ms par image et 0,80 à 1,06 s par fenêtre dans les scènes légères. C'est
le schéma de Dragon Ball Z avant le 561 : l'accès du jeu attend que le GPU
exécute ce que le thread RSX a enregistré depuis la dernière soumission.

Le réglage « Write Color Buffers » de la GameDB en est la cause, mais il est
nécessaire au jeu (éclairage, cinématiques) : il reste actif. Aucun réglage
n'est demandé au joueur.

### Les autres jeux

- **Dragon Ball Z** : 60 fps (plafond du jeu) dans 18 fenêtres sur 25, 28 à
  48 fps dans 5 fenêtres d'une scène plus lourde.
- **Black Ops II** : en jeu, 60 blocages de compilation de pipelines Metal
  (médiane 0,57 s, jusqu'à 4,8 s par fenêtre). Le cache passe de 671 à 801
  pipelines : ce sont de nouvelles zones (règle n° 5, pas un cas de levier).
- **Bladestorm** : 30 fps stables, le plafond du jeu.

## 2. Le changement

**`CELL585_EARLY_SUBMIT_GOW3`** : le mode Automatique de la soumission
anticipée des commandes (561) couvre maintenant les six numéros de God of
War III, en plus de Dragon Ball Z (règle mainteneur n° 4 : une cible de
rendu relue à chaque image).

- Mécanisme inchangé : à la fin d'un dessin, quand le GPU a terminé la
  dernière soumission et qu'au moins 32 dessins attendent, le thread RSX les
  soumet (6 fois par image au plus). Commandes, ordre et synchronisation
  inchangés.
- Sur Dragon Ball Z, ce levier a réduit l'attente de la relecture de
  1,7 ms par image (+1,8 fps en médiane, 12 paires A/B sur 12, build 563).
- Activé et Désactivé sont inchangés ; Désactivé rend le comportement 583.
- Fichiers : `RPCS3IOSExperimentalPolicy.cpp`, `RPCS3IOSSettings.cpp`
  (texte du réglage), `IOSTitleLevers.h` (relevé des valeurs). Tous réservés
  à iOS ; identités de codegen PPU/SPU inchangées : **pas de recompilation à
  froid**.
- God of War III utilise le RSX multithread, contrairement à Dragon Ball Z :
  la soumission anticipée passe par le même `flush_command_queue()` que les
  autres soumissions, qui synchronise déjà l'offloader.

## 3. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell585-host-linux.json`](evidence/rpcs3-cell585-host-linux.json).

- Delta canonique rematérialisé sur l'amont `22f1152` ; préimages 583
  authentifiées par la fixture inverse.
- Le code de sélection réel (`resolve_mode`, `is_dbz_budokai_hd_title`,
  `is_god_of_war_iii_title` et l'expression de la politique, 583 à côté) est
  compilé et évalué, sans et avec ASan/UBSan : Automatique couvre les six
  numéros de God of War III et Dragon Ball Z, pas Black Ops II, Bladestorm
  ni un autre jeu ; Activé couvre tout, Désactivé rien. La décision 561
  (`decide`) est inchangée.
- Seuls l'expression, son commentaire, le texte du réglage et le relevé
  changent ; le corps de `ios_early_submit` et son appel sont ceux du 583.
- Les 3 unités touchées compilent pour ARM64 (`RPCS3_IOS`) avec exactement
  les diagnostics du 583.
- Le pilote du run vérifie aussi `COREPROF OPT581` (oublié par le pilote du
  583).

Ce sont des vérifications sur l'hôte, pas des mesures sur iPhone.

## 4. À relever sur iPhone (God of War III)

- `COREPROF OPT561` : `early_submit=1`, `early_submits`, `gpu_busy_checks` ;
- `READBACK555 fault_read` : attente par image, contre 2,1-6,7 ms en 583 ;
- FPS et intervalle médian, dans les mêmes scènes que la sauvegarde 583.
