import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/widgets/horizontal_swipe.dart';

Widget _host(Widget child) => MaterialApp(
  home: Scaffold(
    body: SizedBox(width: 320, height: 240, child: child),
  ),
);

void main() {
  testWidgets('deliberate left and right swipes fire once', (tester) async {
    var left = 0;
    var right = 0;
    await tester.pumpWidget(
      _host(
        HorizontalSwipe(
          onSwipeLeft: () => left++,
          onSwipeRight: () => right++,
          distanceThreshold: 64,
          velocityThreshold: 450,
          child: const SizedBox.expand(key: ValueKey('surface')),
        ),
      ),
    );

    await tester.timedDrag(
      find.byKey(const ValueKey('surface')),
      const Offset(-100, 0),
      const Duration(milliseconds: 400),
    );
    expect(left, 1);
    expect(right, 0);

    await tester.timedDrag(
      find.byKey(const ValueKey('surface')),
      const Offset(100, 0),
      const Duration(milliseconds: 400),
    );
    expect(left, 1);
    expect(right, 1);
  });

  testWidgets('short slow drag settles without switching', (tester) async {
    var switches = 0;
    await tester.pumpWidget(
      _host(
        HorizontalSwipe(
          onSwipeLeft: () => switches++,
          onSwipeRight: () => switches++,
          distanceThreshold: 64,
          velocityThreshold: 450,
          dragFeedback: true,
          child: const SizedBox.expand(key: ValueKey('surface')),
        ),
      ),
    );

    await tester.timedDrag(
      find.byKey(const ValueKey('surface')),
      const Offset(24, 0),
      const Duration(milliseconds: 500),
    );
    await tester.pumpAndSettle();
    expect(switches, 0);
  });

  testWidgets('nested horizontal control keeps its gesture', (tester) async {
    var parentSwitches = 0;
    var childUpdates = 0;
    await tester.pumpWidget(
      _host(
        HorizontalSwipe(
          onSwipeLeft: () => parentSwitches++,
          onSwipeRight: () => parentSwitches++,
          distanceThreshold: 64,
          velocityThreshold: 450,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onHorizontalDragUpdate: (_) => childUpdates++,
            child: const SizedBox.expand(key: ValueKey('horizontal-child')),
          ),
        ),
      ),
    );

    await tester.timedDrag(
      find.byKey(const ValueKey('horizontal-child')),
      const Offset(-120, 0),
      const Duration(milliseconds: 350),
    );
    expect(childUpdates, greaterThan(0));
    expect(parentSwitches, 0);
  });

  testWidgets('direction guard blocks a committed swipe', (tester) async {
    var switches = 0;
    var allowLeft = false;
    await tester.pumpWidget(
      _host(
        HorizontalSwipe(
          onSwipeLeft: () => switches++,
          canSwipeLeft: () => allowLeft,
          distanceThreshold: 64,
          velocityThreshold: 450,
          dragFeedback: true,
          child: const SizedBox.expand(key: ValueKey('surface')),
        ),
      ),
    );

    await tester.timedDrag(
      find.byKey(const ValueKey('surface')),
      const Offset(-100, 0),
      const Duration(milliseconds: 400),
    );
    await tester.pumpAndSettle();
    expect(switches, 0);

    allowLeft = true;
    await tester.timedDrag(
      find.byKey(const ValueKey('surface')),
      const Offset(-100, 0),
      const Duration(milliseconds: 400),
    );
    expect(switches, 1);
  });
}
