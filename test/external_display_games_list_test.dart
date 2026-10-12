// Build 447 (docs/external-display-universal.md § 8 bis): the games list
// relays its selection to the iOS TV menu through SecondaryDisplayBridge,
// images only, and only while a TV shows the menu; the producers that change
// on every selection (systems grid and carousel, games lists) push their
// current selection again when a TV starts showing the menu. Channel
// behaviour with a fake native coordinator; no iPhone or Apple TV claim.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:external_display/external_display.dart';
import 'package:flutter/material.dart';
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
          case 'configureMenuEngine':
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

  group('selections follow the TV (review of 12 October 2026, m7-m9)', () {
    late StreamController<ExternalDisplayState> events;
    late ExternalDisplayService service;

    setUp(() async {
      events = StreamController<ExternalDisplayState>.broadcast();
      state = nativeState(connected: false);
      service = ExternalDisplayService.forTesting(events: events.stream);
      await service.init();
    });

    tearDown(() async {
      service.dispose();
      await events.close();
    });

    Future<void> emit(Map<String, Object?> native) async {
      events.add(ExternalDisplayState.fromMap(native));
      await Future<void>.delayed(Duration.zero);
    }

    SecondaryDisplayBridge bridge({bool supported = true}) =>
        SecondaryDisplayBridge.forTesting(service: service, supported: supported);

    test('forwardSelection pushes only while a TV shows the menu', () async {
      final subject = bridge();
      Future<bool> select(String game) => subject.forwardSelection(
        (current) => SecondaryDisplayBridge.gameSelected(
          current,
          systemName: 'NES',
          gameId: game,
        ),
      );
      expect(await select('/roms/nes/a.nes'), isFalse);
      expect(pushed, isEmpty, reason: 'no TV: no channel message');

      await emit(nativeState());
      expect(await select('/roms/nes/a.nes'), isTrue);
      expect(pushed.single['gameId'], '/roms/nes/a.nes');

      await emit(nativeState(menuOnTV: false));
      expect(await select('/roms/nes/b.nes'), isFalse);
      await emit(nativeState(enabled: false));
      expect(await select('/roms/nes/b.nes'), isFalse);
      expect(pushed, hasLength(1));
      expect(subject.latest?.gameId, '/roms/nes/a.nes');
    });

    test('a producer pushes its selection again when a TV starts showing the menu',
        () async {
      final subject = bridge();
      final grid = _Producer(subject, 'SNES');
      final follower = subject.followSelections(grid, _Producer.reforward);
      expect(subject.followerCount, 1);
      expect(
        identical(subject.followSelections(grid, _Producer.reforward), follower),
        isTrue,
        reason: 'one follower per producer',
      );
      expect(subject.followerCount, 1);

      await emit(nativeState(connected: false));
      expect(grid.reforwarded, 0, reason: 'nothing to show the selection on');

      await emit(nativeState());
      expect(grid.reforwarded, 1);
      expect(pushed.single['systemName'], 'SNES');

      await emit(<String, Object?>{...nativeState(), 'screenScale': 2.0});
      expect(grid.reforwarded, 1, reason: 'still showing: no second push');

      for (final off in <Map<String, Object?>>[
        nativeState(menuOnTV: false),
        nativeState(enabled: false),
        nativeState(connected: false),
      ]) {
        await emit(off);
        await emit(nativeState());
      }
      expect(grid.reforwarded, 4, reason: 'menu, output and TV each back on');
      expect(pushed, hasLength(4));

      follower.cancel();
      follower.cancel();
      expect(follower.active, isFalse);
      expect(subject.followerCount, 0);
      await emit(nativeState(connected: false));
      await emit(nativeState());
      expect(grid.reforwarded, 4, reason: 'a disposed producer is not called');
    });

    test('the producer opened last pushes last; a failing one stops nobody',
        () async {
      final subject = bridge();
      final grid = _Producer(subject, 'SNES');
      final failing = _Producer(subject, 'boom', fail: true);
      final list = _Producer(subject, 'Super Mario World');
      subject.followSelections(grid, _Producer.reforward);
      subject.followSelections(failing, _Producer.reforward);
      subject.followSelections(list, _Producer.reforward);
      await emit(nativeState());
      expect(grid.reforwarded, 1);
      expect(failing.reforwarded, 1);
      expect(list.reforwarded, 1);
      await Future<void>.delayed(Duration.zero);
      expect(pushed.map((json) => json['systemName']).toList(), <Object?>[
        'SNES',
        'Super Mario World',
      ]);
      expect(subject.latest?.systemName, 'Super Mario World');
    });

    test('outside iOS nothing is followed', () async {
      final subject = bridge(supported: false);
      final grid = _Producer(subject, 'SNES');
      final follower = subject.followSelections(grid, _Producer.reforward);
      expect(follower.active, isFalse);
      expect(subject.followerCount, 0);
      await emit(nativeState());
      expect(grid.reforwarded, 0);
      expect(pushed, isEmpty);
    });

    testWidgets('a producer widget follows from initState to dispose', (
      tester,
    ) async {
      final subject = bridge();
      await tester.pumpWidget(_ProducerWidget(bridge: subject, systemName: 'NES'));
      expect(subject.followerCount, 1);
      await tester.runAsync(() => emit(nativeState()));
      await tester.pump();
      expect(find.text('NES 1'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      expect(subject.followerCount, 0, reason: 'cancelled in dispose');
      await tester.runAsync(() async {
        await emit(nativeState(connected: false));
        await emit(nativeState());
      });
      expect(tester.takeException(), isNull);
    });

    test('systemSelected is the console view of the Android push', () {
      final playing = SecondaryDisplayBridge.gameSelected(
        SecondaryDisplayStateData(systemName: 'WELCOME'),
        systemName: 'NES',
        gameId: '/roms/nes/a.nes',
        fanart: '/f.png',
        screenshot: '/s.png',
        wheel: '/w.png',
      ).copyWith(gameVideo: '/v.mp4', useFluidShader: true);
      final withBackground = SecondaryDisplayBridge.systemSelected(
        playing,
        systemName: 'Super Nintendo',
        backgroundColor: 0xFF102030,
        systemLogo: 'assets/images/logos/snes.webp',
        isLogoAsset: true,
        systemBackground: '/backgrounds/snes.webp',
        shaderColor1: 0xFF000001,
        shaderColor2: 0xFF000002,
        isOled: true,
      );
      expect(withBackground.systemName, 'Super Nintendo');
      expect(withBackground.backgroundColor, 0xFF102030);
      expect(withBackground.systemLogo, 'assets/images/logos/snes.webp');
      expect(withBackground.isLogoAsset, isTrue);
      expect(withBackground.systemBackground, '/backgrounds/snes.webp');
      expect(withBackground.isBackgroundAsset, isFalse);
      expect(withBackground.useShader, isFalse);
      expect(withBackground.shaderColor1, 0xFF000001);
      expect(withBackground.shaderColor2, 0xFF000002);
      expect(withBackground.isOled, isTrue);
      expect(withBackground.isGameSelected, isFalse);
      expect(withBackground.useFluidShader, isFalse);
      for (final cleared in <Object?>[
        withBackground.gameFanart,
        withBackground.gameScreenshot,
        withBackground.gameWheel,
        withBackground.gameVideo,
        withBackground.gameImageBytes,
        withBackground.gameId,
      ]) {
        expect(cleared, isNull);
      }
      final shader = SecondaryDisplayBridge.systemSelected(
        withBackground,
        systemName: 'NES',
        backgroundColor: 0xFF000000,
        systemLogo: null,
        isLogoAsset: false,
        systemBackground: null,
        isOled: false,
      );
      expect(shader.systemBackground, isNull, reason: 'cleared, not kept');
      expect(shader.useShader, isTrue);
      expect(
        shader.systemLogo,
        'assets/images/logos/snes.webp',
        reason: 'merged like the Android push: the producers always name a logo',
      );
    });

    test('the three selection producers follow the bridge', () {
      String source(String path) => File(path).readAsStringSync();
      final carousel = source(
        'lib/screens/systems_screen/my_systems_section/my_systems_carousel.dart',
      );
      final grid = source(
        'lib/screens/systems_screen/my_systems_section/my_systems_grid/theme_background.dart',
      );
      final games = source('lib/screens/game_screen/my_games_list.dart');
      final gamesRelay = source(
        'lib/screens/game_screen/my_games_list/secondary_display.dart',
      );
      // Followed for the life of the producer, with a callback that holds
      // no reference to it (static or top-level), cancelled in dispose.
      expect(
        carousel,
        contains(
          'SecondaryDisplayBridge.instance.followSelections(\n      this,\n      _reforwardToTV,\n    );',
        ),
      );
      expect(carousel, contains('static void _reforwardToTV(_MySystemsCarouselState state)'));
      expect(carousel, contains('_tvSelectionFollower?.cancel();'));
      expect(
        games,
        contains(
          'SecondaryDisplayBridge.instance.followSelections(\n      this,\n      _reforwardToTV,\n    );',
        ),
      );
      expect(games, contains('static void _reforwardToTV(_SystemGamesListState state)'));
      expect(games, contains('_tvSelectionFollower?.cancel();'));
      // The grid's state lives in a file of its own: it follows at its
      // first push, held weakly, its callback checks `mounted`.
      expect(grid, contains('bridge.followSelections<_SystemCardGridViewState>('));
      expect(grid, contains('void _reforwardGridSelectionToTV(_SystemCardGridViewState state) {'));
      expect(grid, contains('if (state.mounted) state._updateSecondaryScreenName();'));
      // Forwarded only while a TV shows the menu.
      expect(RegExp(r'bridge\.forward\(').hasMatch(grid), isFalse);
      expect(grid, contains('bridge.forwardSelection('));
      expect(RegExp(r'bridge\.forward\(').hasMatch(carousel), isFalse);
      expect(carousel, contains('bridge.forwardSelection('));
      expect(carousel, contains('final toTV = bridge.forwardsSelections;'));
      expect(
        gamesRelay,
        contains('if (SecondaryDisplayBridge.instance.forwardsSelections) {'),
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

/// A producer that changes on every selection (systems grid, carousel,
/// games list) as the bridge sees it.
class _Producer {
  _Producer(this.bridge, this.systemName, {this.fail = false});

  final SecondaryDisplayBridge bridge;
  final String systemName;
  final bool fail;
  int reforwarded = 0;

  /// Static, as the real producers' callbacks: the bridge holds the
  /// producer weakly.
  static void reforward(_Producer producer) {
    producer.reforwarded++;
    if (producer.fail) throw StateError('boom');
    unawaited(
      producer.bridge.forwardSelection(
        (current) => current.copyWith(systemName: producer.systemName),
      ),
    );
  }
}

class _ProducerWidget extends StatefulWidget {
  const _ProducerWidget({required this.bridge, required this.systemName});

  final SecondaryDisplayBridge bridge;
  final String systemName;

  @override
  State<_ProducerWidget> createState() => _ProducerWidgetState();
}

class _ProducerWidgetState extends State<_ProducerWidget> {
  SecondaryDisplaySelectionFollower? _follower;
  int _reforwarded = 0;

  @override
  void initState() {
    super.initState();
    _follower = widget.bridge.followSelections(this, _reforward);
  }

  static void _reforward(_ProducerWidgetState state) {
    if (!state.mounted) return;
    state.setState(() => state._reforwarded++);
    unawaited(
      state.widget.bridge.forwardSelection(
        (current) => current.copyWith(systemName: state.widget.systemName),
      ),
    );
  }

  @override
  void dispose() {
    _follower?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Directionality(
    textDirection: TextDirection.ltr,
    child: Text('${widget.systemName} $_reforwarded'),
  );
}
