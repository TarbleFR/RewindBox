# RPCS3 Core 922 — contournement MLAA de God of War III à la reprise d'une sauvegarde d'état, mots de réservation dans le relevé de gel

> **Retiré par le Core 929 (11 novembre 2026)** : l'écriture de la paire dans la mémoire restaurée d'une sauvegarde
> d'état (section 3) cassait l'image de God of War III au premier menu pause après la reprise (builds 724 et 725). Voir
> [rpcs3-core929-gow3-savestate-untouched.md](rpcs3-core929-gow3-savestate-untouched.md). Les sections 4 et 4 bis restent en vigueur.

Core 922 = Core 921 + trois modifications (sections 3, 4 et 4 bis). **Aucune mesure iPhone n'a encore été faite avec ce Core.**

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

## 4 bis. Règle de la base RPCS3 (`REWINDBOX_CONFIG_DATABASE_RULE_922`)

Règle du mainteneur (10 novembre) : la base de réglages RPCS3 (api.rpcs3.net/config, embarquée dans
`assets/data/rpcs3_ios_profiles.json`) est la référence de chaque jeu ; les jeux restent à 100 % de résolution par défaut et
seul l'utilisateur change ses réglages ; le profil RewindBox de God of War III est supprimé.

- **Constat (build 723, PID 48627)** : God of War III démarrait sur un fichier complet `custom_configs/config_BCES00510.yml`
  (`CONFIG_LAYERS legacy_custom=1`), instantané de l'ancien profil RewindBox : résolution 75 %, réservations SPU relâchées,
  RSX multithread, 19 réglages hérités ; ce fichier passait avant la base et supprimait les réglages par jeu de l'utilisateur.
- **Moteur** : un fichier complet `custom_configs` n'est plus appliqué sur iOS (il reste sur le disque ; ligne
  `CONFIG_DB922 … legacy_custom_ignored=1`). Ordre : réglages globaux < base RPCS3 < réglages par jeu de l'utilisateur,
  toujours appliqués en dernier. Le mode Automatic du contournement MLAA vaut activé pour God of War III.
- **Application** : le profil `_godOfWarIII` de `lib/services/rpcs3_game_profile_service.dart` est supprimé ; les six
  références publient leur seule entrée de la base (Write Color Buffers, Shader Precision Ultra, SPU Block Size Mega,
  Asynchronous Texture Streaming true).
- **Contrôle** : `test/rpcs3_config_database922_test.py` (le vrai en-tête avec le yaml-cpp de RPCS3, 9 vérifications,
  exécuté en local ; il n'est pas dans le pilote, qui n'a pas yaml-cpp). Les tests Dart modifiés ne sont pas exécutés ici
  (pas de Flutter) : ils tournent dans le groupe Flutter de la livraison.
- **Risque signalé** : l'entrée de la base active *Asynchronous Texture Streaming* pour God of War III ; ce mode n'a jamais
  tourné sur l'iPhone (l'ancien profil le coupait pour cette raison). À vérifier au premier démarrage ; le réglage par jeu
  permet de le couper.

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
