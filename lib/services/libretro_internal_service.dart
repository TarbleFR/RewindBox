import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/widgets.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../l10n/libretro_locale.dart';
import '../models/game_model.dart';
import '../models/system_model.dart';
import '../repositories/system_repository.dart';
import 'config_service.dart';
import 'libretro_3ds_containers.dart';
import 'libretro_3ds_language.dart';
import 'libretro_core_catalog.dart';
import 'libretro_resolution.dart';
import 'neostation_rom_library.dart';
import 'retro_achievements_session_service.dart';
import 'logger_service.dart';
import 'diagnostics_directory.dart';
import 'storage/storage_import_activity.dart';
import 'storage/storage_picker_copies.dart';

class LibretroLaunchOutcome {
  const LibretroLaunchOutcome({
    required this.success,
    this.errorCode,
    this.technicalDetails = '',
  });

  final bool success;
  final String? errorCode;
  final String technicalDetails;
}

/// Why a picked game was not imported.
enum LibretroRejectReason {
  /// The file type is not one this console opens.
  wrongType,

  /// The file could not be read (not downloaded from iCloud, access lost).
  unreadable,

  /// No space left on the device, or the copy is shorter than the original.
  noSpace,

  /// Any other copy error.
  copyFailed,
}

/// One picked file that was not imported, and why.
class LibretroRejectedFile {
  const LibretroRejectedFile(this.name, this.reason);

  final String name;
  final LibretroRejectReason reason;
}

/// A `.cue` / `.m3u` that was imported while some of the files it names
/// could not be copied next to it. An empty [files] means the sheet itself
/// could not be read.
class LibretroMissingTracks {
  const LibretroMissingTracks(this.name, this.files);

  final String name;
  final List<String> files;
}

class LibretroImportResult {
  const LibretroImportResult({
    required this.imported,
    required this.rejected,
    this.alreadyPresent = 0,
    this.importedPaths = const <String>[],
    this.systemFolder = '',
    this.createdLibraryRoot,
    this.rejectedFiles = const <LibretroRejectedFile>[],
    this.missingTracks = const <LibretroMissingTracks>[],
    this.acceptedExtensions = const <String>[],
    this.noImportableType = false,
  });

  /// Name and reason of each rejected file ([rejected] counts them).
  final List<LibretroRejectedFile> rejectedFiles;

  /// Imported cue sheets and playlists whose tracks are not all there.
  final List<LibretroMissingTracks> missingTracks;

  /// File types the console accepts (without the dot), sorted.
  final List<String> acceptedExtensions;

  /// The console has no file type that can be imported: nothing was asked.
  final bool noImportableType;

  final int imported;
  final int rejected;

  /// Picked games already in the chosen library (same name and size): not
  /// copied again.
  final int alreadyPresent;
  final List<String> importedPaths;

  /// System folder the games were copied into (`roms/<systemFolder>`), the
  /// system to rescan afterwards.
  final String systemFolder;

  /// NeoStation's own `roms` folder when it received the games because no
  /// library folder was registered: the caller registers it.
  final String? createdLibraryRoot;
}

/// A library folder imported games can go to: one of the user's registered
/// ROM folders, with the console's folder inside it.
class LibretroImportLibrary {
  const LibretroImportLibrary({required this.root, required this.directory});

  /// The registered folder.
  final String root;

  /// Where the games are copied: the console's folder of [root] (an alias
  /// folder such as "Nintendo 3DS" when the library has one), or [root]
  /// itself when it is a console folder.
  final String directory;

  String get name => path.basename(root);
}

class LibretroRetroArchCopy {
  const LibretroRetroArchCopy({
    required this.saves,
    required this.states,
    required this.system,
    this.emulator3dsFolder = false,
    this.alreadyPresent = 0,
    this.skipped = 0,
    this.skippedNames = const <String>[],
    this.foundFolders = 0,
    this.folderName = '',
  });

  /// Files already in RewindBox, kept as they are.
  final int alreadyPresent;

  /// Files not copied (over the size limit, unreadable, copy error).
  final int skipped;

  /// The first of the skipped files.
  final List<String> skippedNames;

  /// How many of `saves`, `states` and `system` the chosen folder holds.
  final int foundFolders;

  /// Name of the chosen folder.
  final String folderName;

  final int saves;
  final int states;
  final int system;

  /// The chosen folder is, or holds, the user folder of a Nintendo 3DS
  /// emulator (Azahar, Citra, Lime3DS: a `nand` or `sysdata` folder). Its
  /// system data is read by the 3DS import, not by this copy.
  final bool emulator3dsFolder;
  int get total => saves + states + system;
}

/// Embedded libretro engine: launches games of the systems listed in
/// [LibretroCoreCatalog] inside NeoStation, imports games into
/// NeoStation's own Files-visible `roms` folder and copies RetroArch saves
/// on request. Nothing is ever moved out of, or written into, RetroArch's
/// folders.
abstract final class LibretroInternalService {
  static final _log = LoggerService.instance;
  static const String _corePreferencePrefix = 'libretro_core_v1.';
  static const String retroArchChoice = 'retroarch';
  static const String _retroArchImportKey = 'libretro-retroarch-import';
  static const int _maxSystemFileBytes = 512 * 1024 * 1024;

  /// `library_name` the 3DS core declares (core_info fixture, `[HOST]
  /// loaded Azahar`): the native session names its option file after it,
  /// `Config/Azahar.json`.
  static const String _azaharLibraryName = 'Azahar';

  static bool handlesSystem(String folderName) =>
      Platform.isIOS && LibretroCoreCatalog.handles(folderName);

  /// Canonical catalog key of a system (see
  /// [LibretroCoreCatalog.canonicalSystem]): a system copy named after an
  /// alias folder during a scan still resolves to its bound system.
  static String systemKey(SystemModel system) => LibretroCoreCatalog.canonicalSystem(
        id: system.id,
        folders: system.folders,
        folderName: system.folderName,
      );

  /// [handlesSystem] for a system model, through [systemKey].
  static bool handlesSystemModel(SystemModel system) => handlesSystem(systemKey(system));

  static Future<Directory> rootDirectory() async {
    final documents = await getApplicationDocumentsDirectory();
    return Directory(path.join(documents.path, 'Libretro'));
  }

  static Future<Directory> _child(String name) async =>
      Directory(path.join((await rootDirectory()).path, name));

  static Future<Directory> systemDirectory() => _child('System');
  static Future<Directory> savesDirectory() => _child('Saves');
  static Future<Directory> statesDirectory() => _child('States');
  static Future<Directory> configDirectory() => _child('Config');
  static Future<Directory> cheatsDirectory() => _child('Cheats');

  /// One directory per imported skin (`Skins/<id>`).
  static Future<Directory> skinsDirectory() => _child('Skins');

  /// Journal of the last sessions, written by the native session as it goes
  /// (`session.log`, `previous-session.log`, `unfinished-session.log`), for
  /// diagnosing a launch failure or a session the process did not survive.
  static Future<Directory> logsDirectory({String? console}) =>
      DiagnosticsDirectory.directory(system: console ?? 'System', service: 'Libretro');

  /// Per-console frontend settings, written only by the native
  /// LibretroFrontendStore (`Config/Frontend/<console>.json`).
  static Future<Directory> frontendDirectory() async =>
      Directory(path.join((await configDirectory()).path, 'Frontend'));

  static Future<Directory> cacheDirectory() async {
    final caches = await getApplicationCacheDirectory();
    return Directory(path.join(caches.path, 'Libretro'));
  }

  static Future<void> ensureLayout() async {
    for (final directory in <Directory>[
      await rootDirectory(),
      await systemDirectory(),
      await savesDirectory(),
      await statesDirectory(),
      await configDirectory(),
      await frontendDirectory(),
      await cheatsDirectory(),
      await skinsDirectory(),
      await logsDirectory(),
      await cacheDirectory(),
    ]) {
      await directory.create(recursive: true);
    }
  }

  static String _preferenceKey(String systemFolder, String romName) =>
      '$_corePreferencePrefix${systemFolder.toLowerCase()}/$romName';

  /// Core chosen for one game: a core id, [retroArchChoice], or null for
  /// the system default.
  static Future<String?> coreChoiceFor(String systemFolder, String romName) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(_preferenceKey(systemFolder, romName));
  }

  static Future<void> setCoreChoice(String systemFolder, String romName, String? choice) async {
    final preferences = await SharedPreferences.getInstance();
    final key = _preferenceKey(systemFolder, romName);
    if (choice == null) {
      await preferences.remove(key);
    } else {
      await preferences.setString(key, choice);
    }
  }

  static Future<List<String>> _bundledCores() async {
    try {
      return await LibretroInternalBridge.availableCores();
    } catch (error) {
      _log.w('Embedded libretro cores unavailable: $error');
      return const <String>[];
    }
  }

  /// True when this game should run inside NeoStation: its system has an
  /// embedded core present in this build, the file is readable here, and
  /// the user did not switch the game to the RetroArch app.
  static Future<bool> shouldLaunchEmbedded(SystemModel system, GameModel game) async {
    final key = systemKey(system);
    if (!handlesSystem(key)) return false;
    final romPath = game.romPath;
    if (romPath == null || romPath.isEmpty || !await File(romPath).exists()) return false;
    final choice = await coreChoiceFor(key, game.romname);
    if (choice == retroArchChoice) return false;
    final coreId = _resolveCoreId(key, choice);
    return coreId != null && (await _bundledCores()).contains(coreId);
  }

  static String? _resolveCoreId(String systemFolder, String? choice) {
    final binding = LibretroCoreCatalog.bindingFor(systemFolder);
    if (binding == null) return null;
    final allowed = <String>[binding.coreId, ...binding.alternatives];
    return choice != null && allowed.contains(choice) ? choice : binding.coreId;
  }

  static Future<LibretroLaunchOutcome> launch({
    required SystemModel system,
    required GameModel game,
    required Locale locale,
  }) async {
    final key = systemKey(system);
    final binding = LibretroCoreCatalog.bindingFor(key);
    final console = LibretroCoreCatalog.consoleFor(key);
    final romPath = game.romPath;
    if (binding == null || console == null || romPath == null) {
      return const LibretroLaunchOutcome(success: false, errorCode: 'LIBRETRO_INVALID_REQUEST');
    }
    final choice = await coreChoiceFor(key, game.romname);
    final coreId = _resolveCoreId(key, choice)!;
    final core = LibretroCoreCatalog.cores[coreId]!;
    await ensureLayout();
    final biosDirectory = await systemDirectory();
    if (core.biosAnyOf.isNotEmpty) {
      var found = false;
      for (final name in core.biosAnyOf) {
        if (await File(path.join(biosDirectory.path, name)).exists()) {
          found = true;
          break;
        }
      }
      if (!found) {
        return LibretroLaunchOutcome(
          success: false,
          errorCode: 'LIBRETRO_BIOS_MISSING',
          technicalDetails: core.biosAnyOf.join(', '),
        );
      }
    }
    final missing = <String>[
      for (final name in core.biosAllOf)
        if (!await File(path.join(biosDirectory.path, name)).exists()) name,
    ];
    if (missing.isNotEmpty) {
      return LibretroLaunchOutcome(
        success: false,
        errorCode: 'LIBRETRO_BIOS_MISSING_ALL',
        technicalDetails: missing.join(', '),
      );
    }
    // The 3DS core refuses every encrypted NCCH whatever keys are
    // installed: say so before the session starts, with the header read.
    if (coreId == 'azahar') {
      final encrypted = await Libretro3dsNcch.encryptedGameDetail(romPath);
      if (encrypted != null) {
        _log.w('Embedded libretro launch refused: encrypted 3DS game ($encrypted) $romPath');
        return LibretroLaunchOutcome(
          success: false,
          errorCode: 'LIBRETRO_3DS_ENCRYPTED',
          technicalDetails: encrypted,
        );
      }
    }
    final raService = RetroAchievementsSessionService.shared;
    var raLaunch = await raService.prepareLaunch(engine: 'libretro', system: key,
      core: coreId, language: locale.toLanguageTag(), contentPath: romPath);
    final request = <String, Object?>{
      'coreId': coreId,
      'contentPath': path.normalize(romPath),
      'gameTitle': game.name,
      'console': console.id,
      'consoleName': console.name,
      'gameKey': '$key/${game.romname}',
      'systemDirectory': biosDirectory.path,
      'saveDirectory': (await savesDirectory()).path,
      'stateDirectory': (await statesDirectory()).path,
      'optionsDirectory': (await configDirectory()).path,
      'cheatsDirectory': (await cheatsDirectory()).path,
      'cacheDirectory': (await cacheDirectory()).path,
      'skinsDirectory': (await skinsDirectory()).path,
      'frontendDirectory': (await frontendDirectory()).path,
      'logsDirectory': (await logsDirectory(console: console.id)).path,
      'consoleGeometry': LibretroCoreCatalog.consoleGeometry(),
      'uiLocale': locale.toLanguageTag(),
      'retroLanguage': LibretroLocale.retroLanguage(locale),
      'uiText': LibretroLocale.nativeUI(locale),
      'optionDefaults': await _optionDefaultsFor(core, locale),
      'noJitOverrides': core.noJitOverrides,
      'lockedOptions': core.lockedOptions,
      'coreSettings': LibretroLocale.coreSettings(locale, core),
      // Internal resolution (Build 455): how the session recognizes the
      // core's resolution option among those it declares.
      'resolution': LibretroResolution.nativeRules(),
      'raSessionId': raLaunch['raSessionId'],
      'achievementsAllowed': raLaunch['enabled'] == true,
      'achievementsConsoleId': binding.achievementsConsoleId,
      'preferredHardwareContext': core.preferredHardwareContext,
    };
    try {
      var result = await LibretroInternalBridge.launch(request);
      if (result['success'] != true &&
          result['code'] == 'LIBRETRO_HARDWARE_RENDER_FAILED' &&
          coreId == 'mednafen_psx_hw' &&
          core.preferredHardwareContext == LibretroHardwareContext.vulkan) {
        // Beetle PSX HW asked for Vulkan and the device could not be made
        // (MoltenVK, GPU features): one new session on its software renderer,
        // which never replaces textures (the HD page says so).
        _log.w('Beetle PSX HW: Vulkan unavailable (${result['message'] ?? ''}); relaunching with the software renderer');
        await raService.finishLaunch(raLaunch);
        raLaunch = await raService.prepareLaunch(engine: 'libretro', system: key,
          core: coreId, language: locale.toLanguageTag(), contentPath: romPath);
        result = await LibretroInternalBridge.launch(<String, Object?>{
          ...request,
          'raSessionId': raLaunch['raSessionId'],
          'achievementsAllowed': raLaunch['enabled'] == true,
          'preferredHardwareContext': LibretroHardwareContext.none,
          'lockedOptions': <String, String>{...core.lockedOptions, 'beetle_psx_hw_renderer': 'software'},
        });
      }
      if (result['success'] == true) {
        _log.i(
          'Embedded libretro running core=$coreId '
          '(${result['libraryName']} ${result['libraryVersion']}, '
          'renderer=${result['hardwareRendering']}) game=$romPath',
        );
        return const LibretroLaunchOutcome(success: true);
      }
      final log = result['log'];
      await raService.finishLaunch(raLaunch);
      final details = <String>[
        'Core: $coreId',
        'Code: ${result['code'] ?? 'unknown'}',
        'Message: ${result['message'] ?? ''}',
        if (log is List && log.isNotEmpty) 'Log:\n${log.join('\n')}',
      ].join('\n');
      _log.e('Embedded libretro launch failed\n$details');
      return LibretroLaunchOutcome(
        success: false,
        errorCode: result['code']?.toString(),
        technicalDetails: details,
      );
    } catch (error) {
      await raService.finishLaunch(raLaunch);
      _log.e('Embedded libretro launch error: $error');
      return LibretroLaunchOutcome(success: false, technicalDetails: '$error');
    }
  }

  /// NeoStation's default layer of core options for this launch (applied
  /// by `LibretroCoreHost applyDefaults`, under any stored value and above
  /// the core's own default): the catalog defaults, plus for the 3DS core
  /// the system language matching the NeoStation language, only while
  /// `Config/Azahar.json` stores no `citra_language_value` — a choice made
  /// in the in-game menu or on the Nintendo 3DS page always wins. The
  /// other cores keep the catalog map as it is.
  static Future<Map<String, String>> _optionDefaultsFor(LibretroCore core, Locale locale) async {
    if (core.id != 'azahar') return core.optionDefaults;
    final stored = await _storedCoreOptions(_azaharLibraryName);
    if (stored.containsKey(Libretro3dsLanguage.optionKey)) return core.optionDefaults;
    return <String, String>{
      ...core.optionDefaults,
      Libretro3dsLanguage.optionKey: Libretro3dsLanguage.forAppLocale(locale),
    };
  }

  /// Options the native session stored for one core
  /// (`Config/<library>.json`, `{"values": {key: value}}`, read like
  /// LibretroCoreOptions does: non-string values ignored); empty when the
  /// file is absent or unreadable, which is also what the core would see.
  static Future<Map<String, String>> _storedCoreOptions(String libraryName) async {
    final file = File(path.join((await configDirectory()).path, '$libraryName.json'));
    try {
      if (!await file.exists()) return const <String, String>{};
      final json = jsonDecode(await file.readAsString());
      final values = json is Map ? json['values'] : null;
      if (values is! Map) return const <String, String>{};
      return <String, String>{
        for (final entry in values.entries)
          if (entry.value is String) entry.key.toString(): entry.value as String,
      };
    } catch (error) {
      _log.w('Core options ${file.path} unreadable: $error');
      return const <String, String>{};
    }
  }

  /// NeoStation's own Files-visible ROM folder, registered like any library
  /// folder so imported games appear in the usual playlists; one folder per
  /// system, named as the scanner knows it.
  static Future<Directory> importDirectoryFor(String systemFolder) async {
    final roms = await ConfigService.getDefaultIOSRomsFolder();
    return Directory(path.join(roms, LibretroCoreCatalog.importFolderFor(systemFolder)));
  }

  /// The registered library folders games of [systemFolder] can be imported
  /// into, in their registration order: those this device can open. A
  /// library keeps its own console folder: the first child whose name is
  /// the system's import folder ([LibretroCoreCatalog.importFolderFor], its
  /// id unless the scanner knows it under another name) or one of
  /// [folderAliases] (ignoring case), else a new `<root>/<import folder>`.
  static Future<List<LibretroImportLibrary>> importLibraries(
    String systemFolder, {
    required Iterable<String> registeredRoots,
    Iterable<String> folderAliases = const <String>[],
  }) async {
    final folder = LibretroCoreCatalog.importFolderFor(systemFolder);
    final names = <String>{
      folder,
      for (final alias in folderAliases)
        if (alias.trim().isNotEmpty) alias.trim().toLowerCase(),
    };
    final libraries = <LibretroImportLibrary>[];
    final seen = <String>{};
    for (final registered in registeredRoots) {
      if (registered.startsWith('content://')) continue;
      final root = path.normalize(registered);
      if (!seen.add(root) || !await Directory(root).exists()) continue;
      libraries.add(LibretroImportLibrary(root: root, directory: await _consoleDirectoryIn(root, folder, names)));
    }
    return libraries;
  }

  static Future<String> _consoleDirectoryIn(String root, String folder, Set<String> names) async {
    if (names.contains(path.basename(root).trim().toLowerCase())) return root;
    try {
      await for (final entity in Directory(root).list(followLinks: false)) {
        if (entity is Directory && names.contains(path.basename(entity.path).trim().toLowerCase())) {
          return entity.path;
        }
      }
    } on FileSystemException catch (error) {
      _log.w('Library folder $root unreadable: $error');
    }
    return path.join(root, folder);
  }

  /// Imports games for a system folder. The picker offers only the formats
  /// the system's cores open and the library scanner indexes for it
  /// ([systemExtensions], else the extensions the database lists for the
  /// system): a copied file the scanner ignores would never appear.
  ///
  /// Games go to [library] (see [importLibraries]); without one, to
  /// NeoStation's own `roms` folder ([LibretroImportResult.createdLibraryRoot]).
  /// A picked file already in the destination with the same name and size is
  /// not copied again ([LibretroImportResult.alreadyPresent]); one with the
  /// same name and another size is copied as "name (2).ext".
  static Future<LibretroImportResult> importGames(
    String systemFolder, {
    Iterable<String>? systemExtensions,
    LibretroImportLibrary? library,
  }) => StorageImportActivity.run(() async {
    final folder = systemFolder.toLowerCase();
    final indexed = systemExtensions ?? await _indexedExtensions(folder);
    final extensions = LibretroCoreCatalog.importExtensionsFor(folder, indexed: indexed).toList()..sort();
    if (extensions.isEmpty) {
      return LibretroImportResult(imported: 0, rejected: 0, systemFolder: folder, noImportableType: true);
    }
    final selection = await FilePicker.pickFiles(
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: extensions,
      withData: false,
      lockParentWindow: true,
    );
    if (selection == null) {
      return LibretroImportResult(imported: 0, rejected: 0, systemFolder: folder);
    }
    final destination = library != null ? Directory(library.directory) : await importDirectoryFor(folder);
    await destination.create(recursive: true);
    var imported = 0;
    var rejected = 0;
    var alreadyPresent = 0;
    final importedPaths = <String>[];
    final rejectedFiles = <LibretroRejectedFile>[];
    final missingTracks = <LibretroMissingTracks>[];
    // Picked path -> length its import verified (docs/storage-audit-cleanup.md § 4).
    final verifiedCopies = <String, int>{};
    for (final file in selection.files) {
      final source = file.path;
      final extension = path.extension(file.name).replaceFirst('.', '').toLowerCase();
      if (source == null) {
        rejected++;
        rejectedFiles.add(LibretroRejectedFile(file.name, LibretroRejectReason.unreadable));
        continue;
      }
      if (!extensions.contains(extension)) {
        rejected++;
        rejectedFiles.add(LibretroRejectedFile(file.name, LibretroRejectReason.wrongType));
        continue;
      }
      try {
        final sourceLength = await File(source).length();
        final existing = File(path.join(destination.path, file.name));
        if (await existing.exists() && await existing.length() == sourceLength) {
          alreadyPresent++;
          continue;
        }
        final target = await _uniqueDestination(destination, file.name);
        final copied = await File(source).copy(target.path);
        final length = await copied.length();
        if (length == 0 || length != sourceLength) {
          await copied.delete();
          rejected++;
          rejectedFiles.add(LibretroRejectedFile(file.name, LibretroRejectReason.noSpace));
          continue;
        }
        imported++;
        importedPaths.add(copied.path);
        if (extension == 'cue' || extension == 'm3u') {
          try {
            final missing = await copyReferencedTracks(File(source), destination);
            if (missing.isNotEmpty) {
              missingTracks.add(LibretroMissingTracks(file.name, missing));
            }
          } catch (error) {
            // The sheet is in the library: it counts once, as imported.
            _log.w('Libretro import could not read the tracks of ${file.name}: $error');
            missingTracks.add(LibretroMissingTracks(file.name, const <String>[]));
          }
        }
        // The sheet itself is verified, and its tracks were looked for next
        // to it: the picker's copy is not read again (as before, whatever
        // the tracks turned out to be).
        verifiedCopies[source] = length;
      } catch (error) {
        _log.w('Libretro import rejected ${file.name}: $error');
        rejected++;
        rejectedFiles.add(LibretroRejectedFile(file.name, classifyCopyError(error)));
      }
    }
    // Once every pick is handled (a cue sheet reads its tracks from the
    // picker's folder), the copies of the verified imports are not read again.
    for (final copy in verifiedCopies.entries) {
      await StoragePickerCopies.discardAfterVerifiedImport(copy.key, expectedLength: copy.value);
    }
    return LibretroImportResult(
      imported: imported,
      rejected: rejected,
      alreadyPresent: alreadyPresent,
      importedPaths: importedPaths,
      systemFolder: folder,
      createdLibraryRoot: library == null ? destination.parent.path : null,
      rejectedFiles: rejectedFiles,
      missingTracks: missingTracks,
      acceptedExtensions: extensions,
    );
  });

  static int? _osCode(Object error) => error is FileSystemException ? error.osError?.errorCode : null;

  static bool _isNoSpace(Object error) => _osCode(error) == 28;

  static bool _isUnreadable(Object error) =>
      error is PathNotFoundException || error is PathAccessException || const <int>{1, 2, 13}.contains(_osCode(error));

  /// The reason a copy attempt that threw is reported with.
  @visibleForTesting
  static LibretroRejectReason classifyCopyError(Object error) {
    if (_isNoSpace(error)) return LibretroRejectReason.noSpace;
    if (_isUnreadable(error)) return LibretroRejectReason.unreadable;
    return LibretroRejectReason.copyFailed;
  }

  /// Locale key of the sentence naming the cause of [error] when it is a
  /// known one (folder access lost, no space left, source unreadable); null
  /// otherwise, then the raw text is the last resort.
  static String? knownFailureKey(Object error) {
    if (error.runtimeType.toString() == 'ExternalFolderAccessException' ||
        (error is StateError && error.message.toLowerCase().contains('folder'))) {
      return 'importErrorFolderAccess';
    }
    if (_isNoSpace(error)) return 'importErrorNoSpace';
    if (_isUnreadable(error)) return 'importErrorUnreadable';
    return null;
  }

  /// [importGames] for a system model: its canonical folder and the
  /// extensions it carries from the database.
  static Future<LibretroImportResult> importGamesForSystem(SystemModel system, {LibretroImportLibrary? library}) =>
      importGames(
        systemKey(system),
        systemExtensions: system.extensions.isEmpty ? null : system.extensions,
        library: library,
      );

  /// Imports games for one of the embedded consoles, even before it has any
  /// game: into [system] when the caller resolved it (from the provider's
  /// available systems), else into the console's import system.
  static Future<LibretroImportResult> importGamesForConsole(
    String console, {
    SystemModel? system,
    LibretroImportLibrary? library,
  }) async {
    final descriptor = LibretroCoreCatalog.consoles[console];
    if (descriptor == null) return const LibretroImportResult(imported: 0, rejected: 0);
    if (system != null) return importGamesForSystem(system, library: library);
    return importGames(descriptor.importSystem, library: library);
  }

  /// Extensions the scanner indexes for a system id (from its
  /// `assets/systems` definition, synced into the database); null when they
  /// cannot be read, in which case the picker keeps every core format.
  static Future<Set<String>?> _indexedExtensions(String systemId) async {
    try {
      final extensions = await SystemRepository.getExtensionsForSystem(systemId);
      return extensions.isEmpty ? null : extensions;
    } catch (error) {
      _log.w('Indexed extensions unavailable for $systemId: $error');
      return null;
    }
  }

  /// A cue sheet or playlist only works with the files it names; copy those
  /// that sit next to the picked file when the picker granted access. Returns
  /// the names that are neither in [destination] nor could be copied there.
  @visibleForTesting
  static Future<List<String>> copyReferencedTracks(File descriptor, Directory destination) async {
    final lines = await descriptor.readAsLines();
    final pattern = RegExp(r'FILE\s+"([^"]+)"', caseSensitive: false);
    final names = <String>{
      for (final line in lines)
        ...pattern.allMatches(line).map((match) => match.group(1)!),
      if (path.extension(descriptor.path).toLowerCase() == '.m3u')
        ...lines.map((line) => line.trim()).where((line) => line.isNotEmpty && !line.startsWith('#')),
    };
    final missing = <String>[];
    for (final name in names) {
      final source = File(path.join(descriptor.parent.path, name));
      final target = File(path.join(destination.path, path.basename(name)));
      if (await target.exists()) continue;
      try {
        if (await source.exists()) {
          await source.copy(target.path);
        } else {
          missing.add(path.basename(name));
        }
      } catch (error) {
        _log.w('Libretro import could not copy the track $name: $error');
        missing.add(path.basename(name));
      }
    }
    return missing;
  }

  static Future<File> _uniqueDestination(Directory directory, String name) async {
    final base = path.basenameWithoutExtension(name);
    final extension = path.extension(name);
    var candidate = File(path.join(directory.path, name));
    var index = 2;
    while (await candidate.exists()) {
      candidate = File(path.join(directory.path, '$base ($index)$extension'));
      index++;
    }
    return candidate;
  }

  /// Copies RetroArch's `saves`, `states` and `system` folders from a folder
  /// the user picks (normally On My iPhone › RetroArch). Existing NeoStation
  /// files are kept; RetroArch's files are only read.
  static Future<LibretroRetroArchCopy?> copyRetroArchData() => StorageImportActivity.run(() async {
    final picked = await ExternalFolderAccess.pickAndActivateFolder(key: _retroArchImportKey);
    if (picked == null) return null;
    await ensureLayout();
    final root = Directory(picked);
    final saves = await _findFolder(root, 'saves');
    final states = await _findFolder(root, 'states');
    final system = await _findFolder(root, 'system');
    final savesCopy = saves == null ? const _TreeCopy() : await _copyTree(saves, await savesDirectory());
    final statesCopy = states == null ? const _TreeCopy() : await _copyTree(states, await statesDirectory());
    final systemCopy = system == null ? const _TreeCopy() : await _copyTree(system, await systemDirectory());
    final all = <_TreeCopy>[savesCopy, statesCopy, systemCopy];
    return LibretroRetroArchCopy(
      saves: savesCopy.copied,
      states: statesCopy.copied,
      system: systemCopy.copied,
      emulator3dsFolder: await holds3dsUserFolder(root),
      alreadyPresent: all.fold(0, (sum, copy) => sum + copy.present),
      skipped: all.fold(0, (sum, copy) => sum + copy.skipped.length),
      skippedNames: <String>[for (final copy in all) ...copy.skipped].take(3).toList(),
      foundFolders: <Directory?>[saves, states, system].where((folder) => folder != null).length,
      folderName: path.basename(path.normalize(picked)),
    );
  });

  /// Whether [root] is, or holds within two levels, the user folder of a
  /// Nintendo 3DS emulator (Azahar, Citra, Lime3DS): a `nand` or `sysdata`
  /// folder. That layout is read by the 3DS import
  /// (`Libretro3dsSystemDataService`), not by [copyRetroArchData].
  @visibleForTesting
  static Future<bool> holds3dsUserFolder(Directory root) async =>
      await _findFolder(root, 'nand', depth: 2) != null || await _findFolder(root, 'sysdata', depth: 2) != null;

  static Future<Directory?> _findFolder(Directory root, String name, {int depth = 3}) async {
    if (path.basename(root.path).toLowerCase() == name) return root;
    if (depth == 0) return null;
    try {
      final children = await root.list(followLinks: false).where((entry) => entry is Directory).cast<Directory>().toList();
      for (final child in children) {
        if (path.basename(child.path).toLowerCase() == name) return child;
      }
      for (final child in children) {
        final found = await _findFolder(child, name, depth: depth - 1);
        if (found != null) return found;
      }
    } catch (error) {
      _log.w('RetroArch folder scan skipped ${root.path}: $error');
    }
    return null;
  }

  static Future<_TreeCopy> _copyTree(Directory source, Directory destination) async {
    var copied = 0;
    var present = 0;
    final skipped = <String>[];
    await for (final entity in source.list(recursive: true, followLinks: false)) {
      if (entity is! File) continue;
      final relative = path.relative(entity.path, from: source.path);
      if (relative.split(path.separator).any((part) => part.startsWith('.'))) continue;
      final target = File(path.join(destination.path, relative));
      try {
        if (await target.exists()) {
          present++;
          continue;
        }
        if (await entity.length() > _maxSystemFileBytes) {
          skipped.add(relative);
          continue;
        }
        await target.parent.create(recursive: true);
        await entity.copy(target.path);
        copied++;
      } catch (error) {
        _log.w('RetroArch copy skipped $relative: $error');
        skipped.add(relative);
      }
    }
    return _TreeCopy(copied: copied, present: present, skipped: skipped);
  }
}

class _TreeCopy {
  const _TreeCopy({this.copied = 0, this.present = 0, this.skipped = const <String>[]});

  final int copied;
  final int present;
  final List<String> skipped;
}

/// Sentences shown to the user after an import or a library move: what was
/// refused, and why. Texts come from [LibretroLocale].
abstract final class LibretroImportMessages {
  static const int _maxLines = 3;

  static String _reasonText(Locale locale, LibretroRejectReason reason, List<String> extensions) => switch (reason) {
        LibretroRejectReason.wrongType => LibretroLocale.format(locale, 'importRejectWrongType', {
            'extensions': extensions.map((extension) => '.$extension').join(', '),
          }),
        LibretroRejectReason.unreadable => LibretroLocale.format(locale, 'importRejectUnreadable', const {}),
        LibretroRejectReason.noSpace => LibretroLocale.format(locale, 'importRejectNoSpace', const {}),
        LibretroRejectReason.copyFailed => LibretroLocale.format(locale, 'importRejectCopyFailed', const {}),
      };

  static List<String> _lines(Locale locale, List<String> lines) => <String>[
        ...lines.take(_maxLines),
        if (lines.length > _maxLines) LibretroLocale.format(locale, 'importAndMore', {'count': lines.length - _maxLines}),
      ];

  /// Notices about what was not imported, one per entry: the console cannot
  /// import, rejected files with their cause, cue sheets missing tracks.
  static List<String> forImport(Locale locale, LibretroImportResult result) {
    final notices = <String>[];
    if (result.noImportableType) {
      notices.add(LibretroLocale.format(locale, 'importNoExtensions', const {}));
    }
    if (result.rejected > 0) {
      if (result.rejectedFiles.isEmpty) {
        notices.add(LibretroLocale.format(locale, 'gamesRejected', const {}));
      } else {
        notices.add(<String>[
          LibretroLocale.format(locale, 'importRejectedHeader', {'count': result.rejected}),
          ..._lines(locale, <String>[
            for (final file in result.rejectedFiles)
              '${file.name} — ${_reasonText(locale, file.reason, result.acceptedExtensions)}',
          ]),
        ].join('\n'));
      }
    }
    for (final tracks in result.missingTracks.take(_maxLines)) {
      notices.add(
        tracks.files.isEmpty
            ? LibretroLocale.format(locale, 'importTracksUnreadable', {'name': tracks.name})
            : LibretroLocale.format(locale, 'importMissingTracks', {
                'name': tracks.name,
                'files': tracks.files.take(5).join(', ') + (tracks.files.length > 5 ? ', …' : ''),
              }),
      );
    }
    return notices;
  }

  /// The notice after "Copy RetroArch saves and BIOS" (the 3DS-folder case
  /// stays with the caller).
  static String forRetroArch(Locale locale, LibretroRetroArchCopy copy) {
    final lines = <String>[];
    if (copy.total > 0) {
      lines.add(LibretroLocale.format(locale, 'retroArchImported', {
        'saves': copy.saves,
        'states': copy.states,
        'system': copy.system,
      }));
    } else if (copy.foundFolders == 0 && copy.alreadyPresent == 0 && copy.skipped == 0 && copy.folderName.isNotEmpty) {
      lines.add(LibretroLocale.format(locale, 'retroArchNothingFolder', {'folder': copy.folderName}));
    } else if (copy.alreadyPresent == 0 && copy.skipped == 0) {
      lines.add(LibretroLocale.format(locale, 'retroArchNothing', const {}));
    }
    if (copy.alreadyPresent > 0) {
      lines.add(LibretroLocale.format(locale, 'retroArchPresent', {'count': copy.alreadyPresent}));
    }
    if (copy.skipped > 0) {
      lines.add(LibretroLocale.format(locale, 'retroArchSkipped', {
        'count': copy.skipped,
        'names': copy.skippedNames.join(', ') + (copy.skipped > copy.skippedNames.length ? ', …' : ''),
      }));
    }
    return lines.join('\n');
  }

  /// The sentence for a failed import or library action: the known cause
  /// when there is one, else [fallbackKey] with the raw error.
  static String failure(Locale locale, Object error, {String fallbackKey = 'importFailed'}) {
    final key = LibretroInternalService.knownFailureKey(error);
    return key != null
        ? LibretroLocale.format(locale, key, const {})
        : LibretroLocale.format(locale, fallbackKey, {'error': error});
  }

  /// The notice after a library move.
  static String forMove(Locale locale, RomLibraryMove move, String source) {
    if (move.ownLibrary) return LibretroLocale.format(locale, 'libraryMoveOwn', const {});
    if (move.total == 0) {
      final examples = NeoStationRomLibrary.exampleFolders().map((name) => '“$name”').join(', ');
      final lines = <String>[
        LibretroLocale.format(locale, 'libraryMoveNoConsole', {'folder': source, 'examples': examples}),
        if (move.unrecognisedFolders.isNotEmpty)
          LibretroLocale.format(locale, 'libraryMoveUnrecognised', {
            'folders': move.unrecognisedFolders.take(5).map((name) => '“$name”').join(', ') +
                (move.unrecognisedFolders.length > 5 ? ', …' : ''),
          }),
      ];
      return lines.join('\n');
    }
    final head = LibretroLocale.format(locale, 'libraryMoved', {
      'moved': move.moved + move.notRemoved,
      'kept': move.alreadyPresent,
      'failed': move.failed,
    });
    if (move.failures.isEmpty) return head;
    String reason(RomLibraryFailureReason value) => LibretroLocale.format(locale, switch (value) {
          RomLibraryFailureReason.icloud => 'libraryFailIcloud',
          RomLibraryFailureReason.sizeMismatch => 'libraryFailSize',
          RomLibraryFailureReason.copyError => 'libraryFailCopy',
          RomLibraryFailureReason.notRemoved => 'libraryFailNotRemoved',
        }, const {});
    return <String>[
      head,
      ..._lines(locale, <String>[for (final failure in move.failures) '${failure.name} — ${reason(failure.reason)}']),
    ].join('\n');
  }
}
