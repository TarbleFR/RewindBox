// LibrarySourceHealthStore: one report per Aidoku source id in
// source-health.json, atomic writes, a damaged file kept aside.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_source_health_store.dart';
import 'package:path/path.dart' as p;

LibrarySourceHealthReport _report(
  String sourceId,
  DateTime checkedAt, {
  bool reading = true,
}) {
  return LibrarySourceHealthReport(
    sourceId: sourceId,
    checkedAt: checkedAt,
    steps: <LibrarySourceHealthStepResult>[
      const LibrarySourceHealthStepResult(
        step: LibrarySourceHealthStep.listing,
        ok: true,
        count: 24,
      ),
      const LibrarySourceHealthStepResult(
        step: LibrarySourceHealthStep.details,
        ok: true,
        count: 1,
      ),
      const LibrarySourceHealthStepResult(
        step: LibrarySourceHealthStep.chapters,
        ok: true,
        count: 546,
      ),
      LibrarySourceHealthStepResult(
        step: LibrarySourceHealthStep.pages,
        ok: reading,
        count: reading ? 15 : 0,
        networkError: reading ? null : LibraryNetworkErrorKind.timeout,
      ),
      if (reading)
        const LibrarySourceHealthStepResult(
          step: LibrarySourceHealthStep.image,
          ok: true,
          count: 407122,
        )
      else
        const LibrarySourceHealthStepResult.skipped(
          LibrarySourceHealthStep.image,
        ),
    ],
  );
}

void main() {
  late Directory root;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('ns_health_store_');
  });

  tearDown(() async {
    if (await root.exists()) await root.delete(recursive: true);
  });

  test('keeps the latest report per source and reloads it', () async {
    final store = LibrarySourceHealthStore(directory: () async => root);
    await store.load();
    expect(store.latest('fr.lelscanfr'), isNull);

    await store.record(_report('fr.lelscanfr', DateTime.utc(2026, 10, 11, 8)));
    await store.record(
      _report('fr.lelscanfr', DateTime.utc(2026, 10, 11, 9), reading: false),
    );
    await store.record(_report('fr.sushiscan', DateTime.utc(2026, 10, 11, 9)));

    final file = File(p.join(root.path, LibrarySourceHealthStore.fileName));
    expect(await file.exists(), isTrue);
    expect(await File('${file.path}.tmp').exists(), isFalse);

    final reloaded = LibrarySourceHealthStore(directory: () async => root);
    await reloaded.load();
    final lelscan = reloaded.latest('fr.lelscanfr')!;
    expect(lelscan.checkedAt, DateTime.utc(2026, 10, 11, 9));
    expect(lelscan.navigationWorking, isTrue);
    expect(lelscan.readingWorking, isFalse);
    expect(
      lelscan.step(LibrarySourceHealthStep.pages).networkError,
      LibraryNetworkErrorKind.timeout,
    );
    expect(reloaded.latest('fr.sushiscan')!.readingWorking, isTrue);
    expect(
      reloaded.reports.keys,
      unorderedEquals(<String>['fr.lelscanfr', 'fr.sushiscan']),
    );
  });

  test('notifies listeners when a report is recorded or removed', () async {
    final store = LibrarySourceHealthStore(directory: () async => root);
    var notifications = 0;
    store.addListener(() => notifications++);
    await store.load();
    final afterLoad = notifications;
    await store.record(_report('fr.lelscanfr', DateTime.utc(2026, 10, 11)));
    expect(notifications, afterLoad + 1);
    await store.remove('fr.lelscanfr');
    expect(notifications, afterLoad + 2);
    expect(store.latest('fr.lelscanfr'), isNull);
  });

  test(
    'a damaged file is kept aside and replaced by the next result',
    () async {
      final file = File(p.join(root.path, LibrarySourceHealthStore.fileName));
      await file.writeAsString('{not json');
      final store = LibrarySourceHealthStore(directory: () async => root);
      await store.load();
      expect(store.reports, isEmpty);
      expect(await File('${file.path}.corrupt').readAsString(), '{not json');

      await store.record(_report('fr.lelscanfr', DateTime.utc(2026, 10, 11)));
      final reloaded = LibrarySourceHealthStore(directory: () async => root);
      await reloaded.load();
      expect(reloaded.latest('fr.lelscanfr'), isNotNull);
      expect(
        await File('${file.path}.corrupt').readAsString(),
        '{not json',
        reason: 'the first damaged copy is never replaced',
      );
    },
  );
}
