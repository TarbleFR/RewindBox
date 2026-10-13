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
    `nand.bin`, `*.img`, `ctrnand*`, `twln*` : refus `rawNandImage` (Build 448 :
    `essential.exefs` n'en fait plus partie, voir § 7) ;
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
  pas tenté ; la page affiche ces deux états comme `system3dsFailed` + code technique
  (remplacé, § 6.4 : textes distincts `system3dsRolledBack`, `system3dsNotAttempted`).
- Reconnaissance des titres et de `config` par suffixe de chemin (`title/<8 hex>/<8 hex>/content/<hex>.app|.tmd|.cmd`,
  `content/cmd/<hex>.cmd`, `data/<32 hex>/sysdata/00010017/00000000/config`), tout
  préfixe toléré et id0 facultatif pour les titres (CTRNAND réel, dumps GodMode9) : un
  sur-ensemble de la règle « préfixes `citra/`, `azahar/`, `user/`, `nand/` tolérés » ;
  clés, seeddb et données de console reconnues par nom de base n'importe où et validées
  par contenu. Les entrées contenant un segment `sdmc` ou `Nintendo 3DS` sont listées
  comme ignorées ; un `config` nu n'est accepté que choisi seul (§ 6.4 : élaguées avant
  les limites, plus listées ; le `config` nu exige désormais un fichier choisi seul dans
  le code aussi).
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
- Images NAND brutes : par nom (`nand.bin`, `*.img`, `ctrnand*`, `twln*` ; `essential.exefs`
  jusqu'à la Build 447, lu depuis la Build 448 — § 7) et par contenu (`NCSD` à 0x100) sur fichiers isolés, fichiers de
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
  de sauvegarde, qui devient la plus récente (§ 6.4 : seule une sauvegarde complète est
  restaurée, vérifiée d'abord ; les courants y vont par `rename`).
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
  `system3dsPlanReplace` (« À remplacer (une sauvegarde est conservée) ») (remplacé, § 6.4 :
  texte dédié `system3dsRestoreConfirm` avec la date).
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

### 6.4 Corrections après revue contradictoire (12 octobre 2026, révision de `379e5906`)

Rien n'est validé sur iPhone. Ce paragraphe remplace, là où ils diffèrent, les points des
§ 3.4, 3.5, 6.2 et 6.3. **Sources vérifiées** (lecture seule, `azahar-emu/azahar a5c3d4f8`,
fichiers bruts) : `hw/unique_data.{h,cpp}`, `file_sys/otp.{h,cpp}`, `hle/service/am/am.cpp`,
`hw/aes/key.{h,cpp}`, `hw/rsa/rsa.cpp`, `hw/ecc.cpp`, `file_sys/title_metadata.{h,cpp}`,
`file_sys/signature.h`, `file_sys/seed_db.cpp`, `file_sys/ncch_container.cpp`,
`common/file_derived.h`, `common/common_paths.h`. Non vérifié : `mcu.dat` (aucun chargeur
trouvé dans ces sources, borne inchangée : non vide, ≤ 1 Mio).

**Passages sûrs (M1, M2, M3, m1b, m2, m9, m10).** Un import ou une restauration est un
passage : dossier `Backups/Azahar/<stamp>[-n]` créé d'emblée, journal préalable
`.neostation-pass.jsonl` (une ligne JSON par étape, écrite et `flush` **avant** l'étape :
`begin` avec les unités, `backup`, `install` avec chemin, taille et SHA-256 des copies
installées, `manifest`, `committed`, `end`), staging
`Saves/Azahar/.neostation-3ds-{import,restore}-<nom du passage>`. Ordre : (1) staging complet
dans un isolate d'arrière-plan (`Isolate.run`, blocs de 64 Kio écrits par `writeFromSync`,
arrêt dès que le nombre d'octets écrits dépasse la taille déclarée, contrôle de la méthode
de compression dans les deux en-têtes), puis vérification de chaque copie : SHA-256 de
l'analyse (tous les fichiers reconnus sont hachés à l'analyse, sauf un fichier de titre
de plus de 64 Mio, comparé par taille et date avant et après le staging puis revalidé) ;
(2) **toutes** les sauvegardes par `rename` (cible → `Backups/Azahar/<stamp>/<chemin>`) avant
toute installation, puis le manifeste `.neostation-manifest.json` (chemin, taille,
SHA-256 de chaque fichier sauvegardé) ; (3) les installations par `rename` (staging →
cible), `committed`, puis le marqueur `.neostation-complete.json` (SHA-256 du manifeste),
écrit en dernier ; (4) suppression du staging, `end`. Aucune copie sur un fichier vivant,
aucun espace libre nécessaire (`Backups` et `Saves` sont dans le même conteneur
`Documents/Libretro`) ; une copie (vérifiée par SHA-256, source intacte en cas d'échec)
n'intervient que sur `EXDEV` (volumes différents, jamais sur iOS ; testé entre `/tmp` et
`/dev/shm`). Les noms des métadonnées commencent par un point (masquées dans Fichiers).

Retour arrière (échec en cours de passage ou reprise) : renames inverses, du dernier
élément au premier ; un élément installé n'est retiré que s'il est encore **octet pour
octet** ce que le passage a installé (chemins, tailles, SHA-256 du journal) ; rien n'est
écrasé : si l'emplacement d'un original est occupé, les deux sont gardés et signalés
(`kept`) ; un original introuvable est nommé (`missing`, aussi dans le rapport d'installation
et le journal Diagnostics). Un passage annulé ne laisse aucune sauvegarde : ses originaux
sont revenus par `rename` et son dossier vidé est supprimé (contrat remplacé du test
« a commit failure… », qui gardait une copie dans `Backups/Azahar/20261012-100001`).

Reprise (`recoverUnfinished()`, à l'ouverture de la page, avant chaque analyse et en tête
de `install`/`restoreLastBackup`, jamais pendant une session libretro : même sonde
fail-closed) : un passage sans `committed` est annulé depuis son journal, un passage
`committed` est terminé (marqueur, staging), puis les dossiers de staging orphelins sont
supprimés. Issues : `rolledBack`, `completed`, `partial` (original perdu ou emplacement
occupé : clos et signalé, ne bloque rien), `failed` (une étape en erreur d'E/S ou un
journal invalide : le passage reste ouvert, est réessayé, et install/restore sont refusés
avec `unfinishedPass` d'ici là). Les opérations d'un même service sont sérialisées (verrou
par instance, sans futur partagé entre zones).

Sauvegardes : seules les sauvegardes **complètes** sont listées et restaurables (marqueur,
manifeste dont le SHA-256 concorde, chaque fichier présent à sa taille) ; un dossier vide,
partiel, d'un passage interrompu ou d'une révision antérieure n'est ni listé ni supprimé.
`backups()` rend des `Libretro3dsBackup` (`path`, `name`, `kind` import/restore,
`createdAt`, `files`, `units`). La restauration vérifie d'abord le SHA-256 de chaque fichier
(`backupDamaged` sinon, rien d'écrit), copie dans le staging (la sauvegarde reste
intacte), déplace les fichiers ou dossiers `content` courants dans un nouveau passage
complet, puis installe ; une restauration de 0 fichier est une erreur
(`Libretro3dsRestoreReport.succeeded`). Les fichiers ajoutés depuis (clés, données de
console, nouveaux titres) ne sont pas supprimés.

Titres (m1b) : groupés par `<high>/<low>`, installés ou refusés en unité : tout le
dossier `content` existant part dans la sauvegarde et le dossier `content` préparé prend
sa place (`rename` de dossiers). Refus `incompleteTitle` sans `.tmd` valide et `.app`, ou
quand un fichier du titre est refusé (un doublon entre sources ne refuse pas le titre :
la première source gagne). Le plan expose `retiredTargets`, le rapport `retired` (anciens
fichiers du titre absents de l'import, partis avec lui dans la sauvegarde). Le crochet de
test `beforeCommit` est appelé pour chaque fichier d'une unité juste avant son `rename` ;
`beforeBackup` et `beforeFinish` s'y ajoutent (tests).

**Analyse.**
- m1a : la recherche de signature d'archive ne s'applique plus qu'aux fichiers non
  reconnus ; `NCSD` à 0x100 reste refusé partout. `.app` : `NCCH` à 0x100 **ou** les
  conteneurs que le cœur ouvre lui-même pour le contenu installé, `Z3DS` (compressé) et
  `AZCR` (chiffrement propre à la console) à 0 (`NCCHContainer::AutoOpenNCCHNCSD`), ou un
  titre DS (drapeau TWL `0x8000` de l'identifiant haut) — écart motivé : « NCCH seul »
  refuserait le contenu installé par Azahar. `.tmd` : vérifié comme `TitleMetadata::Load`
  (type de signature, corps de 0x9C4 octets après la signature alignée, blocs de contenu
  dans le fichier) et l'identifiant de titre du corps doit être celui du dossier.
- m3 : limites ZIP appliquées après élagage : `sdmc`, `Nintendo 3DS`, `__MACOSX`, `.git`
  à toute profondeur ; `cache`, `states`, `shaders`, `log`, `logs`, `dump`, `screenshots`,
  `load`, `cheats` aussi, sauf comme premier dossier commun du ZIP (le dossier zippé
  lui-même, comme le dossier choisi d'un parcours) ; les entrées élaguées ne sont plus
  listées (comme dans un parcours de dossier) ; les limites de taille ne comptent que les
  fichiers reconnus ; plafond brut de 100 000 entrées. `nintendo 3ds` élagué aussi dans les
  parcours (insensible à la casse).
- m4 : un dossier au-delà de la profondeur 8 (inchangée) est listé comme ignoré
  (`Libretro3dsIgnoreReason.tooDeep`, `system3dsIgnoredTooDeep`) ; le nom du dossier
  choisi entre dans les règles de chemin (choisir `title` est reconnu).
- m8 : noms ZIP normalisés (`\` → `/`, `./` en tête retiré) avant les contrôles de
  traversée, toujours refusés pour `..`, chemin absolu, lettre de lecteur, NUL ; méthode
  de compression lue dans le répertoire central **et** l'en-tête local (archive 4.0.9
  décode une méthode inconnue comme « stockée ») : autre que 0/8 → `unsupportedCompression`
  ; tailles exactes vérifiées des données de console : `SecureInfo_A` 0x111,
  `LocalFriendCodeSeed_B` 0x110, `otp.bin` 0x100 (sa signature 0xDEADB00F n'existe qu'une
  fois déchiffré : non exigée), `movable.sed` 0x120 ou 0x140 avec `SEED` à 0 ; titres NAND
  limités par la règle du cœur `GetTitleMediaType` (plateforme ≠ 0x0004, ou catégorie avec
  le bit système 0x0010 ou téléchargement 0x0001, ou variation avec le bit système 0x02) :
  applications 00040000, démos 00040002, mises à jour 0004000e, DLC 0004008c → `sdTitle` ;
  une image NAND brute dans un ZIP est signalée comme telle (hors limites de taille) ; un
  `config` nu n'est reconnu que choisi comme fichier isolé.
- **Clés (constat supplémentaire, hors liste de la revue)** : le cœur lit
  `sysdata/keys.txt` (`KEYS_FILE`), et un fichier présent **remplace** le blob intégré
  (`GetKeysStream`) ; `LoadPresetKeys` ne lit les clés AES que sous une ligne `:AES`
  (découpage sur `\n` seul, `#` en tête = commentaire). Un `aes_keys.txt` de Citra, sans
  section, n'apporterait aucune clé tout en masquant les intégrées : refus `keysFormat`
  (`system3dsRejectedKeysFormat`) quand le cœur n'y lirait aucune clé `slot0x<hex>Key<X|Y|N>`
  (emplacement < 0x40, 32 chiffres hex) ; une marque d'ordre d'octets est acceptée tant
  qu'elle ne précède pas l'en-tête (m8), des fins de ligne CRLF sont refusées (`:AES\r` n'est
  pas une en-tête pour le cœur). Le fichier installé n'est jamais modifié.
- m9 : tous les fichiers reconnus sont hachés à l'analyse (voir plus haut) ; l'élément
  identique (`skipIdentical`) n'est toujours pas revérifié à l'installation.
- m11 (décision du lead) : la sauvegarde CFG `config` (identifiant de console, nom,
  anniversaire) est une donnée de console : exclue par défaut, installée seulement avec
  la case « données de console » ; listée avec elles dans l'inventaire (la ligne `config`
  disparaît, contrat remplacé dans les tests de la page) et dans le plan.

**Page (m5, m6, m12, m13, point 10).** Confirmation de restauration dédiée
`system3dsRestoreConfirm` ({date} de la sauvegarde, fichiers ajoutés non supprimés) et
date sous les boutons (`system3dsLastBackup`) ; dates brutes `aaaa-mm-jj hh:mm` à l'heure
du téléphone (`Libretro3dsSystemScreen.backupDate`, non traduites). Échec de la sonde de
session : texte `system3dsSessionUnknown` + code technique brut à part (le service garde
`sessionActive` avec `sessionUnknown: true`, le magasin son `technicalDetail`) ; statuts
`system3dsRolledBack` et `system3dsNotAttempted` ; clés et données de console listées dans
un groupe « laissés de côté » (`system3dsPlanExcluded`) tant que leur case n'est pas cochée.
Note de reprise en tête de page (`system3dsRecoveredUndone`, `…Finished`, `…Partial`,
`system3dsRecoveryFailed`, chemins et codes bruts) et dans le résultat ; fichiers manquants
après un échec (`system3dsMissingFiles`) ; anciens fichiers d'un titre remplacé
(`system3dsRetired`). Le signet du dossier choisi (`libretro-3ds-import`) est effacé dès
que le passage se termine ou est annulé (`releaseFolder` injectable). Tailles par
`Rpcs3SaveExchangeService.formatBytes` ; phrases à paramètres par le catalogue
(`system3dsConfirm` reçoit `{count}`, `system3dsPresentSize`, `system3dsPresentFiles`) ;
l'échec d'action est une phrase traduite puis le code technique sur sa propre ligne.
Point 10 : une région ou un modèle absents s'affichent « valeur propre au cœur »
(`setting3dsCoreDefault`) et aucune valeur n'est cochée dans le choix : **la page n'affirme
plus de défaut**. Les textes des dialogues de choix et de source sont résolus avant
l'ouverture (le dialogue peut survivre au contexte de la page).

**Menu en jeu (point 9).** `LibretroCuratedSetting.inGameMenu` (vrai par défaut) ;
`citra_is_new_3ds` à `false` : `LibretroLocale.coreSettings` ne l'envoie plus au menu en jeu,
dont le pied de page promet « après redémarrage » alors que le modèle exige une nouvelle
session ; la page Émulateurs le garde avec `system3dsRestartHint`. Contrats remplacés
(commentés) : `test/libretro_locale_test.dart`, `test/libretro_core_catalog_test.dart` et
`test/libretro_3ds_launch_default_test.dart` (requête de lancement : région et langue
seulement) — ce dernier fichier est hors de la liste de fichiers confiée, modifié parce que
le point 9 change exactement ce qu'il vérifie.

**Preuve des options (point 10).** `test/libretro_core_options_test.py --cores` prouve que
chaque chaîne de clé et de valeur existe dans le binaire épinglé, **ni** qu'une valeur
appartient à une clé donnée, **ni** quelle valeur est le défaut. Le § 1 (« défaut effectif »
d'une option, blob de clés intégré « ON par défaut ») n'est donc pas prouvé pour le binaire
livré ; les textes `system3dsKeysOptional` et `system3dsIncludeKeysHelp` (m7) sont reformulés
sans affirmer de clés intégrées.

**Traductions (douze langues, mêmes paramètres).** Nouvelles clés : `setting3dsCoreDefault`,
`system3dsSessionUnknown`, `system3dsRolledBack`, `system3dsNotAttempted`,
`system3dsPlanExcluded`, `system3dsRestoreConfirm` ({date}), `system3dsLastBackup` ({date}),
`system3dsPresentSize` ({size}), `system3dsPresentFiles` ({count}),
`system3dsRejectedSdTitle`, `system3dsRejectedIncompleteTitle`,
`system3dsRejectedCompression`, `system3dsRejectedKeysFormat`, `system3dsIgnoredTooDeep`
({depth}), `system3dsRetired`, `system3dsBackupDamaged`, `system3dsRecoveredUndone`,
`system3dsRecoveredFinished`, `system3dsRecoveredPartial`, `system3dsRecoveryFailed`,
`system3dsMissingFiles`. Modifiées : `system3dsConfirm` (+ `{count}`),
`system3dsKeysOptional`, `system3dsIncludeKeysHelp` (m7), `system3dsIncludeConsoleDataHelp`
(m11).

**Tests.** `test/libretro_3ds_system_data_service_test.dart` : fixtures au format réel
(`:AES`, NCCH, TMD, `SEED`), titres entiers ; nouveaux cas pour chaque point, dont une
installation **tuée** dans un isolate séparé (`Isolate.kill`, ni `catch` ni `finally`)
pendant les sauvegardes, pendant les installations et après `committed`, suivie de la
reprise ; preuve du `rename` par la date de modification conservée des originaux ; repli
`EXDEV` entre deux volumes (Linux). `test/libretro_3ds_system_screen_test.dart` : sauvegardes
créées par le service (une sauvegarde à la main n'est plus complète), statuts distincts,
sonde en échec, signet libéré, sauvegarde abîmée, reprise à l'ouverture. Ajustements de
contrats commentés dans les tests (comptes changés par les titres entiers, le CFG en données
de console, l'élagage `sdmc`) ; aucune assertion supprimée sans son remplacement.

## 7. Build 448 — sauvegarde essentielle GodMode9, fichiers inutiles, contenus chiffrés

Demande du mainteneur (12 octobre 2026) : importer le ZIP « BIOS 3DS » pour qu'il soit
réellement lu par le moteur intégré, ou rendre compatibles les fichiers du dossier NAND.
Faits vérifiés dans les sources (Azahar au commit épinglé a5c3d4f8 et sur `master` le
12 octobre 2026 ; GodMode9 `master`) — le binaire nightly livré peut être plus récent que
a5c3d4f8 :

- `NCCHContainer::LoadHeader`/`Load` renvoient `ErrorEncrypted` pour **tout** NCCH sans le
  bit `NoCrypto` (flags[7] 0x04, octet 0x18F), quelles que soient les clés : un jeu ou un
  titre système chiffré n'est jamais lu, un fichier de clés n'y change rien.
- `hw/aes/key.cpp` lit les clés dans `sysdata/keys.txt` (ou un blob intégré à la
  compilation) ; aucune lecture de `boot9.bin`, `boot11.bin`, `sector0x96.bin`.
- `FileSys::OTP::Load` accepte `otp.bin` déchiffré (magie `0xDEADB00F`) ou chiffré (déchiffré
  avec `otpKey`/`otpIV`), puis vérifie son SHA-256 ; un échec n'est pas bloquant.
- `essential.exefs` (`BuildEssentialBackup`, `arm9/source/utils/nandutil.c`) : en-tête ExeFS
  de 0x200 octets, dix entrées (nom, décalage après l'en-tête, taille), SHA-256 de l'entrée
  `i` à `0x200 − (i + 1) × 0x20` ; sections `nand_hdr` (0x200), `secinfo` (0x111),
  `movable` (0x140 ou 0x120), `frndseed` (0x110), `nand_cid` (0x10), `otp` (0x100),
  `hwcal0`/`hwcal1` (0x9D0) ; console verrouillée : `otp`, `hwcal0`, `hwcal1` listés mais
  non hachés, `otp` vide.

Changements (`lib/services/libretro_3ds_containers.dart`, service et page 3DS) :

- `essential.exefs` (fichier isolé, fichier de dossier ou entrée ZIP) est lu section par
  section : `secinfo` → `nand/rw/sys/SecureInfo_A`, `frndseed` →
  `nand/rw/sys/LocalFriendCodeSeed_B`, `movable` → `nand/private/movable.sed`, `otp` →
  `sysdata/otp.bin`, chacune vérifiée par le SHA-256 de l'en-tête puis par les contrôles des
  fichiers isolés (tailles, magie `SEED`), classée données de console (case à cocher), et
  copiée depuis sa place dans le fichier (tranche `sliceStart` + taille, staging vérifié par
  SHA-256 comme les autres éléments). Section au SHA-256 faux : refusée (`invalid`), les
  autres conservées. Section de console vide et non hachée (OTP d'une console verrouillée) :
  rien à installer. Fichier sans l'entrée `nand_hdr` de GodMode9 ou dont une section sort du
  fichier : refusé entier (`invalid`).
- Nouveau motif `Libretro3dsIgnoreReason.notNeeded` (groupe « Inutile pour le cœur 3DS, non
  copié ») : `boot9.bin`, `boot11.bin`, `sector0x96.bin`, `secret_sector.bin`, et les sections
  `nand_hdr`, `nand_cid`, `hwcal0`, `hwcal1`.
- Nouveau refus `Libretro3dsRejection.encryptedContent` : un `.app` de titre NAND dont le NCCH
  n'a pas le bit `NoCrypto` est refusé, et son titre entier avec lui (contrat des tests
  modifié et commenté : les fixtures NCCH portent désormais ce bit).
- Lancement d'un jeu 3DS (`LibretroInternalService.launch`, cœur `azahar`) : un `.3ds`/`.cci`
  (NCSD, partition 0) ou `.cxi`/`.app` (NCCH) sans `NoCrypto` est refusé avant la session avec
  `LIBRETRO_3DS_ENCRYPTED` → `error3dsEncrypted` (douze langues), l'en-tête lu en détail
  technique ; les autres formats (3DSX, ELF, Z3DS…) et les fichiers illisibles restent
  confiés au cœur.
- Textes corrigés (douze langues) : `system3dsKeysOptional` et `system3dsIncludeKeysHelp`
  ne disent plus d'importer des clés « si un jeu chiffré ne démarre pas » (faux : le cœur
  refuse tout NCCH chiffré) et n'affirment toujours pas de clés intégrées (m7) ;
  `system3dsRejectedRawNand` oriente vers `essential.exefs` ou les dossiers `nand`/`sysdata`
  d'un dossier utilisateur Citra, Lime3DS ou Azahar.

Limites : une image NAND brute (`*_sysnand_*.bin`, `nand.bin`) reste illisible — la
déchiffrer demanderait les clés propres à la console (OTP + boot9) et un lecteur FAT ; non
implémenté. Les titres système copiés du CTRNAND sans déchiffrement sont chiffrés, donc
refusés ; `shared_font.bin` reste non reconnu (le cœur ne le lit qu'en dernier recours,
après ses polices de remplacement). Aucune validation sur iPhone : tests Dart sur fixtures
synthétiques au format réel (`test/libretro_3ds_system_data_service_test.dart`, groupe
« GodMode9 essential backup… », `test/libretro_3ds_encrypted_launch_test.dart`,
`test/libretro_3ds_system_screen_test.dart`).

## 8. Build 449 — dossier encore dans iCloud Drive (12-13 octobre 2026)

Constat du mainteneur : « je ne peux toujours pas importer un dossier Nand-zip pour la 3DS ».
Défaut confirmé dans les sources, indépendamment du contenu exact de ses fichiers : un dossier
choisi dans iCloud Drive (emplacement par défaut des téléchargements de l'iPhone) contient, pour
chaque fichier qu'iOS n'a pas téléchargé, un marqueur caché `.<nom>.icloud` dont le contenu n'est
pas celui du fichier. `dart:io` ne voit que ces marqueurs : l'analyse les rangeait en « non
reconnu » et concluait « rien de reconnu », sans dire pourquoi (sonde du 12 octobre : quatre
marqueurs `config`, `.app`, `.tmd`, `seeddb.bin` → quatre « non reconnu »).

Correctif (`lib/services/libretro_3ds_system_data_service.dart`) : le parcours de dossier met de
côté ces marqueurs ; celui d'un fichier que l'import lirait (même reconnaissance par chemin
que les autres fichiers) devient un refus `Libretro3dsRejection.notDownloaded`, nommé par le
chemin du fichier qu'il remplace, le nom du marqueur en détail technique ; celui de tout autre
fichier n'est pas listé. Rien n'est jamais lu ni copié depuis un marqueur. Texte
`system3dsRejectedNotDownloaded` (douze langues) : le dossier est encore dans iCloud Drive ; dans
Fichiers, maintenir le doigt sur le dossier › « Télécharger maintenant », puis recommencer.
Test : `test/libretro_3ds_system_data_service_test.dart`, « iCloud Drive placeholders of system
files are said, never read ».

Non traité ici, faute d'élément sur les fichiers du mainteneur (constats de la sonde, à confirmer
sur ses fichiers) : un ZIP de plus de 2 000 entrées hors dossiers élagués est refusé en bloc
(`tooManyEntries`), même quand la plupart de ces entrées seraient ignorées (un dump CTRNAND
complet peut s'en approcher) ; une image NAND brute (`nand.bin`, `*_sysnand_*.bin`) reste
refusée (§ 7) ; les titres système d'une console réelle sont des NCCH chiffrés, refusés par le
cœur (§ 7). Aucune validation sur iPhone.

## 9. Build 451 — titres chiffrés par Azahar pour leur console (13 octobre 2026)

Le mainteneur a fourni le ZIP qui échoue (`nand.zip`, 203 201 036 octets, 1 246 entrées dont
459 `__MACOSX`), examiné en lecture seule sur son PC (rien copié ni versionné). C'est le dossier
`nand` d'un dossier utilisateur Azahar : 133 titres NAND, TMD lisibles. Les 4 titres DS passent.
Les 140 `.app` des 129 autres titres n'ont ni `NCCH` à 0x100 ni `Z3DS`/`AZCR` à 0 : chacun est
refusé (`no NCCH header at 0x100 (nor a Z3DS or AZCR container)`), et son titre avec lui. Le
fichier `otp.bin` n'y est pas : Azahar le range dans `sysdata`, à côté de `nand`.

**Démontré sur le fichier.** Tout NCCH porte en clair quatre champs connus :
- `NCCH` à 0x100 ;
- sa taille en unités de 0x200 à 0x104 ;
- l'identifiant de programme, qui est celui du titre, à 0x118 ;
- des zéros de 0x120 à 0x12F.

Combinés par XOR avec les octets stockés, ces champs donnent un **seul** flux de clé pour les
140 contenus, dont deux champs varient d'un fichier à l'autre (taille, titre). L'entropie mesurée
est de 7,998 bits par octet.

**Sources amont** (azahar `a5c3d4f8`) :
- `NCCHContainer::AutoOpenNCCHNCSD` appelle d'abord `HW::UniqueData::IsUniqueCryptoFile`, puis
  `FileUtil::CryptoIOFile::IsCryptoIOFile` (`src/common/file_derived.cpp`). Deux formes sont
  acceptées : l'en-tête `AZCR` (version 0, SHA-256 de la clé et du nonce), ou le « Legacy mode »
  (« To be removed in a few years »). Dans ce dernier, tout le fichier est en AES-CTR, sans
  en-tête ; il est lu si le déchiffrement donne `NCCH`/`NCSD` à 0x100 ou `Z3DS` à 0.
- La clé et le compteur viennent de `GetUniqueCryptoFileKeyIV` (`src/core/hw/unique_data.cpp`).
  C'est le SHA-256 de la clé publique ECC du certificat CT (construit depuis l'OTP), de
  l'identifiant d'appareil et de l'identifiant 0 : 16 octets de clé, 12 de nonce, identiques
  pour tous les fichiers d'une console.
- `LoadOTP` exige `sysdata/otp.bin` et les clés OTP (`GetOTPKeyIV`). Le blob intégré
  `ENABLE_BUILTIN_KEYBLOB` est ON par défaut et n'est pas désactivé par la recette iOS d'Azahar
  (`.github/workflows/libretro.yml`) ; la recette du buildbot n'a pas été lue.
- Ensuite `LoadHeader` exige NoCrypto, comme pour tout NCCH.
- `archive_ncch.cpp` remplace un titre qu'il ne peut pas ouvrir par ses polices, données Mii,
  liste de pays et mots interdits de substitution : un titre illisible équivaut à un titre
  absent.

**Défaut NeoStation.** L'import ne reconnaissait que la forme `AZCR`. Il refusait la forme
« Legacy », que le cœur lit pourtant avec l'OTP de la console.

**Correctif** (`lib/services/libretro_3ds_system_data_service.dart`) :
- `consoleCryptoFingerprint` calcule le SHA-256 des 32 octets de flux trouvés sur ces champs.
  Aucune clé n'est nécessaire ; aucun octet de flux n'est conservé ni journalisé.
- Un `.app` sans en-tête lisible, d'un titre non DS, d'une taille multiple de 0x200, n'est
  conservé que si un contenu d'un autre titre ou d'une autre taille confirme son empreinte, et si
  l'import ne contient qu'une seule empreinte confirmée. Sinon il est refusé `invalid` (détail
  `not confirmed as encrypted by Azahar for one console…`) et son titre est `incompleteTitle`.
  Des contenus chiffrés titre par titre (un téléchargement jamais déchiffré) ne partagent aucun
  flux : ils restent refusés.
- Tous les fichiers d'un tel titre portent `consoleEncrypted`. Le titre n'est installé que si
  `sysdata/otp.bin` (0x100 octets) est déjà en place, ou s'il est importé dans le même passage
  avec la case des données de console (`Libretro3dsImportPlan.consoleOtpReady`, vérifié de nouveau
  à l'installation). Sinon il est laissé de côté (`excluded`). Le texte `system3dsConsoleEncrypted`
  (douze langues) s'affiche une fois par groupe du plan et une fois dans le résultat.
- Un gros fichier n'a pas d'empreinte SHA-256 à l'analyse : sa copie préparée doit alors redonner
  la même empreinte de clé.
- Les octets installés sont ceux du ZIP : le cœur déchiffre en lisant.

**Règle de la Build 448 maintenue.** Un NCCH chiffré (sans NoCrypto) reste refusé, et aucun texte
ne présente un fichier de clés comme remède. `otp.bin` est une donnée de console (case existante) ;
il est nommé parce que le cœur en dérive réellement la clé de ces titres.

**Ce que donnera le ZIP du mainteneur :**
- seul : les 4 titres DS, et les données de console si la case est cochée ; les 129 titres sont
  laissés de côté, avec l'explication ;
- avec `sysdata/otp.bin` du même dossier Azahar et la case cochée : les 133 titres.

**Limites, non vérifié :**
- L'import ne peut pas vérifier que `otp.bin` vient de la console qui a chiffré les titres : la
  dérivation demande les clés OTP du cœur. Un autre `otp.bin` rend ces titres illisibles, ce qui
  revient à des titres absents.
- La présence du blob de clés dans le binaire du buildbot n'est pas prouvée.
- Un contenu isolé (un seul titre importé de nouveau) n'est pas confirmable : il est refusé.
- Azahar annonce le retrait du « Legacy mode » : une mise à jour future du cœur pourrait ne plus
  lire ces fichiers.
- Les tickets (`dbs/ticket.db/*.tik`), les extdata partagées et les sauvegardes système autres que
  `config` restent non reconnus ; ils ne servent pas à charger les titres.
- Aucune validation sur iPhone.

**Tests :**
- `test/libretro_3ds_system_data_service_test.dart`, groupe « titles Azahar encrypted for their
  console (Build 451) » : reconnaissance et attente d'`otp.bin`, `otp.bin` dans le même import,
  refus (contenu isolé, deux copies d'un en-tête, chiffrement par titre, deux consoles, contenu
  déplacé dans un autre titre), empreinte, nouvelle vérification d'un gros fichier préparé ;
- `test/libretro_3ds_system_screen_test.dart` : deux tests de l'écran, texte et cases.
