import 'dart:ui' show FrameTiming, SemanticsAction;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/ui_refresh_rate_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/general_settings_content.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/ui_refresh_rate_setting_row.dart';
import 'package:neostation/services/ui_refresh_rate_service.dart';
import 'package:neostation/widgets/custom_toggle_switch.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:ui_refresh_rate/ui_refresh_rate.dart';

Map<String, Object?> nativeState({
  String hookStatus = 'installed',
  bool storedEnabled = true,
  bool activeEnabled = true,
  int screenMaxHz = 120,
  bool lowPowerMode = false,
  int thermalState = 0,
}) => <String, Object?>{
  'hookStatus': hookStatus,
  'storedEnabled': storedEnabled,
  'activeEnabled': activeEnabled,
  'screenMaxHz': screenMaxHz,
  'engineTargetHz': activeEnabled ? screenMaxHz.toDouble() : 60.0,
  'cappedHz': 60.0,
  'lowPowerMode': lowPowerMode,
  'thermalState': thermalState,
};

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  final ios = TargetPlatformVariant.only(TargetPlatform.iOS);
  late Map<String, Object?> native;
  late List<MethodCall> calls;

  String en(String key) => UiRefreshRateLocale.values['en']![key]!;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  setUp(() {
    native = nativeState();
    calls = <MethodCall>[];
    final messenger = binding.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(UiRefreshRateChannel.channel, (
      call,
    ) async {
      calls.add(call);
      if (call.method == 'setEnabled') {
        native = <String, Object?>{
          ...native,
          'storedEnabled': (call.arguments as Map)['enabled'] as bool,
        };
      }
      return native;
    });
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

  Future<void> pumpRow(
    WidgetTester tester,
    UiRefreshRateService service,
  ) async {
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(1920, 1080)),
        child: ScreenUtilInit(
          designSize: const Size(1920, 1080),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: UiRefreshRateSettingRow(focused: false, service: service),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  CustomToggleSwitch toggle(WidgetTester tester) =>
      tester.widget<CustomToggleSwitch>(
        find.byKey(UiRefreshRateSettingRow.toggleKey),
      );

  testWidgets('iOS shows the row after the clock and navigation reaches it', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final withoutRow = (await pumpGeneral(tester)).getItemCount();
    expect(find.byType(UiRefreshRateSettingRow), findsNothing);

    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    await tester.pumpWidget(const SizedBox.shrink());
    final general = await pumpGeneral(tester);
    // +1 for this row; +3 for the external display rows that share the iOS
    // condition since Build 447 (test/general_settings_external_display_test.dart).
    expect(general.getItemCount(), withoutRow + 1 + 3);
    expect(find.byType(UiRefreshRateSettingRow), findsOneWidget);
    expect(find.text(en(UiRefreshRateLocale.title)), findsOneWidget);
    expect(find.text(en(UiRefreshRateLocale.description)), findsOneWidget);
    // Nothing is claimed before a measurement.
    expect(find.text(en(UiRefreshRateLocale.notMeasured)), findsOneWidget);
    expect(find.textContaining('120 Hz'), findsOneWidget); // the title only
    expect(toggle(tester).value, isTrue);
    expect(toggle(tester).disabled, isFalse);

    // Row order: scan, hidden files, sounds, clock, then 120 Hz (index 4).
    final clock = tester.getTopLeft(
      find.text(AppLocale.en[AppLocale.use12HourClock] as String),
    );
    final row = tester.getTopLeft(find.text(en(UiRefreshRateLocale.title)));
    expect(row.dy, greaterThan(clock.dy));

    // Gamepad A on the row stores the opposite choice for the next launch.
    general.selectItem(4);
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.method == 'setEnabled').single.arguments, {
      'enabled': false,
    });
    expect(toggle(tester).value, isFalse);
    expect(find.text(en(UiRefreshRateLocale.restartRequired)), findsOneWidget);

    general.selectItem(4);
    await tester.pumpAndSettle();
    expect(toggle(tester).value, isTrue);
    expect(find.text(en(UiRefreshRateLocale.restartRequired)), findsNothing);
    // pumpAndSettle completed: the row adds no perpetual animation.
    expect(tester.binding.hasScheduledFrame, isFalse);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('a 60 Hz screen disables the switch and says why', (
    tester,
  ) async {
    native = nativeState(screenMaxHz: 60);
    final general = await pumpGeneral(tester);
    expect(toggle(tester).disabled, isTrue);
    expect(toggle(tester).value, isFalse);
    expect(
      find.text('Not available on this screen (maximum 60 Hz).'),
      findsOneWidget,
    );
    general.selectItem(4);
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.method == 'setEnabled'), isEmpty);
  }, variant: ios);

  testWidgets('a missing engine seam is unavailable with its raw code', (
    tester,
  ) async {
    native = nativeState(hookStatus: 'methodMissing');
    await pumpGeneral(tester);
    expect(toggle(tester).disabled, isTrue);
    expect(
      find.text(en(UiRefreshRateLocale.unavailableEngine)),
      findsOneWidget,
    );
    expect(find.text('Technical code: methodMissing'), findsOneWidget);
  }, variant: ios);

  testWidgets('Low Power Mode and heat are reported as system limits', (
    tester,
  ) async {
    native = nativeState(lowPowerMode: true);
    await pumpGeneral(tester);
    expect(find.text(en(UiRefreshRateLocale.limitedLowPower)), findsOneWidget);
    expect(toggle(tester).disabled, isFalse);

    native = nativeState(thermalState: 3);
    await UiRefreshRateService.instance.refresh();
    await tester.pumpAndSettle();
    expect(find.text(en(UiRefreshRateLocale.limitedThermal)), findsOneWidget);
    expect(find.text(en(UiRefreshRateLocale.limitedLowPower)), findsNothing);
  }, variant: ios);

  testWidgets('a refused save is shown as an error, never as saved', (
    tester,
  ) async {
    final general = await pumpGeneral(tester);
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      UiRefreshRateChannel.channel,
      (call) async {
        if (call.method == 'setEnabled') {
          throw PlatformException(code: 'SAVE_FAILED');
        }
        return native;
      },
    );
    general.selectItem(4);
    await tester.pumpAndSettle();
    expect(find.text(en(UiRefreshRateLocale.saveFailed)), findsOneWidget);
    expect(find.text('Technical code: SAVE_FAILED'), findsOneWidget);
    expect(toggle(tester).value, isTrue);
    expect(find.text(en(UiRefreshRateLocale.restartRequired)), findsNothing);
  }, variant: ios);

  testWidgets(
    'Measure runs one bounded animation, then shows only a measured rate',
    (tester) async {
      final service = UiRefreshRateService.forTesting(
        reportWait: const Duration(milliseconds: 100),
      );
      addTearDown(service.dispose);
      await pumpRow(tester, service);
      service.startProbe();
      await tester.pumpAndSettle();
      expect(find.text(en(UiRefreshRateLocale.notMeasured)), findsOneWidget);

      await tester.tap(find.byKey(UiRefreshRateSettingRow.measureKey));
      await tester.pump();
      expect(find.text(en(UiRefreshRateLocale.measuring)), findsOneWidget);
      expect(find.byKey(UiRefreshRateSettingRow.progressKey), findsOneWidget);
      expect(tester.hasRunningAnimations, isTrue);

      // The engine reports the animation frames (here: a 120 Hz cadence).
      binding.platformDispatcher.onReportTimings!(<FrameTiming>[
        for (var index = 0; index < 180; index++)
          FrameTiming(
            vsyncStart: 1000000 + index * 8333,
            buildStart: 1000000 + index * 8333 + 100,
            buildFinish: 1000000 + index * 8333 + 900,
            rasterStart: 1000000 + index * 8333 + 1000,
            rasterFinish: 1000000 + index * 8333 + 3000,
            rasterFinishWallTime: 1000000 + index * 8333 + 3000,
          ),
      ]);

      // Bounded: 1.5 s of animation, then the report wait, then idle.
      await tester.pump(UiRefreshRateService.measureDuration);
      await tester.pump(const Duration(milliseconds: 17)); // one more vsync
      expect(tester.hasRunningAnimations, isFalse);
      expect(service.measuring, isTrue, reason: 'waiting for the report');
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      expect(service.measuring, isFalse);
      expect(find.text('Measured rate: 120 Hz'), findsOneWidget);
      expect(find.byKey(UiRefreshRateSettingRow.progressKey), findsNothing);
      expect(tester.binding.hasScheduledFrame, isFalse);
    },
    variant: ios,
  );

  testWidgets('a measurement without frames says so', (tester) async {
    final service = UiRefreshRateService.forTesting(
      reportWait: const Duration(milliseconds: 50),
    );
    addTearDown(service.dispose);
    await pumpRow(tester, service);
    await tester.tap(find.byKey(UiRefreshRateSettingRow.measureKey));
    await tester.pump();
    await tester.pump(UiRefreshRateService.measureDuration);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();
    expect(find.text(en(UiRefreshRateLocale.measureFailed)), findsOneWidget);
    expect(find.textContaining('Measured rate'), findsNothing);
  }, variant: ios);

  testWidgets('VoiceOver can start a measurement from its translated label', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final service = UiRefreshRateService.forTesting(
      reportWait: const Duration(milliseconds: 50),
    );
    addTearDown(service.dispose);
    await pumpRow(tester, service);

    final node = tester.getSemantics(
      find.bySemanticsLabel(en(UiRefreshRateLocale.measureHint)),
    );
    expect(node.getSemanticsData().hasAction(SemanticsAction.tap), isTrue);
    tester.semantics.tap(
      find.semantics.byLabel(en(UiRefreshRateLocale.measureHint)),
    );
    await tester.pump();
    expect(service.measuring, isTrue);

    await tester.pump(UiRefreshRateService.measureDuration);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();
    expect(service.measuring, isFalse);
    semantics.dispose();
  }, variant: ios);

  testWidgets('leaving the page during a measurement cancels it cleanly', (
    tester,
  ) async {
    final service = UiRefreshRateService.forTesting(
      reportWait: const Duration(milliseconds: 50),
    );
    addTearDown(service.dispose);
    await pumpRow(tester, service);
    await tester.tap(find.byKey(UiRefreshRateSettingRow.measureKey));
    await tester.pump();
    expect(service.measuring, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    expect(service.measuring, isFalse);
    expect(tester.takeException(), isNull);
  }, variant: ios);
}
