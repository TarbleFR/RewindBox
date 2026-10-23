import 'package:neostation/widgets/header_layout.dart';
// Full production Header + NativeCarousel + SystemCard composition.
// Optional local reference art is used for review only, never redistributed.
import 'dart:io';
import 'dart:ui' as ui;
// Native readings are injected at the plugin interface; no product dependency is added.
// ignore: depend_on_referenced_packages
import 'package:battery_plus_platform_interface/battery_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neoplay_bridge/neoplay_bridge.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/my_systems.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/services/controller_battery_service.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/system_card.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/widgets/header.dart';
import 'package:neostation/widgets/native_carousel.dart';
import 'package:neostation/widgets/system_logo_fallback.dart';

class _Battery extends BatteryPlatform {
  @override
  Future<int> get batteryLevel async => 90;
  @override
  Future<bool> get isInBatterySaveMode async => false;
  @override
  Stream<BatteryState> get onBatteryStateChanged => const Stream.empty();
  @override
  Future<BatteryState> get batteryState async => BatteryState.discharging;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ThemeProvider theme;
  late Directory artDir;
  const folders = ['nes', 'sms', 'md', 'gb', 'snes'];
  const names = [
    'Nintendo Entertainment System',
    'Sega Master System',
    'Sega Mega Drive',
    'Game Boy',
    'Super Nintendo',
  ];
  setUpAll(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('neostation/neoplay/controller_battery'),
          (_) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    BatteryPlatform.instance = _Battery();
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('fr', AppLocale.fr)],
      initLanguageCode: 'fr',
    );
    theme = await ThemeProvider.create();
    final roboto = File(
      '${File(Platform.resolvedExecutable).parent.parent.parent.path}/material_fonts/Roboto-Regular.ttf',
    );
    if (roboto.existsSync()) {
      await (FontLoader(
            'Roboto',
          )..addFont(roboto.readAsBytes().then((b) => ByteData.sublistView(b))))
          .load();
    }
    await (FontLoader(
          'packages/material_symbols_icons/MaterialSymbolsOutlined',
        )..addFont(
          rootBundle.load(
            'packages/material_symbols_icons/lib/fonts/MaterialSymbolsOutlined.ttf',
          ),
        ))
        .load();
    for (final family in ['MaterialSymbolsRounded', 'MaterialSymbolsSharp']) {
      await (FontLoader('packages/material_symbols_icons/$family')..addFont(
            rootBundle.load(
              'packages/material_symbols_icons/lib/fonts/$family.ttf',
            ),
          ))
          .load();
    }
    await (FontLoader('MaterialIcons')..addFont(
          File(
            '${File(Platform.resolvedExecutable).parent.parent.parent.path}/material_fonts/MaterialIcons-Regular.otf',
          ).readAsBytes().then((b) => ByteData.sublistView(b)),
        ))
        .load();
    artDir = await Directory.systemTemp.createTemp(
      'rewindbox-carousel-review-',
    );
    final reference = Platform.environment['REFERENCE_CAROUSEL'];
    ui.Image? capture;
    if (reference != null) {
      capture = await (await ui.instantiateImageCodec(
        await File(reference).readAsBytes(),
      )).getNextFrame().then((f) => f.image);
    }
    const crops = [
      Rect.fromLTRB(223, 224, 487, 487),
      Rect.fromLTRB(520, 185, 811, 482),
      Rect.fromLTRB(867, 146, 1196, 483),
      Rect.fromLTRB(1242, 184, 1534, 482),
      Rect.fromLTRB(1568, 228, 1825, 485),
    ];
    for (var i = 0; i < folders.length; i++) {
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      const rect = Rect.fromLTWH(0, 0, 512, 512);
      if (capture != null) {
        canvas.drawImageRect(
          capture,
          crops[i],
          rect,
          Paint()..filterQuality = FilterQuality.high,
        );
      } else {
        canvas.drawRect(
          rect,
          Paint()
            ..shader = LinearGradient(
              colors: [
                Colors.primaries[i * 2].shade700,
                Colors.blueGrey.shade900,
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ).createShader(rect),
        );
        final text = TextPainter(
          text: TextSpan(
            text: folders[i].toUpperCase(),
            style: const TextStyle(
              fontFamily: 'Roboto',
              fontSize: 88,
              color: Colors.white,
              fontWeight: FontWeight.bold,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: 480);
        text.paint(canvas, Offset((512 - text.width) / 2, 210));
      }
      final image = await recorder.endRecording().toImage(512, 512);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await File(
        '${artDir.path}/${folders[i]}.png',
      ).writeAsBytes(bytes!.buffer.asUint8List());
      image.dispose();
    }
    capture?.dispose();
  });
  tearDownAll(() async {
    theme.dispose();
    await artDir.delete(recursive: true);
  });

  for (final size in [const Size(956, 440), const Size(393, 852)]) {
    testWidgets(
      'complete production composition retains branded artwork without duplicate footers: $size',
      (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.binding.setSurfaceSize(size);
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final config = SqliteConfigProvider(), assets = NeoAssetsProvider();
        addTearDown(config.dispose);
        addTearDown(assets.dispose);
        ControllerBatteryService.instance.controllers.value = [
          const NeoPlayControllerBattery(
            player: 1,
            name: 'DualSense',
            percent: 100,
            charge: 'discharging',
            low: false,
          ),
        ];
        final extent = ValueNotifier<double>(80),
            selection = ValueNotifier<int>(2);
        addTearDown(extent.dispose);
        addTearDown(selection.dispose);
        final capture = GlobalKey();
        await tester.pumpWidget(const MaterialApp(home: SizedBox()));
        final imageContext = tester.element(find.byType(SizedBox).last);
        await tester.runAsync(() async {
          for (final asset in [
            'assets/images/icons/grids.webp',
            'assets/images/icons/enhance-prize.webp',
            'assets/images/icons/box-search.webp',
            'assets/images/icons/setting.webp',
            'assets/images/gamepad/Xbox_X_button.png',
            'assets/images/gamepad/Xbox_LB_bumper.png',
            'assets/images/gamepad/Xbox_RB_bumper.png',
            'assets/images/gamepad/Xbox_LB_bumper_filled.png',
            'assets/images/gamepad/Xbox_RB_bumper_filled.png',
          ]) {
            await precacheImage(AssetImage(asset), imageContext);
          }
          for (final folder in folders) {
            await precacheImage(
              ResizeImage(
                FileImage(File('${artDir.path}/$folder.png')),
                width: 1024,
              ),
              imageContext,
            );
          }
        });
        final safe = size.width > size.height
            ? const EdgeInsets.symmetric(horizontal: 59)
            : const EdgeInsets.only(top: 59);
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
                theme: AppThemes.darkTheme,
                locale: const Locale('fr'),
                localizationsDelegates:
                    FlutterLocalization.instance.localizationsDelegates,
                supportedLocales: FlutterLocalization.instance.supportedLocales,
                home: MediaQuery(
                  data: MediaQueryData(size: size, viewPadding: safe),
                  child: RepaintBoundary(
                    key: capture,
                    child: Scaffold(
                      body: DecoratedBox(
                        decoration: const BoxDecoration(
                          gradient: LinearGradient(
                            colors: [Color(0xFF12203F), Color(0xFF071621)],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                        ),
                        child: MainMenuChromeLayout(
                          baseClearance: 46.r,
                          header: Header(
                            selectedTabIndex: 0,
                            onTabSelected: (_) {},
                            onExtentChanged: (h) => extent.value = h,
                          ),
                          body: Stack(
                            children: [
                              Positioned.fill(
                                top: 51.r,
                                bottom: 86,
                                left: safe.left + 8,
                                right: safe.right + 8,
                                child: ValueListenableBuilder<int>(
                                  valueListenable: selection,
                                  builder: (_, selected, _) => NativeCarousel(
                                    perspective: true,
                                    itemCount: 5,
                                    initialIndex: selected,
                                    onPageChanged: (index, _) =>
                                        selection.value = index,
                                    itemBuilder: (_, i) => SystemCard(
                                      info: SystemInfo(
                                        title: names[i],
                                        folderName: folders[i],
                                        customBackgroundPath:
                                            '${artDir.path}/${folders[i]}.png',
                                      ),
                                      isSelected: i == selected,
                                      carouselArtworkOnly: true,
                                      backgroundCacheWidth: 1024,
                                    ),
                                  ),
                                ),
                              ),
                              Positioned(
                                left: 24,
                                right: 24,
                                bottom: 25,
                                child: ValueListenableBuilder<int>(
                                  valueListenable: selection,
                                  builder: (_, i, _) => Text(
                                    names[i],
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      fontFamily: 'Roboto',
                                      fontSize: 23,
                                      fontWeight: FontWeight.w600,
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
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 50));
        expect(
          find.byType(SystemLogoFallback),
          findsNothing,
          reason:
              'Artwork already carries branding; the grid footer must not be appended.',
        );
        expect(find.text('Sega Mega Drive'), findsOneWidget);
        final groups = [
          'header-controls',
          'tabs-container',
          'header-status',
        ].map((k) => tester.getRect(find.byKey(ValueKey(k)))).toList();
        for (var i = 0; i < groups.length; i++) {
          for (var j = i + 1; j < groups.length; j++) {
            expect(groups[i].overlaps(groups[j]), isFalse);
          }
        }
        final art = find.byKey(const ValueKey('console-artwork-md'));
        expect(tester.getSize(art).aspectRatio, closeTo(1, .001));
        final artBox = tester.renderObject<RenderBox>(art);
        final projected = MatrixUtils.transformRect(
          artBox.getTransformTo(null),
          Offset.zero & artBox.size,
        );
        final headerBox = tester.renderObject<RenderBox>(find.byType(Header));
        expect(
          projected.top,
          greaterThanOrEqualTo(headerBox.size.height),
          reason:
              'The actual artwork must remain below every header row in the same layout frame.',
        );

        expect(tester.takeException(), isNull);
        final boundary =
            capture.currentContext!.findRenderObject()!
                as RenderRepaintBoundary;
        final output = Directory('build/ui-correction-qa')
          ..createSync(recursive: true);
        await tester.runAsync(() async {
          final image = await boundary.toImage(pixelRatio: 2);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await File(
            '${output.path}/${size.width > size.height ? 'landscape' : 'portrait'}.png',
          ).writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
        await tester.pumpWidget(const SizedBox());
        await tester.pump(const Duration(minutes: 1));
        ControllerBatteryService.instance.controllers.value = [];
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );
  }
}
