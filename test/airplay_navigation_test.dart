import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/config_model.dart';
import 'package:neostation/screens/airplay_screen.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/horizontal_swipe.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';

/// A small frontend fixture uses the real tab registry, drag recognizer,
/// controller translator, moving header and receiver page. Heavy startup,
/// scanning and native game sessions are deliberately outside this test.
class _Menu extends StatefulWidget {
  const _Menu({super.key});
  @override
  State<_Menu> createState() => _MenuState();
}

class _MenuState extends State<_Menu> {
  NavTab selected = NavTab.search;
  final visited = <NavTab>[];
  late final GamepadNavigation navigation;
  void cycle(int step) {
    if (selected == NavTab.airplay && !AirPlayScreen.canSwitchTabs) return;
    final next = cycleNavTab(
      visibleNavTabs(ConfigModel.empty),
      selected,
      step,
    )!;
    setState(() {
      selected = next;
      visited.add(next);
    });
  }

  @override
  void initState() {
    super.initState();
    navigation =
        GamepadNavigation(
            onNextTab: () => cycle(1),
            onPreviousTab: () => cycle(-1),
            onNavigateRight: () => cycle(1),
            onNavigateLeft: () => cycle(-1),
            onNavigateUp: AirPlayScreen.navigateUp,
            onNavigateDown: AirPlayScreen.navigateDown,
            onSelectItem: AirPlayScreen.selectCurrent,
            onBack: AirPlayScreen.backCurrent,
          )
          ..initialize()
          ..activate();
  }

  @override
  void dispose() {
    navigation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Column(
      children: [
        MainMenuTabStrip(
          tabs: visibleNavTabs(ConfigModel.empty),
          selected: selected,
          tabBuilder: (tab) => IconButton(
            icon: Icon(navTabSpec(tab).iconData ?? Icons.circle),
            onPressed: () => setState(() => selected = tab),
          ),
        ),
        Expanded(
          child: HorizontalSwipe(
            key: ValueKey('swipe-${selected.name}'),
            distanceThreshold: 64,
            velocityThreshold: 450,
            onSwipeLeft: () => cycle(1),
            onSwipeRight: () => cycle(-1),
            child: selected == NavTab.airplay
                ? AirPlayScreen(
                    onPreviousTab: () => cycle(-1),
                    onNextTab: () => cycle(1),
                  )
                : SizedBox.expand(child: Center(child: Text(selected.name))),
          ),
        ),
      ],
    ),
  );
}

Future<void> inputEvent(WidgetTester tester, String key, double value) async {
  // Dispatch through the test messenger's registered platform handler rather
  // than a ChannelBuffers drain that can belong to a completed fake-clock zone.
  final response = await tester.runAsync(
    () => tester.binding.defaultBinaryMessenger.handlePlatformMessage(
      'xyz.luan/gamepads',
      const StandardMethodCodec().encodeMethodCall(
        MethodCall('onGamepadEvent', {
          'gamepadId': 'test-pad',
          'time': DateTime.now().millisecondsSinceEpoch,
          'type': key.startsWith('axis') ? 'analog' : 'button',
          'key': key,
          'value': value,
        }),
      ),
      null,
    ),
  );
  expect(
    response,
    isNotNull,
    reason: 'the real platform parser must receive every input',
  );
}

void main() {
  final calls = <String>[];
  setUp(() {
    SfxService().setEnabled(false);
    calls.clear();
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (_) async => [],
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('neostation/neoplay'),
      (call) async {
        calls.add(call.method);
        return null;
      },
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('neostation/neoplay/events'),
      (_) async => null,
    );
  });
  tearDown(() async {
    SfxService().setEnabled(true);
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      null,
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('neostation/neoplay'),
      null,
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('neostation/neoplay/events'),
      null,
    );
  });
  Future<GlobalKey<_MenuState>> mount(WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(844, 390));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final key = GlobalKey<_MenuState>();
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (_, child) => MaterialApp(home: _Menu(key: key)),
      ),
    );
    await tester.pumpAndSettle();
    return key;
  }

  for (final duration in [
    const Duration(milliseconds: 600),
    const Duration(milliseconds: 80),
  ]) {
    testWidgets(
      'slow/fast touch stops on AirPlay once then reaches Achievements: $duration',
      (tester) async {
        final key = await mount(tester);
        Future<void> swipe(bool left) async {
          await tester.timedDrag(
            find.byType(HorizontalSwipe),
            Offset(left ? -120 : 120, 0),
            duration,
          );
          await tester.pumpAndSettle();
        }

        await swipe(true);
        expect(key.currentState!.selected, NavTab.airplay);
        expect(
          calls,
          isEmpty,
          reason: 'visiting AirPlay never starts discovery',
        );
        expect(
          tester
              .getRect(find.byKey(const ValueKey('main-menu-tab-indicator')))
              .left,
          tester
              .getRect(find.byKey(const ValueKey('main-menu-cell-airplay')))
              .left,
        );
        await swipe(true);
        expect(key.currentState!.selected, NavTab.achievements);
        await swipe(false);
        expect(key.currentState!.selected, NavTab.airplay);
        await swipe(false);
        expect(key.currentState!.visited, [
          NavTab.airplay,
          NavTab.achievements,
          NavTab.airplay,
          NavTab.search,
        ]);
        expect(
          calls.where(
            (c) => c == 'discover' || c == 'connect' || c == 'disconnect',
          ),
          isEmpty,
        );
        await tester.pumpWidget(const SizedBox());
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );
  }

  testWidgets(
    'keyboard, D-pad, stick and bumpers use the same cycle without double dispatch',
    (tester) async {
      final key = await mount(tester);
      await tester.sendKeyEvent(LogicalKeyboardKey.keyE);
      await tester.pumpAndSettle();
      expect(key.currentState!.selected, NavTab.airplay);
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 75)),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.keyE);
      await tester.pumpAndSettle();
      expect(key.currentState!.selected, NavTab.achievements);
      // Linux host events enter the actual gamepad translator and repeat owner.
      // iOS named-event mappings are covered independently by its bridge tests.
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 180)),
      );
      expect(key.currentState!.navigation.isActive, isTrue);
      for (final input in [
        ('axis_6', -32767.0),
        ('axis_0', -32767.0),
        ('button-5', 1.0),
        ('button-5', 1.0),
      ]) {
        await inputEvent(tester, input.$1, input.$2);
        await tester.pump();
        await inputEvent(tester, input.$1, 0);
        await tester.pumpAndSettle();
        await tester.runAsync(
          () => Future<void>.delayed(
            Duration(milliseconds: input.$1.startsWith('axis') ? 150 : 75),
          ),
        );
      }
      expect(key.currentState!.visited, [
        NavTab.airplay,
        NavTab.achievements,
        NavTab.airplay,
        NavTab.search,
        NavTab.airplay,
        NavTab.achievements,
      ]);
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  testWidgets(
    'controller activation reaches receiver controls and back preserves the parent tab',
    (tester) async {
      final key = await mount(tester);
      key.currentState!.cycle(1);
      await tester.pumpAndSettle();
      expect(AirPlayScreen.canSwitchTabs, isTrue);
      AirPlayScreen.selectCurrent();
      await tester.pumpAndSettle();
      expect(
        find.byType(AlertDialog),
        findsOneWidget,
        reason: 'first action is Apple TV help',
      );
      expect(AirPlayScreen.canSwitchTabs, isFalse);
      key.currentState!.cycle(1);
      await tester.pumpAndSettle();
      expect(key.currentState!.selected, NavTab.airplay);
      AirPlayScreen.backCurrent();
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      AirPlayScreen.navigateDown();
      await tester.pump();
      AirPlayScreen.selectCurrent();
      await tester.pumpAndSettle();
      expect(calls, contains('discover'));
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
      expect(calls, isNot(contains('disconnect')));
      expect(tester.takeException(), isNull);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );
}
