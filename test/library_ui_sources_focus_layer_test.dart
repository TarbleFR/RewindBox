// LibraryFocusGamepadLayer: a pushed Library route takes the controller
// (modal GamepadNavigationManager layer) and gives it back when closed; the
// d-pad moves Flutter's focus, A activates the focused control, B goes
// back, and the focus is drawn while the controller is used.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    // GamepadNavigation.initialize() lists controllers: none here.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
  });

  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('a pushed route holds the controller until it is closed', (
    tester,
  ) async {
    var baseActive = 0;
    var baseInactive = 0;
    GamepadNavigationManager.pushLayer(
      'library_focus_test_base',
      onActivate: () => baseActive++,
      onDeactivate: () => baseInactive++,
    );
    addTearDown(
      () => GamepadNavigationManager.popLayer('library_focus_test_base'),
    );
    baseActive = 0;

    var first = 0;
    var second = 0;
    var secondary = 0;
    late BuildContext hostContext;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            hostContext = context;
            return const Scaffold(body: Text('host'));
          },
        ),
      ),
    );

    Navigator.of(hostContext).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryFocusGamepadLayer(
          debugLabel: 'test',
          onSecondary: () => secondary++,
          child: Scaffold(
            body: Column(
              children: <Widget>[
                TextButton(
                  onPressed: () => first++,
                  child: const Text('first'),
                ),
                TextButton(
                  onPressed: () => second++,
                  child: const Text('second'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(baseInactive, 1, reason: 'the route layer took the controller');

    final layer = tester.state<LibraryFocusGamepadLayerState>(
      find.byType(LibraryFocusGamepadLayer),
    );

    // Nothing focused yet: the first move lands on the first control.
    expect(layer.move(TraversalDirection.down), isTrue);
    await tester.pump();
    expect(
      FocusManager.instance.highlightStrategy,
      FocusHighlightStrategy.alwaysTraditional,
      reason: 'the focus is drawn for controller users',
    );
    layer.activateFocused();
    await tester.pump();
    expect(first, 1);

    expect(layer.move(TraversalDirection.down), isTrue);
    await tester.pump();
    layer.activateFocused();
    await tester.pump();
    expect(second, 1);
    expect(first, 1);

    // A touch gives the highlight back to touch mode.
    await tester.tap(find.text('first'));
    await tester.pump();
    expect(first, 2);
    expect(
      FocusManager.instance.highlightStrategy,
      isNot(FocusHighlightStrategy.alwaysTraditional),
    );

    layer.back();
    await tester.pumpAndSettle();
    expect(find.text('first'), findsNothing);
    expect(find.text('host'), findsOneWidget);
    expect(baseActive, 1, reason: 'the screen below gets it back');
    expect(secondary, 0);
  });

  testWidgets('a route without its own layer on top is never acted behind', (
    tester,
  ) async {
    var pressed = 0;
    var secondary = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: LibraryFocusGamepadLayer(
          enableGamepad: false,
          onSecondary: () => secondary++,
          child: Scaffold(
            body: TextButton(
              onPressed: () => pressed++,
              child: const Text('behind'),
            ),
          ),
        ),
      ),
    );
    final layer = tester.state<LibraryFocusGamepadLayerState>(
      find.byType(LibraryFocusGamepadLayer),
    );
    final top = FocusNode(debugLabel: 'top');
    addTearDown(top.dispose);
    unawaited(
      Navigator.of(tester.element(find.text('behind'))).push<void>(
        MaterialPageRoute<void>(
          builder: (_) => Scaffold(
            body: TextButton(
              focusNode: top,
              autofocus: true,
              onPressed: () {},
              child: const Text('on top'),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(top.hasPrimaryFocus, isTrue);

    expect(layer.move(TraversalDirection.down), isFalse);
    layer.activateFocused();
    layer.activateFocused();
    layer.secondary();
    await tester.pump();
    expect(top.hasPrimaryFocus, isTrue, reason: 'the focus stays on top');
    expect(pressed, 0);
    expect(secondary, 0);

    // B closes the route on top; the layer then drives its own route again.
    layer.back();
    await tester.pumpAndSettle();
    expect(find.text('on top'), findsNothing);
    expect(layer.move(TraversalDirection.down), isTrue);
    await tester.pump();
    layer.activateFocused();
    layer.secondary();
    await tester.pump();
    expect(pressed, 1);
    expect(secondary, 1);
  });

  testWidgets('a custom back action replaces the pop', (tester) async {
    var backs = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: LibraryFocusGamepadLayer(
          enableGamepad: false,
          onBack: () => backs++,
          child: const Scaffold(body: Text('page')),
        ),
      ),
    );
    tester
        .state<LibraryFocusGamepadLayerState>(
          find.byType(LibraryFocusGamepadLayer),
        )
        .back();
    expect(backs, 1);
    expect(find.text('page'), findsOneWidget);
  });

  testWidgets('a focus ring outlines the focused control', (tester) async {
    final node = FocusNode();
    addTearDown(node.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: LibraryFocusRing(
            child: TextButton(
              focusNode: node,
              onPressed: () {},
              child: const Text('ring'),
            ),
          ),
        ),
      ),
    );
    BoxDecoration decoration() =>
        tester
                .widget<DecoratedBox>(
                  find
                      .descendant(
                        of: find.byType(LibraryFocusRing),
                        matching: find.byType(DecoratedBox),
                      )
                      .first,
                )
                .decoration
            as BoxDecoration;

    expect((decoration().border! as Border).top.color, Colors.transparent);
    node.requestFocus();
    await tester.pump();
    expect(
      (decoration().border! as Border).top.color,
      isNot(Colors.transparent),
    );
  });
}
