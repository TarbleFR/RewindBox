// LibrarySourcesView: remembered catalogues, active sources with their
// verification ladder, on-device test (live progress, saved report, device
// offline vs site offline), deactivation, catalogue import by URL with a
// preview where nothing is pre-selected, and controller focus navigation.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_catalog_preview_screen.dart';
import 'package:neostation/screens/library_screen/library_gamepad_view_controller.dart';
import 'package:neostation/screens/library_screen/library_sources_view.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_catalog_import_fakes.dart' as catalog_fakes;
import 'library_ui_sources_harness.dart';

const String _catalogUrl = 'https://example.org/aidoku/index.min.json';

class _Fixture {
  _Fixture({
    required this.addons,
    required this.catalogs,
    required this.aidoku,
    required this.health,
    required this.fetcher,
  });

  final LibraryAddonService addons;
  final LibrarySourceCatalogService catalogs;
  final FakeAidokuService aidoku;
  final MemoryHealthStore health;
  final catalog_fakes.FakeLibraryFetcher fetcher;
  final LibraryGamepadViewController controller =
      LibraryGamepadViewController();
  int sourcesChanged = 0;
  int backs = 0;
  bool deviceOnline = true;
  int probes = 0;

  Widget view() => LibrarySourcesView(
    controller: controller,
    onBack: () => backs++,
    onSourcesChanged: () => sourcesChanged++,
    catalogService: catalogs,
    addonService: addons,
    aidokuService: aidoku,
    healthStore: health,
    connectivityProbe: () async {
      probes++;
      return deviceOnline;
    },
    imageCache: images,
    catalogFilePicker: () async => pickedFile,
    enableGamepad: false,
  );

  final NoImageCache images = NoImageCache();
  LibraryPickedCatalogFile? pickedFile;
}

Future<_Fixture> _fixture({
  List<LibraryAddon> installed = const <LibraryAddon>[],
  List<LibraryStoredCatalog> remembered = const <LibraryStoredCatalog>[],
  Map<String, catalog_fakes.FakeRoute>? routes,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final addons = LibraryAddonService.forTesting();
  await addons.load();
  if (installed.isNotEmpty) await addons.upsertAddons(installed);
  final fetcher = catalog_fakes.FakeLibraryFetcher(routes);
  return _Fixture(
    addons: addons,
    catalogs: LibrarySourceCatalogService(
      fetcher: fetcher.call,
      addons: addons,
      store: LibraryCatalogMemoryStore(remembered),
      clock: () => DateTime.utc(2026, 10, 11, 8),
    ),
    aidoku: FakeAidokuService(),
    health: MemoryHealthStore(),
    fetcher: fetcher,
  );
}

/// Catalogue service whose previews wait for [gate].
class _GatedPreviewService extends LibrarySourceCatalogService {
  _GatedPreviewService({
    required this.gate,
    super.fetcher,
    super.addons,
    super.store,
    super.clock,
  });

  final Future<void> gate;

  @override
  Future<LibraryCatalogPreview> preview(
    String input, {
    LibraryCancelToken? cancel,
    bool refresh = false,
  }) async {
    await gate;
    return super.preview(input, cancel: cancel, refresh: refresh);
  }
}

LibrarySourceHealthStepResult _ok(LibrarySourceHealthStep step, int count) =>
    LibrarySourceHealthStepResult(
      step: step,
      ok: true,
      count: count,
      durationMs: 120,
    );

Finder _rowOf(String addonId) =>
    find.byKey(ValueKey<String>('source-$addonId'));

void main() {
  final lelscan = testAidokuAddon('fr.lelscanfr', 'LelscanFR');
  final scantrad = testAidokuAddon('fr.mangascantrad', 'Manga Scantrad');
  final astral = testAidokuAddon(
    'fr.astralmanga',
    'Astral Manga',
    contentRating: 2,
  );
  final books = testNeoStationAddon();

  testWidgets('lists remembered catalogues and the verification ladder', (
    tester,
  ) async {
    final fixture = await _fixture(
      installed: <LibraryAddon>[lelscan, scantrad, astral, books],
      remembered: <LibraryStoredCatalog>[
        LibraryStoredCatalog(
          url: _catalogUrl,
          name: 'Aidoku FR',
          format: LibraryCatalogFormat.aidokuLegacyIndex,
          lastFetchedAt: DateTime.utc(2026, 10, 10, 12),
          sourceCount: 10,
        ),
      ],
    );
    await pumpLibraryUi(tester, fixture.view(), size: const Size(1280, 2000));
    await tester.pumpAndSettle();

    expect(find.text('Sources and catalogues'), findsOneWidget);
    expect(find.text('Aidoku FR'), findsOneWidget);
    expect(find.text(_catalogUrl), findsOneWidget);
    expect(find.textContaining('10 source(s)'), findsOneWidget);

    // LelscanFR: adapter, verified from a PC on 2026-10-10.
    final lelscanRow = _rowOf(lelscan.id);
    expect(
      find.descendant(
        of: lelscanRow,
        matching: find.text('Catalogue imported'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(of: lelscanRow, matching: find.text('Reader available')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: lelscanRow,
        matching: find.textContaining('Navigation verified ('),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: lelscanRow,
        matching: find.textContaining('Chapter reading verified ('),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: lelscanRow,
        matching: find.textContaining(
          'from a test computer, not on this iPhone',
        ),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(of: lelscanRow, matching: find.text('Test')),
      findsOneWidget,
    );

    // Manga Scantrad: adapter kept, but the site requires a challenge.
    final scantradRow = _rowOf(scantrad.id);
    expect(
      find.descendant(
        of: scantradRow,
        matching: find.text('Browser verification required'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: scantradRow,
        matching: find.text('Navigation not verified'),
      ),
      findsOneWidget,
    );

    // Astral Manga: no adapter, translated reason, no test button, adult.
    final astralRow = _rowOf(astral.id);
    expect(
      find.descendant(
        of: astralRow,
        matching: find.text(
          'The site moved to a new platform protected by a browser '
          'verification.',
        ),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(of: astralRow, matching: find.text('Test')),
      findsNothing,
    );
    expect(
      find.descendant(of: astralRow, matching: find.text('Adults only (18+)')),
      findsOneWidget,
    );

    // A NeoStation manifest is shown with its kind and no ladder.
    final booksRow = _rowOf(books.id);
    expect(
      find.descendant(
        of: booksRow,
        matching: find.textContaining('NeoStation source'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(of: booksRow, matching: find.text('Catalogue imported')),
      findsNothing,
    );
  });

  testWidgets(
    'the test dialog shows each step, saves the report and updates the ladder',
    (tester) async {
      final fixture = await _fixture(installed: <LibraryAddon>[lelscan]);
      fixture.aidoku.healthSteps = <LibrarySourceHealthStepResult>[
        _ok(LibrarySourceHealthStep.listing, 24),
        _ok(LibrarySourceHealthStep.details, 1),
        _ok(LibrarySourceHealthStep.chapters, 546),
        const LibrarySourceHealthStepResult(
          step: LibrarySourceHealthStep.pages,
          ok: false,
          sourceError: LibrarySourceErrorKind.protectedChapter,
          durationMs: 80,
          detail: 'LibrarySourceException(protectedChapter, fr.lelscanfr)',
        ),
      ];
      await pumpLibraryUi(tester, fixture.view());
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(of: _rowOf(lelscan.id), matching: find.text('Test')),
      );
      await tester.pump();
      expect(find.text('Testing LelscanFR'), findsOneWidget);
      expect(find.text('In progress…'), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 15));
      expect(find.text('24 found (120 ms)'), findsOneWidget);

      await tester.pumpAndSettle();
      expect(find.text('546 found (120 ms)'), findsOneWidget);
      expect(
        find.text(
          'This chapter is locked by the site (premium or unlock required).',
        ),
        findsOneWidget,
      );
      expect(find.text('Not run: an earlier step failed'), findsOneWidget);
      expect(
        find.text('Navigation works, but chapters cannot be read right now.'),
        findsOneWidget,
      );
      expect(fixture.health.recordCount, 1);
      expect(fixture.probes, 0, reason: 'only an all-offline run is probed');

      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
      final row = _rowOf(lelscan.id);
      expect(
        find.descendant(
          of: row,
          matching: find.textContaining('Navigation verified ('),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: row,
          matching: find.textContaining('Chapter reading failed ('),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: row,
          matching: find.textContaining('Tested on this device on'),
        ),
        findsOneWidget,
      );
    },
  );

  testWidgets('an offline device is told apart from an offline site', (
    tester,
  ) async {
    final fixture = await _fixture(installed: <LibraryAddon>[lelscan]);
    fixture.aidoku.healthSteps = <LibrarySourceHealthStepResult>[
      const LibrarySourceHealthStepResult(
        step: LibrarySourceHealthStep.listing,
        ok: false,
        networkError: LibraryNetworkErrorKind.offline,
        detail: 'LibraryNetworkException(offline, www.lelscanfr.com)',
      ),
    ];
    fixture.deviceOnline = false;
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();

    await tester.tap(
      find.descendant(of: _rowOf(lelscan.id), matching: find.text('Test')),
    );
    await tester.pumpAndSettle();
    expect(fixture.probes, 1);
    expect(
      find.textContaining('This device seems to be offline'),
      findsOneWidget,
    );
    expect(fixture.health.recordCount, 0, reason: 'says nothing of the site');
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();

    fixture.deviceOnline = true;
    await tester.tap(
      find.descendant(of: _rowOf(lelscan.id), matching: find.text('Test')),
    );
    await tester.pumpAndSettle();
    expect(fixture.probes, 2);
    expect(
      find.text('The device is online, but this site cannot be reached.'),
      findsOneWidget,
    );
    expect(find.text('This source does not work right now.'), findsOneWidget);
    expect(fixture.health.recordCount, 1);
  });

  testWidgets('on a landscape iPhone the verdict scrolls into view', (
    tester,
  ) async {
    final aidoku = FakeAidokuService()
      ..healthSteps = <LibrarySourceHealthStepResult>[
        _ok(LibrarySourceHealthStep.listing, 24),
        _ok(LibrarySourceHealthStep.details, 1),
        _ok(LibrarySourceHealthStep.chapters, 546),
        _ok(LibrarySourceHealthStep.pages, 15),
        _ok(LibrarySourceHealthStep.image, 407122),
      ];
    await pumpLibraryUi(
      tester,
      LibrarySourceHealthDialog(
        addon: lelscan,
        aidokuService: aidoku,
        healthStore: MemoryHealthStore(),
        connectivityProbe: () async => true,
        enableGamepad: false,
      ),
      size: const Size(844, 390),
    );
    await tester.pumpAndSettle();
    final verdict = find.text(
      'Navigation and chapter reading work on this device.',
    );
    final viewport = tester.getRect(
      find.descendant(
        of: find.byType(LibrarySourceHealthDialog),
        matching: find.byType(SingleChildScrollView),
      ),
    );
    expect(tester.getRect(verdict).bottom, lessThanOrEqualTo(viewport.bottom));
    expect(tester.getRect(verdict).top, greaterThanOrEqualTo(viewport.top));

    // A controller can go back up through the steps.
    final layer = tester.state<LibraryFocusGamepadLayerState>(
      find.byType(LibraryFocusGamepadLayer),
    );
    layer.move(TraversalDirection.down);
    await tester.pumpAndSettle();
    final first = tester.getRect(find.text('Title list'));
    expect(first.top, greaterThanOrEqualTo(viewport.top));
  });

  testWidgets('testing a source without a reader explains why it fails', (
    tester,
  ) async {
    // The real service reports the first step before any await.
    final aidoku = LibraryAidokuNativeService(
      fetcher:
          (
            LibraryRequest request, {
            LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
            LibraryCancelToken? cancel,
          }) => throw StateError('no network: ${request.uri}'),
    );
    expect(aidoku.supports(astral), isFalse);
    final health = MemoryHealthStore();
    await pumpLibraryUi(
      tester,
      LibrarySourceHealthDialog(
        addon: astral,
        aidokuService: aidoku,
        healthStore: health,
        connectivityProbe: () async => true,
        enableGamepad: false,
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      find.text('NeoStation has no reader for this source.'),
      findsOneWidget,
    );
    expect(find.text('This source does not work right now.'), findsOneWidget);
    expect(health.recordCount, 1);
  });

  testWidgets('deactivation explains that favourites are kept', (tester) async {
    final fixture = await _fixture(installed: <LibraryAddon>[lelscan, books]);
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();

    await tester.tap(
      find.descendant(
        of: _rowOf(lelscan.id),
        matching: find.text('Deactivate'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Deactivate LelscanFR?'), findsOneWidget);
    expect(
      find.textContaining(
        'favourites, reading progress and read chapters are '
        'kept',
      ),
      findsOneWidget,
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Deactivate'));
    await tester.pumpAndSettle();
    expect(fixture.sourcesChanged, 1);
    expect(fixture.addons.addons.map((addon) => addon.id), <String>[books.id]);
    expect(_rowOf(lelscan.id), findsNothing);
    expect(find.text('LelscanFR deactivated.'), findsOneWidget);
  });

  testWidgets(
    'a URL opens the preview with nothing selected; only ticked sources '
    'are activated',
    (tester) async {
      final fixture = await _fixture(
        routes: <String, catalog_fakes.FakeRoute>{
          _catalogUrl: catalog_fakes.FakeRoute.fixture(
            'aidoku_french_legacy_index.min.json',
          ),
        },
      );
      await pumpLibraryUi(tester, fixture.view());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Add a catalogue (URL)'));
      await tester.pumpAndSettle();
      // The field takes the focus at once (keyboard ready for paste).
      final field = tester.widget<EditableText>(
        find.descendant(
          of: find.byKey(const ValueKey<String>('catalog-url-field')),
          matching: find.byType(EditableText),
        ),
      );
      expect(field.focusNode.hasFocus, isTrue);
      expect(field.keyboardType, TextInputType.url);
      await tester.enterText(
        find.byKey(const ValueKey<String>('catalog-url-field')),
        _catalogUrl,
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Show sources'));
      await tester.pumpAndSettle();

      expect(find.byType(LibraryCatalogPreviewScreen), findsOneWidget);
      final boxes = tester.widgetList<Checkbox>(find.byType(Checkbox)).toList();
      expect(boxes, isNotEmpty);
      expect(boxes.every((box) => box.value == false), isTrue);
      final activate = tester.widget<FilledButton>(
        find.byKey(const ValueKey<String>('activate-button')),
      );
      expect(activate.onPressed, isNull, reason: 'Activate (0) is disabled');

      await tester.tap(
        find.byKey(const ValueKey<String>('entry-fr.lelscanfr')),
      );
      await tester.pump();
      expect(find.text('Activate (1)'), findsOneWidget);
      await tester.tap(find.text('Activate (1)'));
      await tester.pumpAndSettle();
      expect(find.text('Added: 1'), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      expect(find.byType(LibraryCatalogPreviewScreen), findsNothing);
      expect(fixture.sourcesChanged, 1);
      expect(
        fixture.addons.addons.map((addon) => addon.aidokuSourceId),
        <String?>['fr.lelscanfr'],
      );
      expect(
        _rowOf(LibraryAddon.aidokuAddonId('fr.lelscanfr')),
        findsOneWidget,
      );
      expect(find.text(_catalogUrl), findsOneWidget, reason: 'remembered');
    },
  );

  testWidgets('the end of a catalogue load closes its dialog, not a later '
      'route', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final addons = LibraryAddonService.forTesting();
    await addons.load();
    final gate = Completer<void>();
    final fetcher =
        catalog_fakes.FakeLibraryFetcher(<String, catalog_fakes.FakeRoute>{
          _catalogUrl: catalog_fakes.FakeRoute.fixture(
            'aidoku_french_legacy_index.min.json',
          ),
        });
    final fixture = _Fixture(
      addons: addons,
      catalogs: _GatedPreviewService(
        gate: gate.future,
        fetcher: fetcher.call,
        addons: addons,
        store: LibraryCatalogMemoryStore(),
        clock: () => DateTime.utc(2026, 10, 11, 8),
      ),
      aidoku: FakeAidokuService(),
      health: MemoryHealthStore(),
      fetcher: fetcher,
    );
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add a catalogue (URL)'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey<String>('catalog-url-field')),
      _catalogUrl,
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Show sources'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Loading the catalogue…'), findsOneWidget);

    // Another part of the app shows a page while the catalogue loads.
    unawaited(
      Navigator.of(tester.element(find.byType(LibrarySourcesView))).push<void>(
        MaterialPageRoute<void>(
          builder: (_) => const Scaffold(body: Text('Other page')),
        ),
      ),
    );
    await tester.pumpAndSettle();

    gate.complete();
    await tester.pumpAndSettle();
    expect(find.byType(LibraryCatalogPreviewScreen), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Loading the catalogue…'), findsNothing);
    expect(find.text('Other page'), findsOneWidget, reason: 'left open');
  });

  testWidgets('an imported file must be a .json or .aix catalogue', (
    tester,
  ) async {
    final fixture = await _fixture();
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();

    fixture.pickedFile = const LibraryPickedCatalogFile(
      name: 'notes.txt',
      bytes: <int>[0x68, 0x69],
    );
    await tester.tap(find.text('Import a file'));
    await tester.pumpAndSettle();
    expect(
      find.text('Choose a catalogue file ending in .json or .aix.'),
      findsOneWidget,
    );
    expect(find.byType(LibraryCatalogPreviewScreen), findsNothing);

    fixture.pickedFile = LibraryPickedCatalogFile(
      name: 'source.json',
      bytes: utf8.encode(
        jsonEncode(<String, Object?>{
          'info': <String, Object?>{
            'id': 'fr.lelscanfr',
            'name': 'LelscanFR',
            'version': 3,
            'languages': <String>['fr'],
            'url': 'https://www.lelscanfr.com',
          },
        }),
      ),
    );
    await tester.tap(find.text('Import a file'));
    await tester.pumpAndSettle();
    expect(find.byType(LibraryCatalogPreviewScreen), findsOneWidget);
    expect(find.text('Aidoku source (source.json)'), findsOneWidget);
    expect(find.textContaining('Read from a file on this device.'), findsOne);
    expect(
      tester.widget<Checkbox>(find.byType(Checkbox)).value,
      isFalse,
      reason: 'a single source is not pre-selected either',
    );
    expect(find.text('Activate (0)'), findsOneWidget);
  });

  testWidgets('a catalogue error is translated, with the raw detail apart', (
    tester,
  ) async {
    final fixture = await _fixture(
      routes: <String, catalog_fakes.FakeRoute>{
        _catalogUrl: catalog_fakes.FakeRoute.failure(
          LibraryNetworkErrorKind.serverUnavailable,
          statusCode: 522,
        ),
      },
    );
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Add a catalogue (URL)'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey<String>('catalog-url-field')),
      _catalogUrl,
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Show sources'));
    await tester.pumpAndSettle();

    expect(find.text('The catalogue could not be opened'), findsOneWidget);
    expect(
      find.text("The site's server is unavailable right now. Try again later."),
      findsOneWidget,
    );
    expect(find.textContaining('HTTP 522'), findsNothing, reason: 'folded');
    await tester.tap(find.text('Technical details'));
    await tester.pump();
    expect(find.textContaining('HTTP 522'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('forgetting a catalogue can deactivate its sources', (
    tester,
  ) async {
    final fixture = await _fixture(
      installed: <LibraryAddon>[lelscan, books],
      remembered: <LibraryStoredCatalog>[
        LibraryStoredCatalog(
          url: _catalogUrl,
          name: 'Aidoku FR',
          format: LibraryCatalogFormat.aidokuLegacyIndex,
          lastFetchedAt: DateTime.utc(2026, 10, 10, 12),
          sourceCount: 10,
        ),
      ],
    );
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Forget'));
    await tester.pumpAndSettle();
    expect(find.text('Forget this catalogue?'), findsOneWidget);
    await tester.tap(find.text('Deactivate its sources'));
    await tester.pumpAndSettle();

    expect(find.text('Aidoku FR'), findsNothing);
    expect(fixture.addons.addons.map((addon) => addon.id), <String>[books.id]);
    expect(fixture.sourcesChanged, 1);
    expect(
      find.text('Catalogue forgotten. 1 source(s) deactivated.'),
      findsOneWidget,
    );
  });

  testWidgets('controller input moves the focus and activates controls', (
    tester,
  ) async {
    final fixture = await _fixture(installed: <LibraryAddon>[lelscan]);
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();
    expect(fixture.controller.isAttached, isTrue);

    // First move focuses the first control (Back), activation presses it.
    expect(fixture.controller.navigate(0, 1), isTrue);
    await tester.pump();
    expect(fixture.controller.activate(), isTrue);
    await tester.pump();
    expect(fixture.backs, 1);

    // B outside a text field lets LibraryScreen return to the hub.
    expect(fixture.controller.back(), isFalse);

    // Right / left move between the two import actions of one row.
    final addUrl = Focus.of(tester.element(find.text('Add a catalogue (URL)')));
    final importFile = Focus.of(tester.element(find.text('Import a file')));
    addUrl.requestFocus();
    await tester.pump();
    fixture.controller.navigate(1, 0);
    await tester.pump();
    expect(importFile.hasPrimaryFocus, isTrue);
    fixture.controller.navigate(-1, 0);
    await tester.pump();
    expect(addUrl.hasPrimaryFocus, isTrue);

    // A activates the focused action: the URL dialog opens.
    fixture.controller.activate();
    await tester.pumpAndSettle();
    expect(find.text('Catalogue address'), findsOneWidget);
  });

  testWidgets('with the keyboard up on a landscape iPhone, the URL field and '
      'its Paste button stay clear of the actions', (tester) async {
    final fixture = await _fixture();
    await pumpLibraryUi(tester, fixture.view(), size: const Size(844, 390));
    tester.view.padding = const FakeViewPadding(
      left: 47,
      right: 47,
      bottom: 21,
    );
    await tester.pumpAndSettle();
    String? clipboardReads;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.getData') {
          clipboardReads = _catalogUrl;
          return <String, Object?>{'text': _catalogUrl};
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );

    final add = find.text('Add a catalogue (URL)');
    await tester.ensureVisible(add);
    await tester.tap(add);
    await tester.pumpAndSettle();
    for (final keyboard in <double>[150, 190, 210]) {
      tester.view.viewInsets = FakeViewPadding(bottom: keyboard);
      await tester.pumpAndSettle();

      final field = tester.getRect(
        find.byKey(const ValueKey<String>('catalog-url-field')),
      );
      final paste = tester.getRect(find.byTooltip('Paste'));
      final show = tester.getRect(
        find.widgetWithText(FilledButton, 'Show sources'),
      );
      final cancel = tester.getRect(find.widgetWithText(TextButton, 'Cancel'));
      for (final action in <Rect>[show, cancel]) {
        expect(field.overlaps(action), isFalse, reason: 'keyboard $keyboard');
        expect(paste.overlaps(action), isFalse, reason: 'keyboard $keyboard');
      }
      expect(
        field.bottom,
        lessThanOrEqualTo(390 - keyboard),
        reason: 'the field is above the keyboard ($keyboard)',
      );
      // The Paste button is not clipped by the scrolling content.
      final visible = tester.getRect(
        find
            .descendant(
              of: find.byType(AlertDialog),
              matching: find.byType(SingleChildScrollView),
            )
            .first,
      );
      expect(
        visible.contains(paste.topLeft) && visible.contains(paste.bottomRight),
        isTrue,
        reason: 'Paste $paste visible in $visible ($keyboard)',
      );
    }

    // A tap on Paste reaches it (it used to land on 'Show sources').
    await tester.tap(find.byTooltip('Paste'));
    await tester.pump();
    expect(clipboardReads, _catalogUrl);
    expect(
      tester
          .widget<TextField>(
            find.byKey(const ValueKey<String>('catalog-url-field')),
          )
          .controller!
          .text,
      _catalogUrl,
    );
    expect(find.byType(LibraryCatalogPreviewScreen), findsNothing);
  });

  testWidgets('the view detaches its controller delegate when removed', (
    tester,
  ) async {
    final fixture = await _fixture();
    await pumpLibraryUi(tester, fixture.view());
    await tester.pumpAndSettle();
    expect(fixture.controller.isAttached, isTrue);
    fixture.controller.navigate(0, 1);
    await tester.pump();
    expect(
      FocusManager.instance.highlightStrategy,
      FocusHighlightStrategy.alwaysTraditional,
    );
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(fixture.controller.isAttached, isFalse);
    expect(
      FocusManager.instance.highlightStrategy,
      FocusHighlightStrategy.automatic,
      reason: 'leaving the section gives the highlight back to touch',
    );
  });
}
