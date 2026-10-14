# Consoles de l'onglet Consoles : intégration des cœurs libretro, lot 2

14 octobre 2026. Suite du lot 1 (`docs/libretro-consoles-lot1.md`), mêmes
règles : consoles déjà présentes dans l'onglet Consoles et lancées jusqu'ici
par l'application RetroArch, cœurs officiels du buildbot iOS ARM64 ajoutés
sans modification, aucun BIOS fourni, aucun shader activé, Dolphin, RPCS3,
ARMSX2 et Azahar non touchés.

## 1. Consoles intégrées (4)

| Console (id de l'onglet) | Cœur | Licence | BIOS |
| --- | --- | --- | --- |
| Fairchild Channel F (`chf`) | FreeChaF | GPLv3 | facultatif : sans `sl31253.bin` (ou `sl90025.bin`) et `sl31254.bin`, BIOS de remplacement expérimental du cœur (son propre code) ; jeux intégrés absents |
| Intellivision (`intv`) | FreeIntv | GPLv2 | `exec.bin` **et** `grom.bin` requis ; NeoStation refuse le lancement sans l'un d'eux (`LIBRETRO_BIOS_MISSING_ALL`, fichiers manquants nommés) car le cœur charge le jeu et n'affiche qu'un écran d'erreur |
| Magnavox Odyssey 2 (`mo2`) | O2EM | Artistic License 2.0 | `o2rom.bin` requis (option du cœur par défaut) ; `c52.bin`, `g7400.bin`, `jopac.bin` (Videopac, Videopac+) choisis dans les options du cœur |
| NEC PC-FX (`pcfx`) | Beetle PC-FX | GPLv2 | `pcfx.rom` (1 Mo) requis |

Les quatre figurent dans la liste App Store iOS de RetroArch (aucun JIT),
s'affichent en rendu logiciel et n'embarquent aucun firmware de console.
Chaque console garde l'identifiant et le nom qu'elle avait dans l'onglet ;
l'import va dans le dossier du même nom, reconnu par le scanner.

Paquet : `LibretroCores-fdeaef56f1acdeb3afa4fd0ef42e94114bc4a258`, run
`38638115521` (34 cœurs, 53 374 262 octets, expire le 28 octobre 2026),
construit par `add_cores.py` sur le paquet du lot 1 (`df0124b8`, run
`38627332377`) recopié octet pour octet. Sources lues : FreeChaF
`76c7a84f`, FreeIntv `ef3e0fe3`, libretro-o2em `679d6fec`,
beetle-pcfx-libretro `c1650bad`.

## 2. Commandes

| Console | Tactile (habillage par défaut) | Manette seulement |
| --- | --- | --- |
| Channel F | croix ; bouton tiré ⤒ (X), poussé ⤓ (B), tourné à droite ↻ (A) et à gauche ↺ (Y) en losange ; 1-4 (START) ouvre les touches de la console (RESET, TIME, MODE, HOLD, START) choisies à la croix | SELECT (échange des manettes) |
| Intellivision | disque (croix) ; boutons d'action ◤ haut (Y), ◣ gauche (A), ◢ droite (B) ; ⌨ maintenu (L) affiche le clavier du cœur (croix puis un bouton d'action) ; ↺ (X) répète la dernière touche ; CLR (L2), 0 (L3), 5 (R3), ENT (R2) ; ❚❚ pause (START) | R (clavier), touches 1 à 9 au stick droit, SELECT |
| Odyssey 2 | joystick (croix) ; ● action (B) ; ⌨ (SELECT) affiche le clavier du cœur, tapé à la croix et B | touches 0 à 6 (X, L, R, L2, R2, L3, R3), Y, START |
| PC-FX | I (A), II (B), III (X), IV (Y), V (L), VI (R) sur deux rangées ; RUN (START), SELECT | interrupteurs MODE 1 / MODE 2 (L2, R2) |

Les dispositions ont été vérifiées avant envoi avec le portage Python du
générateur (tailles ≥ 24 points de l'iPhone SE à l'iPad, aucun
chevauchement, zone sûre, bouton menu à sa place).

## 3. Défaut corrigé en passant

`LibretroLocale.launchError` ne remplissait pas `{files}` : un BIOS manquant
(PlayStation, ColecoVision…) affichait littéralement « Un fichier BIOS est
nécessaire : {files}. » Le message reçoit maintenant le détail technique ;
le contrat `test/libretro_route_contract_test.py` est remplacé en
conséquence et `test/libretro_locale_test.dart` vérifie les douze langues.

## 4. Consoles en attente et raisons

| Console | Cœur | Raison |
| --- | --- | --- |
| Vectrex (`vect`) | vecx | **exclu** (consigne du mainteneur du 14 octobre 2026 : ne jamais fournir de BIOS) : le binaire du buildbot embarque la ROM système Vectrex d'origine (`bios/system.bin`, avec Mine Storm), compilée sans possibilité de la lire depuis System. Seule voie : un cœur construit depuis ses sources sans cette ROM et lisant celle de l'utilisateur, ce qui suppose une chaîne de compilation de cœurs que NeoStation n'a pas aujourd'hui. |
| Atari Jaguar (`jag`) | Virtual Jaguar | **exclu** (même consigne) : le binaire embarque les ROM de démarrage et BIOS CD d'Atari (`src/bios/`), même si le démarrage HLE ne les utilise pas par défaut. Même voie possible (construction sans `src/bios/`, ROM de l'utilisateur en option). |
| Neo Geo CD (`ngcd`) | NeoCD | **décision de licence** : composant Z80 « freeware for non-commercial purposes » ; le dépôt a un Patreon (`.github/FUNDING.yml`), même question ouverte que Snes9x, PicoDrive ou FBNeo. |
| 3DO (`3do`) | Opera | **décision de licence** : clause FreeDO non commerciale ; BIOS libre « Opera Boot » intégré seulement depuis le 12 octobre 2026 (présence dans le binaire épinglé à vérifier). |
| Sega Saturn (`sat`) | Yabause | performances : deux SH-2 interprétés sans JIT, compatibilité faible ; à mesurer sur iPhone avant intégration. |
| RPG Maker (`rpgmaker`) | EasyRPG | **incompatible en l'état** : tout le son passe par `RETRO_ENVIRONMENT_SET_AUDIO_CALLBACK`, que l'hôte n'offre pas (jeu muet) ; jeux en dossiers. |
| PICO-8 (`pico8`) | fake-08 / retro8 | absents de la liste App Store de RetroArch ; fake-08 n'a de cible iOS qu'armv7. |
| Arcadia 2001 / VC 4000 (`a2001`, `vc4k`) | AmiArcadia | licence « Non-commercial use only » sans texte de licence. |

Les autres consoles en attente (ordinateurs, CD-i, Palm, ScummVM, MAME,
Flycast, Hatari, TIC-80) sont décrites dans le lot 1, § 7.

## 5. Aucun BIOS fourni : audit des 34 cœurs

Consigne du mainteneur : ne jamais fournir de BIOS. Aucun cœur du paquet
n'embarque le BIOS d'un fabricant. Trois embarquent un remplacement libre
écrit par leur communauté, crédité dans `LIBRETRO_CORES.md` : a5200
(AltirraOS 5200, Avery Lee, avis tout-permissif dans sa source), PokeMini
(FreeBIOS, GPLv3) et Ardens (chargeurs d'amorçage Arduboy Cathy3K de
Mr.Blinky, MIT ; son avis de licence, requis, est ajouté). NeoPop, Handy,
FreeChaF et Beetle PSX (OpenBIOS) remplacent le BIOS par leur propre code.
Les images de BIOS de substitution de la sonde simulateur (une instruction)
ne quittent jamais l'application de sonde.

## 6. Vérifications

- Dart : `libretro_core_catalog_test` (42 consoles), `console_manager_test`
  (36 consoles restent à RetroArch), `libretro_bios_*` (Intellivision prête
  seulement avec ses deux fichiers, O2EM selon son option, PC-FX requis,
  Channel F facultatif), `libretro_bios_launch_test` (refus nommant les
  fichiers manquants), `libretro_locale_test`, `legal_credits_dialog_test`.
- Contrats Python : options des cœurs, BIOS (66 entrées, 95 lignes de
  firmware), routes, crédits.
- Natif (macOS) : `input_map_test` (42 tables), `default_skins_test`,
  `chrome_layout_test`, `skin_test`.
- Simulateur iOS (`--lot2`, job `lot2`) : chaque cœur lancé deux fois,
  exécuté puis fermé. FreeChaF sur une cartouche écrite par la sonde
  (`$55`, `JMP $0802`) avec son BIOS de remplacement ; FreeIntv sans BIOS
  (le cœur dessine son écran d'erreur : le cœur se charge et tourne, pas un
  jeu) ; O2EM et Beetle PC-FX sur des images de BIOS de substitution écrites
  par la sonde (une instruction qui saute sur elle-même), jamais un BIOS de
  console. Le simulateur n'est pas l'iPhone.

## 7. Journal

- `285d87e` : paquet de 6 cœurs (run `38636930244`, réussi) — remplacé.
- `fdeaef5` : vecx et Virtual Jaguar retirés (firmware embarqué), paquet de
  4 cœurs (run `38638115521`, réussi).
- `6e88e78` (intégration) et `8811491` (vérificateur de livraison) :
  contrôles run `38639581124` **réussis** (analyse et tests Dart, contrats
  dont `--cores` sur les 34 cœurs du paquet, natif macOS : hôte, tables
  d'entrées, habillages par défaut, compilation iPhone, codec de canal).
  Sonde simulateur run `38639585110` **réussie**, tous jobs compris. Job
  `lot2` (iPhone SE 3e génération, iOS 26.2) : 8 scénarios sur 8 conformes —
  FreeChaF, FreeIntv, O2EM et Beetle PC-FX lancés deux fois chacun, rendu
  logiciel, arrêtés et terminés proprement. Jobs `lot1`, `probe`,
  `shaders`, `official-shaders`, `before-fix` et `before-reservation`
  réussis. Le simulateur n'est pas l'iPhone ; FreeIntv n'y tourne que sur
  son écran d'erreur sans BIOS (cœur chargé et exécuté, pas un jeu).
- `3b0a5b1` et `df35dc9` (règle « aucun BIOS fourni », crédit des chargeurs
  Cathy3K d'Ardens, mentions épinglées dans le vérificateur), puis
  `036632b` : contrôles run `38641524647` **réussis**.
- **Livraison 459** (lots 1 et 2) : source
  `e5400cbeacf850328a6d069be46dbf0479eb7a4a`, run `38642923272` (`checks`,
  `native` et `cold` réussis), cœurs `LibretroCores-fdeaef56…` run
  `38638115521`, artefact `NeoStation-Build-459-e5400cbe…-cold`
  (`11932985033`, 215 447 453 octets, archive SHA-256
  `d2378c2607941fb5a57710897f26c355f1c34f888170e9c876b9fcdaae087654`,
  conservé jusqu'au 28 octobre 2026), chiffré pour
  `build-utils/delivery-424-recipient.pem`. IPA
  `NeoStation-Build459-e5400cbe…-cold.ipa`, 215 167 326 octets, SHA-256
  `e72d9163b4b3c02f8d96f8294c18de9c547f729a41bdd4d67ed8060a53bbb513`, égal
  à `SHA256SUMS` et à `signed-payload-identity.json` ; version 0.0.7 (459)
  dans l'application et ses cinq extensions ; 34 cœurs libretro, dont
  FreeChaF, FreeIntv, O2EM et Beetle PC-FX, sans vecx ni Virtual Jaguar.
  Déchiffrée sur le PC du mainteneur à sa demande (`decrypt-459.ps1`, clé
  424) ; copie `C:\Users\Coren\Downloads\NeoStation-Build459-e5400cb.ipa`.
  Aucune validation sur iPhone. Ne pas réutiliser le numéro 459.
