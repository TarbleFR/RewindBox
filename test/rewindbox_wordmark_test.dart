import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/widgets/rewindbox_wordmark.dart';

void main() {
  for (final brightness in Brightness.values) {
    for (final width in <double>[64, 96, 112, 280]) {
      testWidgets('RewindBox wordmark $brightness at width $width', (tester) async {
        final semantics = tester.ensureSemantics();
        try {
          await tester.pumpWidget(MaterialApp(
            theme: ThemeData(brightness: brightness),
            home: Scaffold(body: Center(child: RewindBoxWordmark(
              width: width, height: width,
            ))),
          ));
          expect(find.text('RewindBox'), findsOneWidget);
          expect(find.bySemanticsLabel('RewindBox'), findsOneWidget);
          expect(tester.getSize(find.byType(RewindBoxWordmark)), Size(width, width));
          expect(tester.takeException(), isNull);
        } finally {
          semantics.dispose();
        }
      });
    }
  }
}
