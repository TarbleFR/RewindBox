import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/screens/libretro/libretro_bios_checker_screen.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/tools_settings_content.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/settings_card_row.dart';
import 'package:neostation/screens/storage/storage_audit_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Test I of docs/storage-audit-cleanup.md § 6 (§ 3.10): Settings › Tools
/// gains a fifth row on iOS, « Analyse et nettoyage du stockage », after the
/// BIOS checker (index 4, storage icon, its own row key), selected by the
/// controller at index 4 and opening the analysis page; other platforms keep
/// their three tools.
const _gamepads = MethodChannel('xyz.luan/gamepads');
const _paths = MethodChannel('plugins.flutter.io/path_provider');
const _bridge = MethodChannel('neostation/libretro_internal');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final english = StorageLocale.values['en']!;
  late Directory root;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = Directory.systemTemp.createTempSync('storage_tools_row_');
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(_paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(
      _bridge,
      (call) async => call.method == 'availableCores' ? <String>[] : null,
    );
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(_gamepads, null);
    messenger.setMockMethodCallHandler(_paths, null);
    messenger.setMockMethodCallHandler(_bridge, null);
    root.deleteSync(recursive: true);
  });

  Future<GlobalKey<ToolsSettingsContentState>> pumpTools(
    WidgetTester tester, {
    int selected = 4,
    bool focused = true,
  }) async {
    final key = GlobalKey<ToolsSettingsContentState>();
    tester.view.physicalSize = const Size(1600, 2400);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(800, 1200),
        builder: (context, child) => MaterialApp(
          locale: const Locale('en'),
          localizationsDelegates:
              FlutterLocalization.instance.localizationsDelegates,
          supportedLocales: FlutterLocalization.instance.supportedLocales,
          home: Scaffold(
            body: ToolsSettingsContent(
              key: key,
              isContentFocused: focused,
              selectedContentIndex: selected,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    return key;
  }

  List<SettingsCardRow> rows(WidgetTester tester) =>
      tester.widgetList<SettingsCardRow>(find.byType(SettingsCardRow)).toList();

  testWidgets('iOS: the storage analysis is the fifth tool, after the BIOS '
      'checker', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final key = await pumpTools(tester);
    expect(key.currentState!.getItemCount(), 5);

    final all = rows(tester);
    expect(all, hasLength(5));
    final storage = all[4];
    expect(storage.icon, Symbols.storage_rounded);
    expect(storage.title, english[StorageLocale.toolTitle]);
    expect(storage.subtitle, english[StorageLocale.toolSubtitle]);
    expect(storage.subtitleMaxLines, 4);
    expect(storage.selected, isTrue, reason: 'the controller is on index 4');
    expect(storage.trailing, isA<Icon>());
    expect((storage.trailing! as Icon).icon, Icons.chevron_right);
    expect(storage.key, isA<GlobalKey>(), reason: 'its own row key');
    expect(
      {for (final row in all) row.key}.length,
      5,
      reason: 'five distinct row keys',
    );
    // The BIOS checker stays fourth and is no longer selected.
    expect(all[3].icon, Symbols.fact_check_rounded);
    expect(all[3].selected, isFalse);
    expect(find.text(english[StorageLocale.toolTitle]!), findsOneWidget);
    expect(find.text(english[StorageLocale.toolSubtitle]!), findsOneWidget);

    // The controller keeps the fifth row on screen.
    key.currentState!.scrollToIndex(4);
    await tester.pump(const Duration(milliseconds: 200));
    expect(tester.takeException(), isNull);
    // Reset before the binding checks its debug variables.
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('iOS: index 4 and a tap open the storage analysis', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final key = await pumpTools(tester, selected: 0);
    expect(rows(tester)[4].selected, isFalse);

    key.currentState!.selectItem(4);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(StorageAuditScreen), findsOneWidget);
    expect(find.byType(LibretroBiosCheckerScreen), findsNothing);

    // Without the settings provider the page refuses to analyse (library
    // folders unknown) and stays idle: the transitions can settle.
    expect(
      find.textContaining('SqliteConfigProvider unavailable'),
      findsOneWidget,
    );
    Navigator.of(tester.element(find.byType(StorageAuditScreen))).pop();
    await tester.pumpAndSettle();
    expect(find.byType(StorageAuditScreen), findsNothing);

    await tester.tap(find.text(english[StorageLocale.toolTitle]!));
    await tester.pumpAndSettle();
    expect(find.byType(StorageAuditScreen), findsOneWidget);
    // Reset before the binding checks its debug variables.
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('iOS: index 3 still opens the BIOS checker', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final key = await pumpTools(tester, selected: 3);
    expect(rows(tester)[3].selected, isTrue);
    expect(rows(tester)[4].selected, isFalse);
    key.currentState!.selectItem(3);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(LibretroBiosCheckerScreen), findsOneWidget);
    expect(find.byType(StorageAuditScreen), findsNothing);
    // Reset before the binding checks its debug variables.
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('other platforms keep three tools and no storage row', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final key = await pumpTools(tester);
    expect(key.currentState!.getItemCount(), 3);
    expect(rows(tester), hasLength(3));
    expect(find.text(english[StorageLocale.toolTitle]!), findsNothing);
    expect(find.byIcon(Symbols.storage_rounded), findsNothing);

    key.currentState!.selectItem(4);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(StorageAuditScreen), findsNothing);
    // Reset before the binding checks its debug variables.
    debugDefaultTargetPlatformOverride = null;
  });
}
