/// Read-only measurement of the inventory (docs/storage-audit-cleanup.md
/// § 3.2): one `Isolate.run` per root, an iterative walk with
/// `Directory.list(recursive: false, followLinks: false)`, bounded in depth
/// and in entries. Links count 0 bytes and are never followed,
/// `.<name>.icloud` placeholders count 0 bytes, unreadable entries are
/// counted with their path. Logical sizes come from `FileStat.size`,
/// allocated sizes from `lstat` ([StorageStatFfi]) when its self-test
/// passed, free/total bytes from `statvfs`. Nothing is ever written.
library;

import 'dart:async';
import 'dart:io';
import 'dart:isolate';

import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:path/path.dart' as p;

import 'storage_categorizer.dart';
import 'storage_roots.dart';
import 'storage_stat_ffi.dart';

export 'storage_roots.dart' show StorageEntryKind;

/// Lists one directory without recursion nor link following. Replaced in
/// tests only (it must be a top-level function: it runs in the isolates).
typedef StorageDirectoryLister =
    Stream<FileSystemEntity> Function(Directory directory);

Stream<FileSystemEntity> _defaultLister(Directory directory) =>
    directory.list(recursive: false, followLinks: false);

/// Bytes and files of one category.
class StorageCategoryTotals {
  const StorageCategoryTotals({
    required this.logicalBytes,
    this.allocatedBytes,
    required this.fileCount,
  });

  final int logicalBytes;

  /// Null when allocated sizes are unavailable (logical fallback).
  final int? allocatedBytes;
  final int fileCount;

  StorageCategoryTotals operator +(StorageCategoryTotals other) =>
      StorageCategoryTotals(
        logicalBytes: logicalBytes + other.logicalBytes,
        allocatedBytes: allocatedBytes == null || other.allocatedBytes == null
            ? null
            : allocatedBytes! + other.allocatedBytes!,
        fileCount: fileCount + other.fileCount,
      );
}

/// One measured entry. Directories carry the totals of their subtree.
///
/// Additions to § 3.2 (documented deviations): [container], [rootId],
/// [icloudCount], [truncated], [byCategory] (location nodes only). A
/// subtree measured but never detailed (the hidden library folder) has no
/// node: its bytes are in its parent's totals, not in its children.
class StorageNode {
  const StorageNode({
    required this.path,
    required this.relativePath,
    required this.container,
    required this.rootId,
    required this.kind,
    required this.logicalBytes,
    this.allocatedBytes,
    this.fileCount = 0,
    this.linkCount = 0,
    this.inaccessibleCount = 0,
    this.icloudCount = 0,
    this.modified,
    required this.category,
    required this.deletionClass,
    this.ruleId,
    this.children = const [],
    this.truncated = false,
    this.byCategory = const {},
  });

  /// Absolute path, as listed (not canonical).
  final String path;

  /// Path relative to [container] (`''` for the container itself).
  final String relativePath;
  final StorageContainer container;

  /// Root (`INV-xx`) owning the entry.
  final String rootId;
  final StorageEntryKind kind;

  /// `FileStat.size` of the files of the subtree; links, placeholders and
  /// directory entries themselves count 0.
  final int logicalBytes;

  /// `st_blocks * 512` of the files (hard links counted once per root);
  /// null without `lstat`.
  final int? allocatedBytes;

  /// Regular files (placeholders excluded).
  final int fileCount;
  final int linkCount;
  final int inaccessibleCount;
  final int icloudCount;
  final DateTime? modified;
  final StorageCategory category;
  final StorageDeletionClass deletionClass;
  final String? ruleId;

  /// Sorted by [logicalBytes] (largest first), then name.
  final List<StorageNode> children;

  /// Part of the subtree was not listed (depth or entry limit).
  final bool truncated;

  /// Location nodes ([StorageScanResult.roots]) only: totals per category.
  final Map<StorageCategory, StorageCategoryTotals> byCategory;

  String get name => p.basename(path);

  bool get isDirectory =>
      kind == StorageEntryKind.directory ||
      (kind == StorageEntryKind.inaccessible && children.isNotEmpty);

  /// `<Documents>/a/b` form.
  String get displayPath {
    final placeholder = StorageContainers.placeholderOf(container);
    return relativePath.isEmpty ? placeholder : '$placeholder/$relativePath';
  }

  /// Every node below this one, depth first (iterative).
  Iterable<StorageNode> get descendants sync* {
    final stack = <StorageNode>[...children.reversed];
    while (stack.isNotEmpty) {
      final node = stack.removeLast();
      yield node;
      stack.addAll(node.children.reversed);
    }
  }

  @override
  String toString() =>
      'StorageNode($displayPath, ${kind.name}, $logicalBytes B, ${category.name}/${deletionClass.name})';
}

class StorageScanProgress {
  const StorageScanProgress({
    required this.rootsDone,
    required this.rootsTotal,
    required this.entries,
    required this.bytes,
    required this.rootId,
  });

  final int rootsDone;
  final int rootsTotal;

  /// Entries listed so far (all roots).
  final int entries;

  /// Logical bytes measured so far (all roots).
  final int bytes;

  /// Root being (or last) measured.
  final String rootId;
}

class StorageScanResult {
  const StorageScanResult({
    required this.containers,
    required this.roots,
    required this.logicalBytes,
    this.allocatedBytes,
    this.freeBytes,
    this.volumeBytes,
    required this.statViaFfi,
    required this.inaccessible,
    required this.startedAt,
    required this.duration,
    this.cancelled = false,
    this.entries = 0,
    this.byCategory = const {},
    this.statLayout,
  });

  final StorageContainers containers;

  /// One node per scanned directory ([StorageRootRegistry.locations]), in
  /// root order; several for a root spanning several directories.
  final List<StorageNode> roots;
  final int logicalBytes;
  final int? allocatedBytes;

  /// `f_bavail * f_frsize` of the Documents volume; null without `statvfs`.
  final int? freeBytes;

  /// `f_blocks * f_frsize`; null without `statvfs`.
  final int? volumeBytes;
  final bool statViaFfi;

  /// `<Container>/relative/path` of every unreadable entry.
  final List<String> inaccessible;
  final DateTime startedAt;
  final Duration duration;

  /// Additions (documented deviations): cancelled before the end (roots
  /// measured so far only), entries listed, totals per category, `lstat`
  /// layout used (`darwin-arm64`, `linux-x64`).
  final bool cancelled;
  final int entries;
  final Map<StorageCategory, StorageCategoryTotals> byCategory;
  final String? statLayout;

  /// Some subtree was not fully listed.
  bool get truncated => roots.any((root) => root.truncated);

  /// Location nodes of [rootId].
  Iterable<StorageNode> nodesOfRoot(String rootId) =>
      roots.where((node) => node.rootId == rootId);

  /// Every node of the scan (location nodes included).
  Iterable<StorageNode> get allNodes sync* {
    for (final root in roots) {
      yield root;
      yield* root.descendants;
    }
  }

  /// Totals per category of each root.
  Map<String, Map<StorageCategory, StorageCategoryTotals>> get byRoot {
    final result = <String, Map<StorageCategory, StorageCategoryTotals>>{};
    for (final node in roots) {
      final target = result.putIfAbsent(node.rootId, () => {});
      node.byCategory.forEach((category, totals) {
        final current = target[category];
        target[category] = current == null ? totals : current + totals;
      });
    }
    return result;
  }
}

/// Cancels a scan between roots and, inside a root, at the next listed
/// entry (the isolate is told through its control port).
class StorageScanCancelToken {
  final Completer<void> _cancelled = Completer<void>();

  void cancel() {
    if (!_cancelled.isCompleted) _cancelled.complete();
  }

  bool get isCancelled => _cancelled.isCompleted;

  /// Completes when [cancel] is called.
  Future<void> get whenCancelled => _cancelled.future;
}

class StorageScanner {
  StorageScanner({
    StorageStat? stat,
    this.maxDepth = 24,
    this.maxEntriesPerRoot = 500000,
    @visibleForTesting StorageDirectoryLister? lister,
  }) : _stat = stat,
       _lister = lister ?? _defaultLister;

  final StorageStat? _stat;
  final int maxDepth;
  final int maxEntriesPerRoot;
  final StorageDirectoryLister _lister;

  /// Entries between two progress messages of an isolate.
  static const int progressInterval = 256;

  Future<StorageScanResult> scan(
    StorageRootRegistry registry, {
    StorageScanCancelToken? cancel,
    void Function(StorageScanProgress)? onProgress,
  }) async {
    final startedAt = DateTime.now();
    final watch = Stopwatch()..start();
    final stat =
        _stat ??
        StorageStatFfi.tryLoad(probePath: registry.containers.documents) ??
        const StorageStatLogical();
    final ffi = stat.available;
    final roots = registry.roots;
    final locations = registry.locations;
    final nodes = <StorageNode>[];
    final inaccessible = <String>[];
    var entries = 0;
    var bytes = 0;
    var done = 0;
    var cancelled = false;

    void report(String rootId, {int extraEntries = 0, int extraBytes = 0}) {
      onProgress?.call(
        StorageScanProgress(
          rootsDone: done,
          rootsTotal: roots.length,
          entries: entries + extraEntries,
          bytes: bytes + extraBytes,
          rootId: rootId,
        ),
      );
    }

    for (final root in roots) {
      if (cancel?.isCancelled ?? false) {
        cancelled = true;
        break;
      }
      report(root.id);
      final own = [
        for (final location in locations)
          if (location.rootId == root.id) location,
      ];
      if (own.isNotEmpty) {
        final inputs = [
          for (final location in own)
            _LocationInput(
              path: location.path,
              relative: location.relative,
              container: location.container,
              excluded: _excludedBelow(location, locations),
            ),
        ];
        final output = await _runRoot(
          (progress) => _RootInput(
            registry: registry,
            rootId: root.id,
            locations: inputs,
            maxDepth: maxDepth,
            maxEntries: maxEntriesPerRoot,
            stat: stat,
            lister: _lister,
            progress: progress,
          ),
          cancel,
          (rootEntries, rootBytes) =>
              report(root.id, extraEntries: rootEntries, extraBytes: rootBytes),
        );
        if (output.cancelled) {
          cancelled = true;
          break;
        }
        nodes.addAll(output.nodes);
        inaccessible.addAll(output.inaccessible);
        entries += output.entries;
        bytes += output.logicalBytes;
      }
      done++;
      report(root.id);
    }

    final byCategory = <StorageCategory, StorageCategoryTotals>{};
    var allocated = ffi ? 0 : null;
    for (final node in nodes) {
      node.byCategory.forEach((category, totals) {
        final current = byCategory[category];
        byCategory[category] = current == null ? totals : current + totals;
      });
      if (allocated != null) allocated += node.allocatedBytes ?? 0;
    }
    final volume = ffi ? stat.statvfs(registry.containers.documents) : null;
    watch.stop();
    return StorageScanResult(
      containers: registry.containers,
      roots: List.unmodifiable(nodes),
      logicalBytes: bytes,
      allocatedBytes: allocated,
      freeBytes: volume?.freeBytes,
      volumeBytes: volume?.totalBytes,
      statViaFfi: ffi,
      inaccessible: List.unmodifiable(inaccessible),
      startedAt: startedAt,
      duration: watch.elapsed,
      cancelled: cancelled,
      entries: entries,
      byCategory: Map.unmodifiable(byCategory),
      statLayout: stat is StorageStatFfi ? stat.layout.name : null,
    );
  }

  static Set<String> _excludedBelow(
    StorageLocationPath location,
    List<StorageLocationPath> all,
  ) {
    final base = storageCanonicalPath(location.path);
    return {
      for (final other in all)
        if (!identical(other, location) &&
            p.isWithin(base, storageCanonicalPath(other.path)))
          storageCanonicalPath(other.path),
    };
  }

  /// Runs one root in its isolate, relaying counters and cancellation.
  static Future<_RootOutput> _runRoot(
    _RootInput Function(SendPort progress) build,
    StorageScanCancelToken? cancel,
    void Function(int entries, int bytes) onCounters,
  ) async {
    final port = ReceivePort();
    SendPort? control;
    var cancelSent = false;
    void sendCancel() {
      final target = control;
      if (cancelSent || target == null) return;
      cancelSent = true;
      target.send(true);
    }

    final subscription = port.listen((message) {
      if (message is SendPort) {
        control = message;
        if (cancel?.isCancelled ?? false) sendCancel();
      } else if (message is List && message.length == 2) {
        onCounters(message[0] as int, message[1] as int);
        if (cancel?.isCancelled ?? false) sendCancel();
      }
    });
    unawaited(cancel?.whenCancelled.then((_) => sendCancel()));
    try {
      return await _spawn(build(port.sendPort));
    } finally {
      await subscription.cancel();
      port.close();
    }
  }

  /// Separate function: the closure sent to the isolate captures [input]
  /// only (never a port or a subscription of the caller).
  static Future<_RootOutput> _spawn(_RootInput input) =>
      Isolate.run(() => _scanRootInIsolate(input));
}

class _LocationInput {
  const _LocationInput({
    required this.path,
    required this.relative,
    required this.container,
    required this.excluded,
  });

  final String path;
  final String relative;
  final StorageContainer container;

  /// Canonical directories of other roots below [path] (measured there).
  final Set<String> excluded;
}

class _RootInput {
  const _RootInput({
    required this.registry,
    required this.rootId,
    required this.locations,
    required this.maxDepth,
    required this.maxEntries,
    required this.stat,
    required this.lister,
    required this.progress,
  });

  final StorageRootRegistry registry;
  final String rootId;
  final List<_LocationInput> locations;
  final int maxDepth;
  final int maxEntries;
  final StorageStat stat;
  final StorageDirectoryLister lister;
  final SendPort progress;
}

class _RootOutput {
  const _RootOutput({
    required this.nodes,
    required this.inaccessible,
    required this.entries,
    required this.logicalBytes,
    required this.cancelled,
  });

  final List<StorageNode> nodes;
  final List<String> inaccessible;
  final int entries;
  final int logicalBytes;
  final bool cancelled;
}

Future<_RootOutput> _scanRootInIsolate(_RootInput input) async {
  final control = ReceivePort();
  final walker = _RootWalker(input);
  control.listen((_) => walker.cancelled = true);
  input.progress.send(control.sendPort);
  try {
    final nodes = <StorageNode>[];
    for (final location in input.locations) {
      final node = await walker.scanLocation(location);
      if (walker.cancelled || node == null) {
        return _RootOutput(
          nodes: const [],
          inaccessible: const [],
          entries: walker.entries,
          logicalBytes: walker.logicalBytes,
          cancelled: true,
        );
      }
      nodes.add(node);
    }
    return _RootOutput(
      nodes: nodes,
      inaccessible: walker.inaccessible,
      entries: walker.entries,
      logicalBytes: walker.logicalBytes,
      cancelled: false,
    );
  } finally {
    control.close();
  }
}

class _CategoryAccumulator {
  final List<int> logical = List.filled(StorageCategory.values.length, 0);
  final List<int> allocated = List.filled(StorageCategory.values.length, 0);
  final List<int> files = List.filled(StorageCategory.values.length, 0);
  final List<bool> seen = List.filled(StorageCategory.values.length, false);

  void add(
    StorageCategory category, {
    required int logicalBytes,
    required int allocatedBytes,
    required int fileCount,
  }) {
    final index = category.index;
    seen[index] = true;
    logical[index] += logicalBytes;
    allocated[index] += allocatedBytes;
    files[index] += fileCount;
  }

  Map<StorageCategory, StorageCategoryTotals> build({required bool ffi}) => {
    for (final category in StorageCategory.values)
      if (seen[category.index])
        category: StorageCategoryTotals(
          logicalBytes: logical[category.index],
          allocatedBytes: ffi ? allocated[category.index] : null,
          fileCount: files[category.index],
        ),
  };
}

class _Frame {
  _Frame({
    required this.path,
    required this.relative,
    required this.context,
    required this.depth,
    required this.classification,
    required this.modified,
    required this.fold,
  });

  final String path;
  final String relative;
  final StorageMatchContext context;
  final int depth;
  final StorageClassification classification;
  final DateTime? modified;

  /// Measured, no node kept (aggregate-only subtree).
  final bool fold;

  bool listed = false;
  bool listFailed = false;
  bool truncated = false;
  final List<_Frame> pending = [];
  final List<StorageNode> children = [];
  int logical = 0;
  int allocated = 0;
  int files = 0;
  int links = 0;
  int unreadable = 0;
  int icloud = 0;

  void absorb(StorageNode node, {required bool keep}) {
    logical += node.logicalBytes;
    allocated += node.allocatedBytes ?? 0;
    files += node.fileCount;
    links += node.linkCount;
    unreadable += node.inaccessibleCount;
    icloud += node.icloudCount;
    if (node.truncated) truncated = true;
    if (keep) children.add(node);
  }
}

class _RootWalker {
  _RootWalker(this.input)
    : categorizer = StorageCategorizer(input.registry),
      ffi = input.stat.available;

  final _RootInput input;
  final StorageCategorizer categorizer;
  final bool ffi;
  bool cancelled = false;
  int entries = 0;
  int logicalBytes = 0;
  int _sinceProgress = 0;
  final List<String> inaccessible = [];
  final Set<String> _hardLinks = {};

  StorageRootRegistry get registry => input.registry;

  void _tick() {
    _sinceProgress++;
    if (_sinceProgress >= StorageScanner.progressInterval) {
      _sinceProgress = 0;
      input.progress.send(<int>[entries, logicalBytes]);
    }
  }

  static int _compare(StorageNode a, StorageNode b) {
    final bySize = b.logicalBytes.compareTo(a.logicalBytes);
    return bySize != 0 ? bySize : a.path.compareTo(b.path);
  }

  String _display(StorageContainer container, String relative) {
    final placeholder = StorageContainers.placeholderOf(container);
    return relative.isEmpty ? placeholder : '$placeholder/$relative';
  }

  /// Measures one directory of the root; null when cancelled.
  Future<StorageNode?> scanLocation(_LocationInput location) async {
    final totals = _CategoryAccumulator();
    final type = _typeOf(location.path);
    final classification = categorizer.classify(
      location.path,
      StorageEntryKind.directory,
    );
    StorageNode bare(
      StorageEntryKind kind, {
      int links = 0,
      int unreadable = 0,
    }) => StorageNode(
      path: location.path,
      relativePath: location.relative,
      container: location.container,
      rootId: input.rootId,
      kind: kind,
      logicalBytes: 0,
      allocatedBytes: ffi ? 0 : null,
      linkCount: links,
      inaccessibleCount: unreadable,
      category: classification.category,
      deletionClass: StorageDeletionClass.never,
      ruleId: classification.ruleId,
    );

    switch (type) {
      case null:
        inaccessible.add(_display(location.container, location.relative));
        return bare(StorageEntryKind.inaccessible, unreadable: 1);
      case FileSystemEntityType.notFound:
        // An absent root counts 0 bytes.
        return bare(StorageEntryKind.directory);
      case FileSystemEntityType.link:
        // Never followed, even as a root.
        return bare(StorageEntryKind.link, links: 1);
      case FileSystemEntityType.directory:
        break;
      default:
        // A file where a directory is expected: measured as one entry.
        final leaf = _fileNode(
          location.path,
          location.relative,
          location.container,
          p.basename(location.path),
          registry.contextFor(p.dirname(location.path)),
          totals,
        );
        return _withTotals(leaf, totals);
    }

    final context = registry.contextFor(location.path);
    final rootFrame = _Frame(
      path: location.path,
      relative: location.relative,
      context: context,
      depth: 0,
      classification: classification,
      modified: _modified(location.path),
      fold: context.aggregate,
    );
    final stack = <_Frame>[rootFrame];
    StorageNode? result;
    while (stack.isNotEmpty) {
      if (cancelled) return null;
      final frame = stack.last;
      if (!frame.listed) {
        frame.listed = true;
        if (frame.depth >= input.maxDepth || entries >= input.maxEntries) {
          frame.truncated = true;
        } else {
          await _list(frame, location, totals);
          if (cancelled) return null;
        }
      }
      if (frame.pending.isNotEmpty) {
        stack.add(frame.pending.removeLast());
        continue;
      }
      stack.removeLast();
      final node = _directoryNode(frame, location.container, totals);
      if (stack.isEmpty) {
        result = node;
      } else {
        stack.last.absorb(node, keep: !frame.fold);
      }
    }
    return _withTotals(result!, totals);
  }

  StorageNode _withTotals(StorageNode node, _CategoryAccumulator totals) =>
      StorageNode(
        path: node.path,
        relativePath: node.relativePath,
        container: node.container,
        rootId: node.rootId,
        kind: node.kind,
        logicalBytes: node.logicalBytes,
        allocatedBytes: node.allocatedBytes,
        fileCount: node.fileCount,
        linkCount: node.linkCount,
        inaccessibleCount: node.inaccessibleCount,
        icloudCount: node.icloudCount,
        modified: node.modified,
        category: node.category,
        deletionClass: node.deletionClass,
        ruleId: node.ruleId,
        children: node.children,
        truncated: node.truncated,
        byCategory: totals.build(ffi: ffi),
      );

  static FileSystemEntityType? _typeOf(String path) {
    try {
      return FileSystemEntity.typeSync(path, followLinks: false);
    } on FileSystemException {
      return null;
    }
  }

  static DateTime? _modified(String path) {
    try {
      final stat = FileStat.statSync(path);
      return stat.type == FileSystemEntityType.notFound ? null : stat.modified;
    } on FileSystemException {
      return null;
    }
  }

  Future<void> _list(
    _Frame frame,
    _LocationInput location,
    _CategoryAccumulator totals,
  ) async {
    try {
      await for (final entity in input.lister(Directory(frame.path))) {
        if (cancelled) return;
        if (entries >= input.maxEntries) {
          frame.truncated = true;
          return;
        }
        final childPath = entity.path;
        if (location.excluded.isNotEmpty &&
            location.excluded.contains(storageCanonicalPath(childPath))) {
          continue;
        }
        entries++;
        _tick();
        final name = p.basename(childPath);
        final relative = frame.relative.isEmpty
            ? name
            : '${frame.relative}/$name';
        if (entity is Link) {
          _leaf(
            frame,
            totals,
            childPath,
            relative,
            location.container,
            name,
            StorageEntryKind.link,
          );
        } else if (entity is Directory) {
          final child = registry.childContext(frame.context, name);
          frame.pending.add(
            _Frame(
              path: childPath,
              relative: relative,
              context: child,
              depth: frame.depth + 1,
              classification: categorizer.classifyChild(
                frame.context,
                name,
                StorageEntryKind.directory,
              ),
              modified: _modified(childPath),
              fold: frame.fold || child.aggregate,
            ),
          );
        } else {
          final node = _fileNode(
            childPath,
            relative,
            location.container,
            name,
            frame.context,
            totals,
          );
          frame.absorb(node, keep: !frame.fold);
        }
      }
    } on IOException catch (_) {
      // FileSystemException (EACCES, ENOENT while listing, …): counted.
      frame.listFailed = true;
      frame.unreadable++;
      inaccessible.add(_display(location.container, frame.relative));
    }
  }

  void _leaf(
    _Frame frame,
    _CategoryAccumulator totals,
    String path,
    String relative,
    StorageContainer container,
    String name,
    StorageEntryKind kind,
  ) {
    final classification = categorizer.classifyChild(frame.context, name, kind);
    totals.add(
      classification.category,
      logicalBytes: 0,
      allocatedBytes: 0,
      fileCount: 0,
    );
    if (kind == StorageEntryKind.inaccessible) {
      inaccessible.add(_display(container, relative));
    }
    frame.absorb(
      StorageNode(
        path: path,
        relativePath: relative,
        container: container,
        rootId: input.rootId,
        kind: kind,
        logicalBytes: 0,
        allocatedBytes: ffi ? 0 : null,
        linkCount: kind == StorageEntryKind.link ? 1 : 0,
        inaccessibleCount: kind == StorageEntryKind.inaccessible ? 1 : 0,
        icloudCount: kind == StorageEntryKind.icloudPlaceholder ? 1 : 0,
        category: classification.category,
        deletionClass: classification.deletionClass,
        ruleId: classification.ruleId,
      ),
      keep: !frame.fold,
    );
  }

  StorageNode _fileNode(
    String path,
    String relative,
    StorageContainer container,
    String name,
    StorageMatchContext parent,
    _CategoryAccumulator totals,
  ) {
    StorageNode zero(StorageEntryKind kind, DateTime? modified) {
      final classification = categorizer.classifyChild(parent, name, kind);
      totals.add(
        classification.category,
        logicalBytes: 0,
        allocatedBytes: 0,
        fileCount: 0,
      );
      if (kind == StorageEntryKind.inaccessible) {
        inaccessible.add(_display(container, relative));
      }
      return StorageNode(
        path: path,
        relativePath: relative,
        container: container,
        rootId: input.rootId,
        kind: kind,
        logicalBytes: 0,
        allocatedBytes: ffi ? 0 : null,
        inaccessibleCount: kind == StorageEntryKind.inaccessible ? 1 : 0,
        icloudCount: kind == StorageEntryKind.icloudPlaceholder ? 1 : 0,
        modified: modified,
        category: classification.category,
        deletionClass: classification.deletionClass,
        ruleId: classification.ruleId,
      );
    }

    if (StorageLayout.icloudPlaceholder.hasMatch(name)) {
      return zero(StorageEntryKind.icloudPlaceholder, _modified(path));
    }
    final FileStat stat;
    try {
      stat = FileStat.statSync(path);
    } on FileSystemException {
      return zero(StorageEntryKind.inaccessible, null);
    }
    if (stat.type == FileSystemEntityType.notFound) {
      // Gone between the listing and the stat: unreadable for this scan.
      return zero(StorageEntryKind.inaccessible, null);
    }
    final logical = stat.size < 0 ? 0 : stat.size;
    var allocated = 0;
    if (ffi) {
      final info = input.stat.lstat(path);
      if (info == null) {
        allocated = logical;
      } else if (info.nlink > 1 && !_hardLinks.add('${info.dev}:${info.ino}')) {
        allocated = 0;
      } else {
        allocated = info.allocatedBytes;
      }
    }
    final classification = categorizer.classifyChild(
      parent,
      name,
      StorageEntryKind.file,
    );
    totals.add(
      classification.category,
      logicalBytes: logical,
      allocatedBytes: allocated,
      fileCount: 1,
    );
    logicalBytes += logical;
    return StorageNode(
      path: path,
      relativePath: relative,
      container: container,
      rootId: input.rootId,
      kind: StorageEntryKind.file,
      logicalBytes: logical,
      allocatedBytes: ffi ? allocated : null,
      fileCount: 1,
      modified: stat.modified,
      category: classification.category,
      deletionClass: classification.deletionClass,
      ruleId: classification.ruleId,
    );
  }

  StorageNode _directoryNode(
    _Frame frame,
    StorageContainer container,
    _CategoryAccumulator totals,
  ) {
    final failed = frame.listFailed;
    frame.children.sort(_compare);
    return StorageNode(
      path: frame.path,
      relativePath: frame.relative,
      container: container,
      rootId: input.rootId,
      kind: failed ? StorageEntryKind.inaccessible : StorageEntryKind.directory,
      logicalBytes: frame.logical,
      allocatedBytes: ffi ? frame.allocated : null,
      fileCount: frame.files,
      linkCount: frame.links,
      inaccessibleCount: frame.unreadable,
      icloudCount: frame.icloud,
      modified: frame.modified,
      category: frame.classification.category,
      deletionClass: failed
          ? StorageDeletionClass.never
          : frame.classification.deletionClass,
      ruleId: failed ? 'NEVER.inaccessible' : frame.classification.ruleId,
      children: List.unmodifiable(frame.children),
      truncated: frame.truncated,
    );
  }
}
