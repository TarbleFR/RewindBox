import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/widgets/library_book_cover.dart';

const _artKey = ValueKey('test-cover-art');

void main() {
  Future<void> pumpCover(
    WidgetTester tester, {
    bool selected = false,
    bool rightToLeft = false,
    bool reduceMotion = false,
    bool tickerEnabled = true,
    VoidCallback? onTap,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: reduceMotion),
          child: Scaffold(
            body: Center(
              child: TickerMode(
                enabled: tickerEnabled,
                child: GestureDetector(
                  onTap: onTap,
                  child: SizedBox(
                    width: 160,
                    height: 220,
                    child: LibraryBookCover(
                      selected: selected,
                      rightToLeft: rightToLeft,
                      child: const ColoredBox(
                        key: _artKey,
                        color: Colors.deepPurple,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  testWidgets('selection opens and closes without changing the tile size', (
    tester,
  ) async {
    await pumpCover(tester);
    final closed = tester.getRect(find.byKey(_artKey));
    final tile = tester.getRect(find.byType(LibraryBookCover));
    await pumpCover(tester, selected: true);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)).width, lessThan(closed.width));
    expect(tester.getRect(find.byType(LibraryBookCover)), tile);
    expect(tester.binding.hasScheduledFrame, isFalse);
    await pumpCover(tester);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    expect(tester.takeException(), isNull);
  });

  testWidgets('manga opens from the opposite edge', (tester) async {
    await pumpCover(tester);
    final closed = tester.getRect(find.byKey(_artKey));
    await pumpCover(tester, selected: true);
    await tester.pumpAndSettle();
    final book = tester.getRect(find.byKey(_artKey));
    await pumpCover(tester, selected: true, rightToLeft: true);
    await tester.pumpAndSettle();
    final manga = tester.getRect(find.byKey(_artKey));
    expect(book.right, lessThan(closed.right));
    expect(manga.left, greaterThan(closed.left));
    expect(tester.takeException(), isNull);
  });

  testWidgets('touch preview never consumes or delays the parent tap', (
    tester,
  ) async {
    var taps = 0;
    await pumpCover(tester, onTap: () => taps++);
    final closed = tester.getRect(find.byKey(_artKey));
    final touch = await tester.startGesture(
      tester.getCenter(find.byType(LibraryBookCover)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 160));
    expect(tester.getRect(find.byKey(_artKey)).width, lessThan(closed.width));
    await touch.up();
    expect(taps, 1);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
  });

  testWidgets('cancelled touch and hover leave no animation running', (
    tester,
  ) async {
    await pumpCover(tester);
    final closed = tester.getRect(find.byKey(_artKey));
    final touch = await tester.startGesture(
      tester.getCenter(find.byType(LibraryBookCover)),
    );
    await tester.pump(const Duration(milliseconds: 160));
    await touch.cancel();
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: Offset.zero);
    await mouse.moveTo(tester.getCenter(find.byType(LibraryBookCover)));
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)).width, lessThan(closed.width));
    await mouse.moveTo(Offset.zero);
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    await mouse.removePointer();
    await tester.pumpWidget(const SizedBox.shrink());
    expect(tester.takeException(), isNull);
  });

  testWidgets('Reduce Motion keeps a static cover and immediate activation', (
    tester,
  ) async {
    var taps = 0;
    await pumpCover(tester, reduceMotion: true);
    final closed = tester.getRect(find.byKey(_artKey));
    await pumpCover(
      tester,
      selected: true,
      reduceMotion: true,
      onTap: () => taps++,
    );
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(_artKey)), closed);
    await tester.tap(find.byType(LibraryBookCover));
    expect(taps, 1);
    await tester.pumpAndSettle();
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('a scrolling gesture still scrolls the library', (tester) async {
    final scroll = ScrollController();
    addTearDown(scroll.dispose);
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListView(
            controller: scroll,
            children: [
              GestureDetector(
                onTap: () => taps++,
                child: const SizedBox(
                  height: 220,
                  child: LibraryBookCover(
                    child: ColoredBox(color: Colors.deepPurple),
                  ),
                ),
              ),
              const SizedBox(height: 1800),
            ],
          ),
        ),
      ),
    );
    await tester.drag(find.byType(LibraryBookCover), const Offset(0, -160));
    await tester.pumpAndSettle();
    expect(scroll.offset, greaterThan(0));
    expect(taps, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('hidden and disposed covers do not keep a ticker alive', (
    tester,
  ) async {
    await pumpCover(tester);
    await pumpCover(tester, selected: true);
    await tester.pump(const Duration(milliseconds: 60));
    await pumpCover(tester, selected: true, tickerEnabled: false);
    await tester.pumpAndSettle();
    expect(tester.binding.hasScheduledFrame, isFalse);
    await tester.pumpWidget(const SizedBox.shrink());
    expect(tester.takeException(), isNull);
  });
}
