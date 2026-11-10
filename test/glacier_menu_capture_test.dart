// RewindBox Glacier: real Flutter rendering of the Systems menu at the
// reference format (1837 x 856 px, 918.5 x 428 logical at 2x) with the demo
// data of the approved mock-up, plus the variants of the brief.
//
// The menu is composed from the production widgets (GlassBackdrop,
// MainMenuChromeLayout, Header, GlacierSystemsFrame, SystemCardGridView,
// SystemCard, GlacierSystemsFooter) with the System Art pack installed from
// the application assets by BundledSystemArt, as on a first launch offline.
// Only the library is demo data (it normally comes from the database), and
// the recent game's artwork is a synthetic picture standing in for scraped
// artwork. The mock-up is read only to compose the side-by-side comparison.
//
// Captures are written to build/glacier-qa/. Set GLACIER_FONT to a TTF to
// render with the app's Google Font (Anta); Roboto is used otherwise.
// ignore_for_file: depend_on_referenced_packages
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:battery_plus_platform_interface/battery_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/my_systems.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/my_systems_grid.dart';
import 'package:neostation/services/glacier_preset.dart';
import 'package:neostation/services/neo_assets_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/services/system_art/bundled_system_art.dart';
import 'package:neostation/services/system_art/system_art_alias_table.dart';
import 'package:neostation/themes/glacier_theme.dart';
import 'package:neostation/widgets/glass/glass_backdrop.dart';
import 'package:neostation/widgets/header.dart';
import 'package:neostation/widgets/header_layout.dart';

class _Battery extends BatteryPlatform {
  @override
  Future<int> get batteryLevel async => 40;
  @override
  Future<bool> get isInBatterySaveMode async => false;
  @override
  Stream<BatteryState> get onBatteryStateChanged => const Stream.empty();
  @override
  Future<BatteryState> get batteryState async => BatteryState.discharging;
}

const _row1 = ['fbneo', 'nes', 'sms', 'md', 'gb'];
const _row2 = ['snes', 'mcd', '32x', 'ps1', 'n64', 'gbc'];
const _demoNames = {
  'fbneo': 'FinalBurn Neo',
  'nes': 'NES',
  'sms': 'Master System',
  'md': 'Mega Drive',
  'gb': 'Game Boy',
  'snes': 'Super Nintendo',
  'mcd': 'Mega-CD',
  '32x': '32X',
  'ps1': 'PlayStation',
  'n64': 'Nintendo 64',
  'gbc': 'Game Boy Color',
};

final _ios = TargetPlatformVariant.only(TargetPlatform.iOS);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ThemeProvider theme;
  late Directory root;
  late String recentArt;
  late String userBackground;
  final out = Directory('build/glacier-qa')..createSync(recursive: true);

  setUpAll(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('neostation/neoplay/controller_battery'),
          (_) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    BatteryPlatform.instance = _Battery();
    SfxService().setEnabled(false);
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [
        MapLocale('fr', AppLocale.fr),
        MapLocale('en', AppLocale.en),
        MapLocale('de', AppLocale.de),
      ],
      initLanguageCode: 'fr',
    );
    final flutterRoot = File(
      Platform.resolvedExecutable,
    ).parent.parent.parent.path;
    final font = Platform.environment['GLACIER_FONT'];
    final textFont = font != null && File(font).existsSync()
        ? File(font)
        : File('$flutterRoot/material_fonts/Roboto-Regular.ttf');
    final bold = File('$flutterRoot/material_fonts/Roboto-Bold.ttf');
    for (final family in ['GlacierText', 'Roboto']) {
      final loader = FontLoader(family)
        ..addFont(textFont.readAsBytes().then(ByteData.sublistView));
      if (family == 'Roboto' && bold.existsSync()) {
        loader.addFont(bold.readAsBytes().then(ByteData.sublistView));
      }
      await loader.load();
    }
    for (final family in [
      'MaterialSymbolsOutlined',
      'MaterialSymbolsRounded',
      'MaterialSymbolsSharp',
    ]) {
      await (FontLoader('packages/material_symbols_icons/$family')..addFont(
            rootBundle.load(
              'packages/material_symbols_icons/lib/fonts/$family.ttf',
            ),
          ))
          .load();
    }

    root = await Directory.systemTemp.createTemp('rewindbox-glacier-qa-');
    final themes = Directory('${root.path}/themes')..createSync();
    BundledSystemArt.themesDirectoryOverride = () async => themes.path;
    NeoAssetsService.debugSetThemesDirectory(themes.path);
    expect(await BundledSystemArt.ensureInstalled(), isTrue);
    SystemArtAliasTable.invalidate();

    recentArt = await _paintPicture(
      '${root.path}/recent-fanart.png',
      const Size(1024, 576),
      _paintNightCastle,
    );
    File(recentArt).copySync('${out.path}/demo-recent-game-artwork.png');
    userBackground = await _paintPicture(
      '${root.path}/user-background.png',
      const Size(512, 512),
      _paintUserBackground,
    );
    theme = ThemeProvider.testing(
      themeName: GlacierPreset.themeName,
      interfaceStyle: GlacierPreset.interfaceSettings(),
    );
  });

  tearDownAll(() async {
    BundledSystemArt.themesDirectoryOverride = null;
    NeoAssetsService.debugSetThemesDirectory(null);
    SystemArtAliasTable.invalidate();
    theme.dispose();
    SfxService().setEnabled(true);
    await root.delete(recursive: true);
  });

  SystemInfo recent() => SystemInfo(
    title: 'Hogwarts Legacy',
    folderName: 'recent_hogwarts-legacy',
    primaryFolderName: 'recent_games',
    customBackgroundPath: recentArt,
    numOfRoms: 1,
    isGame: true,
  );

  SystemInfo system(String folder, {String? title, String? background}) =>
      SystemInfo(
        title: title ?? _demoNames[folder],
        shortName: folder.toUpperCase(),
        folderName: folder,
        primaryFolderName: folder,
        numOfRoms: 12,
        customBackgroundPath: background,
      );

  List<SystemInfo> demo({bool withRecent = true}) => [
    if (withRecent) recent(),
    for (final f in _row1) system(f),
    for (final f in _row2) system(f),
  ];

  Future<GlobalKey> pumpMenu(
    WidgetTester tester, {
    required Size physical,
    double dpr = 2,
    EdgeInsets safe = EdgeInsets.zero,
    List<SystemInfo>? systems,
    int selected = 0,
    double textScale = 1,
    bool reduceMotion = false,
    String locale = 'fr',
    String pack = BundledSystemArt.folder,
  }) async {
    final cards = systems ?? demo();
    FlutterLocalization.instance.translate(locale);
    tester.view.physicalSize = physical;
    tester.view.devicePixelRatio = dpr;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final logical = physical / dpr;
    final config = SqliteConfigProvider();
    final assets = NeoAssetsProvider()..debugSetActiveTheme(pack);
    addTearDown(config.dispose);
    addTearDown(assets.dispose);
    final capture = GlobalKey();
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    final imageContext = tester.element(find.byType(SizedBox).last);
    await tester.runAsync(() async {
      await precacheImage(
        const AssetImage(glacierBackgroundAsset),
        imageContext,
      );
      for (final asset in [
        glacierEmblemAsset,
        for (final tab in [
          'systems',
          'consoles',
          'search',
          'airplay',
          'achievements',
          'scraper',
          'settings',
          'library',
        ])
          glacierNavGlyphAsset(tab),
        'assets/images/gamepad/Xbox_A_button.png',
        'assets/images/gamepad/Xbox_X_button.png',
        'assets/images/gamepad/Xbox_Menu_button.png',
      ]) {
        await precacheImage(AssetImage(asset), imageContext);
      }
      for (final card in cards) {
        final logo = 'assets/images/logos/${card.folderName}.webp';
        if (!card.isGame && File(logo).existsSync()) {
          await precacheImage(
            ResizeImage(AssetImage(logo), width: 256),
            imageContext,
          );
        }
        final path =
            card.customBackgroundPath ??
            assets.getBackgroundForSystemSync(card.folderName ?? '');
        if (path != null && File(path).existsSync()) {
          await precacheImage(
            ResizeImage(FileImage(File(path)), width: 512),
            imageContext,
          );
          await precacheImage(
            ResizeImage(FileImage(File(path)), width: 192),
            imageContext,
          );
        }
      }
    });
    final base = theme.currentTheme;
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        minTextAdapt: true,
        splitScreenMode: true,
        builder: (_, _) => MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: theme),
            ChangeNotifierProvider.value(value: config),
            ChangeNotifierProvider.value(value: assets),
          ],
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            theme: base.copyWith(
              textTheme: base.textTheme.apply(fontFamily: 'GlacierText'),
            ),
            locale: Locale(locale),
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: MediaQuery(
              data: MediaQueryData(
                size: logical,
                devicePixelRatio: dpr,
                viewPadding: safe,
                padding: safe,
                textScaler: TextScaler.linear(textScale),
                disableAnimations: reduceMotion,
              ),
              child: DefaultTextStyle(
                style: const TextStyle(fontFamily: 'GlacierText'),
                child: RepaintBoundary(
                  key: capture,
                  child: Scaffold(
                    body: Stack(
                      children: [
                        const Positioned.fill(child: GlassBackdrop()),
                        Positioned.fill(
                          child: MainMenuChromeLayout(
                            baseClearance: 46.r,
                            header: Header(
                              selectedTabIndex: 0,
                              onTabSelected: (_) {},
                            ),
                            // As SystemContent on iOS: the Systems tab sits
                            // inside the horizontal safe area.
                            body: Padding(
                              padding: EdgeInsets.only(
                                left: safe.left,
                                right: safe.right,
                              ),
                              child: GlacierSystemsFrame(
                                current: cards[selected],
                                onEnter: () {},
                                onSettings: () {},
                                content: SystemCardGridView(
                                  glacier: true,
                                  crossAxisCount: 6,
                                  systems: cards,
                                  selectedIndex: selected,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    return capture;
  }

  Future<ui.Image> grab(WidgetTester tester, GlobalKey key, double dpr) async {
    final boundary =
        key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    late ui.Image image;
    await tester.runAsync(() async {
      image = await boundary.toImage(pixelRatio: dpr);
    });
    return image;
  }

  Future<void> save(WidgetTester tester, ui.Image image, String name) async {
    await tester.runAsync(() async {
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await File(
        '${out.path}/$name.png',
      ).writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  Rect rectOf(WidgetTester tester, String key) =>
      tester.getRect(find.byKey(ValueKey(key)));

  testWidgets(
    'reference capture: 1837 x 856, demo data, order, two full rows, footer, focus',
    (tester) async {
      final key = await pumpMenu(tester, physical: const Size(1837, 856));
      expect(tester.takeException(), isNull);

      // Order: recent game, then the systems of the mock-up, row by row.
      final ids = ['recent_hogwarts-legacy', ..._row1, ..._row2];
      final cards = [for (final id in ids) rectOf(tester, 'glacier-card-$id')];
      for (var i = 0; i < 12; i++) {
        final row = i ~/ 6, col = i % 6;
        expect(cards[i].top, closeTo(cards[row * 6].top, .01), reason: ids[i]);
        expect(cards[i].left, closeTo(cards[col].left, .01), reason: ids[i]);
        expect(cards[i].width, closeTo(cards[0].width, .01), reason: ids[i]);
        expect(cards[i].height, closeTo(cards[0].height, .01), reason: ids[i]);
      }
      expect(cards[6].top, greaterThan(cards[0].bottom));

      // Two full rows between the title and the action bar.
      final title = rectOf(tester, 'glacier-section-header');
      final footer = rectOf(tester, 'glacier-systems-footer');
      expect(cards.first.top, greaterThan(title.bottom));
      expect(cards.last.bottom, lessThan(footer.top));
      expect(footer.bottom, lessThanOrEqualTo(428));

      // Title aligned with the first card; footer as wide as the grid.
      expect(title.left, closeTo(cards[0].left, .5));
      expect(footer.left, closeTo(cards[0].left, .5));
      expect(footer.right, closeTo(cards[5].right, .5));

      // Focus frame on the first card; "A · Jouer" at the right of the bar.
      final focus = rectOf(tester, 'glacier-focus-frame');
      expect(focus.center.dx, closeTo(cards[0].center.dx, .5));
      expect(focus.center.dy, closeTo(cards[0].center.dy, .5));
      expect(focus.width, greaterThan(cards[0].width));
      final play = rectOf(tester, 'glacier-footer-primary');
      expect(play.right, closeTo(footer.right - 3.r, 1));
      expect(find.text('Jouer'), findsOneWidget);
      expect(find.text('Dernier joué'), findsOneWidget);
      expect(find.text('Hogwarts Legacy'), findsNWidgets(2));
      expect(find.text('Mode de Vue'), findsOneWidget);
      // Section title (the tab strip also names the active tab).
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('glacier-section-header')),
          matching: find.text('Systèmes'),
        ),
        findsOneWidget,
      );

      // Header: brand left, LB · 8 tabs · RB centred, status right.
      final brand = rectOf(tester, 'glacier-brand');
      final lb = rectOf(tester, 'glacier-bumper-lb');
      final rb = rectOf(tester, 'glacier-bumper-rb');
      final status = rectOf(tester, 'header-status');
      expect(brand.right, lessThan(lb.left));
      expect(rb.right, lessThan(status.left));
      expect((lb.left + rb.right) / 2, closeTo(918.5 / 2, 2));
      for (final tab in [
        'systems',
        'consoles',
        'search',
        'airplay',
        'achievements',
        'scraper',
        'settings',
        'library',
      ]) {
        expect(
          find.byKey(ValueKey('glacier-nav-glyph-$tab')),
          findsWidgets,
          reason: tab,
        );
      }

      // Measurements in reference pixels (2x), next to the composition.
      final reference = jsonDecode(
        File(
          'docs/design/rewindbox-glacier/reference/composition.json',
        ).readAsStringSync(),
      )['reference'];
      final strip = rectOf(tester, 'main-menu-tab-strip');
      List<int> px(double a, double b) => [(a * 2).round(), (b * 2).round()];
      final measured = {
        'xContent': px(cards[0].left, cards[5].right),
        'headerY': px(strip.top, strip.bottom),
        'sectionY': px(title.top, title.bottom),
        'row1Y': px(cards[0].top, cards[0].bottom),
        'row2Y': px(cards[6].top, cards[6].bottom),
        'footerY': px(footer.top, footer.bottom),
        'cardSize': px(cards[0].width, cards[0].height),
      };
      File('${out.path}/measurements.json').writeAsStringSync(
        const JsonEncoder.withIndent(
          '  ',
        ).convert({'reference': reference, 'flutter': measured}),
      );

      final image = await grab(tester, key, 2);
      expect(image.width, 1837);
      expect(image.height, 856);
      await save(tester, image, 'glacier-reference-1837x856');
      await tester.runAsync(() async {
        final mock = await (await ui.instantiateImageCodec(
          await File(
            'docs/design/rewindbox-glacier/reference/MENU-CIBLE.png',
          ).readAsBytes(),
        )).getNextFrame();
        final recorder = ui.PictureRecorder();
        final canvas = Canvas(recorder);
        const gap = 24;
        canvas.drawRect(
          Rect.fromLTWH(0, 0, 1837, 856.0 * 2 + gap),
          Paint()..color = Colors.white,
        );
        canvas.drawImage(mock.image, Offset.zero, Paint());
        canvas.drawImage(image, Offset(0, 856.0 + gap), Paint());
        final both = await recorder.endRecording().toImage(1837, 856 * 2 + gap);
        final bytes = await both.toByteData(format: ui.ImageByteFormat.png);
        await File(
          '${out.path}/glacier-mockup-vs-flutter.png',
        ).writeAsBytes(bytes!.buffer.asUint8List());
        both.dispose();
        mock.image.dispose();
      });
      image.dispose();
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(minutes: 1));
    },
    variant: _ios,
  );

  Future<void> variant(
    WidgetTester tester,
    String name, {
    required Size physical,
    double dpr = 2,
    EdgeInsets safe = EdgeInsets.zero,
    List<SystemInfo>? systems,
    int selected = 0,
    double textScale = 1,
    bool reduceMotion = false,
    String locale = 'fr',
    void Function()? check,
  }) async {
    final key = await pumpMenu(
      tester,
      physical: physical,
      dpr: dpr,
      safe: safe,
      systems: systems,
      selected: selected,
      textScale: textScale,
      reduceMotion: reduceMotion,
      locale: locale,
    );
    expect(tester.takeException(), isNull, reason: name);
    final footer = rectOf(tester, 'glacier-systems-footer');
    final logical = physical / dpr;
    expect(footer.bottom, lessThanOrEqualTo(logical.height - safe.bottom));
    expect(footer.left, greaterThanOrEqualTo(safe.left));
    expect(footer.right, lessThanOrEqualTo(logical.width - safe.right));
    final header = tester.getRect(find.byType(Header));
    expect(header.width, closeTo(logical.width, .01));
    check?.call();
    final image = await grab(tester, key, dpr);
    await save(tester, image, name);
    image.dispose();
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(minutes: 1));
  }

  testWidgets('iPhone landscape with notch and home indicator', (tester) async {
    await variant(
      tester,
      'variant-iphone-notch-956x440',
      physical: const Size(2868, 1320),
      dpr: 3,
      safe: const EdgeInsets.only(left: 62, right: 62, bottom: 21),
      check: () {
        final first = rectOf(tester, 'glacier-card-recent_hogwarts-legacy');
        final brand = rectOf(tester, 'glacier-brand');
        expect(first.left, greaterThanOrEqualTo(62));
        expect(brand.left, greaterThanOrEqualTo(62));
        // One margin, not the safe area twice (device report of
        // 2 November 2026): the first card lines up with the brand.
        expect(first.left, closeTo(brand.left, 1));
        expect(first.left, lessThan(62 + 12));
        expect(
          rectOf(tester, 'header-status').right,
          lessThanOrEqualTo(956 - 62),
        );
        expect(
          rectOf(tester, 'glacier-systems-footer').right,
          closeTo(956 - first.left, 1),
        );
      },
    );
  }, variant: _ios);

  testWidgets('compact width (iPhone SE landscape)', (tester) async {
    await variant(
      tester,
      'variant-compact-667x375',
      physical: const Size(1334, 750),
    );
  }, variant: _ios);

  testWidgets('iPad landscape: wider cards, scrolling for more', (
    tester,
  ) async {
    // A larger library: the taller screen shows more whole rows.
    final systems = [
      ...demo(),
      for (final f in [
        'gba',
        'ds',
        '3ds',
        'psp',
        'ps2',
        'ps3',
        'gc',
        'wii',
        'dc',
        'sat',
        'pce',
        'ngp',
      ])
        system(f, title: f.toUpperCase()),
    ];
    await variant(
      tester,
      'variant-ipad-1194x834',
      physical: const Size(2388, 1668),
      safe: const EdgeInsets.only(bottom: 20),
      systems: systems,
      check: () {
        final first = rectOf(tester, 'glacier-card-recent_hogwarts-legacy');
        final fourth = rectOf(tester, 'glacier-card-ngp');
        final footer = rectOf(tester, 'glacier-systems-footer');
        expect(fourth.bottom, lessThan(footer.top), reason: 'four whole rows');
        expect(first.height / first.width, inInclusiveRange(.78, 1.12));
      },
    );
  }, variant: _ios);

  testWidgets('large text and reduced motion: frame without animation', (
    tester,
  ) async {
    await pumpMenu(
      tester,
      physical: const Size(1837, 856),
      textScale: 1.35,
      reduceMotion: true,
    );
    final positioned = tester.widget<AnimatedPositioned>(
      find.byKey(const ValueKey('focus_indicator')),
    );
    expect(positioned.duration, Duration.zero);
    expect(tester.takeException(), isNull);
    await variant(
      tester,
      'variant-large-text-reduced-motion',
      physical: const Size(1837, 856),
      textScale: 1.35,
      reduceMotion: true,
    );
  }, variant: _ios);

  testWidgets('no recent game: the first system takes its place', (
    tester,
  ) async {
    await variant(
      tester,
      'variant-no-recent-game',
      physical: const Size(1837, 856),
      systems: demo(withRecent: false),
    );
    await pumpMenu(
      tester,
      physical: const Size(1837, 856),
      systems: demo(withRecent: false),
    );
    final first = rectOf(tester, 'glacier-card-fbneo');
    final focus = rectOf(tester, 'glacier-focus-frame');
    expect(focus.center.dx, closeTo(first.center.dx, .5));
    expect(find.text('Entrer'), findsOneWidget);
    expect(find.text('Paramètres'), findsOneWidget);
    expect(find.text('12 Jeux'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(minutes: 1));
  }, variant: _ios);

  testWidgets(
    'hidden system, user background, long German names, selected console',
    (tester) async {
      final semantics = tester.ensureSemantics();
      final systems = [
        recent(),
        system('fbneo'),
        system('nes', title: 'Nintendo Entertainment System'),
        // "sms" hidden by the user: absent from the library list.
        system('md', background: userBackground),
        system('gb'),
        system('snes', title: 'Super Nintendo Entertainment System'),
        system('mcd', title: 'Sega Mega-CD'),
        system('32x'),
        system('ps1', title: 'Sony PlayStation'),
        system('n64'),
        system('gbc'),
        system('pspminis', title: 'PlayStation Portable Minis'),
        system('psp'),
      ];
      await variant(
        tester,
        'variant-de-long-names-hidden-user-background',
        physical: const Size(1837, 856),
        systems: systems,
        selected: 5,
        locale: 'de',
      );
      await pumpMenu(
        tester,
        physical: const Size(1837, 856),
        systems: systems,
        selected: 5,
        locale: 'de',
      );
      expect(find.byKey(const ValueKey('glacier-card-sms')), findsNothing);
      // Full names stay available to screen readers.
      expect(
        tester
            .getSemantics(find.byKey(const ValueKey('glacier-card-snes')))
            .label,
        'Super Nintendo Entertainment System',
      );
      semantics.dispose();
      // The user's own background wins over the pack image.
      final image = tester
          .widgetList<Image>(
            find.descendant(
              of: find.byKey(const ValueKey('glacier-card-md')),
              matching: find.byType(Image),
            ),
          )
          .first;
      expect(
        ((image.image as ResizeImage).imageProvider as FileImage).file.path,
        userBackground,
      );
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(minutes: 1));
    },
    variant: _ios,
  );

  testWidgets('scrolled cards stay under the title row and above the bar', (
    tester,
  ) async {
    final systems = [
      ...demo(),
      for (final f in ['gba', 'ds', '3ds', 'psp', 'ps2', 'ps3', 'gc', 'wii', 'dc', 'sat', 'pce', 'ngp'])
        system(f, title: f.toUpperCase()),
    ];
    final key = await pumpMenu(
      tester,
      physical: const Size(2868, 1320),
      dpr: 3,
      safe: const EdgeInsets.only(left: 62, right: 62, bottom: 21),
      systems: systems,
    );
    final scroll = find.descendant(
      of: find.byKey(const ValueKey('glacier-systems-layout')),
      matching: find.byType(SingleChildScrollView),
    );
    await tester.drag(scroll, const Offset(0, -260));
    await tester.pump(const Duration(seconds: 1));
    final viewport = tester.getRect(scroll);
    final title = rectOf(tester, 'glacier-section-header');
    final footer = rectOf(tester, 'glacier-systems-footer');
    // The grid is clipped to its band: nothing it paints can cover the
    // title, the view-mode button or the action bar.
    expect(viewport.top, greaterThanOrEqualTo(title.bottom));
    expect(viewport.bottom, lessThanOrEqualTo(footer.top));
    final clip = tester.renderObject<RenderClipRect>(
      find.ancestor(of: scroll, matching: find.byType(ClipRect)).first,
    );
    final clipRect = MatrixUtils.transformRect(
      clip.getTransformTo(null),
      Offset.zero & clip.size,
    );
    expect(clipRect.top, greaterThanOrEqualTo(title.bottom));
    expect(clipRect.bottom, lessThanOrEqualTo(footer.top));
    expect(tester.takeException(), isNull);
    final image = await grab(tester, key, 3);
    await save(tester, image, 'variant-scrolled-under-title');
    image.dispose();
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(minutes: 1));
  }, variant: _ios);

  testWidgets('another System Art pack: no Glacier art, logos fall back', (
    tester,
  ) async {
    final key = await pumpMenu(
      tester,
      physical: const Size(1837, 856),
      pack: 'some-downloaded-pack',
    );
    expect(tester.takeException(), isNull);
    final image = await grab(tester, key, 2);
    await save(tester, image, 'variant-pack-not-installed-logo-fallback');
    image.dispose();
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(minutes: 1));
  }, variant: _ios);
}

Future<String> _paintPicture(
  String path,
  Size size,
  void Function(Canvas canvas, Size size) painter,
) async {
  final recorder = ui.PictureRecorder();
  painter(Canvas(recorder), size);
  final image = await recorder.endRecording().toImage(
    size.width.round(),
    size.height.round(),
  );
  final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
  await File(path).writeAsBytes(bytes!.buffer.asUint8List());
  image.dispose();
  return path;
}

/// Synthetic stand-in for a scraped game fan art: a night sky and a castle
/// silhouette with lit windows.
void _paintNightCastle(Canvas canvas, Size size) {
  final rect = Offset.zero & size;
  canvas.drawRect(
    rect,
    Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF0B1626), Color(0xFF233B58), Color(0xFF0A0F18)],
        stops: [0, .62, 1],
      ).createShader(rect),
  );
  canvas.drawCircle(
    Offset(size.width * .78, size.height * .2),
    size.height * .06,
    Paint()..color = const Color(0xFFE8EEF5),
  );
  final castle = Paint()..color = const Color(0xFF070B12);
  final base = size.height * .72;
  final towers = [
    (.18, .30, .05),
    (.30, .18, .06),
    (.42, .10, .07),
    (.52, .22, .05),
    (.63, .14, .065),
    (.76, .28, .05),
  ];
  for (final (x, top, w) in towers) {
    final left = size.width * (x - w / 2), right = size.width * (x + w / 2);
    final y = size.height * top + size.height * .1;
    canvas.drawRect(Rect.fromLTRB(left, y, right, size.height), castle);
    canvas.drawPath(
      Path()
        ..moveTo(left - 6, y)
        ..lineTo(size.width * x, y - size.height * .12)
        ..lineTo(right + 6, y)
        ..close(),
      castle,
    );
  }
  canvas.drawRect(
    Rect.fromLTRB(size.width * .1, base, size.width * .9, size.height),
    castle,
  );
  final light = Paint()..color = const Color(0xFFF2C46B);
  for (var i = 0; i < 22; i++) {
    final x = size.width * (.14 + (i * 37 % 70) / 100);
    final y = size.height * (.42 + (i * 13 % 36) / 100);
    canvas.drawRect(Rect.fromLTWH(x, y, 6, 10), light);
  }
}

/// A personal per-system background (plain, recognisable).
void _paintUserBackground(Canvas canvas, Size size) {
  final rect = Offset.zero & size;
  canvas.drawRect(
    rect,
    Paint()
      ..shader = const LinearGradient(
        colors: [Color(0xFF6B2A86), Color(0xFF1D3E78)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ).createShader(rect),
  );
}
