# Textures HD : Nintendo DS, NES (Mesen) et nouvelles sources, 20 octobre 2026

Demande du mainteneur (20 octobre 2026) : rechercher de nouvelles sources pour
les catalogues HD, ajouter des packs HD pour la Nintendo DS et pour toutes les
autres consoles rétro qui en ont, afin de proposer des packs HD pour le reste
des émulateurs disponibles. Les règles de la Build 488 restent en vigueur (pas
de contournement d'hébergeur, de réhébergement, de miroir non autorisé ni
d'entrée fictive ; branche `Claude` seule ; aucune release).

Inventaire généré : [`HD_TEXTURE_CATALOG_SOURCES.md`](HD_TEXTURE_CATALOG_SOURCES.md).
Cycle précédent : [`hd-textures-expansion-2026-10-19.md`](hd-textures-expansion-2026-10-19.md),
[`build489-hd-catalogue-ps1-vulkan.md`](build489-hd-catalogue-ps1-vulkan.md).

## 1. Quels moteurs embarqués lisent des textures de remplacement

Lu dans les sources de chaque cœur (dépôts clonés le 20 octobre 2026) :

| Console | Moteur embarqué | Remplacement de textures | Source lue |
|---|---|---|---|
| Nintendo DS | DeSmuME (libretro) | **aucun** : seul un vidage de débogage, compilé sous `WIN32` seulement (`texcache.cpp`, `DEBUG_DUMP_TEXTURE`) | libretro/desmume `95b4d798` |
| Nintendo DS | melonDS (non embarqué) | **aucun** dans la branche principale (`HiresCoordinates` règle la précision du rendu) ; seul le fork KHMelonMix (Kingdom Hearts, Windows/Linux) annonce un remplacement en cours | melonDS-emu/melonDS `906e9ebb` |
| NES | Nestopia (défaut) | aucun | libretro/nestopia `06a8949e` |
| NES | **Mesen** (ajouté) | **packs HD `hires.txt`, format 106 au plus** | libretro/Mesen `0102910c` |
| SNES, GB/GBC, GBA, Mega Drive/SMS/GG, arcade | Snes9x, Gambatte, mGBA, Genesis Plus GX, PicoDrive, FBNeo | aucun | `fae2fea`, `d9d6cd0`, `7a12d6d`, `aa74d79`, `1890c29`, `2dbbac7` |
| PC Engine, WonderSwan, Neo Geo Pocket, Virtual Boy, Lynx, PC-FX | Beetle PCE Fast/WS/NGP/VB/PC-FX, Handy | aucun | `3f946f2`, `4b01295`, `a50d5ac`, `d5ae54c`, `c1650ba`, `bc55d46` |
| Dreamcast | Flycast | non embarqué (JIT requis, déjà établi) | — |

La Nintendo DS n'a donc aucun pack installable : ni le moteur embarqué ni
melonDS ne remplacent de textures. Aucun pack DS n'est catalogué, et aucun
support n'est annoncé.

Pour la NES, les packs HD existent (format `hires.txt` de Mesen, souvent
appelés « HDNes packs »), mais Nestopia ne les lit pas. Mesen figure dans la
liste App Store iOS de RetroArch (`pkg/apple/update-cores.sh` `df16ef19`),
condition d'entrée d'un cœur dans un lot : il est ajouté comme moteur NES
**alternatif** (lot 3), Nestopia restant le moteur par défaut. Mesen 2 (format
109) n'a pas de cœur libretro : ses packs (format ≥ 107) restent exclus.

## 2. Mesen dans le moteur libretro intégré

- **Cœur** : binaire officiel iOS ARM64 du buildbot (`mesen_libretro_ios.dylib.zip`,
  construit le 19 octobre 2026, 3 337 040 octets, SHA-256
  `547b840f3911dfe52bc1ce3b44f6bd4a137c869f21cb25e280434818ef06d2b6`, iOS 9.0
  minimum, dépendances `libSystem` et `libc++` seules, option `mesen_hdpacks`
  présente ; sonde run `39365387492`). Empaqueté sans modification par
  `build-utils/libretro/add_cores.py` sur le paquet livré de 34 cœurs
  (`LibretroCores-c3408821`, run `39081741396`, correctif Nestopia compris),
  recopié octet pour octet : paquet `LibretroCores-4c2186204ce06b50b989689a9c2322068f523a58`,
  run `39366986940`, 35 cœurs, 243 fichiers. GPLv3 ; licence et README de
  libretro/Mesen `0102910c` dans `assets/legal/libretro/`. Aucun BIOS fourni :
  `disksys.rom` (FDS) reste un fichier de l'utilisateur, déclaré au
  vérificateur de BIOS.
- **Choix du moteur** : NES, Famicom, NES hacks et FDS ont Mesen comme
  alternative (`libretro_core_catalog.dart`), choisie dans Réglages du jeu ›
  Émulateur, ou par la page Textures HD (ci-dessous). Les sauvegardes de
  cartouche (`.srm`) sont gérées par l'hôte sous le nom du contenu ; les états
  de sauvegarde d'un cœur ne se chargent pas dans l'autre.
- **Où Mesen lit un pack** (`FolderUtilities::GetHdPackFolder`,
  `HdPackLoader::InitializeLoader`) : `<système libretro>/HdPacks/<nom du
  fichier chargé sans extension>/hires.txt`. Pour un ZIP, l'hôte NeoStation
  extrait la première entrée `.nes`/`.fds`/`.unf`/`.unif` et la passe sous son
  propre nom : c'est ce nom qui compte. Le format est refusé au-delà de 106 ;
  une `<img>` illisible fait échouer tout le pack ; un `<background>`, un
  `<patch>` ou une musique absents sont ignorés. Toutes les images sont
  décodées au démarrage du jeu (aucun chargement paresseux).

- **Défaut de l'hôte trouvé par la sonde** : la première session Mesen du
  Simulateur (run `39370233922`, `mesen-plain-1`, sans pack) s'est terminée
  par un SIGSEGV à l'adresse `0xc0` juste après le démarrage du fil
  d'émulation. L'hôte appelait `retro_set_video_refresh`, les fonctions audio
  et d'entrée **avant** `retro_init` ; Mesen déréférence dans chacune sa
  console, créée dans `retro_init` (`Libretro/libretro.cpp`, `0102910c`).
  RetroArch les appelle après `retro_init` (`runloop.c`,
  `core_init_libretro_cbs`, RetroArch `054ecb46`) : c'est l'ordre pour
  lequel les cœurs du buildbot sont faits. `LibretroCoreHost.m` suit
  désormais cet ordre (toujours avant `retro_load_game`) ; le cœur de test
  compte les appels faits avant et après `retro_init`, et
  `test/libretro_host/host_test.m` exige zéro avant et cinq après. Ce test
  du hôte ne compilait plus depuis la Build 474 (en-tête
  `<neo_cheat_catalog/…>` introuvable) : il prépare maintenant les en-têtes
  publics des pods comme la vérification iPhone et compile le magasin du
  catalogue de triches, sans retirer ni affaiblir aucune vérification. Le
  changement d'ordre vaut pour les 35 cœurs : toute la sonde du Simulateur
  est relancée.

## 3. Page Textures HD pour la NES

- **Identité** (`NeoTextureIdentity::NES`) : le SHA-1 du fichier entier que
  Mesen charge (en-tête iNES compris, `VirtualFile::GetSha1Hash` : le hachage
  des lignes `<supportedRom>` et `<patch>` des packs), schéma `nes-rom-sha1`,
  et le nom du fichier (dossier du pack). Une autre copie de la même cartouche
  avec un autre en-tête a un autre SHA-1 : le pack n'est alors proposé qu'en
  candidat à confirmer, jamais comme exact.
- **Installation** (`NeoTextureInstall.h`, code partagé avec le vérificateur de
  CI) : seuls `hires.txt` et `palette.dat` à la racine et les PNG, OGG et
  correctifs IPS/UPS/BPS sont installés ; le dossier du pack est celui du
  `hires.txt` le moins profond (une variante dans un sous-dossier n'est pas
  installée). `CheckMesenPack` refuse ce que Mesen refuserait (format > 106,
  image manquante ou illisible) et compte la mémoire des images décodées ; le
  pack est refusé quand elle dépasse la moitié de ce que l'app peut encore
  allouer hors jeu (`os_proc_available_memory`).
- **Interrupteur** : l'option du cœur `mesen_hdpacks` par jeu (activée par
  défaut dans le cœur). Pour un jeu lancé avec Nestopia, l'interrupteur est
  affiché éteint avec l'explication ; l'activer (ou installer un pack) fait
  démarrer ce jeu avec Mesen, en passant par le choix de moteur de NeoStation
  (le plugin demande à Dart, qui l'enregistre comme Réglages du jeu ›
  Émulateur). Si ce choix ne peut pas être enregistré, l'interrupteur reste
  éteint et le dit. Pendant une partie sous Mesen, le menu de pause propose
  Textures HD.
- **Textes** : dix textes en douze langues (`tools/textures/labels_*.py`).

## 4. Sources étudiées

### NES (Mesen)

- **GitHub** : découverte dédiée (run `39363594847` : recherches « mesen hd
  pack », « hdnes », sujets `mesen`, `hdpack`, recherche de code
  `filename:hires.txt`) ; `discover.py` lit désormais le `<ver>`, le `<scale>`
  et les `<supportedRom>` de chaque `hires.txt`. Dix dépôts portent un
  `hires.txt`.
- **Forums** : forums.nesdev.org, romhacking.net et metroidconstruction.com
  refusent la lecture automatisée (HTTP 403, run `39363711824`, non contourné) ;
  l'archive nesdev.nes.science, RetroGamingBanter et LaunchBox ont été lus.
- **Hébergeurs** (sonde run `39367094174`, liens publics seulement) : voir les
  exclusions.

Packs ajoutés (5), tous en un geste :

| Pack | Auteur | Jeu (ROM) | Format | État |
|---|---|---|---|---|
| Contra 80s 1.4.2 | Tastic | Contra (USA), `C9EA66BB…` | 106, ×2 | un geste ; vérifié ici (323 fichiers, 208 Mo installés, ≈ 1,6 Go d'images décodées) |
| Megaman: Super | AxlRocks | Mega Man (USA), deux SHA-1 du `<patch>` | 106, ×1 (tuiles redessinées) | un geste ; archive de dépôt vérifiée en CI (300 fichiers, 94 Mo décodés) |
| Pac-Man HDNes Pack | PepCodes | Pac-Man (Namco 1993), `E7D818E1…` | 100, ×4 | un geste ; archive de dépôt vérifiée en CI (25 fichiers, 22 Mo décodés) |
| Super Mario Bros. HD | roney33 | Super Mario Bros. (World), `EA343F4E…` | 104, ×1 | un geste ; archive de dépôt vérifiée en CI (44 fichiers) |
| Super Mario Bros. HD graphics | lyonhrt | même ROM, **à confirmer** (le pack n'en nomme aucune) | HDNes 2, ×4 | un geste après confirmation ; archive de dépôt vérifiée en CI (20 fichiers, 17 Mo décodés) |

Exclus avec leur motif (`tools/textures/sources/excluded-nes-mesen.json`) :
ZII et Battle City (format 108/109 : Mesen 2) ; Zelda II Revamped (fork
mkwong98 de Mesen requis) ; Castlevania de johnnyoak85 (gabarits de
recoloration) ; Dragon Quest III (ROM modifiée et script Lua, que le cœur
n'exécute pas) ; Kiwi Machine Workspace et RetroAami Xtreme (réhébergements
de packs d'autres auteurs) ; un fichier de test d'émulateur ; Ninja Gaiden 1
et 2 (lien Drive 404) ; Metroid HD 1.5 (archives imbriquées, pages de
l'auteur inaccessibles) ; Duck Hunt Remastered (fichier lisible, aucune page
de ses auteurs lisible) ; Donkey Kong de mkwong98 (MediaFire, défi
anti-robot) ; Castlevania de kya (Yandex Disk renvoie une page).

### Autres consoles

Recherche complémentaire (dépôts nommés d'après le jeu seulement, index de
fichiers des RAR lu par requêtes partielles, pages de publication GitHub) :

- **PSP** : neuf packs MESKH4H4 publiés en RAR, donc manuels (extraire puis
  importer le dossier du jeu) : Samurai Shodown Anthology (ULUS10401), Bleach:
  Heat the Soul 1 et 2 (UCJS10008, UCJS10017), Dragon Ball Z: Shin Budokai 1
  et 2 (ULUS10081, ULES00789), Saint Seiya Omega: Ultimate Cosmo (NPJH50699),
  Naruto Shippuden UNH3 (ULUS10518), Naruto UNH2 (ULES01088), God of War:
  Chains of Olympus (UCES00842, variantes PNG seulement). Cinq d'entre eux
  correspondent à des fils de forum des 386 références qui ne montraient
  aucun fichier.
- **PS2** : SRW Z English, pack d'interface 4x (retro-trans, MIT,
  SLPS-25887), un geste, vérifié ici (64 PNG).
- **PS1** : Wip3out HD Texture Pack de NR74W (quatre éditions, 292 textures
  Beetle), un geste ; archive de dépôt vérifiée en CI (292 PNG contrôlés).
- Exclus : Naruto Ultimate Ninja Impact (volumes RAR fractionnés, contenu non
  contrôlé), icônes de boutons de Project Mirai DX (deux textures),
  Phantasy Star Online HD (aucun identifiant, MediaFire), réhébergements
  (sinceohsix/dolphin-hd), un téléchargement contenant une image de jeu.
- N64 et Wii : aucune nouvelle source vérifiable trouvée dans ce cycle.

## 5. Vérifications

Exécutées dans le conteneur :

- `test/texture_identity_test.py` : 58 images synthétiques, dont 6 NES
  (fichier, FDS, ZIP dont le ROM n'est pas la première entrée, ZIP sans ROM,
  7z, nom caché), sous AddressSanitizer et UBSan.
- `test/texture_install_test.py` : 103 vérifications, dont les filtres Mesen,
  la détection du dossier, une installation ZIP réelle et `CheckMesenPack`
  (format 108, image manquante, chemin sortant, PNG endommagé, taille
  décodée, SHA-1 de `<supportedRom>` et `<patch>`).
- `test/texture_labels_test.py` (12 langues, 187 clés natives),
  `test/libretro_bios_requirements_test.py`, `test/libretro_core_options_test.py`
  (35 cœurs), validation des notices libretro (47), `build_catalogue.py --check`.
- `verify_packs.py` avec le pilote natif de l'app, sur le vrai fichier de
  Contra 80s et de SRW Z (`tools/textures/verified.jsonl`).

En CI : sonde des cœurs (runs `39365219934`, `39365387492`), paquet de 35
cœurs (run `39366986940`), puis les contrôles host/native/uikit du catalogue,
la vérification des archives de dépôt, le test Foundation de l'adaptateur Mesen
(`test/texture_catalog_store_test.mm`) et la sonde du Simulateur
`--mesen` (jeu de test NES et pack HD écrits par la sonde : 256 × 240 sans
pack, 512 × 480 avec, 256 × 240 avec `mesen_hdpacks` désactivé) — résultats
au § 7.

## 6. Limites

- Aucun pack n'a été chargé dans un jeu sur iPhone ; le Simulateur prouve que
  le vrai cœur lit un pack depuis `HdPacks/<nom du contenu>` dans l'hôte
  NeoStation, pas le rendu ni les performances d'un pack réel sur iPhone. La
  fiche du cœur avertit que Mesen demande plus de calcul que les autres
  émulateurs NES.
- Contra 80s demande environ 1,6 Go de mémoire au démarrage : il est refusé
  sur les appareils qui ne peuvent pas la donner.
- Identité NES par SHA-1 avec en-tête : un dump avec un autre en-tête n'est
  pas reconnu comme exact.
- Mesen n'a pas de profil de triches revu : les triches restent disponibles
  avec Nestopia.

## 7. Résultats CI

- Sonde des cœurs : runs `39365219934` (échec du paquet épinglé, Mesen pas encore
  empaqueté, corrigé par `44067e20`) et `39365387492` (réussi : binaire du
  buildbot, option `mesen_hdpacks`, marqueurs `HdPacks`, `hires.txt`).
- Paquet de 35 cœurs : run `39366986940` sur `4c218620` (réussi).
- Archives de dépôt : run `39367466788` sur `92b368ce`, parties `nes` et `ps1`
  réussies, cinq enregistrements (quatre packs NES, Wip3out) recopiés dans
  `verified.jsonl` et déclarés dans `ci-records.json`.
- Sonde des hébergeurs : run `39367094174` (motifs des exclusions NES).
- Catalogue, partie host/native/uikit/cores : run `39369224779` (`ea864315`,
  native en échec : la déclaration `invokeMethod:arguments:result:` manquait
  au talon Flutter de la vérification iPhone, ajoutée par `e4b6802a`), puis
  runs `39369640295` (`e4b6802a`) et `39370828138` (`38efdf80`, avec le cas
  UIKit de la page NES) entièrement réussis.
- Sonde du Simulateur, scénarios existants : run `39366986952` (`4c218620`),
  tous les travaux réussis avec la sonde modifiée.
- Sonde Mesen : run `39370233922` (`e4b6802a`) en échec, SIGSEGV de l'hôte
  décrit au § 2 ; corrigé par `31222605`.
- Catalogue `2026-10-20.212eb2401253` : 1 050 packs (PS2 698, GameCube 98,
  Wii 63, PSP 110, 3DS 53, N64 21, PS1 2, NES 5), 408 sources, aucun pack en
  attente.

Contrôles host/native/uikit du catalogue et sonde du Simulateur `--mesen` :
ajoutés ci-dessous à leur fin.
