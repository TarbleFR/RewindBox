// Build 440: the app's own LibraryAddonService.instance, built as on iOS,
// mirrors its sources in Documents/Library/Sources, follows the app's return
// to the foreground and refreshes the Library hub feed after a source was
// removed through Files. Its own test file: the instance is created once per
// isolate, after the platform check is overridden.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart' as feed_fakes;
import 'library_ui_sources_harness.dart';

const MethodChannel _pathProvider = MethodChannel(
  'plugins.flutter.io/path_provider',
);

Future<void> _waitFor(bool Function() done) async {
  for (var round = 0; round < 300 && !done(); round++) {
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('the app service, as on iOS, removes a source whose file was '
      'deleted in Files on return to the app and drops it from the hub', (
    tester,
  ) async {
    final lelscan = testAidokuAddon('fr.lelscanfr', 'LelscanFR');
    final scantrad = testAidokuAddon('fr.mangascantrad', 'Manga Scantrad');
    final documents = Directory.systemTemp.createTempSync('ns_source_app_');
    final sources = Directory(p.join(documents.path, 'Library', 'Sources'));
    final messenger = tester.binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      _pathProvider,
      (call) async => documents.path,
    );
    SharedPreferences.setMockInitialValues(<String, Object>{
      'neostation_library_addons_v1': jsonEncode(
        <LibraryAddon>[lelscan, scantrad].map((a) => a.toJson()).toList(),
      ),
    });
    final backend = feed_fakes.FakeFeedBackend();
    for (final addon in <LibraryAddon>[lelscan, scantrad]) {
      backend.pages[addon.aidokuSourceId!] = (call) async => feed_fakes
          .testPage([feed_fakes.testItem('${addon.id}-title')], hasMore: false);
    }
    final previousFeed = LibraryCatalogFeed.instance;
    final feed = LibraryCatalogFeed(backend: backend);
    LibraryCatalogFeed.instance = feed;
    LibrarySourceFiles.debugSupportedByPlatformOverride = true;
    addTearDown(() {
      LibrarySourceFiles.debugSupportedByPlatformOverride = null;
      LibraryCatalogFeed.instance = previousFeed;
      feed.dispose();
      messenger.setMockMethodCallHandler(_pathProvider, null);
      try {
        documents.deleteSync(recursive: true);
      } on FileSystemException {
        // The system clears its temporary folder.
      }
    });

    // First use of the app's instance in this isolate.
    final service = LibraryAddonService.instance;
    final files = service.sourceFiles;
    expect(files, isNotNull);
    addTearDown(files!.dispose);

    await tester.runAsync(() async {
      await service.load();
      expect(
        sources.listSync().map((entity) => p.basename(entity.path)).toList()
          ..sort(),
        <String>['LelscanFR (fr).json', 'Manga Scantrad (fr).json'],
      );
      await feed.open(service.addons);
      expect(feed.source(scantrad.id), isNotNull);

      File(p.join(sources.path, 'Manga Scantrad (fr).json')).deleteSync();
      final passes = files.passCount;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await _waitFor(() => feed.source(scantrad.id) == null);
      expect(files.passCount, passes + 1);
    });

    expect(service.addons.map((addon) => addon.id), <String>[lelscan.id]);
    expect(feed.source(scantrad.id), isNull);
    expect(feed.source(lelscan.id), isNotNull);
    expect(
      feed.entries.map((entry) => entry.item.id),
      isNot(contains('${scantrad.id}-title')),
    );
  });
}
