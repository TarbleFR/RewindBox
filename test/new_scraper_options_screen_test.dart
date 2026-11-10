import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/scraper_screen/new_scraper_options_screen.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/widgets/glass/glass_surface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final dbHelper = DatabaseTestHelper();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  setUp(() async {
    await dbHelper.setUp();
  });

  tearDown(() async {
    await dbHelper.tearDown();
  });

  testWidgets('builds after localization becomes available', (tester) async {
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(1920, 1080)),
        child: ScreenUtilInit(
          designSize: const Size(1920, 1080),
          builder: (context, child) => MaterialApp(
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: const Scaffold(body: NewScraperOptionsScreen()),
          ),
        ),
      ),
    );

    await tester.pump();

    expect(find.text('Account'), findsOneWidget);
  });

  testWidgets('the side menu floats as bubbles unless its panel is chosen', (
    tester,
  ) async {
    Future<GlassSurface> rail(InterfaceStyleSettings settings) async {
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(1920, 1080)),
          child: ScreenUtilInit(
            designSize: const Size(1920, 1080),
            builder: (context, child) => MaterialApp(
              theme: applyLiquidGlass(AppThemes.darkTheme, settings),
              localizationsDelegates:
                  FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: const Scaffold(body: NewScraperOptionsScreen()),
            ),
          ),
        ),
      );
      await tester.pump();
      // MaterialApp animates theme changes; let it reach the new settings.
      await tester.pump(const Duration(milliseconds: 400));
      return tester.widget<GlassSurface>(
        find.byKey(const ValueKey('side-menu-rail')),
      );
    }

    final floating = await rail(InterfaceStyleSettings.defaults);
    expect(floating.fillColor, Colors.transparent);
    expect(floating.shadow, GlassShadow.none);
    final panel = await rail(
      const InterfaceStyleSettings(showSideMenuPanel: true),
    );
    expect(panel.fillColor, isNull);
    expect(panel.shadow, isNull);
  });
}
