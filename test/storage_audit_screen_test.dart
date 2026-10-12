import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/repositories/storage_maintenance_repository.dart';
import 'package:neostation/screens/storage/storage_audit_screen.dart';
import 'package:neostation/screens/storage/storage_cleanup_preview_screen.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:neostation/services/rpcs3_save_exchange_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/services/storage/storage_cleanup_planner.dart';
import 'package:neostation/services/storage/storage_deletion_manager.dart';
import 'package:neostation/services/storage/storage_orphan_detector.dart';
import 'package:neostation/services/storage/storage_report.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:neostation/services/storage/storage_scanner.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

/// Tests C and I of docs/storage-audit-cleanup.md § 6 (screens, § 3.10):
/// the analysis at opening, on return to the foreground and on demand, its
/// error kept with its technical text, its progress and cancellation; the
/// three levels; the preview with levels 1–2 ticked and level 3 never,
/// warning badges and totals; the confirmation that repeats warnings, count
/// and size, nothing deleted without it; the result (counts, refusals with
/// raw code and path, journal) and the new analysis on return; the export in
/// aggregates or detailed, and a failed share. The scanner, detector,
/// planner, deletion manager and sharer are fakes: nothing is deleted.
const _gamepads = MethodChannel('xyz.luan/gamepads');
const _paths = MethodChannel('plugins.flutter.io/path_provider');
const _bridge = MethodChannel('neostation/libretro_internal');

const _home =
    '/var/mobile/Containers/Data/Application/0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0';
const _containers = StorageContainers(
  documents: '$_home/Documents',
  applicationSupport: '$_home/Library/Application Support',
  caches: '$_home/Library/Caches',
  temporary: '$_home/tmp',
);
final _modified = DateTime.utc(2026, 10, 1, 8);

String _abs(StorageContainer container, String relative) => relative.isEmpty
    ? _containers.pathOf(container)
    : p.join(_containers.pathOf(container), relative);

String en(String key, [Map<String, Object?> values = const {}]) =>
    StorageLocale.forLocale(const Locale('en'), key, values);

String size(int bytes) => Rpcs3SaveExchangeService.formatBytes(bytes);

StorageSessionGuard _idleGuard() => StorageSessionGuard(
  launchActive: () => false,
  libretroActive: () async => false,
  dolphinMarkerPresent: () async => false,
  libretroJournalUnfinished: () async => false,
);

StorageNode _node(
  String rootId,
  StorageContainer container,
  String relative, {
  StorageEntryKind kind = StorageEntryKind.directory,
  int bytes = 0,
  int files = 0,
  StorageCategory category = StorageCategory.unknown,
  List<StorageNode> children = const [],
  Map<StorageCategory, StorageCategoryTotals> byCategory = const {},
}) => StorageNode(
  path: _abs(container, relative),
  relativePath: relative,
  container: container,
  rootId: rootId,
  kind: kind,
  logicalBytes: bytes,
  allocatedBytes: bytes,
  fileCount: kind == StorageEntryKind.file ? 1 : files,
  modified: _modified,
  category: category,
  deletionClass: StorageDeletionClass.never,
  children: children,
  byCategory: byCategory,
);

StorageNode _file(
  String rootId,
  StorageContainer container,
  String relative,
  int bytes,
  StorageCategory category,
) => _node(
  rootId,
  container,
  relative,
  kind: StorageEntryKind.file,
  bytes: bytes,
  category: category,
);

const _games = 6000000000;
const _cache = 2000000000;
const _picked = 700000000;
const _saves = 20000000;

/// A measured container: games, libretro saves, the Library (with the
/// hidden folder a scanner never details), the RPCS3 cache, NeoSwap (not
/// listable) and a picker copy in tmp/.
StorageScanResult _scanResult({bool ffi = true, DateTime? startedAt}) {
  final library = _node(
    'INV-15',
    StorageContainer.documents,
    'Library',
    bytes: 1300,
    files: 2,
    category: StorageCategory.userContent,
    children: [
      _file(
        'INV-15',
        StorageContainer.documents,
        'Library/Books/Dune.epub',
        1000,
        StorageCategory.userContent,
      ),
      // Never produced by the scanner (folded into its parent); the screen
      // leaves it out anyway.
      _node(
        'INV-15',
        StorageContainer.documents,
        'Library/${LibrarySourceFiles.folderName}',
        bytes: 300,
        files: 1,
        category: StorageCategory.userContent,
      ),
    ],
  );
  final roots = [
    _node(
      'INV-01',
      StorageContainer.documents,
      'roms',
      bytes: _games,
      files: 3,
      category: StorageCategory.games,
      byCategory: const {
        StorageCategory.games: StorageCategoryTotals(
          logicalBytes: _games,
          allocatedBytes: _games,
          fileCount: 3,
        ),
      },
      children: [
        _node(
          'INV-01',
          StorageContainer.documents,
          'roms/snes',
          bytes: 4000000000,
          files: 2,
          category: StorageCategory.games,
          children: [
            _file(
              'INV-01',
              StorageContainer.documents,
              'roms/snes/Super Mario World.sfc',
              3000000000,
              StorageCategory.games,
            ),
            _file(
              'INV-01',
              StorageContainer.documents,
              'roms/snes/Zelda.sfc',
              1000000000,
              StorageCategory.games,
            ),
          ],
        ),
        _node(
          'INV-01',
          StorageContainer.documents,
          'roms/gba',
          bytes: 2000000000,
          files: 1,
          category: StorageCategory.games,
        ),
      ],
    ),
    _node(
      'INV-14',
      StorageContainer.documents,
      'Libretro',
      bytes: _saves,
      files: 4,
      category: StorageCategory.saves,
      byCategory: const {
        StorageCategory.saves: StorageCategoryTotals(
          logicalBytes: _saves,
          allocatedBytes: _saves,
          fileCount: 4,
        ),
      },
    ),
    library,
    _node(
      'INV-18',
      StorageContainer.applicationSupport,
      'NeoStation/RPCS3/Cache',
      bytes: _cache,
      files: 10,
      category: StorageCategory.caches,
      byCategory: const {
        StorageCategory.caches: StorageCategoryTotals(
          logicalBytes: _cache,
          allocatedBytes: _cache,
          fileCount: 10,
        ),
      },
    ),
    _node(
      'INV-27',
      StorageContainer.caches,
      'NeoSwap-v1',
      category: StorageCategory.neoSwap,
    ),
    _node(
      'INV-28',
      StorageContainer.temporary,
      '',
      bytes: _picked,
      files: 1,
      category: StorageCategory.temporary,
      byCategory: const {
        StorageCategory.temporary: StorageCategoryTotals(
          logicalBytes: _picked,
          allocatedBytes: _picked,
          fileCount: 1,
        ),
      },
      children: [
        _file(
          'INV-28',
          StorageContainer.temporary,
          'Picked Game.zip',
          _picked,
          StorageCategory.temporary,
        ),
      ],
    ),
  ];
  const total = _games + _saves + 1300 + _cache + _picked;
  return StorageScanResult(
    containers: _containers,
    roots: roots,
    logicalBytes: total,
    allocatedBytes: ffi ? 8800000000 : null,
    freeBytes: ffi ? 12400000000 : null,
    volumeBytes: ffi ? 128000000000 : null,
    statViaFfi: ffi,
    inaccessible: const [],
    startedAt: startedAt ?? DateTime(2026, 10, 12, 9, 30),
    duration: const Duration(seconds: 3),
    entries: 42,
    byCategory: const {
      StorageCategory.games: StorageCategoryTotals(
        logicalBytes: _games,
        allocatedBytes: _games,
        fileCount: 3,
      ),
      StorageCategory.saves: StorageCategoryTotals(
        logicalBytes: _saves,
        allocatedBytes: _saves,
        fileCount: 4,
      ),
      StorageCategory.caches: StorageCategoryTotals(
        logicalBytes: _cache,
        allocatedBytes: _cache,
        fileCount: 10,
      ),
      StorageCategory.temporary: StorageCategoryTotals(
        logicalBytes: _picked,
        allocatedBytes: _picked,
        fileCount: 1,
      ),
    },
  );
}

StorageOrphanEntry _orphan(
  StorageOrphanKind kind,
  StorageContainer container,
  String relative,
  int bytes, {
  bool selectable = true,
}) => StorageOrphanEntry(
  kind: kind,
  path: _abs(container, relative),
  relativePath: relative,
  container: container,
  rootId: 'INV-05',
  entryKind: StorageEntryKind.file,
  logicalBytes: bytes,
  modified: _modified,
  category: StorageCategory.media,
  deletionClass: StorageDeletionClass.regenerableAtCost,
  key: p.basenameWithoutExtension(relative),
  selectable: selectable,
);

final _orphanReport = StorageOrphanReport(
  media: [
    _orphan(
      StorageOrphanKind.media,
      StorageContainer.documents,
      'media/snes/box2d/Deleted.png',
      10,
    ),
    _orphan(
      StorageOrphanKind.media,
      StorageContainer.documents,
      'media/snes/wheels/Deleted.png',
      20,
    ),
  ],
  metadata: const [
    StorageOrphanMetadataKey('snes', 'Deleted.sfc'),
    StorageOrphanMetadataKey('snes', 'Gone.sfc'),
    StorageOrphanMetadataKey('gba', 'Old.gba'),
  ],
  libraryCovers: [
    _orphan(
      StorageOrphanKind.libraryCover,
      StorageContainer.applicationSupport,
      'Library/covers/old.png',
      5,
    ),
  ],
  libretroSaves: [
    _orphan(
      StorageOrphanKind.libretroSave,
      StorageContainer.documents,
      'Libretro/Saves/Snes9x/Gone.srm',
      8,
      selectable: false,
    ),
  ],
  duplicates: [
    StorageDuplicateGroup(
      name: 'Zelda.sfc',
      size: 1000,
      copies: [
        StorageDuplicateCopy(
          path: _abs(StorageContainer.documents, 'roms/snes/Zelda.sfc'),
          relativePath: 'roms/snes/Zelda.sfc',
          container: StorageContainer.documents,
          rootId: 'INV-01',
          logicalBytes: 1000,
          modified: _modified,
          referenced: true,
          selectable: false,
          keep: StorageDuplicateKeep.referenced,
        ),
        StorageDuplicateCopy(
          path: _abs(StorageContainer.documents, 'MyGames/snes/Zelda.sfc'),
          relativePath: 'MyGames/snes/Zelda.sfc',
          container: StorageContainer.documents,
          rootId: 'INV-01',
          logicalBytes: 1000,
          modified: _modified,
          referenced: false,
          selectable: true,
        ),
      ],
    ),
  ],
);

StorageCleanupCandidate _candidate(
  String rootId,
  StorageContainer container,
  String relative,
  int bytes, {
  required StorageCleanupLevel level,
  required String reasonKey,
  StorageEntryKind kind = StorageEntryKind.file,
  int fileCount = 1,
  List<String> warnings = const [],
  StorageCandidateSource source = StorageCandidateSource.rule,
  StorageCategory category = StorageCategory.temporary,
  String? pairedRelative,
}) => StorageCleanupCandidate(
  path: _abs(container, relative),
  kind: kind,
  logicalBytes: bytes,
  modified: _modified,
  category: category,
  deletionClass: level == StorageCleanupLevel.confirmed
      ? StorageDeletionClass.confirmation
      : StorageDeletionClass.temporaryWhenIdle,
  reasonKey: reasonKey,
  warningKeys: warnings,
  // As the planner sets it: levels 1 and 2 preselected, level 3 never.
  preselected: level != StorageCleanupLevel.confirmed,
  pairedPath: pairedRelative == null ? null : _abs(container, pairedRelative),
  pairedDisplayPath: pairedRelative == null
      ? null
      : '${StorageContainers.placeholderOf(container)}/$pairedRelative',
  level: level,
  source: source,
  rootId: rootId,
  container: container,
  relativePath: relative,
  fileCount: fileCount,
);

final _pickedCopy = _candidate(
  'INV-28',
  StorageContainer.temporary,
  'Picked Game.zip',
  _picked,
  level: StorageCleanupLevel.safe,
  reasonKey: StorageLocale.catTemporary,
);
final _rpcs3Cache = _candidate(
  'INV-18',
  StorageContainer.applicationSupport,
  'NeoStation/RPCS3/Cache',
  _cache,
  level: StorageCleanupLevel.regenerable,
  reasonKey: StorageLocale.catCaches,
  kind: StorageEntryKind.directory,
  fileCount: 10,
  warnings: const [StorageLocale.rpcs3CacheWarning],
  category: StorageCategory.caches,
);
final _orphanMedia = _candidate(
  'INV-05',
  StorageContainer.documents,
  'media/snes/box2d/Deleted.png',
  10,
  level: StorageCleanupLevel.regenerable,
  reasonKey: StorageLocale.orphanMedia,
  warnings: const [StorageLocale.mediaQuotaWarning],
  source: StorageCandidateSource.orphanMedia,
  category: StorageCategory.media,
);
final _diagnostics = _candidate(
  'INV-06',
  StorageContainer.documents,
  'Diagnostics/rpcs3_startup_debug.txt',
  5000,
  level: StorageCleanupLevel.confirmed,
  reasonKey: StorageLocale.catLogs,
  warnings: const [StorageLocale.diagnosticsWarning],
  category: StorageCategory.logs,
);
final _duplicate = _candidate(
  'INV-01',
  StorageContainer.documents,
  'MyGames/snes/Zelda.sfc',
  1000,
  level: StorageCleanupLevel.confirmed,
  reasonKey: StorageLocale.duplicates,
  warnings: const [StorageLocale.duplicateWarning],
  source: StorageCandidateSource.duplicate,
  category: StorageCategory.games,
  pairedRelative: 'roms/snes/Zelda.sfc',
);

StorageCleanupPlan _plan(StorageCleanupLevel level, {bool blocked = false}) {
  if (blocked) {
    return StorageCleanupPlan(
      level: level,
      builtAt: DateTime(2026, 10, 12, 10),
      candidates: const [],
      metadataKeys: const [],
      refusals: const [
        StoragePlanRefusal(
          path: StoragePlanRefusal.wholePlan,
          reason: StorageRefusalReason.sessionActive,
        ),
      ],
      containers: _containers,
      session: const StorageSessionState(launchActive: true),
    );
  }
  return StorageCleanupPlan(
    level: level,
    builtAt: DateTime(2026, 10, 12, 10),
    candidates: [
      _duplicate,
      _orphanMedia,
      _diagnostics,
      _rpcs3Cache,
      _pickedCopy,
    ].where((c) => c.level.index <= level.index).toList(),
    metadataKeys: level == StorageCleanupLevel.safe
        ? const []
        : _orphanReport.metadata,
    refusals: level == StorageCleanupLevel.confirmed
        ? [
            StoragePlanRefusal(
              path: _abs(
                StorageContainer.documents,
                'Libretro/Logs/session.log',
              ),
              reason: StorageRefusalReason.sessionActive,
              displayPath: '<Documents>/Libretro/Logs/session.log',
              rootId: 'INV-14',
            ),
          ]
        : const [],
    containers: _containers,
  );
}

class _FakeScanner extends StorageScanner {
  _FakeScanner(this.results);

  /// Results (or errors to throw), in order; the last one repeats.
  final List<Object> results;
  int calls = 0;
  final registries = <StorageRootRegistry>[];

  /// When set, each scan waits for it (or for its cancellation).
  Completer<void>? gate;
  List<StorageScanProgress> progress = const [];

  @override
  Future<StorageScanResult> scan(
    StorageRootRegistry registry, {
    StorageScanCancelToken? cancel,
    void Function(StorageScanProgress)? onProgress,
  }) async {
    calls++;
    registries.add(registry);
    for (final update in progress) {
      onProgress?.call(update);
    }
    final wait = gate;
    if (wait != null) {
      await Future.any<void>([
        wait.future,
        if (cancel != null) cancel.whenCancelled,
      ]);
    }
    final next =
        results[calls - 1 < results.length ? calls - 1 : results.length - 1];
    if (next is! StorageScanResult) throw next;
    if (cancel?.isCancelled ?? false) {
      return StorageScanResult(
        containers: next.containers,
        roots: const [],
        logicalBytes: 0,
        statViaFfi: next.statViaFfi,
        inaccessible: const [],
        startedAt: next.startedAt,
        duration: Duration.zero,
        cancelled: true,
      );
    }
    return next;
  }
}

class _FakeDetector extends StorageOrphanDetector {
  _FakeDetector(StorageRootRegistry registry, this.report)
    : super(
        database: () async => throw StateError('no database in widget tests'),
        registry: registry,
      );

  StorageOrphanReport report;
  final hashes = <bool>[];

  @override
  Future<StorageOrphanReport> detect(
    StorageScanResult scan, {
    bool hashDuplicates = false,
    StorageScanCancelToken? cancel,
  }) async {
    hashes.add(hashDuplicates);
    return report;
  }
}

class _FakePlanner extends StorageCleanupPlanner {
  _FakePlanner(StorageRootRegistry registry)
    : super(registry: registry, guard: _idleGuard());

  /// A game or an import is running: the whole plan is refused.
  bool blocked = false;
  final levels = <StorageCleanupLevel>[];
  final reports = <StorageOrphanReport>[];

  /// When set, each plan waits for it.
  Completer<void>? gate;

  @override
  Future<StorageCleanupPlan> plan(
    StorageScanResult scan,
    StorageOrphanReport orphans,
    StorageCleanupLevel level,
  ) async {
    levels.add(level);
    reports.add(orphans);
    final wait = gate;
    if (wait != null) await wait.future;
    return _plan(level, blocked: blocked);
  }
}

class _FakeDeletionManager extends StorageDeletionManager {
  _FakeDeletionManager(StorageRootRegistry registry)
    : super(
        registry: registry,
        guard: _idleGuard(),
        deleteFile: (path) async =>
            throw StateError('nothing is deleted in widget tests: $path'),
        journalDirectory: () async => throw StateError('no journal here'),
      );

  final selections = <Set<String>>[];
  final plans = <StorageCleanupPlan>[];
  final maintenances = <StorageMaintenanceRepository?>[];
  Completer<void>? gate;
  List<StorageDeletionProgress> progress = const [];
  Object? failure;

  StorageDeletionResult result = StorageDeletionResult(
    deletedFiles: 11,
    deletedBytes: 2700000010,
    skippedChanged: 1,
    skippedMissing: 2,
    refusals: [
      StoragePlanRefusal(
        path: _abs(StorageContainer.documents, 'Diagnostics/locked.txt'),
        reason: StorageRefusalReason.accessDenied,
        displayPath: '<Documents>/Diagnostics/locked.txt',
        rootId: 'INV-06',
        detail: 'OS Error: Permission denied, errno = 13',
        errorCode: 13,
      ),
      StoragePlanRefusal(
        path: _abs(StorageContainer.temporary, 'Inbox'),
        reason: StorageRefusalReason.notEmpty,
        displayPath: '<tmp>/Inbox',
        rootId: 'INV-28',
        errorCode: 66,
      ),
    ],
    metadata: const StorageMetadataDeletion(
      deleted: 3,
      skippedNotOrphan: 0,
      backupPath: '/backup/data-20261012-101500.sqlite',
    ),
    journalPath:
        '$_home/Documents/Diagnostics/storage-cleanup-20261012-101500.jsonl',
    journalDisplayPath:
        '<Documents>/Diagnostics/storage-cleanup-20261012-101500.jsonl',
    cancelled: false,
  );

  @override
  Future<StorageDeletionResult> execute(
    StorageCleanupPlan plan, {
    required Set<String> selectedPaths,
    StorageMaintenanceRepository? maintenance,
    StorageCacheClearer? clearLibraryCaches,
    void Function(StorageDeletionProgress)? onProgress,
    StorageScanCancelToken? cancel,
  }) async {
    selections.add(Set.of(selectedPaths));
    plans.add(plan);
    maintenances.add(maintenance);
    for (final update in progress) {
      onProgress?.call(update);
    }
    final wait = gate;
    if (wait != null) {
      await Future.any<void>([
        wait.future,
        if (cancel != null) cancel.whenCancelled,
      ]);
    }
    final error = failure;
    if (error != null) throw error;
    if (cancel?.isCancelled ?? false) {
      return StorageDeletionResult(
        deletedFiles: 4,
        deletedBytes: 400,
        skippedChanged: 0,
        skippedMissing: 0,
        refusals: const [],
        journalPath: result.journalPath,
        journalDisplayPath: result.journalDisplayPath,
        cancelled: true,
      );
    }
    return result;
  }
}

class _FakeSharer extends StorageReportSharer {
  final shared = <({String content, String fileName})>[];
  Object? failure;

  @override
  Future<void> share(
    String content, {
    required String fileName,
    Rect? origin,
  }) async {
    final error = failure;
    if (error != null) throw error;
    shared.add((content: content, fileName: fileName));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  late StorageRootRegistry registry;
  late _FakeScanner scanner;
  late _FakeDetector detector;
  late _FakePlanner planner;
  late _FakeDeletionManager manager;
  late _FakeSharer sharer;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    registry = StorageRootRegistry(_containers);
    scanner = _FakeScanner([_scanResult()]);
    detector = _FakeDetector(registry, _orphanReport);
    planner = _FakePlanner(registry);
    manager = _FakeDeletionManager(registry);
    sharer = _FakeSharer();
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(_paths, (_) async => '/nonexistent');
    messenger.setMockMethodCallHandler(_bridge, (call) async => false);
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(_gamepads, null);
    messenger.setMockMethodCallHandler(_paths, null);
    messenger.setMockMethodCallHandler(_bridge, null);
  });

  Future<void> pumpAudit(
    WidgetTester tester, {
    Locale locale = const Locale('en'),
    bool settle = true,
  }) async {
    tester.view.physicalSize = const Size(1200, 6000);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        locale: locale,
        supportedLocales: [locale],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: StorageAuditScreen(
          scanner: scanner,
          orphanDetector: detector,
          registry: registry,
          planner: planner,
          deletionManager: manager,
          sharer: sharer,
        ),
      ),
    );
    if (settle) await tester.pumpAndSettle();
  }

  Future<void> tapKey(WidgetTester tester, String key) async {
    final finder = find.byKey(ValueKey(key));
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  Future<void> openPreview(WidgetTester tester, StorageCleanupLevel level) =>
      tapKey(tester, 'storage-level-${level.name}');

  bool? ticked(WidgetTester tester, String path) => tester
      .widget<CheckboxListTile>(find.byKey(ValueKey('storage-candidate-$path')))
      .value;

  group('analysis', () {
    testWidgets('runs at opening and shows summary, categories and folders', (
      tester,
    ) async {
      await pumpAudit(tester);
      expect(scanner.calls, 1);
      expect(scanner.registries.single, same(registry));
      expect(detector.hashes, [false]);

      final scan = _scanResult();
      expect(
        find.text(
          en(StorageLocale.totalLogical, {'size': size(scan.logicalBytes)}),
        ),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.totalAllocated, {'size': size(8800000000)})),
        findsOneWidget,
      );
      expect(
        find.text(
          en(StorageLocale.freeSpace, {
            'free': size(12400000000),
            'total': size(128000000000),
          }),
        ),
        findsOneWidget,
      );
      expect(find.text(en(StorageLocale.gapExplanation)), findsOneWidget);
      // Categories A–I plus the index files and the unidentified data.
      for (final category in StorageCategory.values) {
        expect(
          find.byKey(ValueKey('storage-category-${category.name}')),
          findsOneWidget,
        );
      }
      final games = find.byKey(const ValueKey('storage-category-games'));
      expect(
        find.descendant(
          of: games,
          matching: find.text(en(StorageLocale.catGames)),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(of: games, matching: find.text(size(_games))),
        findsOneWidget,
      );
      // Orphans and duplicates.
      expect(
        find.text(
          en(StorageLocale.orphanMedia, {'count': 2, 'size': size(30)}),
        ),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.orphanMetadata, {'count': 3})),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.orphanCovers, {'count': 1})),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.orphanSavesInfo, {'count': 1})),
        findsOneWidget,
      );
      expect(
        find.text(
          en(StorageLocale.duplicates, {'count': 1, 'size': size(1000)}),
        ),
        findsOneWidget,
      );
      // The limits of § 7 (FFI available: no logical-size fallback).
      for (final key in [
        StorageLocale.limitFreeSpace,
        StorageLocale.limitNeoSwap,
        StorageLocale.limitExtensions,
        StorageLocale.limitLinkedFolders,
        StorageLocale.limitRpcs3Cache,
        StorageLocale.limitDolphinStates,
        StorageLocale.limitScannerOrphans,
        StorageLocale.limitNoAutoPurge,
        StorageLocale.limitUnverified,
      ]) {
        expect(find.byKey(ValueKey('storage-limit-$key')), findsOneWidget);
      }
      expect(
        find.byKey(const ValueKey('storage-limit-${StorageLocale.limitFfi}')),
        findsNothing,
      );
      // The analysis date is kept for the next opening (ISO 8601).
      final preferences = await SharedPreferences.getInstance();
      expect(
        preferences.getString(StorageAuditPreferences.lastScanAt),
        scan.startedAt.toUtc().toIso8601String(),
      );
    });

    testWidgets(
      'logical fallback: no allocated size, no free space, the limit',
      (tester) async {
        scanner = _FakeScanner([_scanResult(ffi: false)]);
        await pumpAudit(tester);
        expect(
          find.text(en(StorageLocale.allocatedUnavailable)),
          findsOneWidget,
        );
        expect(
          find.text(en(StorageLocale.freeSpaceUnavailable)),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('storage-limit-${StorageLocale.limitFfi}')),
          findsOneWidget,
        );
      },
    );

    testWidgets('folders open to depth 2, NeoSwap shows its limit, the hidden '
        'Library folder is never named', (tester) async {
      await pumpAudit(tester);
      final romsPath = _abs(StorageContainer.documents, 'roms');
      expect(find.text('INV-01 · <Documents>/roms'), findsOneWidget);
      expect(
        find.byKey(ValueKey('storage-node-header-$romsPath/snes')),
        findsNothing,
      );

      await tapKey(tester, 'storage-root-header-INV-01');
      expect(
        find.byKey(ValueKey('storage-node-header-$romsPath/snes')),
        findsOneWidget,
      );
      expect(find.text('snes'), findsOneWidget);
      expect(find.text('Zelda.sfc'), findsNothing);
      await tapKey(tester, 'storage-node-header-$romsPath/snes');
      // Depth 2: the games themselves, leaves.
      expect(find.text('Zelda.sfc'), findsOneWidget);
      expect(find.text(size(1000000000)), findsWidgets);
      expect(
        find.byKey(ValueKey('storage-node-header-$romsPath/snes/Zelda.sfc')),
        findsNothing,
      );

      await tapKey(tester, 'storage-root-header-INV-27');
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('storage-root-INV-27')),
          matching: find.text(en(StorageLocale.limitNeoSwap)),
        ),
        findsOneWidget,
      );

      await tapKey(tester, 'storage-root-header-INV-15');
      expect(find.text('Dune.epub'), findsOneWidget);
      expect(find.textContaining(LibrarySourceFiles.folderName), findsNothing);
      expect(find.textContaining('Sources'), findsNothing);
    });

    testWidgets(
      'a return to the foreground and « Analyze again » analyse again',
      (tester) async {
        await pumpAudit(tester);
        expect(scanner.calls, 1);

        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.inactive,
        );
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await tester.pumpAndSettle();
        expect(scanner.calls, 2);
        expect(detector.hashes, [false, false]);

        await tapKey(tester, 'storage-scan-again');
        expect(scanner.calls, 3);
      },
    );

    testWidgets('a failed analysis keeps its technical text and can run again', (
      tester,
    ) async {
      final failure = StateError(
        'PathAccessException: Directory listing failed, path = '
        "'$_home/Documents/roms' (OS Error: Operation not permitted, errno = 1)",
      );
      scanner = _FakeScanner([failure, _scanResult()]);
      await pumpAudit(tester);
      expect(
        find.text(en(StorageLocale.scanFailed, {'error': failure})),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('storage-summary')), findsNothing);
      expect(detector.hashes, isEmpty, reason: 'no detection without a scan');

      await tapKey(tester, 'storage-scan-again');
      expect(scanner.calls, 2);
      expect(find.byKey(const ValueKey('storage-scan-error')), findsNothing);
      expect(find.byKey(const ValueKey('storage-summary')), findsOneWidget);
    });

    testWidgets(
      'progress is shown and a cancelled analysis keeps the last one',
      (tester) async {
        await pumpAudit(tester);
        expect(find.byKey(const ValueKey('storage-summary')), findsOneWidget);

        scanner.gate = Completer<void>();
        scanner.progress = const [
          StorageScanProgress(
            rootsDone: 7,
            rootsTotal: 29,
            entries: 1234,
            bytes: 5000000,
            rootId: 'INV-08',
          ),
        ];
        // The busy indicator spins: pump frames, never settle, until the end.
        final again = find.byKey(const ValueKey('storage-scan-again'));
        await tester.ensureVisible(again);
        await tester.pumpAndSettle();
        await tester.tap(again);
        await tester.pump();
        await tester.pump();
        expect(find.text(en(StorageLocale.scanning)), findsOneWidget);
        final bar = tester.widget<LinearProgressIndicator>(
          find.byKey(const ValueKey('storage-scan-progress')),
        );
        expect(bar.value, closeTo(7 / 29, 1e-9));
        expect(
          find.text(en(StorageLocale.entries, {'count': 1234})),
          findsOneWidget,
        );
        expect(find.text('INV-08 · ${size(5000000)}'), findsOneWidget);
        // The cleanup levels wait for the analysis.
        final level = tester.widget<ListTile>(
          find.byKey(const ValueKey('storage-level-safe')),
        );
        expect(level.enabled, isFalse);

        await tester.ensureVisible(
          find.byKey(const ValueKey('storage-scan-cancel')),
        );
        await tester.tap(find.byKey(const ValueKey('storage-scan-cancel')));
        await tester.pumpAndSettle();
        expect(scanner.calls, 2);
        expect(
          find.byKey(const ValueKey('storage-scan-progress')),
          findsNothing,
        );
        // The previous analysis stays, without a new detection.
        expect(find.byKey(const ValueKey('storage-summary')), findsOneWidget);
        expect(detector.hashes, [false]);
      },
    );

    testWidgets('« Compute checksums » detects again with hashing, saved', (
      tester,
    ) async {
      await pumpAudit(tester);
      await tapKey(tester, 'storage-hash-toggle');
      expect(detector.hashes, [false, true]);
      expect(scanner.calls, 1, reason: 'the measurement is reused');
      final preferences = await SharedPreferences.getInstance();
      expect(
        preferences.getBool(StorageAuditPreferences.hashDuplicates),
        isTrue,
      );
    });

    testWidgets('the saved choices are read back at opening', (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        StorageAuditPreferences.hashDuplicates: true,
        StorageAuditPreferences.detailedExport: true,
        StorageAuditPreferences.lastLevel: 3,
      });
      await pumpAudit(tester);
      expect(detector.hashes, [true]);
      expect(
        tester
            .widget<SwitchListTile>(
              find.byKey(const ValueKey('storage-export-detailed')),
            )
            .value,
        isTrue,
      );
      expect(
        tester
            .widget<ListTile>(
              find.byKey(const ValueKey('storage-level-confirmed')),
            )
            .selected,
        isTrue,
      );
    });
  });

  group('cleanup', () {
    testWidgets('three levels, each with its help and preselection note', (
      tester,
    ) async {
      await pumpAudit(tester);
      for (final level in StorageCleanupLevel.values) {
        final tile = find.byKey(ValueKey('storage-level-${level.name}'));
        expect(tile, findsOneWidget);
        expect(
          find.descendant(
            of: tile,
            matching: find.text(en(StorageLocale.levelKeys[level.name]!)),
          ),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: tile,
            matching: find.text(en(StorageLocale.levelHelpKeys[level.name]!)),
          ),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: tile,
            matching: find.text(
              en(
                level == StorageCleanupLevel.confirmed
                    ? StorageLocale.levelNeverPreselectedNote
                    : StorageLocale.levelPreselectedNote,
              ),
            ),
          ),
          findsOneWidget,
        );
      }

      await openPreview(tester, StorageCleanupLevel.regenerable);
      expect(planner.levels, [StorageCleanupLevel.regenerable]);
      expect(planner.reports.single, same(_orphanReport));
      expect(find.byType(StorageCleanupPreviewScreen), findsOneWidget);
      expect(find.text(en(StorageLocale.levelRegenerable)), findsOneWidget);
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getInt(StorageAuditPreferences.lastLevel), 2);
    });

    testWidgets('levels 1–2 ticked, level 3 never; badges, reasons and totals', (
      tester,
    ) async {
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.confirmed);

      expect(ticked(tester, _pickedCopy.path), isTrue);
      expect(ticked(tester, _rpcs3Cache.path), isTrue);
      expect(ticked(tester, _orphanMedia.path), isTrue);
      expect(ticked(tester, _diagnostics.path), isFalse);
      expect(ticked(tester, _duplicate.path), isFalse);
      expect(
        tester
            .widget<CheckboxListTile>(
              find.byKey(const ValueKey('storage-candidate-metadata')),
            )
            .value,
        isTrue,
      );
      expect(
        find.text(en(StorageLocale.orphanMetadata, {'count': 3})),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.levelNeverPreselectedNote)),
        findsOneWidget,
      );

      // Raw paths, warning badges, the copy the library keeps.
      expect(find.text('<tmp>/Picked Game.zip'), findsOneWidget);
      expect(
        find.byKey(
          ValueKey(
            'storage-warning-${_rpcs3Cache.path}-${StorageLocale.rpcs3CacheWarning}',
          ),
        ),
        findsOneWidget,
      );
      expect(find.text(en(StorageLocale.rpcs3CacheWarning)), findsOneWidget);
      expect(find.text(en(StorageLocale.duplicateWarning)), findsOneWidget);
      expect(find.text(en(StorageLocale.duplicateReferenced)), findsOneWidget);
      expect(find.text('<Documents>/roms/snes/Zelda.sfc'), findsOneWidget);
      // Reason lines: {count}/{size} of the candidates listed under them.
      expect(
        find.text(
          en(StorageLocale.orphanMedia, {'count': 1, 'size': size(10)}),
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          en(StorageLocale.duplicates, {'count': 1, 'size': size(1000)}),
        ),
        findsOneWidget,
      );
      // The session guards' exclusions, greyed, with their raw path.
      expect(find.text(en(StorageLocale.sessionActive)), findsOneWidget);
      expect(
        find.text('<Documents>/Libretro/Logs/session.log'),
        findsOneWidget,
      );

      final preselected = _picked + _cache + 10;
      expect(
        find.text(
          en(StorageLocale.selectedTotal, {
            'count': 4,
            'size': size(preselected),
          }),
        ),
        findsOneWidget,
      );
      await tapKey(tester, 'storage-candidate-${_duplicate.path}');
      expect(ticked(tester, _duplicate.path), isTrue);
      expect(
        find.text(
          en(StorageLocale.selectedTotal, {
            'count': 5,
            'size': size(preselected + 1000),
          }),
        ),
        findsOneWidget,
      );
    });

    testWidgets('the confirmation repeats warnings, count and size; cancelling '
        'deletes nothing', (tester) async {
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.confirmed);
      await tapKey(tester, 'storage-candidate-${_diagnostics.path}');

      await tapKey(tester, 'storage-preview-delete');
      final dialog = find.byKey(const ValueKey('storage-confirm-dialog'));
      expect(dialog, findsOneWidget);
      expect(
        find.descendant(
          of: dialog,
          matching: find.text(en(StorageLocale.confirmTitle)),
        ),
        findsOneWidget,
      );
      final bytes = _picked + _cache + 10 + 5000;
      expect(
        find.descendant(
          of: dialog,
          matching: find.text(
            en(StorageLocale.confirmBody, {'count': 5, 'size': size(bytes)}),
          ),
        ),
        findsOneWidget,
      );
      for (final warning in [
        StorageLocale.rpcs3CacheWarning,
        StorageLocale.mediaQuotaWarning,
        StorageLocale.diagnosticsWarning,
        StorageLocale.metadataBackupNote,
      ]) {
        expect(
          find.descendant(of: dialog, matching: find.text(en(warning))),
          findsOneWidget,
          reason: warning,
        );
      }
      // The duplicate is not ticked: its warning is not repeated.
      expect(
        find.descendant(
          of: dialog,
          matching: find.text(en(StorageLocale.duplicateWarning)),
        ),
        findsNothing,
      );

      await tester.tap(find.byKey(const ValueKey('storage-confirm-cancel')));
      await tester.pumpAndSettle();
      expect(dialog, findsNothing);
      expect(
        manager.selections,
        isEmpty,
        reason: 'nothing without confirmation',
      );
      expect(find.byKey(const ValueKey('storage-result')), findsNothing);
      expect(
        ticked(tester, _diagnostics.path),
        isTrue,
        reason: 'selection kept',
      );
    });

    testWidgets('nothing ticked: nothing to delete', (tester) async {
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.safe);
      await tapKey(tester, 'storage-candidate-${_pickedCopy.path}');
      final delete = tester.widget<FilledButton>(
        find.byKey(const ValueKey('storage-preview-delete')),
      );
      expect(delete.onPressed, isNull);
      expect(
        find.text(
          en(StorageLocale.selectedTotal, {'count': 0, 'size': size(0)}),
        ),
        findsOneWidget,
      );
    });

    testWidgets('a confirmed deletion runs exactly the ticked items, then shows '
        'its result; going back analyses again', (tester) async {
      await pumpAudit(tester);
      expect(scanner.calls, 1);
      await openPreview(tester, StorageCleanupLevel.confirmed);
      await tapKey(tester, 'storage-candidate-${_pickedCopy.path}');
      await tapKey(tester, 'storage-candidate-${_diagnostics.path}');
      await tapKey(tester, 'storage-preview-delete');
      await tester.tap(find.byKey(const ValueKey('storage-confirm-delete')));
      await tester.pumpAndSettle();

      expect(manager.selections.single, {
        _rpcs3Cache.path,
        _orphanMedia.path,
        _diagnostics.path,
        StorageCleanupPlan.metadataSelectionKey,
      });
      expect(manager.plans.single.level, StorageCleanupLevel.confirmed);
      expect(manager.maintenances.single, isNotNull);

      expect(
        find.text(
          en(StorageLocale.resultDeleted, {
            'count': 11,
            'size': size(2700000010),
          }),
        ),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.resultSkippedChanged, {'count': 1})),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.resultMissing, {'count': 2})),
        findsOneWidget,
      );
      expect(
        find.text(en(StorageLocale.resultRefused, {'count': 2})),
        findsWidgets,
      );
      expect(
        find.text(en(StorageLocale.resultMetadata, {'count': 3})),
        findsOneWidget,
      );
      expect(
        find.text(
          en(StorageLocale.journalSaved, {
            'path':
                '<Documents>/Diagnostics/storage-cleanup-20261012-101500.jsonl',
          }),
        ),
        findsOneWidget,
      );
      // Each refusal: translated reason, raw code, raw path.
      final denied = find.byKey(const ValueKey('storage-result-refusal-0'));
      expect(
        find.descendant(
          of: denied,
          matching: find.text(en(StorageLocale.refuseAccess)),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: denied,
          matching: find.text(
            en(StorageLocale.technicalCode, {
              'code': 'OS Error: Permission denied, errno = 13',
            }),
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: denied,
          matching: find.text('<Documents>/Diagnostics/locked.txt'),
        ),
        findsOneWidget,
      );
      final notEmpty = find.byKey(const ValueKey('storage-result-refusal-1'));
      expect(
        find.descendant(
          of: notEmpty,
          matching: find.text(en(StorageLocale.refuseNotEmpty)),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: notEmpty,
          matching: find.text(en(StorageLocale.technicalCode, {'code': 66})),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('storage-preview-delete')),
        findsNothing,
      );

      await tapKey(tester, 'storage-result-rescan');
      expect(find.byType(StorageCleanupPreviewScreen), findsNothing);
      expect(scanner.calls, 2, reason: 'back from the result: a new analysis');
      expect(
        find.byKey(const ValueKey('storage-last-cleanup')),
        findsOneWidget,
      );
    });

    testWidgets('progress of the deletion and its cancellation', (
      tester,
    ) async {
      manager.gate = Completer<void>();
      manager.progress = const [
        StorageDeletionProgress(
          done: 3,
          total: 12,
          deletedFiles: 3,
          deletedBytes: 300,
          phase: StorageDeletionPhase.files,
          currentPath: '<tmp>/Picked Game.zip',
        ),
      ];
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.regenerable);
      await tapKey(tester, 'storage-preview-delete');
      await tester.tap(find.byKey(const ValueKey('storage-confirm-delete')));
      await tester.pump();
      await tester.pump();

      expect(
        find.text(en(StorageLocale.deleting, {'done': 3, 'total': 12})),
        findsOneWidget,
      );
      expect(
        tester
            .widget<LinearProgressIndicator>(
              find.byKey(const ValueKey('storage-delete-progress')),
            )
            .value,
        closeTo(0.25, 1e-9),
      );
      // Boxes are frozen while it runs, and the page cannot be left.
      final box = tester.widget<CheckboxListTile>(
        find.byKey(ValueKey('storage-candidate-${_rpcs3Cache.path}')),
      );
      expect(box.onChanged, isNull);
      final popped = await tester.binding.handlePopRoute();
      expect(popped, isTrue);
      await tester.pump();
      expect(find.byType(StorageCleanupPreviewScreen), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('storage-delete-cancel')));
      await tester.pumpAndSettle();
      expect(find.text(en(StorageLocale.cancelled)), findsOneWidget);
      expect(
        find.text(
          en(StorageLocale.resultDeleted, {'count': 4, 'size': size(400)}),
        ),
        findsOneWidget,
      );
    });

    testWidgets('an unexpected failure keeps its technical text', (
      tester,
    ) async {
      manager.failure = StateError('journal unwritable');
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.safe);
      await tapKey(tester, 'storage-preview-delete');
      await tester.tap(find.byKey(const ValueKey('storage-confirm-delete')));
      await tester.pumpAndSettle();
      expect(find.text(en(StorageLocale.refuseUnknown)), findsOneWidget);
      expect(
        find.text(
          en(StorageLocale.technicalCode, {
            'code': StateError('journal unwritable'),
          }),
        ),
        findsOneWidget,
      );
      await tapKey(tester, 'storage-result-rescan');
      expect(scanner.calls, 2);
    });

    testWidgets('a game or an import in progress blocks the whole plan', (
      tester,
    ) async {
      planner.blocked = true;
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.safe);
      expect(
        find.byKey(const ValueKey('storage-preview-blocked')),
        findsOneWidget,
      );
      expect(find.text(en(StorageLocale.sessionActive)), findsOneWidget);
      expect(
        find.byKey(const ValueKey('storage-preview-delete')),
        findsNothing,
      );
      expect(manager.selections, isEmpty);
    });

    testWidgets('no analysis under an open preview: it runs once it closes', (
      tester,
    ) async {
      await pumpAudit(tester);
      await openPreview(tester, StorageCleanupLevel.safe);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(scanner.calls, 1, reason: 'the preview keeps the plan it shows');

      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(scanner.calls, 2);

      // Back without a cleanup nor a return to the foreground: nothing.
      await openPreview(tester, StorageCleanupLevel.safe);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(scanner.calls, 2);
    });
  });

  testWidgets('no analysis while a plan is being built either', (tester) async {
    await pumpAudit(tester);
    planner.gate = Completer<void>();
    final tile = find.byKey(const ValueKey('storage-level-safe'));
    await tester.ensureVisible(tile);
    await tester.pumpAndSettle();
    await tester.tap(tile);
    await tester.pump();
    expect(planner.levels, [StorageCleanupLevel.safe]);
    expect(
      find.descendant(
        of: tile,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
    final again = tester.widget<FilledButton>(
      find.byKey(const ValueKey('storage-scan-again')),
    );
    expect(again.onPressed, isNull);
    expect(
      tester
          .widget<SwitchListTile>(
            find.byKey(const ValueKey('storage-hash-toggle')),
          )
          .onChanged,
      isNull,
    );

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(scanner.calls, 1);

    planner.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.byType(StorageCleanupPreviewScreen), findsOneWidget);
    expect(scanner.calls, 1);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(
      scanner.calls,
      2,
      reason: 'the return to the foreground is honoured',
    );
  });

  testWidgets('the controller reaches every action: analysis, boxes, '
      'delete and both answers of the confirmation', (tester) async {
    // Navigation sounds use flutter_soloud (FFI), which has no test double.
    SfxService().setEnabled(false);
    addTearDown(() => SfxService().setEnabled(true));
    await pumpAudit(tester);

    // True when the primary focus is on, under or around [finder]'s widget
    // (a button owns its focus node below it; a read-only block is wrapped
    // by its focus node).
    bool focusedOn(Finder finder) {
      final target = finder.evaluate().single;
      final focus = FocusManager.instance.primaryFocus?.context;
      if (focus == null) return false;
      if (focus == target) return true;
      var found = false;
      focus.visitAncestorElements((ancestor) {
        found = ancestor == target;
        return !found;
      });
      void visit(Element element) {
        if (found) return;
        if (element == target) {
          found = true;
          return;
        }
        element.visitChildren(visit);
      }

      if (!found) (focus as Element).visitChildren(visit);
      return found;
    }

    // A layer ignores input for a short grace period after it is
    // activated, and throttles repeated keys (real clock).
    Future<void> press(LogicalKeyboardKey key) async {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 220)),
      );
      await tester.sendKeyEvent(key);
      await tester.pump();
    }

    // The D-pad starts on « Analyze again »; Enter runs it.
    await press(LogicalKeyboardKey.arrowDown);
    expect(focusedOn(find.byKey(const ValueKey('storage-scan-again'))), isTrue);
    await press(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(scanner.calls, 2);

    await openPreview(tester, StorageCleanupLevel.safe);
    await press(LogicalKeyboardKey.arrowDown);
    expect(
      focusedOn(find.byKey(const ValueKey('storage-preview-level'))),
      isTrue,
    );
    await press(LogicalKeyboardKey.arrowDown);
    expect(
      focusedOn(
        find.byKey(const ValueKey('storage-preview-root-header-INV-28')),
      ),
      isTrue,
    );
    await press(LogicalKeyboardKey.arrowDown);
    final box = find.byKey(ValueKey('storage-candidate-${_pickedCopy.path}'));
    expect(focusedOn(box), isTrue);
    await press(LogicalKeyboardKey.enter);
    expect(ticked(tester, _pickedCopy.path), isFalse);
    await press(LogicalKeyboardKey.enter);
    expect(ticked(tester, _pickedCopy.path), isTrue);
    await press(LogicalKeyboardKey.arrowDown);
    final delete = find.byKey(const ValueKey('storage-preview-delete'));
    expect(focusedOn(delete), isTrue);

    // Backspace answers « no »: nothing is deleted.
    await press(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    final dialog = find.byKey(const ValueKey('storage-confirm-dialog'));
    expect(dialog, findsOneWidget);
    await press(LogicalKeyboardKey.backspace);
    await tester.pumpAndSettle();
    expect(dialog, findsNothing);
    expect(find.byType(StorageCleanupPreviewScreen), findsOneWidget);
    expect(manager.selections, isEmpty);

    // The dialog starts on Cancel, Delete is next to it; Enter on Delete.
    expect(focusedOn(delete), isTrue, reason: 'the focus comes back');
    await press(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    await press(LogicalKeyboardKey.arrowDown);
    expect(
      focusedOn(find.byKey(const ValueKey('storage-confirm-cancel'))),
      isTrue,
    );
    await press(LogicalKeyboardKey.arrowRight);
    expect(
      focusedOn(find.byKey(const ValueKey('storage-confirm-delete'))),
      isTrue,
    );
    await press(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(manager.selections.single, {_pickedCopy.path});
    expect(find.byKey(const ValueKey('storage-result')), findsOneWidget);

    // Backspace leaves the result: a new analysis.
    await press(LogicalKeyboardKey.backspace);
    await tester.pumpAndSettle();
    expect(find.byType(StorageCleanupPreviewScreen), findsNothing);
    expect(scanner.calls, 3);
  });

  group('export', () {
    testWidgets('aggregates by default, relative paths in detailed mode', (
      tester,
    ) async {
      await pumpAudit(tester);
      await tapKey(tester, 'storage-share');
      expect(sharer.shared, hasLength(1));
      final aggregate = sharer.shared.single;
      expect(
        aggregate.fileName,
        matches(RegExp(r'^storage-report-\d{8}-\d{6}\.json$')),
      );
      final json = jsonDecode(aggregate.content) as Map<String, dynamic>;
      expect(json['format'], StorageReport.format);
      expect(json['mode'], 'aggregate');
      expect(
        (json['totals'] as Map)['logicalBytes'],
        _scanResult().logicalBytes,
      );
      for (final root in json['roots'] as List) {
        expect((root as Map).containsKey('largest'), isFalse);
      }
      expect(aggregate.content, isNot(contains(_home)));
      expect(aggregate.content, isNot(contains('Zelda')));
      expect(aggregate.content, isNot(contains('Sources')));

      await tapKey(tester, 'storage-export-detailed');
      final preferences = await SharedPreferences.getInstance();
      expect(
        preferences.getBool(StorageAuditPreferences.detailedExport),
        isTrue,
      );
      await tapKey(tester, 'storage-share');
      final detailed =
          jsonDecode(sharer.shared.last.content) as Map<String, dynamic>;
      expect(detailed['mode'], 'detailed');
      final roms = (detailed['roots'] as List)
          .cast<Map<String, dynamic>>()
          .firstWhere((root) => root['id'] == 'INV-01');
      expect(
        (roms['largest'] as List).map((entry) => (entry as Map)['path']),
        contains('<Documents>/roms/snes/Zelda.sfc'),
      );
      expect(sharer.shared.last.content, isNot(contains(_home)));
      expect(sharer.shared.last.content, isNot(contains('Sources')));
    });

    testWidgets('a failed share says so, with its technical text', (
      tester,
    ) async {
      sharer.failure = PlatformException(
        code: 'share_failed',
        message: 'No activity view controller',
      );
      await pumpAudit(tester);
      await tapKey(tester, 'storage-share');
      expect(find.text(en(StorageLocale.shareFailed)), findsOneWidget);
      expect(
        find.text(en(StorageLocale.technicalCode, {'code': sharer.failure})),
        findsOneWidget,
      );
      expect(scanner.calls, 1);
    });
  });

  group('real analysis of a temporary container', () {
    final helper = DatabaseTestHelper();
    late DatabaseAdapter db;
    late Directory home;
    late StorageContainers containers;
    late StorageRootRegistry real;

    String at(StorageContainer container, String relative) =>
        p.join(containers.pathOf(container), relative);

    Future<void> write(
      String path,
      int length, {
      Duration age = Duration.zero,
    }) async {
      final file = File(path);
      await file.parent.create(recursive: true);
      await file.writeAsBytes(List<int>.filled(length, 3));
      await file.setLastModified(DateTime.now().subtract(age));
    }

    setUp(() async {
      StorageStatFfi.resetSession();
      db = await helper.setUp();
      home = await Directory.systemTemp.createTemp('storage_audit_screen_');
      containers = StorageContainers(
        documents: p.join(home.path, 'Documents'),
        applicationSupport: p.join(home.path, 'Library', 'Application Support'),
        caches: p.join(home.path, 'Library', 'Caches'),
        temporary: p.join(home.path, 'tmp'),
      );
      for (final container in StorageContainer.values) {
        await Directory(containers.pathOf(container)).create(recursive: true);
      }
      real = StorageRootRegistry(containers);
    });

    tearDown(() async {
      StorageStatFfi.resetSession();
      await helper.tearDown();
      if (await home.exists()) await home.delete(recursive: true);
    });

    /// Real scanner, detector and planner run real isolates and file I/O:
    /// each step needs real time, then a frame.
    Future<void> settleReal(WidgetTester tester, Finder until) async {
      for (var round = 0; round < 600; round++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 5)),
        );
        await tester.pump();
        if (until.evaluate().isNotEmpty &&
            find.byType(CircularProgressIndicator).evaluate().isEmpty) {
          await tester.pump();
          return;
        }
      }
      fail('Timed out waiting for $until');
    }

    testWidgets('the real plan of level 3: level 1 and 2 ticked, level 3 '
        'never; games never proposed; only the ticked paths reach the '
        'deletion', (tester) async {
      const hour = Duration(hours: 3);
      final picked = at(StorageContainer.temporary, 'Picked Game.zip');
      final cache = at(
        StorageContainer.applicationSupport,
        'NeoStation/RPCS3/Cache/ppu-BLES00113',
      );
      final diagnostics = at(
        StorageContainer.documents,
        'Diagnostics/rpcs3_startup_debug.txt',
      );
      final game = at(StorageContainer.documents, 'roms/snes/Game.sfc');
      await tester.runAsync(() async {
        await write(picked, 700, age: hour);
        await write(p.join(cache, 'obj.bin'), 2000, age: hour);
        await write(diagnostics, 50, age: hour);
        await write(game, 4000, age: hour);
      });
      final realManager = _FakeDeletionManager(real);
      tester.view.physicalSize = const Size(1200, 6000);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          locale: const Locale('en'),
          home: StorageAuditScreen(
            registry: real,
            orphanDetector: StorageOrphanDetector(
              database: () async => db,
              registry: real,
            ),
            planner: StorageCleanupPlanner(
              registry: real,
              guard: _idleGuard(),
              now: () => DateTime.now().add(const Duration(days: 2)),
            ),
            deletionManager: realManager,
            sharer: sharer,
          ),
        ),
      );
      await settleReal(tester, find.byKey(const ValueKey('storage-orphans')));
      expect(
        find.text(en(StorageLocale.totalLogical, {'size': size(6750)})),
        findsOneWidget,
      );

      final level = find.byKey(const ValueKey('storage-level-confirmed'));
      await tester.ensureVisible(level);
      await tester.pump();
      await tester.tap(level);
      await settleReal(tester, find.byType(StorageCleanupPreviewScreen));
      await tester.pumpAndSettle();

      expect(ticked(tester, picked), isTrue);
      expect(ticked(tester, cache), isTrue);
      expect(ticked(tester, diagnostics), isFalse);
      expect(find.byKey(ValueKey('storage-candidate-$game')), findsNothing);
      expect(
        find.byKey(
          ValueKey('storage-warning-$cache-${StorageLocale.rpcs3CacheWarning}'),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          ValueKey(
            'storage-warning-$diagnostics-${StorageLocale.diagnosticsWarning}',
          ),
        ),
        findsOneWidget,
      );

      await tapKey(tester, 'storage-preview-delete');
      await tester.tap(find.byKey(const ValueKey('storage-confirm-delete')));
      await tester.pumpAndSettle();
      expect(realManager.selections.single, {picked, cache});
      // The fake manager deleted nothing: every file is still there.
      for (final path in [
        picked,
        p.join(cache, 'obj.bin'),
        diagnostics,
        game,
      ]) {
        expect(File(path).existsSync(), isTrue, reason: path);
      }
    });
  });

  testWidgets('every text of the pages follows the app language', (
    tester,
  ) async {
    String fr(String key, [Map<String, Object?> values = const {}]) =>
        StorageLocale.forLocale(const Locale('fr'), key, values);
    await pumpAudit(tester, locale: const Locale('fr'));
    expect(find.text(fr(StorageLocale.title)), findsOneWidget);
    expect(find.text(fr(StorageLocale.scanAgain)), findsOneWidget);
    expect(find.text(fr(StorageLocale.byCategory)), findsOneWidget);
    expect(find.text(fr(StorageLocale.computeHashes)), findsOneWidget);
    expect(find.text(fr(StorageLocale.levelSafe)), findsOneWidget);
    expect(find.text(fr(StorageLocale.levelConfirmed)), findsOneWidget);
    expect(find.text(fr(StorageLocale.limitsTitle)), findsOneWidget);
    await openPreview(tester, StorageCleanupLevel.regenerable);
    expect(find.text(fr(StorageLocale.preview)), findsOneWidget);
    expect(find.text(fr(StorageLocale.deleteAction)), findsOneWidget);
    expect(find.text(fr(StorageLocale.rpcs3CacheWarning)), findsOneWidget);
    expect(find.text(en(StorageLocale.deleteAction)), findsNothing);
  });
}
