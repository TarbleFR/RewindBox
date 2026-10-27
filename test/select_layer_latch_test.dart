// The `⋯` menu of the game views (docs: the Select chord layer of
// GameActionButtons) driven through the real GamepadNavigation. Controller
// events are injected on the gamepads plugin channel with the Linux button
// numbering the Dart tests run with (A 0, B 1, X 2, Y 3, Select 6). The
// navigation debounces with the wall clock, so everything runs in real time.
//
// Regression: a Select tap only showed the menu while the button was down and
// also muted the preview on release, so with a controller the `⋯` menu opened
// and shut again within a frame or two (maintainer video, 27 October 2026).
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:neostation/utils/select_tap.dart';

const _a = '0', _b = '1', _x = '2', _y = '3', _select = '6';

Future<void> _wait(WidgetTester tester, int ms) =>
    tester.runAsync(() => Future<void>.delayed(Duration(milliseconds: ms)));

Future<void> _edge(WidgetTester tester, String key, double value) async {
  await tester.runAsync(() async {
    await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
      'xyz.luan/gamepads',
      const StandardMethodCodec().encodeMethodCall(
        MethodCall('onGamepadEvent', <String, Object>{
          'gamepadId': 'pad-1',
          'time': 0,
          'type': 'button',
          'key': key,
          'value': value,
        }),
      ),
      null,
    );
    await Future<void>.delayed(const Duration(milliseconds: 40));
  });
}

/// One press and release, then past the action debounce.
Future<void> _tap(WidgetTester tester, String key) async {
  await _edge(tester, key, 1);
  await _edge(tester, key, 0);
  await _wait(tester, 150);
}

/// A Select tap, then past the chord window that confirms it was a tap.
Future<void> _selectTap(WidgetTester tester) async {
  await _tap(tester, _select);
  await _wait(tester, SelectTap.chordWindow.inMilliseconds + 100);
}

bool get _layerOpen => GamepadNavigation.selectHeldNotifier.value;

void main() {
  final calls = <String>[];
  late GamepadNavigation nav;

  GamepadNavigation build({required bool latch}) => GamepadNavigation(
    onSelectItem: () => calls.add('launch'),
    onBack: () => calls.add('back'),
    onXButton: () => calls.add('view-mode'),
    onFavorite: () => calls.add('favorite'),
    onSelectButton: () => calls.add('mute'),
    onSelectModifierA: () => calls.add('scrape'),
    onSelectModifierB: () => calls.add('legend'),
    onSelectModifierX: () => calls.add('context'),
    onSelectModifierY: () => calls.add('random'),
    latchSelectLayer: latch,
  );

  Future<void> start(WidgetTester tester, {bool latch = true}) async {
    SfxService().setEnabled(false);
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (_) async => <Object>[],
    );
    calls.clear();
    nav = build(latch: latch);
    await tester.runAsync(() async {
      nav.initialize();
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    nav.activate();
    // Past the reactivation grace of a freshly activated layer.
    await _wait(tester, 250);
  }

  tearDown(() {
    nav.dispose();
    GamepadNavigation.closeSelectLayer();
    SfxService().setEnabled(true);
  });

  testWidgets('a Select tap opens the menu and it stays open', (tester) async {
    await start(tester);
    await _selectTap(tester);
    expect(_layerOpen, isTrue);
    await _wait(tester, 1200);
    expect(_layerOpen, isTrue, reason: 'only a real closing action shuts it');
    expect(calls, isEmpty, reason: 'the tap no longer also mutes the preview');
  });

  testWidgets('A runs the menu action once and closes the menu', (
    tester,
  ) async {
    await start(tester);
    await _selectTap(tester);
    await _tap(tester, _a);
    expect(calls, ['scrape'], reason: 'the game underneath is not launched');
    expect(_layerOpen, isFalse);
    await _tap(tester, _a);
    expect(calls, ['scrape', 'launch'], reason: 'A is the screen\'s again');
  });

  testWidgets('X and Y run their menu actions', (tester) async {
    await start(tester);
    await _selectTap(tester);
    await _tap(tester, _x);
    await _selectTap(tester);
    await _tap(tester, _y);
    expect(calls, ['context', 'random']);
    expect(_layerOpen, isFalse);
  });

  testWidgets('B only closes the menu', (tester) async {
    await start(tester);
    await _selectTap(tester);
    await _tap(tester, _b);
    expect(_layerOpen, isFalse);
    expect(calls, isEmpty, reason: 'neither back nor the legend chord fires');
    await _tap(tester, _b);
    expect(calls, ['back']);
  });

  testWidgets('a second Select tap closes the menu', (tester) async {
    await start(tester);
    await _selectTap(tester);
    expect(_layerOpen, isTrue);
    await _selectTap(tester);
    expect(_layerOpen, isFalse);
    expect(calls, isEmpty);
  });

  testWidgets('holding Select still fires a chord and shows no menu after', (
    tester,
  ) async {
    await start(tester);
    await _edge(tester, _select, 1);
    expect(_layerOpen, isTrue);
    await _tap(tester, _y);
    await _edge(tester, _select, 0);
    await _wait(tester, SelectTap.chordWindow.inMilliseconds + 100);
    expect(calls, ['random']);
    expect(_layerOpen, isFalse);
  });

  testWidgets('the touch pill and the controller share the same menu', (
    tester,
  ) async {
    await start(tester);
    GamepadNavigation.toggleSelectLayer();
    expect(_layerOpen, isTrue);
    await _tap(tester, _a);
    expect(calls, ['scrape']);
    expect(_layerOpen, isFalse);
  });

  testWidgets('a background navigator going away leaves the menu open', (
    tester,
  ) async {
    await start(tester);
    await _selectTap(tester);
    final background = build(latch: true)..deactivate();
    background.dispose();
    expect(_layerOpen, isTrue);
    nav.deactivate();
    expect(_layerOpen, isFalse, reason: 'the focused screen closes it');
  });

  testWidgets('without the menu a Select tap keeps its own action', (
    tester,
  ) async {
    await start(tester, latch: false);
    await _selectTap(tester);
    expect(calls, ['mute']);
    expect(_layerOpen, isFalse);
  });
}
