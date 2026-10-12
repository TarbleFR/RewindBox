import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/storage/storage_cleanup_planner.dart';
import 'package:neostation/services/storage/storage_import_activity.dart';

/// Imports in progress (docs/storage-audit-cleanup.md § 3.7, review of phase
/// 5d): every import that follows a Files pick runs inside
/// [StorageImportActivity.run]; it is counted from its start to its end,
/// whatever it returns or throws, and the session guard reports it, so the
/// planner refuses the whole plan and the deletion manager stops
/// (test/storage_cleanup_planner_test.dart, test/storage_deletion_manager_test.dart,
/// test/storage_audit_screen_test.dart). Where the imports are wrapped is
/// pinned by test/storage_contract_test.py.
void main() {
  tearDown(StorageImportActivity.reset);

  StorageSessionGuard guard() => StorageSessionGuard(
    launchActive: () => false,
    libretroActive: () async => false,
    dolphinMarkerPresent: () async => false,
    libretroJournalUnfinished: () async => false,
  );

  test('an import counts from its start to its end', () async {
    expect(StorageImportActivity.active, isFalse);
    expect(StorageImportActivity.running, 0);
    final picking = Completer<void>();
    final first = StorageImportActivity.run(() async {
      await picking.future;
      return 7;
    });
    expect(StorageImportActivity.active, isTrue);
    expect(StorageImportActivity.running, 1);
    // Two imports overlap: a counter, not a flag.
    final second = StorageImportActivity.run(() async => 'done');
    expect(StorageImportActivity.running, 2);
    expect(await second, 'done');
    expect(StorageImportActivity.running, 1);
    expect(StorageImportActivity.active, isTrue);
    picking.complete();
    expect(await first, 7);
    expect(StorageImportActivity.active, isFalse);
  });

  test('a failed import is released, its error kept', () async {
    final failing = StorageImportActivity.run<int>(() async {
      await Future<void>.delayed(Duration.zero);
      throw StateError('copy failed: errno = 28');
    });
    expect(StorageImportActivity.active, isTrue);
    await expectLater(
      failing,
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          'copy failed: errno = 28',
        ),
      ),
    );
    expect(StorageImportActivity.active, isFalse);

    // A body that throws before its first await is released too.
    await expectLater(
      StorageImportActivity.run<void>(() => throw StateError('no file')),
      throwsStateError,
    );
    expect(StorageImportActivity.running, 0);
  });

  test('the session guard reports an import while it runs', () async {
    var state = await guard().check();
    expect(state.importActive, isFalse);
    expect(state.wholeCleanupRefused, isFalse);
    expect(state.anyActive, isFalse);

    final picking = Completer<void>();
    final import = StorageImportActivity.run(() => picking.future);
    state = await guard().check();
    expect(state.importActive, isTrue);
    expect(state.launchActive, isFalse);
    expect(state.wholeCleanupRefused, isTrue);
    expect(state.anyActive, isTrue);
    expect(state.toString(), contains('import: true'));

    picking.complete();
    await import;
    state = await guard().check();
    expect(state.importActive, isFalse);
    expect(state.wholeCleanupRefused, isFalse);
  });

  test('an import starting during the other probes still counts', () async {
    // The import probe is read last: an import a slow probe let start is
    // seen by the same check.
    final picking = Completer<void>();
    Future<void>? import;
    final state = await StorageSessionGuard(
      launchActive: () => false,
      libretroActive: () async {
        import = StorageImportActivity.run(() => picking.future);
        return false;
      },
      dolphinMarkerPresent: () async => false,
      libretroJournalUnfinished: () async => false,
    ).check();
    expect(state.importActive, isTrue);
    expect(state.wholeCleanupRefused, isTrue);
    picking.complete();
    await import;
  });
}
