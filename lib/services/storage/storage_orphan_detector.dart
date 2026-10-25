/// Read-only detection of orphans and duplicates
/// (docs/storage-audit-cleanup.md § 3.5). Never deletes anything: media and
/// library covers become level-2 candidates of the planner, metadata keys go
/// through [StorageMaintenanceRepository], saves and states are listed for
/// information only, duplicates are listed with the one copy a level-3
/// cleanup may offer.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

import '../../data/datasources/sqlite_service.dart';
import '../../providers/file_provider.dart';
import '../rpcs3_library_service.dart';
import 'storage_roots.dart';
import 'storage_scanner.dart';

/// Orphan metadata rows: the LEFT JOIN of § 3.5 on
/// `UNIQUE(app_system_id, filename)` (`sqlite_service.dart:1894`), of the
/// systems that still have at least one game row (review of the storage
/// services: a system without any row — its library folder unreadable and
/// its rows pruned by a scan — is not evidence that its metadata is
/// orphan; [storageMetadataSystemsWithoutGamesQuery] lists them).
const String storageOrphanMetadataQuery =
    'SELECT m.app_system_id, m.filename '
    'FROM user_screenscraper_metadata m '
    'LEFT JOIN user_roms r ON r.app_system_id = m.app_system_id '
    'AND r.filename = m.filename '
    'WHERE r.filename IS NULL '
    'AND EXISTS (SELECT 1 FROM user_roms s '
    'WHERE s.app_system_id = m.app_system_id) '
    'ORDER BY 1, 2';

/// Systems holding metadata rows but no game row: their metadata is not
/// analysed.
const String storageMetadataSystemsWithoutGamesQuery =
    'SELECT DISTINCT m.app_system_id FROM user_screenscraper_metadata m '
    'WHERE NOT EXISTS (SELECT 1 FROM user_roms s '
    'WHERE s.app_system_id = m.app_system_id) '
    'ORDER BY 1';

/// Key of one `user_screenscraper_metadata` row.
class StorageOrphanMetadataKey {
  const StorageOrphanMetadataKey(this.appSystemId, this.filename);

  final String appSystemId;
  final String filename;

  @override
  bool operator ==(Object other) =>
      other is StorageOrphanMetadataKey &&
      other.appSystemId == appSystemId &&
      other.filename == filename;

  @override
  int get hashCode => Object.hash(appSystemId, filename);

  @override
  String toString() => 'StorageOrphanMetadataKey($appSystemId, $filename)';
}

/// Family of an orphan entry.
enum StorageOrphanKind {
  /// Scraped media no game of its system matches (level 2).
  media,

  /// Media of a folder that is no system of `app_systems` (never).
  unattributedMedia,

  /// Library cover absent from `local-index.json` (level 2).
  libraryCover,

  /// Information only, never deletable.
  libretroSave,
  libretroState,
  dolphinState,
  rpcs3Savedata,
  armsx2Savestate,
}

/// One file (or save folder) found orphan.
class StorageOrphanEntry {
  const StorageOrphanEntry({
    required this.kind,
    required this.path,
    required this.relativePath,
    required this.container,
    required this.rootId,
    required this.entryKind,
    required this.logicalBytes,
    this.allocatedBytes,
    required this.modified,
    required this.category,
    required this.deletionClass,
    this.ruleId,
    required this.key,
    this.group,
    required this.selectable,
  });

  final StorageOrphanKind kind;

  /// Absolute path, as scanned.
  final String path;

  /// Relative to [container].
  final String relativePath;
  final StorageContainer container;
  final String rootId;
  final StorageEntryKind entryKind;
  final int logicalBytes;
  final int? allocatedBytes;
  final DateTime modified;
  final StorageCategory category;
  final StorageDeletionClass deletionClass;
  final String? ruleId;

  /// What was matched: media base name, book id, save radical, PS3 title
  /// ID, PS2 serial, state file name.
  final String key;

  /// System folder (media), core folder (libretro), save folder (RPCS3).
  final String? group;

  /// May become a cleanup candidate (media and covers whose class is not
  /// never); always false for saves and states.
  final bool selectable;

  String get displayPath {
    final placeholder = StorageContainers.placeholderOf(container);
    return relativePath.isEmpty ? placeholder : '$placeholder/$relativePath';
  }

  @override
  String toString() => 'StorageOrphanEntry(${kind.name}, $displayPath)';
}

/// Why a duplicate copy cannot be offered.
enum StorageDuplicateKeep {
  /// `user_roms.rom_path` points to it (« référencée par la bibliothèque »).
  referenced,

  /// No copy of the group is referenced: none is offered.
  noReferencedCopy,

  /// A descriptor (`.cue`, `.gdi`, `.m3u`, …) beside or above it may use it.
  companionFiles,

  /// The SHA-256 differs from the other copies (hashing requested).
  differentContent,

  /// The checksums were not computed: the same name and size do not prove
  /// the same content (review of the storage services), nothing is offered.
  notHashed,
}

/// One copy of a duplicate group.
class StorageDuplicateCopy {
  const StorageDuplicateCopy({
    required this.path,
    required this.relativePath,
    required this.container,
    required this.rootId,
    required this.logicalBytes,
    this.allocatedBytes,
    required this.modified,
    required this.referenced,
    required this.selectable,
    this.keep,
    this.sha256,
  });

  final String path;
  final String relativePath;
  final StorageContainer container;
  final String rootId;
  final int logicalBytes;
  final int? allocatedBytes;
  final DateTime modified;

  /// `user_roms.rom_path` designates this copy.
  final bool referenced;

  /// The only copies a level-3 cleanup may offer (never preselected): not
  /// referenced, not a companion of a descriptor, in a group where another
  /// copy is referenced, with the same SHA-256 as the referenced copy (the
  /// checksums computed: review of the storage services). Every copy lies
  /// in a never-class game folder (`isProtected` is true); this flag is the
  /// only exception of § 3.7.
  final bool selectable;

  /// Why it is not [selectable] (null when it is).
  final StorageDuplicateKeep? keep;

  /// Lower-case hex SHA-256 when hashing was requested.
  final String? sha256;

  String get displayPath {
    final placeholder = StorageContainers.placeholderOf(container);
    return relativePath.isEmpty ? placeholder : '$placeholder/$relativePath';
  }
}

/// Copies sharing a file name and a size (`neostation_rom_library.dart`),
/// and the same SHA-256 when [hashed].
class StorageDuplicateGroup {
  const StorageDuplicateGroup({
    required this.name,
    required this.size,
    required this.copies,
    this.hashed = false,
    this.sha256,
  });

  final String name;
  final int size;
  final List<StorageDuplicateCopy> copies;
  final bool hashed;
  final String? sha256;

  /// Logical bytes of the copies a cleanup may offer.
  int get selectableBytes => copies
      .where((copy) => copy.selectable)
      .fold(0, (sum, copy) => sum + copy.logicalBytes);
}

class StorageOrphanReport {
  const StorageOrphanReport({
    this.media = const [],
    this.libraryCovers = const [],
    this.metadata = const [],
    this.libretroSaves = const [],
    this.libretroStates = const [],
    this.dolphinStates = const [],
    this.rpcs3Savedata = const [],
    this.armsx2Savestates = const [],
    this.duplicates = const [],
    this.unattributedMedia = const [],
    this.skipped = const {},
    this.cancelled = false,
  });

  final List<StorageOrphanEntry> media;
  final List<StorageOrphanEntry> libraryCovers;
  final List<StorageOrphanMetadataKey> metadata;

  /// Listed, never deletable.
  final List<StorageOrphanEntry> libretroSaves;
  final List<StorageOrphanEntry> libretroStates;
  final List<StorageOrphanEntry> dolphinStates;
  final List<StorageOrphanEntry> rpcs3Savedata;
  final List<StorageOrphanEntry> armsx2Savestates;
  final List<StorageDuplicateGroup> duplicates;

  /// Additions (documented deviations): media of folders that are no
  /// system (never), analyses not made with their technical reason (raw,
  /// never translated), hashing interrupted.
  final List<StorageOrphanEntry> unattributedMedia;
  final Map<String, String> skipped;
  final bool cancelled;

  /// Every save and state listed (information only).
  List<StorageOrphanEntry> get savesAndStates => [
    ...libretroSaves,
    ...libretroStates,
    ...dolphinStates,
    ...rpcs3Savedata,
    ...armsx2Savestates,
  ];
}

class _Rom {
  const _Rom(this.systemId, this.filename, this.romPath, this.titleId);

  final String systemId;
  final String filename;
  final String romPath;
  final String? titleId;
}

class _Database {
  const _Database({
    required this.folderOfSystem,
    required this.extensions,
    required this.roms,
    required this.metadata,
    required this.metadataSystemsWithoutGames,
  });

  final Map<String, String> folderOfSystem;
  final Map<String, Set<String>> extensions;
  final List<_Rom> roms;
  final List<StorageOrphanMetadataKey> metadata;

  /// `app_system_id` of the metadata rows whose system has no game row.
  final List<String> metadataSystemsWithoutGames;
}

/// The names the media of each system folder are matched against (§ 3.5):
/// the four variants of every game row (and the Title ID of the virtual
/// rows), by `app_systems.folder_name`.
class _MediaIndex {
  _MediaIndex(_Database database) {
    database.folderOfSystem.forEach((id, folder) {
      _systemsOfFolder.putIfAbsent(folder, () => <String>{}).add(id);
    });
    for (final rom in database.roms) {
      final folder = database.folderOfSystem[rom.systemId];
      if (folder == null) continue;
      final variants = _names.putIfAbsent(folder, () => <String>{});
      variants.addAll(
        StorageOrphanDetector.mediaNameVariants(
          rom.filename,
          database.extensions[folder] ?? const {},
        ),
      );
      // GameModel looks MeloNX/RPCS3 virtual rows up by Title ID first.
      final lower = rom.romPath.toLowerCase();
      final virtual =
          lower.startsWith('melonx://') ||
          lower.startsWith('rpcs3-library://') ||
          rom.filename.toLowerCase().endsWith('.melonx') ||
          rom.filename.toLowerCase().endsWith('.rpcs3');
      final titleId = rom.titleId?.trim();
      if (virtual && titleId != null && titleId.isNotEmpty) {
        variants.add(titleId);
      }
    }
  }

  final Map<String, Set<String>> _systemsOfFolder = {};
  final Map<String, Set<String>> _names = {};

  /// A folder of `app_systems`.
  bool known(String folder) => _systemsOfFolder.containsKey(folder);

  /// A known folder one of whose systems has a game row (review of the
  /// storage services: the others are not analysed).
  bool analysed(String folder) => _names.containsKey(folder);

  bool attributed(String folder, String base) =>
      _names[folder]?.contains(base) ?? false;
}

/// What a media file is for the orphan analysis.
enum _MediaVerdict { ignored, unattributed, notAnalysed, attributed, orphan }

/// What is still orphan when a cleanup runs (review of the storage
/// services): the same matching as [StorageOrphanDetector.detect], on a
/// fresh read of the database, of the library index and of the registered
/// library folders.
class StorageOrphanRecheck {
  const StorageOrphanRecheck({
    this.media = const {},
    this.covers = const {},
    this.metadata = const {},
    this.refused,
  });

  /// Canonical paths of the media still orphan.
  final Set<String> media;

  /// Canonical paths of the library covers still orphan.
  final Set<String> covers;

  /// Metadata keys still orphan.
  final Set<StorageOrphanMetadataKey> metadata;

  /// Raw reason nothing could be confirmed (database unreadable, library
  /// empty, a library folder missing or unreadable); every set is then
  /// empty.
  final String? refused;
}

class StorageOrphanDetector {
  StorageOrphanDetector({
    required Future<DatabaseAdapter> Function() database,
    required StorageRootRegistry registry,
  }) : _database = database,
       _registry = registry;

  final Future<DatabaseAdapter> Function() _database;
  final StorageRootRegistry _registry;

  /// Media types and extensions of `GameRepository.deleteNeoStationScrapedMedia`.
  static const List<String> mediaTypes = [
    'screenshots',
    'fanarts',
    'wheels',
    'box2d',
    'videos',
    'manuals',
  ];
  static const List<String> mediaExtensions = [
    'png',
    'jpg',
    'jpeg',
    'webp',
    'mp4',
    'pdf',
  ];

  /// Descriptors that reference other files of their folder.
  static const Set<String> descriptorExtensions = {
    'cue',
    'gdi',
    'm3u',
    'ccd',
    'toc',
    'mds',
    'cdi',
  };

  /// `GameRepository._stripExtension`.
  static String stripLastExtension(String name) {
    final dot = name.lastIndexOf('.');
    return dot == -1 ? name : name.substring(0, dot);
  }

  /// The four names `deleteNeoStationScrapedMedia` matches for a row, with
  /// `romBaseName = FileProvider.stripRomExtension(filename, extensions)`.
  static Set<String> mediaNameVariants(
    String filename,
    Set<String> systemExtensions,
  ) {
    final romBaseName = FileProvider.stripRomExtension(
      filename,
      systemExtensions,
    );
    return {
      stripLastExtension(romBaseName),
      stripLastExtension(filename),
      romBaseName,
      filename,
    };
  }

  Future<StorageOrphanReport> detect(
    StorageScanResult scan, {
    bool hashDuplicates = false,
    StorageScanCancelToken? cancel,
  }) async {
    final skipped = <String, String>{};
    bool stopped() => cancel?.isCancelled ?? false;

    _Database? database;
    try {
      database = await _load();
    } catch (error) {
      skipped['database'] = '$error';
    }
    final hasGames = database != null && database.roms.isNotEmpty;
    if (database != null && !hasGames) {
      // An empty user_roms is indistinguishable from a library not
      // scanned yet: nothing is claimed orphan from it.
      const reason = 'user_roms is empty';
      skipped['media'] = reason;
      skipped['metadata'] = reason;
      skipped['libretroSaves'] = reason;
      skipped['libretroStates'] = reason;
    }

    // A registered library folder the analysis cannot see may have lost its
    // games' rows to a scan: nothing is then claimed orphan from the rows or
    // from the library index (review of the storage services).
    final unreadable = await unreadableLibraryFolders(scan);
    final foldersSeen = unreadable.isEmpty;
    if (!foldersSeen) {
      final reason =
          'library folder missing or unreadable: ${unreadable.join('; ')}';
      skipped['media'] = reason;
      skipped['metadata'] = reason;
      skipped['libraryCovers'] = reason;
    }

    final media = <StorageOrphanEntry>[];
    final unattributed = <StorageOrphanEntry>[];
    final mediaNotAnalysed = <String>{};
    if (database != null && hasGames && foldersSeen) {
      _media(scan, database, media, unattributed, mediaNotAnalysed);
      // A known system without any game row: its media and metadata are
      // not analysed (its rows may have been pruned).
      final metadataNotAnalysed = database.metadataSystemsWithoutGames;
      if (mediaNotAnalysed.isNotEmpty || metadataNotAnalysed.isNotEmpty) {
        skipped['systemsWithoutGames'] = [
          if (mediaNotAnalysed.isNotEmpty)
            'media: ${(mediaNotAnalysed.toList()..sort()).join(', ')}',
          if (metadataNotAnalysed.isNotEmpty)
            'metadata: ${metadataNotAnalysed.join(', ')}',
        ].join('; ');
      }
    } else if (database == null) {
      skipped['media'] = 'database unavailable';
    }
    if (stopped()) {
      return StorageOrphanReport(skipped: skipped, cancelled: true);
    }

    final covers = foldersSeen
        ? await _covers(scan, skipped)
        : const <StorageOrphanEntry>[];
    final libretroSaves = <StorageOrphanEntry>[];
    final libretroStates = <StorageOrphanEntry>[];
    if (database != null && hasGames) {
      final radicals = _romRadicals(database.roms);
      _libretro(
        scan,
        StorageLayout.libretroSaves,
        StorageOrphanKind.libretroSave,
        radicals,
        libretroSaves,
      );
      _libretro(
        scan,
        StorageLayout.libretroStates,
        StorageOrphanKind.libretroState,
        radicals,
        libretroStates,
      );
    } else if (database == null) {
      skipped['libretroSaves'] = 'database unavailable';
      skipped['libretroStates'] = 'database unavailable';
    }
    final dolphinStates = _dolphinStates(scan);
    if (stopped()) {
      return StorageOrphanReport(skipped: skipped, cancelled: true);
    }
    final rpcs3 = await _rpcs3Savedata(scan, database, skipped);
    if (stopped()) {
      return StorageOrphanReport(skipped: skipped, cancelled: true);
    }
    final armsx2 = await _armsx2(scan, database, skipped);
    if (stopped()) {
      return StorageOrphanReport(skipped: skipped, cancelled: true);
    }

    final duplicates = await _duplicates(
      scan,
      database,
      skipped,
      hash: hashDuplicates,
      cancel: cancel,
    );
    return StorageOrphanReport(
      media: List.unmodifiable(media),
      unattributedMedia: List.unmodifiable(unattributed),
      libraryCovers: List.unmodifiable(covers),
      metadata: database == null || !hasGames || !foldersSeen
          ? const []
          : List.unmodifiable(database.metadata),
      libretroSaves: List.unmodifiable(libretroSaves),
      libretroStates: List.unmodifiable(libretroStates),
      dolphinStates: List.unmodifiable(dolphinStates),
      rpcs3Savedata: List.unmodifiable(rpcs3),
      armsx2Savestates: List.unmodifiable(armsx2),
      duplicates: List.unmodifiable(duplicates.groups),
      skipped: Map.unmodifiable(skipped),
      cancelled: duplicates.cancelled,
    );
  }

  Future<_Database> _load() async {
    final db = await _database();
    final systems = await db.rawQuery(
      'SELECT id, folder_name FROM app_systems',
    );
    final folderOfSystem = <String, String>{
      for (final row in systems)
        if (row['id'] != null && row['folder_name'] != null)
          row['id'].toString(): row['folder_name'].toString(),
    };
    final extensionRows = await db.rawQuery(
      'SELECT s.folder_name, e.extension FROM app_systems s '
      'JOIN app_system_extensions e ON s.id = e.system_id',
    );
    final extensions = <String, Set<String>>{};
    for (final row in extensionRows) {
      final folder = row['folder_name']?.toString();
      final extension = row['extension']?.toString().toLowerCase();
      if (folder == null || extension == null) continue;
      extensions.putIfAbsent(folder, () => <String>{})
        ..add(extension)
        // Older migrations stored `.nsp`: compare like the current sync.
        ..add(extension.replaceAll('.', ''));
    }
    final romRows = await db.rawQuery(
      'SELECT app_system_id, filename, rom_path, title_id FROM user_roms',
    );
    final roms = [
      for (final row in romRows)
        if (row['filename'] != null)
          _Rom(
            row['app_system_id']?.toString() ?? '',
            row['filename'].toString(),
            row['rom_path']?.toString() ?? '',
            row['title_id']?.toString(),
          ),
    ];
    final metadata = [
      for (final row in await db.rawQuery(storageOrphanMetadataQuery))
        StorageOrphanMetadataKey(
          row['app_system_id'].toString(),
          row['filename'].toString(),
        ),
    ];
    final withoutGames = [
      for (final row in await db.rawQuery(
        storageMetadataSystemsWithoutGamesQuery,
      ))
        if (row['app_system_id'] != null) row['app_system_id'].toString(),
    ];
    return _Database(
      folderOfSystem: folderOfSystem,
      extensions: extensions,
      roms: roms,
      metadata: metadata,
      metadataSystemsWithoutGames: withoutGames,
    );
  }

  StorageOrphanEntry _entry(
    StorageNode node,
    StorageOrphanKind kind,
    String key, {
    String? group,
    required bool selectable,
  }) => StorageOrphanEntry(
    kind: kind,
    path: node.path,
    relativePath: node.relativePath,
    container: node.container,
    rootId: node.rootId,
    entryKind: node.kind,
    logicalBytes: node.logicalBytes,
    allocatedBytes: node.allocatedBytes,
    modified: node.modified ?? DateTime.fromMillisecondsSinceEpoch(0),
    category: node.category,
    deletionClass: node.deletionClass,
    ruleId: node.ruleId,
    key: key,
    group: group,
    selectable: selectable && node.deletionClass != StorageDeletionClass.never,
  );

  static StorageNode? _child(StorageNode? node, String name) {
    if (node == null) return null;
    for (final child in node.children) {
      if (child.name == name) return child;
    }
    return null;
  }

  static StorageNode? _descend(StorageNode? node, String relative) {
    var current = node;
    for (final segment in p.split(relative)) {
      current = _child(current, segment);
      if (current == null) return null;
    }
    return current;
  }

  /// The verdict of the media file [name] of the [type] folder of the
  /// system [folder]: the same for an analysis and for a re-check.
  static _MediaVerdict _mediaVerdict(
    _MediaIndex index,
    String folder,
    String type,
    String name,
  ) {
    if (!mediaTypes.contains(type) || name.startsWith('.')) {
      return _MediaVerdict.ignored;
    }
    final dot = name.lastIndexOf('.');
    final extension = dot == -1 ? '' : name.substring(dot + 1).toLowerCase();
    if (!mediaExtensions.contains(extension)) return _MediaVerdict.ignored;
    final base = dot == -1 ? name : name.substring(0, dot);
    if (!index.known(folder)) return _MediaVerdict.unattributed;
    if (!index.analysed(folder)) return _MediaVerdict.notAnalysed;
    return index.attributed(folder, base)
        ? _MediaVerdict.attributed
        : _MediaVerdict.orphan;
  }

  void _media(
    StorageScanResult scan,
    _Database database,
    List<StorageOrphanEntry> orphans,
    List<StorageOrphanEntry> unattributed,
    Set<String> notAnalysed,
  ) {
    final index = _MediaIndex(database);
    for (final location in scan.nodesOfRoot('INV-05')) {
      for (final system in location.children) {
        if (!system.isDirectory) continue;
        final folder = system.name;
        for (final type in system.children) {
          if (!type.isDirectory) continue;
          for (final file in type.children) {
            if (file.kind != StorageEntryKind.file) continue;
            final name = file.name;
            final dot = name.lastIndexOf('.');
            final base = dot == -1 ? name : name.substring(0, dot);
            switch (_mediaVerdict(index, folder, type.name, name)) {
              case _MediaVerdict.ignored:
              case _MediaVerdict.attributed:
                break;
              case _MediaVerdict.notAnalysed:
                notAnalysed.add(folder);
              case _MediaVerdict.unattributed:
                unattributed.add(
                  _entry(
                    file,
                    StorageOrphanKind.unattributedMedia,
                    base,
                    group: folder,
                    selectable: false,
                  ),
                );
              case _MediaVerdict.orphan:
                orphans.add(
                  _entry(
                    file,
                    StorageOrphanKind.media,
                    base,
                    group: folder,
                    selectable: true,
                  ),
                );
            }
          }
        }
      }
    }
    orphans.sort((a, b) => a.path.compareTo(b.path));
    unattributed.sort((a, b) => a.path.compareTo(b.path));
  }

  /// `id` of every book of `local-index.json`; null (with the reason in
  /// [skipped], when given) when the index is missing or unreadable.
  Future<Set<String>?> _libraryIndexIds([Map<String, String>? skipped]) async {
    final index = File(
      _registry.pathIn(
        StorageContainer.applicationSupport,
        StorageLayout.libraryIndex,
      ),
    );
    try {
      if (!await index.exists()) {
        skipped?['libraryCovers'] = 'local-index.json missing';
        return null;
      }
      final decoded = jsonDecode(utf8.decode(await index.readAsBytes()));
      if (decoded is! Map ||
          decoded['version'] is! int ||
          decoded['books'] is! List) {
        skipped?['libraryCovers'] = 'local-index.json is not a library index';
        return null;
      }
      return {
        for (final book in decoded['books'] as List)
          if (book is Map && book['id'] is String) book['id'] as String,
      };
    } catch (error) {
      skipped?['libraryCovers'] = 'local-index.json unreadable: $error';
      return null;
    }
  }

  /// Book id of the cover file [name] (`<id>.png`), null for any other.
  static String? _coverId(String name) =>
      name.startsWith('.') || !name.endsWith('.png') || name.length <= 4
      ? null
      : name.substring(0, name.length - 4);

  Future<List<StorageOrphanEntry>> _covers(
    StorageScanResult scan,
    Map<String, String> skipped,
  ) async {
    final covers = <StorageNode>[];
    for (final location in scan.nodesOfRoot('INV-23')) {
      final directory = _child(
        location,
        p.basename(StorageLayout.libraryCovers),
      );
      if (directory == null) continue;
      for (final file in directory.children) {
        if (file.kind == StorageEntryKind.file && _coverId(file.name) != null) {
          covers.add(file);
        }
      }
    }
    if (covers.isEmpty) return const [];
    final ids = await _libraryIndexIds(skipped);
    if (ids == null) return const [];
    final orphans = [
      for (final file in covers)
        if (!ids.contains(_coverId(file.name)))
          _entry(
            file,
            StorageOrphanKind.libraryCover,
            _coverId(file.name)!,
            selectable: true,
          ),
    ]..sort((a, b) => a.path.compareTo(b.path));
    return orphans;
  }

  /// The registered library folders (`libraryRoots`, the linked folder)
  /// the analysis cannot see, with the raw reason (review of the storage
  /// services): missing, or unreadable on the disk or in [scan] (a stale
  /// bookmark on iOS). Each is named `<Documents>/…` inside a container,
  /// `<library folder>` outside. A scan of the library prunes the rows of an
  /// unreadable folder, so while one is listed no media, metadata or cover
  /// is claimed orphan.
  Future<List<String>> unreadableLibraryFolders([
    StorageScanResult? scan,
  ]) async {
    final problems = <String>[];
    final seen = <String>{};
    for (final folder in [
      ..._registry.libraryRoots,
      ?_registry.linkedExternalFolder,
    ]) {
      final trimmed = folder.trim();
      if (trimmed.isEmpty) continue;
      final canonical = storageCanonicalPath(trimmed);
      if (!seen.add(canonical)) continue;
      // A folder outside the containers is never spelled out (a name the
      // user chose; the journal and the report hold relative paths only).
      final shown =
          _registry.containers.displayPathOf(trimmed) ?? '<library folder>';
      if (scan != null) {
        for (final node in scan.nodesOfRoot('INV-01')) {
          if (storageCanonicalPath(node.path) != canonical) continue;
          if (node.kind != StorageEntryKind.directory) {
            problems.add('$shown: ${node.kind.name} in the analysis');
          } else if (node.modified == null) {
            problems.add('$shown: missing in the analysis');
          }
        }
      }
      try {
        final type = await FileSystemEntity.type(trimmed);
        if (type != FileSystemEntityType.directory) {
          problems.add(
            '$shown: ${type == FileSystemEntityType.notFound ? 'missing' : type.toString()}',
          );
          continue;
        }
        await Directory(trimmed).list(followLinks: false).take(1).drain<void>();
      } on FileSystemException catch (error) {
        problems.add('$shown: ${error.osError?.toString() ?? error.message}');
      }
    }
    return problems;
  }

  /// What is still orphan now among [media], [covers] and [metadata] (the
  /// paths and keys of a previewed plan): the same matching as [detect] on
  /// a fresh read of the database, of `local-index.json` and of the
  /// registered library folders (review of the storage services: a scan or
  /// an import may have run since the preview).
  Future<StorageOrphanRecheck> recheck({
    Iterable<String> media = const [],
    Iterable<String> covers = const [],
    Iterable<StorageOrphanMetadataKey> metadata = const [],
  }) async {
    final _Database database;
    try {
      database = await _load();
    } catch (error) {
      return StorageOrphanRecheck(refused: 'database: $error');
    }
    if (database.roms.isEmpty) {
      return const StorageOrphanRecheck(refused: 'user_roms is empty');
    }
    final unreadable = await unreadableLibraryFolders();
    if (unreadable.isNotEmpty) {
      return StorageOrphanRecheck(
        refused:
            'library folder missing or unreadable: ${unreadable.join('; ')}',
      );
    }
    final index = _MediaIndex(database);
    final mediaRoot = storageCanonicalPath(_registry.mediaPath);
    final stillMedia = <String>{};
    for (final path in media) {
      final canonical = storageCanonicalPath(path);
      if (!p.isWithin(mediaRoot, canonical)) continue;
      final segments = p.split(p.relative(canonical, from: mediaRoot));
      if (segments.length != 3) continue;
      if (_mediaVerdict(index, segments[0], segments[1], segments[2]) ==
          _MediaVerdict.orphan) {
        stillMedia.add(canonical);
      }
    }
    final stillCovers = <String>{};
    final coverPaths = covers.toList();
    if (coverPaths.isNotEmpty) {
      final ids = await _libraryIndexIds();
      final coversRoot = storageCanonicalPath(
        _registry.pathIn(
          StorageContainer.applicationSupport,
          StorageLayout.libraryCovers,
        ),
      );
      for (final path in coverPaths) {
        final canonical = storageCanonicalPath(path);
        if (ids == null || p.dirname(canonical) != coversRoot) continue;
        final id = _coverId(p.basename(canonical));
        if (id != null && !ids.contains(id)) stillCovers.add(canonical);
      }
    }
    final orphanKeys = database.metadata.toSet();
    return StorageOrphanRecheck(
      media: stillMedia,
      covers: stillCovers,
      metadata: {
        for (final key in metadata)
          if (orphanKeys.contains(key)) key,
      },
    );
  }

  /// Every prefix of [name] at a dot, longest first (`a.b.c` → `a.b.c`,
  /// `a.b`, `a`).
  static Iterable<String> _prefixes(String name) sync* {
    var current = name;
    while (true) {
      yield current;
      final dot = current.lastIndexOf('.');
      if (dot <= 0) return;
      current = current.substring(0, dot);
    }
  }

  static Set<String> _romRadicals(List<_Rom> roms) => {
    for (final rom in roms) ..._prefixes(rom.filename),
  };

  void _libretro(
    StorageScanResult scan,
    String relative,
    StorageOrphanKind kind,
    Set<String> radicals,
    List<StorageOrphanEntry> orphans,
  ) {
    for (final location in scan.nodesOfRoot('INV-14')) {
      final root = _descend(
        location,
        p.relative(relative, from: StorageLayout.libretro),
      );
      if (root == null) continue;
      for (final core in root.children) {
        if (!core.isDirectory) continue;
        for (final file in core.children) {
          if (file.kind != StorageEntryKind.file || file.name.startsWith('.')) {
            continue;
          }
          // `<content>.srm`, `<content>.state<N>`: the content name is the
          // ROM file name without its last extension (LibretroCoreHost).
          final attributed = _prefixes(
            stripLastExtension(file.name),
          ).any(radicals.contains);
          if (!attributed) {
            orphans.add(
              _entry(
                file,
                kind,
                stripLastExtension(file.name),
                group: core.name,
                selectable: false,
              ),
            );
          }
        }
      }
    }
    orphans.sort((a, b) => a.path.compareTo(b.path));
  }

  List<StorageOrphanEntry> _dolphinStates(StorageScanResult scan) {
    final states = <StorageOrphanEntry>[];
    for (final location in scan.nodesOfRoot('INV-21')) {
      final root = _descend(
        location,
        p.relative(StorageLayout.dolphinStates, from: StorageLayout.dolphin),
      );
      if (root == null) continue;
      for (final node in root.descendants) {
        if (node.kind != StorageEntryKind.file) continue;
        // Listed, never attributed to a game.
        states.add(
          _entry(
            node,
            StorageOrphanKind.dolphinState,
            node.name,
            selectable: false,
          ),
        );
      }
    }
    states.sort((a, b) => a.path.compareTo(b.path));
    return states;
  }

  static final RegExp _titleId = RegExp(r'^[A-Z]{4}[0-9]{5}');
  static final RegExp _titleIdAnywhere = RegExp(r'[A-Z]{4}[0-9]{5}');

  static String? _titleIdPrefix(String? value) {
    final match = _titleId.firstMatch(value?.trim().toUpperCase() ?? '');
    return match?.group(0);
  }

  /// `TITLE_ID` (or the title-ID prefix of `SAVEDATA_DIRECTORY`) of the
  /// first readable `PARAM.SFO` among [candidates]; null otherwise.
  static Future<String?> _sfoTitleId(List<String> candidates) async {
    for (final candidate in candidates) {
      try {
        final sfo = File(candidate);
        if (!await sfo.exists() || await sfo.length() > 1 << 20) continue;
        final values = Rpcs3LibraryService.parseParamSfoBytes(
          await sfo.readAsBytes(),
        );
        final id =
            _titleIdPrefix(values['TITLE_ID']?.toString()) ??
            _titleIdPrefix(values['SAVEDATA_DIRECTORY']?.toString());
        if (id != null) return id;
      } catch (_) {
        continue;
      }
    }
    return null;
  }

  /// Title IDs of the games installed in `dev_hdd0/game` and `games/*`
  /// (folder or file names, then their `PARAM.SFO`), plus the PS3 rows of
  /// the library: generous on purpose, a save is claimed orphan only when
  /// no installed game can own it.
  Future<Set<String>> _installedTitleIds(
    StorageNode data,
    _Database? database,
  ) async {
    final installed = <String>{};
    Future<void> add(StorageNode entry) async {
      for (final match in _titleIdAnywhere.allMatches(
        entry.name.toUpperCase(),
      )) {
        installed.add(match.group(0)!);
      }
      if (entry.isDirectory) {
        final id = await _sfoTitleId([
          p.join(entry.path, 'PARAM.SFO'),
          p.join(entry.path, 'PS3_GAME', 'PARAM.SFO'),
        ]);
        if (id != null) installed.add(id);
      }
    }

    for (final game
        in _descend(data, StorageLayout.rpcs3HddGames)?.children ??
            const <StorageNode>[]) {
      await add(game);
    }
    for (final alias
        in _descend(data, StorageLayout.rpcs3Games)?.children ??
            const <StorageNode>[]) {
      if (!alias.isDirectory) {
        await add(alias);
        continue;
      }
      for (final game in alias.children) {
        await add(game);
      }
    }
    for (final rom in database?.roms ?? const <_Rom>[]) {
      if (!Rpcs3LibraryService.isVirtualLibraryPath(rom.romPath)) continue;
      final id = _titleIdPrefix(
        Uri.tryParse(rom.romPath)?.queryParameters['title-id'] ?? rom.titleId,
      );
      if (id != null) installed.add(id);
    }
    return installed;
  }

  Future<List<StorageOrphanEntry>> _rpcs3Savedata(
    StorageScanResult scan,
    _Database? database,
    Map<String, String> skipped,
  ) async {
    if (_registry.rpcs3Redirected) {
      skipped['rpcs3Savedata'] = 'Data/vfs.yml redirects dev_hdd0';
      return const [];
    }
    StorageNode? data;
    for (final location in scan.nodesOfRoot('INV-16')) {
      data ??= location;
    }
    final savedata = _descend(data, StorageLayout.rpcs3Savedata);
    if (data == null || savedata == null || savedata.children.isEmpty) {
      return const [];
    }
    final installed = await _installedTitleIds(data, database);
    final orphans = <StorageOrphanEntry>[];
    for (final save in savedata.children) {
      if (!save.isDirectory) continue;
      final titleId =
          await _sfoTitleId([p.join(save.path, 'PARAM.SFO')]) ??
          _titleIdPrefix(save.name);
      // A save whose title cannot be read is not claimed orphan.
      if (titleId == null || installed.contains(titleId)) continue;
      orphans.add(
        _entry(
          save,
          StorageOrphanKind.rpcs3Savedata,
          titleId,
          group: save.name,
          selectable: false,
        ),
      );
    }
    orphans.sort((a, b) => a.path.compareTo(b.path));
    return orphans;
  }

  static final RegExp _serialToken = RegExp(
    r'(?:^|[^A-Z])([A-Z]{4})[-_ ]?([0-9]{3})\.?([0-9]{2})(?![0-9])',
  );

  /// PS2 serial (`SLUS20946`) in a file name, or null.
  static String? serialInName(String name) {
    final match = _serialToken.firstMatch(name.toUpperCase());
    if (match == null) return null;
    return '${match.group(1)}${match.group(2)}${match.group(3)}';
  }

  /// `BOOT2` serial of the `SYSTEM.CNF` of a plain ISO 9660 image, or null
  /// (compressed images and raw CD sectors are not read).
  static Future<String?> serialFromIso(String path) async {
    RandomAccessFile? file;
    try {
      final handle = await File(path).open();
      file = handle;
      const sector = 2048;
      Future<Uint8List> read(int offset, int length) async {
        await handle.setPosition(offset);
        return handle.read(length);
      }

      final pvd = await read(16 * sector, sector);
      if (pvd.length < 190 ||
          pvd[0] != 1 ||
          ascii.decode(pvd.sublist(1, 6), allowInvalid: true) != 'CD001') {
        return null;
      }
      final view = ByteData.sublistView(pvd);
      final rootLba = view.getUint32(156 + 2, Endian.little);
      final rootLength = view.getUint32(156 + 10, Endian.little);
      if (rootLength == 0) return null;
      final directory = await read(
        rootLba * sector,
        rootLength.clamp(0, 64 * sector).toInt(),
      );
      var offset = 0;
      while (offset < directory.length) {
        final length = directory[offset];
        if (length == 0) {
          // Records never cross a sector: skip to the next one.
          offset = (offset ~/ sector + 1) * sector;
          continue;
        }
        if (offset + length > directory.length || length < 34) break;
        final nameLength = directory[offset + 32];
        final name = ascii
            .decode(
              directory.sublist(offset + 33, offset + 33 + nameLength),
              allowInvalid: true,
            )
            .toUpperCase();
        if (name == 'SYSTEM.CNF;1' || name == 'SYSTEM.CNF') {
          final record = ByteData.sublistView(
            directory,
            offset,
            offset + length,
          );
          final lba = record.getUint32(2, Endian.little);
          final size = record.getUint32(10, Endian.little);
          final text = latin1.decode(
            await read(lba * sector, size.clamp(0, 4096).toInt()),
          );
          final boot = RegExp(
            r'BOOT2\s*=\s*cdrom0:\\?([A-Za-z]{4})[_-]?([0-9]{3})\.?([0-9]{2})',
          ).firstMatch(text);
          if (boot == null) return null;
          return '${boot.group(1)!.toUpperCase()}${boot.group(2)}${boot.group(3)}';
        }
        offset += length;
      }
      return null;
    } catch (_) {
      return null;
    } finally {
      await file?.close();
    }
  }

  Future<List<StorageOrphanEntry>> _armsx2(
    StorageScanResult scan,
    _Database? database,
    Map<String, String> skipped,
  ) async {
    final states = <StorageNode>[];
    final games = <String>[];
    for (final location in scan.nodesOfRoot('INV-11')) {
      final savestates = _descend(
        location,
        p.relative(StorageLayout.armsx2Savestates, from: StorageLayout.armsx2),
      );
      for (final file in savestates?.children ?? const <StorageNode>[]) {
        if (file.kind == StorageEntryKind.file &&
            !file.name.startsWith('.') &&
            file.name.toLowerCase().contains('.p2s')) {
          states.add(file);
        }
      }
      final folder = _descend(
        location,
        p.relative(StorageLayout.armsx2Games, from: StorageLayout.armsx2),
      );
      for (final node
          in folder?.descendants ?? const Iterable<StorageNode>.empty()) {
        if (node.kind == StorageEntryKind.file && !node.name.startsWith('.')) {
          games.add(node.path);
        }
      }
    }
    if (states.isEmpty) return const [];
    if (database == null) {
      skipped['armsx2Savestates'] = 'database unavailable';
      return const [];
    }
    for (final rom in database.roms) {
      if (database.folderOfSystem[rom.systemId]?.toLowerCase() == 'ps2' &&
          rom.romPath.isNotEmpty) {
        games.add(rom.romPath);
      }
    }
    final serials = <String>{};
    var unknown = 0;
    for (final game in {...games}) {
      final serial =
          serialInName(p.basename(game)) ??
          (p.extension(game).toLowerCase() == '.iso'
              ? await serialFromIso(game)
              : null);
      if (serial == null) {
        unknown++;
      } else {
        serials.add(serial);
      }
    }
    if (unknown > 0) {
      // A game whose serial is unknown could own any state.
      skipped['armsx2Savestates'] = 'serial unknown for $unknown game(s)';
      return const [];
    }
    final orphans = <StorageOrphanEntry>[];
    for (final state in states) {
      final serial = serialInName(state.name);
      if (serial == null || serials.contains(serial)) continue;
      orphans.add(
        _entry(
          state,
          StorageOrphanKind.armsx2Savestate,
          serial,
          selectable: false,
        ),
      );
    }
    orphans.sort((a, b) => a.path.compareTo(b.path));
    return orphans;
  }

  /// `user_roms.rom_path` keys: case-insensitive (`COLLATE NOCASE`) and
  /// `/private/var` = `/var`.
  static String _referenceKey(String path) =>
      storageCanonicalPath(path).toLowerCase();

  Future<({List<StorageDuplicateGroup> groups, bool cancelled})> _duplicates(
    StorageScanResult scan,
    _Database? database,
    Map<String, String> skipped, {
    required bool hash,
    StorageScanCancelToken? cancel,
  }) async {
    // Copies of the game folders: Documents/roms and the library folders
    // (INV-01), Dolphin/Library (INV-20), Ports/KartPad/Games, ARMSX2/Games.
    final searched = <StorageNode>[
      ...scan.nodesOfRoot('INV-01'),
      ...scan.nodesOfRoot('INV-20'),
    ];
    for (final (root, relative, base) in [
      ('INV-11', StorageLayout.armsx2Games, StorageLayout.armsx2),
      ('INV-12', StorageLayout.kartpadGames, StorageLayout.kartpad),
    ]) {
      for (final location in scan.nodesOfRoot(root)) {
        if (location.container != StorageContainer.documents) continue;
        final folder = _descend(location, p.relative(relative, from: base));
        if (folder != null) searched.add(folder);
      }
    }
    final candidates = <(StorageNode, bool)>[];
    for (final top in searched) {
      // (directory, an .m3u in it or above)
      final stack = <(StorageNode, bool)>[(top, false)];
      while (stack.isNotEmpty) {
        final (directory, m3uAbove) = stack.removeLast();
        var descriptorHere = false;
        var m3uHere = false;
        for (final child in directory.children) {
          if (child.kind != StorageEntryKind.file) continue;
          final extension = p
              .extension(child.name)
              .replaceFirst('.', '')
              .toLowerCase();
          if (descriptorExtensions.contains(extension)) descriptorHere = true;
          if (extension == 'm3u') m3uHere = true;
        }
        for (final child in directory.children) {
          if (child.isDirectory) {
            stack.add((child, m3uAbove || m3uHere));
          } else if (child.kind == StorageEntryKind.file &&
              child.logicalBytes > 0 &&
              !child.name.startsWith('.') &&
              !child.name.endsWith('.part')) {
            candidates.add((child, descriptorHere || m3uAbove));
          }
        }
      }
    }
    final byKey = <String, List<(StorageNode, bool)>>{};
    for (final candidate in candidates) {
      final node = candidate.$1;
      byKey
          .putIfAbsent('${node.name}\u0000${node.logicalBytes}', () => [])
          .add(candidate);
    }
    final references = <String>{
      for (final rom in database?.roms ?? const <_Rom>[])
        if (rom.romPath.startsWith('/')) _referenceKey(rom.romPath),
    };
    if (database == null) {
      skipped['duplicateReferences'] = 'database unavailable';
    }
    Future<bool> isReferenced(String path) async {
      if (references.contains(_referenceKey(path))) return true;
      try {
        final resolved = await File(path).resolveSymbolicLinks();
        return references.contains(_referenceKey(resolved));
      } on FileSystemException {
        return false;
      }
    }

    final groups = <StorageDuplicateGroup>[];
    var cancelled = false;
    final keys = byKey.keys.toList()..sort();
    for (final key in keys) {
      final members = byKey[key]!;
      if (members.length < 2) continue;
      members.sort((a, b) => a.$1.path.compareTo(b.$1.path));
      final referenced = [
        for (final member in members) await isReferenced(member.$1.path),
      ];
      var subgroups = <List<int>>[List<int>.generate(members.length, (i) => i)];
      final digests = List<String?>.filled(members.length, null);
      var hashed = false;
      if (hash && !cancelled) {
        for (var index = 0; index < members.length; index++) {
          if (cancel?.isCancelled ?? false) {
            cancelled = true;
            break;
          }
          digests[index] = await sha256OfFile(members[index].$1.path);
        }
        if (!cancelled) {
          hashed = true;
          final byDigest = <String, List<int>>{};
          for (var index = 0; index < members.length; index++) {
            final digest = digests[index];
            if (digest == null) continue;
            byDigest.putIfAbsent(digest, () => []).add(index);
          }
          subgroups = [
            for (final indexes in byDigest.values)
              if (indexes.length >= 2) indexes,
          ];
        }
      }
      for (final indexes in subgroups) {
        final anyReferenced = indexes.any((index) => referenced[index]);
        final copies = <StorageDuplicateCopy>[];
        for (final index in indexes) {
          final (node, companion) = members[index];
          // Without checksums the same name and size do not make the same
          // game (USA and EUR images, two GameCube discs of the standard
          // size): listed, never offered (review of the storage services).
          final StorageDuplicateKeep? keep = referenced[index]
              ? StorageDuplicateKeep.referenced
              : companion
              ? StorageDuplicateKeep.companionFiles
              : !anyReferenced
              ? StorageDuplicateKeep.noReferencedCopy
              : !hashed
              ? StorageDuplicateKeep.notHashed
              : null;
          copies.add(
            StorageDuplicateCopy(
              path: node.path,
              relativePath: node.relativePath,
              container: node.container,
              rootId: node.rootId,
              logicalBytes: node.logicalBytes,
              allocatedBytes: node.allocatedBytes,
              modified: node.modified ?? DateTime.fromMillisecondsSinceEpoch(0),
              referenced: referenced[index],
              selectable: keep == null && database != null,
              keep: keep,
              sha256: digests[index],
            ),
          );
        }
        final first = members[indexes.first].$1;
        groups.add(
          StorageDuplicateGroup(
            name: first.name,
            size: first.logicalBytes,
            copies: List.unmodifiable(copies),
            hashed: hashed,
            sha256: hashed ? digests[indexes.first] : null,
          ),
        );
      }
    }
    return (groups: groups, cancelled: cancelled);
  }

  /// Lower-case hex SHA-256 of [path], streamed in a background isolate;
  /// null when the file cannot be read.
  static Future<String?> sha256OfFile(String path) =>
      Isolate.run(() => _sha256InIsolate(path));
}

Future<String?> _sha256InIsolate(String path) async {
  try {
    final digest = await sha256.bind(File(path).openRead()).first;
    return digest.toString();
  } on FileSystemException {
    return null;
  }
}
