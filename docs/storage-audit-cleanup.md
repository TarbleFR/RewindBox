# Analyse et nettoyage du stockage — conception et contrat (12 octobre 2026)

Chantier 5 de la grande mise à jour (`docs/grande-mise-a-jour-audit-2026-10-12.md`, § 7, verdict § 10,
décisions 26–32 du § 11). Candidate : l'IPA unique construite par-dessus la Build 446, numéro attribué à la
livraison. Tout en Dart (`dart:ffi` compris) : aucun fichier natif, aucun cœur, aucun plugin. Ce document fixe
les noms, signatures, chemins, clés et fichiers **avant** le code ; toute déviation y est reportée. Chaque chemin,
API et ligne cités ont été relus dans les sources de `Claude` (HEAD `5183c8d9`) ; là où elles contredisent
l'audit, les sources l'emportent (§ 2.2).

## 1. Décisions du mainteneur et cadre

- **Décisions 26–32** : légende A–I du § 7.1 confirmée (A jeux/ROM, B sauvegardes/états/NAND/cartes mémoire,
  C BIOS/firmware/licences/fichiers système/pairing-JIT, D caches régénérables, E médias et métadonnées scrapés,
  F temporaires, G journaux/diagnostics, H contenu utilisateur hors jeux, I NeoSwap) ; lignes orphelines de
  `user_screenscraper_metadata` supprimables **seulement** sur action explicite, prévisualisées, transactionnelles
  et journalisées ; `RPCS3/Cache` en niveau 2 avec avertissement ; `dart:ffi` dans un fichier Dart pour l'espace
  libre et la taille allouée, repli tailles logiques sur tout échec, aucun plugin natif ; export en agrégats par
  défaut, mode détaillé opt-in ; sous-chantier « maintenance légère » (§ 4) autorisé **après** l'outil de mesure ;
  10 journaux de session Dolphin conservés ; `Documents/Diagnostics` supprimable en niveau 3 seulement.
- **Fichiers verrouillés** (dix de la 419 : `config_service.dart`, `sqlite_service.dart`, `sqlite_database_service.dart`,
  `sqlite_config_provider.dart`, `sqlite_config_provider/scanning.dart`, `scraper_repository.dart`,
  `system_repository.dart`, `system_content.dart`, `ios_rom_library_root_resolver.dart`, plus `lib/main.dart` hors
  blocs `LIBRARY_RELOCATION_*`) : lus par leur seule API publique (`SqliteService.instance.database`,
  `ConfigService.getMediaPath()`, `ConfigService.linkedExternalFolderPath`, `SqliteConfigProvider.config.romFolders`,
  `FileProvider.stripRomExtension`). Aucune colonne ni migration SQLite (`_databaseVersion = 112`), aucune
  réparation automatique, aucun nettoyage au démarrage ni en arrière-plan : tout passe par un geste de
  l'utilisateur dans Réglages › Outils.
- **Jamais appelés** : `FilePicker.clearTemporaryFiles()` (vide toute `NSTemporaryDirectory()`,
  `IOSFilePickerHandler.swift:289-301`), `UserDataLocationService` (parcours `list(recursive: true)` suivant les
  liens), `SqliteService.resetDatabase()` (`sqlite_service.dart:2166`). Effets de démarrage de `main.dart` (thèmes
  retirés, iFly, `DiagnosticsDirectory.migrateLegacyRootFiles()`) : exceptions connues, hors périmètre.
- **Douze langues** par `lib/l10n/storage_locale.dart` (modèle `UiRefreshRateLocale`), test de parité, inscription
  dans `test/localization_12_locale_coverage_test.py` ; jamais de repli anglais affiché. **Gate** : bloc
  `BUILD447_STORAGE_DELTA` dans `build-utils/verify_delivery_reuse.py` ; `pubspec.yaml`/`pubspec.lock` sans diff
  (donc `dart:ffi` seul, sans `package:ffi`, § 3.3) ; tests ajoutés explicitement aux lanes (§ 5).
- **Jamais** : aucun bouton, lien, chemin, aide, message ni export qui nomme `Library/Sources` (agrégé sous
  « Bibliothèque »). Aucune annonce de validation iPhone ; la cause de l'écart « 40 Go pour 20 Go de jeux » reste
  une hypothèse à mesurer (§ 7).

## 2. Inventaire des racines (INV-01 … INV-29)

Chemins relatifs au conteneur (`Documents/`, `Library/Application Support/` noté `Support/`, `Library/Caches/`
noté `Caches/`, `tmp/`). Classes : **jamais** · **régénérable à coût** · **temporaire si inactif** ·
**confirmation**. Un chemin sans règle = « non identifié », jamais.

| INV | Chemin | Source | Cat. | Classe |
| --- | --- | --- | --- | --- |
| 01 | `Documents/roms/<console>/`, dossiers de bibliothèque enregistrés, dossier lié externe | `config_service.dart:225-238` (crée, verrouillé), `linkedExternalFolderPath` | A | jamais |
| 02 | `Documents/user-data/{config.json, data.sqlite, -wal, -shm}` ; `app.log` (ouvert) ; `app.log.old` (rotation 5 Mio, `logger_service.dart:45`) ; `Support/NeoStation/Maintenance/data-<horodatage>.sqlite` (sauvegardes `VACUUM INTO`, § 3.6) | `config_service.dart:322-324, 452-461` | index ; G ; H | jamais ; `app.log.old` confirmation ; sauvegardes confirmation (3 conservées) |
| 03 | `Documents/user-data/temp/<système>/<archive>/` (extraction pour hachage, dossiers laissés) | `archive_service.dart:31-37, 159-168` ; `temp_rom.7z` seulement sur Android (`content://`) | F | temporaire si inactif |
| 04 | `Documents/user-data/{themes/, systems/*.json, media/systems/, background.<ext>, menu_music/}` ; `background.importing<ext>` | `neo_assets_service.dart:443`, `systems_update_service.dart:69`, `home_music_service.dart:32,175`, `theme_provider.dart:207,362` | H / D / H ; F | jamais ; `background.importing*` temporaire si inactif |
| 05 | `Documents/media/<système>/<type>/<nom>.<ext>` (types `screenshots, fanarts, wheels, box2d, videos, manuals` ; extensions `png, jpg, jpeg, webp, mp4, pdf`) | `config_service.dart:408-410` (pur sur iOS), `game_repository.dart:147-155` | E | régénérable à coût (quota ScreenScraper) ; orphelins niveau 2 |
| 06 | `Documents/Diagnostics/*` (`rpcs3_startup_debug.txt`, `rpcs3_sync_debug.txt`, `armsx2_internal_debug.txt`, `stikjit_melonx_debug.txt`, `controller_battery.log`, `NeoSwap-v1.jsonl`, scraper, sync, `libretro-3ds-import-*.jsonl`, `storage-cleanup-*.jsonl`) | `diagnostics_directory.dart:10-20` (crée), `NeoSwapPlugin.mm:35` | G | confirmation (niveau 3 seulement) |
| 07 | `Documents/{NeoPlay.jsonl, NeoPlay.jsonl.previous, armsx2_jit_debug.log, RPCS3-core-load-stderr.log}` (écrits par le natif) | `NPDiagnostics.swift:10`, `Armsx2JitBridgePlugin.mm:24`, `Rpcs3EarlyLoaderDiagnostics.h:16` | G | confirmation (niveau 3) |
| 08 | `Documents/Recordings/Dolphin/*.mp4` | `DolphinRecordingController.mm:411` | H | confirmation |
| 09 | `Documents/Dolphin/{Wii, GameCube/USA, GameCube/EUR, GameCube/JAP}` (échange de fichiers système) | `dolphin_internal_v2_service.dart:402-417` (crée) | C | jamais |
| 10 | `Documents/RPCS3/{Import/Game Saves, Import/Savestates, Export/Game Saves, Export/Savestates, README.txt}` ; `Export/Game Saves/.<zip>.part` | `rpcs3_internal_service.dart:209-233` (crée, réécrit le README) ; `rpcs3_save_exchange_service.dart:416` | H ; F | exports `*.zip` confirmation ; `.part` temporaire si inactif ; Import jamais |
| 11 | `Documents/ARMSX2/{Games, BIOS, Saves/Memory Cards, Saves/Savestates}` (+ `cheats` si présent, non créé par Dart) | `armsx2_internal_service.dart:27-62` | A / C / B / B / H | jamais |
| 12 | `Documents/Ports/KartPad/{Games, Saves/NAND, Config, Mods, Metadata}` ; `Games/*.part` ; `Runtime/GameData` (extraction du RVZ) ; `Runtime/GameData.import-<uuid>`, `GameData.rollback-<uuid>` ; `Logs/` (écrits par le cœur) ; `Support/KartPad/{NAND, Config.toml, Logs, texture_replacements, GameData}` = **liens symboliques** vers ces dossiers | `kartpad_internal_service.dart:73-99, 194-212, 280-282, 347-368` ; `NeoKartPadDonorCore.mm:894-915, 1203-1205` | A/B/H ; F ; D ; F ; G | jamais ; temporaire si inactif ; régénérable à coût (niveau 3, re-préparé au lancement) ; temporaire si inactif ; journaux bornés § 4, anciens niveau 2 ; liens jamais (0 octet) |
| 13 | `Documents/Ports/Dusklight/{Games, Saves, Config, Mods, Metadata}` ; `Games/*.part` ; `tmp/Dusklight` | `dusklight_internal_service.dart:71-98, 157-164, 206-210` | A/B/H ; F | jamais ; temporaire si inactif |
| 14 | `Documents/Libretro/{System, Saves, States, Config, Config/Frontend, Cheats, Skins/<id>, SkinFavorites.json}` ; `Skins/.staging/*` (purgé > 1 h au prochain import) ; `Logs/{session.log, previous-session.log, unfinished-session.log, failed-launch.log}` (quatre fichiers, taille non bornée, `write(2)`) | `libretro_internal_service.dart:114-144` ; `libretro_skin_service.dart:293, 731-741` ; `LibretroSessionJournal.m:8-14` | C/B/B/H/H/H ; F ; G | jamais ; temporaire si inactif ; journaux confirmation (niveau 3, hors session) |
| 15 | `Documents/Library/{Books, Downloads}` ; `Books/.import-<hex>.part` ; `Documents/Library/Sources` (**jamais nommé**, agrégé sous « Bibliothèque ») | `library_local_library_service.dart:17-42, 922` ; `library_source_files.dart:130, 153-156` | H ; F ; — | jamais ; temporaire si inactif ; jamais |
| 16 | `Support/NeoStation/RPCS3/Data/` : `dev_hdd0/game/*`, `games/*` (+ alias `extractedgames`/`discimages`/`discimgs`) A ; `dev_hdd0/home/00000001/savedata` B ; `dev_hdd0/home/00000001/exdata/*.rap`, `dev_flash` C ; états B ; `dev_hdd0/tmp` F (vidé par le Core, `empty_hdd0_tmp = true`) ; `games.yml`, `vfs.yml`, `Icons` jamais ; `dev_hdd0/home/00000001/.neostation-save-import-<ts>` F | `rpcs3_internal_service.dart:159-178` (crée) ; `rpcs3_game_deletion.dart:22-30` ; `rpcs3_save_exchange_service.dart:213, 349-359` ; `rpcs3_rap_licence_service.dart:195-196` | A/B/C/F | jamais ; `dev_hdd0/tmp` et staging temporaire si inactif |
| 17 | `Support/NeoStation/RPCS3/Data/{dev_hdd1, dev_usb000, dev_bdvd, …}` (racines VFS amont, hors inventaire initial ; `dev_hdd1` = disque cache PS3 écrit par les jeux) ; redirection par `Data/vfs.yml` | `rpcs3_rap_licence_service.dart:525-549` (`storageRedirection`, lecture seule) ; chemins déduits de l'amont | D / A | `dev_hdd1` confirmation (niveau 3, avertissement) ; autres jamais ; **toute** racine RPCS3 exclue de la suppression si `storageRedirection` ≠ null |
| 18 | `Support/NeoStation/RPCS3/Cache/` (objets LLVM PPU/SPU/RSX ; disposition par titre non vérifiée ; borné à 4 Gio par le Core sur iOS, `embedded-core.patch:13489-13491`, routine non vérifiée sur l'appareil ; jamais purgé par NeoStation) | `rpcs3_internal_service.dart:173-178, 393-428` | D | régénérable à coût élevé (niveau 2, avertissement recompilation/JITPROF) |
| 19 | `Support/NeoStation/RPCS3/{Imports/PS3UPDAT-<µs>.PUP, SaveBackups/<DIR>-<stamp>, RapBackups/}` | `rpcs3_internal_service.dart:598-610` ; `rpcs3_save_exchange_service.dart:305, 1593-1603` ; `rpcs3_rap_licence_service.dart:507` | F ; H | `*.PUP` temporaire si inactif ; sauvegardes confirmation |
| 20 | `Support/NeoStation/Dolphin/Library/{gc, wii}` (bibliothèque cachée, copies hors Fichiers) | `dolphin_internal_v2_service.dart:160-175, 196-198` | A | jamais (doublons listés niveau 3, copie non référencée seulement) |
| 21 | `Support/NeoStation/Dolphin/{User/Config, User/GC/{USA,EUR,JAP}, User/Wii, User/StateSaves, User/Load/Textures, User/Dump, Saves, Metadata/IPL}` ; `ShaderCache` (`GameSettings` non créé par NeoStation, compté si présent) | `dolphin_internal_v2_service.dart:196-215` | C/B/H ; D | jamais ; `ShaderCache` régénérable à coût |
| 22 | `Support/NeoStation/Dolphin/Logs/dolphin-<ISO>.jsonl` (un par lancement), `Logs/dolphin-persistent.jsonl` (sans borne) ; `CrashMarkers/active-session.json` (garde), `active-session.json.<ms>.recovered` | `dolphin_internal_v2_service.dart:956-975, 604-606, 796-800, 1018-1020` | G ; — ; G | sessions au-delà des 10 plus récentes niveau 2 ; persistant confirmation ; marqueur actif jamais ; `.recovered` niveau 2 |
| 23 | `Support/Library/{local-index.json, local-index.json.corrupt*, catalogs.json, source-health.json, reading-state.json}` ; `covers/<id>.png` | `library_local_library_service.dart:26-32, 177, 224` | index ; D | jamais ; couvertures orphelines (hors `local-index.json`) niveau 2 |
| 24 | `Support/StikJIT/{pairing.mobiledevicepairing, pairing.import.tmp, pairing.backup.tmp, images DDI}` | `pairing_file_service.dart:12-26, 67-68` (crée) ; `StikjitBridgePlugin.swift:98-108` | C | jamais (`.tmp` compris, par prudence) |
| 25 | `Caches/Libretro/{SkinCache/, Content/<contenu>/, SkinDownloads/, SkinInspection/, skin-catalog.json, skin-verdicts.json, bios-check-v1.json}` | `libretro_internal_service.dart:141-144` ; `LibretroSkinRenderer.m:50-52` ; `LibretroCoreHost.m:772` ; `libretro_skin_catalog_service.dart:126-127` ; `libretro_skin_catalogs.dart:171-173` ; `libretro_bios_check_service.dart:394` | D ; F | régénérable ; `Content/*` temporaire si inactif |
| 26 | `Caches/Library/{library_http/ (96 Mio LRU), library_images/ (256 Mio LRU, épinglés)}` | `library_http.dart:454, 495, 518-520` ; `library_image_cache.dart:86-87` | D | régénérable (par `LibraryHttp.instance.clearCache()` / `LibraryImageCache.instance.clear()`) |
| 27 | `Caches/NeoSwap-v1/`, `Caches/NeoSwapShaderStorage-v1/` (fichiers `unlink`és, non listables) | `NeoSwapPlugin.mm:176`, `NeoSwapStorageService.mm:420` | I | jamais |
| 28 | `tmp/` : copies du sélecteur, **deux par sélection** (copie système d'`asCopy: true` dans `tmp/<bundle-id>-Inbox/<nom>`, emplacement iOS documenté, hypothèse, puis copie du plugin `tmp/<nom>`, la première jamais supprimée) ; `tmp/KartPad`, `tmp/Dusklight` ; `NeoStation-Dolphin-FramePacing.json` ; `SoLoudLoader-Temp-Files/` ; copie de métadonnées du lecteur Musique ; helpers JIT ; shaders ARMSX2 | `IOSFilePickerHandler.swift:238-245, 315-327` ; `kartpad_internal_service.dart:171, 442` ; `dusklight_internal_service.dart:210` ; `DolphinFramePacing.mm:274` ; `sfx_service.dart:59-61` ; `music_player_service.dart:823` | F | temporaire si inactif (copies du sélecteur : niveau 1 après 10 min) |
| 29 | `Support/<nom>_<hash>.ttf` (google_fonts 8.1.0, `file_io_desktop_and_mobile.dart:52-61`) ; `Caches/<bundle-id>/` (NSURLCache de `NSURLSession.sharedSession`, shaders ARMSX2 `Armsx2InternalBridgePlugin.mm:786`) | pub-cache ; sources | D | régénérable (niveau 2 ; retéléchargés) |

Hors inventaire : aucun App Group ; conteneurs des `.appex` illisibles ; dossiers liés par signet hors conteneur
(RetroArch, bibliothèques externes) en lecture seule, jamais supprimés.

### 2.1 Primitives existantes réutilisées

`Rpcs3SaveExchangeService.formatBytes(int)` (unités décimales comme Fichiers, jamais traduit) ;
`LibraryHttp.instance.cacheSizeBytes()/clearCache()/trimCache()` ; `LibraryImageCache.instance.cacheSizeBytes()/clear({includePinned})` ;
`Rpcs3RapLicenceService.storageRedirection(dataRoot)` ; `Rpcs3InternalService.runSaveExchange(body)` comme garde
RPCS3 (§ 3.7) ; `LibretroInternalBridge.isSessionActive()` ; `GameLaunchManager().isActive` (getter d'instance du
singleton). `NeoAssetsService.clearThemeCache(themeFolder)` est par thème et n'est pas utilisé ici.

### 2.2 Corrections apportées à l'audit par les sources

- `Logs/session.log` libretro : **quatre** fichiers (`failed-launch.log` en plus des trois cités), taille non
  bornée confirmée (`LibretroSessionJournal.h:20-22`).
- `Documents/ARMSX2/cheats` non créé par `Armsx2InternalService.ensureLayout()` ; Dolphin `User/GameSettings` jamais
  créé par NeoStation (ni Dart ni pont) ; tous deux comptés s'ils existent. Omission : les marqueurs
  `CrashMarkers/active-session.json.<ms>.recovered` s'accumulent.
- `temp_rom.7z` : écrit seulement sur Android (`archive_service.dart:66-72`), jamais sur iOS.
- Variantes de nom des médias : `game_repository.dart:169-172` (quatre), types/extensions `:147-155`, pas `:166-170` ;
  schémas `user_roms` et `user_screenscraper_metadata` à `sqlite_service.dart:1796` et `:1872`.
- `GameLaunchManager.isActive` est un getter d'instance (`game_launch_manager.dart:90`) ; `Rpcs3InternalService`
  n'expose pas son drapeau de mutation (garde par `runSaveExchange`) ; Dolphin n'expose ni `_launchInProgress` ni
  `_systemImportBusy` (garde par le marqueur `CrashMarkers/active-session.json`).
- `LibraryDiskCache.sizeBytes()` n'est joignable que par `LibraryHttp.instance.cacheSizeBytes()`, et
  `LibraryHttp.instance` résout son dossier paresseusement : le scanner mesure les dossiers lui-même.
- Copies du sélecteur : le plugin copie l'URL rendue par `UIDocumentPickerViewController(asCopy: true)` dans
  `NSTemporaryDirectory()/<nom>` sans supprimer l'original (`IOSFilePickerHandler.swift:144, 203, 315-327`) ; le
  nom `<bundle-id>-Inbox` reste une hypothèse iOS à valider sur l'appareil.
- `dev_hdd1` et les racines VFS n'apparaissent dans aucun fichier du dépôt hors audit : classées par prudence (INV-17).
- `Rpcs3InternalService.rootDirectory()` crée aussi son dossier ; `Armsx2InternalService.ensureLayout()` écrit en
  plus `ConfigService.linkedArmsx2FolderPath` ; `DiagnosticsDirectory.directory()` et `PairingFileService.storedFile()`
  créent leur dossier.

## 3. Architecture (tout en Dart, lecture seule par défaut)

Dossier `lib/services/storage/` (nouveau). Aucune écriture hors : suppression planifiée (§ 3.8), journal sous
`Documents/Diagnostics`, sauvegarde `VACUUM INTO` sous `Support/NeoStation/Maintenance`, rapport temporaire sous `tmp/`.

### 3.1 `storage_roots.dart` — registre déclaratif sans effet de bord

```dart
enum StorageCategory { games, saves, systemFiles, caches, media, temporary, logs, userContent, neoSwap, indexFiles, unknown } // A…I + index/DB/config + non identifié ; `index` est réservé par Enum.index en Dart
enum StorageDeletionClass { never, regenerableAtCost, temporaryWhenIdle, confirmation }
enum StorageEngine { frontend, libretro, rpcs3, dolphin, kartpad, dusklight, armsx2, library, neoSwap, system }
enum StorageContainer { documents, applicationSupport, caches, temporary }
class StorageContainers { final String documents, applicationSupport, caches, temporary; static Future<StorageContainers> resolve(); } // seuls appels path_provider
class StorageRule { const StorageRule({required this.relative, required this.category, required this.deletionClass, this.engine, this.namePattern, this.orphanAnchor, this.minimumAge, this.labelKey}); }
class StorageRoot { const StorageRoot({required this.id, required this.container, required this.relative, required this.labelKey, required this.rules, this.engine, this.hidden = false}); } // id = 'INV-21'
class StorageRootRegistry {
  const StorageRootRegistry(this.containers, {this.mediaDirectory, this.libraryRoots = const [], this.linkedExternalFolder, this.rpcs3Redirected = false});
  static Future<StorageRootRegistry> resolve({Iterable<String> libraryRoots = const []});
  List<StorageRoot> get roots;               // les 29 racines, ordre de la table
  Set<String> get resolvedRootPaths;         // liste blanche (après resolveSymbolicLinks)
  StorageRule? ruleFor(String absolutePath); // règle la plus profonde, listes « jamais » d'abord
  bool isProtected(String absolutePath);
}
```

Résolution par `path.join` sur `getApplicationDocumentsDirectory()`, `getApplicationSupportDirectory()`,
`getApplicationCacheDirectory()`, `getTemporaryDirectory()`, puis les seuls accesseurs **sans création** :
`LibretroInternalService.{rootDirectory, systemDirectory, savesDirectory, statesDirectory, configDirectory, cheatsDirectory, skinsDirectory, logsDirectory, frontendDirectory, cacheDirectory}()`,
`DolphinInternalV2Service.{rootDirectory, libraryDirectory, scanRootPath}()`,
`KartPadInternalService.{rootDirectory, gamesDirectory, savesDirectory, configDirectory, modsDirectory, logsDirectory}()`,
`DusklightInternalService.{rootDirectory, gamesDirectory, savesDirectory, configDirectory, modsDirectory}()`,
`Armsx2InternalService.{rootDirectory, gamesDirectory, biosDirectory, savesDirectory}()`, `LibraryLocalRoots.platform()`,
`LibraryHttp.defaultCacheDirectory()`, `ConfigService.getMediaPath()` (branche iOS pure), `ConfigService.linkedExternalFolderPath`,
`Rpcs3SaveExchangeService.savedataPath()`, `Rpcs3RapLicenceService.{exdataPath, storageRedirection}()`.
**Jamais appelés** par le registre : `Rpcs3InternalService.{rootDirectory, dataDirectory, cacheDirectory, filesWorkspaceDirectory, synchronizeFilesWorkspace}()`,
`ConfigService.{getDefaultIOSRomsFolder, getUserDataPath}()`, tout `ensureLayout()`, `DolphinInternalV2Service.sharedSystemDirectory()`,
`DiagnosticsDirectory.{directory, file}()`, `PairingFileService.storedFile()`, `LibraryHttp.instance`. Racine absente = 0 octet.

### 3.2 `storage_scanner.dart`

```dart
enum StorageEntryKind { file, directory, link, icloudPlaceholder, inaccessible }
class StorageNode { final String path, relativePath; final StorageEntryKind kind; final int logicalBytes; final int? allocatedBytes; final int fileCount, linkCount, inaccessibleCount; final DateTime? modified; final StorageCategory category; final StorageDeletionClass deletionClass; final String? ruleId; final List<StorageNode> children; }
class StorageScanProgress { final int rootsDone, rootsTotal, entries, bytes; final String rootId; }
class StorageScanResult { final StorageContainers containers; final List<StorageNode> roots; final int logicalBytes; final int? allocatedBytes, freeBytes, volumeBytes; final bool statViaFfi; final List<String> inaccessible; final DateTime startedAt; final Duration duration; }
class StorageScanCancelToken { void cancel(); bool get isCancelled; }
class StorageScanner {
  StorageScanner({StorageStat? stat, int maxDepth = 24, int maxEntriesPerRoot = 500000});
  Future<StorageScanResult> scan(StorageRootRegistry registry, {StorageScanCancelToken? cancel, void Function(StorageScanProgress)? onProgress});
}
```

Un `Isolate.run` par racine (parcours itératif `Directory.list(recursive: false, followLinks: false)`, profondeur et
entrées bornées contre les boucles) ; progression et annulation observées entre racines et par un compteur
d'entrées remonté par `SendPort` ; liens comptés dans `linkCount` à 0 octet, jamais suivis ; `.<nom>.icloud` →
`icloudPlaceholder` à 0 octet (règle de `neostation_rom_library.dart:94`) ; `FileSystemException` → `inaccessible`
(chemin relatif consigné) ; taille logique `FileStat.size` (champs : `changed`, `modified`, `accessed`, `type`,
`mode`, `size` — `file_system_entity.dart:77-100`, ni inode ni blocs), taille allouée par § 3.3 quand disponible.

### 3.3 `storage_stat_ffi.dart` — `lstat`/`statvfs` par `dart:ffi`

```dart
abstract class StorageStat { bool get available; StorageStatInfo? lstat(String path); StorageVolumeInfo? statvfs(String path); }
class StorageStatInfo { final int size, blocks, nlink, ino, dev, mode; int get allocatedBytes => blocks * 512; bool get isLink => (mode & 0xF000) == 0xA000; }
class StorageVolumeInfo { final int freeBytes /* f_bavail * f_frsize */, totalBytes /* f_blocks * f_frsize */; }
class StorageStatFfi implements StorageStat { static StorageStatFfi? tryLoad(); } // DynamicLibrary.process() : 'lstat', 'statvfs', 'calloc', 'free'
class StorageStatLogical implements StorageStat { /* FileStat seulement, available = false */ }
```

Précédent : `packages/flutter_7zip/lib/flutter_7zip.dart:12-23` (`DynamicLibrary.open`) ; ici `DynamicLibrary.process()`
(libSystem déjà chargée), `dart:ffi` seul — `package:ffi` n'est pas une dépendance directe et `pubspec.yaml` ne change
pas : l'UTF-8 du chemin est copié dans un tampon `calloc` de la libc, libéré par `free`. **Dispositions arm64 Darwin,
hypothèses à valider sur l'appareil** : `struct stat` (`__DARWIN_STRUCT_STAT64`, 144 octets) : `st_dev` int32 @0,
`st_mode` uint16 @4, `st_nlink` uint16 @6, `st_ino` uint64 @8, `st_uid`/`st_gid` @16/@20, `st_rdev` @24, quatre
`timespec` @32…@95, `st_size` int64 @96, `st_blocks` int64 @104, `st_blksize` int32 @112 ; sur arm64 le symbole
`lstat` est déjà la variante inode 64 bits (`$INODE64` n'existe que sur x86_64 : simulateur Intel non couvert).
`struct statvfs` (64 octets) : `f_bsize` @0, `f_frsize` @8 (unsigned long), `f_blocks` @16, `f_bfree` @20,
`f_bavail` @24 (unsigned int). Auto-test au chargement : `lstat` du conteneur `Documents` comparé à `FileStat`
(taille, type) et `statvfs` avec `512 ≤ f_frsize ≤ 1 Mio`, `f_bavail ≤ f_blocks` ; tout écart, symbole manquant ou
exception → repli `StorageStatLogical` pour la session, signalé (`statViaFfi = false`, limite § 7). Le chiffre
« Disponible » des Réglages iOS (espace purgeable compris) n'est pas reproduit.

### 3.4 `storage_categorizer.dart`

`class StorageCategorizer { const StorageCategorizer(this.registry); StorageClassification classify(String absolutePath, StorageEntryKind kind); }`
avec `StorageClassification { category, deletionClass, ruleId, protectedReason }`. Ordre : (1) listes **jamais** :
racines et conteneurs eux-mêmes, `Documents`, `Documents/roms`, chaque dossier de bibliothèque, dossier lié externe,
`Documents/Library/Sources`, `Caches/NeoSwap*`, `dev_flash`, `exdata`, `savedata`, `games`, `dev_hdd0/game`,
`Libretro/System`, `ARMSX2/BIOS`, `StikJIT`, `*.sqlite*`, `config.json`, `local-index.json*`, `reading-state.json`,
`catalogs.json`, `source-health.json`, `games.yml`, `vfs.yml`, `SkinFavorites.json`, `CrashMarkers/active-session.json`,
liens, `.icloud`, tout chemin sans règle (`unknown`, « Autres données (non identifiées) ») ; (2) règle la plus
profonde du registre ; (3) surcharge de nom : `*.part` → temporaire si inactif.

### 3.5 `storage_orphan_detector.dart`

```dart
class StorageOrphanDetector { StorageOrphanDetector({required Future<DatabaseAdapter> Function() database, required StorageRootRegistry registry}); Future<StorageOrphanReport> detect(StorageScanResult scan, {bool hashDuplicates = false, StorageScanCancelToken? cancel}); }
class StorageOrphanReport { final List<StorageOrphanEntry> media, libraryCovers; final List<StorageOrphanMetadataKey> metadata; final List<StorageOrphanEntry> libretroSaves, libretroStates, dolphinStates, rpcs3Savedata, armsx2Savestates; /* listés, jamais supprimables */ final List<StorageDuplicateGroup> duplicates; }
class StorageOrphanMetadataKey { final String appSystemId, filename; }
```

- **Médias** : pour chaque fichier de `Documents/media/<système>/<type>/`, la base (nom sans dernière extension,
  `game_repository.dart:165-168`) est comparée aux **quatre** variantes de `deleteNeoStationScrapedMedia` (`:169-172`)
  de chaque ligne `user_roms` du système (`app_systems.folder_name`) : `_stripExtension(romBaseName)`,
  `_stripExtension(filename)`, `romBaseName`, `filename`, avec `romBaseName` recalculé par
  `FileProvider.stripRomExtension(filename, extensions du système)`. Non apparié → orphelin E (niveau 2) ; système
  absent de `app_systems` → « non attribué », jamais.
- **Métadonnées** : `SELECT m.app_system_id, m.filename FROM user_screenscraper_metadata m LEFT JOIN user_roms r ON
  r.app_system_id = m.app_system_id AND r.filename = m.filename WHERE r.filename IS NULL ORDER BY 1, 2`
  (`UNIQUE(app_system_id, filename)`, `sqlite_service.dart:1894`).
- **Sauvegardes/états** (B, information seulement) : libretro `Saves/<cœur>/…`, `States/…` par radical sans
  correspondance dans `user_roms.filename` ; états Dolphin `User/StateSaves` listés, non attribués ; `savedata/<DIR>`
  RPCS3 dont le `TITLE_ID` du `PARAM.SFO` (`Rpcs3LibraryService.parseParamSfoBytes`) n'est ni dans `dev_hdd0/game` ni
  dans `games` ; `ARMSX2/Saves/Savestates` par sérial sans jeu. `RPCS3/Cache` : un seul nœud, pas d'attribution.
- **Couvertures** : `Support/Library/covers/<id>.png` dont `<id>` n'est pas dans `local-index.json` (`books[].id`).
- **Doublons** : même nom de fichier et même taille (`neostation_rom_library.dart:110-114`) entre `Documents/roms`,
  dossiers enregistrés, `Dolphin/Library`, `Ports/*/Games`, `ARMSX2/Games` ; SHA-256 en isolate sur demande seulement ;
  une copie référencée par `user_roms.rom_path` est « référencée par la bibliothèque », jamais sélectionnable.
  **Jamais de suppression automatique.**

### 3.6 `lib/repositories/storage_maintenance_repository.dart`

```dart
class StorageMaintenanceRepository {
  StorageMaintenanceRepository({Future<DatabaseAdapter> Function()? database /* SqliteService.instance.database */, Future<String> Function()? backupDirectory, DateTime Function()? now, int keptBackups = 3});
  Future<List<StorageOrphanMetadataKey>> previewOrphanMetadata();                           // requête § 3.5
  Future<StorageMetadataDeletion> deleteOrphanMetadata(List<StorageOrphanMetadataKey> keys); // transaction
  Future<String> integrityCheck();                                                          // PRAGMA integrity_check
  Future<void> walCheckpoint();                                                             // PRAGMA wal_checkpoint(TRUNCATE)
  Future<String> backupBeforeDeletion();                                                    // VACUUM INTO
}
class StorageMetadataDeletion { final int deleted, skippedNotOrphan; final String backupPath; }
```

`deleteOrphanMetadata` : `DatabaseAdapter.transaction()` (`sqlite_service.dart:251`) ; chaque clé revérifiée par la même
jointure avant `DELETE FROM user_screenscraper_metadata WHERE app_system_id = ? AND filename = ?` ; une clé redevenue
référencée est ignorée (`skippedNotOrphan`) ; la transaction ne porte que les clés exactes prévisualisées. **Jamais de
`DELETE` sur `user_roms`**, aucune autre table. Sauvegarde : `VACUUM INTO ?` (hors transaction, paramètre lié) vers
`Support/NeoStation/Maintenance/data-<yyyyMMdd-HHmmss>.sqlite`, trois conservées, puis `wal_checkpoint`.
`package:sqlite3` 3.5.0 (`pubspec.lock`) se lie au SQLite du système iOS (`VACUUM INTO` depuis 3.27 ; version
consignée dans le journal).

### 3.7 `storage_cleanup_planner.dart`

```dart
enum StorageCleanupLevel { safe, regenerable, confirmed }
class StorageCleanupCandidate { final String path; final StorageEntryKind kind; final int logicalBytes; final int? allocatedBytes; final DateTime modified; final StorageCategory category; final StorageDeletionClass deletionClass; final String reasonKey; final List<String> warningKeys; final bool preselected; final String? pairedPath; final StorageEngine? engine; }
class StoragePlanRefusal { final String path; final StorageRefusalReason reason; }
class StorageCleanupPlan { final StorageCleanupLevel level; final DateTime builtAt; final List<StorageCleanupCandidate> candidates; final List<StorageOrphanMetadataKey> metadataKeys; final List<StoragePlanRefusal> refusals; int get bytes; }
class StorageSessionState { final bool launchActive, libretroActive, dolphinMarker, libretroUnfinishedJournal; }
class StorageSessionGuard { StorageSessionGuard({bool Function()? launchActive /* GameLaunchManager().isActive */, Future<bool> Function()? libretroActive /* LibretroInternalBridge.isSessionActive */, Future<bool> Function()? dolphinMarkerPresent, Future<bool> Function()? libretroJournalUnfinished}); Future<StorageSessionState> check(); }
class StorageCleanupPlanner { StorageCleanupPlanner({required StorageRootRegistry registry, required StorageSessionGuard guard, DateTime Function()? now}); Future<StorageCleanupPlan> plan(StorageScanResult scan, StorageOrphanReport orphans, StorageCleanupLevel level); }
```

- **Niveau 1 « Sûr »** (présélectionné) : copies du sélecteur dans `tmp/` et `tmp/*-Inbox/` (fichiers réguliers,
  âge ≥ 10 min) ; `tmp/SoLoudLoader-Temp-Files` ; `tmp/NeoStation-Dolphin-FramePacing.json` sans marqueur Dolphin ;
  `*.part` > 1 h hors moteur actif ; `user-data/temp/**` ; `Skins/.staging/*` > 1 h ; `background.importing*` ;
  `RPCS3/Imports/*.PUP` > 1 h ; `.neostation-save-import-*` ; `KartPad/Runtime/GameData.import-*`, `GameData.rollback-*` ;
  `Caches/Libretro/Content/*` et `dev_hdd0/tmp/*` hors session. Aucune ligne de base, aucune donnée de jeu.
- **Niveau 2 « Régénérable »** (présélectionné, avertissements) : niveau 1 + `Caches/Library/*` (par API),
  `Caches/Libretro/{SkinCache, SkinDownloads, SkinInspection, *.json}`, `Dolphin/ShaderCache`, `RPCS3/Cache`
  (`rpcs3CacheWarning`), médias orphelins (`mediaQuotaWarning`), lignes de métadonnées orphelines (aperçu § 3.6),
  couvertures orphelines, `Dolphin/Logs/dolphin-*.jsonl` et `KartPad/Logs/*` au-delà des 10 plus récents,
  `CrashMarkers/*.recovered`, `Support/*.ttf`, `Caches/<bundle-id>/`, `user-data/app.log.old`.
- **Niveau 3 « Avec confirmation détaillée »** (**jamais présélectionné**, case par case) : niveau 2 +
  `Documents/Diagnostics/*` (`diagnosticsWarning`), INV-07, `Recordings/Dolphin/*.mp4`, `Documents/RPCS3/Export/Game Saves/*.zip`,
  `RPCS3/{SaveBackups, RapBackups}/*`, `Maintenance/*.sqlite` hors la plus récente, `Libretro/Logs/*` hors session,
  `dolphin-persistent.jsonl`, `RPCS3/Data/dev_hdd1` (`hdd1Warning`), `KartPad/Runtime/GameData` (`kartpadGameDataWarning`),
  doublons (deux chemins affichés, copie non référencée seule sélectionnable, `duplicateWarning`).
- **Gardes de session** (planification et exécution) : `GameLaunchManager().isActive` → exécution refusée
  (`sessionActive`) ; `LibretroInternalBridge.isSessionActive()` vrai, ou `Logs/session.log` sans ligne `END ` dans
  ses 4 derniers Kio (`LibretroSessionJournal.m:14-22`) alors que la session est déclarée active → exclusion de
  INV-14, INV-25 ; marqueur `Dolphin/CrashMarkers/active-session.json` présent → exclusion de INV-20…22 et du
  FramePacing ; candidats RPCS3 (INV-16…19) exécutés dans `Rpcs3InternalService.runSaveExchange(body)` (refus
  `gameRunning`/`libraryBusy`, état d'émulation 0/1 seulement, `rpcs3_internal_service.dart:268-292`) ;
  `storageRedirection != null` → INV-16…19 refusés ; KartPad/Dusklight/ARMSX2 n'existent qu'en session (`isActive`).

### 3.8 `storage_deletion_manager.dart`

```dart
enum StorageRefusalReason { sessionActive, notInPlan, outsideWhitelist, isRoot, isProtected, isLink, changedSincePreview, accessDenied, notEmpty, cacheApiFailed, rpcs3Busy, redirected, unknown }
class StorageDeletionResult { final int deletedFiles, deletedBytes, skippedChanged, skippedMissing; final List<StoragePlanRefusal> refusals; final StorageMetadataDeletion? metadata; final String journalPath; final bool cancelled; }
class StorageDeletionManager {
  StorageDeletionManager({required StorageRootRegistry registry, required StorageSessionGuard guard, StorageStat? stat, Future<void> Function(String path)? deleteFile, Future<String> Function()? journalDirectory /* DiagnosticsDirectory.directory() */, DateTime Function()? now, int journalLimit = 20});
  Future<StorageDeletionResult> execute(StorageCleanupPlan plan, {required Set<String> selectedPaths, StorageMaintenanceRepository? maintenance, Future<void> Function()? clearLibraryCaches, void Function(StorageDeletionProgress)? onProgress, StorageScanCancelToken? cancel});
}
```

Pour chaque chemin sélectionné : (1) présent dans le plan ; (2) canonisation `resolveSymbolicLinks()` du parent +
`path.isWithin(racineRésolue, cheminRésolu)` pour une racine de `resolvedRootPaths` ; refus des racines elles-mêmes,
des conteneurs, de `Documents`, des dossiers de bibliothèque, du dossier lié, de `Library/Sources`, de
`Caches/NeoSwap*`, de `dev_flash`/`exdata`/`savedata`/`System`/`BIOS`/`StikJIT` ; (3) `lstat` (ffi) ou
`FileSystemEntity.isLink` → lien refusé ; (4) re-stat : taille ou `modified` différents de l'aperçu →
`changedSincePreview` ; (5) suppression **fichier par fichier** (`File.delete()`), dossiers vidés puis
`Directory.delete(recursive: false)` (sinon `notEmpty`) ; `OSError.errorCode == 2` (ENOENT) toléré → `skippedMissing` ;
13/1 (EACCES/EPERM) → refus avec le texte brut ; (6) garde de session revérifiée avant le début et tous les 50
fichiers ; annulation après le fichier en cours ; (7) INV-26 par `clearLibraryCaches` (API, jamais fichier par
fichier) ; (8) métadonnées après les fichiers : `backupBeforeDeletion()` puis `deleteOrphanMetadata()` ; (9) journal
`Documents/Diagnostics/storage-cleanup-<yyyyMMdd-HHmmss>.jsonl` (lignes `{t, op: begin|delete|skip|refuse|metadata|end,
path (relatif au conteneur), bytes, reason, errno, sqlite}`), au plus 20 fichiers `storage-cleanup-*.jsonl` (les plus
anciens retirés par le gestionnaire, ses propres fichiers seulement). Jamais `FilePicker.clearTemporaryFiles()`, jamais
`Directory.delete(recursive: true)` sur une racine.

### 3.9 `storage_report.dart`

```dart
class StorageReport {
  static Map<String, Object?> aggregate(StorageScanResult scan, {StorageOrphanReport? orphans, StorageDeletionResult? lastCleanup});
  static Map<String, Object?> detailed(StorageScanResult scan, {StorageOrphanReport? orphans, StorageDeletionResult? lastCleanup, int maxEntriesPerRoot = 200});
  static String text(Map<String, Object?> json, String Function(String key) t);
}
class StorageReportSharer { Future<void> share(String content, {required String fileName}); } // SharePlus.instance.share(ShareParams(files: [XFile('<tmp>/storage-report-<stamp>.json')])), share_plus 13.3.0
```

Agrégats (défaut) : par racine (`INV-xx`) et catégorie, octets logiques/alloués, compteurs, volume libre/total,
orphelins, doublons, temporaires, `statViaFfi` ; conteneurs remplacés par `<Documents>`, `<Support>`, `<Caches>`,
`<tmp>` ; **aucun nom de jeu, de livre ou d'utilisateur, aucun UUID de conteneur, jamais « Sources »** (INV-15
agrégé en `library`). Mode détaillé (préférence opt-in) : chemins relatifs des 200 plus grosses entrées par racine ;
`Documents/Library/Sources` reste agrégé.

### 3.10 Écrans, rangée Outils, préférences

- `lib/screens/storage/storage_audit_screen.dart` : `StorageAuditScreen({scanner, orphanDetector, registry, planner,
  deletionManager, maintenance, sharer})` injectables (modèle `LibretroBiosCheckerScreen({service, copyRetroArch})`) ;
  état `with LibretroPageNavigation<…>, WidgetsBindingObserver` ; `libretroPage(Scaffold(appBar: libretroPageAppBar(context, …)))` ;
  analyse à l'ouverture, au retour au premier plan (`AppLifecycleState.resumed`, sauf nettoyage en cours), bouton
  « Analyser à nouveau » ; erreur conservée avec son texte technique ; sections : Résumé (total logique, alloué si
  ffi, espace libre, explication de l'écart), Par catégorie (A–I + Autres), Par racine (nœuds dépliables,
  profondeur 2), Orphelins et doublons (compteurs, « Calculer les empreintes »), Nettoyage (trois niveaux → aperçu),
  Export (commutateur « mode détaillé », Partager), Limites (§ 7).
- `lib/screens/storage/storage_cleanup_preview_screen.dart` : `StorageCleanupPreviewScreen({required plan, required level, …})` ;
  liste par racine avec cases (niveaux 1–2 cochées, niveau 3 **décochées**), badges d'avertissement, totaux ;
  « Supprimer » → dialogue de confirmation reprenant les avertissements, le nombre et les octets
  (`pausePageNavigation()`/`resumePageNavigation()`) ; progression ; résultat (supprimés, ignorés modifiés, absents,
  refus avec raison brute, chemin du journal) ; retour → nouvelle analyse.
- `tools_settings_content.dart` : `_showStorageAudit => defaultTargetPlatform == TargetPlatform.iOS` (même porte que
  `_showBiosChecker`, `:59`) ; `getItemCount() => _showBiosChecker ? 5 : 3` ; `_rowKeys` généré à 5 ; `selectItem(4)`
  → `_openStorageAudit()` (`MaterialPageRoute`) ; cinquième `SettingsCardRow(key: _rowKeys[4], icon: Symbols.storage_rounded,
  title: StorageLocale.text(context, StorageLocale.toolTitle), subtitle: …toolSubtitle, subtitleMaxLines: 4,
  selected: … == 4, onTap: _openStorageAudit, trailing: Icon(Icons.chevron_right))` après le vérificateur de BIOS.
  `test/libretro_bios_checker_screen_test.dart:349-362` attend `getItemCount() == 4` : mis à jour explicitement à 5
  (contrat remplacé, documenté).
- SharedPreferences : `neostation_storage_detailed_export` (bool, défaut `false`), `neostation_storage_hash_duplicates`
  (bool, défaut `false`), `neostation_storage_last_level` (int 1..3, défaut 1), `neostation_storage_last_scan_at`
  (ISO 8601). Aucune colonne SQLite.

### 3.11 `lib/l10n/storage_locale.dart` (douze cartes, modèle `UiRefreshRateLocale`)

Clés (~70) avec le français du mainteneur : `toolTitle` « Analyse et nettoyage du stockage », `toolSubtitle` « Mesure
l'espace utilisé par NeoStation et ses moteurs, puis propose un nettoyage prévisualisé. », `title`, `scanning`
« Analyse en cours… », `scanAgain` « Analyser à nouveau », `scanFailed` (`{error}`), `cancel`, `summary`, `totalLogical`
(`{size}`), `totalAllocated` (`{size}`), `freeSpace` (`{free}`, `{total}`), `freeSpaceUnavailable`, `gapExplanation`
« L'écart avec les Réglages iOS vient des blocs APFS, du dossier temporaire purgé par iOS, de la mémoire NeoSwap
délinkée et des fichiers iCloud non téléchargés. », `byCategory`, `catGames`, `catSaves`, `catSystem`, `catCaches`,
`catMedia`, `catTemporary`, `catLogs`, `catUserContent`, `catNeoSwap`, `catIndex`, `catUnknown` « Autres données (non
identifiées) », `byRoot`, `rootLibrary` « Bibliothèque », `rootDocuments`, `rootSupport`, `rootCaches`, `rootTemporary`,
`entries` (`{count}`), `links` (`{count}`), `inaccessible` (`{count}`), `icloudPlaceholders` (`{count}`), `orphans`,
`orphanMedia` (`{count}`, `{size}`), `orphanMetadata` (`{count}`), `orphanCovers` (`{count}`), `orphanSavesInfo`
« Sauvegardes et états sans jeu associé : {count} (jamais supprimés) », `duplicates` (`{count}`, `{size}`),
`computeHashes` « Calculer les empreintes », `duplicateReferenced` « Référencé par la bibliothèque », `cleanup`,
`levelSafe` « Sûr », `levelSafeHelp`, `levelRegenerable` « Régénérable », `levelRegenerableHelp`, `levelConfirmed`
« Avec confirmation détaillée », `levelConfirmedHelp`, `preview`, `nothingToClean`, `selectedTotal` (`{count}`,
`{size}`), `deleteAction` « Supprimer », `confirmTitle`, `confirmBody` (`{count}`, `{size}`), `rpcs3CacheWarning`
« RPCS3 recompilera ses caches LLVM au prochain lancement (démarrage plus long). », `mediaQuotaWarning` « Les médias
retirés devront être rescrapés (quota ScreenScraper). », `diagnosticsWarning`, `hdd1Warning`, `kartpadGameDataWarning`,
`duplicateWarning`, `sessionActive` « Nettoyage refusé : un jeu ou un import est en cours. », `rpcs3Busy`, `deleting`
(`{done}`, `{total}`), `resultTitle`, `resultDeleted` (`{count}`, `{size}`), `resultSkippedChanged` (`{count}`),
`resultMissing` (`{count}`), `resultRefused` (`{count}`), `resultMetadata` (`{count}`), `journalSaved` (`{path}`),
`refuseLink`, `refuseProtected`, `refuseOutside`, `refuseAccess`, `refuseNotEmpty`, `refuseChanged`, `export`,
`exportDetailed` « Mode détaillé (chemins relatifs) », `exportDetailedHelp` « Par défaut, l'export ne contient que des
totaux. », `share`, `shareFailed`, `limitsTitle`, `limitFfi` « Tailles allouées et espace libre non disponibles sur cet
appareil : tailles logiques affichées. », `limitNeoSwap`, `limitExtensions`, `limitUnverified` « Chiffres non vérifiés
sur iPhone. », `technicalCode` (`{code}`). Tailles par `Rpcs3SaveExchangeService.formatBytes` ; chemins et codes bruts
jamais traduits.

## 4. Sous-chantier « maintenance légère » (après l'outil de mesure)

Nouveau `lib/services/storage/storage_picker_copies.dart` :

```dart
class StoragePickerCopies {
  @visibleForTesting static Future<Directory> Function() temporaryDirectory = getTemporaryDirectory;
  /// Supprime la copie du plugin [pickedPath] et la copie système de même nom et même taille sous `<tmp>/*-Inbox/`,
  /// seulement si chaque chemin résolu est sous `getTemporaryDirectory()` résolu, est un fichier régulier (pas un lien)
  /// et si [expectedLength] correspond (import vérifié). Ne lève jamais ; octets libérés en retour.
  static Future<int> discardAfterVerifiedImport(String pickedPath, {required int expectedLength});
}
class StorageLogRotation { static Future<int> keepNewest(Directory directory, {required Pattern name, required int keep}); static Future<void> rotateAtSize(File file, {int maxBytes = 5 * 1024 * 1024}); }
```

Points d'appel exacts, **après** la vérification de longueur existante et jamais au démarrage :
`libretro_internal_service.dart:404-409` (`importGames`, après `length == sourceLength`) ;
`dolphin_internal_v2_service.dart:263-266` (`importGames`, après `sourceLength == outputLength`) ;
`kartpad_internal_service.dart:212` (`importGame`, après `temporary.rename`) ; `dusklight_internal_service.dart:164`
(`importGames`, après `temporary.rename`) ; `armsx2_internal_service.dart:149-153` (`_copySelection`, jeux et BIOS) ;
`rpcs3_internal_service.dart:608` (`importFirmware`, après `_stageFirmware`) et `rpcs3_save_exchange_service.dart:863-869`
où `FilePicker.clearTemporaryFiles()` est **remplacé** par `StoragePickerCopies.discardAfterVerifiedImport(pickedPath)`
pour la source ZIP (décision 4 ter). `Rpcs3InternalService.importGames()` (`:684`) et les imports « open in place »
ne copient pas dans `tmp/` : inchangés. Journaux : `DolphinInternalV2Service._sessionLogPath()` (`:956-960`) appelle
`StorageLogRotation.keepNewest(Logs, name: RegExp(r'^dolphin-.*\.jsonl$'), keep: 10)` en excluant
`dolphin-persistent.jsonl`, lui-même borné à 5 Mio par `rotateAtSize` (`.old`, politique de `app.log`) ;
`KartPadInternalService.launch()` après la fin de session : `keepNewest(Logs, keep: 10)` sur `*.log`/`console.txt`
(jamais pendant la session, le cœur écrit). Tests § 6 J.

### 4.1 Déviations consignées à l'implémentation (12 octobre 2026)

- **Racine des copies du sélecteur.** Sur iOS, `getTemporaryDirectory()` de
  `path_provider_foundation` 2.6.0 renvoie `NSCachesDirectory`, c'est-à-dire
  `Library/Caches` (`path_provider_foundation_real.dart:40-42`), alors que le
  sélecteur copie dans `NSTemporaryDirectory()`, le vrai `tmp/`
  (`IOSFilePickerHandler.swift:316`). La racine par défaut de
  `StoragePickerCopies` est donc `<dirname(Documents)>/tmp` résolu ; un fichier
  sous `Library/Caches` est refusé (test). Même correction pour INV-28 : les
  chemins « `tmp/KartPad` », « `tmp/Dusklight` », `SoLoudLoader-Temp-Files` et la
  copie de métadonnées du lecteur Musique sont en réalité sous `Library/Caches`.
- **Plateforme.** Seul iOS copie chaque sélection : hors iOS, un chemin choisi est
  le fichier de l'utilisateur et rien n'est supprimé (`pickedPathsAreCopies`).
- **Boucles à plusieurs sélections** (libretro, Dolphin, Dusklight, ARMSX2) : la
  longueur vérifiée est notée après le contrôle et les copies sont retirées après
  la boucle (une feuille cue/m3u relit ses pistes dans `tmp/` ; deux sélections
  de même nom partagent une copie du sélecteur).
- **Import Dolphin du menu** : `DolphinSmartImportService.importGames`, le
  chemin réellement utilisé par l'interface, applique la même règle.
- **KartPad** : la rotation des journaux n'a lieu au lancement que si aucune
  session lancée auparavant ne peut encore tourner (la session reste détenue par
  le pont jusqu'à son événement de fin) ; le journal de cycle de vie du pont,
  `neostation-kartpad-lifecycle.log` à la racine KartPad, est borné à 5 Mio
  (`.old`) au même moment.
- **Dolphin** : la rotation a lieu quand le nouveau journal est nommé, avant sa
  création : dix journaux précédents plus le courant restent sur le disque.
- **RPCS3, sauvegardes** : l'archive ZIP est lue sur place ; sa copie est retirée
  dans le `finally` de l'import gardé (après validation, rejet, refus ou échec),
  avec la longueur lue à l'ouverture. **RPCS3, micrologiciel** : la longueur
  attendue est celle de la copie préparée par `_stageFirmware`.
- **Non traités** : une sélection « déjà présente » (jamais copiée ni vérifiée)
  garde sa copie ; `Rpcs3InternalService.importGames()` laisse les copies du
  sélecteur (lecture de l'ISO sur place non vérifiée) ; ces deux cas restent
  visibles dans l'analyse au niveau 1.

## 5. Phases, gate DELTA et lanes

| Phase | Contenu | Gate |
| --- | --- | --- |
| 5a | `storage_roots.dart`, `storage_stat_ffi.dart`, `storage_scanner.dart`, `storage_categorizer.dart` + tests | `flutter analyze`, tests A/E, baseline |
| 5b | `storage_orphan_detector.dart`, `storage_maintenance_repository.dart` + tests | tests A/B/D |
| 5c | `storage_cleanup_planner.dart`, `storage_deletion_manager.dart`, `storage_report.dart` + tests | tests B/C/D/E/F/G |
| 5d | écrans, rangée Outils, `storage_locale.dart`, couverture 12 langues | tests H/I, `localization_12_locale_coverage_test.py` |
| 5e | CI : lanes et `BUILD447_STORAGE_DELTA` | `verify_delivery_reuse.py --offline`, `delivery_pipeline_test.py`, `retroarch_baseline_scope_test.py` |
| 5f | maintenance légère (§ 4) | tests J, revalidation des tests d'import existants |

`BUILD447_STORAGE_DELTA` liste chaque fichier : `lib/services/storage/*.dart`, `lib/repositories/storage_maintenance_repository.dart`,
`lib/screens/storage/*.dart`, `lib/l10n/storage_locale.dart`, `lib/screens/settings_screen/new_settings_options/tools_settings_content.dart`,
les six services d'import et `rpcs3_save_exchange_service.dart` (5f), `test/storage_*`, `test/libretro_bios_checker_screen_test.dart`,
`test/localization_12_locale_coverage_test.py`, `build-utils/verify_delivery_reuse.py`, `.github/workflows/retroarch-delivery.yml`,
`.github/workflows/libretro-checks.yml`, `docs/storage-audit-cleanup.md`. Lane Dart de `retroarch-delivery.yml` (job
`checks`, étape « Validate changed library, callback, launch and restart behavior », après la ligne
`flutter test test/dolphin_shake_locale_test.dart …`) : une ligne `flutter test test/storage_roots_test.dart
test/storage_stat_ffi_test.dart test/storage_scanner_test.dart test/storage_categorizer_test.dart
test/storage_orphan_detector_test.dart test/storage_maintenance_repository_test.dart test/storage_cleanup_planner_test.dart
test/storage_deletion_manager_test.dart test/storage_report_test.dart test/storage_locale_test.dart
test/storage_audit_screen_test.dart test/storage_tools_row_test.dart test/storage_picker_copies_test.dart
test/storage_log_rotation_test.dart` (également dans `libretro-checks.yml:102`) ; lane Python, après
`python3 test/libretro_bios_requirements_test.py` : `python3 test/storage_contract_test.py`. Les trois `hashFiles`
identiques et la forme du job restent telles que `test/delivery_pipeline_test.py:77-82` les fige ; `storage_locale.dart`
ajouté à la liste fixe de `localization_12_locale_coverage_test.py:35-44`.

## 6. Tests (brief A–J → fichiers)

| Test | Fichiers | Vérifie |
| --- | --- | --- |
| A — détection des orphelins | `test/storage_orphan_detector_test.dart` (base en mémoire `DatabaseTestHelper`, arbre temporaire comme `game_deletion_regression_test.dart`) | médias : les quatre variantes, playlists multi-disques, système inconnu non attribué ; métadonnées : LEFT JOIN ; couvertures hors index ; sauvegardes listées seulement ; doublons nom + taille, copie référencée non sélectionnable |
| B — données protégées jamais supprimables | `test/storage_categorizer_test.dart`, `test/storage_cleanup_planner_test.dart` | chaque chemin des classes A/B/C/H/I/index et `Sources` classé `never` ; aucun plan (niveaux 1–3) ne contient ROM, ISO, jeux installés, sauvegardes, états, cartes mémoire, BIOS, firmware, NAND, licences, pairing, livres, skins, réglages, NeoSwap, inconnus |
| C — aperçu avant suppression | `test/storage_deletion_manager_test.dart`, `test/storage_audit_screen_test.dart` | rien n'est supprimé sans plan ni sélection ; niveau 3 décoché ; dialogue de confirmation avec avertissements |
| D — atomicité et retour arrière | `test/storage_maintenance_repository_test.dart` | transaction sur les clés exactes, clé redevenue référencée ignorée, échec simulé → aucune ligne retirée, `user_roms` intact, `VACUUM INTO` produit une base lisible, `integrity_check` « ok », trois sauvegardes conservées |
| E — validation des chemins | `test/storage_deletion_manager_test.dart`, `test/storage_scanner_test.dart`, `test/storage_stat_ffi_test.dart` | lien sortant refusé, racine refusée, hors liste blanche refusé, modifié depuis l'aperçu ignoré, ENOENT toléré, EACCES remonté brut, `followLinks: false`, `.icloud` à 0, inaccessibles comptés ; ffi : repli logique sur symbole absent, auto-test, tailles égales à `FileStat` sur Linux (CI) |
| F — garde de session | `test/storage_cleanup_planner_test.dart`, `test/storage_deletion_manager_test.dart` | `isActive` → refus ; marqueur Dolphin → exclusions ; `isSessionActive` et journal sans `END ` → exclusions ; `runSaveExchange` lève `gameRunning`/`libraryBusy` → refus RPCS3 ; revérification tous les 50 fichiers ; annulation |
| G — confidentialité du rapport | `test/storage_report_test.dart` | agrégats sans nom de fichier, sans UUID, sans « Sources » (même en mode détaillé), tailles et compteurs exacts, partage par fichier temporaire |
| H — i18n | `test/storage_locale_test.dart` (modèle `ui_refresh_rate_locale_test.dart`), `python3 test/localization_12_locale_coverage_test.py` | douze langues, parité des clés, placeholders, non-anglais, `zh_Hant` + script + TW/HK/MO, français du mainteneur, chaque clé utilisée par les écrans existe |
| I — interface | `test/storage_audit_screen_test.dart`, `test/storage_tools_row_test.dart`, `test/libretro_bios_checker_screen_test.dart` (adapté : 5 rangées) | analyse à l'ouverture/au retour/à la demande, erreur conservée, niveaux, aperçu, résultat, export ; cinquième rangée iOS (index 4, icône, clés), trois rangées ailleurs ; canaux simulés `plugins.flutter.io/path_provider`, `xyz.luan/gamepads`, `neostation/libretro_internal` |
| J — maintenance légère | `test/storage_picker_copies_test.dart`, `test/storage_log_rotation_test.dart`, `test/storage_contract_test.py` | suppression des deux copies seulement sous `tmp` résolu, refus hors `tmp`/liens/taille différente, import non vérifié → rien ; 10 journaux Dolphin conservés, `dolphin-persistent.jsonl` jamais retiré ; KartPad après session ; contrat de sources : plus aucun `FilePicker.clearTemporaryFiles()` dans `lib/`, aucun appel depuis `main.dart`, aucune chaîne `Library/Sources` dans `lib/screens/storage` ni `storage_locale.dart` |

## 7. Limites annoncées dans l'interface et non vérifié sans iPhone

Annoncé dans l'écran : tailles logiques (allouées seulement si l'auto-test ffi réussit), espace libre `f_bavail`
≠ « Disponible » des Réglages iOS ; fichiers NeoSwap délinkés et conteneurs des extensions non mesurables ; dossiers
liés hors conteneur non analysés ; disposition interne de `RPCS3/Cache` inconnue (un seul nœud) ; états Dolphin non
attribués ; orphelins du scanner verrouillé détectés après coup, jamais évités à la source ; aucune purge automatique
au démarrage ou en arrière-plan.

Non vérifié ici, jamais présenté comme acquis : tailles réelles sur l'iPhone ; **cause mesurée de l'écart
40 Go / 20 Go** (part des copies `tmp/`, de la bibliothèque Dolphin cachée, de l'extraction KartPad, de `RPCS3/Cache`
et de `dev_hdd1` : hypothèse jusqu'à la première analyse sur l'appareil) ; nom réel du dossier `*-Inbox` ;
dispositions `struct stat`/`statvfs` arm64 ; exécution de la routine de plafonnement 4 Gio du Core RPCS3 sur iOS ;
purge de `tmp/` par iOS ; version du SQLite système et `VACUUM INTO` ; comportement de `NSURLCache` ; durée d'analyse
sur un conteneur de 40 Go. Protocole iPhone : première analyse exportée en agrégats (sans nettoyage), comparaison avec
les Réglages iOS, puis niveau 1 seul et nouvelle analyse, et seulement ensuite niveau 2 avec capture du JITPROF RPCS3
avant/après.
