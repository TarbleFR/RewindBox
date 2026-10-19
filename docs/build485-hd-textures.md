# Build 485 — packs de textures HD PS2 (ARMSX2 embarqué, ABI 8), 18–19 octobre 2026

Demande du mainteneur : permettre d'importer et d'appliquer des packs de textures HD pour les jeux PS2 du moteur ARMSX2 embarqué, si ce n'est pas déjà accessible ; les distinguer des shaders, de la résolution interne et des patchs PNACH ; réutiliser le code existant ; installation dans le dossier que lit le moteur ; activation réelle par jeu ; stabilité (hors thread principal, pas d'archive en mémoire, chemins validés, espace vérifié, annulation sans perte du pack en place) ; douze langues ; IPA de test après les autres compilations. Aucune release, aucun changement de `main`.

## 1. Ce que les sources établissent

Moteur épinglé : `ARMSX2/ARMSX2` révision `9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe` (`iOSv2.6.0`, `build-utils/armsx2/source.json`). Lecture des sources à cette révision :

| Élément | Source amont | Constat |
|---|---|---|
| Remplacement des textures | `pcsx2/GS/Renderers/HW/GSTextureReplacements.cpp` l. 50, 359–415, 535, 657, 1023–1047 | Avec `EmuCore/GS` › `LoadTextureReplacements`, `ReloadReplacementMap()` indexe récursivement `EmuFolders::Textures/<numéro de série>/replacements` par **nom de fichier** (six formes d'empreinte `TEX0`/`CLUT`/région) ; la recherche se fait par empreinte au moment de l'upload ; `UpdateConfig` démarre ou vide le tout quand l'option change ; `ProcessAsyncLoadedTextures` envoie au plus 16 Mo par image. |
| Budget mémoire iOS | même fichier l. 225–242 | Sous `TARGET_OS_IPHONE` le cache est borné à `os_proc_available_memory() / 2`, avec éviction des moins récemment utilisées. |
| Options | `pcsx2/Config.h` l. 974–976 ; `pcsx2/Pcsx2Config.cpp` l. 813–815, 1111–1113 ; `pcsx2/GS/GS.cpp` l. 1244 | `LoadTextureReplacements` (défaut non), `LoadTextureReplacementsAsync` (défaut oui), `PrecacheTextureReplacements` (défaut non) ; `GSUpdateConfig` applique un changement **en jeu, sans redémarrage**. |
| Formats chargés | `pcsx2/GS/Renderers/HW/GSTextureReplacementLoaders.cpp` l. 35–39, 696–765 ; `pcsx2/GS/Renderers/Metal/GSDeviceMTL.mm` | PNG ; DDS non compressé (A8R8G8B8, X8R8G8B8, X8B8G8R8, R8G8B8, A8B8G8R8) ; DDS BC1/BC2/BC3/BC7 natifs si le GPU les déclare, sinon décodés par le processeur en RGBA8 (≈ 4× la mémoire) ; ASTC (2D, empreinte de bloc reconnue) et KTX ASTC linéaire sur GPU Apple2+. BC4/BC5/BC6H et KTX sRGB : refusés par le moteur. |
| Lecteurs de packs iOS | `platforms/ios/app/src/main/cpp/IOS/TexturePackPaths.h`, `TexturePackTar.h`, `TexturePackZstd.h` ; `ARMSX2Bridge.mm` l. 71–73 | L'application ARMSX2 range les entrées d'archive sous `textures/<série>/replacements` (racine GitHub `nom-<40 hex>`, dossier de série, dossier `replacements`) et lit le TAR (GNU long names) éventuellement compressé zstd. |
| NeoStation jusqu'à la 484 | `packages/armsx2_internal_bridge` | `EmuFolders::Textures` est bien `ARMSX2/textures` du conteneur NeoStation, mais **aucune** interface ne permettait d'importer un pack, de l'activer par jeu ni de voir ce que le moteur charge. Le code existait, la fonction n'était pas accessible. |

## 2. Ce que la Build 485 change

### 2.1 Core ARMSX2 — ABI 7 → 8

- `build-utils/armsx2/neostation-core.patch` : deux ajouts en fin de patch (les blocs existants sont inchangés octet pour octet) dans `GSTextureReplacements` : `GetIndexedReplacementCount()` et `GetReplacementCacheUsage(bytes, budget, budget_hit)`, lus sous le verrou du cache. `upstream-files.json` épingle les SHA-256 des fichiers amont concernés.
- `packages/armsx2_internal_bridge/core/ARMSX2TextureReplacements.inc` (inclus par `ARMSX2Core.mm`) et cinq entrées ajoutées en fin de `NeoARMSX2API` :
  - `get_texture_replacements_json` : série, CRC, version, titre ; choix du jeu (−1 / 0 / 1), valeur globale, valeur **effective** (`EmuConfig.GS`) ; sur le thread GS : rendu matériel, textures **reconnues** (indexées) et **chargées**, octets du cache et budget, budget atteint, formats BC/ASTC du GPU ; mémoire disponible.
  - `set_texture_replacements` : écrit `LoadTextureReplacements` dans l'INI **du jeu** par les accesseurs amont (`setPerGameINIBool`) ; à l'activation, aussi `LoadTextureReplacementsAsync = oui` et `PrecacheTextureReplacements = non` ; puis `ReloadGameSettings` + `MTGS::ApplySettings` sur le thread CPU ; relecture de contrôle (refus `write` si l'INI ou `EmuConfig` ne suivent pas).
  - `reload_texture_replacements` : `ReloadReplacementMap()` + purge du cache de textures sur le thread GS, après un remplacement ou une suppression pendant le jeu.
  - `set_texture_boot_preferences` / `apply_texture_boot_preference` : le choix fait dans la bibliothèque (où le CRC, donc le nom de l'INI, est inconnu) est transmis avant le démarrage et écrit dans l'INI du jeu juste après `VMManager::Initialize`, avant la première image.
  - `expand_texture_archive` : `.tar.zst` décodé par les lecteurs du moteur (zstd en flux, TAR, règles de chemins), seules les textures écrites ; bornes 100 000 entrées, 512 Mio par fichier, 512 Mio d'espace laissé libre ; annulation ; codes d'erreur.
- `NEO_ARMSX2_ABI_VERSION 8u`, `abi_version: 8` ; un Core ABI 7 est refusé par l'hôte.

### 2.2 Hôte natif (`packages/armsx2_internal_bridge/ios/Classes`)

- `ARMSX2TexturePackCore.h` (C++20 + zlib, sans Foundation) : identification du disque (SYSTEM.CNF › BOOT2 en ISO 9660 2048 et 2352 octets) ; lecture **en flux** des dossiers, ZIP (Store/Deflate, ZIP64, noms CP437, CRC vérifié ; liens, chiffrement, volumes multiples et autres méthodes refusés) et TAR (lecteur amont) ; plan d'installation (dossier de série, racine GitHub, `replacements`, textures à plat) avec les mêmes règles que `TexturePackPaths::Classify` ; reconnaissance du format par les **octets d'en-tête** (pas l'extension) ; préparation dans `ARMSX2/textures/.neostation-import-<jeton>`, remplacement atomique par renommages, suppression par déplacement, nettoyage des restes d'une import interrompue.
- `ARMSX2TexturePackStore.h/.mm` : dossier résolu depuis la racine ARMSX2 de NeoStation (`<données>/textures`, jamais un chemin de conteneur en dur) ; identité du jeu (session enregistrée → disque → nom de fichier) ; manifeste `NeoStation-texture-pack.json` ; choix par jeu dans `inis/NeoStation-textures.json` ; formats du GPU par Metal.
- `Armsx2TextureBridge.h/.mm` : canal Flutter (`textureStatus`, `texturePick`, `textureInstall`, `textureCancel`, `textureDiscard`, `textureSetEnabled`, `textureRemove`, progression `textureProgress`) ; toutes les opérations sur une file série hors du thread principal ; modifications refusées pendant une partie (elles passent alors par le menu en jeu) ; hôte de session pour le menu en jeu (activation, remplacement et suppression appliqués au jeu en cours).
- Menu en jeu › **Graphismes** › **Textures HD** (`ARMSX2TexturePage`, 8ᵉ ligne ; disque PS2 seulement) : jeu et origine du numéro de série, pack installé, ligne **Moteur** (textures reconnues/chargées, mémoire, budget), interrupteur, import dossier ou archive (ZIP, TAR, TAR.ZST), suppression, aide.

### 2.3 Flutter

- Réglages du jeu › onglet Émulateur d'un jeu PS2 (ARMSX2 embarqué, fichier réel) : `Armsx2TexturePanel` sous l'identité du moteur, avec manette (A active la ligne) ; `lib/services/armsx2_texture_service.dart` ; confirmations par `ConfirmActionDialog` ; aide défilable.
- Textes : `tools/armsx2_textures/strings.json` (99 clés × 12 langues) → `ARMSX2TextureStrings.m` et `lib/l10n/armsx2_texture_locale.dart` par `generate_strings.py` (`--check` vérifie la synchronisation et les paramètres de substitution).
- Crédits : les deux en-têtes amont copiés tels quels (`ios/Classes/upstream/`, SPDX GPL-3.0-or-later conservé) sont crédités dans `docs/LEGAL_AND_CREDITS.md`.

## 3. Ce que l'utilisateur voit

Trois états restent séparés :

1. **Pack installé** (fichiers sur l'appareil) : nombre de textures portant un nom de remplacement ARMSX2, taille, formats, provenance, dossier `ARMSX2/textures/<série>/replacements`.
2. **Fonction activée** pour ce jeu (interrupteur) : depuis la bibliothèque, « s'applique au démarrage du jeu » ; depuis le menu en jeu, « s'applique immédiatement au jeu en cours ».
3. **Reconnu/chargé par le moteur** : uniquement dans le menu en jeu, valeurs rapportées par ARMSX2 lui-même. Un import réussi ne prouve que les fichiers.

Formats acceptés à l'import : dossier ; ZIP (Store, Deflate, ZIP64) ; TAR ; TAR.ZST seulement depuis le menu en jeu (décodeur du moteur). Images utilisables : PNG, DDS (BC1–BC3, BC7, non compressé), ASTC, KTX (ASTC). Les fichiers inutilisables sont comptés et nommés, pas installés.

Avant toute écriture, NeoStation explique : pack nommé pour un autre numéro de série, régions citées dans les noms différentes de celle du jeu, CRC cité différent, numéro de série déduit du seul nom de fichier, remplacement du pack actuel. Un pack prévu pour une autre région ou édition peut ne remplacer qu'une partie des textures : rien n'est présenté comme compatible à partir d'un nom.

## 4. Stabilité et sécurité

- Lecture et extraction en flux (blocs de 256 Kio), jamais d'archive entière en mémoire ; progression et annulation (y compris pendant la décompression d'un TAR.ZST dans le menu en jeu).
- Espace : un TAR.ZST décompressé dans un dossier privé du même volume est déplacé, pas recopié ; l'espace libre est mesuré même avant le premier lancement d'un jeu PS2 (dossier `textures` pas encore créé).
- Chemins : refus des chemins absolus, `..`, liens symboliques, noms invalides ; écriture seulement sous le dossier de préparation, puis renommage.
- Espace : taille annoncée vérifiée avant l'écriture et pendant, 512 Mio toujours laissés libres.
- Échec ou annulation : le dossier de préparation est supprimé, le pack en place n'est pas touché ; le pack précédent n'est effacé qu'une fois le nouveau en place (et, en jeu, réindexé par le moteur).
- Seul `ARMSX2/textures/<série>/replacements` est remplacé ou supprimé : `dumps`, jeux, sauvegardes, cartes mémoire et états ne sont jamais modifiés (vérifié par les tests).
- Aucun préchargement complet : `PrecacheTextureReplacements = non`, chargement asynchrone, budget mémoire du moteur.

## 5. Vérifications

Exécutées dans le conteneur de travail (Linux, sans SDK Apple) sur la source candidate :

- `test/armsx2_texture_packs_test.py` : 150 contrôles du lecteur/installateur de production sur de vrais fichiers (ZIP Store/Deflate/ZIP64 avec 65 536 entrées/CP437, refus lien/traversée/chiffrement/volumes/Deflate64/CRC/répertoire central falsifié ; TAR GNU/pax/tronqué ; dossiers et liens ; ISO 2048 et 2352 ; remplacement atomique, échec qui conserve le pack, `dumps` et sauvegardes intacts, suppression, restes). Même suite sous AddressSanitizer/UBSan : propre. 6 000 archives ZIP/TAR mutées : aucun plantage ni accès invalide.
- `tools/armsx2_textures/generate_strings.py --check`, `test/localization_12_locale_coverage_test.py` : 99 clés, 12 langues, paramètres identiques, chinois traditionnel sélectionné.
- `flutter analyze` (projet entier, Flutter 3.47.2) : aucune erreur ni avertissement ; `flutter test` : 10 tests du panneau (affichage séparé, interrupteur, confirmation autre région, refus, annulation avec progression, suppression, numéro de série inconnu, aide, couverture des langues) + 72 tests ARMSX2/libretro/RPCS3 voisins.
- Contrats : `test/armsx2_bios_hacks_test.py`, `test/armsx2_graphics_test.py` (partie portable), `test/retroarch_baseline_scope_test.py`, `test/libretro_frontend_ui_contract_test.py`, `test/game_audio_handoff_test.py` et les autres contrats source de `libretro-checks.yml`.

Exécutés en CI macOS (`armsx2-core.yml`, `build485-checks.yml`) — résultats au § 7 :

- `test/armsx2_texture_native_test.py` : magasin de production avec Foundation (identification, verdicts, consentement, installation, remplacement, annulation, suppression, INI du jeu, choix au démarrage, chemin `.tar.zst`) et adaptateur du Core en MRC contre des substituts du moteur et le vrai lecteur TAR amont.
- Compilation du Core ABI 8 (patch, adaptateur, export de la table) ; vérification syntaxique iPhone de la page, du magasin, des textes, du pont et du plugin ; `test/armsx2_graphics_ui_test.py` sur UIKit (ligne Textures HD, page avec hôte factice : états séparés, interrupteur, suppression, explication avant installation, aide, numéro de série inconnu).

Non vérifié : affichage effectif des textures dans un jeu, consommation mémoire réelle, comportement sur iPhone. Aucun résultat sur appareil n'est revendiqué.

## 6. Procédure courte et protocole iPhone

Importer et activer :

1. Bibliothèque › jeu PS2 › Réglages du jeu › Émulateur › **Textures HD** › « Importer un dossier » ou « Importer une archive (ZIP, TAR) ». Un TAR.ZST : lancer le jeu, menu pause › Graphismes › Textures HD.
2. Lire la vérification ; confirmer seulement si le pack correspond au jeu.
3. Le premier pack d'un jeu active l'interrupteur ; démarrer le jeu (ou, en jeu, l'effet est immédiat).
4. Menu pause › Graphismes › Textures HD › ligne **Moteur** : textures reconnues et chargées.

Protocole d'essai sur l'iPhone (mainteneur) : un jeu dont la série est connue et un pack connu pour cette série ; vérifier (a) l'import et l'association, (b) « reconnues » > 0 au démarrage, « chargées » qui augmente en jouant et rendu remplacé, (c) désactivation en jeu → textures d'origine, réactivation, (d) relance de l'app puis du jeu → choix conservé, (e) remplacement par un autre pack, puis suppression → `dumps`/sauvegardes intacts, (f) un pack d'une autre région → avertissement, (g) une archive invalide → message, rien d'installé ; noter la mémoire (ligne Moteur) et toute fermeture inattendue avec le journal de l'application.

## 7. Identités et résultats CI

- **Base** : Build 484 livrée, source `e76f40b77fb45e8ce23f161d5d4f4b0dd6fbf3f3`, run `39177384518` ; enregistrement `39a22de2` (tête de `Claude` avant ce cycle). Le pousser de la 485 n'a eu lieu qu'après la fin de cette livraison, aucune autre exécution en cours.
- **Core ARMSX2 ABI 8** : `armsx2-core.yml` run `39178893158` sur `1343906f05e33b40f10f7026a1a6e2327c338d0e`, réussi :
  - job « Compile pinned ARMSX2 iOS framework » : sélection des patchs, `generate_strings.py --check`, `armsx2_texture_packs_test.py`, `armsx2_texture_native_test.py` (magasin Foundation + adaptateur MRC), bibliothèque graphique et traductions, vérification syntaxique iPhone du menu, de la page, du magasin et des textes, compilation du Core (≈ 21 min) et vérification de l'ABI ; identité : révision `9d989ca9`, `iOSv2.6.0`, ABI 8, `arm64`, 12 préréglages / 28 fichiers de shaders, Core SHA-256 `65df97dd253eca2d08bcf638e5fd2de40000579483d4321f585ef7d266319779`, artefact `ARMSX2Core-1343906f…` (`12155939578`, 14 060 684 octets) ;
  - job « Verify ARMSX2 Graphics menu and host ABI » : `armsx2_graphics_ui_test.py` sur UIKit (ligne Textures HD, page avec hôte factice), compilation du plugin et du pont contre Flutter et l'ABI 8, tests Dart ARMSX2 dont `armsx2_texture_panel_test.dart`.
- **Contrôles ciblés** : `build485-checks.yml` run `39178889233` sur `1343906f` réussi ; puis run `39181081216` sur `587a9d9dc3a52cd613388abc73150f034474910a` réussi (source testée de la livraison). Entre les deux, seuls changent le commentaire du podspec et le script ciblé (contrôlé par la clôture `hdtex485_delivery.py`, aucune entrée du Core).
- **Échec causé par ce cycle, corrigé** : `touch-layout-checks.yml` run `39178889242` (partie hôte) sur `1343906f` — `test/armsx2_external_display_test.py` refuse le mot « vendored » dans le podspec du pont (le framework du Core reste un chemin préservé, jamais lié au démarrage) ; commentaire reformulé dans `587a9d9d`, test ajouté aux contrôles ciblés ; la partie hôte complète (40 vérifications) repasse localement. Les deux parties UIKit de ce run (compilation iPhone des sources modifiées, éditeur tactile) ont réussi sur `1343906f`.
- **Échecs déjà présents, identiques sur la base `2a39948b`** (hors périmètre, non modifiés) : `libretro-checks.yml` job `native`, étapes « portable host » et « portable frontend modules » (run `39178889192`, base `39168693769`) ; `unified-cheats.yml` test UIKit `test479LateMatchingPartsAfterClosingCannotRenderOrActivate` (même message, run `39178889190`, base `39168693750`). Les jobs Dart et skin-press de `libretro-checks` (qui couvrent l'onglet Émulateur modifié) ont réussi.
- **Livraison** : à consigner après le run (`retroarch-delivery.yml`, numéro 485).
