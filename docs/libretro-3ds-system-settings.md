# Nintendo 3DS — langue système, région, modèle et données système (conception, 12 octobre 2026)

Chantier 2 de la grande mise à jour (`docs/grande-mise-a-jour-audit-2026-10-12.md`, § 4,
verdicts § 10). Tout en Dart : aucun changement natif, aucun cœur modifié. Les faits
amont cités viennent de la source `azahar-emu/azahar a5c3d4f8` (dernier commit connu avant
le run épinglé du 9 octobre) ; le binaire livré est celui de l'artefact ré-épinglé
`LibretroCores-ba3dc14d…` (run `38195212647`, 12 octobre 2026, archive `azahar_libretro.dylib.zip`
de même taille que le 9 octobre). **Seule preuve des options** : le contrôle `--cores` de
`test/libretro_core_options_test.py` (job `dart`, Ubuntu, de `libretro-checks.yml`).

## 1. Faits établis

- Le cœur `azahar` déclare `citra_region_value` {Auto, Japan, USA, Europe, Australia, China,
  Korea, Taiwan}, `citra_language_value` {English, Japanese, French, Spanish, German, Italian,
  Dutch, Portuguese, Russian, Korean, Traditional Chinese, Simplified Chinese},
  `citra_is_new_3ds` {New 3DS, Old 3DS}, `citra_use_libretro_save_path` {LibRetro Default,
  Azahar Default}. Défaut effectif de langue dans NeoStation : English.
- La langue n'est appliquée par le cœur **que si la région vaut Auto**, puis ajustée aux régions
  acceptées par le jeu ; le cœur n'appelle jamais `RETRO_ENVIRONMENT_GET_LANGUAGE`.
- Langue et région prennent effet au prochain lancement ou après « Redémarrer le jeu » ; le
  **modèle** Old/New 3DS exige une nouvelle session (le reset s'exécute avant la relecture des
  options). `preferred_region_chosen` est sérialisé dans les états de sauvegarde.
- Un seul fichier d'options par cœur : `Documents/Libretro/Config/Azahar.json`
  (`{"values": {clé: valeur}}`), écrit par le natif pendant une session, lu à `loadCore:` ;
  aucune portée par jeu. Dossier utilisateur du cœur : `Documents/Libretro/Saves/Azahar/Azahar/`
  (`config/`, `nand/`, `sdmc/`, `sysdata/`, `cache/`, `cheats/`, `load/`, `states/`).
- Fichiers lus par le cœur dans ce dossier : `sysdata/keys.txt` (optionnel : blob de clés
  intégré ON par défaut en amont), `sysdata/seeddb.bin`, la sauvegarde CFG
  `nand/data/00000000000000000000000000000000/sysdata/00010017/00000000/config` (0x8000
  octets, créée si absente), les titres `nand/00000000000000000000000000000000/title/<high>/<low>/content/…`,
  et les données uniques de console `nand/rw/sys/SecureInfo_A`, `nand/rw/sys/LocalFriendCodeSeed_B`,
  `nand/private/movable.sed`, `sysdata/otp.bin`, `sysdata/mcu.dat`. Les images NAND brutes
  (`nand.bin`, `*.img`, `ctrnand*`) ne sont pas lues (chiffrées par console).
- Preuve sur iPhone : contenu de `Config/Azahar.json`, dossiers créés sous
  `Saves/Azahar/Azahar/`, texte du jeu ; **pas** `session.log` (anneau de 200 lignes en
  niveau Debug).

## 2. Décisions (mainteneur, § 11 de l'audit)

Région et langue exposées toutes deux, avec avertissement « langue ignorée hors Auto » et
proposition de repasser en Auto ; modèle Old/New exposé ; `citra_use_libretro_save_path`
verrouillé à `LibRetro Default` ; import avec titres NAND, clés en option avancée,
**données uniques de console exclues par défaut** (case explicite) ; emplacement : panneau
Émulateurs du système 3DS ; aucune distribution de clés/firmware ; aucun réseau.

## 3. Fichiers

### 3.1 Catalogue — `lib/services/libretro_core_catalog.dart`

Entrée `'azahar'` : `lockedOptions` + `'citra_use_libretro_save_path': 'LibRetro Default'` ;
`settings` :

```dart
LibretroCuratedSetting('citra_region_value', 'setting3dsRegion',
  ['Auto', 'Japan', 'USA', 'Europe', 'Australia', 'China', 'Korea', 'Taiwan'],
  valueLabelKeys: {'Auto': 'region3dsAuto', 'Japan': 'region3dsJapan', 'USA': 'region3dsUsa',
    'Europe': 'region3dsEurope', 'Australia': 'region3dsAustralia', 'China': 'region3dsChina',
    'Korea': 'region3dsKorea', 'Taiwan': 'region3dsTaiwan'}),
LibretroCuratedSetting('citra_language_value', 'setting3dsLanguage',
  ['English', 'Japanese', 'French', 'Spanish', 'German', 'Italian', 'Dutch', 'Portuguese',
   'Russian', 'Korean', 'Traditional Chinese', 'Simplified Chinese'],
  valueLabelKeys: {'English': 'lang3dsEnglish', 'Japanese': 'lang3dsJapanese', 'French': 'lang3dsFrench',
    'Spanish': 'lang3dsSpanish', 'German': 'lang3dsGerman', 'Italian': 'lang3dsItalian',
    'Dutch': 'lang3dsDutch', 'Portuguese': 'lang3dsPortuguese', 'Russian': 'lang3dsRussian',
    'Korean': 'lang3dsKorean', 'Traditional Chinese': 'lang3dsZhHant', 'Simplified Chinese': 'lang3dsZhHans'}),
LibretroCuratedSetting('citra_is_new_3ds', 'setting3dsModel', ['New 3DS', 'Old 3DS'],
  valueLabelKeys: {'New 3DS': 'model3dsNew', 'Old 3DS': 'model3dsOld'}),
```

Effet mécanique : la ligne « Réglages du cœur » du menu en jeu expose ces trois réglages
(pied de page existant « après redémarrage ») ; `test/libretro_core_options_test.py`
(CURATED/LOCKED exacts) est mis à jour explicitement et prouve, en mode `--cores`, chaque
clé et chaque valeur dans le binaire épinglé. `test/libretro_core_catalog_test.dart` adapté.

### 3.2 Langue « Automatique » — `lib/services/libretro_internal_service.dart`

Quand `Config/Azahar.json` n'a **pas** de `citra_language_value` stockée, la requête de
lancement ajoute `optionDefaults['citra_language_value'] = Libretro3dsLanguage.forAppLocale(locale)`
(couche « défaut NeoStation », priorité sous la valeur stockée et au-dessus du défaut du cœur,
déjà appliquée par `LibretroCoreHost applyDefaults`). Table (nouveau
`lib/services/libretro_3ds_language.dart`) : en→English, ja→Japanese, fr→French, es→Spanish,
de→German, it→Italian, pt→Portuguese, ru→Russian, ko→Korean, zh_Hant→Traditional Chinese,
zh→Simplified Chinese, **id→English (repli explicite, affiché)**. Le natif ne change pas.
Test : `test/libretro_3ds_language_test.dart` (12 langues, repli `id`) et un test de
`libretro_internal_service` vérifiant la présence/absence du défaut selon le store.

### 3.3 Magasin d'options — `lib/services/libretro_core_option_store.dart`

`LibretroCoreOptionStore` : `read(coreLibraryName)` → `Map<String,String>` (clés `values`,
valeurs non-String ignorées, fichier absent = vide) ; `write(coreLibraryName, {clé: valeur?})`
(fusion clé par clé, `null` retire la clé, valeurs inconnues conservées, écriture atomique
`<nom>.json.tmp` + `rename`, format identique au natif : `{"values": {...}}` avec
`JsonEncoder.withIndent`) ; **refus** avec `LibretroCoreOptionStoreError.sessionActive`
quand `LibretroInternalBridge.isSessionActive()` est vrai (fenêtre `launching` incluse).
Nom de fichier : `SafeFolderName(library_name)` reproduit en Dart (`libraryFileName`) ;
constante `azaharLibraryName = 'Azahar'` et test liant cette constante au nom déclaré par
le cœur (fixture `core_info_5a74858a.json` ou journal `[HOST] loaded Azahar`). Chemin :
`LibretroInternalService.configDirectory()`.

### 3.4 Page « Nintendo 3DS » — `lib/screens/libretro/libretro_3ds_system_screen.dart`

`Libretro3dsSystemScreen` (`LibretroPageNavigation`, `WidgetsBindingObserver`, `libretroPage`,
`libretroPageAppBar(context, 'system3dsTitle')`, rafraîchissement au retour au premier plan).
Sections :

1. **Système** — trois sélecteurs (feuille de choix navigable à la manette, modèle des
   réglages existants des pages libretro) : Langue (« Automatique (langue de NeoStation :
   {language}) » = valeur absente + les 12 valeurs du cœur), Région (8 valeurs), Modèle
   (2 valeurs). Note `system3dsRestartHint` (« Langue et région s'appliquent au prochain
   lancement ou après Redémarrer le jeu ; le modèle à la prochaine session »). Quand une
   région autre qu'Auto est choisie : avertissement `system3dsLanguageIgnored` + bouton
   `system3dsUseAutoRegion` qui remet la région sur Auto. Note `system3dsLanguageAdjusted`
   (langue ajustée aux régions du jeu). Note `system3dsSavestateRegion` (états de sauvegarde
   antérieurs). Écriture par `LibretroCoreOptionStore` ; erreur `sessionActive` affichée
   (`system3dsSessionActive`), jamais présentée comme enregistrée sans relecture.
2. **Données système** — inventaire (`Libretro3dsSystemDataService.inventory()`) : lignes
   `keys.txt` (optionnel, `system3dsKeysOptional`), `seeddb.bin`, `config` CFG, titres NAND
   (nombre, taille), polices CHN/KOR/TWN (titres `0004009b/00014x02` présents ou non,
   `system3dsFontsMissing`), données de console (présentes/absentes), avec statut et
   taille ; boutons `system3dsImport` (assistant), `system3dsRestoreBackup` (dernière
   sauvegarde), rappel des chemins réels (non traduits) ; note `system3dsNoDistribution`
   (NeoStation ne fournit aucun fichier Nintendo).

Assistant d'import (dialogue en étapes, `pausePageNavigation()`/`resumePageNavigation()`
autour des sélecteurs) : (1) source — ZIP ou fichiers isolés par `FilePicker.pickFiles(type:
FileType.any, allowMultiple: true)`, ou dossier par `ExternalFolderAccess.pickAndActivateFolder`
(dump GodMode9 « citra », dossier utilisateur Citra/Lime3DS/Azahar, dossier `nand`) ;
(2) analyse (isolate) → plan : éléments reconnus, créés/remplacés, taille, éléments
refusés avec raison ; case « Inclure les données de console (identifient votre console) »
décochée par défaut ; case « Inclure les clés » (avancé) décochée par défaut ;
(3) confirmation ; (4) installation avec progression ; (5) résultat (installés, remplacés
avec chemin de sauvegarde, ignorés, échecs avec code technique brut).

### 3.5 Service — `lib/services/libretro_3ds_system_data_service.dart`

- Racines : `userDirectory()` = `<savesDirectory>/Azahar/Azahar` (créé seulement à
  l'installation) ; `backupsDirectory()` = `Documents/Libretro/Backups/Azahar` ; staging
  `<savesDirectory>/Azahar/.neostation-3ds-import-<yyyyMMdd-HHmmss>` (même volume → `rename`).
- `inventory()` lecture seule (jamais de création de dossier).
- `analyze(sources)` → `Libretro3dsImportPlan` : détection par **contenu et chemin
  relatif**, jamais par le seul nom du conteneur :
  - ZIP : signature `PK\x03\x04`, `ZipDecoder().decodeStream` ; limites 2000 entrées,
    1 Gio total, 512 Mio/fichier ; refus `..`, chemins absolus, liens symboliques
    (`isSymbolicLink` ou mode `0xA000`), `__MACOSX` ignoré ; 7z et autres : refus
    `unsupportedArchive` (surface réduite volontairement) ;
  - dossier : parcours borné (profondeur 8, 5 000 entrées, `followLinks: false`) ;
  - reconnaissance (chemin relatif normalisé, insensible à la casse, préfixes `citra/`,
    `azahar/`, `user/`, `nand/` tolérés) :
    `sysdata/keys.txt` ou `aes_keys.txt` → `keys.txt` (texte ASCII, lignes `slot0x..=hex`,
    `generator=`, `common0=` ; ≤ 64 Kio) ;
    `sysdata/seeddb.bin` (taille 16 + 32·n, n ≥ 0, ≤ 1 Mio) ;
    `nand/data/<32 hex>/sysdata/00010017/00000000/config` (exactement 0x8000 octets,
    `data_entries_offset` plausible à 0x0 … 0x8000 ; installé sous l'id0 **de
    destination** = `00000000000000000000000000000000`) ;
    titres `nand/<32 hex>/title/<8 hex>/<8 hex>/content/*.app|*.tmd|*.cmd` et
    `.../content/cmd/*` (noms hexadécimaux, installés sous l'id0 de destination) ;
    données de console (liste § 1) : classées `consoleUnique`, exclues sauf case cochée ;
    `nand.bin`, `*.img`, `ctrnand*`, `twln*`, `essential.exefs` : refus `rawNandImage` ;
    tout le reste : `ignored` (listé, jamais copié).
  - plan : pour chaque élément, chemin de destination, `exists`, `identical` (taille + SHA-256
    si taille égale), action `create` / `replace` / `skipIdentical`.
- `install(plan, {includeConsoleUnique, includeKeys})` : refus si session libretro active ;
  vérification d'espace libre non disponible (dart:io) → échec propre à l'écriture ;
  staging puis vérification octet à octet (taille + SHA-256) ; sauvegarde des fichiers
  remplacés dans `Backups/Azahar/<stamp>/<chemin relatif>` (jamais supprimée par l'app) ;
  `rename` fichier par fichier ; en cas d'échec, restauration depuis la sauvegarde de ce
  passage et rapport ; journal `Documents/Diagnostics/libretro-3ds-import-<stamp>.jsonl`
  (chemins relatifs, tailles, résultats, aucun contenu).
- `restoreLastBackup()` : liste des sauvegardes par horodatage, restauration de la plus
  récente (copie inverse avec sauvegarde du courant), refus en session.
- Jamais d'écriture hors `Saves/Azahar/`, `Backups/Azahar/` et `Diagnostics/`.

### 3.6 Panneau Émulateurs — `lib/widgets/libretro_engine_panel.dart`

`enum LibretroEnginePage { skins, systemData3ds, biosChecker }` ; `pages` insère
`systemData3ds` entre `skins` et `biosChecker` **seulement quand `_console?.id == '3ds'`** ;
`_rowText` : icône `Symbols.sd_card_rounded`, titre `engine3dsSystem`, sous-titre
`engine3dsSystemSubtitle` ; `pushPage`/`pageFor` ouvrent `Libretro3dsSystemScreen`.
`test/libretro_engine_settings_test.dart` : les attentes existantes (psx, md, gba, null)
restent identiques ; nouveau cas 3ds = `[skins, systemData3ds, biosChecker]` et ouverture.

### 3.7 Traductions — `lib/l10n/libretro_locale.dart` (douze cartes)

Nouvelles clés (ajoutées en fin de chaque carte, mêmes paramètres) : `system3dsTitle`,
`engine3dsSystem`, `engine3dsSystemSubtitle` (`{console}`), `setting3dsLanguage`,
`setting3dsRegion`, `setting3dsModel`, `lang3dsAutomatic` (`{language}`), `lang3dsEnglish`,
`lang3dsJapanese`, `lang3dsFrench`, `lang3dsSpanish`, `lang3dsGerman`, `lang3dsItalian`,
`lang3dsDutch`, `lang3dsPortuguese`, `lang3dsRussian`, `lang3dsKorean`, `lang3dsZhHant`,
`lang3dsZhHans`, `lang3dsFallback` (`{language}` : « Indonésien n'existe pas sur 3DS : anglais »),
`region3dsAuto` … `region3dsTaiwan` (8), `model3dsNew`, `model3dsOld`, `system3dsRestartHint`,
`system3dsLanguageIgnored`, `system3dsUseAutoRegion`, `system3dsLanguageAdjusted`,
`system3dsSavestateRegion`, `system3dsSessionActive`, `system3dsSaved`,
`system3dsDataTitle`, `system3dsKeys`, `system3dsKeysOptional`, `system3dsSeeddb`,
`system3dsConfig`, `system3dsTitles` (`{count}`, `{size}`), `system3dsFonts`,
`system3dsFontsMissing`, `system3dsConsoleData`, `system3dsPresent`, `system3dsAbsent`,
`system3dsImport`, `system3dsImportZip`, `system3dsImportFolder`, `system3dsImportFiles`,
`system3dsAnalyzing`, `system3dsPlanCreate`, `system3dsPlanReplace`, `system3dsPlanIdentical`,
`system3dsPlanIgnored`, `system3dsIncludeConsoleData`, `system3dsIncludeConsoleDataHelp`,
`system3dsIncludeKeys`, `system3dsIncludeKeysHelp`, `system3dsConfirm`, `system3dsInstalling`,
`system3dsInstalled`, `system3dsReplaced` (`{backup}`), `system3dsSkipped`, `system3dsFailed`,
`system3dsRestoreBackup`, `system3dsRestored`, `system3dsNoBackup`, `system3dsNoDistribution`,
`system3dsRejectedRawNand`, `system3dsRejectedArchive`, `system3dsRejectedTooLarge`,
`system3dsRejectedUnsafe`, `system3dsRejectedInvalid`, `system3dsNothingRecognized`,
`system3dsTechnicalCode` (`{code}`). Valeurs brutes (« Japan », « keys.txt », chemins,
`0004009b`) jamais traduites. `test/libretro_locale_test.dart` (parité, paramètres, zh_Hant)
et `test/libretro_frontend_ui_contract_test.py` (aucun texte en dur dans `lib/screens/libretro`)
restent les gates.

### 3.8 Vérificateur de BIOS (optionnel, si le temps le permet)

Nouvel emplacement `saves/<core>/<sub>` dans `LibretroBiosLocation.parse` et entrées
optionnelles azahar (`keys.txt`, `seeddb.bin`, `config`) avec `binaryStrings` ; sinon la
note `biosNoteAzahar` est complétée par un renvoi à la page 3DS.

## 4. Tests

| Fichier | Vérifie |
| --- | --- |
| `test/libretro_core_options_test.py` (CURATED/LOCKED mis à jour) | clés/valeurs des trois réglages et du verrou dans le binaire (`--cores` en CI) |
| `test/libretro_core_catalog_test.dart` | entrée azahar : réglages, verrou, libellés présents dans les douze cartes |
| `test/libretro_core_option_store_test.dart` | lecture/écriture/fusion/suppression de clé, valeurs inconnues conservées, atomicité (fichier `.tmp` absent après), format identique à une fixture écrite par le natif, refus en session (canal simulé `isSessionActive`) |
| `test/libretro_3ds_language_test.dart` | table des 12 langues, repli `id` → English |
| `test/libretro_3ds_system_data_service_test.dart` | fixtures synthétiques : ZIP valide (keys/seeddb/config/titres/données de console), traversée, lien symbolique, trop d'entrées, 7z et NAND brute refusés, dossier Citra avec `aes_keys.txt` → `keys.txt`, id0 source ≠ destination, identique ignoré, remplacement avec sauvegarde, échec simulé → restauration, session active → refus, données de console exclues par défaut, aucune écriture hors des racines |
| `test/libretro_3ds_system_screen_test.dart` | page : sélecteurs, avertissement région fixe + bouton Auto, note modèle, erreur session, inventaire, manette (modèle `libretro_bios_checker_screen_test.dart`) |
| `test/libretro_engine_settings_test.dart` | ligne 3DS pour `3ds` seulement, ordre, ouverture |
| `test/libretro_locale_test.dart`, `python3 test/localization_12_locale_coverage_test.py`, `python3 test/libretro_frontend_ui_contract_test.py` | douze langues, aucun texte en dur |

CI : `libretro-checks.yml` et `libretro-simulator.yml` se déclenchent sur push pour le
catalogue ; les tests Dart nouveaux sont ajoutés à la liste `flutter test` de
`libretro-checks.yml:102` et de `retroarch-delivery.yml` ; bloc `BUILD447_3DS_DELTA` dans
`verify_delivery_reuse.py`.

## 5. Limites annoncées dans l'interface

Langue ignorée hors région Auto (cœur) ; langue ajustée aux régions du jeu en Auto ;
modèle à la prochaine session ; aucune distribution de clés, firmware ou polices
(remplacements open source intégrés sauf polices CHN/KOR/TWN) ; images NAND chiffrées
refusées ; réglages par console, pas par jeu ; aucune validation iPhone revendiquée.
