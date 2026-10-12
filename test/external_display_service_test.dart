import 'dart:async';
import 'dart:convert';

import 'package:external_display/external_display.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/external_display/external_display_entrypoint.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/screens/app_screen.dart';
import 'package:neostation/services/external_display_service.dart';
import 'package:neostation/services/secondary_display_bridge.dart';

Map<String, Object?> nativeState({
  bool supported = true,
  bool connected = false,
  String content = 'none',
  double screenWidth = 0,
  double screenHeight = 0,
  double screenScale = 0,
  int mode = 0,
  bool enabled = true,
  bool menuOnTV = true,
  bool suspended = false,
  bool mirroringActive = false,
  String accessoryStatus = 'unavailable',
  String sceneRole = 'none',
  String menuEngine = 'none',
}) => <String, Object?>{
  'supported': supported,
  'connected': connected,
  'content': content,
  'screenWidth': screenWidth,
  'screenHeight': screenHeight,
  'screenScale': screenScale,
  'mode': mode,
  'enabled': enabled,
  'menuOnTV': menuOnTV,
  'suspended': suspended,
  'mirroringActive': mirroringActive,
  'accessoryStatus': accessoryStatus,
  'sceneRole': sceneRole,
  'menuEngine': menuEngine,
};

/// Fake native side: answers like ExternalDisplayPlugin.m (preferences in
/// "NSUserDefaults", every answer is the re-read state).
class FakeNative {
  FakeNative({Map<String, Object?>? state}) : state = state ?? nativeState();

  Map<String, Object?> state;
  final List<MethodCall> calls = <MethodCall>[];
  final List<String> pushed = <String>[];
  PlatformException? failGetState;
  PlatformException? failSetEnabled;
  PlatformException? failSetMode;
  PlatformException? failSetMenuOnTV;
  PlatformException? failConfigure;
  PlatformException? failUpdate;

  /// What `updateMenuEngine` answers (the native host answers true).
  Object? updateAnswer = true;

  /// When false the mode write "succeeds" without keeping the value.
  bool keepMode = true;

  Future<Object?> handle(MethodCall call) async {
    calls.add(call);
    final arguments = call.arguments is Map
        ? (call.arguments as Map).cast<String, Object?>()
        : const <String, Object?>{};
    switch (call.method) {
      case 'getState':
        if (failGetState != null) throw failGetState!;
        return state;
      case 'setEnabled':
        if (failSetEnabled != null) throw failSetEnabled!;
        state = <String, Object?>{...state, 'enabled': arguments['enabled']};
        return state;
      case 'setMode':
        if (failSetMode != null) throw failSetMode!;
        if (keepMode) {
          state = <String, Object?>{...state, 'mode': arguments['mode']};
        }
        return state;
      case 'setMenuOnTV':
        if (failSetMenuOnTV != null) throw failSetMenuOnTV!;
        state = <String, Object?>{...state, 'menuOnTV': arguments['enabled']};
        return state;
      case 'configureMenuEngine':
        if (failConfigure != null) throw failConfigure!;
        state = <String, Object?>{...state, 'menuEngine': 'none'};
        return state;
      case 'updateMenuEngine':
        if (failUpdate != null) throw failUpdate!;
        return updateAnswer;
      case 'pushMenuState':
        pushed.add(arguments['json'] as String);
        return true;
    }
    throw MissingPluginException();
  }

  int count(String method) => calls.where((c) => c.method == method).length;

  Iterable<MethodCall> of(String method) =>
      calls.where((c) => c.method == method);
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  late FakeNative native;
  late StreamController<ExternalDisplayState> events;

  ExternalDisplayService service() =>
      ExternalDisplayService.forTesting(events: events.stream);

  setUp(() {
    native = FakeNative();
    events = StreamController<ExternalDisplayState>.broadcast();
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      native.handle,
    );
  });

  tearDown(() async {
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      null,
    );
    await events.close();
  });

  group('state', () {
    test('the native state is read field by field', () async {
      native.state = nativeState(
        connected: true,
        content: 'menu',
        screenWidth: 1920,
        screenHeight: 1080,
        screenScale: 1,
        mode: 2,
        menuOnTV: true,
        accessoryStatus: 'registered',
        sceneRole: 'scene',
        menuEngine: 'attached',
      );
      final state = await service().refresh();
      expect(state.supported, isTrue);
      expect(state.connected, isTrue);
      expect(state.content, ExternalDisplayContent.menu);
      expect(state.menuOnExternal, isTrue);
      expect(state.gameOnExternal, isFalse);
      expect(state.screenWidth, 1920);
      expect(state.screenHeight, 1080);
      expect(state.mode, ExternalDisplayMode.fill);
      expect(state.effectiveGameMode, ExternalDisplayMode.fill);
      expect(state.accessoryStatus, 'registered');
      expect(state.sceneRole, 'scene');
      expect(state.menuEngine, 'attached');
      expect(state.suspended, isFalse);
      expect(native.count('getState'), 1);
    });

    test('the suspension of an unsupported engine is read, absent is false', () async {
      native.state = nativeState(
        connected: true,
        suspended: true,
        mirroringActive: true,
      );
      expect((await service().refresh()).suspended, isTrue);
      // A native host before the review of 12 October 2026 sends no key.
      native.state = Map<String, Object?>.of(nativeState(connected: true))
        ..remove('suspended');
      expect((await service().refresh()).suspended, isFalse);
    });

    test('Automatic applies as Fit to a game', () async {
      native.state = nativeState(connected: true, content: 'game');
      final state = await service().refresh();
      expect(state.mode, ExternalDisplayMode.automatic);
      expect(state.effectiveGameMode, ExternalDisplayMode.fit);
      expect(state.gameOnExternal, isTrue);
    });

    test('a missing plugin or a failing channel is unsupported', () async {
      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        ExternalDisplayChannel.channel,
        null,
      );
      final missing = await service().refresh();
      expect(missing.supported, isFalse);
      expect(missing.accessoryStatus, ExternalDisplayState.pluginMissing);

      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        ExternalDisplayChannel.channel,
        native.handle,
      );
      native.failGetState = PlatformException(code: 'BROKEN');
      final failing = await service().refresh();
      expect(failing.supported, isFalse);
      expect(failing.accessoryStatus, 'BROKEN');
    });

    test('concurrent refreshes share one read', () async {
      final subject = service();
      final results = await Future.wait(<Future<ExternalDisplayState>>[
        subject.refresh(),
        subject.refresh(),
        subject.refresh(),
      ]);
      expect(native.count('getState'), 1);
      expect(results.map((s) => s.supported), everyElement(isTrue));
      // A later refresh reads again.
      await subject.refresh();
      expect(native.count('getState'), 2);
    });
  });

  group('preferences', () {
    test('a format is stored and re-read from the native answer', () async {
      final subject = service();
      await subject.refresh();
      var notified = 0;
      subject.addListener(() => notified++);

      expect(await subject.setMode(ExternalDisplayMode.original), isTrue);
      expect(native.of('setMode').single.arguments, <String, Object?>{
        'mode': 3,
      });
      expect(subject.state!.mode, ExternalDisplayMode.original);
      expect(subject.error, isNull);
      expect(subject.saving, isFalse);
      expect(notified, greaterThanOrEqualTo(2), reason: 'saving, then stored');
    });

    test('the switches are stored and toggled from the native state', () async {
      final subject = service();
      await subject.refresh();

      expect(await subject.toggleEnabled(), isTrue);
      expect(native.of('setEnabled').single.arguments, <String, Object?>{
        'enabled': false,
      });
      expect(subject.state!.enabled, isFalse);

      expect(await subject.toggleMenuOnTV(), isTrue);
      expect(native.of('setMenuOnTV').single.arguments, <String, Object?>{
        'enabled': false,
      });
      expect(subject.state!.menuOnTV, isFalse);

      expect(await subject.toggleEnabled(), isTrue);
      expect(subject.state!.enabled, isTrue);
    });

    test('cycleMode walks Automatic, Fit, Fill, Original, Automatic', () async {
      final subject = service();
      await subject.refresh();
      final seen = <ExternalDisplayMode>[];
      for (var step = 0; step < 4; step++) {
        expect(await subject.cycleMode(), isTrue);
        seen.add(subject.state!.mode);
      }
      expect(seen, <ExternalDisplayMode>[
        ExternalDisplayMode.fit,
        ExternalDisplayMode.fill,
        ExternalDisplayMode.original,
        ExternalDisplayMode.automatic,
      ]);
      expect(
        native.of('setMode').map((c) => (c.arguments as Map)['mode']).toList(),
        <int>[1, 2, 3, 0],
      );
      expect(ExternalDisplayMode.fill.crops, isTrue);
      expect(ExternalDisplayMode.fit.crops, isFalse);
    });

    test('SAVE_FAILED is surfaced and never shown as a saved choice', () async {
      final subject = service();
      await subject.refresh();
      native.failSetMode = PlatformException(code: 'SAVE_FAILED');

      expect(await subject.setMode(ExternalDisplayMode.fill), isFalse);
      expect(subject.error, ExternalDisplayError.saveFailed);
      expect(subject.errorField, ExternalDisplayField.mode);
      expect(subject.errorCode, 'SAVE_FAILED');
      expect(subject.state!.mode, ExternalDisplayMode.automatic);
      expect(subject.saving, isFalse);
      // The state was re-read to show what iOS kept.
      await Future<void>.delayed(Duration.zero);
      expect(native.count('getState'), 2);

      native.failSetMode = null;
      expect(await subject.setMode(ExternalDisplayMode.fill), isTrue);
      expect(subject.error, isNull);
      expect(subject.errorField, isNull);
      expect(subject.errorCode, isNull);
    });

    test('an answer that did not keep the choice is a save failure', () async {
      final subject = service();
      await subject.refresh();
      native.keepMode = false;
      expect(await subject.setMode(ExternalDisplayMode.fit), isFalse);
      expect(subject.error, ExternalDisplayError.saveFailed);
      expect(subject.errorCode, 'SAVE_NOT_KEPT');
      expect(subject.state!.mode, ExternalDisplayMode.automatic);
    });

    test('each switch reports its own failure', () async {
      final subject = service();
      await subject.refresh();
      native.failSetEnabled = PlatformException(code: 'SAVE_FAILED');
      expect(await subject.setEnabled(false), isFalse);
      expect(subject.errorField, ExternalDisplayField.enabled);
      expect(subject.state!.enabled, isTrue);

      native.failSetMenuOnTV = PlatformException(code: 'SAVE_FAILED');
      expect(await subject.setMenuOnTV(false), isFalse);
      expect(subject.errorField, ExternalDisplayField.menuOnTV);
      expect(subject.state!.menuOnTV, isTrue);
    });

    test('nothing is written while the plugin is unsupported', () async {
      native.state = nativeState(supported: false);
      final subject = service();
      await subject.refresh();
      expect(await subject.setEnabled(false), isFalse);
      expect(await subject.setMode(ExternalDisplayMode.fit), isFalse);
      expect(await subject.setMenuOnTV(false), isFalse);
      expect(await subject.toggleEnabled(), isFalse);
      expect(await subject.cycleMode(), isFalse);
      expect(await subject.toggleMenuOnTV(), isFalse);
      expect(native.count('setEnabled'), 0);
      expect(native.count('setMode'), 0);
      expect(native.count('setMenuOnTV'), 0);
    });

    test('nothing is written before the first state', () async {
      final subject = service();
      expect(await subject.setMode(ExternalDisplayMode.fit), isFalse);
      expect(native.count('setMode'), 0);
    });
  });

  group('init', () {
    // Retired contract: the arguments were the entrypoint pair only. The TV
    // engine never opens the database (review of 12 October 2026, m11), so
    // configureMenuEngine also carries the language and theme it starts
    // with (null when unknown).
    test('configureMenuEngine is sent once with the entrypoint pair', () async {
      final subject = service();
      await subject.init();
      await subject.init(languageCode: 'fr', themeName: 'oled');
      final configured = native.of('configureMenuEngine').toList();
      expect(configured, hasLength(1));
      expect(configured.single.arguments, <String, Object?>{
        'entrypoint': kExternalDisplayEntrypoint,
        'libraryUri': kExternalDisplayLibraryUri,
        'languageCode': null,
        'themeName': null,
      });
      expect(kExternalDisplayEntrypoint, 'externalDisplayMain');
      expect(
        kExternalDisplayLibraryUri,
        'package:neostation/external_display/external_display_entrypoint.dart',
      );
      expect(subject.initialized, isTrue);
      expect(subject.menuEngineConfigured, 1);
      // The response is the first state: no separate read was needed.
      expect(subject.state, isNotNull);
      expect(subject.state!.supported, isTrue);
      expect(native.count('getState'), 0);
    });

    test('a missing plugin leaves an unsupported state and never throws', () async {
      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        ExternalDisplayChannel.channel,
        null,
      );
      final subject = service();
      await subject.init();
      expect(subject.state!.supported, isFalse);
      expect(subject.state!.accessoryStatus, ExternalDisplayState.pluginMissing);
      expect(subject.menuEngineConfigured, 0);
    });

    test('a refused configuration keeps its raw code', () async {
      native.failConfigure = PlatformException(code: 'BAD_ARGS');
      final subject = service();
      await subject.init();
      expect(subject.state!.supported, isFalse);
      expect(subject.state!.accessoryStatus, 'BAD_ARGS');
    });

    test('the TV engine is given the app language and theme', () async {
      final subject = service();
      await subject.init(languageCode: ' zh_Hant ', themeName: 'tokyo_night');
      expect(native.of('configureMenuEngine').single.arguments, <String, Object?>{
        'entrypoint': kExternalDisplayEntrypoint,
        'libraryUri': kExternalDisplayLibraryUri,
        'languageCode': 'zh_Hant',
        'themeName': 'tokyo_night',
      });
      expect(subject.menuLanguageCode, 'zh_Hant');
      expect(subject.menuThemeName, 'tokyo_night');
      // Blank values are no value.
      final blank = service();
      await blank.init(languageCode: '', themeName: '  ');
      final arguments = native.of('configureMenuEngine').last.arguments as Map;
      expect(arguments['languageCode'], isNull);
      expect(arguments['themeName'], isNull);
    });
  });

  group('updateMenuEngine', () {
    test('a new language or theme reaches the native copy once', () async {
      final subject = service();
      await subject.init(languageCode: 'fr', themeName: 'dark');

      expect(await subject.updateMenuEngine(languageCode: 'fr'), isFalse);
      expect(await subject.updateMenuEngine(themeName: 'dark'), isFalse);
      expect(native.count('updateMenuEngine'), 0, reason: 'nothing changed');

      expect(await subject.updateMenuEngine(languageCode: 'de'), isTrue);
      expect(native.of('updateMenuEngine').single.arguments, <String, Object?>{
        'languageCode': 'de',
        'themeName': null,
      });
      expect(subject.menuLanguageCode, 'de');

      expect(
        await subject.updateMenuEngine(languageCode: 'de', themeName: 'nord'),
        isTrue,
      );
      expect(native.of('updateMenuEngine').last.arguments, <String, Object?>{
        'languageCode': null,
        'themeName': 'nord',
      });
      expect(subject.menuThemeName, 'nord');
      expect(subject.menuEngineUpdates, 2);
    });

    test('nothing is sent before init: init carries the values', () async {
      final subject = service();
      expect(await subject.updateMenuEngine(languageCode: 'ja'), isFalse);
      expect(native.count('updateMenuEngine'), 0);
      expect(subject.menuLanguageCode, isNull);
      await subject.init(languageCode: 'ko');
      expect(
        (native.of('configureMenuEngine').single.arguments as Map)['languageCode'],
        'ko',
      );
    });

    test('a refusal or a missing plugin never throws', () async {
      final subject = service();
      await subject.init(languageCode: 'en');
      native.failUpdate = PlatformException(code: 'BAD_ARGS');
      expect(await subject.updateMenuEngine(languageCode: 'it'), isFalse);
      expect(subject.menuEngineUpdates, 0);
      native.failUpdate = null;
      native.updateAnswer = null;
      expect(await subject.updateMenuEngine(languageCode: 'pt'), isFalse);

      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        ExternalDisplayChannel.channel,
        null,
      );
      expect(await subject.updateMenuEngine(languageCode: 'es'), isFalse);
      expect(subject.menuLanguageCode, 'es', reason: 'kept for a later engine');
    });
  });

  group('events', () {
    test('native state events update the state after init', () async {
      final subject = service();
      var notified = 0;
      subject.addListener(() => notified++);
      await subject.init();
      expect(subject.state!.connected, isFalse);

      events.add(
        ExternalDisplayState.fromMap(
          nativeState(
            connected: true,
            content: 'menu',
            screenWidth: 1920,
            screenHeight: 1080,
            menuEngine: 'attached',
          ),
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(subject.state!.connected, isTrue);
      expect(subject.state!.menuOnExternal, isTrue);
      expect(subject.state!.screenWidth, 1920);
      expect(notified, greaterThanOrEqualTo(2));

      events.add(
        ExternalDisplayState.fromMap(nativeState(connected: false)),
      );
      await Future<void>.delayed(Duration.zero);
      expect(subject.state!.connected, isFalse);

      // Disposed: later events are ignored.
      subject.dispose();
      events.add(ExternalDisplayState.fromMap(nativeState(connected: true)));
      await Future<void>.delayed(Duration.zero);
      expect(subject.state!.connected, isFalse);
    });

    test('events are not followed before init', () async {
      final subject = service();
      await subject.refresh();
      events.add(ExternalDisplayState.fromMap(nativeState(connected: true)));
      await Future<void>.delayed(Duration.zero);
      expect(subject.state!.connected, isFalse);
    });

    test('the real event channel delivers the native state', () async {
      MockStreamHandlerEventSink? sink;
      binding.defaultBinaryMessenger.setMockStreamHandler(
        ExternalDisplayChannel.eventChannel,
        MockStreamHandler.inline(
          onListen: (Object? arguments, MockStreamHandlerEventSink events) {
            sink = events;
          },
        ),
      );
      addTearDown(
        () => binding.defaultBinaryMessenger.setMockStreamHandler(
          ExternalDisplayChannel.eventChannel,
          null,
        ),
      );
      final subject = ExternalDisplayService.forTesting();
      await subject.init();
      await Future<void>.delayed(Duration.zero);
      expect(sink, isNotNull, reason: 'init subscribed to the event channel');
      sink!.success(
        nativeState(connected: true, content: 'game', screenWidth: 1280),
      );
      await Future<void>.delayed(Duration.zero);
      expect(subject.state!.gameOnExternal, isTrue);
      expect(subject.state!.screenWidth, 1280);
      subject.dispose();
    });
  });

  group('menu state', () {
    test('pushMenuState relays the JSON of the display state', () async {
      final subject = service();
      final data = SecondaryDisplayStateData(
        systemName: 'SNES',
        systemLogo: 'assets/images/logos/snes.webp',
        isLogoAsset: true,
        backgroundColor: 0xFF102030,
      );
      expect(await subject.pushMenuState(data), isTrue);
      expect(native.pushed, hasLength(1));
      expect(native.pushed.single, jsonEncode(data.toJson()));
      final decoded = jsonDecode(native.pushed.single) as Map<String, dynamic>;
      expect(SecondaryDisplayStateData.fromJson(decoded).systemName, 'SNES');
    });

    test('a missing plugin refuses the menu state without throwing', () async {
      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        ExternalDisplayChannel.channel,
        null,
      );
      expect(
        await service().pushMenuState(
          SecondaryDisplayStateData(systemName: 'WELCOME'),
        ),
        isFalse,
      );
    });

    test('the bridge merges like the shared state and forwards on iOS only', () async {
      final subject = service();
      final bridge = SecondaryDisplayBridge.forTesting(service: subject);
      expect(bridge.latest, isNull);

      expect(
        await bridge.forward(
          (current) => current.copyWith(systemName: 'SNES', isOled: true),
        ),
        isTrue,
      );
      expect(bridge.latest!.systemName, 'SNES');
      expect(bridge.latest!.isOled, isTrue);

      // A partial update keeps the fields it does not name.
      expect(
        await bridge.forward(
          (current) => current.copyWith(backgroundColor: 0xFF000000),
        ),
        isTrue,
      );
      expect(bridge.latest!.systemName, 'SNES');
      expect(bridge.latest!.isOled, isTrue);
      expect(bridge.latest!.backgroundColor, 0xFF000000);
      expect(bridge.forwarded, 2);
      expect(native.pushed, hasLength(2));
      expect(
        SecondaryDisplayStateData.fromJson(
          jsonDecode(native.pushed.last) as Map<String, dynamic>,
        ).systemName,
        'SNES',
      );

      // A merge that throws is contained.
      expect(
        await bridge.forward((current) => throw StateError('boom')),
        isFalse,
      );
      expect(bridge.latest!.backgroundColor, 0xFF000000);

      // Outside iOS nothing is pushed.
      final elsewhere = SecondaryDisplayBridge.forTesting(
        service: subject,
        supported: false,
      );
      expect(
        await elsewhere.forward((current) => current.copyWith(isOled: false)),
        isFalse,
      );
      expect(elsewhere.latest, isNull);
      expect(native.pushed, hasLength(2));
    });
  });

  group('producers', () {
    SecondaryDisplayStateData lastPushed() => SecondaryDisplayStateData.fromJson(
      jsonDecode(native.pushed.last) as Map<String, dynamic>,
    );

    test('the app tabs forward the Android arguments to the TV menu', () async {
      final bridge = SecondaryDisplayBridge.forTesting(service: service());
      final producer = AppScreenSecondaryDisplay(bridge: bridge);
      // The systems grid left a console with its art on the TV.
      expect(
        await bridge.forward(
          (current) => current.copyWith(
            systemName: 'SNES',
            systemLogo: 'assets/images/logos/snes.webp',
            isLogoAsset: true,
            systemBackground: '/backgrounds/snes.webp',
            gameFanart: '/fanarts/game.png',
            gameScreenshot: '/screenshots/game.png',
            gameWheel: '/wheels/game.png',
            gameVideo: '/videos/game.mp4',
            isGameSelected: true,
            useFluidShader: false,
          ),
        ),
        isTrue,
      );

      expect(
        await producer.tabChanged(
          index: AppTabs.search,
          isOled: true,
          backgroundColor: 0xFF000000,
          themeName: 'oled',
        ),
        isTrue,
      );
      expect(native.pushed, hasLength(2));
      final search = lastPushed();
      expect(search.systemName, 'Search');
      expect(search.useFluidShader, isTrue);
      expect(search.isOled, isTrue);
      expect(search.backgroundColor, 0xFF000000);
      expect(search.themeName, 'oled');
      expect(search.isGameSelected, isFalse);
      expect(search.systemLogo, isNull);
      expect(search.systemBackground, isNull);
      expect(search.gameFanart, isNull);
      expect(search.gameScreenshot, isNull);
      expect(search.gameWheel, isNull);
      expect(search.gameVideo, isNull);
      expect(search.gameImageBytes, isNull);

      // Every tab the bottom screen names; the consoles tab has no name.
      for (final entry in <int, String>{
        AppTabs.achievements: 'Achievements',
        AppTabs.scraper: 'Scraper',
        AppTabs.settings: 'Settings',
        AppTabs.library: 'Library',
        AppTabs.consoles: '',
      }.entries) {
        expect(
          await producer.tabChanged(
            index: entry.key,
            isOled: false,
            backgroundColor: 0xFF102030,
            themeName: 'dark',
          ),
          isTrue,
        );
        expect(lastPushed().systemName, entry.value, reason: '${entry.key}');
      }
      expect(native.pushed, hasLength(7));

      // The systems tab pushes its own state (systems grid): nothing here.
      expect(
        await producer.tabChanged(
          index: AppTabs.systems,
          isOled: false,
          backgroundColor: 0xFF102030,
          themeName: 'dark',
        ),
        isFalse,
      );
      expect(native.pushed, hasLength(7));
      expect(bridge.latest!.systemName, '');
    });

    test('a theme change forwards the theme fields and keeps the rest', () async {
      final bridge = SecondaryDisplayBridge.forTesting(service: service());
      final producer = AppScreenSecondaryDisplay(bridge: bridge);
      await producer.tabChanged(
        index: AppTabs.library,
        isOled: true,
        backgroundColor: 0xFF000000,
        themeName: 'oled',
      );

      expect(
        await producer.themeChanged(
          isOled: false,
          backgroundColor: 0xFF123456,
          themeName: 'dark',
        ),
        isTrue,
      );
      expect(native.pushed, hasLength(2));
      final themed = lastPushed();
      expect(themed.systemName, 'Library');
      expect(themed.useFluidShader, isTrue);
      expect(themed.isOled, isFalse);
      expect(themed.backgroundColor, 0xFF123456);
      expect(themed.themeName, 'dark');
    });

    test('outside iOS the tab and theme producers push nothing', () async {
      final producer = AppScreenSecondaryDisplay(
        bridge: SecondaryDisplayBridge.forTesting(
          service: service(),
          supported: false,
        ),
      );
      expect(producer.forwardsToTV, isFalse);
      expect(
        await producer.tabChanged(
          index: AppTabs.search,
          isOled: false,
          backgroundColor: 0xFF102030,
          themeName: 'dark',
        ),
        isFalse,
      );
      expect(
        await producer.themeChanged(
          isOled: true,
          backgroundColor: 0xFF000000,
          themeName: 'oled',
        ),
        isFalse,
      );
      expect(native.pushed, isEmpty);
    });
  });
}
