// LibraryCatalogPreviewScreen: nothing is pre-selected, the convenience
// selection only takes sources NeoStation can read, activation installs
// exactly the ticked ids, the summary explains skipped sources, and a
// Tachiyomi repository can only be looked at.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_catalog_preview_screen.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_catalog_import_fakes.dart' as catalog_fakes;
import 'library_ui_sources_harness.dart';

const String _catalogUrl = 'https://example.org/aidoku/index.min.json';

LibraryCatalogSourceEntry _entry(
  String id,
  String name, {
  int version = 3,
  int rating = 0,
  bool activatable = true,
}) => LibraryCatalogSourceEntry(
  id: id,
  addonId: LibraryAddon.aidokuAddonId(id),
  name: name,
  version: version,
  versionLabel: '$version',
  languages: const <String>['fr'],
  contentRating: rating,
  activatable: activatable,
);

class _Host {
  _Host(this.addons, this.service);

  final LibraryAddonService addons;
  final LibrarySourceCatalogService service;
  LibraryActivationResult? result;
  bool popped = false;
}

/// Catalogue service whose activation waits for [gate].
class _GatedCatalogService extends LibrarySourceCatalogService {
  _GatedCatalogService({required super.addons, required this.gate})
    : super(
        fetcher: catalog_fakes.FakeLibraryFetcher().call,
        store: LibraryCatalogMemoryStore(),
        clock: () => DateTime.utc(2026, 10, 11, 8),
      );

  final Future<void> gate;

  @override
  Future<LibraryActivationResult> activate(
    LibraryCatalogPreview preview,
    Set<String> sourceIds,
  ) async {
    await gate;
    return super.activate(preview, sourceIds);
  }
}

Future<_Host> _host(
  WidgetTester tester,
  LibraryCatalogPreview preview, {
  List<LibraryAddon> installed = const <LibraryAddon>[],
  Future<void>? activationGate,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final addons = LibraryAddonService.forTesting();
  await addons.load();
  if (installed.isNotEmpty) await addons.upsertAddons(installed);
  final service = activationGate != null
      ? _GatedCatalogService(addons: addons, gate: activationGate)
      : LibrarySourceCatalogService(
          fetcher: catalog_fakes.FakeLibraryFetcher().call,
          addons: addons,
          store: LibraryCatalogMemoryStore(),
          clock: () => DateTime.utc(2026, 10, 11, 8),
        );
  final host = _Host(addons, service);
  final aidoku = FakeAidokuService();
  await pumpLibraryUi(
    tester,
    Builder(
      builder: (context) => Center(
        child: FilledButton(
          onPressed: () async {
            host.result = await LibraryCatalogPreviewScreen.open(
              context,
              preview,
              catalogService: service,
              aidokuService: aidoku,
              imageCache: NoImageCache(),
              enableGamepad: false,
            );
            host.popped = true;
          },
          child: const Text('open preview'),
        ),
      ),
    ),
    size: const Size(1280, 1600),
  );
  await tester.tap(find.text('open preview'));
  await tester.pumpAndSettle();
  return host;
}

LibraryCatalogPreview _aidokuPreview(List<LibraryCatalogSourceEntry> sources) =>
    LibraryCatalogPreview(
      inputUrl: _catalogUrl,
      catalogUrl: _catalogUrl,
      documentUrl: _catalogUrl,
      resolvedUrl: _catalogUrl,
      format: LibraryCatalogFormat.aidokuLegacyIndex,
      name: 'Aidoku FR',
      sources: sources,
      fetchedAt: DateTime.utc(2026, 10, 11, 7),
    );

List<bool?> _checkboxValues(WidgetTester tester) => tester
    .widgetList<Checkbox>(find.byType(Checkbox))
    .map((box) => box.value)
    .toList();

void main() {
  _controllerListTests();

  final sources = <LibraryCatalogSourceEntry>[
    _entry('fr.astralmanga', 'Astral Manga', version: 5),
    _entry('fr.lelscanfr', 'LelscanFR', rating: 1),
    _entry('fr.mangasorigines', 'Mangas Origines', version: 7),
    _entry('fr.phenixscans', 'PhenixScans', version: 5),
    _entry('fr.sushiscan', 'SushiScan', version: 4),
  ];

  testWidgets('nothing is pre-selected and Activate (0) is disabled', (
    tester,
  ) async {
    await _host(tester, _aidokuPreview(sources));

    expect(find.text('Aidoku FR'), findsOneWidget);
    expect(find.text('Aidoku catalog (former format)'), findsOneWidget);
    expect(find.textContaining('5 source(s)'), findsOneWidget);
    expect(_checkboxValues(tester), everyElement(isFalse));
    expect(_checkboxValues(tester), hasLength(5));
    expect(find.text('Activate (0)'), findsOneWidget);
    final button = tester.widget<FilledButton>(
      find.byKey(const ValueKey<String>('activate-button')),
    );
    expect(button.onPressed, isNull);

    // Adapter status per source, translated.
    final astral = find.byKey(const ValueKey<String>('entry-fr.astralmanga'));
    expect(
      find.descendant(
        of: astral,
        matching: find.text(
          'The site moved to a new platform protected by a browser '
          'verification.',
        ),
      ),
      findsOneWidget,
    );
    final lelscan = find.byKey(const ValueKey<String>('entry-fr.lelscanfr'));
    expect(
      find.descendant(of: lelscan, matching: find.text('Reader available')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: lelscan, matching: find.text('Some adult content')),
      findsOneWidget,
    );
  });

  testWidgets(
    '"select all with a reader" only selects when tapped, and only readers',
    (tester) async {
      final host = await _host(tester, _aidokuPreview(sources));
      expect(_checkboxValues(tester), everyElement(isFalse));

      await tester.tap(find.text('Select all with a reader'));
      await tester.pump();
      expect(find.text('Activate (3)'), findsOneWidget);
      expect(_checkboxValues(tester), <bool>[false, true, true, false, true]);

      // Untick one by tapping its row, then activate.
      await tester.tap(
        find.byKey(const ValueKey<String>('entry-fr.mangasorigines')),
      );
      await tester.pump();
      await tester.tap(find.text('Activate (2)'));
      await tester.pumpAndSettle();

      expect(find.text('Activation finished'), findsOneWidget);
      expect(find.text('Added: 2'), findsOneWidget);
      expect(find.text('Updated: 0'), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      expect(host.popped, isTrue);
      expect(host.result?.added.map((addon) => addon.aidokuSourceId), <String>[
        'fr.lelscanfr',
        'fr.sushiscan',
      ]);
      expect(
        host.addons.addons.map((addon) => addon.aidokuSourceId).toSet(),
        <String>{'fr.lelscanfr', 'fr.sushiscan'},
        reason: 'exactly the ticked sources were installed',
      );
    },
  );

  testWidgets('installed versions, updates and skipped sources are explained', (
    tester,
  ) async {
    final installedNewer = testAidokuAddon(
      'fr.lelscanfr',
      'LelscanFR',
      version: '9',
      origin: 'https://other.example.org/index.min.json',
    );
    final installedOlder = testAidokuAddon(
      'fr.sushiscan',
      'SushiScan',
      version: '1',
    );
    final host = await _host(
      tester,
      _aidokuPreview(sources),
      installed: <LibraryAddon>[installedNewer, installedOlder],
    );
    // The preview was computed before; install state comes from the entry.
    expect(host.addons.addons, hasLength(2));

    await tester.tap(find.byKey(const ValueKey<String>('entry-fr.lelscanfr')));
    await tester.tap(find.byKey(const ValueKey<String>('entry-fr.sushiscan')));
    await tester.pump();
    await tester.tap(find.text('Activate (2)'));
    await tester.pumpAndSettle();

    expect(find.text('Updated: 1'), findsOneWidget);
    expect(find.text('Not activated: 1'), findsOneWidget);
    expect(
      find.text('• LelscanFR – version 9 is already active and is newer'),
      findsOneWidget,
    );
  });

  testWidgets('a Tachiyomi repository can be looked at, not activated', (
    tester,
  ) async {
    final preview = LibraryCatalogPreview(
      inputUrl: 'https://example.org/index.min.json',
      catalogUrl: 'https://example.org/index.min.json',
      documentUrl: 'https://example.org/index.min.json',
      resolvedUrl: 'https://example.org/index.min.json',
      format: LibraryCatalogFormat.tachiyomiRepository,
      name: null,
      sources: <LibraryCatalogSourceEntry>[
        _entry('123', 'MangaDex-like', activatable: false),
      ],
      fetchedAt: DateTime.utc(2026, 10, 11, 7),
    );
    await _host(tester, preview);

    expect(
      find.byKey(const ValueKey<String>('tachiyomi-banner')),
      findsOneWidget,
    );
    expect(find.text('Tachiyomi/Mihon repository'), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('activate-button')), findsNothing);
    expect(find.text('Select all with a reader'), findsNothing);
    final box = tester.widget<Checkbox>(find.byType(Checkbox));
    expect(box.onChanged, isNull);
    await tester.tap(find.text('MangaDex-like'));
    await tester.pump();
    expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isFalse);
  });

  testWidgets('back waits for a running activation and its summary', (
    tester,
  ) async {
    final gate = Completer<void>();
    final host = await _host(
      tester,
      _aidokuPreview(sources),
      activationGate: gate.future,
    );
    await tester.tap(find.byKey(const ValueKey<String>('entry-fr.lelscanfr')));
    await tester.pump();
    await tester.tap(find.text('Activate (1)'));
    await tester.pump();
    expect(find.text('Activating…'), findsOneWidget);

    // Back (button, swipe or controller B all go through maybePop) must
    // not drop the result the sources view needs.
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    expect(await navigator.maybePop(), isTrue);
    // The spinner keeps animating: pump past a route transition instead.
    await tester.pump(const Duration(milliseconds: 600));
    expect(host.popped, isFalse);
    expect(find.text('Activating…'), findsOneWidget);

    gate.complete();
    await tester.pumpAndSettle();
    expect(find.text('Added: 1'), findsOneWidget);
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    expect(host.popped, isTrue);
    expect(host.result?.changed, isTrue);
  });

  testWidgets('a local file preview says where it comes from', (tester) async {
    final preview = LibraryCatalogPreview(
      inputUrl: 'source.json',
      catalogUrl: 'file:source.json',
      documentUrl: 'file:source.json',
      resolvedUrl: 'file:source.json',
      format: LibraryCatalogFormat.aidokuSourceJson,
      name: 'Single',
      sources: <LibraryCatalogSourceEntry>[_entry('fr.lelscanfr', 'LelscanFR')],
      fetchedAt: DateTime.utc(2026, 10, 11, 7),
    );
    await _host(tester, preview);

    expect(
      find.textContaining('Read from a file on this device.'),
      findsOneWidget,
    );
    expect(find.text('Aidoku source (source.json)'), findsOneWidget);
    expect(_checkboxValues(tester), <bool>[false]);
  });
}

void _controllerListTests() {
  testWidgets('on a landscape iPhone several sources are visible at once', (
    tester,
  ) async {
    final preview = _aidokuPreview(<LibraryCatalogSourceEntry>[
      for (var index = 0; index < 12; index++)
        _entry('fr.source$index', 'Source $index'),
    ]);
    await pumpLibraryUi(
      tester,
      LibraryCatalogPreviewScreen(
        preview: preview,
        aidokuService: FakeAidokuService(),
        imageCache: NoImageCache(),
        enableGamepad: false,
      ),
      size: const Size(844, 390),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();
    // Once the catalogue information is scrolled away, the rows have the
    // whole height left by the title bar and the Activate button (fixed,
    // that information left room for less than two rows).
    final scrollRect = tester.getRect(
      find.byKey(const ValueKey<String>('preview-scroll')),
    );
    final row = tester.getRect(
      find.byKey(const ValueKey<String>('entry-fr.source0')),
    );
    expect(scrollRect.height, greaterThanOrEqualTo(3 * row.height));
    final activate = tester.getRect(
      find.byKey(const ValueKey<String>('activate-button')),
    );
    expect(activate.bottom, lessThanOrEqualTo(390));
    expect(activate.top, greaterThanOrEqualTo(scrollRect.bottom));
  });

  testWidgets('a controller scrolls through a Tachiyomi list it cannot tick', (
    tester,
  ) async {
    final preview = LibraryCatalogPreview(
      inputUrl: 'https://example.org/index.min.json',
      catalogUrl: 'https://example.org/index.min.json',
      documentUrl: 'https://example.org/index.min.json',
      resolvedUrl: 'https://example.org/index.min.json',
      format: LibraryCatalogFormat.tachiyomiRepository,
      name: 'Extensions',
      sources: <LibraryCatalogSourceEntry>[
        for (var index = 0; index < 20; index++)
          _entry('$index', 'Extension $index', activatable: false),
      ],
      fetchedAt: DateTime.utc(2026, 10, 11, 7),
    );
    await pumpLibraryUi(
      tester,
      LibraryCatalogPreviewScreen(
        preview: preview,
        aidokuService: FakeAidokuService(),
        imageCache: NoImageCache(),
        enableGamepad: false,
      ),
      size: const Size(844, 390),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();
    final list = find.byKey(const ValueKey<String>('preview-scroll'));
    bool visible(String text) {
      final found = find.text(text);
      if (found.evaluate().isEmpty) return false;
      final viewport = tester.getRect(list);
      final rect = tester.getRect(found);
      return rect.top >= viewport.top && rect.bottom <= viewport.bottom;
    }

    expect(visible('Extension 19'), isFalse);
    final layer = tester.state<LibraryFocusGamepadLayerState>(
      find.byType(LibraryFocusGamepadLayer),
    );
    for (var press = 0; press < 20; press++) {
      layer.move(TraversalDirection.down);
      await tester.pumpAndSettle();
    }
    expect(visible('Extension 19'), isTrue);
    // Nothing can be ticked on iOS.
    layer.activateFocused();
    await tester.pumpAndSettle();
    expect(_checkboxValues(tester), everyElement(isFalse));
  });
}
