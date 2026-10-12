/// Export of a storage analysis (docs/storage-audit-cleanup.md § 3.9).
///
/// [StorageReport.aggregate] (the default) holds totals only: by root
/// (`INV-xx`) and category, logical and allocated bytes, counters, free and
/// total space, orphans, duplicates, temporaries and `statViaFfi`. Paths only
/// appear with their container replaced by `<Documents>`, `<Support>`,
/// `<Caches>` or `<tmp>`; no game, book or user name, no container UUID, and
/// the hidden library folder never appears: it is counted in the Library root
/// (INV-15). [StorageReport.detailed] (opt-in) adds the relative paths of the
/// largest entries of each root, the hidden library folder still aggregated.
/// [StorageReportSharer] shares a report through a temporary file of the
/// app's `tmp/`.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:ui' show Rect;

import 'package:path/path.dart' as p;
import 'package:share_plus/share_plus.dart';

import '../../l10n/storage_locale.dart';
import '../library_source_files.dart';
import '../rpcs3_save_exchange_service.dart';
import 'storage_deletion_manager.dart';
import 'storage_orphan_detector.dart';
import 'storage_roots.dart';
import 'storage_scanner.dart';

abstract final class StorageReport {
  /// `format` of every report.
  static const String format = 'neostation-storage-report';

  /// Version of the report layout.
  static const int version = 1;

  /// Roots counted under « Bibliothèque » (`rootLibrary`).
  static const Set<String> libraryRootIds = {'INV-15', 'INV-23', 'INV-26'};

  /// Rule ids of the hidden library folder (measured, never detailed).
  static const Set<String> _hiddenRuleIds = {
    'NEVER.libraryHidden',
    'INV-15.hidden',
  };

  /// Totals only (the default export).
  static Map<String, Object?> aggregate(
    StorageScanResult scan, {
    StorageOrphanReport? orphans,
    StorageDeletionResult? lastCleanup,
  }) => _sanitized(
    _build(
      scan,
      orphans: orphans,
      lastCleanup: lastCleanup,
      maxEntriesPerRoot: 0,
    ),
    scan.containers,
  );

  /// [aggregate] plus the relative paths of the [maxEntriesPerRoot] largest
  /// entries of each root and of the unreadable entries (opt-in).
  static Map<String, Object?> detailed(
    StorageScanResult scan, {
    StorageOrphanReport? orphans,
    StorageDeletionResult? lastCleanup,
    int maxEntriesPerRoot = 200,
  }) => _sanitized(
    _build(
      scan,
      orphans: orphans,
      lastCleanup: lastCleanup,
      maxEntriesPerRoot: maxEntriesPerRoot < 0 ? 0 : maxEntriesPerRoot,
      detailed: true,
    ),
    scan.containers,
  );

  /// Indented JSON of a report.
  static String encode(Map<String, Object?> json) =>
      const JsonEncoder.withIndent('  ').convert(json);

  /// `storage-report-<yyyyMMdd-HHmmss>.json`.
  static String fileNameFor(DateTime time) =>
      'storage-report-${StorageDeletionManager.stamp(time)}.json';

  static Map<String, Object?> _totals(StorageCategoryTotals? totals) => {
    'logicalBytes': totals?.logicalBytes ?? 0,
    'allocatedBytes': totals?.allocatedBytes,
    'fileCount': totals?.fileCount ?? 0,
  };

  /// Inside the hidden library folder of `Documents/Library`.
  static bool _hidden(StorageNode node) {
    if (_hiddenRuleIds.contains(node.ruleId)) return true;
    if (node.container != StorageContainer.documents) return false;
    final segments = p.split(node.relativePath);
    return segments.length >= 2 &&
        segments[0] == StorageLayout.documentsLibrary &&
        segments[1].toLowerCase() ==
            LibrarySourceFiles.folderName.toLowerCase();
  }

  static bool _hiddenDisplayPath(String displayPath) {
    final segments = displayPath.split('/');
    return segments.length >= 3 &&
        segments[0] ==
            StorageContainers.placeholderOf(StorageContainer.documents) &&
        segments[1] == StorageLayout.documentsLibrary &&
        segments[2].toLowerCase() ==
            LibrarySourceFiles.folderName.toLowerCase();
  }

  static String _labelOf(String rootId, StorageContainer container) {
    if (libraryRootIds.contains(rootId)) return StorageLocale.rootLibrary;
    return StorageLocale.containerKeys[container.name] ??
        StorageLocale.rootDocuments;
  }

  /// Fixed inventory locations with their placeholder; a library folder of
  /// INV-01 (a name the user chose) is never spelled out.
  static String _location(StorageNode node) {
    if (node.rootId == 'INV-01' &&
        !(node.container == StorageContainer.documents &&
            node.relativePath == StorageLayout.roms)) {
      return '<library folder>';
    }
    return node.displayPath;
  }

  static Map<String, Object?> _build(
    StorageScanResult scan, {
    StorageOrphanReport? orphans,
    StorageDeletionResult? lastCleanup,
    required int maxEntriesPerRoot,
    bool detailed = false,
  }) {
    final ffi = scan.statViaFfi;
    var files = 0;
    var links = 0;
    var unreadable = 0;
    var icloud = 0;
    final byContainer = <StorageContainer, List<int>>{};
    final rootOrder = <String>[];
    final rootNodes = <String, List<StorageNode>>{};
    for (final node in scan.roots) {
      files += node.fileCount;
      links += node.linkCount;
      unreadable += node.inaccessibleCount;
      icloud += node.icloudCount;
      final totals = byContainer.putIfAbsent(node.container, () => [0, 0, 0]);
      totals[0] += node.logicalBytes;
      totals[1] += node.allocatedBytes ?? 0;
      totals[2] += node.fileCount;
      if (!rootNodes.containsKey(node.rootId)) rootOrder.add(node.rootId);
      rootNodes.putIfAbsent(node.rootId, () => []).add(node);
    }
    final byRoot = scan.byRoot;

    final roots = <Map<String, Object?>>[];
    for (final id in rootOrder) {
      final nodes = rootNodes[id]!;
      var logical = 0;
      var allocated = 0;
      var rootFiles = 0;
      var rootLinks = 0;
      var rootUnreadable = 0;
      var rootIcloud = 0;
      var truncated = false;
      for (final node in nodes) {
        logical += node.logicalBytes;
        allocated += node.allocatedBytes ?? 0;
        rootFiles += node.fileCount;
        rootLinks += node.linkCount;
        rootUnreadable += node.inaccessibleCount;
        rootIcloud += node.icloudCount;
        truncated = truncated || node.truncated;
      }
      final categories = byRoot[id] ?? const {};
      final root = <String, Object?>{
        'id': id,
        'label': _labelOf(id, nodes.first.container),
        'locations': [for (final node in nodes) _location(node)],
        'logicalBytes': logical,
        'allocatedBytes': ffi ? allocated : null,
        'fileCount': rootFiles,
        'linkCount': rootLinks,
        'inaccessibleCount': rootUnreadable,
        'icloudCount': rootIcloud,
        'truncated': truncated,
        'categories': {
          for (final category in StorageCategory.values)
            if (categories.containsKey(category))
              category.name: _totals(categories[category]),
        },
      };
      if (detailed) {
        final entries =
            <StorageNode>[
              for (final location in nodes)
                for (final node in location.descendants)
                  if (!_hidden(node)) node,
            ]..sort((a, b) {
              final bySize = b.logicalBytes.compareTo(a.logicalBytes);
              return bySize != 0 ? bySize : a.path.compareTo(b.path);
            });
        root['largest'] = [
          for (final node in entries.take(maxEntriesPerRoot))
            {
              'path': node.displayPath,
              'kind': node.kind.name,
              'logicalBytes': node.logicalBytes,
              'allocatedBytes': node.allocatedBytes,
              'fileCount': node.fileCount,
              'category': node.category.name,
              'deletionClass': node.deletionClass.name,
              'ruleId': node.ruleId,
            },
        ];
      }
      roots.add(root);
    }

    final report = <String, Object?>{
      'format': format,
      'version': version,
      'mode': detailed ? 'detailed' : 'aggregate',
      'scan': {
        'startedAt': scan.startedAt.toUtc().toIso8601String(),
        'durationMs': scan.duration.inMilliseconds,
        'cancelled': scan.cancelled,
        'truncated': scan.truncated,
        'entries': scan.entries,
        'statViaFfi': ffi,
        'statLayout': scan.statLayout,
      },
      'statViaFfi': ffi,
      'totals': {
        'logicalBytes': scan.logicalBytes,
        'allocatedBytes': ffi ? scan.allocatedBytes : null,
        'fileCount': files,
        'linkCount': links,
        'inaccessibleCount': unreadable,
        'icloudCount': icloud,
      },
      'volume': {'freeBytes': scan.freeBytes, 'totalBytes': scan.volumeBytes},
      'containers': {
        for (final container in StorageContainer.values)
          if (byContainer.containsKey(container))
            StorageContainers.placeholderOf(container): {
              'logicalBytes': byContainer[container]![0],
              'allocatedBytes': ffi ? byContainer[container]![1] : null,
              'fileCount': byContainer[container]![2],
            },
      },
      'categories': {
        for (final category in StorageCategory.values)
          if (scan.byCategory.containsKey(category))
            category.name: _totals(scan.byCategory[category]),
      },
      'temporaries': _totals(scan.byCategory[StorageCategory.temporary]),
      'roots': roots,
      'inaccessible': {
        'count': scan.inaccessible.length,
        if (detailed)
          'paths': [
            for (final path in scan.inaccessible)
              if (!_hiddenDisplayPath(path)) path,
          ],
      },
      'orphans': orphans == null ? null : _orphans(orphans),
      'duplicates': orphans == null ? null : _duplicates(orphans),
      'lastCleanup': lastCleanup == null ? null : _cleanup(lastCleanup),
    };
    return report;
  }

  static Map<String, Object?> _count(List<StorageOrphanEntry> entries) => {
    'count': entries.length,
    'logicalBytes': entries.fold<int>(
      0,
      (sum, entry) => sum + entry.logicalBytes,
    ),
  };

  static Map<String, Object?> _orphans(StorageOrphanReport orphans) {
    final saves = orphans.savesAndStates;
    return {
      'media': _count(orphans.media),
      'unattributedMedia': _count(orphans.unattributedMedia),
      'metadata': {'count': orphans.metadata.length},
      'libraryCovers': _count(orphans.libraryCovers),
      'savesAndStates': {
        ..._count(saves),
        'libretroSaves': orphans.libretroSaves.length,
        'libretroStates': orphans.libretroStates.length,
        'dolphinStates': orphans.dolphinStates.length,
        'rpcs3Savedata': orphans.rpcs3Savedata.length,
        'armsx2Savestates': orphans.armsx2Savestates.length,
      },
      // The reasons are raw texts that may quote a file: names only.
      'skipped': orphans.skipped.keys.toList()..sort(),
      'cancelled': orphans.cancelled,
    };
  }

  static Map<String, Object?> _duplicates(StorageOrphanReport orphans) {
    var copies = 0;
    var referenced = 0;
    var selectable = 0;
    var selectableBytes = 0;
    var hashed = 0;
    for (final group in orphans.duplicates) {
      if (group.hashed) hashed++;
      for (final copy in group.copies) {
        copies++;
        if (copy.referenced) referenced++;
        if (copy.selectable) {
          selectable++;
          selectableBytes += copy.logicalBytes;
        }
      }
    }
    return {
      'groups': orphans.duplicates.length,
      'copies': copies,
      'referencedCopies': referenced,
      'selectableCopies': selectable,
      'selectableBytes': selectableBytes,
      'hashedGroups': hashed,
    };
  }

  static Map<String, Object?> _cleanup(StorageDeletionResult result) => {
    'deletedFiles': result.deletedFiles,
    'deletedBytes': result.deletedBytes,
    'deletedDirectories': result.deletedDirectories,
    'skippedChanged': result.skippedChanged,
    'skippedMissing': result.skippedMissing,
    'refusals': {
      for (final entry in result.refusalCounts.entries)
        entry.key.name: entry.value,
    },
    'metadataDeleted': result.metadata?.deleted,
    'metadataSkippedNotOrphan': result.metadata?.skippedNotOrphan,
    'clearedCaches': [for (final cache in result.clearedCaches) cache.name],
    'cancelled': result.cancelled,
    'stoppedBySession': result.stoppedBySession,
    'journal': result.journalDisplayPath,
  };

  static final RegExp _uuid = RegExp(
    r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-'
    r'[0-9A-Fa-f]{12}',
  );

  /// Every string of [json] with the container paths replaced by their
  /// placeholders and every UUID by `<uuid>` (the container's own included).
  static Map<String, Object?> _sanitized(
    Map<String, Object?> json,
    StorageContainers containers,
  ) {
    final pairs = <(String, String)>[];
    for (final container in StorageContainer.values) {
      final placeholder = StorageContainers.placeholderOf(container);
      final raw = p.normalize(containers.pathOf(container));
      final canonical = storageCanonicalPath(raw);
      pairs
        ..add((raw, placeholder))
        ..add((canonical, placeholder))
        ..add(('/private$canonical', placeholder));
    }
    pairs.sort((a, b) => b.$1.length.compareTo(a.$1.length));
    String clean(String value) {
      var result = value;
      for (final (path, placeholder) in pairs) {
        if (path.length > 1) result = result.replaceAll(path, placeholder);
      }
      return result.replaceAll(_uuid, '<uuid>');
    }

    Object? walk(Object? value) {
      if (value is String) return clean(value);
      if (value is Map) {
        return <String, Object?>{
          for (final entry in value.entries)
            clean('${entry.key}'): walk(entry.value),
        };
      }
      if (value is List) return [for (final item in value) walk(item)];
      return value;
    }

    return walk(json)! as Map<String, Object?>;
  }

  /// A readable rendering of a report: [t] gives the catalog text of a
  /// `StorageLocale` key, whose placeholders are filled here; sizes come
  /// from `Rpcs3SaveExchangeService.formatBytes`, paths and ids stay raw.
  static String text(Map<String, Object?> json, String Function(String key) t) {
    String size(Object? value) =>
        value is int ? Rpcs3SaveExchangeService.formatBytes(value) : '—';
    String line(String key, [Map<String, Object?> values = const {}]) =>
        StorageLocale.fill(t(key), values);
    Map<String, Object?> map(Object? value) =>
        value is Map ? value.cast<String, Object?>() : const {};
    int count(Object? value) => value is int ? value : 0;

    final out = StringBuffer();
    void write(String text, {int indent = 0}) =>
        out.writeln('${'  ' * indent}$text');

    final totals = map(json['totals']);
    final volume = map(json['volume']);
    final scan = map(json['scan']);
    write(line(StorageLocale.title));
    if (scan['startedAt'] is String) {
      write(line(StorageLocale.lastScan, {'date': scan['startedAt']}));
    }
    out.writeln();
    write(line(StorageLocale.summary));
    write(
      line(StorageLocale.totalLogical, {'size': size(totals['logicalBytes'])}),
      indent: 1,
    );
    write(
      totals['allocatedBytes'] is int
          ? line(StorageLocale.totalAllocated, {
              'size': size(totals['allocatedBytes']),
            })
          : line(StorageLocale.allocatedUnavailable),
      indent: 1,
    );
    write(
      volume['freeBytes'] is int && volume['totalBytes'] is int
          ? line(StorageLocale.freeSpace, {
              'free': size(volume['freeBytes']),
              'total': size(volume['totalBytes']),
            })
          : line(StorageLocale.freeSpaceUnavailable),
      indent: 1,
    );
    write(
      line(StorageLocale.entries, {'count': count(scan['entries'])}),
      indent: 1,
    );
    for (final (key, field) in const [
      (StorageLocale.links, 'linkCount'),
      (StorageLocale.inaccessible, 'inaccessibleCount'),
      (StorageLocale.icloudPlaceholders, 'icloudCount'),
    ]) {
      if (count(totals[field]) > 0) {
        write(line(key, {'count': count(totals[field])}), indent: 1);
      }
    }

    out.writeln();
    write(line(StorageLocale.byCategory));
    map(json['categories']).forEach((name, value) {
      final key = StorageLocale.categoryKeys[name] ?? StorageLocale.catUnknown;
      write('${line(key)}: ${size(map(value)['logicalBytes'])}', indent: 1);
    });

    out.writeln();
    write(line(StorageLocale.byRoot));
    final roots = json['roots'];
    for (final root in roots is List ? roots : const []) {
      final values = map(root);
      final label = values['label'] is String
          ? line(values['label'] as String)
          : '';
      write(
        '${values['id']} · $label: ${size(values['logicalBytes'])} · '
        '${line(StorageLocale.entries, {'count': count(values['fileCount'])})}',
        indent: 1,
      );
      final largest = values['largest'];
      for (final entry in largest is List ? largest : const []) {
        final item = map(entry);
        write('${item['path']}  ${size(item['logicalBytes'])}', indent: 2);
      }
    }

    final orphans = map(json['orphans']);
    final duplicates = map(json['duplicates']);
    if (orphans.isNotEmpty || duplicates.isNotEmpty) {
      out.writeln();
      write(line(StorageLocale.orphans));
      if (orphans.isNotEmpty) {
        final media = map(orphans['media']);
        write(
          line(StorageLocale.orphanMedia, {
            'count': count(media['count']),
            'size': size(media['logicalBytes']),
          }),
          indent: 1,
        );
        write(
          line(StorageLocale.orphanMetadata, {
            'count': count(map(orphans['metadata'])['count']),
          }),
          indent: 1,
        );
        write(
          line(StorageLocale.orphanCovers, {
            'count': count(map(orphans['libraryCovers'])['count']),
          }),
          indent: 1,
        );
        write(
          line(StorageLocale.orphanSavesInfo, {
            'count': count(map(orphans['savesAndStates'])['count']),
          }),
          indent: 1,
        );
      }
      if (duplicates.isNotEmpty) {
        write(
          line(StorageLocale.duplicates, {
            'count': count(duplicates['groups']),
            'size': size(duplicates['selectableBytes']),
          }),
          indent: 1,
        );
      }
    }

    final cleanup = map(json['lastCleanup']);
    if (cleanup.isNotEmpty) {
      out.writeln();
      write(line(StorageLocale.resultTitle));
      write(
        line(StorageLocale.resultDeleted, {
          'count': count(cleanup['deletedFiles']),
          'size': size(cleanup['deletedBytes']),
        }),
        indent: 1,
      );
      write(
        line(StorageLocale.resultSkippedChanged, {
          'count': count(cleanup['skippedChanged']),
        }),
        indent: 1,
      );
      write(
        line(StorageLocale.resultMissing, {
          'count': count(cleanup['skippedMissing']),
        }),
        indent: 1,
      );
      final refusals = map(cleanup['refusals']);
      write(
        line(StorageLocale.resultRefused, {
          'count': refusals.values.fold<int>(
            0,
            (sum, value) => sum + count(value),
          ),
        }),
        indent: 1,
      );
      if (cleanup['metadataDeleted'] is int) {
        write(
          line(StorageLocale.resultMetadata, {
            'count': cleanup['metadataDeleted'],
          }),
          indent: 1,
        );
      }
      if (cleanup['journal'] is String) {
        write(
          line(StorageLocale.journalSaved, {'path': cleanup['journal']}),
          indent: 1,
        );
      }
    }

    out.writeln();
    write(line(StorageLocale.limitsTitle));
    if (json['statViaFfi'] != true) {
      write(line(StorageLocale.limitFfi), indent: 1);
    }
    for (final key in const [
      StorageLocale.limitFreeSpace,
      StorageLocale.limitNeoSwap,
      StorageLocale.limitExtensions,
      StorageLocale.limitLinkedFolders,
      StorageLocale.limitRpcs3Cache,
      StorageLocale.limitUnverified,
    ]) {
      write(line(key), indent: 1);
    }
    return out.toString();
  }
}

/// Shares one prepared report.
typedef StorageShare = Future<void> Function(ShareParams params);

/// Shares a report as `<tmp>/<fileName>` (the app's `tmp/`, beside
/// `Documents`), through `SharePlus.instance.share`; the file is removed once
/// the share sheet is closed.
class StorageReportSharer {
  StorageReportSharer({
    Future<Directory> Function()? temporaryDirectory,
    StorageShare? share,
  }) : _temporaryDirectory =
           temporaryDirectory ?? StorageContainers.temporaryDirectory,
       _share = share ?? _sharePlus;

  final Future<Directory> Function() _temporaryDirectory;
  final StorageShare _share;

  static Future<void> _sharePlus(ShareParams params) async {
    await SharePlus.instance.share(params);
  }

  /// Writes [content] to `<tmp>/<fileName>` ([fileName] is a bare file name,
  /// see [StorageReport.fileNameFor]), shares it, then deletes it. Errors of
  /// the share sheet are rethrown (the screen shows `shareFailed`).
  Future<void> share(
    String content, {
    required String fileName,
    Rect? origin,
  }) async {
    if (fileName.isEmpty ||
        fileName.startsWith('.') ||
        p.basename(fileName) != fileName ||
        fileName.contains('\\')) {
      throw ArgumentError.value(fileName, 'fileName', 'not a bare file name');
    }
    final directory = await _temporaryDirectory();
    await directory.create(recursive: true);
    final file = File(p.join(directory.path, fileName));
    await file.writeAsString(content, flush: true);
    try {
      await _share(
        ShareParams(
          files: [
            XFile(file.path, mimeType: 'application/json', name: fileName),
          ],
          subject: fileName,
          sharePositionOrigin: origin,
        ),
      );
    } finally {
      try {
        if (await FileSystemEntity.type(file.path, followLinks: false) ==
            FileSystemEntityType.file) {
          await file.delete();
        }
      } catch (_) {
        // Left to the next level-1 cleanup of tmp/.
      }
    }
  }
}
