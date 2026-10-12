import 'package:external_display/external_display.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/console_manager_locale.dart';
import 'package:neostation/l10n/external_display_locale.dart';
import 'package:neostation/l10n/ui_refresh_rate_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/general_settings_content.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/setting_value_chip.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/ui_refresh_rate_setting_row.dart';
import 'package:neostation/services/external_display_service.dart';
import 'package:neostation/widgets/custom_toggle_switch.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:ui_refresh_rate/ui_refresh_rate.dart';

Map<String, Object?> externalState({
  bool supported = true,
  bool connected = false,
  String content = 'none',
  double screenWidth = 0,
  double screenHeight = 0,
  int mode = 0,
  bool enabled = true,
  // Always false since Build 449: outside a game the TV mirrors the iPhone.
  bool menuOnTV = false,
  bool suspended = false,
  bool mirroringActive = false,
  String accessoryStatus = 'unavailable',
}) => <String, Object?>{
  'supported': supported,
  'connected': connected,
  'content': content,
  'screenWidth': screenWidth,
  'screenHeight': screenHeight,
  'screenScale': 1.0,
  'mode': mode,
  'enabled': enabled,
  'menuOnTV': menuOnTV,
  'suspended': suspended,
  'mirroringActive': mirroringActive,
  'accessoryStatus': accessoryStatus,
  'sceneRole': connected ? 'scene' : 'none',
  'menuEngine': 'none',
};

Map<String, Object?> refreshRateState() => <String, Object?>{
  'hookStatus': 'installed',
  'storedEnabled': true,
  'activeEnabled': true,
  'screenMaxHz': 120,
  'engineTargetHz': 120.0,
  'cappedHz': 60.0,
  'lowPowerMode': false,
  'thermalState': 0,
};

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  final ios = TargetPlatformVariant.only(TargetPlatform.iOS);
  late Map<String, Object?> native;
  late List<MethodCall> calls;

  String en(String key) => ExternalDisplayLocale.values['en']![key]!;

  // Row order on iOS: scan 0, hidden files 1, sounds 2, ambient music 3 and
  // its volume 4 (Build 448, which moved the rows below by two), clock 5,
  // 120 Hz 6, then the two external display rows. Retired with Build 449:
  // the third row, "Show the menu on the TV" (index 9): outside a game the
  // TV mirrors the iPhone, and "Use built-in emulators" follows the format.
  const enabledIndex = 7;
  const modeIndex = 8;
  const builtInEnginesIndex = 9;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  Future<Object?> handle(MethodCall call) async {
    calls.add(call);
    final arguments = call.arguments is Map
        ? (call.arguments as Map).cast<String, Object?>()
        : const <String, Object?>{};
    switch (call.method) {
      case 'setEnabled':
        native = <String, Object?>{...native, 'enabled': arguments['enabled']};
      case 'setMode':
        native = <String, Object?>{...native, 'mode': arguments['mode']};
    }
    return native;
  }

  setUp(() {
    native = externalState();
    calls = <MethodCall>[];
    final messenger = binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(ExternalDisplayChannel.channel, handle);
    // The 120 Hz row above is built on iOS too.
    messenger.setMockMethodCallHandler(
      UiRefreshRateChannel.channel,
      (call) async => refreshRateState(),
    );
    // Desktop test hosts build the fullscreen row; answer its channels.
    for (final name in <String>['fullscreen_window', 'window_manager']) {
      messenger.setMockMethodCallHandler(MethodChannel(name), (call) async {
        return null;
      });
    }
  });

  tearDown(() {
    final messenger = binding.defaultBinaryMessenger;
    for (final name in <String>[
      'neostation/external_display',
      'neostation/ui_refresh_rate',
      'fullscreen_window',
      'window_manager',
    ]) {
      messenger.setMockMethodCallHandler(MethodChannel(name), null);
    }
  });

  Future<GeneralSettingsContentState> pumpGeneral(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1920, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final key = GlobalKey<GeneralSettingsContentState>();
    await tester.pumpWidget(
      ChangeNotifierProvider<SqliteConfigProvider>(
        create: (_) => SqliteConfigProvider(),
        child: MediaQuery(
          data: const MediaQueryData(size: Size(1920, 4000)),
          child: ScreenUtilInit(
            designSize: const Size(1920, 1080),
            builder: (context, child) => MaterialApp(
              localizationsDelegates:
                  FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: Scaffold(
                body: GeneralSettingsContent(
                  key: key,
                  isContentFocused: true,
                  selectedContentIndex: 0,
                  onFullscreenToggle: (_) {},
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return key.currentState!;
  }

  CustomToggleSwitch enabledToggle(WidgetTester tester) =>
      tester.widget<CustomToggleSwitch>(
        find.byKey(ExternalDisplayEnabledRow.toggleKey),
      );

  String chipText(WidgetTester tester) => tester
      .widget<SettingValueChip>(
        find.descendant(
          of: find.byKey(ExternalDisplayModeRow.chipKey),
          matching: find.byType(SettingValueChip),
        ),
      )
      .text;

  double top(WidgetTester tester, String text) =>
      tester.getTopLeft(find.text(text)).dy;

  List<Object?> modeArguments() => calls
      .where((c) => c.method == 'setMode')
      .map((c) => (c.arguments as Map)['mode'])
      .toList();

  testWidgets('iOS shows two rows after 120 Hz and the gamepad reaches them', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final withoutRows = (await pumpGeneral(tester)).getItemCount();
    expect(find.byType(ExternalDisplayEnabledRow), findsNothing);
    expect(find.byType(ExternalDisplayModeRow), findsNothing);
    expect(calls, isEmpty);

    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    await tester.pumpWidget(const SizedBox.shrink());
    final general = await pumpGeneral(tester);
    // +1 for 120 Hz, +2 for the external display, +1 for "Use built-in
    // emulators" (iOS only, Build 448). Retired contract (Build 447/448):
    // +3 with a "Show the menu on the TV" switch, which put the second
    // engine's TV view (the selected console's logo) on the TV instead of
    // the interface; since Build 449 the TV mirrors the iPhone outside a
    // game, and no row offers that view any more.
    expect(general.getItemCount(), withoutRows + 4);
    expect(find.byType(ExternalDisplayEnabledRow), findsOneWidget);
    expect(find.byType(ExternalDisplayModeRow), findsOneWidget);
    expect(find.byKey(const Key('externalDisplay.menu')), findsNothing,
        reason: 'no "menu on the TV" switch any more');
    expect(find.text(en(ExternalDisplayLocale.title)), findsOneWidget);
    expect(find.text(en(ExternalDisplayLocale.description)), findsOneWidget);
    expect(find.text(en(ExternalDisplayLocale.modeTitle)), findsOneWidget);
    expect(find.text(en(ExternalDisplayLocale.noExternalScreen)), findsOneWidget);
    expect(
      find.text(en(ExternalDisplayLocale.modeAutomaticHelp)),
      findsOneWidget,
    );
    expect(chipText(tester), en(ExternalDisplayLocale.modeAutomatic));
    expect(enabledToggle(tester).value, isTrue);
    expect(enabledToggle(tester).disabled, isFalse);
    // The two rows share one native read.
    expect(calls.where((c) => c.method == 'getState'), hasLength(1));

    // Order: 120 Hz, then switch, format, then "Use built-in emulators".
    final refresh = top(tester, UiRefreshRateLocale.values['en']![
        UiRefreshRateLocale.title]!);
    final enabled = top(tester, en(ExternalDisplayLocale.title));
    final mode = top(tester, en(ExternalDisplayLocale.modeTitle));
    final builtIn = top(tester, ConsoleManagerLocale.values['en']![
        ConsoleManagerLocale.useEmbeddedTitle]!);
    expect(enabled, greaterThan(refresh));
    expect(mode, greaterThan(enabled));
    expect(builtIn, greaterThan(mode),
        reason: 'the row after the format is "Use built-in emulators" (index $builtInEnginesIndex)');
    expect(find.byType(UiRefreshRateSettingRow), findsOneWidget);

    // Gamepad A on each row: switch, format cycle.
    general.selectItem(enabledIndex);
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.method == 'setEnabled').single.arguments, {
      'enabled': false,
    });
    expect(enabledToggle(tester).value, isFalse);
    expect(find.text(en(ExternalDisplayLocale.mirroringOff)), findsOneWidget);
    expect(find.text(en(ExternalDisplayLocale.noExternalScreen)), findsNothing);

    general.selectItem(enabledIndex);
    await tester.pumpAndSettle();
    expect(enabledToggle(tester).value, isTrue);
    expect(find.text(en(ExternalDisplayLocale.noExternalScreen)), findsOneWidget);

    general.selectItem(modeIndex);
    await tester.pumpAndSettle();
    expect(modeArguments(), <Object?>[1]);
    expect(chipText(tester), en(ExternalDisplayLocale.modeFit));
    expect(find.text(en(ExternalDisplayLocale.modeFitHelp)), findsOneWidget);
    // Nothing in Settings writes the retired preference any more.
    expect(calls.where((c) => c.method == 'setMenuOnTV'), isEmpty);

    // pumpAndSettle completed: the rows add no perpetual animation.
    expect(tester.binding.hasScheduledFrame, isFalse);
    // Leave the singleton as found for the next test.
    general.selectItem(modeIndex);
    await tester.pumpAndSettle();
    general.selectItem(modeIndex);
    await tester.pumpAndSettle();
    general.selectItem(modeIndex);
    await tester.pumpAndSettle();
    expect(chipText(tester), en(ExternalDisplayLocale.modeAutomatic));
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('the chip cycles the four formats and Fill announces the crop', (
    tester,
  ) async {
    await pumpGeneral(tester);
    final chip = find.byKey(ExternalDisplayModeRow.chipKey);
    expect(chipText(tester), en(ExternalDisplayLocale.modeAutomatic));
    expect(find.text(en(ExternalDisplayLocale.fillCrops)), findsNothing);

    await tester.tap(chip);
    await tester.pumpAndSettle();
    expect(chipText(tester), en(ExternalDisplayLocale.modeFit));
    expect(find.text(en(ExternalDisplayLocale.modeFitHelp)), findsOneWidget);
    expect(find.text(en(ExternalDisplayLocale.fillCrops)), findsNothing);

    await tester.tap(chip);
    await tester.pumpAndSettle();
    expect(chipText(tester), en(ExternalDisplayLocale.modeFill));
    expect(find.text(en(ExternalDisplayLocale.modeFillHelp)), findsOneWidget);
    expect(find.text(en(ExternalDisplayLocale.fillCrops)), findsOneWidget);

    await tester.tap(chip);
    await tester.pumpAndSettle();
    expect(chipText(tester), en(ExternalDisplayLocale.modeOriginal));
    expect(
      find.text(en(ExternalDisplayLocale.modeOriginalHelp)),
      findsOneWidget,
    );
    expect(find.text(en(ExternalDisplayLocale.fillCrops)), findsNothing);

    await tester.tap(chip);
    await tester.pumpAndSettle();
    expect(chipText(tester), en(ExternalDisplayLocale.modeAutomatic));
    expect(modeArguments(), <Object?>[1, 2, 3, 0]);
    expect(native['mode'], 0);
  }, variant: ios);

  testWidgets('the state of the external screen is described', (tester) async {
    // Outside a game (Build 449) the TV mirrors the iPhone: the connected
    // screen, then what it shows. Retired contract (Build 447/448): a
    // connected TV outside a game showed the second engine's menu with the
    // size line alone, and a separate line said "Menu on the TV off".
    native = externalState(
      connected: true,
      content: 'none',
      mirroringActive: true,
      screenWidth: 1920,
      screenHeight: 1080,
    );
    final general = await pumpGeneral(tester);
    expect(find.text('External screen: 1920×1080'), findsOneWidget);
    expect(
      find.text(en(ExternalDisplayLocale.mirroringOutsideGames)),
      findsOneWidget,
    );
    final size = top(tester, 'External screen: 1920×1080');
    expect(
      top(tester, en(ExternalDisplayLocale.mirroringOutsideGames)),
      greaterThan(size),
      reason: 'the screen first, then what it shows',
    );

    native = externalState(
      connected: true,
      content: 'game',
      screenWidth: 1920,
      screenHeight: 1080,
    );
    await ExternalDisplayService.instance.refresh();
    await tester.pumpAndSettle();
    expect(find.text(en(ExternalDisplayLocale.gameOnExternal)), findsOneWidget);
    expect(find.text('External screen: 1920×1080'), findsNothing);
    expect(
      find.text(en(ExternalDisplayLocale.mirroringOutsideGames)),
      findsNothing,
    );

    // The unsupported-engine line needs the native suspension (Dusklight,
    // KartPad; review of 12 October 2026, m2).
    native = externalState(
      connected: true,
      content: 'none',
      suspended: true,
      mirroringActive: true,
      screenWidth: 1920,
      screenHeight: 1080,
    );
    await ExternalDisplayService.instance.refresh();
    await tester.pumpAndSettle();
    expect(
      find.text(en(ExternalDisplayLocale.unsupportedEngine)),
      findsOneWidget,
    );
    expect(find.text('External screen: 1920×1080'), findsNothing);
    expect(
      find.text(en(ExternalDisplayLocale.mirroringOutsideGames)),
      findsNothing,
    );

    // A state from an older native host that still reports the menu on the
    // TV is described the same way: mirroring outside a game.
    native = externalState(
      connected: true,
      content: 'none',
      menuOnTV: true,
      screenWidth: 1920,
      screenHeight: 1080,
    );
    await ExternalDisplayService.instance.refresh();
    await tester.pumpAndSettle();
    expect(find.text('External screen: 1920×1080'), findsOneWidget);
    expect(
      find.text(en(ExternalDisplayLocale.mirroringOutsideGames)),
      findsOneWidget,
    );
    expect(find.text(en(ExternalDisplayLocale.unsupportedEngine)), findsNothing);

    native = externalState(enabled: false, connected: true, content: 'none');
    await ExternalDisplayService.instance.refresh();
    await tester.pumpAndSettle();
    expect(find.text(en(ExternalDisplayLocale.mirroringOff)), findsOneWidget);
    expect(
      find.text(en(ExternalDisplayLocale.mirroringOutsideGames)),
      findsNothing,
    );
    expect(enabledToggle(tester).value, isFalse);

    // Without the plugin: unavailable, raw code, nothing written.
    native = externalState(supported: false, accessoryStatus: 'pluginMissing');
    await ExternalDisplayService.instance.refresh();
    await tester.pumpAndSettle();
    expect(find.text(en(ExternalDisplayLocale.unavailable)), findsOneWidget);
    expect(find.text('Technical code: pluginMissing'), findsOneWidget);
    expect(enabledToggle(tester).disabled, isTrue);
    expect(enabledToggle(tester).value, isFalse);
    general.selectItem(enabledIndex);
    general.selectItem(modeIndex);
    await tester.tap(find.byKey(ExternalDisplayModeRow.chipKey));
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.method != 'getState'), isEmpty);
  }, variant: ios);

  testWidgets('a refused save is shown as an error, never as saved', (
    tester,
  ) async {
    final general = await pumpGeneral(tester);
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      (call) async {
        if (call.method == 'setMode') {
          throw PlatformException(code: 'SAVE_FAILED');
        }
        return native;
      },
    );
    await tester.tap(find.byKey(ExternalDisplayModeRow.chipKey));
    await tester.pumpAndSettle();
    expect(find.text(en(ExternalDisplayLocale.saveFailed)), findsOneWidget);
    expect(find.text('Technical code: SAVE_FAILED'), findsOneWidget);
    // The native value stays: Automatic, no crop warning.
    expect(chipText(tester), en(ExternalDisplayLocale.modeAutomatic));
    expect(find.text(en(ExternalDisplayLocale.fillCrops)), findsNothing);
    expect(native['mode'], 0);
    // The error belongs to the format row only (retired check: above the
    // "menu on the TV" row, removed with Build 449).
    expect(
      find.descendant(
        of: find.byType(ExternalDisplayModeRow),
        matching: find.text(en(ExternalDisplayLocale.saveFailed)),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byType(ExternalDisplayEnabledRow),
        matching: find.text(en(ExternalDisplayLocale.saveFailed)),
      ),
      findsNothing,
    );

    // The next accepted write clears the error.
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      handle,
    );
    general.selectItem(modeIndex);
    await tester.pumpAndSettle();
    expect(find.text(en(ExternalDisplayLocale.saveFailed)), findsNothing);
    expect(chipText(tester), en(ExternalDisplayLocale.modeFit));
    // Leave the singleton as found.
    for (var step = 0; step < 3; step++) {
      general.selectItem(modeIndex);
      await tester.pumpAndSettle();
    }
    expect(chipText(tester), en(ExternalDisplayLocale.modeAutomatic));
  }, variant: ios);
}
