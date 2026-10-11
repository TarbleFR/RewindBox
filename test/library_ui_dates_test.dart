// Dates of the Library screens in the app's real delegate order: lib/main.dart
// puts an English-only Material delegate before the Global ones, so every
// date formatted through MaterialLocalizations read 'Oct 9, 2026' inside
// translated sentences. The screens now use LibraryDateFormat (the Library
// language, with the year) and preload it when they start.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_date_format.dart';
import 'package:neostation/screens/library_screen/library_manga_details_screen.dart';
import 'package:neostation/screens/library_screen/library_screen.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart';
import 'library_ui_sources_harness.dart';

/// What the Global French Material formats give (the reference).
Future<MaterialLocalizations> _french() =>
    GlobalMaterialLocalizations.delegate.load(const Locale('fr'));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [
        MapLocale('en', AppLocale.en),
        MapLocale('fr', AppLocale.fr),
      ],
      initLanguageCode: 'fr',
    );
  });

  setUp(LibraryDateFormat.resetForTesting);

  testWidgets('chapter dates of a title page follow the Library language', (
    tester,
  ) async {
    final item = testMangaItem();
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 20)
      ..watchResult = testDetails(item, count: 20);
    await pumpLibraryUi(
      tester,
      LibraryMangaDetailsScreen(
        item: item,
        addon: testAidokuAddon('fr.lelscanfr', 'LelscanFR'),
        aidokuService: aidoku,
        readingStore: MemoryReadingStore(),
        imageCache: NoImageCache(),
        enableGamepad: false,
      ),
      locale: const Locale('fr'),
      wrapInScaffold: false,
      appDelegateOrder: true,
    );
    await tester.pumpAndSettle();

    // Chapter 20 was published on 2026-01-21 (UTC).
    final date = DateTime.utc(2026, 1, 21).toLocal();
    final row = find.byKey(const ValueKey<String>('chapter-20'));
    final french = (await _french()).formatShortDate(date);
    expect(french, contains('janv.'));
    expect(
      find.descendant(of: row, matching: find.text(french)),
      findsOneWidget,
    );
    expect(
      find.descendant(of: row, matching: find.textContaining('Jan')),
      findsNothing,
    );
  });

  testWidgets('the date a blocked source was checked has its year and the '
      'Library language', (tester) async {
    final backend = FakeFeedBackend();
    final feed = LibraryCatalogFeed(
      backend: backend,
      clock: TestClock().call,
      loadMoreThrottle: Duration.zero,
    );
    addTearDown(feed.dispose);
    final blocked = aidokuTestAddon('fr.blocked', name: 'Blocked Scans');
    backend.support['fr.blocked'] = blockedSupport(
      'fr.blocked',
      LibrarySourceKnownState.challenge,
    );
    tester.view.physicalSize = const Size(1280, 720);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, child) => MaterialApp(
          locale: const Locale('fr'),
          theme: ThemeData(extensions: [ChromeSurface.standard()]),
          localizationsDelegates: <LocalizationsDelegate<dynamic>>[
            const EnglishFirstMaterialLocalizations(),
            ...FlutterLocalization.instance.localizationsDelegates,
          ],
          supportedLocales: FlutterLocalization.instance.supportedLocales,
          home: Scaffold(
            body: LibraryScreen(
              feed: feed,
              loadAddons: () async => [blocked],
              enableSounds: false,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.pump();

    await tester.tap(find.text('1 source(s) indisponible(s)').first);
    await tester.pumpAndSettle();
    final verified = (await _french()).formatShortDate(
      DateTime.utc(2026, 10, 10).toLocal(),
    );
    expect(verified, endsWith('oct. 2026'));
    expect(find.textContaining('État vérifié le $verified ;'), findsOneWidget);
    expect(find.textContaining('Sat'), findsNothing);
    expect(find.textContaining('Oct'), findsNothing);
  });
}
