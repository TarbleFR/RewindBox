import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/enhancements_locale.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/screens/enhancements/enhancements_screen.dart';
import 'package:neostation/services/enhancements/adapters/rpcs3_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:path/path.dart' as path;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'enhancement_test_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  String en(String key) => EnhancementsLocale.forLocale(const Locale('en'), key);

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    SfxService().setEnabled(false);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (call) async => <dynamic>[],
    );
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });
  tearDownAll(() => SfxService().setEnabled(true));

  testWidgets('a PS3 game lists its categories and switches a cheat in one tap', (tester) async {
    final temp = Directory.systemTemp.createTempSync('enh-screen-');
    addTearDown(() => temp.deleteSync(recursive: true));
    final data = Directory(path.join(temp.path, 'Data'))..createSync();
    final service = EnhancementService(
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [Rpcs3EnhancementAdapter(dataDirectory: () async => data, installedVersion: (_) async => '01.00')],
      texturesSupported: (_) => false,
    );
    await tester.binding.setSurfaceSize(const Size(956, 440));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    Future<void> settle(bool Function() done) async {
      for (var i = 0; i < 100 && !done(); i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
        await tester.pump();
      }
    }

    await tester.pumpWidget(
      ChangeNotifierProvider<ThemeProvider>.value(
        value: ThemeProvider.testing(),
        child: ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, _) => Consumer<ThemeProvider>(
            builder: (context, theme, _) => MaterialApp(
              theme: theme.currentTheme,
              localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: EnhancementsScreen(
                game: testGame(name: "Demon's Souls", romPath: '/rpcs3/BLUS30443', titleId: 'BLUS30443'),
                system: const SystemModel(folderName: 'ps3', realName: 'PlayStation 3', iconImage: '', color: ''),
                systemFolder: 'ps3',
                service: service,
              ),
            ),
          ),
        ),
      ),
    );
    final toggle = find.byWidgetPredicate(
      (widget) =>
          widget.key is ValueKey<String> && (widget.key! as ValueKey<String>).value.startsWith('enhancements-toggle-'),
    );
    await settle(() => toggle.evaluate().isNotEmpty);
    expect(toggle, findsWidgets);
    expect(find.textContaining(en(EnhancementsLocale.catCheat)), findsWidgets);
    expect(find.textContaining(en(EnhancementsLocale.catGraphics)), findsWidgets);
    expect(find.text(en(EnhancementsLocale.restartNote)), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(toggle.first);
    final staged = File(path.join(data.path, 'NeoStationUnifiedCheats', 'state.json'));
    await settle(() => find.byKey(const ValueKey('enhancements-active-count')).evaluate().isNotEmpty);
    expect(find.byKey(const ValueKey('enhancements-active-count')), findsOneWidget);
    expect(staged.readAsStringSync(), contains('"enabled":true'));
    final restore = find.text(en(EnhancementsLocale.restore));
    await tester.scrollUntilVisible(
      restore,
      300,
      scrollable: find.descendant(of: find.byType(ListView), matching: find.byType(Scrollable)).first,
    );
    expect(restore, findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
