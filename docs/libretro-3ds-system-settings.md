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

## 6. Déviations consignées (implémentation du 12 octobre 2026)

Écarts par rapport aux § 3 et 4, minimaux et motivés ; rien n'est validé sur iPhone.

### 6.1 Catalogue, langue automatique, défaut de lancement (§ 3.1, 3.2)

- `Libretro3dsLanguage` porte trois membres de plus que l'API demandée : `optionKey`,
  `fallback` et `isFallback(Locale)` (vrai seulement pour `id` ; faux pour `en` et pour
  une langue que NeoStation ne livre pas, car `LibretroLocale.localeKey` affiche alors
  NeoStation en anglais : l'anglais 3DS est une correspondance, pas le repli affiché).
- Libellés : `region3dsUsa` = « United States » en anglais (« USA » en allemand),
  `model3dsNew`/`model3dsOld` = « New model (New Nintendo 3DS) » / « Original model
  (Nintendo 3DS) », `system3dsTitle` = « Nintendo 3DS system » (et non le seul nom de
  produit), pour garder les libellés distincts de l'anglais et les noms de produits
  intacts. `test/libretro_locale_test.dart` : l'ensemble d'exemptions `identical` existant
  gagne 14 noms de régions réellement identiques à l'anglais dans leur langue (fr :
  Europe ; de : Japan/China/Korea/Taiwan ; es : Australia/China ; it : Australia/Taiwan ;
  pt : China/Taiwan ; id : Australia/Korea/Taiwan), par le mécanisme existant du test ;
  aucune assertion affaiblie.
- `test/libretro_core_catalog_test.dart` : l'attente exacte de `lockedOptions` du test
  « DS and 3DS options NeoStation needs are locked for the session » inclut désormais
  `citra_use_libretro_save_path` (remplacement de contrat commenté dans le test) ; un
  nouveau test vérifie les trois réglages azahar, leurs libellés dans les douze cartes et
  le rendu de `coreSettings()` dans chaque langue.
- Aucun test Dart existant ne couvrait `optionDefaults` des requêtes de lancement : le
  défaut par lancement est testé dans le nouveau `test/libretro_3ds_launch_default_test.dart`
  (canaux `path_provider` et `neostation/libretro_internal` simulés, Documents temporaire).
- Le service lit `Config/Azahar.json` par son propre `_storedCoreOptions('Azahar')` privé
  (le lancement ne dépend pas du magasin § 3.3 écrit en parallèle) ; il n'écrit jamais le
  fichier d'options.
- `test/libretro_core_options_test.py` contrôle en plus les listes de valeurs exactes
  (`CURATED_CHOICES`) des trois réglages azahar sans `--cores` ; renforcement seulement.

### 6.2 Magasin d'options et service de données (§ 3.3, 3.5)

- Un échec de la sonde `isSessionActive` (PlatformException, etc.) est rapporté comme
  `sessionActive` avec `technicalDetail` « isSessionActive probe failed: … »
  (fail-closed, aucune écriture) : le contrat ne nomme aucune erreur distincte pour un
  état de session inconnu.
- `Libretro3dsInstallStatus` ajoute `rolledBack` et `notAttempted` : après un échec de
  commit, les éléments déjà déplacés dans le passage sont remis en place, le reste n'est
  pas tenté ; la page affiche ces deux états comme `system3dsFailed` + code technique.
- Reconnaissance des titres et de `config` par suffixe de chemin (`title/<8 hex>/<8 hex>/content/<hex>.app|.tmd|.cmd`,
  `content/cmd/<hex>.cmd`, `data/<32 hex>/sysdata/00010017/00000000/config`), tout
  préfixe toléré et id0 facultatif pour les titres (CTRNAND réel, dumps GodMode9) : un
  sur-ensemble de la règle « préfixes `citra/`, `azahar/`, `user/`, `nand/` tolérés » ;
  clés, seeddb et données de console reconnues par nom de base n'importe où et validées
  par contenu. Les entrées contenant un segment `sdmc` ou `Nintendo 3DS` sont listées
  comme ignorées ; un `config` nu n'est accepté que choisi seul.
- Le parcours de dossier élague les dossiers connus sans données système d'un dossier
  utilisateur Citra/Azahar (`sdmc`, `cache`, `states`, `shaders`, `log`, `logs`, `dump`,
  `screenshots`, `load`, `cheats`, `__MACOSX`, `.git`) en plus des bornes profondeur 8 /
  5 000 entrées ; `__MACOSX`, `.DS_Store`, `Thumbs.db`, `desktop.ini` et `._*` ne sont
  jamais listés.
- Refus de conteneur entier (entrée dangereuse, lien symbolique, trop d'entrées, trop
  volumineux, fichier trop volumineux, ZIP illisible) = un seul élément refusé dont
  `sourceEntry` est le nom du conteneur et `relativeTarget` nul (comme le flux RPCS3) ;
  dans un dossier, un lien symbolique ne refuse que cette entrée, trop d'entrées refuse
  le dossier entier.
- `Libretro3dsRejection.invalid` couvre aussi : destination en double entre sources (la
  première gagne), source manquante ou illisible, entrée ZIP chiffrée ou compression non
  prise en charge, source modifiée entre l'analyse et l'installation.
- Images NAND brutes : par nom (`nand.bin`, `*.img`, `ctrnand*`, `twln*`,
  `essential.exefs`) et par contenu (`NCSD` à 0x100) sur fichiers isolés, fichiers de
  dossier et entrées ZIP (préfixe diffusé en flux, au plus 0x200 octets décompressés) ;
  une entrée ZIP au-dessus de 512 Mio est rapportée `fileTooLarge` pour toute l'archive
  avant tout contrôle de contenu.
- Validation : clés = ASCII ≤ 64 Kio, chaque ligne hors commentaire `nom=hex`, au moins
  une clé `slot0x..`/`generator`/`commonN` ; seeddb = 16 + 32·n, ≤ 1 Mio, compte déclaré
  ≤ n ; config = exactement 0x8000 octets, `total_entries` ≤ 1479,
  `data_entries_offset` ≤ 0x8000 ; données de console ≤ 1 Mio ; titres non vides.
- Horodatages UTC (staging, sauvegarde, journal) ; deux passages la même seconde donnent
  `Backups/Azahar/<stamp>-2`, `-3`… et s'ajoutent au même journal ; l'événement `end` du
  journal garde les comptes par statut sous `counts` et caviarde les racines absolues.
- `restoreLastBackup()` recopie seulement les fichiers (ceux créés par le passage
  restauré ne sont pas supprimés), via un staging `.neostation-3ds-restore-<stamp>` à
  côté du dossier utilisateur ; les fichiers courants écrasés vont dans un nouveau dossier
  de sauvegarde, qui devient la plus récente.
- Le magasin trie les clés à l'écriture (l'ordre natif de NSJSONSerialization n'est pas
  spécifié) ; un élément `skipIdentical` du plan n'est pas revérifié à l'installation.

### 6.3 Page, panneau Émulateurs, CI (§ 3.4, 3.6, 4)

- `Libretro3dsSystemScreen` reçoit `languageNames` (la liste des langues de l'application,
  `AppLocale.supportedLanguages`, passée par `LibretroEngineSettingsPanel.pageFor`) pour
  nommer la langue de NeoStation dans l'entrée « Automatique » et dans `lang3dsFallback` :
  les pages de `lib/screens/libretro` ne peuvent pas référencer `AppLocale`
  (`test/libretro_frontend_ui_contract_test.py`) et le catalogue n'a pas de libellé pour
  l'indonésien. Sans cette liste, le libellé 3DS de la langue correspondante est utilisé
  (la clé de catalogue pour le repli).
- Les étapes (2) plan et (3) confirmation sont un seul dialogue : le bouton principal est
  `system3dsConfirm` suivi du nombre d'éléments sélectionnés par les cases, les deux
  cases sont toujours affichées, décochées, et désactivées quand le plan ne contient
  aucun élément de leur sorte ; `system3dsNothingRecognized` remplace le bouton quand
  rien n'est reconnu. L'analyse n'est pas relancée avant l'installation.
- L'analyse s'exécute par `Isolate.run` sur `Libretro3dsSystemDataService.analyzeSources`
  (chemin du dossier utilisateur résolu avant) ; la page accepte une analyse, un sélecteur
  de fichiers et un sélecteur de dossier injectés pour les tests. ZIP et fichiers isolés
  passent tous deux par `FilePicker.pickFiles(type: FileType.any, allowMultiple: true)`.
- Progression d'installation indéterminée (le service n'expose aucun rappel de
  progression) ; le dialogue de progression ne se ferme pas par B.
- Clés réutilisées faute de clé dédiée dans le catalogue : `controlsEditDone` (« Done »)
  ferme le dialogue de résultat ; `cancel` annule le plan ; la confirmation de
  restauration (`ConfirmActionDialog`) reprend `system3dsRestoreBackup` et
  `system3dsPlanReplace` (« À remplacer (une sauvegarde est conservée) »).
- Le bouton `system3dsRestoreBackup` est désactivé sans sauvegarde, avec la note
  `system3dsNoBackup` ; l'erreur `noBackup` du service reste traitée.
- Chemins réels : le dossier utilisateur est montré comme dans Fichiers
  (`libretroLibraryLocation`), chaque ligne de l'inventaire montre son chemin relatif brut,
  la paire brute `clé = valeur` apparaît sous chaque réglage stocké ; les polices sont
  listées par titre `0004009b/<low>`.
- Les dialogues de la page reprennent les raccourcis de `libretroPage` (Entrée et flèches
  réservés à la couche manette) pour qu'une touche n'agisse jamais deux fois ; aucun
  nouveau calque `GamepadNavigationManager` n'est poussé pour eux.
- Les commandes de la page restent actives pendant une écriture, un import ou une
  restauration (leurs gestionnaires refusent la réentrance ; un indicateur tourne dans
  l'en-tête de la carte) : constaté en test, désactiver la commande focalisée
  (`onPressed: null`) pendant que le dialogue de choix se ferme fait sortir le focus de la
  page (Flutter, `unfocus(previouslyFocusedChild)` remonte jusqu'à la route précédente) et
  la manette n'agit plus sur rien de visible.
- `test/libretro_engine_settings_test.dart` : `_newKeys` gagne `engine3dsSystem` et
  `engine3dsSystemSubtitle` (renforcement) ; les attentes psx/md/gba/null sont inchangées.
- `BUILD447_3DS_DELTA` liste aussi `build-utils/verify_delivery_reuse.py` ; les fichiers
  non suivis ne sont jugés par `verify_delivery_reuse.py` qu'une fois commités.
