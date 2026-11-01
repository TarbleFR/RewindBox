import 'dart:async';

import 'package:flutter/cupertino.dart' show CupertinoLocalizations;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/app_widget_localizations.dart'
    show appWidgetLocalizationsDelegates;
import 'package:neostation/main.dart' show FallbackMaterialLocalizationsDelegate;
import 'package:neostation/providers/retro_achievements_provider.dart';
import 'package:neostation/screens/retro_achievements_screen/ra_content.dart';
import 'package:neostation/screens/retro_achievements_screen/ra_session_settings.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/ra_dashboard_fixture.dart';

const _catalogs = <String, Map<String, dynamic>>{
  'en': AppLocale.en, 'es': AppLocale.es, 'ru': AppLocale.ru,
  'zh': AppLocale.zh, 'zh_Hant': AppLocale.zhHant, 'pt': AppLocale.pt,
  'fr': AppLocale.fr, 'de': AppLocale.de, 'it': AppLocale.it,
  'id': AppLocale.id, 'ja': AppLocale.ja, 'ko': AppLocale.ko,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final localization = FlutterLocalization.instance;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'),
          (_) async => <dynamic>[]);
    await localization.ensureInitialized();
  });

  tearDownAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), null);
  });

  test('the actual application catalogs contain all central RA labels in exactly 12 languages', () {
    expect(AppLocale.supportedLanguages.keys.toSet(),
      {'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'});
    expect(_catalogs.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    final keys = AppLocale.en.keys.where((key) => key.startsWith('ra_session_')).toSet();
    expect(keys, containsAll([AppLocale.raSessionSettings, AppLocale.raSessionHardcoreHelp,
      AppLocale.raSessionPending, AppLocale.raSessionDifferentAccount,
      AppLocale.raSessionMigrationChoice, AppLocale.raSessionNotifications]));
    for (final locale in _catalogs.entries) {
      for (final key in keys) {
        expect(locale.value[key], isA<String>(), reason: '${locale.key}:$key');
        expect((locale.value[key] as String).trim(), isNotEmpty, reason: '${locale.key}:$key');
        expect(locale.value[key], isNot(key), reason: '${locale.key}:$key');
      }
      if (locale.key != 'en') {
        expect(locale.value[AppLocale.raSessionAccountHelp],
          isNot(AppLocale.en[AppLocale.raSessionAccountHelp]), reason: locale.key);
      }
    }
    expect(AppLocale.zhHant[AppLocale.raSessionAccountHelp], isNot(AppLocale.zh[AppLocale.raSessionAccountHelp]));
    expect(AppLocale.zhHant[AppLocale.raSessionAccountHelp], contains('內建'));
    expect(AppLocale.zh[AppLocale.raSessionAccountHelp], contains('内置'));
    expect(AppLocale.fr[AppLocale.raSessionAccountHelp], contains('mot de passe'));
  });

  Future<void> pumpRA(WidgetTester tester, RetroAchievementsProvider provider,
      String language, {Widget? home, TextDirection? direction}) async {
    tester.view.physicalSize = const Size(667, 375);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    localization.init(mapLocales: [for (final entry in _catalogs.entries)
      MapLocale(entry.key, entry.value)], initLanguageCode: language);
    localization.translate(language);
    await tester.pumpWidget(ScreenUtilInit(designSize: const Size(1920, 1080),
      builder: (_, _) => ChangeNotifierProvider.value(value: provider,
        child: MaterialApp(locale: Locale(language),
          supportedLocales: localization.supportedLocales,
          localizationsDelegates: [
            ...localization.localizationsDelegates,
            ...appWidgetLocalizationsDelegates],
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(1.4)),
            child: direction == null ? child! : Directionality(textDirection: direction, child: child!)),
          home: Scaffold(body: home ?? const RAContent())))));
    await tester.pumpAndSettle();
  }

  Finder dialogText(String text) => find.descendant(
    of: find.byType(AlertDialog), matching: find.text(text));

  for (final code in _catalogs.keys) {
    testWidgets('$code: main RA tab, password, Hardcore, pending and errors render using the real catalog', (tester) async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      await pumpRA(tester, provider, code);
      final catalog = _catalogs[code]!;
      String text(String key) => catalog[key] as String;
      expect(find.byKey(const ValueKey('ra-central-settings')), findsOneWidget);
      expect(find.text(text(AppLocale.raSessionSettings)), findsOneWidget);
      expect(find.text(text(AppLocale.raSessionWeb)), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('ra-central-settings')));
      await tester.pumpAndSettle();
      expect(dialogText(text(AppLocale.raSessionSettings)), findsOneWidget);
      expect(dialogText(text(AppLocale.raSessionAccountHelp)), findsOneWidget);
      expect(dialogText(text(AppLocale.raSessionNotifications)), findsOneWidget);
      final password = tester.widget<TextField>(find.byKey(const ValueKey('ra-native-password')));
      expect(password.decoration!.labelText, text(AppLocale.password));
      expect(password.obscureText, isTrue);
      expect(password.enableSuggestions, isFalse);
      expect(password.autocorrect, isFalse);

      // Keep the real catalog/manager key while verifying that standard
      // widgets use Flutter's own translations for the requested language.
      final fieldContext = tester.element(find.byKey(const ValueKey('ra-native-password')));
      expect(Localizations.localeOf(fieldContext).languageCode, code);
      expect(localization.currentLocale!.languageCode, code);
      final frameworkLocale = code == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(code);
      final expectedMaterial = await GlobalMaterialLocalizations.delegate.load(frameworkLocale);
      final expectedCupertino = await GlobalCupertinoLocalizations.delegate.load(frameworkLocale);
      final expectedWidgets = await GlobalWidgetsLocalizations.delegate.load(frameworkLocale);
      expect(MaterialLocalizations.of(fieldContext).runtimeType, expectedMaterial.runtimeType);
      expect(MaterialLocalizations.of(fieldContext).pasteButtonLabel, expectedMaterial.pasteButtonLabel);
      expect(CupertinoLocalizations.of(fieldContext).runtimeType, expectedCupertino.runtimeType);
      expect(CupertinoLocalizations.of(fieldContext).pasteButtonLabel, expectedCupertino.pasteButtonLabel);
      expect(WidgetsLocalizations.of(fieldContext).runtimeType, expectedWidgets.runtimeType);
      // The historical public class imported from main.dart must remain usable.
      final compatibility = await const FallbackMaterialLocalizationsDelegate().load(Locale(code));
      expect(compatibility.runtimeType, expectedMaterial.runtimeType);
      expect(tester.takeException(), isNull);

      // Exercise the real UI -> central service -> native error mapping.
      native.loginError = 'RA_AUTHENTICATION_FAILED';
      await tester.enterText(find.byKey(const ValueKey('ra-native-username')), 'Alice');
      await tester.enterText(find.byKey(const ValueKey('ra-native-password')), 'fixture-password');
      final login = find.descendant(of: find.byType(AlertDialog), matching: find.byType(FilledButton));
      await tester.ensureVisible(login);
      await tester.tap(login);
      await tester.pumpAndSettle();
      expect(dialogText(text(AppLocale.raSessionLoginError)), findsOneWidget);
      expect(find.text('RA_AUTHENTICATION_FAILED'), findsNothing);
      expect(tester.widget<TextField>(find.byKey(const ValueKey('ra-native-password'))).controller!.text, isEmpty);

      native.loginError = null;
      expect(await native.service.login('Alice', 'fixture-password'), isTrue);
      expect(await native.service.setEnabled(true), isTrue);
      expect(await native.service.setHardcore(true), isTrue);
      native.client.onSessionChanged!({'sessionId': 'locale-$code', 'engine': 'libretro',
        'generation': 3, 'enabled': true, 'supported': true, 'active': true,
        'gameLoaded': true, 'hardcoreActive': true});
      // Running Hardcore remains true while a new preference is pending.
      expect(await native.service.setHardcore(false), isTrue);
      await tester.pumpAndSettle();
      expect(dialogText(text(AppLocale.raSessionHardcoreHelp)), findsOneWidget);
      expect(dialogText(text(AppLocale.raSessionPending)), findsOneWidget);
      expect(dialogText(text(AppLocale.raSessionActive)), findsOneWidget);
      expect(dialogText('${text(AppLocale.raSessionHardcore)}: ${text(AppLocale.enabled)}'), findsOneWidget);
      expect(tester.widget<SwitchListTile>(find.byKey(const ValueKey('ra-central-enabled'))).value, isTrue);
      expect(tester.widget<SwitchListTile>(find.byKey(const ValueKey('ra-central-hardcore'))).value, isFalse);

      native.client.onSessionChanged!({'sessionId': 'locale-$code', 'engine': 'libretro',
        'generation': 3, 'enabled': true, 'supported': true, 'active': false,
        'gameLoaded': false, 'hardcoreActive': false, 'errorCode': 'RA_HARDCORE_OPTIONS'});
      await tester.pumpAndSettle();
      expect(dialogText(text(AppLocale.raSessionHardcoreError)), findsOneWidget);
      expect(dialogText(text(AppLocale.raSessionAwaiting)), findsOneWidget);
      expect(dialogText(text(AppLocale.raSessionActive)), findsNothing);
      expect(tester.takeException(), isNull, reason: code);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      expect(tester.takeException(), isNull);
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
  }

  testWidgets('long accents, CJK and Arabic content wrap under RTL without adding an Arabic UI locale', (tester) async {
    final longName = List.filled(24, 'Élodie 日本語 繁體中文 한국어 العربية').join(' · ');
    final native = RANativeFixture(username: longName);
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    final diagnostic = List.filled(80, 'RA_UNKNOWN_Échec_日本語_خطأ').join('_');
    native.client.onSessionChanged!({'sessionId': 'rtl', 'engine': 'libretro',
      'enabled': true, 'supported': true, 'active': false, 'errorCode': diagnostic});
    await pumpRA(tester, provider, 'fr', direction: TextDirection.rtl,
      home: RASessionSettings(initialUsername: '', service: native.service, onAccountChanged: (_) async {}));
    expect(AppLocale.supportedLanguages.keys, isNot(contains('ar')));
    expect(dialogText(longName), findsOneWidget);
    final renderedName = tester.widget<Text>(dialogText(longName));
    expect(renderedName.maxLines, isNull);
    expect(renderedName.softWrap, isNot(false));
    expect(dialogText(AppLocale.fr[AppLocale.raSessionUnavailable] as String), findsOneWidget);
    expect(find.text(diagnostic), findsNothing);
    final paragraphContext = tester.element(dialogText(longName));
    expect(Directionality.of(paragraphContext), TextDirection.rtl);
    final dialogRect = tester.getRect(find.byType(AlertDialog));
    expect(dialogRect.left, greaterThanOrEqualTo(0));
    expect(dialogRect.right, lessThanOrEqualTo(667));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('closing the dialog and tab during native login cannot retain the previous Web account', (tester) async {
    final native = RANativeFixture();
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isTrue);
    // The old dashboard is gone immediately when the central account signs out.
    expect(await native.service.logout(), isTrue);
    expect(provider.user, isNull);
    await pumpRA(tester, provider, 'fr');
    await tester.tap(find.byKey(const ValueKey('ra-central-settings')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('ra-native-username')), 'Bob');
    await tester.enterText(find.byKey(const ValueKey('ra-native-password')), 'fixture-password');
    native.loginGate = Completer<void>();
    final login = find.descendant(of: find.byType(AlertDialog), matching: find.byType(FilledButton));
    await tester.ensureVisible(login);
    await tester.tap(login);
    await tester.pump();
    expect(native.service.busy, isTrue);
    await tester.tap(dialogText(AppLocale.fr[AppLocale.close] as String));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    native.loginGate!.complete();
    await tester.pumpAndSettle();

    expect(native.service.username, 'Bob');
    expect(native.service.authenticated, isTrue);
    expect(provider.user, isNull);
    expect(provider.isConnected, isFalse);
    expect(source.profiles.where((request) => request.$1 == 'Alice'), hasLength(1));
    expect(await provider.connect('Bob', apiKey: 'bob-web-key'), isTrue);
    expect(provider.user!.user, 'Bob');
    expect(tester.takeException(), isNull);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
}
