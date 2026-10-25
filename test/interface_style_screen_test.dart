import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/interface_style_locale.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/screens/settings_screen/interface_style/interface_style_preview.dart';
import 'package:neostation/screens/settings_screen/interface_style/interface_style_screen.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';
import 'package:neostation/widgets/glass/glass_controls.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Settings › Themes › User interface: the preview follows the draft, Apply
/// persists it for the whole app, Restore defaults brings the designed look
/// back, and nothing is saved before Apply.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  String en(String key) => InterfaceStyleLocale.values['en']![key]!;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    // Taps play navigation sounds; the test host has no audio library.
    SfxService().setEnabled(false);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  tearDownAll(() => SfxService().setEnabled(true));

  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<ThemeProvider> pumpScreen(WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(956, 440));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final provider = ThemeProvider.testing();
    await tester.pumpWidget(
      ChangeNotifierProvider<ThemeProvider>.value(
        value: provider,
        child: ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, _) => Consumer<ThemeProvider>(
            builder: (context, theme, _) => MaterialApp(
              theme: theme.currentTheme,
              localizationsDelegates:
                  FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: const InterfaceStyleScreen(),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return provider;
  }

  LiquidGlassTheme previewGlass(WidgetTester tester) {
    final context = tester.element(find.byType(InterfaceStylePreview));
    return LiquidGlassTheme.of(context);
  }

  Finder row(String key) => find.byKey(ValueKey('interface-style-$key'));

  /// A segment label inside one row: several rows share labels ("Classic").
  Finder segment(String rowKey, String label) =>
      find.descendant(of: row(rowKey), matching: find.text(label));

  /// Rows below the fold live in the settings list, not in the preview.
  Future<void> reveal(WidgetTester tester, Finder target) async {
    final list = find.descendant(
      of: find.byType(InterfaceStyleScreen),
      matching: find.byType(Scrollable),
    );
    await tester.scrollUntilVisible(target, 80, scrollable: list.first);
    await tester.pumpAndSettle();
  }

  testWidgets('the preview follows the draft before anything is applied', (
    tester,
  ) async {
    final provider = await pumpScreen(tester);
    expect(previewGlass(tester).style, InterfaceStyle.liquidGlass);
    expect(find.byKey(const ValueKey('interface-style-unsaved')), findsNothing);

    await tester.tap(segment('style', en(InterfaceStyleLocale.styleMinimal)));
    await tester.pumpAndSettle();

    expect(previewGlass(tester).style, InterfaceStyle.minimal);
    expect(previewGlass(tester).blurEnabled, isFalse);
    expect(
      find.byKey(const ValueKey('interface-style-unsaved')),
      findsOneWidget,
    );
    // The application itself still runs the applied style.
    expect(provider.interfaceStyle, InterfaceStyleSettings.defaults);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(ThemeProvider.interfaceStylePreferenceKey), isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Apply persists the draft and Restore brings the defaults back', (
    tester,
  ) async {
    final provider = await pumpScreen(tester);
    await tester.tap(segment('style', en(InterfaceStyleLocale.styleClassic)));
    await tester.pumpAndSettle();
    await reveal(tester, row('tabBarStyle'));
    await tester.tap(
      segment('tabBarStyle', en(InterfaceStyleLocale.tabBarCompact)),
    );
    await tester.pumpAndSettle();

    final apply = row('apply');
    await reveal(tester, apply);
    await tester.tap(apply);
    await tester.pumpAndSettle();

    expect(provider.interfaceStyle.style, InterfaceStyle.classic);
    expect(provider.interfaceStyle.tabBarStyle, TabBarStyle.compact);
    final prefs = await SharedPreferences.getInstance();
    final saved = InterfaceStyleSettings.decode(
      prefs.getString(ThemeProvider.interfaceStylePreferenceKey),
    );
    expect(saved, provider.interfaceStyle);
    expect(find.byKey(const ValueKey('interface-style-unsaved')), findsNothing);
    // The live theme now carries the applied style.
    final screenContext = tester.element(find.byType(InterfaceStyleScreen));
    expect(LiquidGlassTheme.of(screenContext).style, InterfaceStyle.classic);

    final reset = row('reset');
    await reveal(tester, reset);
    await tester.tap(reset);
    await tester.pumpAndSettle();
    expect(provider.interfaceStyle, InterfaceStyleSettings.defaults);
    expect(previewGlass(tester).style, InterfaceStyle.liquidGlass);
    expect(
      InterfaceStyleSettings.decode(
        prefs.getString(ThemeProvider.interfaceStylePreferenceKey),
      ),
      InterfaceStyleSettings.defaults,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('sliders adjust the draft within 0..1 and show a percentage', (
    tester,
  ) async {
    await pumpScreen(tester);
    final blur = row('blur');
    await reveal(tester, blur);
    final slider = find.descendant(of: blur, matching: find.byType(Slider));
    final rect = tester.getRect(slider);
    await tester.tapAt(Offset(rect.right - 2, rect.center.dy));
    await tester.pumpAndSettle();
    expect(previewGlass(tester).settings.blur, 1.0);
    expect(find.text('100 %'), findsWidgets);
    expect(find.byType(GlassSlider), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
