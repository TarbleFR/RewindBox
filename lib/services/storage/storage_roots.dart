/// Declarative inventory of the storage used by NeoStation and its engines
/// (docs/storage-audit-cleanup.md § 2, INV-01 … INV-29, and § 3.1).
///
/// Nothing here writes: the registry only joins the container paths with the
/// relative paths of the inventory. The only `path_provider` calls are in
/// [StorageContainers] (through its test seams); [StorageRootRegistry.resolve]
/// additionally reads `ConfigService.linkedExternalFolderPath` and the
/// ARMSX2 linked folders (static fields), `Rpcs3RapLicenceService
/// .storageRedirection()` (reads `Data/vfs.yml`) and the bundle identifier.
/// The service accessors of § 3.1 are not called: their paths are joined
/// here from the containers, exactly as they compute them (checked in their
/// sources), so no accessor that creates a directory or a file can run.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../config_service.dart';
import '../libretro_3ds_system_data_service.dart';
import '../library_source_files.dart';
import '../rpcs3_rap_licence_service.dart';
import 'storage_categorizer.dart';

/// Legend A–I of the audit plus the index/database/configuration files and
/// the paths no rule identifies.
enum StorageCategory {
  /// A — games, ROM, ISO, installed games.
  games,

  /// B — saves, states, NAND, memory cards.
  saves,

  /// C — BIOS, firmware, licences, system files, pairing/JIT.
  systemFiles,

  /// D — regenerable caches.
  caches,

  /// E — scraped media and metadata.
  media,

  /// F — temporary files.
  temporary,

  /// G — logs and diagnostics.
  logs,

  /// H — user content other than games.
  userContent,

  /// I — NeoSwap.
  neoSwap,

  /// Database, configuration and index files. Named `index` in § 3.1;
  /// renamed because an enum value cannot be called `index` in Dart
  /// (`Enum.index`).
  indexFiles,

  /// No rule identifies the path (« Autres données (non identifiées) »).
  unknown,
}

/// What a cleanup may do with a path. [never] is the default of every path
/// without a rule.
enum StorageDeletionClass {
  never,
  regenerableAtCost,
  temporaryWhenIdle,
  confirmation,
}

/// Engine that owns a path; product names are never translated.
enum StorageEngine {
  frontend,
  libretro,
  rpcs3,
  dolphin,
  kartpad,
  dusklight,
  armsx2,
  library,
  neoSwap,
  system,
}

/// The four directories of the app container that are measured.
enum StorageContainer { documents, applicationSupport, caches, temporary }

/// Kind of a scanned entry (§ 3.2). Declared here, the base library of the
/// storage tool, and exported by `storage_scanner.dart` and
/// `storage_categorizer.dart`.
enum StorageEntryKind { file, directory, link, icloudPlaceholder, inaccessible }

/// Family of orphan analysis a rule anchors (§ 3.5).
enum StorageOrphanAnchor {
  /// `Documents/media/<system>/<type>/<name>.<ext>` (INV-05).
  media,

  /// `Support/Library/covers/<id>.png` (INV-23).
  libraryCover,

  /// `Documents/Libretro/Saves/<core>/…` (INV-14), listed only.
  libretroSave,

  /// `Documents/Libretro/States/<core>/…` (INV-14), listed only.
  libretroState,

  /// `Support/NeoStation/Dolphin/User/StateSaves` (INV-21), listed only.
  dolphinState,

  /// `…/dev_hdd0/home/00000001/savedata/<DIR>` (INV-16), listed only.
  rpcs3Savedata,

  /// `Documents/ARMSX2/Saves/Savestates` (INV-11), listed only.
  armsx2Savestate,

  /// Folders searched for duplicate game copies (name and size).
  gameCopy,
}

/// iOS answers the same container through `/var/…` and `/private/var/…`
/// (`resolveSymbolicLinks()`): both forms compare equal once canonical.
String storageCanonicalPath(String path) {
  var value = p.normalize(path);
  for (final prefix in const ['/private/var', '/private/tmp']) {
    if (value == prefix || value.startsWith('$prefix/')) {
      value = value.substring('/private'.length);
      break;
    }
  }
  return value;
}

/// Absolute paths of the four measured containers.
class StorageContainers {
  const StorageContainers({
    required this.documents,
    required this.applicationSupport,
    required this.caches,
    required this.temporary,
  });

  final String documents;
  final String applicationSupport;
  final String caches;

  /// `<container>/tmp` (`NSTemporaryDirectory()`), see [resolve].
  final String temporary;

  /// Test seams of the three `path_provider` calls.
  @visibleForTesting
  static Future<Directory> Function() documentsDirectory =
      getApplicationDocumentsDirectory;
  @visibleForTesting
  static Future<Directory> Function() supportDirectory =
      getApplicationSupportDirectory;
  @visibleForTesting
  static Future<Directory> Function() cacheDirectory =
      getApplicationCacheDirectory;

  /// The only `path_provider` calls of the storage tool.
  ///
  /// [temporary] is never `getTemporaryDirectory()`: on iOS that answers
  /// `NSCachesDirectory` (`Library/Caches`, path_provider_foundation 2.6.0
  /// `getTemporaryPath`), not the `tmp/` of the inventory (INV-28,
  /// `NSTemporaryDirectory()`, where file_picker copies every pick and iOS
  /// puts its `*-Inbox` copies). It is the `tmp` folder next to `Documents`
  /// in the app container ([temporaryDirectory]).
  /// `getApplicationSupportDirectory()` and `getApplicationCacheDirectory()`
  /// create their standard container folder when it is missing, as
  /// everywhere else in the app.
  static Future<StorageContainers> resolve() async {
    final documents = p.normalize((await documentsDirectory()).path);
    final support = p.normalize((await supportDirectory()).path);
    final caches = p.normalize((await cacheDirectory()).path);
    return StorageContainers(
      documents: documents,
      applicationSupport: support,
      caches: caches,
      temporary: temporaryPathFor(documents),
    );
  }

  /// `<container>/tmp` for the Documents directory [documents].
  static String temporaryPathFor(String documents) =>
      p.join(p.dirname(p.normalize(documents)), 'tmp');

  /// The app's `tmp/` (`NSTemporaryDirectory()` on iOS), from the Documents
  /// directory only; for the picker-copy maintenance (§ 4).
  static Future<Directory> temporaryDirectory() async =>
      Directory(temporaryPathFor((await documentsDirectory()).path));

  /// `Library/Application Support` alone (maintenance backups, § 3.6).
  static Future<String> applicationSupportPath() async =>
      p.normalize((await supportDirectory()).path);

  String pathOf(StorageContainer container) => switch (container) {
    StorageContainer.documents => documents,
    StorageContainer.applicationSupport => applicationSupport,
    StorageContainer.caches => caches,
    StorageContainer.temporary => temporary,
  };

  /// `<Documents>`, `<Support>`, `<Caches>` or `<tmp>` (report and journal).
  static String placeholderOf(StorageContainer container) =>
      switch (container) {
        StorageContainer.documents => '<Documents>',
        StorageContainer.applicationSupport => '<Support>',
        StorageContainer.caches => '<Caches>',
        StorageContainer.temporary => '<tmp>',
      };

  /// The container holding [absolutePath] (the deepest one if two nest),
  /// or null outside the four containers.
  StorageContainer? containerOf(String absolutePath) {
    final target = storageCanonicalPath(absolutePath);
    StorageContainer? best;
    var bestLength = -1;
    for (final container in StorageContainer.values) {
      final base = storageCanonicalPath(pathOf(container));
      if ((target == base || p.isWithin(base, target)) &&
          base.length > bestLength) {
        best = container;
        bestLength = base.length;
      }
    }
    return best;
  }

  /// [absolutePath] relative to its container (`''` for the container
  /// itself), or null outside the containers.
  String? relativePathOf(String absolutePath) {
    final container = containerOf(absolutePath);
    if (container == null) return null;
    final base = storageCanonicalPath(pathOf(container));
    final target = storageCanonicalPath(absolutePath);
    return target == base ? '' : p.relative(target, from: base);
  }

  /// `<Documents>/a/b` form of [absolutePath], or null outside the
  /// containers.
  String? displayPathOf(String absolutePath) {
    final container = containerOf(absolutePath);
    final relative = relativePathOf(absolutePath);
    if (container == null || relative == null) return null;
    final placeholder = placeholderOf(container);
    return relative.isEmpty ? placeholder : '$placeholder/$relative';
  }
}

/// Relative paths of the inventory used outside the registry (detector,
/// planner, guards). Relative to the container named in each comment.
abstract final class StorageLayout {
  /// Documents.
  static const String roms = 'roms';
  static const String userData = 'user-data';
  static const String userDataTemp = 'user-data/temp';
  static const String media = 'media';
  static const String diagnostics = 'Diagnostics';
  static const String libretro = 'Libretro';
  static const String libretroSystem = 'Libretro/System';
  static const String libretroSaves = 'Libretro/Saves';
  static const String libretroStates = 'Libretro/States';
  static const String libretroSkins = 'Libretro/Skins';
  static const String libretroSkinStaging = 'Libretro/Skins/.staging';
  static const String libretroLogs = 'Libretro/Logs';
  static const String libretroSessionLog = 'Libretro/Logs/session.log';

  /// `Saves/<core>` and `Backups/<core>` of the 3DS core
  /// (`Libretro3dsSystemDataService.coreFolderName`).
  static const String libretro3dsSaves =
      'Libretro/Saves/${Libretro3dsSystemDataService.coreFolderName}';
  static const String libretro3dsBackups =
      'Libretro/Backups/${Libretro3dsSystemDataService.coreFolderName}';
  static const String documentsLibrary = 'Library';
  static const String armsx2 = 'ARMSX2';
  static const String armsx2Games = 'ARMSX2/Games';
  static const String armsx2Bios = 'ARMSX2/BIOS';
  static const String armsx2Savestates = 'ARMSX2/Saves/Savestates';
  static const String kartpad = 'Ports/KartPad';
  static const String kartpadGames = 'Ports/KartPad/Games';
  static const String kartpadLogs = 'Ports/KartPad/Logs';
  static const String kartpadGameData = 'Ports/KartPad/Runtime/GameData';
  static const String dusklight = 'Ports/Dusklight';
  static const String dusklightGames = 'Ports/Dusklight/Games';
  static const String rpcs3Workspace = 'RPCS3';
  static const String rpcs3ExportSaves = 'RPCS3/Export/Game Saves';
  static const String dolphinRecordings = 'Recordings/Dolphin';

  /// Application Support.
  static const String supportLibrary = 'Library';
  static const String libraryIndex = 'Library/local-index.json';
  static const String libraryCovers = 'Library/covers';
  static const String stikjit = 'StikJIT';
  static const String rpcs3 = 'NeoStation/RPCS3';
  static const String rpcs3Data = 'NeoStation/RPCS3/Data';
  static const String rpcs3Cache = 'NeoStation/RPCS3/Cache';
  static const String rpcs3Imports = 'NeoStation/RPCS3/Imports';
  static const String rpcs3SaveBackups = 'NeoStation/RPCS3/SaveBackups';
  static const String rpcs3RapBackups = 'NeoStation/RPCS3/RapBackups';
  static const String dolphin = 'NeoStation/Dolphin';
  static const String dolphinLibrary = 'NeoStation/Dolphin/Library';
  static const String dolphinStates = 'NeoStation/Dolphin/User/StateSaves';
  static const String dolphinLogs = 'NeoStation/Dolphin/Logs';
  static const String dolphinCrashMarkers = 'NeoStation/Dolphin/CrashMarkers';
  static const String dolphinActiveMarker =
      'NeoStation/Dolphin/CrashMarkers/active-session.json';
  static const String dolphinShaderCache = 'NeoStation/Dolphin/ShaderCache';
  static const String maintenance = 'NeoStation/Maintenance';
  static const String kartpadSupport = 'KartPad';

  /// Caches.
  static const String libretroCaches = 'Libretro';
  static const String libretroContent = 'Libretro/Content';
  static const String libraryCaches = 'Library';
  static const String libraryHttpCache = 'Library/library_http';
  static const String libraryImageCache = 'Library/library_images';

  /// Temporary (`tmp/`).
  static const String framePacing = 'NeoStation-Dolphin-FramePacing.json';

  /// RPCS3 paths relative to the `Data` root.
  static const String rpcs3HddGames = 'dev_hdd0/game';
  static const String rpcs3Games = 'games';
  static const String rpcs3UserHome = 'dev_hdd0/home/00000001';
  static const String rpcs3Savedata = 'dev_hdd0/home/00000001/savedata';
  static const String rpcs3Exdata = 'dev_hdd0/home/00000001/exdata';
  static const String rpcs3DevFlash = 'dev_flash';
  static const String rpcs3HddTmp = 'dev_hdd0/tmp';
  static const String rpcs3Hdd1 = 'dev_hdd1';

  /// `Maintenance/data-<yyyyMMdd-HHmmss>.sqlite` (§ 3.6), optional `-<n>`
  /// when two backups share a second.
  static final RegExp maintenanceBackup = RegExp(
    r'^data-\d{8}-\d{6}(?:-\d+)?\.sqlite$',
  );

  /// `.<name>.icloud`: a file of iCloud Drive not downloaded
  /// (`neostation_rom_library.dart`).
  static final RegExp icloudPlaceholder = RegExp(r'^\..+\.icloud$');
}

/// One rule of the inventory: the paths under [relative] (in [container],
/// the root's container when null), or only the entries directly in
/// [relative] whose name matches [namePattern] together with everything
/// below them.
class StorageRule {
  const StorageRule({
    required this.relative,
    required this.category,
    required this.deletionClass,
    this.engine,
    this.namePattern,
    this.orphanAnchor,
    this.minimumAge,
    this.labelKey,
    this.id = '',
    this.container,
    this.absolutePath,
    this.aggregateOnly = false,
  });

  /// Directory of the rule relative to [container] (`''` = the container).
  final String relative;
  final StorageCategory category;
  final StorageDeletionClass deletionClass;
  final StorageEngine? engine;

  /// A [String] matches one exact name, a [RegExp] through `hasMatch`.
  final Pattern? namePattern;
  final StorageOrphanAnchor? orphanAnchor;

  /// Age below which a temporary file is never proposed (§ 3.7).
  final Duration? minimumAge;

  /// `StorageLocale` key; null: the category's label is used.
  final String? labelKey;

  /// Stable identifier (`INV-14.saves`, `NEVER.sqlite`); never names a
  /// game, a book or the hidden library folder.
  final String id;

  /// Null: the container of the root that declares the rule.
  final StorageContainer? container;

  /// Never-list entries outside the containers (library folders, linked
  /// folder): their absolute directory; null otherwise.
  final String? absolutePath;

  /// The subtree is measured but never detailed (scanner folds it into its
  /// parent, report aggregates it).
  final bool aggregateOnly;

  bool matchesName(String name) {
    final pattern = namePattern;
    if (pattern == null) return true;
    if (pattern is String) return pattern == name;
    if (pattern is RegExp) return pattern.hasMatch(name);
    final match = pattern.matchAsPrefix(name);
    return match != null && match.end == name.length;
  }

  @override
  String toString() => 'StorageRule($id)';
}

/// A directory of a root: [relative] in [container] (`''` = the container).
class StorageLocation {
  const StorageLocation(this.container, this.relative);

  final StorageContainer container;
  final String relative;

  @override
  bool operator ==(Object other) =>
      other is StorageLocation &&
      other.container == container &&
      other.relative == relative;

  @override
  int get hashCode => Object.hash(container, relative);
}

/// One row of the inventory. [container]/[relative] is its main directory;
/// rows spanning several directories list the others in
/// [additionalLocations] (deviation from § 3.1, documented in the report).
class StorageRoot {
  const StorageRoot({
    required this.id,
    required this.container,
    required this.relative,
    required this.labelKey,
    required this.rules,
    this.engine,
    this.hidden = false,
    this.additionalLocations = const [],
  });

  /// `INV-01` … `INV-29`.
  final String id;
  final StorageContainer container;
  final String relative;

  /// `rootLibrary`, `rootDocuments`, `rootSupport`, `rootCaches` or
  /// `rootTemporary` (§ 3.11).
  final String labelKey;
  final List<StorageRule> rules;
  final StorageEngine? engine;

  /// The content cannot be listed (NeoSwap unlinks its files): the screen
  /// shows the NeoSwap limit instead of entries; its bytes still count.
  final bool hidden;
  final List<StorageLocation> additionalLocations;

  List<StorageLocation> get locations => [
    StorageLocation(container, relative),
    ...additionalLocations,
  ];
}

/// A scanned directory of the registry, resolved.
class StorageLocationPath {
  const StorageLocationPath({
    required this.rootId,
    required this.container,
    required this.relative,
    required this.path,
  });

  final String rootId;
  final StorageContainer container;
  final String relative;

  /// Absolute path as joined from the container (not canonical).
  final String path;
}

/// Why a path matched the exact never-list.
enum StorageExactMatch { container, root, marker }

/// Matching state of one directory, derived from its parent's
/// ([StorageRootRegistry.childContext]); lets the scanner classify each
/// entry in constant time with exactly the rules of
/// [StorageRootRegistry.ruleFor].
class StorageMatchContext {
  const StorageMatchContext._({
    required this.path,
    this.neverSubtree,
    this.deepest,
    this.rpcs3 = false,
    this.aggregate = false,
    this.rootId,
  });

  /// Canonical path of the directory.
  final String path;

  /// Never-list subtree entry covering the directory, if any.
  final StorageRule? neverSubtree;

  /// Deepest registry rule of the directory, if any.
  final StorageRule? deepest;

  /// Inside an RPCS3 root (INV-16 … INV-19).
  final bool rpcs3;

  /// Inside a subtree measured but never detailed.
  final bool aggregate;

  /// Root owning the directory (its deepest location), if any.
  final String? rootId;
}

/// What the registry knows of one entry.
class StorageRuleMatch {
  const StorageRuleMatch({
    this.exact,
    this.never,
    this.rule,
    this.rpcs3 = false,
    this.aggregate = false,
    this.rootId,
  });

  /// The entry is a container, a root directory or the Dolphin marker.
  final StorageExactMatch? exact;

  /// Never-list entry matched (exact, subtree, name), if any.
  final StorageRule? never;

  /// Deepest registry rule, if any.
  final StorageRule? rule;
  final bool rpcs3;
  final bool aggregate;
  final String? rootId;
}

class _NameNever {
  const _NameNever(this.rule, {this.exemptDirectory, this.exemptPattern});

  final StorageRule rule;
  final String? exemptDirectory;
  final Pattern? exemptPattern;
}

int _protection(StorageDeletionClass value) => switch (value) {
  StorageDeletionClass.never => 3,
  StorageDeletionClass.confirmation => 2,
  StorageDeletionClass.regenerableAtCost => 1,
  StorageDeletionClass.temporaryWhenIdle => 0,
};

/// The inventory resolved for one container (§ 3.1).
///
/// Deviation: the constructor is not `const` — the 29 roots and the rule
/// index are computed once here, then every lookup is a few map reads.
class StorageRootRegistry {
  StorageRootRegistry(
    this.containers, {
    this.mediaDirectory,
    this.libraryRoots = const [],
    this.linkedExternalFolder,
    this.rpcs3Redirected = false,
    this.bundleIdentifier,
  }) {
    _build();
  }

  final StorageContainers containers;

  /// INV-05; null: `Documents/media` (`ConfigService.getMediaPath()` on
  /// iOS). Ignored when it is outside the containers.
  final String? mediaDirectory;

  /// Registered library folders (`SqliteConfigProvider.config.romFolders`):
  /// always protected; measured (INV-01) only inside a container and
  /// outside the other roots.
  final List<String> libraryRoots;

  /// `ConfigService.linkedExternalFolderPath`: protected like a library
  /// folder.
  final String? linkedExternalFolder;

  /// `Rpcs3RapLicenceService.storageRedirection(Data) != null`: every RPCS3
  /// root (INV-16 … INV-19) is then classified never.
  final bool rpcs3Redirected;

  /// Runtime bundle identifier (SideStore may rename it): names
  /// `Caches/<bundle-id>/` (INV-29, `NSURLCache`). Null:
  /// [defaultBundlePattern]. (`tmp/*-Inbox` matches any bundle.)
  final String? bundleIdentifier;

  /// Ids of the RPCS3 roots excluded as a whole under a redirection.
  static const Set<String> rpcs3RootIds = {
    'INV-16',
    'INV-17',
    'INV-18',
    'INV-19',
  };

  /// Default bundle identifier and the SideStore variant (`.<team id>`).
  static final RegExp defaultBundlePattern = RegExp(
    r'^com\.neogamelab\.neostation(?:\.[A-Za-z0-9-]+)?$',
  );

  late final List<StorageRoot> _roots;
  late final List<StorageLocationPath> _locations;
  final Map<String, StorageRoot> _rootsById = {};
  final Map<String, List<StorageRule>> _plain = {};
  final Map<String, List<StorageRule>> _patterned = {};
  final Map<String, StorageRule> _neverExact = {};
  final Map<String, StorageExactMatch> _exactKinds = {};
  final Map<String, StorageRule> _neverSubtree = {};
  final Map<String, List<StorageRule>> _neverPatterned = {};
  final List<_NameNever> _neverNames = [];
  final Map<String, String> _locationOwner = {};
  final Set<String> _rpcs3Locations = {};
  Set<String>? _resolvedRootPaths;

  /// Builds the registry of the running app (iOS).
  static Future<StorageRootRegistry> resolve({
    Iterable<String> libraryRoots = const [],
  }) async {
    final containers = await StorageContainers.resolve();
    // ConfigService.getMediaPath() on iOS is exactly Documents/media.
    final media = p.join(containers.documents, StorageLayout.media);
    final dataRoot = p.join(
      containers.applicationSupport,
      StorageLayout.rpcs3Data,
    );
    var redirected = true;
    try {
      redirected =
          await Rpcs3RapLicenceService.storageRedirection(dataRoot) != null;
    } catch (_) {
      // An unreadable redirection keeps every RPCS3 root protected.
      redirected = true;
    }
    String? bundle;
    try {
      final info = await PackageInfo.fromPlatform().timeout(
        const Duration(seconds: 2),
      );
      if (info.packageName.isNotEmpty) bundle = info.packageName;
    } catch (_) {
      bundle = null;
    }
    return StorageRootRegistry(
      containers,
      mediaDirectory: media,
      libraryRoots: [
        ...libraryRoots,
        ?ConfigService.linkedArmsx2FolderPath,
        ?ConfigService.linkedArmsx2GameFolderPath,
      ],
      linkedExternalFolder: ConfigService.linkedExternalFolderPath,
      rpcs3Redirected: redirected,
      bundleIdentifier: bundle,
    );
  }

  /// The 29 roots, in the order of the inventory table.
  List<StorageRoot> get roots => _roots;

  /// Every scanned directory, in root order (deepest location owns a path).
  List<StorageLocationPath> get locations => _locations;

  StorageRoot? rootById(String id) => _rootsById[id];

  /// Absolute path of [relative] in [container].
  String pathIn(StorageContainer container, String relative) {
    final base = containers.pathOf(container);
    return relative.isEmpty ? base : p.join(base, relative);
  }

  /// INV-05, absolute.
  String get mediaPath {
    final custom = mediaDirectory;
    if (custom != null && containers.containerOf(custom) != null) {
      return p.normalize(custom);
    }
    return pathIn(StorageContainer.documents, StorageLayout.media);
  }

  /// RPCS3 `Data` root (INV-16), absolute.
  String get rpcs3DataRoot =>
      pathIn(StorageContainer.applicationSupport, StorageLayout.rpcs3Data);

  /// Whitelist of the deletion manager: every scanned directory, symbolic
  /// links resolved (a missing directory resolves through its deepest
  /// existing parent). Computed once, on first use.
  Set<String> get resolvedRootPaths => _resolvedRootPaths ??= {
    for (final location in _locations) _resolve(location.path),
  };

  /// Deepest rule of [absolutePath], never-list entries first; null when no
  /// rule identifies the path (« non identifié », never).
  StorageRule? ruleFor(String absolutePath) {
    final match = matchPath(absolutePath);
    return match.never ?? match.rule;
  }

  /// Whether the path must never be deleted (classified never by
  /// [StorageCategorizer] as a file or directory). Links are refused by the
  /// deletion manager from `lstat`, not here.
  bool isProtected(String absolutePath) =>
      StorageCategorizer(
        this,
      ).classify(absolutePath, StorageEntryKind.file).deletionClass ==
      StorageDeletionClass.never;

  /// The container itself.
  bool isContainerPath(String absolutePath) =>
      _exactKinds[storageCanonicalPath(absolutePath)] ==
      StorageExactMatch.container;

  /// A scanned directory of a root (or a container).
  bool isRootPath(String absolutePath) {
    final kind = _exactKinds[storageCanonicalPath(absolutePath)];
    return kind == StorageExactMatch.root ||
        kind == StorageExactMatch.container;
  }

  /// Root owning [absolutePath] (deepest location containing it).
  String? rootIdFor(String absolutePath) => matchPath(absolutePath).rootId;

  /// Inside the hidden library subtree or another aggregate-only subtree.
  bool isAggregateOnly(String absolutePath) =>
      matchPath(absolutePath).aggregate;

  /// Inside an RPCS3 root (INV-16 … INV-19).
  bool isRpcs3Path(String absolutePath) => matchPath(absolutePath).rpcs3;

  /// Context of the filesystem root.
  StorageMatchContext get rootContext => const StorageMatchContext._(path: '/');

  /// Context of [directory], derived segment by segment from `/`.
  StorageMatchContext contextFor(String directory) {
    final canonical = storageCanonicalPath(directory);
    var context = rootContext;
    for (final segment in canonical.split('/')) {
      if (segment.isEmpty) continue;
      context = childContext(context, segment);
    }
    return context;
  }

  /// Context of the child [name] of [parent].
  StorageMatchContext childContext(StorageMatchContext parent, String name) {
    final child = _join(parent.path, name);
    final match = matchChild(parent, name);
    final subtree =
        _neverSubtree[child] ??
        _firstMatching(_neverPatterned[parent.path], name) ??
        parent.neverSubtree;
    return StorageMatchContext._(
      path: child,
      neverSubtree: subtree,
      deepest: match.rule,
      rpcs3: match.rpcs3,
      aggregate: match.aggregate,
      rootId: match.rootId,
    );
  }

  /// Everything the registry knows of the child [name] of [parent].
  StorageRuleMatch matchChild(StorageMatchContext parent, String name) {
    final child = _join(parent.path, name);
    final exact = _exactKinds[child];
    final ownSubtree =
        _neverSubtree[child] ??
        _firstMatching(_neverPatterned[parent.path], name);
    final never =
        _neverExact[child] ??
        ownSubtree ??
        parent.neverSubtree ??
        _nameNever(parent.path, name);
    final rule = _levelRule(parent.path, child, name) ?? parent.deepest;
    return StorageRuleMatch(
      exact: exact,
      never: never,
      rule: rule,
      rpcs3: parent.rpcs3 || _rpcs3Locations.contains(child),
      aggregate:
          parent.aggregate ||
          (ownSubtree?.aggregateOnly ?? false) ||
          (rule?.aggregateOnly ?? false),
      rootId: _locationOwner[child] ?? parent.rootId,
    );
  }

  /// [matchChild] for an absolute path.
  StorageRuleMatch matchPath(String absolutePath) {
    final canonical = storageCanonicalPath(absolutePath);
    if (canonical == '/') return const StorageRuleMatch();
    return matchChild(contextFor(p.dirname(canonical)), p.basename(canonical));
  }

  static String _join(String parent, String name) =>
      parent == '/' ? '/$name' : '$parent/$name';

  static StorageRule? _firstMatching(List<StorageRule>? rules, String name) {
    if (rules == null) return null;
    for (final rule in rules) {
      if (rule.matchesName(name)) return rule;
    }
    return null;
  }

  StorageRule? _levelRule(String parent, String child, String name) {
    StorageRule? best;
    void consider(StorageRule rule) {
      if (best == null ||
          _protection(rule.deletionClass) > _protection(best!.deletionClass)) {
        best = rule;
      }
    }

    final plain = _plain[child];
    if (plain != null) plain.forEach(consider);
    final patterned = _patterned[parent];
    if (patterned != null) {
      for (final rule in patterned) {
        if (rule.matchesName(name)) consider(rule);
      }
    }
    return best;
  }

  StorageRule? _nameNever(String parent, String name) {
    // Cheap filter: every global never name contains one of these (the
    // NSURLCache database `Cache.db*` since the review of the storage
    // services).
    if (!name.contains('.json') &&
        !name.contains('.yml') &&
        !name.contains('.sqlite') &&
        !name.endsWith('.icloud') &&
        !name.startsWith('Cache.db')) {
      return null;
    }
    for (final entry in _neverNames) {
      if (!entry.rule.matchesName(name)) continue;
      final exempt = entry.exemptPattern;
      if (exempt != null &&
          entry.exemptDirectory == parent &&
          (exempt is RegExp ? exempt.hasMatch(name) : exempt == name)) {
        continue;
      }
      return entry.rule;
    }
    return null;
  }

  static String _resolve(String path) {
    final segments = <String>[];
    var current = p.normalize(path);
    while (true) {
      try {
        if (FileSystemEntity.typeSync(current, followLinks: false) !=
            FileSystemEntityType.notFound) {
          final resolved = Directory(current).resolveSymbolicLinksSync();
          return segments.isEmpty
              ? resolved
              : p.joinAll([resolved, ...segments.reversed]);
        }
      } on FileSystemException {
        // Unreadable parent: keep walking up.
      }
      final parent = p.dirname(current);
      if (parent == current) return p.normalize(path);
      segments.add(p.basename(current));
      current = parent;
    }
  }

  String _abs(StorageContainer container, String relative) =>
      storageCanonicalPath(pathIn(container, relative));

  void _addRule(StorageRoot root, StorageRule rule) {
    final dir = rule.absolutePath != null
        ? storageCanonicalPath(rule.absolutePath!)
        : _abs(rule.container ?? root.container, rule.relative);
    final target = rule.namePattern == null ? _plain : _patterned;
    target.putIfAbsent(dir, () => []).add(rule);
  }

  void _build() {
    _roots = List.unmodifiable([
      for (final root in _buildRoots())
        StorageRoot(
          id: root.id,
          container: root.container,
          relative: root.relative,
          labelKey: root.labelKey,
          rules: List.unmodifiable(root.rules),
          engine: root.engine,
          hidden: root.hidden,
          additionalLocations: List.unmodifiable(root.additionalLocations),
        ),
    ]);
    for (final root in _roots) {
      _rootsById[root.id] = root;
      for (final rule in root.rules) {
        _addRule(root, rule);
      }
    }

    // Locations: the first root to declare a directory owns it.
    final locations = <StorageLocationPath>[];
    for (final root in _roots) {
      for (final location in root.locations) {
        final absolute = pathIn(location.container, location.relative);
        final canonical = storageCanonicalPath(absolute);
        if (_locationOwner.containsKey(canonical)) continue;
        _locationOwner[canonical] = root.id;
        if (rpcs3RootIds.contains(root.id)) _rpcs3Locations.add(canonical);
        locations.add(
          StorageLocationPath(
            rootId: root.id,
            container: location.container,
            relative: location.relative,
            path: absolute,
          ),
        );
      }
    }
    _locations = List.unmodifiable(locations);

    _buildNeverLists();

    // Containers and root directories themselves (§ 3.4, list 1).
    for (final container in StorageContainer.values) {
      final canonical = _abs(container, '');
      _exactKinds[canonical] = StorageExactMatch.container;
      _neverExact[canonical] = StorageRule(
        relative: '',
        container: container,
        category: StorageCategory.unknown,
        deletionClass: StorageDeletionClass.never,
        id: 'NEVER.container',
      );
    }
    for (final location in _locations) {
      final canonical = storageCanonicalPath(location.path);
      if (_exactKinds.containsKey(canonical)) continue;
      final regular = matchPath(location.path).rule;
      _exactKinds[canonical] = StorageExactMatch.root;
      _neverExact[canonical] = StorageRule(
        relative: location.relative,
        container: location.container,
        category: regular?.category ?? StorageCategory.unknown,
        deletionClass: StorageDeletionClass.never,
        engine: _rootsById[location.rootId]?.engine,
        id: 'NEVER.root',
      );
    }
    final marker = _abs(
      StorageContainer.applicationSupport,
      StorageLayout.dolphinActiveMarker,
    );
    _exactKinds[marker] = StorageExactMatch.marker;
    _neverExact[marker] = const StorageRule(
      relative: StorageLayout.dolphinActiveMarker,
      container: StorageContainer.applicationSupport,
      category: StorageCategory.logs,
      deletionClass: StorageDeletionClass.never,
      engine: StorageEngine.dolphin,
      id: 'NEVER.dolphinActiveMarker',
    );
  }

  void _buildNeverLists() {
    void subtree(StorageRule rule) {
      final dir = rule.absolutePath != null
          ? storageCanonicalPath(rule.absolutePath!)
          : _abs(rule.container!, rule.relative);
      _neverSubtree.putIfAbsent(dir, () => rule);
    }

    const documents = StorageContainer.documents;
    const support = StorageContainer.applicationSupport;
    const never = StorageDeletionClass.never;

    subtree(
      const StorageRule(
        relative: StorageLayout.roms,
        container: documents,
        category: StorageCategory.games,
        deletionClass: never,
        engine: StorageEngine.frontend,
        id: 'NEVER.roms',
      ),
    );
    for (final folder in libraryRoots) {
      if (folder.trim().isEmpty) continue;
      subtree(
        StorageRule(
          relative: '',
          absolutePath: p.normalize(folder.trim()),
          category: StorageCategory.games,
          deletionClass: never,
          engine: StorageEngine.frontend,
          id: 'NEVER.libraryRoot',
        ),
      );
    }
    final linked = linkedExternalFolder?.trim();
    if (linked != null && linked.isNotEmpty) {
      subtree(
        StorageRule(
          relative: '',
          absolutePath: p.normalize(linked),
          category: StorageCategory.games,
          deletionClass: never,
          engine: StorageEngine.frontend,
          id: 'NEVER.linkedFolder',
        ),
      );
    }
    subtree(
      StorageRule(
        relative: p.join(
          StorageLayout.documentsLibrary,
          LibrarySourceFiles.folderName,
        ),
        container: documents,
        category: StorageCategory.userContent,
        deletionClass: never,
        engine: StorageEngine.library,
        labelKey: 'rootLibrary',
        id: 'NEVER.libraryHidden',
        aggregateOnly: true,
      ),
    );
    _neverPatterned
        .putIfAbsent(_abs(StorageContainer.caches, ''), () => [])
        .add(
          StorageRule(
            relative: '',
            container: StorageContainer.caches,
            namePattern: RegExp(r'^NeoSwap'),
            category: StorageCategory.neoSwap,
            deletionClass: never,
            engine: StorageEngine.neoSwap,
            id: 'NEVER.neoSwap',
          ),
        );
    String rpcs3(String relative) => p.join(StorageLayout.rpcs3Data, relative);
    for (final entry in <(String, StorageCategory, String)>[
      (
        StorageLayout.rpcs3DevFlash,
        StorageCategory.systemFiles,
        'NEVER.devFlash',
      ),
      (StorageLayout.rpcs3Exdata, StorageCategory.systemFiles, 'NEVER.exdata'),
      (StorageLayout.rpcs3Savedata, StorageCategory.saves, 'NEVER.savedata'),
      (StorageLayout.rpcs3Games, StorageCategory.games, 'NEVER.rpcs3Games'),
      (
        StorageLayout.rpcs3HddGames,
        StorageCategory.games,
        'NEVER.rpcs3HddGames',
      ),
    ]) {
      subtree(
        StorageRule(
          relative: rpcs3(entry.$1),
          container: support,
          category: entry.$2,
          deletionClass: never,
          engine: StorageEngine.rpcs3,
          id: entry.$3,
        ),
      );
    }
    subtree(
      const StorageRule(
        relative: StorageLayout.libretroSystem,
        container: documents,
        category: StorageCategory.systemFiles,
        deletionClass: never,
        engine: StorageEngine.libretro,
        id: 'NEVER.libretroSystem',
      ),
    );
    subtree(
      const StorageRule(
        relative: StorageLayout.armsx2Bios,
        container: documents,
        category: StorageCategory.systemFiles,
        deletionClass: never,
        engine: StorageEngine.armsx2,
        id: 'NEVER.armsx2Bios',
      ),
    );
    subtree(
      const StorageRule(
        relative: StorageLayout.stikjit,
        container: support,
        category: StorageCategory.systemFiles,
        deletionClass: never,
        engine: StorageEngine.system,
        id: 'NEVER.stikjit',
      ),
    );

    // Names protected wherever they are (§ 3.4 list 1). The VACUUM INTO
    // backups of § 3.6 are the only exemption of `*.sqlite*`: they keep
    // their own rule (INV-02.maintenanceBackup), never proposed either
    // since the review of the storage services (backups of user data).
    StorageRule named(Pattern pattern, StorageCategory category, String id) =>
        StorageRule(
          relative: '',
          namePattern: pattern,
          category: category,
          deletionClass: never,
          id: id,
        );
    _neverNames.addAll([
      _NameNever(
        named(RegExp(r'\.sqlite'), StorageCategory.indexFiles, 'NEVER.sqlite'),
        exemptDirectory: _abs(support, StorageLayout.maintenance),
        exemptPattern: StorageLayout.maintenanceBackup,
      ),
      _NameNever(
        named('config.json', StorageCategory.indexFiles, 'NEVER.config'),
      ),
      // NSURLCache's database (`Caches/<bundle-id>/Cache.db` and its WAL):
      // open SQLite files of the system, emptied through the Library cache
      // API only (review of the storage services).
      _NameNever(
        named(
          RegExp(r'^Cache\.db(?:-wal|-shm)?$'),
          StorageCategory.caches,
          'NEVER.urlCacheDatabase',
        ),
      ),
      _NameNever(
        named(
          RegExp(r'^local-index\.json'),
          StorageCategory.indexFiles,
          'NEVER.libraryIndex',
        ),
      ),
      // The Library reading store and its sidecar of Build 447
      // (`reading-state-extra.json`), classified alike.
      _NameNever(
        named(
          RegExp(r'^reading-state(?:-extra)?\.json$'),
          StorageCategory.indexFiles,
          'NEVER.readingState',
        ),
      ),
      _NameNever(
        named('catalogs.json', StorageCategory.indexFiles, 'NEVER.catalogs'),
      ),
      _NameNever(
        named(
          'source-health.json',
          StorageCategory.indexFiles,
          'NEVER.libraryHealth',
        ),
      ),
      _NameNever(
        named('games.yml', StorageCategory.indexFiles, 'NEVER.gamesYml'),
      ),
      _NameNever(named('vfs.yml', StorageCategory.indexFiles, 'NEVER.vfsYml')),
      _NameNever(
        named(
          'SkinFavorites.json',
          StorageCategory.userContent,
          'NEVER.skinFavorites',
        ),
      ),
      _NameNever(
        named(
          StorageLayout.icloudPlaceholder,
          StorageCategory.unknown,
          'NEVER.icloud',
        ),
      ),
    ]);
  }

  List<StorageRoot> _buildRoots() {
    const documents = StorageContainer.documents;
    const support = StorageContainer.applicationSupport;
    const caches = StorageContainer.caches;
    const temporary = StorageContainer.temporary;
    const never = StorageDeletionClass.never;
    const regenerable = StorageDeletionClass.regenerableAtCost;
    const idle = StorageDeletionClass.temporaryWhenIdle;
    const confirmation = StorageDeletionClass.confirmation;
    const games = StorageCategory.games;
    const saves = StorageCategory.saves;
    const system = StorageCategory.systemFiles;
    const cache = StorageCategory.caches;
    const temp = StorageCategory.temporary;
    const logs = StorageCategory.logs;
    const user = StorageCategory.userContent;
    const index = StorageCategory.indexFiles;
    const hour = Duration(hours: 1);
    const tenMinutes = Duration(minutes: 10);

    // INV-05: the media folder (iOS `ConfigService.getMediaPath()`).
    final mediaContainer =
        containers.containerOf(mediaPath) ?? StorageContainer.documents;
    final mediaRelative =
        containers.relativePathOf(mediaPath) ?? StorageLayout.media;

    // INV-02 … INV-29; INV-01 is built last (its library folders depend on
    // the other roots) and placed first.
    final others = <StorageRoot>[
      StorageRoot(
        id: 'INV-02',
        container: documents,
        relative: StorageLayout.userData,
        labelKey: 'rootDocuments',
        engine: StorageEngine.frontend,
        additionalLocations: const [
          StorageLocation(support, StorageLayout.maintenance),
        ],
        rules: [
          const StorageRule(
            relative: StorageLayout.userData,
            namePattern: 'config.json',
            category: index,
            deletionClass: never,
            id: 'INV-02.config',
          ),
          StorageRule(
            relative: StorageLayout.userData,
            namePattern: RegExp(r'^data\.sqlite(?:-wal|-shm|-journal)?$'),
            category: index,
            deletionClass: never,
            id: 'INV-02.database',
          ),
          const StorageRule(
            relative: StorageLayout.userData,
            namePattern: 'app.log',
            category: logs,
            deletionClass: never,
            id: 'INV-02.appLog',
          ),
          const StorageRule(
            relative: StorageLayout.userData,
            namePattern: 'app.log.old',
            category: logs,
            deletionClass: confirmation,
            id: 'INV-02.appLogOld',
          ),
          // The copies of data.sqlite made before a metadata deletion:
          // backups of user data, never proposed (review of the storage
          // services; § 3.7 offered them at level 3). The repository keeps
          // its three newest itself.
          StorageRule(
            relative: StorageLayout.maintenance,
            container: support,
            namePattern: StorageLayout.maintenanceBackup,
            category: user,
            deletionClass: never,
            id: 'INV-02.maintenanceBackup',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-03',
        container: documents,
        relative: StorageLayout.userDataTemp,
        labelKey: 'rootDocuments',
        engine: StorageEngine.frontend,
        rules: [
          StorageRule(
            relative: StorageLayout.userDataTemp,
            category: temp,
            deletionClass: idle,
            id: 'INV-03.archiveTemp',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-04',
        container: documents,
        relative: 'user-data/themes',
        labelKey: 'rootDocuments',
        engine: StorageEngine.frontend,
        additionalLocations: const [
          StorageLocation(documents, 'user-data/systems'),
          StorageLocation(documents, 'user-data/media/systems'),
          StorageLocation(documents, 'user-data/menu_music'),
        ],
        rules: [
          const StorageRule(
            relative: 'user-data/themes',
            category: user,
            deletionClass: never,
            id: 'INV-04.themes',
          ),
          const StorageRule(
            relative: 'user-data/systems',
            category: cache,
            deletionClass: never,
            id: 'INV-04.systems',
          ),
          const StorageRule(
            relative: 'user-data/media/systems',
            category: cache,
            deletionClass: never,
            id: 'INV-04.systemMedia',
          ),
          const StorageRule(
            relative: 'user-data/menu_music',
            category: user,
            deletionClass: never,
            id: 'INV-04.menuMusic',
          ),
          StorageRule(
            relative: StorageLayout.userData,
            namePattern: RegExp(r'^background\.[A-Za-z0-9]+$'),
            category: user,
            deletionClass: never,
            id: 'INV-04.background',
          ),
          StorageRule(
            relative: StorageLayout.userData,
            namePattern: RegExp(r'^background\.importing'),
            category: temp,
            deletionClass: idle,
            id: 'INV-04.backgroundImporting',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-05',
        container: mediaContainer,
        relative: mediaRelative,
        labelKey: _containerLabel(mediaContainer),
        engine: StorageEngine.frontend,
        rules: [
          StorageRule(
            relative: mediaRelative,
            category: StorageCategory.media,
            deletionClass: regenerable,
            orphanAnchor: StorageOrphanAnchor.media,
            id: 'INV-05.media',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-06',
        container: documents,
        relative: StorageLayout.diagnostics,
        labelKey: 'rootDocuments',
        engine: StorageEngine.frontend,
        rules: [
          StorageRule(
            relative: StorageLayout.diagnostics,
            category: logs,
            deletionClass: confirmation,
            id: 'INV-06.diagnostics',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-07',
        container: documents,
        relative: '',
        labelKey: 'rootDocuments',
        engine: StorageEngine.frontend,
        rules: [
          StorageRule(
            relative: '',
            namePattern: RegExp(r'^NeoPlay\.jsonl(?:\.previous)?$'),
            category: logs,
            deletionClass: confirmation,
            engine: StorageEngine.frontend,
            id: 'INV-07.neoPlayLog',
          ),
          const StorageRule(
            relative: '',
            namePattern: 'armsx2_jit_debug.log',
            category: logs,
            deletionClass: confirmation,
            engine: StorageEngine.armsx2,
            id: 'INV-07.armsx2JitLog',
          ),
          const StorageRule(
            relative: '',
            namePattern: 'RPCS3-core-load-stderr.log',
            category: logs,
            deletionClass: confirmation,
            engine: StorageEngine.rpcs3,
            id: 'INV-07.rpcs3LoadLog',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-08',
        container: documents,
        relative: 'Recordings',
        labelKey: 'rootDocuments',
        engine: StorageEngine.dolphin,
        rules: [
          StorageRule(
            relative: StorageLayout.dolphinRecordings,
            namePattern: RegExp(r'\.mp4$', caseSensitive: false),
            category: user,
            deletionClass: confirmation,
            engine: StorageEngine.dolphin,
            id: 'INV-08.recording',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-09',
        container: documents,
        relative: 'Dolphin',
        labelKey: 'rootDocuments',
        engine: StorageEngine.dolphin,
        rules: [
          StorageRule(
            relative: 'Dolphin',
            category: system,
            deletionClass: never,
            engine: StorageEngine.dolphin,
            id: 'INV-09.systemExchange',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-10',
        container: documents,
        relative: StorageLayout.rpcs3Workspace,
        labelKey: 'rootDocuments',
        engine: StorageEngine.rpcs3,
        rules: [
          const StorageRule(
            relative: StorageLayout.rpcs3Workspace,
            category: user,
            deletionClass: never,
            engine: StorageEngine.rpcs3,
            id: 'INV-10.workspace',
          ),
          StorageRule(
            relative: StorageLayout.rpcs3ExportSaves,
            namePattern: RegExp(r'^[^.].*\.zip$', caseSensitive: false),
            category: user,
            deletionClass: confirmation,
            engine: StorageEngine.rpcs3,
            id: 'INV-10.exportZip',
          ),
          StorageRule(
            relative: StorageLayout.rpcs3ExportSaves,
            namePattern: RegExp(r'^\..+\.zip\.part$', caseSensitive: false),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.rpcs3,
            minimumAge: hour,
            id: 'INV-10.exportPart',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-11',
        container: documents,
        relative: StorageLayout.armsx2,
        labelKey: 'rootDocuments',
        engine: StorageEngine.armsx2,
        rules: [
          StorageRule(
            relative: StorageLayout.armsx2Games,
            category: games,
            deletionClass: never,
            engine: StorageEngine.armsx2,
            orphanAnchor: StorageOrphanAnchor.gameCopy,
            id: 'INV-11.games',
          ),
          StorageRule(
            relative: StorageLayout.armsx2Bios,
            category: system,
            deletionClass: never,
            engine: StorageEngine.armsx2,
            id: 'INV-11.bios',
          ),
          StorageRule(
            relative: 'ARMSX2/Saves',
            category: saves,
            deletionClass: never,
            engine: StorageEngine.armsx2,
            id: 'INV-11.saves',
          ),
          StorageRule(
            relative: StorageLayout.armsx2Savestates,
            category: saves,
            deletionClass: never,
            engine: StorageEngine.armsx2,
            orphanAnchor: StorageOrphanAnchor.armsx2Savestate,
            id: 'INV-11.savestates',
          ),
          StorageRule(
            relative: 'ARMSX2/cheats',
            category: user,
            deletionClass: never,
            engine: StorageEngine.armsx2,
            id: 'INV-11.cheats',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-12',
        container: documents,
        relative: StorageLayout.kartpad,
        labelKey: 'rootDocuments',
        engine: StorageEngine.kartpad,
        additionalLocations: const [
          StorageLocation(support, StorageLayout.kartpadSupport),
          // getTemporaryDirectory()/KartPad: Library/Caches on iOS.
          StorageLocation(caches, 'KartPad'),
        ],
        rules: [
          ..._portRules('Ports/KartPad', 'INV-12', StorageEngine.kartpad),
          const StorageRule(
            relative: StorageLayout.kartpadGameData,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.kartpad,
            id: 'INV-12.gameData',
          ),
          StorageRule(
            relative: 'Ports/KartPad/Runtime',
            namePattern: RegExp(r'^GameData\.(?:import|rollback)-'),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.kartpad,
            id: 'INV-12.gameDataStaging',
          ),
          const StorageRule(
            relative: StorageLayout.kartpadLogs,
            category: logs,
            deletionClass: regenerable,
            engine: StorageEngine.kartpad,
            id: 'INV-12.logs',
          ),
          const StorageRule(
            relative: StorageLayout.kartpadSupport,
            container: support,
            category: saves,
            deletionClass: never,
            engine: StorageEngine.kartpad,
            id: 'INV-12.supportLinks',
          ),
          const StorageRule(
            relative: 'KartPad',
            container: caches,
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.kartpad,
            id: 'INV-12.cache',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-13',
        container: documents,
        relative: StorageLayout.dusklight,
        labelKey: 'rootDocuments',
        engine: StorageEngine.dusklight,
        additionalLocations: const [StorageLocation(caches, 'Dusklight')],
        rules: [
          ..._portRules('Ports/Dusklight', 'INV-13', StorageEngine.dusklight),
          const StorageRule(
            relative: 'Dusklight',
            container: caches,
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.dusklight,
            id: 'INV-13.cache',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-14',
        container: documents,
        relative: StorageLayout.libretro,
        labelKey: 'rootDocuments',
        engine: StorageEngine.libretro,
        rules: [
          const StorageRule(
            relative: StorageLayout.libretroSystem,
            category: system,
            deletionClass: never,
            engine: StorageEngine.libretro,
            id: 'INV-14.system',
          ),
          const StorageRule(
            relative: StorageLayout.libretroSaves,
            category: saves,
            deletionClass: never,
            engine: StorageEngine.libretro,
            orphanAnchor: StorageOrphanAnchor.libretroSave,
            id: 'INV-14.saves',
          ),
          const StorageRule(
            relative: StorageLayout.libretroStates,
            category: saves,
            deletionClass: never,
            engine: StorageEngine.libretro,
            orphanAnchor: StorageOrphanAnchor.libretroState,
            id: 'INV-14.states',
          ),
          const StorageRule(
            relative: 'Libretro/Config',
            category: user,
            deletionClass: never,
            engine: StorageEngine.libretro,
            id: 'INV-14.config',
          ),
          const StorageRule(
            relative: 'Libretro/Cheats',
            category: user,
            deletionClass: never,
            engine: StorageEngine.libretro,
            id: 'INV-14.cheats',
          ),
          const StorageRule(
            relative: StorageLayout.libretroSkins,
            category: user,
            deletionClass: never,
            engine: StorageEngine.libretro,
            id: 'INV-14.skins',
          ),
          const StorageRule(
            relative: StorageLayout.libretroSkinStaging,
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.libretro,
            minimumAge: hour,
            id: 'INV-14.skinStaging',
          ),
          const StorageRule(
            relative: StorageLayout.libretro,
            namePattern: 'SkinFavorites.json',
            category: user,
            deletionClass: never,
            engine: StorageEngine.libretro,
            id: 'INV-14.skinFavorites',
          ),
          const StorageRule(
            relative: StorageLayout.libretroLogs,
            category: logs,
            deletionClass: confirmation,
            engine: StorageEngine.libretro,
            id: 'INV-14.logs',
          ),
          // Nintendo 3DS system data (chantier 2): backups of replaced
          // files — they may hold console-unique files, never proposed
          // (review of the storage services; level 3 before) — and the
          // staging folders an interrupted import or restore leaves beside
          // the user directory. Everything else under Saves/Azahar stays
          // never (NAND, sysdata).
          const StorageRule(
            relative: StorageLayout.libretro3dsBackups,
            category: user,
            deletionClass: never,
            engine: StorageEngine.libretro,
            id: 'INV-14.3dsBackups',
          ),
          StorageRule(
            relative: StorageLayout.libretro3dsSaves,
            namePattern: RegExp(
              '^(?:${RegExp.escape(Libretro3dsSystemDataService.stagingPrefix)}'
              '|${RegExp.escape(Libretro3dsSystemDataService.restoreStagingPrefix)})',
            ),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.libretro,
            id: 'INV-14.3dsStaging',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-15',
        container: documents,
        relative: StorageLayout.documentsLibrary,
        labelKey: 'rootLibrary',
        engine: StorageEngine.library,
        rules: [
          const StorageRule(
            relative: 'Library/Books',
            category: user,
            deletionClass: never,
            engine: StorageEngine.library,
            id: 'INV-15.books',
          ),
          const StorageRule(
            relative: 'Library/Downloads',
            category: user,
            deletionClass: never,
            engine: StorageEngine.library,
            id: 'INV-15.downloads',
          ),
          StorageRule(
            relative: 'Library/Books',
            namePattern: RegExp(r'^\.import-[0-9A-Fa-f]+\.part$'),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.library,
            minimumAge: hour,
            id: 'INV-15.importPart',
          ),
          StorageRule(
            relative: p.join(
              StorageLayout.documentsLibrary,
              LibrarySourceFiles.folderName,
            ),
            category: user,
            deletionClass: never,
            engine: StorageEngine.library,
            labelKey: 'rootLibrary',
            aggregateOnly: true,
            id: 'INV-15.hidden',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-16',
        container: support,
        relative: StorageLayout.rpcs3Data,
        labelKey: 'rootSupport',
        engine: StorageEngine.rpcs3,
        rules: [..._rpcs3DataRules()],
      ),
      StorageRoot(
        id: 'INV-17',
        container: support,
        relative: p.join(StorageLayout.rpcs3Data, StorageLayout.rpcs3Hdd1),
        labelKey: 'rootSupport',
        engine: StorageEngine.rpcs3,
        additionalLocations: [
          for (final name in const [
            'dev_usb000',
            'dev_bdvd',
            'dev_flash2',
            'dev_flash3',
          ])
            StorageLocation(support, p.join(StorageLayout.rpcs3Data, name)),
        ],
        rules: [
          StorageRule(
            relative: p.join(StorageLayout.rpcs3Data, StorageLayout.rpcs3Hdd1),
            category: cache,
            deletionClass: confirmation,
            engine: StorageEngine.rpcs3,
            id: 'INV-17.hdd1',
          ),
          for (final entry in const <(String, StorageCategory, String)>[
            ('dev_usb000', StorageCategory.games, 'INV-17.usb'),
            ('dev_bdvd', StorageCategory.games, 'INV-17.bdvd'),
            ('dev_flash2', StorageCategory.systemFiles, 'INV-17.flash2'),
            ('dev_flash3', StorageCategory.systemFiles, 'INV-17.flash3'),
          ])
            StorageRule(
              relative: p.join(StorageLayout.rpcs3Data, entry.$1),
              category: entry.$2,
              deletionClass: never,
              engine: StorageEngine.rpcs3,
              id: entry.$3,
            ),
        ],
      ),
      const StorageRoot(
        id: 'INV-18',
        container: support,
        relative: StorageLayout.rpcs3Cache,
        labelKey: 'rootSupport',
        engine: StorageEngine.rpcs3,
        rules: [
          StorageRule(
            relative: StorageLayout.rpcs3Cache,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.rpcs3,
            id: 'INV-18.cache',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-19',
        container: support,
        relative: StorageLayout.rpcs3Imports,
        labelKey: 'rootSupport',
        engine: StorageEngine.rpcs3,
        additionalLocations: const [
          StorageLocation(support, StorageLayout.rpcs3SaveBackups),
          StorageLocation(support, StorageLayout.rpcs3RapBackups),
        ],
        rules: [
          StorageRule(
            relative: StorageLayout.rpcs3Imports,
            namePattern: RegExp(r'^PS3UPDAT-.*\.PUP$', caseSensitive: false),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.rpcs3,
            minimumAge: hour,
            id: 'INV-19.firmwareImport',
          ),
          // The saves and licences a replacement moved aside: backups of
          // user data, never proposed (review of the storage services;
          // level 3 before).
          const StorageRule(
            relative: StorageLayout.rpcs3SaveBackups,
            category: user,
            deletionClass: never,
            engine: StorageEngine.rpcs3,
            id: 'INV-19.saveBackups',
          ),
          const StorageRule(
            relative: StorageLayout.rpcs3RapBackups,
            category: user,
            deletionClass: never,
            engine: StorageEngine.rpcs3,
            id: 'INV-19.rapBackups',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-20',
        container: support,
        relative: StorageLayout.dolphinLibrary,
        labelKey: 'rootSupport',
        engine: StorageEngine.dolphin,
        rules: [
          StorageRule(
            relative: StorageLayout.dolphinLibrary,
            category: games,
            deletionClass: never,
            engine: StorageEngine.dolphin,
            orphanAnchor: StorageOrphanAnchor.gameCopy,
            id: 'INV-20.library',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-21',
        container: support,
        relative: StorageLayout.dolphin,
        labelKey: 'rootSupport',
        engine: StorageEngine.dolphin,
        rules: [
          for (final entry
              in const <
                (String, StorageCategory, StorageOrphanAnchor?, String)
              >[
                (
                  'User/Config',
                  StorageCategory.userContent,
                  null,
                  'INV-21.config',
                ),
                ('User/GC', StorageCategory.saves, null, 'INV-21.gc'),
                ('User/Wii', StorageCategory.systemFiles, null, 'INV-21.wii'),
                (
                  'User/StateSaves',
                  StorageCategory.saves,
                  StorageOrphanAnchor.dolphinState,
                  'INV-21.states',
                ),
                ('User/Load', StorageCategory.userContent, null, 'INV-21.load'),
                ('User/Dump', StorageCategory.userContent, null, 'INV-21.dump'),
                (
                  'User/GameSettings',
                  StorageCategory.userContent,
                  null,
                  'INV-21.gameSettings',
                ),
                ('Saves', StorageCategory.saves, null, 'INV-21.saves'),
                (
                  'Metadata',
                  StorageCategory.systemFiles,
                  null,
                  'INV-21.metadata',
                ),
              ])
            StorageRule(
              relative: p.join(StorageLayout.dolphin, entry.$1),
              category: entry.$2,
              deletionClass: never,
              engine: StorageEngine.dolphin,
              orphanAnchor: entry.$3,
              id: entry.$4,
            ),
          const StorageRule(
            relative: StorageLayout.dolphinShaderCache,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.dolphin,
            id: 'INV-21.shaderCache',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-22',
        container: support,
        relative: StorageLayout.dolphinLogs,
        labelKey: 'rootSupport',
        engine: StorageEngine.dolphin,
        additionalLocations: const [
          StorageLocation(support, StorageLayout.dolphinCrashMarkers),
        ],
        rules: [
          StorageRule(
            relative: StorageLayout.dolphinLogs,
            namePattern: RegExp(r'^dolphin-\d{4}-\d{2}-\d{2}T.*\.jsonl$'),
            category: logs,
            deletionClass: regenerable,
            engine: StorageEngine.dolphin,
            id: 'INV-22.sessionLog',
          ),
          StorageRule(
            relative: StorageLayout.dolphinLogs,
            namePattern: RegExp(r'^dolphin-persistent\.jsonl(?:\.old)?$'),
            category: logs,
            deletionClass: confirmation,
            engine: StorageEngine.dolphin,
            id: 'INV-22.persistentLog',
          ),
          const StorageRule(
            relative: StorageLayout.dolphinCrashMarkers,
            namePattern: 'active-session.json',
            category: logs,
            deletionClass: never,
            engine: StorageEngine.dolphin,
            id: 'INV-22.activeMarker',
          ),
          StorageRule(
            relative: StorageLayout.dolphinCrashMarkers,
            namePattern: RegExp(r'^active-session\.json\.\d+\.recovered$'),
            category: logs,
            deletionClass: regenerable,
            engine: StorageEngine.dolphin,
            id: 'INV-22.recoveredMarker',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-23',
        container: support,
        relative: StorageLayout.supportLibrary,
        labelKey: 'rootLibrary',
        engine: StorageEngine.library,
        rules: [
          StorageRule(
            relative: StorageLayout.supportLibrary,
            // Their atomic-write `.tmp` and kept `.corrupt` copies too
            // (prefix match), the reading store's sidecar included.
            namePattern: RegExp(
              r'^(?:local-index|catalogs|source-health|reading-state(?:-extra)?)\.json',
            ),
            category: index,
            deletionClass: never,
            engine: StorageEngine.library,
            id: 'INV-23.index',
          ),
          const StorageRule(
            relative: StorageLayout.libraryCovers,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.library,
            orphanAnchor: StorageOrphanAnchor.libraryCover,
            id: 'INV-23.covers',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-24',
        container: support,
        relative: StorageLayout.stikjit,
        labelKey: 'rootSupport',
        engine: StorageEngine.system,
        rules: [
          StorageRule(
            relative: StorageLayout.stikjit,
            category: system,
            deletionClass: never,
            engine: StorageEngine.system,
            id: 'INV-24.pairing',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-25',
        container: caches,
        relative: StorageLayout.libretroCaches,
        labelKey: 'rootCaches',
        engine: StorageEngine.libretro,
        rules: [
          for (final entry in const <(String, String)>[
            ('Libretro/SkinCache', 'INV-25.skinCache'),
            ('Libretro/SkinDownloads', 'INV-25.skinDownloads'),
            ('Libretro/SkinInspection', 'INV-25.skinInspection'),
          ])
            StorageRule(
              relative: entry.$1,
              category: cache,
              deletionClass: regenerable,
              engine: StorageEngine.libretro,
              id: entry.$2,
            ),
          StorageRule(
            relative: StorageLayout.libretroCaches,
            namePattern: RegExp(
              r'^(?:skin-catalog|skin-verdicts|bios-check-v1)\.json$',
            ),
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.libretro,
            id: 'INV-25.catalogs',
          ),
          const StorageRule(
            relative: StorageLayout.libretroContent,
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.libretro,
            id: 'INV-25.content',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-26',
        container: caches,
        relative: StorageLayout.libraryCaches,
        labelKey: 'rootLibrary',
        engine: StorageEngine.library,
        rules: [
          StorageRule(
            relative: StorageLayout.libraryHttpCache,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.library,
            id: 'INV-26.http',
          ),
          StorageRule(
            relative: StorageLayout.libraryImageCache,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.library,
            id: 'INV-26.images',
          ),
        ],
      ),
      const StorageRoot(
        id: 'INV-27',
        container: caches,
        relative: 'NeoSwap-v1',
        labelKey: 'rootCaches',
        engine: StorageEngine.neoSwap,
        hidden: true,
        additionalLocations: [
          StorageLocation(caches, 'NeoSwapShaderStorage-v1'),
        ],
        rules: [
          StorageRule(
            relative: 'NeoSwap-v1',
            category: StorageCategory.neoSwap,
            deletionClass: never,
            engine: StorageEngine.neoSwap,
            id: 'INV-27.swap',
          ),
          StorageRule(
            relative: 'NeoSwapShaderStorage-v1',
            category: StorageCategory.neoSwap,
            deletionClass: never,
            engine: StorageEngine.neoSwap,
            id: 'INV-27.shaders',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-28',
        container: temporary,
        relative: '',
        labelKey: 'rootTemporary',
        engine: StorageEngine.system,
        additionalLocations: const [
          // SfxService: getTemporaryDirectory() is Library/Caches on iOS.
          StorageLocation(caches, 'SoLoudLoader-Temp-Files'),
        ],
        rules: [
          // Picker copies (regular files directly in tmp/) and everything
          // else in tmp/: temporary, never before 10 minutes.
          const StorageRule(
            relative: '',
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.frontend,
            minimumAge: tenMinutes,
            id: 'INV-28.temporary',
          ),
          // `tmp/<bundle-id>-Inbox` (system copy of each pick, iOS name to be
          // confirmed on the device): any `*-Inbox` folder.
          StorageRule(
            relative: '',
            namePattern: RegExp(r'-Inbox$'),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.frontend,
            minimumAge: tenMinutes,
            id: 'INV-28.pickerInbox',
          ),
          const StorageRule(
            relative: '',
            namePattern: StorageLayout.framePacing,
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.dolphin,
            id: 'INV-28.framePacing',
          ),
          // Staged download of the ARMSX2 shader pack (NSTemporaryDirectory).
          StorageRule(
            relative: '',
            namePattern: RegExp(r'^armsx2-shaders-.*\.zip$'),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.armsx2,
            id: 'INV-28.armsx2Shaders',
          ),
          // The inventory's tmp/KartPad, tmp/Dusklight and
          // tmp/SoLoudLoader-Temp-Files come from getTemporaryDirectory():
          // Library/Caches on iOS (INV-12, INV-13 and the rule below).
          const StorageRule(
            relative: 'SoLoudLoader-Temp-Files',
            container: caches,
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.frontend,
            id: 'INV-28.soloudCache',
          ),
          // MusicPlayerService metadata copies (getTemporaryDirectory()).
          StorageRule(
            relative: '',
            container: caches,
            namePattern: RegExp(
              r'^(?:scan_-?\d+|temp_music_track)\.[^.]{1,5}$',
            ),
            category: temp,
            deletionClass: idle,
            engine: StorageEngine.frontend,
            minimumAge: tenMinutes,
            id: 'INV-28.musicCopy',
          ),
        ],
      ),
      StorageRoot(
        id: 'INV-29',
        container: support,
        relative: '',
        labelKey: 'rootSupport',
        engine: StorageEngine.system,
        additionalLocations: const [StorageLocation(caches, '')],
        rules: [
          StorageRule(
            relative: '',
            namePattern: RegExp(r'^.+_[0-9A-Fa-f]{16,}\.ttf$'),
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.frontend,
            id: 'INV-29.fonts',
          ),
          StorageRule(
            relative: '',
            container: caches,
            namePattern: bundleIdentifier == null
                ? defaultBundlePattern
                : bundleIdentifier!,
            category: cache,
            deletionClass: regenerable,
            engine: StorageEngine.system,
            id: 'INV-29.urlCache',
          ),
        ],
      ),
    ];

    // INV-01: library folders measured here only inside a container and
    // outside every other (non-container) root directory; protected
    // everywhere by the never-list.
    final otherLocations = <String>[
      for (final root in others)
        for (final location in root.locations)
          if (location.relative.isNotEmpty)
            _abs(location.container, location.relative),
    ];
    final measured = <String>[_abs(documents, StorageLayout.roms)];
    final libraryLocations = <StorageLocation>[];
    final libraryRules = <StorageRule>[
      const StorageRule(
        relative: StorageLayout.roms,
        category: games,
        deletionClass: never,
        engine: StorageEngine.frontend,
        orphanAnchor: StorageOrphanAnchor.gameCopy,
        id: 'INV-01.roms',
      ),
    ];
    for (final (folder, id) in [
      for (final folder in libraryRoots) (folder, 'INV-01.library'),
      if (linkedExternalFolder != null)
        (linkedExternalFolder!, 'INV-01.linked'),
    ]) {
      final trimmed = folder.trim();
      if (trimmed.isEmpty) continue;
      final container = containers.containerOf(trimmed);
      final relative = containers.relativePathOf(trimmed);
      if (container == null || relative == null || relative.isEmpty) continue;
      final canonical = _abs(container, relative);
      bool covered(String other) =>
          other == canonical || p.isWithin(other, canonical);
      if (otherLocations.any(covered) || measured.any(covered)) continue;
      measured.add(canonical);
      libraryLocations.add(StorageLocation(container, relative));
      libraryRules.add(
        StorageRule(
          relative: relative,
          container: container,
          category: games,
          deletionClass: never,
          engine: StorageEngine.frontend,
          orphanAnchor: StorageOrphanAnchor.gameCopy,
          id: id,
        ),
      );
    }
    return List.unmodifiable([
      StorageRoot(
        id: 'INV-01',
        container: documents,
        relative: StorageLayout.roms,
        labelKey: 'rootDocuments',
        engine: StorageEngine.frontend,
        rules: List.unmodifiable(libraryRules),
        additionalLocations: List.unmodifiable(libraryLocations),
      ),
      ...others,
    ]);
  }

  static String _containerLabel(StorageContainer container) =>
      switch (container) {
        StorageContainer.documents => 'rootDocuments',
        StorageContainer.applicationSupport => 'rootSupport',
        StorageContainer.caches => 'rootCaches',
        StorageContainer.temporary => 'rootTemporary',
      };

  static List<StorageRule> _portRules(
    String base,
    String root,
    StorageEngine engine,
  ) => [
    StorageRule(
      relative: '$base/Games',
      category: StorageCategory.games,
      deletionClass: StorageDeletionClass.never,
      engine: engine,
      orphanAnchor: StorageOrphanAnchor.gameCopy,
      id: '$root.games',
    ),
    StorageRule(
      relative: '$base/Games',
      namePattern: RegExp(r'\.part$'),
      category: StorageCategory.temporary,
      deletionClass: StorageDeletionClass.temporaryWhenIdle,
      engine: engine,
      minimumAge: const Duration(hours: 1),
      id: '$root.gamePart',
    ),
    StorageRule(
      relative: '$base/Saves',
      category: StorageCategory.saves,
      deletionClass: StorageDeletionClass.never,
      engine: engine,
      id: '$root.saves',
    ),
    for (final folder in const ['Config', 'Mods', 'Metadata'])
      StorageRule(
        relative: '$base/$folder',
        category: StorageCategory.userContent,
        deletionClass: StorageDeletionClass.never,
        engine: engine,
        id: '$root.${folder.toLowerCase()}',
      ),
  ];

  static List<StorageRule> _rpcs3DataRules() {
    String data(String relative) => p.join(StorageLayout.rpcs3Data, relative);
    const rpcs3 = StorageEngine.rpcs3;
    const never = StorageDeletionClass.never;
    return [
      StorageRule(
        relative: data(StorageLayout.rpcs3HddGames),
        category: StorageCategory.games,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.hddGames',
      ),
      StorageRule(
        relative: data(StorageLayout.rpcs3Games),
        category: StorageCategory.games,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.games',
      ),
      StorageRule(
        relative: data('dev_hdd0/home'),
        category: StorageCategory.saves,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.home',
      ),
      StorageRule(
        relative: data(StorageLayout.rpcs3Savedata),
        category: StorageCategory.saves,
        deletionClass: never,
        engine: rpcs3,
        orphanAnchor: StorageOrphanAnchor.rpcs3Savedata,
        id: 'INV-16.savedata',
      ),
      StorageRule(
        relative: data(StorageLayout.rpcs3Exdata),
        category: StorageCategory.systemFiles,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.exdata',
      ),
      StorageRule(
        relative: data(StorageLayout.rpcs3UserHome),
        namePattern: RegExp(r'^\.neostation-save-import-'),
        category: StorageCategory.temporary,
        deletionClass: StorageDeletionClass.temporaryWhenIdle,
        engine: rpcs3,
        id: 'INV-16.saveImportStaging',
      ),
      StorageRule(
        relative: data(StorageLayout.rpcs3DevFlash),
        category: StorageCategory.systemFiles,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.devFlash',
      ),
      StorageRule(
        relative: data('savestates'),
        category: StorageCategory.saves,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.savestates',
      ),
      StorageRule(
        relative: data(StorageLayout.rpcs3HddTmp),
        category: StorageCategory.temporary,
        deletionClass: StorageDeletionClass.temporaryWhenIdle,
        engine: rpcs3,
        id: 'INV-16.hddTmp',
      ),
      StorageRule(
        relative: data('Icons'),
        category: StorageCategory.caches,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.icons',
      ),
      StorageRule(
        relative: StorageLayout.rpcs3Data,
        namePattern: RegExp(r'^(?:games|vfs)\.yml$'),
        category: StorageCategory.indexFiles,
        deletionClass: never,
        engine: rpcs3,
        id: 'INV-16.configuration',
      ),
    ];
  }
}
