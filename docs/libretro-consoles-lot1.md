# Consoles de l'onglet Consoles : intégration des cœurs libretro, lot 1

Demande du mainteneur du 14 octobre 2026 : rendre réellement utilisables dans
le moteur libretro intégré (« RetroArch embarqué ») les consoles déjà listées
par l'onglet Consoles mais que seule l'application RetroArch externe lançait,
par lots, sans nouvelle plateforme, sans toucher Dolphin, RPCS3, ARMSX2 ni
Azahar, et sans annoncer un cœur fonctionnel avant d'avoir vérifié son
chargement et son exécution.

Branche `Claude`, base `0310ba6` (après la Build 457). Aucun essai sur iPhone
n'est revendiqué dans ce document.

## 1. Inventaire réel

L'onglet Consoles (`ConsoleCatalog`, Build 448) liste 85 consoles :

| Moteur | Consoles | Avant le lot 1 | Après le lot 1 |
| --- | --- | --- | --- |
| libretro intégré | `LibretroCoreCatalog.consoles` + Sega Pico | 17 + 1 | 38 + 1 |
| Dolphin, ARMSX2, RPCS3, Ports | GameCube, Wii, PS2, PS3, Ports | 5 | 5 |
| MeloNX (externe) | Switch | 1 | 1 |
| RetroArch seul (externe) | `ConsoleCatalog.retroArchSystems` | 61 | 40 |

Ces consoles sont « masquées par défaut » au sens de l'application : une
console n'apparaît dans le menu principal que lorsqu'un de ses systèmes est
détecté (jeux présents) ou ajouté depuis l'onglet ; Réglages › Systèmes
masque ou réaffiche. Ce comportement n'est pas modifié : seules la
disponibilité du moteur intégré et l'import changent pour les 21 consoles du
lot 1.

Les cœurs candidats ont été relevés dans les `.info` de
`libretro-core-info` `5a74858a` (extensions, firmware, licence, rendu) et dans
la liste App Store iOS de RetroArch (`pkg/apple/update-cores.sh`,
`df16ef19`) : un cœur de cette liste tourne sur iOS sans JIT. Les
correspondances RetroPad, géométries et options de chaque cœur ont été lues
dans les sources amont (tableau § 3).

## 2. Lot 1 : 21 consoles, 16 cœurs

Choix du lot : cœurs logiciels de la liste App Store, sans JIT ni contexte
matériel, manette sans clavier, BIOS absent, facultatif ou unique.

| Console (id) | Systèmes | Cœur | Licence | BIOS |
| --- | --- | --- | --- | --- |
| PC Engine (`pce`), TurboGrafx-16 (`tg16`) | pce, tg16 | Beetle PCE Fast | GPLv2 | aucun pour les HuCards ; System Card pour les disques rangés là |
| PC Engine-CD (`pccd`), TurboGrafx-CD (`tgcd`) | pccd, tgcd | Beetle PCE Fast | GPLv2 | `syscard3.pce` requis par défaut (option `pce_fast_cdbios`) |
| WonderSwan (`ws`), WonderSwan Color (`wsc`) | ws, wsc | Beetle WonderSwan | GPLv2 | aucun |
| NeoGeo Pocket (`ngp`), NeoGeo Pocket Color (`ngpc`) | ngp, ngpc | Beetle NeoPop | GPLv2 | aucun (BIOS intégré) |
| Atari Lynx (`lynx`) | lynx | Handy | zlib | `lynxboot.img` facultatif |
| Virtual Boy (`vb`) | vb | Beetle VB | GPLv2 | aucun |
| Atari 2600 (`2600`) | 2600 | Stella | GPLv2 | aucun |
| Atari 7800 (`7800`) | 7800 | ProSystem | GPLv2 | `7800 BIOS (U).rom` / `(E)` facultatifs |
| Atari 5200 (`5200`) | 5200 | a5200 | GPLv2 | `5200.rom` facultatif (Altirra OS intégré sinon) |
| ColecoVision (`cv`) | cv | Gearcoleco | GPLv3 | `colecovision.rom` **requis** (lancement refusé sans lui) |
| Pokémon Mini (`mini`) | mini | PokeMini | GPLv3+ | `bios.min` facultatif (BIOS libre intégré) |
| Game & Watch (`gw`) | gw | GW | zlib | aucun |
| Mega Duck (`duck`) | duck | SameDuck | MIT | aucun |
| Watara Supervision (`wsv`) | wsv | Potator | Unlicense | aucun |
| Arduboy (`ard`) | ard | Ardens | MIT | aucun |
| WASM-4 (`wasm4`) | wasm4 | WASM-4 | ISC | aucun |
| Uzebox (`uze`) | uze | Uzem | MIT | aucun |

Aucun de ces 16 cœurs n'ajoute de condition non commerciale ; aucun n'a
d'option JIT, dynarec ou recompilateur (sources lues ; le contrôle
`test/libretro_core_options_test.py --cores` le vérifie dans chaque binaire).

### Décisions d'architecture

- **Identifiants conservés.** Chaque console du lot garde l'identifiant et le
  nom qu'elle avait dans l'onglet comme console RetroArch (`pce`, `tg16`,
  `2600`…). Une console déjà ajoutée au menu principal
  (`libretro_main_menu_v1`), son interrupteur « Moteur intégré »
  (`console_engines_disabled_v1`) et son masquage sont donc conservés sans
  migration. Comme Game Boy et Game Boy Color, deux révisions d'un même
  matériel restent deux consoles (habillages et réglages séparés), sur le
  même cœur.
- **Repli RetroArch.** Les fichiers `assets/systems` ne changent pas : la
  route `retroarch://` reste disponible quand le moteur intégré est coupé
  (réglage global ou interrupteur de la console) ou quand un jeu a été réglé
  sur l'application RetroArch.
- **Dossier d'import.** Les jeux importés vont dans le dossier que le
  scanner reconnaît pour le système (`LibretroCoreCatalog.importFolderFor`) :
  `megaduck` pour la Mega Duck, dont l'identifiant `duck` n'est pas un nom de
  dossier connu. Défaut existant corrigé au passage : les jeux importés
  depuis les playlists `gb-hacks` et `sfc-hacks` allaient dans
  `roms/gb-hacks` et `roms/sfc-hacks`, que le scanner ne liste jamais ; ils
  vont désormais dans `gbh` et `sfch`. Un test vérifie ce dossier pour chaque
  système lié.
- **WASM-4.** Son audio par défaut (« callback ») n'est entendu qu'avec
  `RETRO_ENVIRONMENT_SET_AUDIO_CALLBACK`, que l'hôte n'offre pas :
  `wasm4_audio_type` est verrouillé sur `normal` pour la session.
- **Aucun shader activé**, aucun réglage de cœur nouveau exposé hormis ce
  verrou ; résolution native (cœurs 2D, sans résolution interne).

## 3. Commandes (tactile et manette)

Les tables sont dans `LibretroInputMap.h` ; elles suivent les sources des
cœurs. Les manettes gardent la correspondance positionnelle historique :
tout bouton RetroPad que lit un cœur reste joignable à la manette, même s'il
n'est pas dessiné à l'écran.

| Console | Écran tactile (habillage par défaut) | À la manette seulement |
| --- | --- | --- |
| PC Engine (4 consoles) | II, I, SELECT, RUN | III–VI en mode 6 boutons (option du cœur) |
| WonderSwan (2) | A, B, START, pavé Y (Y1 haut, Y2 droite, Y3 bas, Y4 gauche) en seconde croix au-dessus de B et A, ⟳ (rotation de l'écran, SELECT) | — |
| Neo Geo Pocket (2) | A, B (croisés par NeoPop, rétablis), OPTION | — |
| Lynx | A, B, OPT1, OPT2, PAUSE | SELECT (rotation dans le cœur) |
| Virtual Boy | A, B, L, R, START, SELECT, croix droite (R▲ R▼ R◀ R▶) dessinée en seconde croix au-dessus de B et A | — |
| Atari 2600 | 1 (tir), SELECT, RESET | interrupteurs de difficulté et couleur (L, L2, R, R2, L3, R3) |
| Atari 7800 | 1, 2, SELECT, PAUSE, RESET | interrupteurs de difficulté (L, R) |
| Atari 5200 | 1, 2 ; 0-9 (clavier à l'écran du cœur), *, # en rangée au-dessus ; START, PAUSE | touches directes du clavier |
| ColecoVision | clavier 1 2 3 / 4 * # au-dessus de L et R (boutons latéraux) | touches 5 à 8 ; 9 et 0 au stick gauche |
| Pokémon Mini | A, B, C | secousse (L), alimentation (SELECT) |
| Game & Watch, Mega Duck, Supervision | A, B, START, SELECT | — |
| Arduboy, WASM-4 | A, B (WASM-4 : X, Z) | — |
| Uzebox | disposition Super Nintendo | — |

Habillages : l'habillage par défaut est généré pour chaque console
(disposition, rapport d'image). Une rangée de plus de quatre boutons
allongés devenait trop petite sur iPhone SE (moins de 24 points, run
`38632620771`) : WonderSwan et Virtual Boy ont donc leur seconde croix,
ColecoVision et 5200 leur clavier en boutons ronds dans le groupe de
droite. Les habillages Delta/Provenance sont
reconnus par leur `gameTypeIdentifier` (PC Engine, Lynx, Virtual Boy… voir
`LibretroSkin.h`) ; le catalogue Provenance publie des habillages PC Engine,
Lynx et Virtual Boy.

## 4. BIOS (Réglages › Outils › Vérificateur de BIOS)

Le vérificateur liste les 38 consoles. Entrées ajoutées dans
`assets/data/libretro_bios_requirements.json` (tailles et sommes publiques de
`System.dat` `f206bf65`, aucun octet de BIOS) : System Cards PC Engine CD
(obligatoire seulement avec des disques, selon l'option `pce_fast_cdbios`),
`lynxboot.img`, BIOS 7800 (U) et (E), `5200.rom` (option `a5200_bios`),
`colecovision.rom` (obligatoire), `bios.min`. Les firmwares ADAM de
Gearcoleco (`eos.rom`, `writer.rom`) sont exclus avec leur raison : le mode
ADAM n'est pas proposé. Quatre textes nouveaux (`biosCondPceCd`,
`biosNotePceCd`, `biosNote5200`, `biosNoteColeco`) et le libellé
`inputRotateScreen`, en douze langues.

## 5. Paquet de cœurs

- `build-utils/libretro/add_cores.py` vérifie l'artefact que la livraison
  épinglait (`LibretroCores-8b9e87ba…`, run 38352378859) fichier par fichier
  contre sa propre identité, le recopie sans le modifier et n'ajoute que les
  cœurs qui lui manquent, depuis le buildbot officiel iOS ARM64, sans les
  modifier ni les compiler.
- Artefact produit : `LibretroCores-df0124b86f14aa16e8d1bbfa4ba4a43b0a20abaf`,
  run [38627332377](https://github.com/TarbleFR/neostation-ios/actions/runs/38627332377),
  artefact 11924546602 (52 289 173 octets compressés, 233 fichiers),
  conservé 14 jours. Les 16 nouveaux binaires : ARM64, plateforme iOS,
  iOS 8.0 minimum (Gearcoleco 15.0), dépendances `libSystem`/`libc++`
  seulement ; 12,7 Mo non compressés au total.
- Licences : textes amont épinglés dans `assets/legal/libretro/`
  (`license-sources.json`, révisions du 14 octobre 2026), crédits dans
  `LIBRETRO_CORES.md`.

## 6. Vérifications

Résultats consignés au fil du cycle dans le § 8.

- Paquet : `test/libretro_add_cores_test.py` (base vérifiée et conservée,
  cœurs absents seulement, refus d'une base modifiée, d'un cœur non publié
  ou non iOS), `test/libretro_azahar_package_test.py`.
- Catalogue, onglet, BIOS, crédits : `test/libretro_core_catalog_test.dart`,
  `test/console_manager_test.dart`, `test/libretro_consoles_tab_test.dart`,
  `test/libretro_bios_catalog_test.dart`,
  `test/libretro_bios_check_service_test.dart` (comportements ColecoVision,
  PC Engine CD, BIOS facultatifs), `test/libretro_bios_checker_screen_test.dart`
  (compteurs et cartes « aucun BIOS externe »), `test/legal_credits_dialog_test.dart`,
  `test/libretro_bios_requirements_test.py`,
  `test/libretro_core_options_test.py`.
- Natif (macOS) : `input_map_test.m` (38 tables), `default_skins_test.m`
  (chaque habillage par défaut tient sans chevauchement de l'iPhone SE à
  l'iPad), `skin_test.m` (types de jeux des habillages).
- Simulateur iOS (`test/libretro_simulator_probe.py --lot1`, job `lot1`) :
  chaque cœur du lot, binaire iPhone réel passé en plateforme simulateur,
  lancé deux fois sur un programme de test écrit par la sonde (quelques
  instructions qui font tourner la console, aucun contenu tiers), exécuté,
  fermé par « Quitter » ; le journal doit montrer le contenu accepté, le
  démarrage confirmé et la taille d'image attendue. Gearcoleco sans BIOS,
  Uzem et GW sur un fichier qui n'est pas à leur format doivent refuser le
  contenu proprement.

## 7. Consoles encore en attente (40)

Mise à jour : le lot 2 (`docs/libretro-consoles-lot2.md`) intègre le
Channel F, l'Intellivision, l'Odyssey 2 et le PC-FX ; l'état à jour des
autres consoles de ce tableau y est donné (§ 4).

| Console | Cœur envisagé | État |
| --- | --- | --- |
| Panasonic 3DO | Opera | lot 2 : BIOS requis, licence LGPL/non commerciale, charge processeur à mesurer |
| Fairchild Channel F | FreeChaF | intégré au lot 2 |
| Intellivision | FreeIntv | intégré au lot 2 |
| Magnavox Odyssey 2 | O2EM | intégré au lot 2 |
| Emerson Arcadia 2001, Interton VC 4000 | AmiArcadia | lot 2 : licence non commerciale, claviers numériques |
| Neo Geo CD | NeoCD | lot 2 : BIOS requis |
| NEC PC-FX | Beetle PC-FX | intégré au lot 2 |
| Sega Saturn | Yabause / Beetle Saturn | lot 2 : charge processeur sans JIT à mesurer, BIOS |
| Atari Jaguar | Virtual Jaguar | lot 2 : charge processeur à mesurer |
| Vectrex | vecx | lot 2 : le `.info` annonce un rendu OpenGL Core 3.3 ; repli logiciel à vérifier |
| RPG Maker | EasyRPG | lot 2 : jeux en dossiers ou archives |
| PICO-8 | fake-08 / retro8 | lot 2 : absents de la liste App Store, présence iOS à vérifier sur le buildbot |
| Apple II, BBC Micro, C64, VIC-20, PLUS/4, PET, Amstrad CPC, MSX, ZX Spectrum, ZX81, MS-DOS, Amiga, PC-98, PC-88, Sharp X1, X68000 | AppleWin, B2, VICE, Cap32, blueMSX, Fuse, 81, DOSBox Pure, PUAE, NP2kai, QUASI88, X1, PX68k | lot 3 : ordinateurs : clavier (ou clavier virtuel des cœurs) et souris à prendre en charge ; BIOS pour plusieurs ; QUASI88, X1 et 81 absents de la liste App Store |
| Philips CD-i | SAME CDi | lot 3 : absent de la liste App Store, BIOS requis |
| Palm OS | Mu | lot 3 : BIOS requis, licence non commerciale, écran tactile |
| ScummVM | ScummVM | lot 3 : jeux en dossiers, pointeur |
| M.A.M.E. | MAME / MAME 2003-Plus | décision requise : MAME complet ≈ 92 Mo, MAME 2003-Plus sous licence non commerciale ; NeoStation n'envoie volontairement aucun jeu `mame` à FBNeo |
| Sega Dreamcast, Naomi, Naomi 2, Naomi GD-ROM, Atomiswave | Flycast | **incompatible en l'état** : RetroArch l'exclut de sa liste App Store ; sans JIT (les cœurs libretro n'en ont pas dans NeoStation) il n'est pas jouable |
| Atari ST | Hatari | **incompatible en l'état** : le binaire du répertoire iOS du buildbot déclare la plateforme macOS (refusé au contrôle Mach-O du récepteur 781) |
| TIC-80 | TIC-80 | **indisponible** : absent du répertoire iOS ARM64 du buildbot (relevé du 9 octobre 2026) |

## 8. Journal du cycle

- `df0124b` : paquet de cœurs du lot 1 (run 38627332377, réussi).
- Sources du lot 1, avant commit, sous Linux : `flutter analyze` sans
  remarque ; liste Dart de la CI : 2 352 réussis, 3 ignorés, 1 échec —
  `libretro_bios_checker_screen_test.dart` attendait 3 BIOS requis manquants
  et 2 cartes « aucun BIOS externe » ; le catalogue en compte désormais 4
  (BIOS ColecoVision) et 14 (douze consoles du lot 1). Attentes remplacées
  par la liste exacte des consoles, fichier relancé : 10 réussis. Contrats
  Python du lot réussis. Tests natifs, contrôles `--cores` et simulateur :
  macOS seulement, résultats ci-dessous.
- `22fb882` (sources `ed61c9e` + vérificateur), contrôles run
  `38632620771` : **échec**, trois défauts réels corrigés au commit suivant.
  1. `libretro_locale_test.dart` : la clé traduite `inputRotateScreen`
     (⟳ WonderSwan) manquait dans la liste native `LibretroRequiredUIText`
     — sans elle le libellé n'atteignait pas la session. Ajoutée au même rang.
  2. `input_map_test.m` : Game & Watch, Mega Duck et Supervision listaient
     SELECT avant START ; ordre NES rétabli (A, B, START, SELECT).
  3. `default_skins_test.m` (560 échecs) et `chrome_layout_test.m` (12) :
     WonderSwan (6 boutons allongés), Virtual Boy (6 + L/R), ColecoVision (6)
     et 5200 (5) en une rangée descendaient sous 24 points sur iPhone SE et
     déplaçaient le bouton menu sur une fenêtre iPad 700 × 507. Seconde croix
     (pavé Y, croix droite du Virtual Boy) et claviers ronds dans le groupe
     de droite. Vérifié avant envoi par un portage Python du générateur qui
     reproduit exactement les cotes fautives de la CI (par ex. WonderSwan
     `l` {8.5, 452.1, 43.5, 18.1}) : 0 échec de taille, de chevauchement, de
     zone sûre et de bouton menu sur les mêmes formats.
  Le reste du job natif (hôte, shaders Metal, compilation iPhone des 69
  sources, codec de canal) était réussi.
- Même SHA, sonde simulateur run `38632626177`, job `lot1` **réussi** :
  29 scénarios sur 29 conformes. Lancés deux fois, exécutés environ 3 s
  puis fermés par « Quitter » (contenu accepté, démarrage confirmé, taille
  d'image attendue) : SameDuck, Potator, Ardens, Stella, ProSystem, a5200,
  Beetle PCE Fast, Beetle NGP, Beetle WonderSwan, Beetle VB, Handy, PokeMini,
  WASM-4. Refus propre (`LIBRETRO_GAME_REJECTED`, aucune session laissée) :
  Gearcoleco sans BIOS, Uzem et GW sur un fichier qui n'est pas à leur
  format. Gearcoleco, Uzem et GW ne sont donc pas encore démontrés en
  exécution : il faut un BIOS ColecoVision ou un programme Uzebox / Game &
  Watch libre. Jobs `probe`, `shaders`, `official-shaders`, `before-fix` :
  réussis ; `before-reservation` informatif.
