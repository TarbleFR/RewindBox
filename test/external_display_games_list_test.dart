// Build 447 (docs/external-display-universal.md § 8 bis): the games list
// relays its selection to the iOS TV menu through SecondaryDisplayBridge,
// images only, and only while a TV shows the menu. Channel behaviour with a
// fake native coordinator; no iPhone or Apple TV claim.
import 'dart:convert';

import 'package:external_display/external_display.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/services/external_display_service.dart';
import 'package:neostation/services/secondary_display_bridge.dart';

Map<String, Object?> nativeState({
  bool supported = true,
  bool connected = true,
  bool enabled = true,
  bool menuOnTV = true,
}) => <String, Object?>{
  'supported': supported,
  'connected': connected,
  'content': connected ? 'menu' : 'none',
  'screenWidth': 1920.0,
  'screenHeight': 1080.0,
  'screenScale': 1.0,
  'mode': 0,
  'enabled': enabled,
  'menuOnTV': menuOnTV,
  'mirroringActive': false,
  'accessoryStatus': 'unavailable',
  'sceneRole': 'scene',
  'menuEngine': 'attached',
};

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  late Map<String, Object?> state;
  late List<Map<String, Object?>> pushed;

  setUp(() {
    state = nativeState();
    pushed = <Map<String, Object?>>[];
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      (call) async {
        switch (call.method) {
          case 'getState':
            return state;
          case 'pushMenuState':
            final json = (call.arguments as Map)['json'] as String;
            pushed.add((jsonDecode(json) as Map).cast<String, Object?>());
            return true;
        }
        throw MissingPluginException();
      },
    );
  });

  tearDown(() {
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      null,
    );
  });

  Future<SecondaryDisplayBridge> bridgeWith({bool supported = true}) async {
    final service = ExternalDisplayService.forTesting(
      events: const Stream<ExternalDisplayState>.empty(),
    );
    await service.refresh();
    return SecondaryDisplayBridge.forTesting(
      service: service,
      supported: supported,
    );
  }

  group('forwardsSelections', () {
    test('true only while a TV shows the menu', () async {
      expect((await bridgeWith()).forwardsSelections, isTrue);

      state = nativeState(connected: false);
      expect((await bridgeWith()).forwardsSelections, isFalse);

      state = nativeState(enabled: false);
      expect((await bridgeWith()).forwardsSelections, isFalse,
          reason: 'system mirroring chosen: no TV menu');

      state = nativeState(menuOnTV: false);
      expect((await bridgeWith()).forwardsSelections, isFalse);

      state = nativeState(supported: false);
      expect((await bridgeWith()).forwardsSelections, isFalse);
    });

    test('false outside iOS and before the first native state', () async {
      expect((await bridgeWith(supported: false)).forwardsSelections, isFalse);
      final unread = SecondaryDisplayBridge.forTesting(
        service: ExternalDisplayService.forTesting(
          events: const Stream<ExternalDisplayState>.empty(),
        ),
      );
      expect(unread.forwardsSelections, isFalse);
    });
  });

  group('gameSelected', () {
    final playing = SecondaryDisplayStateData(
      systemName: 'NES',
      gameVideo: '/media/nes/videos/a.mp4',
      gameImageBytes: Uint8List.fromList(<int>[1, 2, 3]),
      gameFanart: '/old/fanart.png',
      showAchievementPanel: true,
    );

    test('images only: no video, no artwork bytes on the TV', () {
      final next = SecondaryDisplayBridge.gameSelected(
        playing,
        systemName: 'Super Nintendo',
        gameId: '/roms/snes/zelda.sfc',
        fanart: '/media/snes/fanarts/zelda.png',
        screenshot: '/media/snes/screenshots/zelda.png',
        wheel: '/media/snes/wheels/zelda.png',
        backgroundColor: 0xFF101010,
        isGameLaunching: true,
        isScraperLoggedIn: true,
      );
      expect(next.systemName, 'Super Nintendo');
      expect(next.isGameSelected, isTrue);
      expect(next.gameId, '/roms/snes/zelda.sfc');
      expect(next.gameFanart, '/media/snes/fanarts/zelda.png');
      expect(next.gameScreenshot, '/media/snes/screenshots/zelda.png');
      expect(next.gameWheel, '/media/snes/wheels/zelda.png');
      expect(next.gameVideo, isNull);
      expect(next.gameImageBytes, isNull);
      expect(next.backgroundColor, 0xFF101010);
      expect(next.isGameLaunching, isTrue);
      expect(next.isScraperLoggedIn, isTrue);
      expect(next.showAchievementPanel, isFalse);
    });

    test('missing images are cleared, not kept from the last game', () {
      final next = SecondaryDisplayBridge.gameSelected(
        playing,
        systemName: 'NES',
        gameId: '/roms/nes/b.nes',
      );
      expect(next.gameFanart, isNull);
      expect(next.gameScreenshot, isNull);
      expect(next.gameWheel, isNull);
    });
  });

  group('showsSelection', () {
    final shown = SecondaryDisplayBridge.gameSelected(
      SecondaryDisplayStateData(systemName: 'WELCOME'),
      systemName: 'NES',
      gameId: '/roms/nes/a.nes',
      fanart: '/f.png',
      wheel: '/w.png',
    );

    test('the same selection is skipped', () {
      expect(
        SecondaryDisplayBridge.showsSelection(
          shown,
          systemName: 'NES',
          gameId: '/roms/nes/a.nes',
          fanart: '/f.png',
          wheel: '/w.png',
        ),
        isTrue,
      );
    });

    test('any change pushes again', () {
      bool shows({
        String systemName = 'NES',
        String? gameId = '/roms/nes/a.nes',
        String? fanart = '/f.png',
        String? screenshot,
        String? wheel = '/w.png',
        bool launching = false,
      }) => SecondaryDisplayBridge.showsSelection(
        shown,
        systemName: systemName,
        gameId: gameId,
        fanart: fanart,
        screenshot: screenshot,
        wheel: wheel,
        isGameLaunching: launching,
      );
      expect(shows(systemName: 'SNES'), isFalse);
      expect(shows(gameId: '/roms/nes/b.nes'), isFalse);
      expect(shows(fanart: null), isFalse);
      expect(shows(screenshot: '/s.png'), isFalse);
      expect(shows(wheel: null), isFalse);
      expect(shows(launching: true), isFalse);
      expect(
        SecondaryDisplayBridge.showsSelection(
          null,
          systemName: 'NES',
          gameId: '/roms/nes/a.nes',
        ),
        isFalse,
      );
      expect(
        SecondaryDisplayBridge.showsSelection(
          shown.copyWith(isGameSelected: false),
          systemName: 'NES',
          gameId: '/roms/nes/a.nes',
          fanart: '/f.png',
          wheel: '/w.png',
        ),
        isFalse,
        reason: 'the console view is shown: the game must be pushed',
      );
    });
  });

  test('the forwarded JSON reaches the TV menu without video or bytes',
      () async {
    final bridge = await bridgeWith();
    final accepted = await bridge.forward(
      (current) => SecondaryDisplayBridge.gameSelected(
        current.copyWith(
          gameVideo: '/v.mp4',
          gameImageBytes: Uint8List.fromList(<int>[9]),
        ),
        systemName: 'NES',
        gameId: '/roms/nes/a.nes',
        fanart: '/f.png',
      ),
    );
    expect(accepted, isTrue);
    expect(pushed, hasLength(1));
    final json = pushed.single;
    expect(json['systemName'], 'NES');
    expect(json['gameFanart'], '/f.png');
    expect(json['isGameSelected'], isTrue);
    expect(json['gameVideo'], isNull);
    expect(json['gameImageBytes'], isNull);
    expect(bridge.latest?.gameId, '/roms/nes/a.nes');
  });
}
