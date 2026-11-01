import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/app_widget_localizations.dart'
    show appWidgetLocalizationsDelegates;
import 'package:neostation/l10n/retro_achievements_status_locale.dart';
import 'package:neostation/providers/retro_achievements_provider.dart';
import 'package:neostation/screens/retro_achievements_screen/ra_content.dart';
import 'package:neostation/screens/retro_achievements_screen/ra_session_settings.dart';
import 'package:neostation/services/global_notification_service.dart';
import 'package:neostation/services/retro_achievements_service.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/ra_dashboard_fixture.dart';

/// Regression coverage for the Build 608 credential report: valid Web API
/// credentials were refused locally (no request reached RetroAchievements)
/// whenever the in-game session was signed out, typed fields were wiped by an
/// account notification, and the in-game sign-in dialog collapsed under the
/// landscape keyboard.
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

  setUp(() => GlobalNotificationService().dismiss());

  group('Web dashboard and in-game session are independent credentials', () {
    test('valid Web API credentials connect while the in-game session is signed out', () async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();

      expect(await provider.connect(' Reckkles ', apiKey: ' web-key '), isTrue);
      expect(provider.isConnected, isTrue);
      expect(provider.accountErrorKey, isNull);
      expect(source.profiles, [('Reckkles', 'web-key')]);
      expect(source.savedUsername, 'Reckkles');
      expect(source.savedApiKey, 'web-key');
      // A Web API key never signs in an emulator nor enables RA in games.
      expect(native.service.authenticated, isFalse);
      expect(native.service.preferences.enabled, isFalse);
      expect(native.calls.map((call) => call.method), isNot(contains('login')));
    });

    test('saved Web credentials are restored after a restart without an in-game session', () async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture()
        ..savedUsername = 'Reckkles'
        ..savedApiKey = 'web-key';
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();

      expect(provider.isConnected, isTrue);
      expect(provider.user!.user, 'Reckkles');
      expect(source.writes, ['username:Reckkles', 'key:web-key']);
    });

    test('signing in game with the same account keeps the dashboard connected', () async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      expect(await provider.connect('Reckkles', apiKey: 'web-key'), isTrue);

      expect(await native.service.login('reckkles', 'fixture-password'), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(provider.isConnected, isTrue);
      expect(provider.user!.user, 'Reckkles');
      expect(source.savedApiKey, 'web-key');
    });

    test('signing out of the in-game session alone keeps the Web dashboard', () async {
      final native = RANativeFixture(username: 'Reckkles');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      expect(await provider.connect('Reckkles', apiKey: 'web-key'), isTrue);

      expect(await native.service.logout(), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(provider.isConnected, isTrue);
      expect(source.savedUsername, 'Reckkles');
      expect(source.savedApiKey, 'web-key');
    });

    test('a different in-game account is still reported instead of mixing two accounts', () async {
      final native = RANativeFixture(username: 'Bob');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();

      expect(await provider.connect('Alice', apiKey: 'alice-key'), isFalse);
      expect(provider.accountErrorKey, AppLocale.raSessionDifferentAccount);
      expect(source.profiles, isEmpty);
    });
  });

  group('Web sign-in failures are classified, never shown as raw text', () {
    for (final (failure, key) in [
      (RetroAchievementsWebFailure.rejected, AppLocale.raWebKeyRejected),
      (RetroAchievementsWebFailure.notFound, AppLocale.raWebUserNotFound),
      (RetroAchievementsWebFailure.network, AppLocale.raSessionNetworkError),
      (RetroAchievementsWebFailure.rateLimited, AppLocale.raSessionNetworkError),
      (RetroAchievementsWebFailure.server, AppLocale.raSessionServerError),
    ]) {
      test('${failure.name} -> $key', () async {
        final source = RADashboardFixture()
          ..profile = (_, _) => Future.error(RetroAchievementsWebException(failure, 401));
        final provider = RetroAchievementsProvider(source: source);
        addTearDown(provider.dispose);
        expect(await provider.connect('Reckkles', apiKey: 'web-key'), isFalse);
        expect(provider.accountErrorKey, key);
        expect(provider.isConnected, isFalse);
        expect(provider.isLoading, isFalse);
        expect(source.writes, isEmpty);
      });
    }

    test('an unknown user and empty fields have their own messages', () async {
      final source = RADashboardFixture()..profile = (_, _) => Future.value(null);
      final provider = RetroAchievementsProvider(source: source);
      addTearDown(provider.dispose);
      expect(await provider.connect('Nobody', apiKey: 'web-key'), isFalse);
      expect(provider.accountErrorKey, AppLocale.raWebUserNotFound);
      expect(await provider.connect('Reckkles', apiKey: '  '), isFalse);
      expect(provider.accountErrorKey, AppLocale.pleaseCompleteAllFields);
      expect(source.profiles, [('Nobody', 'web-key')]);
    });

    test('HTTP statuses map to refusal, unknown user, rate limit or server failure', () {
      expect(RetroAchievementsService.classifyProfileStatus(200), isNull);
      expect(RetroAchievementsService.classifyProfileStatus(401), RetroAchievementsWebFailure.rejected);
      expect(RetroAchievementsService.classifyProfileStatus(403), RetroAchievementsWebFailure.rejected);
      expect(RetroAchievementsService.classifyProfileStatus(404), RetroAchievementsWebFailure.notFound);
      expect(RetroAchievementsService.classifyProfileStatus(422), RetroAchievementsWebFailure.notFound);
      expect(RetroAchievementsService.classifyProfileStatus(429), RetroAchievementsWebFailure.rateLimited);
      expect(RetroAchievementsService.classifyProfileStatus(503), RetroAchievementsWebFailure.server);
      // The exception text never carries the key or the request URL.
      expect(const RetroAchievementsWebException(RetroAchievementsWebFailure.rejected, 401).toString(),
        'RetroAchievementsWebException(rejected, HTTP 401)');
    });

    test('a refused saved key is not retried in a loop at startup', () async {
      final source = RADashboardFixture()
        ..savedUsername = 'Reckkles'
        ..savedApiKey = 'reset-key'
        ..profile = (_, _) => Future.error(
          const RetroAchievementsWebException(RetroAchievementsWebFailure.rejected, 401));
      final provider = RetroAchievementsProvider(source: source);
      addTearDown(provider.dispose);
      await provider.initialize();
      expect(source.profiles, hasLength(1));
      expect(provider.accountErrorKey, AppLocale.raWebKeyRejected);
      // The pair stays saved: only the player decides to replace it.
      expect(source.savedApiKey, 'reset-key');
    });
  });

  test('every new label exists, is translated and is non-empty in the 12 catalogs', () {
    const catalogs = <String, Map<String, dynamic>>{
      'en': AppLocale.en, 'es': AppLocale.es, 'ru': AppLocale.ru,
      'zh': AppLocale.zh, 'zh_Hant': AppLocale.zhHant, 'pt': AppLocale.pt,
      'fr': AppLocale.fr, 'de': AppLocale.de, 'it': AppLocale.it,
      'id': AppLocale.id, 'ja': AppLocale.ja, 'ko': AppLocale.ko,
    };
    const keys = [
      AppLocale.raSessionInputRequired, AppLocale.raSessionServerError,
      AppLocale.raSessionTokenRejected, AppLocale.raSessionSignInHint,
      AppLocale.raSessionEnableHint, AppLocale.raSessionStatusSignedOut,
      AppLocale.raSessionStatusDisabled, AppLocale.raSessionStatusEnabled,
      AppLocale.raSessionStatusRejected, AppLocale.raWebKeyRejected,
      AppLocale.raWebUserNotFound,
    ];
    expect(catalogs.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    for (final key in keys) {
      for (final entry in catalogs.entries) {
        final value = entry.value[key];
        expect(value, isA<String>(), reason: '${entry.key}:$key');
        expect((value as String).trim(), isNotEmpty, reason: '${entry.key}:$key');
        if (entry.key != 'en') {
          expect(value, isNot(AppLocale.en[key]), reason: 'untranslated ${entry.key}:$key');
        }
      }
      // Traditional Chinese is its own catalog, not a copy of Simplified.
      expect(AppLocale.zhHant[key], isNot(AppLocale.zh[key]), reason: key);
    }
    // The hint quotes the exact localized button label.
    for (final entry in catalogs.entries) {
      expect(entry.value[AppLocale.raSessionSignInHint] as String,
        contains(entry.value[AppLocale.raSessionSettings] as String), reason: entry.key);
    }
  });

  group('in-game status labels', () {
    const languages = ['en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'];

    test('every status label exists in the 12 catalogs and keeps its placeholders', () {
      for (final language in languages) {
        final labels = RetroAchievementsStatusLocale.forLanguage(language);
        expect(labels.keys.toSet(), RetroAchievementsStatusLocale.keys.keys.toSet(), reason: language);
        for (final entry in labels.entries) {
          expect(entry.value.trim(), isNotEmpty, reason: '$language:${entry.key}');
          final catalogValue = RetroAchievementsStatusLocale.catalogFor(language)[
              RetroAchievementsStatusLocale.keys[entry.key]!];
          expect(catalogValue, entry.value, reason: 'missing $language:${entry.key}');
          // 'points' reuses the existing unit label (Spanish also says "pts").
          if (language != 'en' && entry.key != 'points') {
            expect(entry.value, isNot(RetroAchievementsStatusLocale.forLanguage('en')[entry.key]),
              reason: 'untranslated $language:${entry.key}');
          }
        }
        expect(labels['progress'], allOf(contains('{unlocked}'), contains('{total}')), reason: language);
      }
      final zh = RetroAchievementsStatusLocale.forLanguage('zh');
      final hant = RetroAchievementsStatusLocale.forLanguage('zh_Hant');
      for (final key in zh.keys.where((key) => key != 'points')) {
        expect(hant[key], isNot(zh[key]), reason: 'Traditional Chinese copies Simplified for $key');
      }
    });

    test('application language tags select the right catalog', () {
      for (final tag in ['zh_Hant', 'zh-Hant', 'zh-Hant-TW', 'zh-TW', 'zh-HK']) {
        expect(identical(RetroAchievementsStatusLocale.catalogFor(tag), AppLocale.zhHant), isTrue, reason: tag);
      }
      for (final tag in ['zh', 'zh-Hans', 'zh-Hans-CN']) {
        expect(identical(RetroAchievementsStatusLocale.catalogFor(tag), AppLocale.zh), isTrue, reason: tag);
      }
      expect(identical(RetroAchievementsStatusLocale.catalogFor('fr-CA'), AppLocale.fr), isTrue);
      expect(identical(RetroAchievementsStatusLocale.catalogFor('pt-BR'), AppLocale.pt), isTrue);
      expect(identical(RetroAchievementsStatusLocale.catalogFor('xx'), AppLocale.en), isTrue);
    });

    test('the native English fallbacks match the application catalog', () {
      final source = File('packages/retro_achievements_session/ios/Classes/RetroAchievementsSessionPlugin.m')
          .readAsStringSync();
      final body = source.split('static NSString *RBRAStatusFallback(').last.split('return english[key]').first;
      final pairs = {
        for (final match in RegExp(r'@"([A-Za-z]+)": @"((?:[^"\\]|\\.)*)"').allMatches(body))
          match.group(1)!: match.group(2)!,
      };
      final english = RetroAchievementsStatusLocale.forLanguage('en')..remove('points');
      expect(pairs.keys.toSet(), english.keys.toSet());
      for (final entry in english.entries) {
        // The native sign-in fallback cannot quote the localized button label.
        if (entry.key == 'signIn') continue;
        expect(pairs[entry.key], entry.value, reason: entry.key);
      }
    });

    test('launch preparation carries the labels of the app language and no account data', () async {
      final native = RANativeFixture(username: 'Reckkles');
      addTearDown(native.dispose);
      await native.service.setEnabled(true);
      await native.service.prepareLaunch(engine: 'dolphin', system: 'gc', language: 'zh_Hant');
      final args = Map<String, Object?>.from(
        native.calls.lastWhere((call) => call.method == 'prepareSession').arguments as Map);
      final labels = Map<String, String>.from(args['statusText'] as Map);
      expect(labels, RetroAchievementsStatusLocale.forLanguage('zh_Hant'));
      expect(labels.values.join(' '), isNot(contains('Reckkles')));
      expect(args.keys, isNot(contains('token')));
      expect(args.keys, isNot(contains('password')));
      expect(args.keys, isNot(contains('apiKey')));
    });
  });

  group('central session', () {
    test('a transient startup read failure is retried instead of disabling RA for the whole run', () async {
      final native = RANativeFixture(username: 'Reckkles')..accountFailures = 1;
      addTearDown(native.dispose);
      await native.service.initialize();
      expect(native.service.initialized, isFalse);
      expect(native.service.errorCode, 'RA_STORAGE_UNAVAILABLE');

      // The next consumer (tab, launch or toggle) retries the same read.
      await native.service.initialize();
      expect(native.service.initialized, isTrue);
      expect(native.service.authenticated, isTrue);
      expect(native.service.errorCode, isNull);
    });

    test('empty sign-in fields are an input error, not an authentication refusal', () async {
      final native = RANativeFixture(username: '');
      addTearDown(native.dispose);
      await native.service.initialize();

      expect(await native.service.login('Reckkles', ''), isFalse);
      expect(native.service.errorCode, 'RA_INPUT_REQUIRED');
      expect(await native.service.login('   ', 'secret'), isFalse);
      expect(native.service.errorCode, 'RA_INPUT_REQUIRED');
      expect(native.calls.map((call) => call.method), isNot(contains('login')));
      expect(raSessionErrorLabel('RA_INPUT_REQUIRED'), AppLocale.raSessionInputRequired);
    });

    test('a token refused by RetroAchievements during a game asks for the password again', () async {
      final native = RANativeFixture(username: 'Reckkles');
      addTearDown(native.dispose);
      await native.service.setEnabled(true);
      final launch = await native.service.prepareLaunch(engine: 'libretro', system: 'gba',
        core: 'mgba', language: 'fr');
      expect(launch['enabled'], isTrue);
      final prepared = native.calls.lastWhere((call) => call.method == 'prepareSession');
      expect((prepared.arguments as Map)['requested'], isTrue);
      // An unrelated engine error (another generation) never flags the account.
      native.client.onSessionChanged!({'sessionId': 'old', 'engine': 'dolphin', 'enabled': true,
        'supported': true, 'generation': 999, 'errorCode': 'login_failed_-35'});
      expect(native.service.tokenRejected, isFalse);
      // The launch generation of this account: RetroAchievements refused it.
      native.client.onSessionChanged!({'sessionId': 'game', 'engine': 'dolphin', 'enabled': true,
        'supported': true, 'generation': (prepared.arguments as Map)['generation'],
        'errorCode': 'login_failed_-35'});
      expect(native.service.tokenRejected, isTrue);
      expect(raSessionErrorLabel('login_failed_-35'), AppLocale.raSessionTokenRejected);
      expect(raSessionErrorLabel('login_failed_-32'), AppLocale.raSessionNetworkError);
      // A new sign-in replaces the refused token.
      expect(await native.service.login('Reckkles', 'new-password'), isTrue);
      expect(native.service.tokenRejected, isFalse);
    });

    test('players who switched RA off are not asked to sign in during games', () async {
      final native = RANativeFixture(username: '');
      addTearDown(native.dispose);
      await native.service.prepareLaunch(engine: 'armsx2', system: 'ps2', language: 'fr');
      final prepared = native.calls.lastWhere((call) => call.method == 'prepareSession');
      expect((prepared.arguments as Map)['requested'], isFalse);
      expect((prepared.arguments as Map)['enabled'], isFalse);
      expect((prepared.arguments as Map).keys, isNot(contains('token')));
      expect((prepared.arguments as Map).keys, isNot(contains('password')));
    });

    test('authentication, network and server failures keep distinct messages', () {
      expect(raSessionErrorLabel('RA_AUTHENTICATION_FAILED'), AppLocale.raSessionLoginError);
      expect(raSessionErrorLabel('RA_NETWORK_UNAVAILABLE'), AppLocale.raSessionNetworkError);
      expect(raSessionErrorLabel('RA_SERVER_ERROR'), AppLocale.raSessionServerError);
      expect(raSessionErrorLabel('RA_RATE_LIMITED'), AppLocale.raSessionNetworkError);
      expect(raSessionErrorLabel('RA_TOKEN_REJECTED'), AppLocale.raSessionTokenRejected);
      expect(raSessionErrorLabel('RA_LOGIN_REQUIRED'), AppLocale.raSessionLoginNeeded);
    });
  });

  Future<void> pumpTab(WidgetTester tester, RetroAchievementsProvider provider,
      {Size size = const Size(852, 393), Widget? home}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    localization.init(mapLocales: [
      MapLocale('en', AppLocale.en), MapLocale('fr', AppLocale.fr),
    ], initLanguageCode: 'fr');
    localization.translate('fr');
    // Same ScreenUtil design size as the application (main.dart), on an
    // iPhone 15 Pro landscape viewport (852 x 393 pt).
    await tester.pumpWidget(ScreenUtilInit(designSize: const Size(640, 480),
      builder: (_, _) => ChangeNotifierProvider.value(value: provider,
        child: MaterialApp(locale: const Locale('fr'),
          supportedLocales: localization.supportedLocales,
          localizationsDelegates: [
            ...localization.localizationsDelegates,
            ...appWidgetLocalizationsDelegates],
          home: Scaffold(body: home ?? const RAContent())))));
    await tester.pumpAndSettle();
  }

  List<String> errorNotifications() => [
    for (final item in GlobalNotificationService().notifier.value)
      if (item.type == GlobalNotificationType.error) item.message,
  ];

  List<String> notifications(GlobalNotificationType type) => [
    for (final item in GlobalNotificationService().notifier.value)
      if (item.type == type) item.message,
  ];

  Future<void> tapTabLogin(WidgetTester tester) async {
    final button = find.widgetWithText(ElevatedButton, AppLocale.fr[AppLocale.login] as String);
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pumpAndSettle();
  }

  String fr(String key) => AppLocale.fr[key] as String;

  testWidgets('main tab Web form signs in while the in-game session is signed out', (tester) async {
    final native = RANativeFixture(username: '');
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    await pumpTab(tester, provider);

    // The key alone still connects the statistics; the password of the same
    // form is optional (it only turns on achievements in games).
    await tester.enterText(find.byKey(const ValueKey('ra-web-username')), 'Reckkles');
    await tester.enterText(find.byKey(const ValueKey('ra-web-api-key')), 'web-key');
    await tapTabLogin(tester);

    expect(errorNotifications(), isEmpty);
    expect(native.calls.where((call) => call.method == 'login'), isEmpty);
    expect(provider.isConnected, isTrue);
    expect(source.profiles, [('Reckkles', 'web-key')]);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('a pasted API key survives an in-game sign-in notification', (tester) async {
    final native = RANativeFixture(username: '');
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    await pumpTab(tester, provider);

    await tester.enterText(find.byKey(const ValueKey('ra-web-username')), 'Reckkles');
    await tester.enterText(find.byKey(const ValueKey('ra-web-api-key')), 'pasted-web-key');
    expect(await native.service.login('Reckkles', 'fixture-password'), isTrue);
    await tester.pumpAndSettle();

    // Signed in for games: the password field leaves the form, the key stays.
    expect(find.byKey(const ValueKey('ra-web-password')), findsNothing);
    final key = tester.widget<TextFormField>(find.byKey(const ValueKey('ra-web-api-key')));
    expect(key.controller!.text, 'pasted-web-key');
    final user = tester.widget<TextFormField>(find.byKey(const ValueKey('ra-web-username')));
    expect(user.controller!.text, 'Reckkles');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('moving from the username to the API key keeps the keyboard connected', (tester) async {
    final native = RANativeFixture(username: '');
    final provider = RetroAchievementsProvider(sessionService: native.service, source: RADashboardFixture());
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    await pumpTab(tester, provider);

    await tester.tap(find.byKey(const ValueKey('ra-web-username')));
    await tester.pump();
    expect(tester.testTextInput.hasAnyClients, isTrue);
    // Tapping the second field moves the gamepad highlight with the focus.
    // Build 608 re-created the field at that moment and closed its input
    // connection: the keyboard vanished while the field still looked focused.
    await tester.tap(find.byKey(const ValueKey('ra-web-api-key')));
    await tester.pumpAndSettle();
    expect(tester.testTextInput.hasAnyClients, isTrue);
    tester.testTextInput.enterText('typed-after-one-tap');
    await tester.pump();
    final key = tester.widget<TextFormField>(find.byKey(const ValueKey('ra-web-api-key')));
    expect(key.controller!.text, 'typed-after-one-tap');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('a refused in-game token reopens the sign-in form with its own message', (tester) async {
    final native = RANativeFixture(username: 'Reckkles');
    final provider = RetroAchievementsProvider(sessionService: native.service, source: RADashboardFixture());
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    await native.service.setEnabled(true);
    final launch = await native.service.prepareLaunch(engine: 'libretro', system: 'gba', core: 'mgba', language: 'fr');
    expect(launch['enabled'], isTrue);
    final generation = (native.calls.lastWhere((call) => call.method == 'prepareSession').arguments as Map)['generation'];
    native.client.onSessionChanged!({'sessionId': 'game', 'engine': 'libretro', 'enabled': true,
      'supported': true, 'generation': generation, 'errorCode': 'RA_AUTHENTICATION_FAILED'});
    await pumpTab(tester, provider, home: RASessionSettings(initialUsername: '', service: native.service,
      onAccountChanged: (_) async {}));

    expect(find.byKey(const ValueKey('ra-native-password')), findsOneWidget);
    expect(find.text(AppLocale.fr[AppLocale.raSessionTokenRejected] as String), findsOneWidget);
    final username = tester.widget<TextField>(find.byKey(const ValueKey('ra-native-username')));
    expect(username.controller!.text, 'Reckkles');
    expect(username.autocorrect, isFalse);
    expect(username.enableSuggestions, isFalse);
    expect(username.smartQuotesType, SmartQuotesType.disabled);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('in-game sign-in keeps the focused password visible above a landscape keyboard', (tester) async {
    final native = RANativeFixture(username: '');
    final provider = RetroAchievementsProvider(sessionService: native.service, source: RADashboardFixture());
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    const screen = Size(852, 393);
    const keyboard = 213.0;
    await pumpTab(tester, provider, size: screen, home: Builder(builder: (context) => Center(
      child: TextButton(onPressed: () => showDialog<void>(context: context,
        builder: (_) => RASessionSettings(initialUsername: 'Reckkles', service: native.service,
          onAccountChanged: (_) async {})),
        child: const Text('open')))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    // Real sequence: the player taps the field, then iOS raises the keyboard.
    final password = find.byKey(const ValueKey('ra-native-password'));
    await tester.tap(password);
    await tester.pump();
    tester.view.viewInsets = const FakeViewPadding(bottom: keyboard);
    await tester.pumpAndSettle();
    await tester.enterText(password, 'typed-secret');
    await tester.pumpAndSettle();

    final field = tester.getRect(password);
    final viewport = tester.getRect(find.ancestor(of: password, matching: find.byType(Scrollable)).first);
    final visible = field.intersect(viewport);
    expect(visible.height, greaterThanOrEqualTo(field.height - 1),
      reason: 'field $field is clipped by its scroll viewport $viewport');
    expect(field.bottom, lessThanOrEqualTo(screen.height - keyboard));
    expect(field.top, greaterThanOrEqualTo(0));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
  group('one sign-in for statistics and games (maintainer request, 1 November 2026)', () {
    setUp(() => GlobalNotificationService().notifier.value = const []);

    testWidgets('the tab form signs games and statistics in with one entry', (tester) async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      await pumpTab(tester, provider);

      expect(find.text(fr(AppLocale.raUnifiedPasswordHelp)), findsOneWidget);
      final password = tester.widget<TextField>(find.descendant(
        of: find.byKey(const ValueKey('ra-web-password')), matching: find.byType(TextField)));
      expect(password.obscureText, isTrue);
      expect(password.autocorrect, isFalse);
      expect(password.enableSuggestions, isFalse);
      // "Next", not "Done": the keyboard key never submits the form.
      expect(password.textInputAction, TextInputAction.next);

      await tester.enterText(find.byKey(const ValueKey('ra-web-username')), 'Reckkles');
      await tester.enterText(find.byKey(const ValueKey('ra-web-password')), 'fixture-password');
      await tester.enterText(find.byKey(const ValueKey('ra-web-api-key')), 'web-key');
      await tapTabLogin(tester);

      expect(errorNotifications(), isEmpty);
      final logins = native.calls.where((call) => call.method == 'login').toList();
      expect(logins, hasLength(1));
      expect((logins.single.arguments as Map)['password'], 'fixture-password');
      expect(native.service.authenticated, isTrue);
      // Signing in for games turns achievements in games on.
      expect(native.service.preferences.enabled, isTrue);
      expect(provider.isConnected, isTrue);
      expect(source.profiles, [('Reckkles', 'web-key')]);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('the password alone turns on achievements in games', (tester) async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      await pumpTab(tester, provider);

      await tester.enterText(find.byKey(const ValueKey('ra-web-username')), 'Reckkles');
      await tester.enterText(find.byKey(const ValueKey('ra-web-password')), 'fixture-password');
      await tapTabLogin(tester);

      expect(errorNotifications(), isEmpty);
      expect(native.service.authenticated, isTrue);
      expect(native.service.preferences.enabled, isTrue);
      expect(provider.isConnected, isFalse);
      expect(source.profiles, isEmpty);
      expect(notifications(GlobalNotificationType.success), contains(fr(AppLocale.raInGameSignedInAddKey)));
      expect(find.byKey(const ValueKey('ra-web-password')), findsNothing);
      expect(tester.widget<Switch>(find.byKey(const ValueKey('ra-tab-enabled'))).value, isTrue);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('the Web API key typed as the password is caught before any request', (tester) async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      await pumpTab(tester, provider);

      await tester.enterText(find.byKey(const ValueKey('ra-web-username')), 'Reckkles');
      await tester.enterText(find.byKey(const ValueKey('ra-web-password')), 'same-web-key');
      await tester.enterText(find.byKey(const ValueKey('ra-web-api-key')), 'same-web-key');
      await tapTabLogin(tester);

      expect(errorNotifications(), [fr(AppLocale.raPasswordIsApiKey)]);
      expect(native.calls.where((call) => call.method == 'login'), isEmpty);
      expect(source.profiles, isEmpty);
      final password = tester.widget<TextFormField>(find.byKey(const ValueKey('ra-web-password')));
      expect(password.controller!.text, 'same-web-key');
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('a refused password keeps what was typed and says why', (tester) async {
      final native = RANativeFixture(username: '')..loginError = 'RA_AUTHENTICATION_FAILED';
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      await pumpTab(tester, provider);

      await tester.enterText(find.byKey(const ValueKey('ra-web-username')), 'Reckkles');
      await tester.enterText(find.byKey(const ValueKey('ra-web-password')), 'wrong-password');
      await tester.enterText(find.byKey(const ValueKey('ra-web-api-key')), 'web-key');
      await tapTabLogin(tester);

      expect(errorNotifications(), [fr(AppLocale.raSessionLoginError)]);
      expect(native.service.authenticated, isFalse);
      // No half sign-in: the statistics wait for a password that works.
      expect(source.profiles, isEmpty);
      expect(tester.widget<TextFormField>(find.byKey(const ValueKey('ra-web-password'))).controller!.text,
        'wrong-password');
      expect(tester.widget<TextFormField>(find.byKey(const ValueKey('ra-web-api-key'))).controller!.text,
        'web-key');
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('Hardcore is switched in the tab itself, without credentials', (tester) async {
      final native = RANativeFixture(username: '');
      final provider = RetroAchievementsProvider(sessionService: native.service, source: RADashboardFixture());
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      await pumpTab(tester, provider);

      expect(find.byType(AlertDialog), findsNothing);
      final hardcore = find.byKey(const ValueKey('ra-tab-hardcore'));
      expect(tester.widget<Switch>(hardcore).value, isFalse);
      await tester.tap(hardcore);
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(native.service.preferences.hardcore, isTrue);
      expect(tester.widget<Switch>(hardcore).value, isTrue);
      expect(native.calls.where((call) => call.method == 'login'), isEmpty);

      // Signed in: achievements in games are switched off and on in place.
      expect(await native.service.login('Reckkles', 'fixture-password'), isTrue);
      expect(await native.service.setEnabled(true), isTrue);
      await tester.pumpAndSettle();
      final enabled = find.byKey(const ValueKey('ra-tab-enabled'));
      expect(tester.widget<Switch>(enabled).value, isTrue);
      await tester.tap(enabled);
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(native.service.preferences.enabled, isFalse);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('an account already connected for statistics asks only for its password', (tester) async {
      final native = RANativeFixture(username: '');
      final source = RADashboardFixture();
      final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
      addTearDown(() { provider.dispose(); native.dispose(); });
      await provider.initialize();
      expect(await provider.connect('Reckkles', apiKey: 'web-key'), isTrue);
      await pumpTab(tester, provider);
      // The connected dashboard keeps its own loading spinners running here
      // (fixture without section data): advance time instead of settling.
      Future<void> settle() async {
        for (var i = 0; i < 4; i++) { await tester.pump(const Duration(milliseconds: 150)); }
      }

      // The status says what is missing, and opens the password-only form.
      expect(find.text(fr(AppLocale.raSessionStatusPasswordNeeded)), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('ra-central-settings')));
      await settle();
      expect(find.byKey(const ValueKey('ra-native-username')), findsNothing);
      expect(find.descendant(of: find.byKey(const ValueKey('ra-native-account')),
        matching: find.text('Reckkles')), findsOneWidget);
      expect(find.text(fr(AppLocale.raSessionPasswordOnly)), findsOneWidget);

      // The Web API key pasted as the password: caught locally, kept for correction.
      final password = find.byKey(const ValueKey('ra-native-password'));
      await tester.enterText(password, 'web-key');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await settle();
      expect(find.text(fr(AppLocale.raPasswordIsApiKey)), findsOneWidget);
      expect(native.calls.where((call) => call.method == 'login'), isEmpty);
      expect(tester.widget<TextField>(password).controller!.text, 'web-key');

      // A refused password submitted with the keyboard key stays, with the
      // reason shown next to the button (Build 610 video: it was cleared and
      // the error stayed below the visible area).
      native.loginError = 'RA_AUTHENTICATION_FAILED';
      await tester.enterText(password, 'wrong-password');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await settle();
      expect(find.text(fr(AppLocale.raSessionLoginError)), findsOneWidget);
      expect(tester.widget<TextField>(password).controller!.text, 'wrong-password');
      final logins = native.calls.where((call) => call.method == 'login').toList();
      expect(logins, hasLength(1));
      expect((logins.single.arguments as Map)['username'], 'Reckkles');

      native.loginError = null;
      await tester.enterText(password, 'fixture-password');
      final login = find.descendant(of: find.byType(AlertDialog), matching: find.byType(FilledButton));
      await tester.ensureVisible(login);
      await tester.tap(login);
      await settle();
      expect(native.service.authenticated, isTrue);
      expect(native.service.username, 'Reckkles');
      expect(native.service.preferences.enabled, isTrue);
      expect(provider.isConnected, isTrue);
      expect(provider.username, 'Reckkles');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
  });
}
