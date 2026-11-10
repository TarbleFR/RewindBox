# RPCS3 Core 922 — contournement MLAA de God of War III à la reprise d'une sauvegarde d'état, mots de réservation dans le relevé de gel

Core 922 = Core 921 + deux modifications. **Aucune mesure iPhone n'a encore été faite avec ce Core.**

## 1. Données d'entrée (exports de l'appareil, builds 721 et 723)

| Session God of War III (BCES00510, exécutable 01.00) | Démarrage | `GOW3MLAA909 ppu=` | Relectures du tampon couleur par fenêtre de 5 s (médiane, `READBACK555 fault_read`) | Images/s en jeu |
|---|---|---|---|---|
| build 721, PID 47234, session 1 | normal | `applied` | 0 | — (menus) |
| build 721, PID 47234, session 2 | sauvegarde d'état | `savestate_memory`, `savestate_patched=0` | 88-107 | — |
| build 723, PID 48447, session 2 | normal | `applied` | 0 | 57-60 (menus) |
| build 723, PID 48447, session 3 | sauvegarde d'état | `savestate_memory`, `savestate_patched=0` | 72-75 (3,6 Mo chacune, 206-266 ms par fenêtre) | 12-23 |

Réglage « God of War III MLAA Bypass » activé (`CONFIG_LAYERS mlaa_bypass=1`). Dans la session 3 de la build 723, le thread
PPU principal utilise 0,9 cœur, les quatre threads SPU 0,6-0,75 cœur chacun, le GPU 25 % : l'image suit le PPU et le MLAA des
SPU, qui relit le tampon 1280×720 à chaque image.

## 2. Défaut (code)

Le chargeur n'applique le contournement (la paire officielle « Disable MLAA » : octet 0x52BF2F à 0, appel 0x231248 remplacé par
un nop) qu'au démarrage normal (`if (!ar && …)`, `rpcs3/Emu/Cell/PPUModule.cpp`). Une sauvegarde d'état contient la mémoire du
démarrage qui l'a créée : faite sans le contournement, elle le reste à chaque reprise, et le jeu continue de programmer son MLAA.
La mémoire invitée est restaurée (`vm::load`, `rpcs3/Emu/System.cpp`) avant le chargeur de l'exécutable.

## 3. Correction (`REWINDBOX_GOW3_MLAA_SAVESTATE_922`)

À la reprise d'une sauvegarde d'état, si le réglage est activé, si l'exécutable est exactement le 01.00 (plan gardé) et si la
mémoire restaurée ne contient pas la paire, la même paire est écrite, derrière la même garde de contenu (un appel relatif à
l'adresse, un octet de drapeau à 0 ou 1 ; sinon rien n'est écrit). Le rapport dit `ppu=savestate_applied`. La paire 01.03 (non
gardée) n'est jamais écrite dans une sauvegarde d'état. Un travail MLAA programmé avant la sauvegarde se termine sur son SPU ;
les images suivantes n'en programment plus, comme après un démarrage normal. Une nouvelle sauvegarde d'état faite ensuite
contient la paire (`savestate_patched=1`).

## 4. Relevé de gel (`REWINDBOX_FREEZE_RESERVATION_922`)

Gel de Black Ops II, build 723 (PID 48320) : les six SPU SPURS sur la ligne 0x2e20880 (cinq GETLLAR, un PUTLLC), le thread PPU
`Secondary` à 0,97 cœur à pc 0x73ccdc. Les lignes `FREEZE_DUMP line`, écrites après celles des threads, donnent pour 0x2e20880
le mot 0x854346dc0 (bit 64 posé) alors que le SPU3 en PUTLLC détient le temps 0x85434fd00, plus grand ; même écart pour
0x2e20c00. Aucun chemin d'écriture du mot n'a été trouvé qui le fasse reculer (relecture de tous ses écrivains). Les lignes
`spu` et `ppu` du relevé portent maintenant le mot de leur ligne lu à côté du temps du thread (`res=`, `getllar_res=`, avec le
compteur de temps), et pour le PPU `last_faddr`, `last_ftime`, `last_fail` ; les lignes de mémoire portent leur instant de
lecture. Le prochain gel dira si le mot recule vraiment et qui tient le verrou.

## 5. Contrôle (hôte)

`test/rpcs3_gow3_mlaa_savestate922_test.py` extrait du chargeur réel les deux instructions de décision (la condition de reprise
et celle de l'unique application) et les compile avec le vrai `rpcs3/ios/IOSGow3MlaaPatch.h` sur un modèle de mémoire
(g++ ASan+UBSan et clang) : 13 vérifications — mémoire restaurée sans la paire : exactement l'octet et le mot écrits, puis
`present` ; déjà patchée : rien d'écrit ; drapeau 0x37 ou mot qui n'est pas un appel : rien d'écrit ; paire 01.03 jamais écrite
dans une sauvegarde ; réglage coupé ou autre exécutable : rien ; démarrage normal identique au Core 921. Contre-test : la
condition sans son terme `guarded` est détectée. Le test 916 accepte la nouvelle règle.

## 6. Bilan

- **Coût supprimé** : sur une reprise de sauvegarde d'état, le MLAA du jeu (une relecture du tampon couleur par image, 206-266 ms
  par fenêtre de 5 s sur les threads, et le travail SPU qui le traite), comme au démarrage normal.
- **Coût restant** : aucun à l'exécution ; la paire est écrite une fois au chargement.
- **Chemin critique** : l'image suit le PPU principal et les SPU du MLAA ; leur part MLAA disparaît. Le gain iPhone n'est pas mesuré.
- **Mémoire** : inchangée.
- **Risques** : écrire la paire dans une mémoire en cours de partie ; garde de contenu identique à celle du démarrage, travail
  déjà programmé non interrompu. Image sans l'anticrénelage du jeu, ce que le réglage demande.

## 7. Inchangé

Aucune réservation, attente, synchronisation, résolution, précision, limite d'images, nombre ou priorité de SPU, option LLVM.
Aucun fichier d'entrée des identités de code généré PPU/SPU : les caches du joueur restent valides. ABI 30, 92 exports.

## 8. Protocole iPhone

God of War III repris depuis la même sauvegarde d'état : `GOW3MLAA909 ppu=savestate_applied`, `READBACK555 fault_read` à 0,
images/s comparées à la session 3 de la build 723 (12-23). Black Ops II : en cas de gel, l'export avec le relevé
(`FREEZE_DUMP … res= getllar_res=`).
